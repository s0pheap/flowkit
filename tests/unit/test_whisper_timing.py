"""TIMING_ENGINE order and the local Whisper timing path (agent/services/whisper_timing.py)."""
import wave

import pytest

from agent import config
from agent.services import gemini_tts, tts, whisper_timing


def write_wav(path, seconds=2.0, rate=16000):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(seconds * rate))


@pytest.mark.parametrize("value,expected", [
    ("gemini", ["gemini"]),
    ("whisper, gemini", ["whisper", "gemini"]),
    ("WHISPER,whisper", ["whisper"]),
    ("bogus", ["gemini"]),
])
def test_timing_engines(monkeypatch, value, expected):
    monkeypatch.setattr(config, "TIMING_ENGINE", value)
    assert tts.timing_engines() == expected


async def test_whisper_words_are_mapped_onto_the_script(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    write_wav(wav)
    heard = [{"word": "Phnom", "start": 0.1, "end": 0.4}, {"word": "Srey,", "start": 0.4, "end": 0.9},
             {"word": "rises.", "start": 1.0, "end": 1.5}]
    monkeypatch.setattr(whisper_timing, "_transcribe", lambda *a: heard)
    result = await whisper_timing.word_timings(str(wav), "Phnom Srey rises.")
    assert result["timing_source"] == "whisper"
    assert [w["word"] for w in result["words"]] == ["Phnom", "Srey", "rises."]
    assert result["words"][2]["start"] == 1.0


async def test_whisper_failure_estimates(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    write_wav(wav)

    def boom(*a):
        raise whisper_timing.WhisperUnavailable("no model")
    monkeypatch.setattr(whisper_timing, "_transcribe", boom)
    result = await whisper_timing.word_timings(str(wav), "two words")
    assert result["timing_source"] == "estimated"
    assert "no model" in result["timing_error"]


async def test_next_engine_used_when_first_estimates(monkeypatch, tmp_path):
    wav = tmp_path / "a.wav"
    write_wav(wav)
    monkeypatch.setattr(config, "TIMING_ENGINE", "gemini,whisper")

    async def gemini_out(*a, **kw):
        return {"duration": 2.0, "words": [], "timing_source": "estimated", "timing_error": "quota"}

    async def whisper_ok(*a, **kw):
        return {"duration": 2.0, "words": [{"word": "hi", "start": 0.1, "end": 0.5}], "timing_source": "whisper"}
    monkeypatch.setattr(gemini_tts, "word_timings", gemini_out)
    monkeypatch.setattr(whisper_timing, "word_timings", whisper_ok)
    result = await tts.write_word_timings(str(wav), "hi", engine="kokoro")
    assert result["timing_source"] == "whisper"
    assert (tmp_path / "a.words.json").exists()
