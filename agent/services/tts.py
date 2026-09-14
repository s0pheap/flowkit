"""Narration TTS: Gemini (default), Gemini via the Mindlogic gateway, Kokoro (a self-hosted server),
Piper (local), gTTS, or OmniVoice.

The language of each line decides which engines can speak it: a Korean or Khmer
line never goes to Kokoro, which only knows nine languages. When TTS_ENGINE can't
speak a line (unsupported language, Gemini out of quota, Kokoro server down),
narration switches to ``TTS_FALLBACK_ENGINE`` (Piper by default) instead of failing.

Whatever engine speaks, every narration wav gets a ``*.words.json`` sidecar with
per-word timings, which the subtitle writer reads. The sidecar also records the
engine, so scenes spoken by a fallback voice can be redone once Gemini is back.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
import wave
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx

from agent import config
from agent.services import gemini_tts, whisper_timing

logger = logging.getLogger(__name__)

# Default to python3.10 (has torch/torchaudio/omnivoice); override with TTS_PYTHON_BIN if needed
PYTHON_BIN = os.environ.get("TTS_PYTHON_BIN", "python3.10")


class TTSUnavailableError(RuntimeError):
    """Neither TTS_ENGINE nor any fallback engine could speak the line."""


class TTSEngineUnavailable(RuntimeError):
    """This engine can't speak this line right now (server down, language not supported); a fallback may."""


# ─── Language of a line ──────────────────────────────────────

# Scripts that give a line's language away, and the languages that write with them.
_SCRIPTS = [
    (re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]"), ("ko",)),
    (re.compile(r"[ក-៿᧠-᧿]"), ("km",)),
    (re.compile(r"[぀-ヿ]"), ("ja",)),
    (re.compile(r"[฀-๿]"), ("th",)),
    (re.compile(r"[຀-໿]"), ("lo",)),
    (re.compile(r"[ऀ-ॿ]"), ("hi", "mr", "ne")),
    (re.compile(r"[؀-ۿ]"), ("ar", "fa", "ur")),
    (re.compile(r"[Ѐ-ӿ]"), ("ru", "uk", "bg", "sr", "kk")),
    (re.compile(r"[一-鿿]"), ("zh", "ja")),
]


def base_lang(lang: Optional[str]) -> str:
    """"en-US" → "en"; empty → TTS_LANG."""
    return re.split(r"[-_]", (lang or config.TTS_LANG or "en").strip().lower())[0]


def text_language(text: str, lang: Optional[str] = None) -> str:
    """The language to speak ``text`` in: its script when that settles it, else the project language."""
    base = base_lang(lang)
    for pattern, languages in _SCRIPTS:
        if pattern.search(text):
            return base if base in languages else languages[0]
    return base


# ─── Kokoro (self-hosted Kokoro-82M server) ──────────────────

# Kokoro picks its language from the first letter of the voice name.
KOKORO_LANGS = {"en": "a", "es": "e", "fr": "f", "hi": "h", "it": "i", "pt": "p", "ja": "j", "zh": "z"}
KOKORO_DEFAULT_VOICES = {"a": "af_heart", "b": "bf_emma", "e": "ef_dora", "f": "ff_siwis", "h": "hf_alpha",
                         "i": "if_sara", "p": "pf_dora", "j": "jf_alpha", "z": "zf_xiaobei"}
_KOKORO_VOICE = re.compile(r"^([a-z])[a-z]_[a-z0-9]+$")


def kokoro_voice(lang: str, voice: Optional[str] = None) -> Optional[str]:
    """A Kokoro voice for ``lang``: the requested one or KOKORO_VOICE when it speaks that language, else a default.

    None when Kokoro has no voice for the language.
    """
    code = KOKORO_LANGS.get(lang)
    if not code:
        return None
    allowed = ("a", "b") if code == "a" else (code,)
    for candidate in (voice, config.KOKORO_VOICE):
        match = _KOKORO_VOICE.match(candidate or "")
        if match and match.group(1) in allowed:
            return candidate
    return KOKORO_DEFAULT_VOICES[code]


