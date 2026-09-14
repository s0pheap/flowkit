"""Word timings from a local faster-whisper model (TIMING_ENGINE=whisper).

Whisper transcribes the finished wav with word timestamps, and those timestamps
are mapped onto the script's own words exactly like Gemini timings, so a
subtitle always shows the text that was written. The script is passed as the
prompt, which steers Whisper toward the script's spelling of names and makes
the alignment match more words.

Runs on this machine with no quota. The model loads once, on first use; with
WHISPER_DEVICE=auto it tries the GPU and falls back to the CPU when CUDA
libraries are missing.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

from agent import config
from agent.services import gemini_tts

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_device: Optional[str] = None


class WhisperUnavailable(RuntimeError):
    pass


def _model_ref() -> str:
    """WHISPER_MODEL is a size name ("small") or a model folder, relative to the repo or absolute."""
    name = config.WHISPER_MODEL.strip() or "small"
    local = Path(name) if Path(name).is_absolute() else config.BASE_DIR / name
    return str(local) if local.exists() else name


def _devices() -> list[tuple[str, str]]:
    device = config.WHISPER_DEVICE.strip().lower() or "auto"
    if device == "auto":
        return [("cuda", "float16"), ("cpu", "int8")]
    return [(device, config.WHISPER_COMPUTE_TYPE or ("float16" if device == "cuda" else "int8"))]


def _load(devices: list[tuple[str, str]]):
    global _model, _device
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise WhisperUnavailable("Whisper timing needs faster-whisper: pip install faster-whisper") from e
    errors = []
    for device, compute_type in devices:
        try:
            _model = WhisperModel(_model_ref(), device=device, compute_type=compute_type)
            _device = device
            logger.info("Whisper %s loaded on %s (%s)", _model_ref(), device, compute_type)
            return _model
        except Exception as e:  # missing CUDA, bad model path, failed download
            errors.append(f"{device}: {e}")
    raise WhisperUnavailable("; ".join(errors)[:400])


def _words(model, wav_path: str, text: str, lang: Optional[str]) -> list[dict]:
    segments, _info = model.transcribe(wav_path, language=lang or None, word_timestamps=True,
                                       initial_prompt=text, vad_filter=False, beam_size=5)
    return [{"word": w.word.strip(), "start": float(w.start), "end": float(w.end)}
            for seg in segments for w in (seg.words or [])]


def _transcribe(wav_path: str, text: str, lang: Optional[str]) -> list[dict]:
    """Serialised: one model, one transcription at a time."""
    global _model
    with _lock:
        devices = _devices()
        model = _model or _load(devices)
        try:
            return _words(model, wav_path, text, lang)
        except RuntimeError as e:
            # CUDA can load and still fail on first use (e.g. cublas64_12.dll missing).
            if _device != "cuda" or not any(d == "cpu" for d, _ in devices):
                raise
            logger.warning("Whisper failed on the GPU, switching to the CPU: %s", e)
            _model = None
            return _words(_load([d for d in devices if d[0] == "cpu"]), wav_path, text, lang)


async def word_timings(wav_path: str, text: str, lang: Optional[str] = None) -> dict:
    """Timings for every word of ``text`` in ``wav_path``. Never raises."""
    path = Path(wav_path)
    duration = gemini_tts.wav_duration(path)
    script_words = text.split()
    try:
        raw = await asyncio.to_thread(_transcribe, str(path), text, lang)
    except Exception as e:
        logger.warning("Whisper word timing failed for %s, estimating instead: %s", path.name, e)
        return {"duration": duration, "words": gemini_tts.estimate_timings(script_words, duration),
                "timing_source": "estimated", "timing_error": f"whisper: {e}"[:300]}
    words, source = gemini_tts.align_timings(raw, script_words, duration, source="whisper")
    result = {"duration": duration, "words": words, "timing_source": source}
    if source == "estimated":
        result["timing_error"] = "whisper: transcript did not match the script"
    return result
