"""Gemini text-to-speech plus word timings.

Gemini TTS returns raw audio and nothing else, so timings take a second call:
the finished wav goes back to a Gemini audio model together with the exact
script, and the model reports when each word is spoken. Those timings are then
mapped back onto the script's own words, so a subtitle always shows the text
that was written, never a re-transcription of it.

When the timing call is unavailable or returns something unusable, the words
are spread across the audio by length and marked ``timing_source="estimated"``.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import subprocess
import wave
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_SAMPLE_RATE = 24000
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAYS = (2, 6, 15)


class GeminiTTSError(RuntimeError):
    pass


# ─── Request builders ────────────────────────────────────────

def speech_request(text: str, voice: str, style: Optional[str] = None) -> dict:
    """generateContent body for one narration line.

    Gemini takes delivery direction in the prompt itself ("Say calmly: ...").
    """
    prompt = f"{style.strip().rstrip(':')}: {text}" if style and style.strip() else text
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }


_TIMING_PROMPT = """This audio is a narrator reading the transcript below, and it lasts {duration:.2f} seconds.
Return the time each word of the transcript is spoken: one entry per whitespace-separated word, in order, with "word" copied exactly as written in the transcript, and "start"/"end" in seconds (3 decimals) from the beginning of the audio.

Transcript:
{text}"""


def timing_request(wav_bytes: bytes, text: str, duration: float) -> dict:
    return {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav_bytes).decode()}},
            {"text": _TIMING_PROMPT.format(duration=duration, text=text)},
        ]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "word": {"type": "STRING"},
                        "start": {"type": "NUMBER"},
                        "end": {"type": "NUMBER"},
                    },
                    "required": ["word", "start", "end"],
                },
            },
        },
    }


# ─── Response readers ────────────────────────────────────────

def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def extract_audio(response: dict) -> tuple[bytes, int]:
    """Audio as a complete wav file, from wherever the response carries it."""
    for node in _walk(response):
        inline = node.get("inlineData") or node.get("inline_data")
        if not isinstance(inline, dict) or not inline.get("data"):
            continue
        mime = inline.get("mimeType") or inline.get("mime_type") or ""
        if mime and not mime.startswith("audio"):
            continue
        raw = base64.b64decode(inline["data"])
        rate_match = re.search(r"rate=(\d+)", mime)
        rate = int(rate_match.group(1)) if rate_match else DEFAULT_SAMPLE_RATE
        if raw[:4] == b"RIFF":
            return raw, rate
        return pcm_to_wav(raw, rate), rate
    raise GeminiTTSError(f"No audio in Gemini response: {_describe_empty(response)}")


def extract_json(response: dict) -> Any:
    texts = [n["text"] for n in _walk(response) if isinstance(n.get("text"), str)]
    if not texts:
        raise GeminiTTSError(f"No text in Gemini response: {_describe_empty(response)}")
    body = "".join(texts).strip()
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body)
    return json.loads(body)


def _describe_empty(response: dict) -> str:
    feedback = response.get("promptFeedback") or {}
    reasons = [c.get("finishReason") for c in response.get("candidates", []) if isinstance(c, dict)]
    return json.dumps({"finishReason": reasons, "promptFeedback": feedback})[:300]


def pcm_to_wav(pcm: bytes, rate: int = DEFAULT_SAMPLE_RATE, channels: int = 1, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_duration(path_or_bytes: Path | bytes) -> float:
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else str(path_or_bytes)
    try:
        with wave.open(src, "rb") as wf:
            return round(wf.getnframes() / float(wf.getframerate()), 3)
    except (wave.Error, EOFError):
        # The wave module only reads integer PCM; OmniVoice writes float WAVs.
        if isinstance(path_or_bytes, bytes):
            raise
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path_or_bytes)],
            capture_output=True, text=True, timeout=30,
        )
        return round(float(out.stdout.strip()), 3)


# ─── Timing alignment ────────────────────────────────────────

def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE).lower()


def estimate_timings(script_words: list[str], duration: float, lead: float = 0.05) -> list[dict]:
    """Spread words over the audio in proportion to their length."""
    if not script_words:
        return []
    weights = [max(len(_norm(w)), 1) + 1 for w in script_words]
    span = max(duration - 2 * lead, 0.1)
    total = sum(weights)
    words, t = [], lead
    for word, weight in zip(script_words, weights):
        step = span * weight / total
        words.append({"word": word, "start": round(t, 3), "end": round(t + step, 3)})
        t += step
    return words


def align_timings(raw: Any, script_words: list[str], duration: float) -> tuple[list[dict], str]:
    """Map a model's word timings onto the script's words.

    Returns (words, source) where source is "gemini" or "estimated".
    """
    entries = []
    if isinstance(raw, list):
        for e in raw:
            try:
                entries.append((str(e["word"]), float(e["start"]), float(e["end"])))
            except (KeyError, TypeError, ValueError):
                continue
    if not script_words:
        return [], "gemini"
    if not entries:
        return estimate_timings(script_words, duration), "estimated"

    times: list[Optional[tuple[float, float]]] = [None] * len(script_words)
    if len(entries) == len(script_words):
        times = [(s, e) for _, s, e in entries]
    else:
        matcher = SequenceMatcher(None, [_norm(w) for w in script_words],
                                  [_norm(w) for w, _, _ in entries], autojunk=False)
        for block in matcher.get_matching_blocks():
            for k in range(block.size):
                _, s, e = entries[block.b + k]
                times[block.a + k] = (s, e)
        if sum(t is not None for t in times) < len(script_words) * 0.5:
            return estimate_timings(script_words, duration), "estimated"

    _fill_gaps(times, duration)
    words = []
    floor = 0.0
    for word, (start, end) in zip(script_words, times):
        start = min(max(start, floor, 0.0), duration)
        end = min(max(end, start), duration)
        words.append({"word": word, "start": round(start, 3), "end": round(end, 3)})
        floor = start
    return words, "gemini"


def _fill_gaps(times: list[Optional[tuple[float, float]]], duration: float) -> None:
    """Interpolate unmatched words between their matched neighbours, in place."""
    i = 0
    n = len(times)
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        left = times[i - 1][1] if i > 0 else 0.0
        right = times[j][0] if j < n else duration
        step = max(right - left, 0.0) / (j - i)
        for k in range(i, j):
            times[k] = (left + step * (k - i), left + step * (k - i + 1))
        i = j


# ─── Network ─────────────────────────────────────────────────

async def _generate(model: str, body: dict, api_key: str, timeout: float) -> dict:
    if not api_key:
        raise GeminiTTSError("GEMINI_API_KEY is not set — add it to .env")
    url = f"{API_ROOT}/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(len(_RETRY_DELAYS) + 1):
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in _RETRY_STATUS and attempt < len(_RETRY_DELAYS):
                logger.warning("Gemini %s returned %d, retrying in %ds", model, resp.status_code, _RETRY_DELAYS[attempt])
                await asyncio.sleep(_RETRY_DELAYS[attempt])
                continue
            raise GeminiTTSError(f"Gemini {model} HTTP {resp.status_code}: {resp.text[:300]}")
    raise GeminiTTSError(f"Gemini {model}: retries exhausted")


def _apply_speed(path: Path, speed: float, sample_rate: int) -> None:
    """Gemini has no rate control, so pace changes are done with atempo afterwards."""
    tmp = path.with_suffix(".tempo.wav")
    tempo = min(max(speed, 0.5), 2.0)
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={tempo}",
         "-ar", str(sample_rate), "-ac", "1", str(tmp)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise GeminiTTSError(f"ffmpeg atempo failed: {proc.stderr[-300:]}")
    tmp.replace(path)


async def synthesize(text: str, output_path: str, *, api_key: str, model: str, voice: str,
                     style: Optional[str] = None, speed: float = 1.0) -> float:
    """Write narration to ``output_path`` (wav). Returns its duration in seconds."""
    response = await _generate(model, speech_request(text, voice, style), api_key, timeout=120)
    wav_bytes, rate = extract_audio(response)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav_bytes)
    if abs(speed - 1.0) > 0.01:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _apply_speed, out, speed, rate)
    return wav_duration(out)


async def word_timings(wav_path: str, text: str, *, api_key: str, model: str) -> dict:
    """Timings for every word of ``text`` in ``wav_path``. Never raises for a bad timing reply."""
    path = Path(wav_path)
    duration = wav_duration(path)
    script_words = text.split()
    if not api_key:
        return {"duration": duration, "words": estimate_timings(script_words, duration),
                "timing_source": "estimated", "timing_error": "GEMINI_API_KEY is not set"}
    try:
        response = await _generate(model, timing_request(path.read_bytes(), text, duration), api_key, timeout=120)
        words, source = align_timings(extract_json(response), script_words, duration)
        return {"duration": duration, "words": words, "timing_source": source}
    except (GeminiTTSError, httpx.HTTPError, json.JSONDecodeError) as e:
        logger.warning("Word timing failed for %s, estimating instead: %s", path.name, e)
        return {"duration": duration, "words": estimate_timings(script_words, duration),
                "timing_source": "estimated", "timing_error": str(e)[:300]}