def _kokoro_url() -> str:
    url = config.KOKORO_URL.strip().rstrip("/")
    return url if url.endswith("/tts") else f"{url}/tts"


async def _generate_kokoro_tts(text: str, output_path: str, lang: str, voice: Optional[str], speed: float) -> float:
    """POST the line to the Kokoro server (``{text, voice, speed, lang_code}`` → wav). Returns duration."""
    name = kokoro_voice(lang, voice)
    if not name:
        raise TTSEngineUnavailable(f"Kokoro can't speak {lang!r}")
    body = {"text": text, "voice": name, "speed": min(max(speed, 0.5), 3.0), "lang_code": name[0]}
    try:
        async with httpx.AsyncClient(timeout=config.KOKORO_TIMEOUT) as client:
            resp = await client.post(_kokoro_url(), json=body)
    except httpx.HTTPError as e:
        raise TTSEngineUnavailable(f"Kokoro server {_kokoro_url()} is unreachable: {type(e).__name__} {e}"[:300])
    if resp.status_code != 200:
        # Also a 400: the server answers that way when a language's extras aren't installed
        # ("No module named 'pyopenjtalk'" for Japanese), so the fallback should take the line.
        raise TTSEngineUnavailable(f"Kokoro HTTP {resp.status_code} for voice {name}: {resp.text[:250]}")
    if resp.content[:4] != b"RIFF":
        raise TTSEngineUnavailable(f"Kokoro server returned {resp.headers.get('content-type')}, not a wav")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    return gemini_tts.wav_duration(out)


# ─── Mindlogic API gateway (Gemini TTS) ──────────────────────

MINDLOGIC_MAX_CHARS = 4000
_MINDLOGIC_RETRY_DELAYS = (3, 10, 30)  # 429: the gateway allows 120 requests a minute per user
_MINDLOGIC_BLOCK = "mindlogic/{model}"  # key in gemini_tts._blocked_until


def _mindlogic_blocked() -> float:
    return gemini_tts.quota_blocked(_MINDLOGIC_BLOCK.format(model=config.MINDLOGIC_TTS_MODEL))


def _block_mindlogic(seconds: float) -> None:
    gemini_tts._blocked_until[_MINDLOGIC_BLOCK.format(model=config.MINDLOGIC_TTS_MODEL)] = time.time() + seconds


def _mindlogic_detail(resp: httpx.Response) -> str:
    """The gateway's {"detail": {"code", "message"}} message, else the raw body."""
    try:
        detail = resp.json().get("detail")
        return str(detail.get("message") if isinstance(detail, dict) else detail)[:250]
    except ValueError:
        return resp.text[:250]


