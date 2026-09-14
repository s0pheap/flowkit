"""Gemini TTS request/response handling and word-timing alignment."""
import base64
import json

import pytest

from agent.services import gemini_tts as g


def _pcm(seconds: float, rate: int = 24000) -> bytes:
    return b"\x00\x00" * int(seconds * rate)


class TestSpeechRequest:
    def test_voice_and_audio_modality(self):
        body = g.speech_request("Hello there.", "Kore")
        assert body["contents"][0]["parts"][0]["text"] == "Hello there."
        cfg = body["generationConfig"]
        assert cfg["responseModalities"] == ["AUDIO"]
        assert cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"

    def test_style_becomes_a_spoken_direction(self):
        body = g.speech_request("The convoy moves.", "Puck", style="Say as a tense narrator:")
        assert body["contents"][0]["parts"][0]["text"] == "Say as a tense narrator: The convoy moves."

    def test_blank_style_is_ignored(self):
        assert g.speech_request("Hi", "Kore", style="  ")["contents"][0]["parts"][0]["text"] == "Hi"


class TestExtractAudio:
    def test_pcm_is_wrapped_as_wav_with_rate_from_mime(self):
        response = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000",
            "data": base64.b64encode(_pcm(1.5)).decode(),
        }}]}}]}
        wav, rate = g.extract_audio(response)
        assert wav[:4] == b"RIFF"
        assert rate == 24000
        assert g.wav_duration(wav) == pytest.approx(1.5)

    def test_snake_case_inline_data_is_accepted(self):
        response = {"outputs": [{"inline_data": {"mime_type": "audio/pcm;rate=16000",
                                                 "data": base64.b64encode(_pcm(0.5, 16000)).decode()}}]}
        wav, rate = g.extract_audio(response)
        assert rate == 16000
        assert g.wav_duration(wav) == pytest.approx(0.5)

    def test_no_audio_raises_with_finish_reason(self):
        with pytest.raises(g.GeminiTTSError, match="SAFETY"):
            g.extract_audio({"candidates": [{"finishReason": "SAFETY"}]})


class TestExtractJson:
    def test_reads_fenced_json_text(self):
        payload = [{"word": "Hi", "start": 0.0, "end": 0.2}]
        response = {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(payload) + "\n```"}]}}]}
        assert g.extract_json(response) == payload


class TestTimingRequest:
    def test_sends_audio_and_transcript_with_schema(self):
        body = g.timing_request(b"RIFFdata", "Hello world", 1.25)
        parts = body["contents"][0]["parts"]
        assert parts[0]["inlineData"]["mimeType"] == "audio/wav"
        assert base64.b64decode(parts[0]["inlineData"]["data"]) == b"RIFFdata"
        assert "Hello world" in parts[1]["text"] and "1.25" in parts[1]["text"]
        assert body["generationConfig"]["responseMimeType"] == "application/json"


class TestAlignTimings:
    SCRIPT = "Colonel Harris detects unusual radar signatures.".split()

    def test_same_count_keeps_script_spelling(self):
        raw = [{"word": w.lower().strip("."), "start": i * 0.5, "end": i * 0.5 + 0.4}
               for i, w in enumerate(self.SCRIPT)]
        words, source = g.align_timings(raw, self.SCRIPT, 4.0)
        assert source == "gemini"
        assert [w["word"] for w in words] == self.SCRIPT
        assert words[-1]["word"] == "signatures."
        assert words[2]["start"] == 1.0

    def test_missing_word_is_interpolated_between_neighbours(self):
        raw = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4}
               for i, w in enumerate(self.SCRIPT) if w != "unusual"]
        raw = [dict(e, start=e["start"] + (0.5 if i >= 3 else 0), end=e["end"] + (0.5 if i >= 3 else 0))
               for i, e in enumerate(raw)]
        words, source = g.align_timings(raw, self.SCRIPT, 4.0)
        assert source == "gemini"
        unusual = words[3]
        assert words[2]["end"] <= unusual["start"] <= unusual["end"] <= words[4]["start"]

    def test_times_are_monotonic_and_clamped(self):
        raw = [{"word": w, "start": s, "end": e} for w, (s, e) in
               zip(self.SCRIPT, [(0.1, 0.5), (0.4, 0.9), (0.3, 1.2), (1.3, 1.8), (1.9, 2.5), (2.6, 9.0)])]
        words, _ = g.align_timings(raw, self.SCRIPT, 3.0)
        starts = [w["start"] for w in words]
        assert starts == sorted(starts)
        assert words[-1]["end"] == 3.0

    def test_garbage_falls_back_to_estimate(self):
        words, source = g.align_timings("not a list", self.SCRIPT, 3.0)
        assert source == "estimated"
        assert len(words) == len(self.SCRIPT)

    def test_mostly_unmatched_falls_back_to_estimate(self):
        raw = [{"word": "zzz", "start": 0, "end": 1}, {"word": "qqq", "start": 1, "end": 2}]
        _, source = g.align_timings(raw, self.SCRIPT, 3.0)
        assert source == "estimated"

    def test_korean_words_align(self):
        script = "북한 병사가 국경을 넘었다.".split()
        raw = [{"word": w, "start": i * 0.6, "end": i * 0.6 + 0.5} for i, w in enumerate(script)]
        words, source = g.align_timings(raw, script, 3.0)
        assert source == "gemini"
        assert [w["word"] for w in words] == script


class TestEstimateTimings:
    def test_covers_audio_in_order(self):
        words = g.estimate_timings(["a", "longer", "sentence"], 3.0)
        assert words[0]["start"] == pytest.approx(0.05)
        assert words[-1]["end"] == pytest.approx(2.95, abs=0.01)
        assert words[1]["end"] - words[1]["start"] > words[0]["end"] - words[0]["start"]
