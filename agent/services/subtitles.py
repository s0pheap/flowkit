"""Subtitles from narration word timings.

Pure functions: word timings in, SRT text out. Timings come from the
``*.words.json`` sidecar the TTS step writes next to each narration wav.
"""
from __future__ import annotations

import re
from typing import Optional

SENTENCE_END = tuple(".!?。！？…")
SOFT_BREAK = tuple(",;:，、")
MIN_CUE_SECONDS = 0.7

_HANGUL = re.compile(r"[가-힣]")


def default_max_chars(text: str) -> int:
    """Characters per cue. Hangul reads denser, so Korean cues are shorter."""
    letters = [c for c in text if not c.isspace()]
    if letters and len(_HANGUL.findall(text)) / len(letters) > 0.3:
        return 20
    return 42


def build_cues(words: list[dict], max_chars: int = 42, max_seconds: float = 4.0) -> list[dict]:
    """Group timed words into cues, breaking at sentence ends, length, or duration."""
    cues: list[dict] = []
    current: list[dict] = []

    def flush():
        if current:
            cues.append({
                "start": current[0]["start"],
                "end": current[-1]["end"],
                "text": " ".join(w["word"] for w in current),
            })
            current.clear()

    for word in words:
        if current:
            text_len = len(" ".join(w["word"] for w in current)) + 1 + len(word["word"])
            # A sentence's last word may run a little long rather than sit alone in its own cue.
            limit = max_chars + max_chars // 4 if word["word"].endswith(SENTENCE_END) else max_chars
            if text_len > limit or word["end"] - current[0]["start"] > max_seconds:
                flush()
        current.append(word)
        text = " ".join(w["word"] for w in current)
        if word["word"].endswith(SENTENCE_END):
            flush()
        elif word["word"].endswith(SOFT_BREAK) and len(text) >= max_chars * 0.5:
            flush()
    flush()
    return tidy_cues(cues)


def tidy_cues(cues: list[dict]) -> list[dict]:
    """Stretch very short cues to stay readable, without running into the next one."""
    for i, cue in enumerate(cues):
        next_start = cues[i + 1]["start"] if i + 1 < len(cues) else None
        if cue["end"] - cue["start"] < MIN_CUE_SECONDS:
            cue["end"] = cue["start"] + MIN_CUE_SECONDS
        if next_start is not None and cue["end"] > next_start:
            cue["end"] = next_start
        cue["start"] = round(cue["start"], 3)
        cue["end"] = round(max(cue["end"], cue["start"]), 3)
    return cues


def shift_words(words: list[dict], offset: float, window: Optional[float] = None) -> list[dict]:
    """Move a scene's words onto the video timeline, dropping any past the scene's cut."""
    shifted = []
    for w in words:
        if window is not None and w["start"] >= window:
            continue
        end = min(w["end"], window) if window is not None else w["end"]
        shifted.append({"word": w["word"], "start": w["start"] + offset, "end": end + offset})
    return shifted


def format_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(cues: list[dict]) -> str:
    blocks = [
        f"{i}\n{format_timestamp(c['start'])} --> {format_timestamp(c['end'])}\n{c['text']}\n"
        for i, c in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)