async def _generate_mindlogic_tts(text: str, output_path: str, voice: Optional[str], style: Optional[str],
                                  speed: float) -> float:
    """POST ``{model, input, voice}`` to the gateway; it answers raw 16-bit 24 kHz mono PCM. Returns duration.

    Out of credits (402), rate limited (429 after retries), model not enabled (403),
    maintenance (503) or unreachable raise TTSEngineUnavailable so a fallback takes the line.
    """
    if not config.MINDLOGIC_API_KEY:
        raise RuntimeError("MINDLOGIC_API_KEY is not set — add it to .env")
    wait = _mindlogic_blocked()
    if wait:
        raise TTSEngineUnavailable(f"Mindlogic TTS is paused after a credit or rate limit; trying again in {wait / 60:.0f} min")
    prompt = f"{style.strip().rstrip(':')}: {text}" if style and style.strip() else text  # Gemini takes direction in the text
    if len(prompt) > MINDLOGIC_MAX_CHARS:
        raise TTSEngineUnavailable(f"Mindlogic TTS takes at most {MINDLOGIC_MAX_CHARS} characters (line has {len(prompt)})")
    body = {
        "model": config.MINDLOGIC_TTS_MODEL,
        "input": prompt,
        # Gemini names are one capitalised word; a Kokoro name ("af_heart") would be refused.
        "voice": voice if voice and "_" not in voice else (config.MINDLOGIC_TTS_VOICE or config.GEMINI_TTS_VOICE),
    }
    headers = {"Authorization": f"Bearer {config.MINDLOGIC_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=config.MINDLOGIC_TIMEOUT) as client:
            for attempt in range(len(_MINDLOGIC_RETRY_DELAYS) + 1):
                resp = await client.post(config.MINDLOGIC_TTS_URL, json=body, headers=headers)
                if resp.status_code != 429 or attempt == len(_MINDLOGIC_RETRY_DELAYS):
                    break
                logger.warning("Mindlogic TTS rate limited, retrying in %ds", _MINDLOGIC_RETRY_DELAYS[attempt])
                await asyncio.sleep(_MINDLOGIC_RETRY_DELAYS[attempt])
    except httpx.HTTPError as e:
        raise TTSEngineUnavailable(f"Mindlogic gateway is unreachable: {type(e).__name__} {e}"[:300])

    status = resp.status_code
    if status == 401:
        raise RuntimeError(f"Mindlogic rejected MINDLOGIC_API_KEY: {_mindlogic_detail(resp)}")
    if status == 402:
        _block_mindlogic(config.GEMINI_QUOTA_COOLDOWN)
        raise TTSEngineUnavailable(f"Mindlogic credits are used up: {_mindlogic_detail(resp)}")
    if status == 429:
        _block_mindlogic(60)
        raise TTSEngineUnavailable(f"Mindlogic rate limit: {_mindlogic_detail(resp)}")
    if status != 200:
        raise TTSEngineUnavailable(f"Mindlogic TTS HTTP {status}: {_mindlogic_detail(resp)}")
    pcm = resp.content
    if not pcm or "json" in resp.headers.get("content-type", ""):
        raise TTSEngineUnavailable(f"Mindlogic TTS returned no audio: {resp.text[:200]}")
    if len(pcm) % 2:
        pcm = pcm[:-1]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pcm if pcm[:4] == b"RIFF" else gemini_tts.pcm_to_wav(pcm, gemini_tts.DEFAULT_SAMPLE_RATE))
    if abs(speed - 1.0) > 0.01:  # no rate control on Gemini voices: stretch afterwards
        await asyncio.get_running_loop().run_in_executor(
            None, gemini_tts._apply_speed, out, speed, gemini_tts.DEFAULT_SAMPLE_RATE)
    return gemini_tts.wav_duration(out)


def _generate_google_tts(
    text: str,
    output_path: str,
    lang: str = "en",
    tld: str = "com",
    speed: float = 1.0,
    sample_rate: int = 24000,
) -> float:
    """Generate audio using Google TTS (gTTS) and convert to standardized WAV.

    Returns duration in seconds.
    """
    from gtts import gTTS
    import tempfile

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
        tmp_mp3_path = tmp_mp3.name

    try:
        tts = gTTS(text=text, lang=lang, tld=tld, slow=(speed < 0.9))
        tts.save(tmp_mp3_path)

        cmd = [
            "ffmpeg", "-y", "-i", tmp_mp3_path,
            "-ar", str(sample_rate),
            "-ac", "1",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio conversion failed: {result.stderr[-300:]}")

        with wave.open(str(out), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = round(frames / float(rate), 2)
        return duration
    finally:
        try:
            if os.path.exists(tmp_mp3_path):
                os.remove(tmp_mp3_path)
        except OSError:
            pass


# ─── Piper (local, free) ─────────────────────────────────────

# One voice per language; PIPER_VOICE overrides it. Names come from
# https://huggingface.co/rhasspy/piper-voices (voices.json).
PIPER_DEFAULT_VOICES = {
    "en": "en_US-lessac-medium",
    "ko": "ko_KR-kss-medium",
    "ja": "ja_JA-hi_fi_captain-medium",
    "zh": "zh_CN-huayan-medium",
    "vi": "vi_VN-vais1000-medium",
    "th": "th_TH-tsync2-medium",
    "id": "id_ID-news_tts-medium",
    "hi": "hi_IN-rohan-medium",
    "ar": "ar_JO-kareem-medium",
    "es": "es_ES-davefx-medium",
    "pt": "pt_BR-faber-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "it": "it_IT-paola-medium",
    "ru": "ru_RU-dmitri-medium",
    "tr": "tr_TR-dfki-medium",
}

_piper_voices: dict[str, object] = {}
# One synthesis at a time: it is CPU-bound, and the espeak phonemizer isn't thread-safe.
_piper_lock = threading.Lock()


def piper_voice_name(lang: Optional[str]) -> str:
    if config.PIPER_VOICE:
        return config.PIPER_VOICE
    base = base_lang(lang)
    if base not in PIPER_DEFAULT_VOICES:
        raise RuntimeError(f"No default local voice for language {base!r}. Set PIPER_VOICE in .env "
                           "(a name from https://huggingface.co/rhasspy/piper-voices).")
    return PIPER_DEFAULT_VOICES[base]


def _load_piper_voice(name: str):
    try:
        from piper import PiperVoice
        from piper.download_voices import download_voice
    except ImportError:
        raise RuntimeError("The local voice needs Piper. Install it on the agent: pip install piper-tts")
    if name.lower().endswith(".onnx"):
        model = Path(name)
        if not model.exists():
            raise RuntimeError(f"PIPER_VOICE file not found: {model}")
    else:
        model = config.PIPER_VOICES_DIR / f"{name}.onnx"
        if not model.exists():
            logger.info("Downloading Piper voice %s to %s", name, config.PIPER_VOICES_DIR)
            config.PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
            download_voice(name, config.PIPER_VOICES_DIR)
    return PiperVoice.load(model)


def _generate_piper_tts(text: str, output_path: str, lang: Optional[str] = None, speed: float = 1.0) -> float:
    """Speak ``text`` with a local Piper voice into a wav. Returns duration in seconds."""
    name = piper_voice_name(lang)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".piper.wav")
    with _piper_lock:
        voice = _piper_voices.get(name)
        if voice is None:
            voice = _piper_voices[name] = _load_piper_voice(name)
        from piper import SynthesisConfig

        # Synthesize before opening the wav: a phonemizer error (Japanese needs pyopenjtalk) would
        # otherwise surface as wave's "# channels not specified" when the empty file closes.
        chunks = list(voice.synthesize(text, syn_config=SynthesisConfig(length_scale=1 / min(max(speed, 0.5), 3.0))))
        if not chunks:
            raise RuntimeError("Piper produced no audio for this text")
        try:
            with wave.open(str(tmp), "wb") as wf:
                wf.setframerate(chunks[0].sample_rate)
                wf.setsampwidth(chunks[0].sample_width)
                wf.setnchannels(chunks[0].sample_channels)
                for chunk in chunks:
                    wf.writeframes(chunk.audio_int16_bytes)
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
    return gemini_tts.wav_duration(out)


# Inline script template for TTS generation via subprocess (OmniVoice fallback)
_TTS_SCRIPT = """
import sys, json, torch, torchaudio

args = json.loads(sys.argv[1])
from omnivoice import OmniVoice

model = OmniVoice.from_pretrained(args["model"], device_map="cpu", dtype=torch.float32)

kwargs = {"text": args["text"]}
if args.get("ref_audio") and args.get("ref_text"):
    kwargs["ref_audio"] = args["ref_audio"]
    kwargs["ref_text"] = args["ref_text"]
elif args.get("instruct"):
    kwargs["instruct"] = args["instruct"]
if args.get("speed") and args["speed"] != 1.0:
    kwargs["speed"] = args["speed"]

audio = model.generate(**kwargs)
torchaudio.save(args["output"], audio[0], args["sample_rate"])
print(json.dumps({"ok": True, "path": args["output"]}))
"""

# Batch script — loads model once, generates for multiple texts (OmniVoice fallback)
_TTS_BATCH_SCRIPT = """
import sys, json, torch, torchaudio
from pathlib import Path

args = json.loads(sys.argv[1])
from omnivoice import OmniVoice

model = OmniVoice.from_pretrained(args["model"], device_map="cpu", dtype=torch.float32)

results = []
for item in args["items"]:
    try:
        kwargs = {"text": item["text"]}
        if args.get("ref_audio") and args.get("ref_text"):
            kwargs["ref_audio"] = args["ref_audio"]
            kwargs["ref_text"] = args["ref_text"]
        elif args.get("instruct"):
            kwargs["instruct"] = args["instruct"]
        if args.get("speed") and args["speed"] != 1.0:
            kwargs["speed"] = args["speed"]

        audio = model.generate(**kwargs)
        Path(item["output"]).parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(item["output"], audio[0], args["sample_rate"])

        info = torchaudio.info(item["output"])
        duration = info.num_frames / info.sample_rate
        results.append({"id": item["id"], "ok": True, "path": item["output"], "duration": duration})
    except Exception as e:
        results.append({"id": item["id"], "ok": False, "error": str(e)})

print(json.dumps(results))
"""


# ─── Engine choice and fallback ──────────────────────────────

def fallback_engines() -> list[str]:
    """TTS_FALLBACK_ENGINE as a list ("piper,google" → both, "none" → empty), without TTS_ENGINE itself."""
    names = [e.strip() for e in (config.TTS_FALLBACK_ENGINE or "").lower().split(",")]
    return [e for e in names if e and e not in ("none", "off", config.TTS_ENGINE.lower())]


@lru_cache(maxsize=1)
def _gtts_langs() -> frozenset:
    try:
        from gtts.lang import tts_langs
        return frozenset(tts_langs())
    except Exception:  # gTTS missing or its list failed: let the call report it
        return frozenset()


def _gtts_lang(lang: str) -> str:
    return "zh-CN" if lang == "zh" else lang


def can_speak(engine: str, lang: str) -> bool:
    """Whether ``engine`` is worth asking for a line in ``lang`` (without calling it)."""
    if engine == "kokoro":
        return bool(config.KOKORO_URL) and lang in KOKORO_LANGS
    if engine == "piper":
        return bool(config.PIPER_VOICE) or lang in PIPER_DEFAULT_VOICES
    if engine == "google":
        langs = _gtts_langs()
        return not langs or _gtts_lang(lang) in langs
    if engine == "gemini":
        return bool(config.GEMINI_API_KEY) and not gemini_tts.quota_blocked(config.GEMINI_TTS_MODEL)
    if engine == "mindlogic":
        return bool(config.MINDLOGIC_API_KEY) and not _mindlogic_blocked()
    return True


async def _synthesize(
    engine: str,
    text: str,
    output_path: str,
    *,
    instruct: Optional[str] = None,
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
    speed: float = 1.0,
    lang: Optional[str] = None,
    tld: Optional[str] = None,
    voice: Optional[str] = None,
    style: Optional[str] = None,
) -> Optional[float]:
    """One narration line with one engine. Returns the duration when the engine reports it."""
    loop = asyncio.get_running_loop()
    lang = base_lang(lang)
    if engine == "gemini":
        return await gemini_tts.synthesize(
            text, output_path,
            api_key=config.GEMINI_API_KEY, model=config.GEMINI_TTS_MODEL,
            # A Kokoro name ("af_heart") means nothing to Gemini.
            voice=voice if voice and "_" not in voice else config.GEMINI_TTS_VOICE, style=style, speed=speed,
        )
    if engine == "mindlogic":
        return await _generate_mindlogic_tts(text, output_path, voice, style, speed)
    if engine == "kokoro":
        return await _generate_kokoro_tts(text, output_path, lang, voice, speed)
    if engine == "piper":
        return await loop.run_in_executor(None, _generate_piper_tts, text, output_path, lang, speed)
    if engine == "google":
        return await loop.run_in_executor(
            None, _generate_google_tts, text, output_path,
            _gtts_lang(lang), tld or config.TTS_TLD, speed, config.TTS_SAMPLE_RATE,
        )
    if engine == "omnivoice":
        args = {"model": config.TTS_MODEL, "text": text, "output": output_path,
                "sample_rate": config.TTS_SAMPLE_RATE, "speed": speed}
        if instruct:
            args["instruct"] = instruct
        if ref_audio:
            args["ref_audio"] = ref_audio
        if ref_text:
            args["ref_text"] = ref_text
        result = await loop.run_in_executor(None, _run_tts_subprocess, args)
        if not result.get("ok"):
            raise RuntimeError(f"TTS failed: {result.get('error', 'unknown')}")
        return None
    raise RuntimeError(f"Unknown TTS engine {engine!r}")


async def speak(text: str, output_path: str, **opts) -> dict:
    """Narrate with TTS_ENGINE, or with the fallback engines when it can't speak this line.

    It can't when the line's language isn't one it knows, Gemini is out of quota,
    or the Kokoro server is down. Returns ``{"path", "duration", "engine",
    "fallback_reason", "lang"}``. Raises GeminiQuotaError / TTSEngineUnavailable
    when there is no fallback, TTSUnavailableError when every fallback failed too.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    engine = config.TTS_ENGINE.lower()
    lang = text_language(text, opts.get("lang"))
    opts = {**opts, "lang": lang}

    if can_speak(engine, lang) or engine in ("gemini", "mindlogic"):  # their own error says why (no key, quota)
        try:
            duration = await _synthesize(engine, text, output_path, **opts)
            return {"path": output_path, "duration": duration, "engine": engine, "fallback_reason": None, "lang": lang}
        except (gemini_tts.GeminiQuotaError, TTSEngineUnavailable) as e:
            if not fallback_engines():
                raise
            reason = str(e)[:300]
    else:
        reason = f"{engine} can't speak {lang!r}"

    fallbacks = [e for e in fallback_engines() if can_speak(e, lang)]
    if not fallbacks:
        raise TTSEngineUnavailable(f"{reason}, and no engine in TTS_FALLBACK_ENGINE={config.TTS_FALLBACK_ENGINE!r} can")
    errors = []
    for fallback in fallbacks:
        try:
            duration = await _synthesize(fallback, text, output_path, **opts)
            logger.warning("%s spoken by %s instead of %s: %s", Path(output_path).name, fallback, engine, reason)
            return {"path": output_path, "duration": duration, "engine": fallback, "fallback_reason": reason, "lang": lang}
        except Exception as e:  # try the next one, then report all of them
            logger.warning("Fallback TTS %s failed: %s", fallback, e)
            errors.append(f"{fallback}: {e}")
    raise TTSUnavailableError(f"{reason}; the fallback voice failed too — {'; '.join(errors)[:400]}")


async def generate_speech(
    text: str,
    output_path: str,
    instruct: Optional[str] = None,
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
    speed: float = 1.0,
    lang: Optional[str] = None,
    tld: Optional[str] = None,
    voice: Optional[str] = None,
    style: Optional[str] = None,
) -> str:
    """Generate speech for text with the configured TTS_ENGINE (or its fallback)."""
    result = await speak(text, output_path, instruct=instruct, ref_audio=ref_audio, ref_text=ref_text,
                         speed=speed, lang=lang, tld=tld, voice=voice, style=style or instruct)
    logger.info("TTS saved to %s (engine=%s)", output_path, result["engine"])
    return result["path"]


# ─── Word timings ────────────────────────────────────────────

def timings_path_for(wav_path: str) -> Path:
    """scene_000_<id>.wav -> scene_000_<id>.words.json"""
    return Path(wav_path).with_suffix(".words.json")


TIMING_ENGINES = ("gemini", "whisper")


def timing_engines() -> list[str]:
    """TIMING_ENGINE as an ordered list, e.g. "whisper,gemini" -> ["whisper", "gemini"]."""
    names = [n.strip().lower() for n in config.TIMING_ENGINE.split(",")]
    return [n for n in dict.fromkeys(names) if n in TIMING_ENGINES] or ["gemini"]


async def word_timings(wav_path: str, text: str) -> dict:
    """Try each timing engine in order; the first real timing wins, else the words are estimated."""
    errors, result = [], None
    for name in timing_engines():
        if name == "whisper":
            attempt = await whisper_timing.word_timings(wav_path, text, lang=text_language(text))
        else:
            attempt = await gemini_tts.word_timings(
                wav_path, text, api_key=config.GEMINI_API_KEY, model=config.GEMINI_TIMING_MODEL,
            )
        if attempt.get("timing_source") != "estimated":
            return attempt
        result = result or attempt
        if attempt.get("timing_error"):
            errors.append(attempt["timing_error"])
    if errors:
        result["timing_error"] = "; ".join(errors)[:300]
    return result


async def write_word_timings(wav_path: str, text: str, engine: Optional[str] = None) -> dict:
    """Time every word of ``text`` in ``wav_path`` and save the sidecar JSON next to it."""
    result = await word_timings(wav_path, text)
    sidecar = timings_path_for(wav_path)
    payload = {"text": text, **result}
    if engine:
        payload["engine"] = engine
    sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**result, "timings_path": str(sidecar)}


def load_word_timings(wav_path: str) -> Optional[dict]:
    sidecar = timings_path_for(wav_path)
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def spoken_by_fallback(wav_path: str) -> bool:
    """True when the sidecar says a different engine than TTS_ENGINE spoke this wav."""
    engine = (load_word_timings(wav_path) or {}).get("engine")
    return bool(engine and engine != config.TTS_ENGINE.lower())


def _run_tts_subprocess(args: dict) -> dict:
    """Run TTS subprocess."""
    proc = subprocess.run(
        [PYTHON_BIN, "-c", _TTS_SCRIPT, json.dumps(args)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr[-500:] if proc.stderr else "unknown error"}
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "error": proc.stdout[-200:] + proc.stderr[-200:]}


async def generate_video_narration(
    scenes: list[dict],
    output_dir: str,
    instruct: Optional[str] = None,
    ref_audio: Optional[str] = None,
    ref_text: Optional[str] = None,
    speed: float = 1.0,
    lang: Optional[str] = None,
    tld: Optional[str] = None,
    voice: Optional[str] = None,
    style: Optional[str] = None,
    with_timings: bool = True,
    redo_fallback: bool = False,
) -> list[dict]:
    """Generate narration WAVs (plus word-timing sidecars) for scenes with narrator_text.

    Existing WAVs are kept, except that ``redo_fallback`` speaks again the ones a
    fallback voice made. OmniVoice runs as one batch subprocess so the model loads once.
    Returns list of result dicts.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build batch items (only scenes with narrator_text)
    items = []
    scene_map = {}
    for scene in scenes:
        scene_id = scene.get("id")
        display_order = scene.get("display_order", 0)
        narrator_text = scene.get("narrator_text")

        if not narrator_text:
            continue

        wav_path = str(out_dir / f"scene_{display_order:03d}_{scene_id}.wav")
        # Skip if WAV already exists and is non-trivial (>1KB)
        if Path(wav_path).exists() and Path(wav_path).stat().st_size > 1024:
            # Redo only what TTS_ENGINE can speak now: a Korean line stays with its fallback voice under Kokoro.
            primary_can = can_speak(config.TTS_ENGINE.lower(), text_language(narrator_text, lang))
            if not (redo_fallback and spoken_by_fallback(wav_path) and primary_can):
                logger.info("Skipping scene %03d (WAV exists: %s)", display_order, wav_path)
                scene_map[scene_id] = {"display_order": display_order, "narrator_text": narrator_text, "skipped": True, "wav_path": wav_path}
                continue
            logger.info("Redoing scene %03d: a fallback voice spoke it", display_order)
        items.append({"id": scene_id, "text": narrator_text, "output": wav_path})
        scene_map[scene_id] = {"display_order": display_order, "narrator_text": narrator_text}

    # Run generation if there are items
    batch_results = {}
    if items:
        if config.TTS_ENGINE.lower() == "omnivoice":
            args = {
                "model": config.TTS_MODEL,
                "sample_rate": config.TTS_SAMPLE_RATE,
                "speed": speed,
                "items": items,
            }
            if instruct:
                args["instruct"] = instruct
            if ref_audio:
                args["ref_audio"] = ref_audio
            if ref_text:
                args["ref_text"] = ref_text

            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, _run_batch_subprocess, args)
            for r in raw:
                batch_results[r["id"]] = {**r, "engine": "omnivoice"}
        else:
            gate = asyncio.Semaphore(max(config.GEMINI_TTS_CONCURRENCY, 1))

            async def _item(item):
                async with gate:
                    try:
                        # Gemini gets `style`, not `instruct`: here instruct is the project's
                        # OmniVoice voice-design string ("male, low pitch"), which Gemini would read out loud.
                        r = await speak(item["text"], item["output"], instruct=instruct, ref_audio=ref_audio,
                                        ref_text=ref_text, speed=speed, lang=lang, tld=tld, voice=voice, style=style)
                        return {"id": item["id"], "ok": True, "path": item["output"], "duration": r["duration"],
                                "engine": r["engine"], "fallback_reason": r["fallback_reason"]}
                    except Exception as e:
                        logger.exception("TTS failed for scene %s", item["id"])
                        return {"id": item["id"], "ok": False, "error": str(e)}

            for r in await asyncio.gather(*(_item(item) for item in items)):
                batch_results[r["id"]] = r

    # Build final results for all scenes
    results = []
    for scene in scenes:
        scene_id = scene.get("id")
        display_order = scene.get("display_order", 0)
        narrator_text = scene.get("narrator_text")

        if not narrator_text:
            results.append({
                "scene_id": scene_id,
                "display_order": display_order,
                "narrator_text": None,
                "audio_path": None,
                "duration": None,
                "status": "SKIPPED",
                "error": None,
            })
            continue

        sm = scene_map.get(scene_id, {})
        if sm.get("skipped"):
            results.append({
                "scene_id": scene_id,
                "display_order": display_order,
                "narrator_text": narrator_text,
                "audio_path": sm["wav_path"],
                "duration": None,
                "engine": (load_word_timings(sm["wav_path"]) or {}).get("engine"),
                "status": "COMPLETED",
                "error": None,
            })
            continue

        br = batch_results.get(scene_id, {})
        if br.get("ok"):
            results.append({
                "scene_id": scene_id,
                "display_order": display_order,
                "narrator_text": narrator_text,
                "audio_path": br.get("path"),
                "duration": br.get("duration"),
                "engine": br.get("engine"),
                "fallback_reason": br.get("fallback_reason"),
                "fresh": True,
                "status": "COMPLETED",
                "error": None,
            })
        else:
            results.append({
                "scene_id": scene_id,
                "display_order": display_order,
                "narrator_text": narrator_text,
                "audio_path": None,
                "duration": None,
                "status": "FAILED",
                "error": br.get("error", "not processed"),
            })

    if with_timings:
        await _attach_word_timings(results)
    return results


async def _attach_word_timings(results: list[dict]) -> None:
    """Add timings to completed results, reusing a sidecar whose text still matches the untouched wav."""
    gate = asyncio.Semaphore(max(config.GEMINI_TTS_CONCURRENCY, 1))

    async def _one(r: dict):
        existing = load_word_timings(r["audio_path"])
        if not r.get("fresh") and existing and existing.get("text") == r["narrator_text"] and existing.get("words"):
            timing = {**existing, "timings_path": str(timings_path_for(r["audio_path"]))}
        else:
            async with gate:
                timing = await write_word_timings(r["audio_path"], r["narrator_text"], engine=r.get("engine"))
        r["timings_path"] = timing["timings_path"]
        r["timing_source"] = timing.get("timing_source")
        r["duration"] = r.get("duration") or timing.get("duration")

    await asyncio.gather(*(
        _one(r) for r in results
        if r["status"] == "COMPLETED" and r.get("audio_path") and Path(r["audio_path"]).exists()
    ))


def _run_batch_subprocess(args: dict) -> list[dict]:
    """Run batch TTS subprocess. Model loads once."""
    timeout = 180 + len(args.get("items", [])) * 45  # ~180s model load + ~45s per scene
    proc = subprocess.run(
        [PYTHON_BIN, "-c", _TTS_BATCH_SCRIPT, json.dumps(args)],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        error = proc.stderr[-500:] if proc.stderr else "unknown"
        return [{"id": item["id"], "ok": False, "error": error} for item in args["items"]]
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except (json.JSONDecodeError, IndexError):
        error = proc.stdout[-200:] + proc.stderr[-200:]
        return [{"id": item["id"], "ok": False, "error": error} for item in args["items"]]
