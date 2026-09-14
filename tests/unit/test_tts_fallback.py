"""Gemini quota detection and the switch to a free local voice (agent/services/tts.py)."""
import json
import os
import wave

import httpx
import pytest

from agent import config
from agent.services import gemini_tts as g
from agent.services import tts

DAILY_429 = json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "39s"},
]}})
MINUTE_429 = json.dumps({"error": {"code": 429, "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
]}})


def write_wav(path, seconds=1.0, rate=22050):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x01\x00" * int(seconds * rate))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    g._blocked_until.clear()
    monkeypatch.setattr(config, "TTS_ENGINE", "gemini")
    monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "piper")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    yield
    g._blocked_until.clear()


@pytest.fixture
def gemini_replies(monkeypatch):
    """Serve queued (status, body) replies to every Gemini call and count the calls."""
    replies, calls = [], []

    def handler(request):
        calls.append(request.url.path)
        status, body = replies.pop(0) if replies else (429, DAILY_429)
        return httpx.Response(status, text=body)

    real = httpx.AsyncClient
    monkeypatch.setattr(g.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    async def no_sleep(_):
        return None
    monkeypatch.setattr(g.asyncio, "sleep", no_sleep)
    return replies, calls


class TestQuotaDetection:
    def test_daily_quota_and_retry_delay(self):
        assert g.quota_details(DAILY_429) == (True, 39.0)
        assert g.quota_details(MINUTE_429) == (False, None)
        assert g.quota_details("<html>") == (False, None)

    async def test_daily_quota_fails_at_once_and_blocks_the_model(self, gemini_replies):
        replies, calls = gemini_replies
        replies.append((429, DAILY_429))
        with pytest.raises(g.GeminiQuotaError):
            await g._generate("tts-model", {}, "key", timeout=5)
        assert len(calls) == 1  # no pointless retries against a daily limit
        assert g.quota_blocked("tts-model") > 3000
        with pytest.raises(g.GeminiQuotaError):
            await g._generate("tts-model", {}, "key", timeout=5)
        assert len(calls) == 1  # blocked: Gemini isn't asked again
        assert g.quota_blocked("other-model") == 0

    async def test_rate_limit_retries_then_blocks_briefly(self, gemini_replies):
        replies, calls = gemini_replies
        replies.extend([(429, MINUTE_429)] * 4)
        with pytest.raises(g.GeminiQuotaError):
            await g._generate("tts-model", {}, "key", timeout=5)
        assert len(calls) == 4
        assert 0 < g.quota_blocked("tts-model") <= 60

    async def test_rate_limit_that_clears_is_not_an_error(self, gemini_replies):
        replies, _calls = gemini_replies
        replies.extend([(429, MINUTE_429), (200, "{}")])
        assert await g._generate("tts-model", {}, "key", timeout=5) == {}

    async def test_other_errors_are_not_quota_errors(self, gemini_replies):
        replies, _calls = gemini_replies
        replies.append((400, '{"error": {"message": "bad voice"}}'))
        with pytest.raises(g.GeminiTTSError) as err:
            await g._generate("tts-model", {}, "key", timeout=5)
        assert not isinstance(err.value, g.GeminiQuotaError)

    async def test_word_timings_estimate_while_blocked(self, tmp_path):
        g._blocked_until[config.GEMINI_TIMING_MODEL] = 9e12
        wav = tmp_path / "a.wav"
        write_wav(wav, 2.0)
        result = await g.word_timings(str(wav), "one two three", api_key="k", model=config.GEMINI_TIMING_MODEL)
        assert result["timing_source"] == "estimated" and len(result["words"]) == 3


class TestFallback:
    @pytest.fixture
    def engines(self, monkeypatch):
        """Gemini out of quota; Piper writes a real wav."""
        spoken = []

        async def gemini(text, output_path, **kw):
            raise g.GeminiQuotaError("Gemini tts HTTP 429: quota")

        def piper(text, output_path, lang=None, speed=1.0):
            spoken.append((text, lang))
            write_wav(tts.Path(output_path), 1.5)
            return 1.5

        monkeypatch.setattr(g, "synthesize", gemini)
        monkeypatch.setattr(tts, "_generate_piper_tts", piper)

        async def timings(wav_path, text, **kw):
            return {"duration": 1.5, "words": g.estimate_timings(text.split(), 1.5), "timing_source": "estimated"}
        monkeypatch.setattr(g, "word_timings", timings)
        return spoken

    async def test_speak_switches_to_piper(self, engines, tmp_path):
        result = await tts.speak("Hello there", str(tmp_path / "a.wav"), lang="ko")
        assert result["engine"] == "piper" and "quota" in result["fallback_reason"]
        assert engines == [("Hello there", "ko")]

    async def test_no_fallback_keeps_the_quota_error(self, engines, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "none")
        with pytest.raises(g.GeminiQuotaError):
            await tts.speak("Hello", str(tmp_path / "a.wav"))

    async def test_failing_fallback_explains_both(self, engines, tmp_path, monkeypatch):
        def broken(*a, **kw):
            raise RuntimeError("The local voice needs Piper. Install it on the agent: pip install piper-tts")
        monkeypatch.setattr(tts, "_generate_piper_tts", broken)
        with pytest.raises(tts.TTSUnavailableError, match="pip install piper-tts"):
            await tts.speak("Hello", str(tmp_path / "a.wav"))

    async def test_other_gemini_errors_do_not_fall_back(self, engines, tmp_path, monkeypatch):
        async def bad(*a, **kw):
            raise g.GeminiTTSError("HTTP 400")
        monkeypatch.setattr(g, "synthesize", bad)
        with pytest.raises(g.GeminiTTSError):
            await tts.speak("Hello", str(tmp_path / "a.wav"))
        assert engines == []

    async def test_video_narration_records_engine_and_redoes_later(self, engines, tmp_path, monkeypatch):
        scenes = [{"id": "s1", "display_order": 0, "narrator_text": "First line"},
                  {"id": "s2", "display_order": 1, "narrator_text": None}]
        results = await tts.generate_video_narration(scenes, str(tmp_path), lang="en")
        assert results[0]["status"] == "COMPLETED" and results[0]["engine"] == "piper"
        sidecar = json.loads((tmp_path / "scene_000_s1.words.json").read_text(encoding="utf-8"))
        assert sidecar["engine"] == "piper"

        # Quota is back: a plain run keeps the Piper wav, redo_fallback speaks it with Gemini.
        async def gemini_ok(text, output_path, **kw):
            write_wav(tts.Path(output_path), 1.0, 24000)
            return 1.0
        monkeypatch.setattr(g, "synthesize", gemini_ok)
        kept = await tts.generate_video_narration(scenes, str(tmp_path))
        assert kept[0]["engine"] == "piper" and len(engines) == 1
        redone = await tts.generate_video_narration(scenes, str(tmp_path), redo_fallback=True)
        assert redone[0]["engine"] == "gemini"
        assert json.loads((tmp_path / "scene_000_s1.words.json").read_text(encoding="utf-8"))["engine"] == "gemini"

    def test_fallback_list(self, monkeypatch):
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "Piper, google")
        assert tts.fallback_engines() == ["piper", "google"]
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "none")
        assert tts.fallback_engines() == []


class TestPiperVoice:
    def test_voice_per_language(self, monkeypatch):
        monkeypatch.setattr(config, "PIPER_VOICE", "")
        assert tts.piper_voice_name("ko") == "ko_KR-kss-medium"
        assert tts.piper_voice_name("en-GB") == "en_US-lessac-medium"
        with pytest.raises(RuntimeError, match="PIPER_VOICE"):
            tts.piper_voice_name("xx")
        monkeypatch.setattr(config, "PIPER_VOICE", "en_US-ryan-high")
        assert tts.piper_voice_name("ko") == "en_US-ryan-high"

    @pytest.mark.skipif(not os.environ.get("PIPER_TEST"), reason="downloads a voice; set PIPER_TEST=1 to run")
    def test_real_piper(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "PIPER_VOICE", "")
        monkeypatch.setattr(config, "PIPER_VOICES_DIR", tmp_path / "voices")
        duration = tts._generate_piper_tts("This is a local voice.", str(tmp_path / "out.wav"), "en")
        assert duration > 0.5


class TestLanguage:
    @pytest.mark.parametrize("text, lang, expected", [
        ("Hello there", "en", "en"),
        ("Bonjour", "fr-FR", "fr"),
        ("호송대가 새벽에", "en", "ko"),       # the script wins over the project language
        ("ក្បួននាវា", "ko", "km"),
        ("こんにちは世界", "en", "ja"),
        ("你好世界", "en", "zh"),
        ("漢字", "ja", "ja"),                 # kanji-only line in a Japanese project
        ("Привет", "uk", "uk"),
        ("Hi", "ko", "ko"),                   # Latin text keeps the project language
    ])
    def test_text_language(self, text, lang, expected):
        assert tts.text_language(text, lang) == expected

    def test_kokoro_voice_matches_the_language(self, monkeypatch):
        monkeypatch.setattr(config, "KOKORO_VOICE", "")
        assert tts.kokoro_voice("en") == "af_heart"
        assert tts.kokoro_voice("en", "bf_emma") == "bf_emma"
        assert tts.kokoro_voice("en", "Kore") == "af_heart"         # a Gemini name is ignored
        assert tts.kokoro_voice("fr", "af_heart") == "ff_siwis"    # an English voice can't read French
        assert tts.kokoro_voice("ko") is None
        monkeypatch.setattr(config, "KOKORO_VOICE", "am_michael")
        assert tts.kokoro_voice("en") == "am_michael" and tts.kokoro_voice("es") == "ef_dora"


class TestKokoro:
    @pytest.fixture
    def kokoro(self, monkeypatch, tmp_path):
        """A fake Kokoro server plus stub fallbacks that record what they were asked to speak."""
        requests, spoken, replies = [], [], []
        monkeypatch.setattr(config, "TTS_ENGINE", "kokoro")
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "piper,google")
        monkeypatch.setattr(config, "KOKORO_URL", "http://kokoro.test:9013")
        monkeypatch.setattr(config, "KOKORO_VOICE", "")

        def handler(request):
            requests.append((str(request.url), json.loads(request.content)))
            if replies:
                reply = replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply
            buf = tmp_path / "reply.wav"
            write_wav(buf, 2.0, 24000)
            return httpx.Response(200, content=buf.read_bytes(), headers={"content-type": "audio/wav"})

        real = httpx.AsyncClient
        monkeypatch.setattr(tts.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

        def fake(engine):
            def run(text, output_path, lang=None, *rest):
                spoken.append((engine, lang))
                write_wav(tts.Path(output_path), 1.0)
                return 1.0
            return run
        monkeypatch.setattr(tts, "_generate_piper_tts", fake("piper"))
        monkeypatch.setattr(tts, "_generate_google_tts", fake("google"))
        return requests, spoken, replies

    async def test_english_goes_to_kokoro(self, kokoro, tmp_path):
        requests, spoken, _ = kokoro
        result = await tts.speak("The convoy moves.", str(tmp_path / "a.wav"), lang="en", voice="bf_emma", speed=1.2)
        assert result["engine"] == "kokoro" and result["duration"] == pytest.approx(2.0)
        url, body = requests[0]
        assert url == "http://kokoro.test:9013/tts"
        assert body == {"text": "The convoy moves.", "voice": "bf_emma", "speed": 1.2, "lang_code": "b"}
        assert spoken == []

    async def test_korean_and_khmer_never_reach_kokoro(self, kokoro, tmp_path):
        requests, spoken, _ = kokoro
        ko = await tts.speak("해리스 대령이 신호를 포착합니다.", str(tmp_path / "ko.wav"), lang="en")
        km = await tts.speak("ក្បួននាវាឆ្លងកាត់ច្រកសមុទ្រ", str(tmp_path / "km.wav"), lang="km")
        assert requests == []
        assert (ko["engine"], km["engine"]) == ("piper", "google")  # Piper has no Khmer voice
        assert spoken == [("piper", "ko"), ("google", "km")]
        assert "can't speak 'ko'" in ko["fallback_reason"]

    @pytest.mark.parametrize("reply", [
        httpx.Response(400, json={"detail": "No module named 'pyopenjtalk'"}),
        httpx.Response(503, text="overloaded"),
        httpx.Response(200, text="not audio"),
    ])
    async def test_kokoro_errors_fall_back(self, kokoro, tmp_path, reply):
        _requests, spoken, replies = kokoro
        replies.append(reply)
        result = await tts.speak("Hello.", str(tmp_path / "a.wav"), lang="en")
        assert result["engine"] == "piper" and "Kokoro" in result["fallback_reason"]

    async def test_unreachable_server_falls_back(self, kokoro, tmp_path):
        kokoro[2].append(httpx.ConnectError("All connection attempts failed"))
        result = await tts.speak("Hello.", str(tmp_path / "a.wav"), lang="en")
        assert result["engine"] == "piper" and "unreachable" in result["fallback_reason"]

    async def test_no_engine_for_the_language(self, kokoro, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "piper")
        with pytest.raises(tts.TTSEngineUnavailable, match="no engine"):
            await tts.speak("ក្បួននាវា", str(tmp_path / "km.wav"), lang="km")

    async def test_redo_leaves_lines_kokoro_cannot_speak(self, kokoro, tmp_path, monkeypatch):
        requests, spoken, _ = kokoro

        async def timings(wav_path, text, **kw):
            return {"duration": 1.0, "words": [], "timing_source": "estimated"}
        monkeypatch.setattr(g, "word_timings", timings)
        scenes = [{"id": "ko", "display_order": 0, "narrator_text": "안녕하세요 여러분"},
                  {"id": "en", "display_order": 1, "narrator_text": "Hello everyone"}]
        replies = kokoro[2]
        replies.append(httpx.Response(503, text="busy"))  # English falls back the first time
        first = await tts.generate_video_narration(scenes, str(tmp_path), lang="en")
        assert [r["engine"] for r in first] == ["piper", "piper"]
        redone = await tts.generate_video_narration(scenes, str(tmp_path), lang="en", redo_fallback=True)
        assert [r["engine"] for r in redone] == ["piper", "kokoro"]


class TestMindlogic:
    @pytest.fixture
    def gateway(self, monkeypatch, tmp_path):
        """A fake Mindlogic gateway that answers raw PCM, plus a stub Piper fallback."""
        requests, replies, spoken = [], [], []
        monkeypatch.setattr(config, "TTS_ENGINE", "mindlogic")
        monkeypatch.setattr(config, "TTS_FALLBACK_ENGINE", "piper")
        monkeypatch.setattr(config, "MINDLOGIC_API_KEY", "ml-key")
        monkeypatch.setattr(config, "MINDLOGIC_TTS_VOICE", "")
        monkeypatch.setattr(config, "GEMINI_TTS_VOICE", "Kore")

        def handler(request):
            requests.append((request, json.loads(request.content)))
            if replies:
                return replies.pop(0)
            return httpx.Response(200, content=b"\x01\x00" * 24000 * 2, headers={"content-type": "audio/pcm"})

        real = httpx.AsyncClient
        monkeypatch.setattr(tts.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

        async def no_sleep(_):
            return None
        monkeypatch.setattr(tts.asyncio, "sleep", no_sleep)

        def piper(text, output_path, lang=None, speed=1.0):
            spoken.append(text)
            write_wav(tts.Path(output_path), 1.0)
            return 1.0
        monkeypatch.setattr(tts, "_generate_piper_tts", piper)
        return requests, replies, spoken

    async def test_pcm_becomes_a_wav(self, gateway, tmp_path):
        requests, _replies, spoken = gateway
        out = tmp_path / "a.wav"
        result = await tts.speak("The convoy moves.", str(out), lang="en", voice="Charon", style="Say calmly")
        assert result["engine"] == "mindlogic" and result["duration"] == pytest.approx(2.0)
        assert out.read_bytes()[:4] == b"RIFF"
        request, body = requests[0]
        assert request.headers["authorization"] == "Bearer ml-key"
        assert str(request.url) == config.MINDLOGIC_TTS_URL
        assert body == {"model": config.MINDLOGIC_TTS_MODEL, "input": "Say calmly: The convoy moves.", "voice": "Charon"}
        assert spoken == []

    async def test_kokoro_voice_names_are_not_sent(self, gateway, tmp_path):
        requests, _replies, _spoken = gateway
        await tts.speak("Korean works too: 안녕하세요", str(tmp_path / "a.wav"), voice="af_heart")
        assert requests[0][1]["voice"] == "Kore"

    async def test_out_of_credits_falls_back_and_pauses(self, gateway, tmp_path):
        requests, replies, spoken = gateway
        replies.append(httpx.Response(402, json={"detail": {"code": 402, "message": "credit balance exhausted"}}))
        first = await tts.speak("One.", str(tmp_path / "1.wav"))
        assert first["engine"] == "piper" and "credit balance exhausted" in first["fallback_reason"]
        second = await tts.speak("Two.", str(tmp_path / "2.wav"))
        assert second["engine"] == "piper" and len(requests) == 1  # paused: the gateway isn't asked again
        assert spoken == ["One.", "Two."]

    async def test_rate_limit_retries_before_falling_back(self, gateway, tmp_path):
        requests, replies, _spoken = gateway
        replies.extend([httpx.Response(429, json={"detail": {"code": 429, "message": "slow down"}})] * 2)
        assert (await tts.speak("Hi.", str(tmp_path / "a.wav")))["engine"] == "mindlogic"
        assert len(requests) == 3
        replies.extend([httpx.Response(429, json={"detail": {"code": 429, "message": "slow down"}})] * 4)
        assert (await tts.speak("Hi.", str(tmp_path / "b.wav")))["engine"] == "piper"

    async def test_bad_key_is_an_error_not_a_fallback(self, gateway, tmp_path):
        _requests, replies, spoken = gateway
        replies.append(httpx.Response(401, json={"detail": {"code": 401, "message": "authentication_error"}}))
        with pytest.raises(RuntimeError, match="MINDLOGIC_API_KEY"):
            await tts.speak("Hi.", str(tmp_path / "a.wav"))
        assert spoken == []

    async def test_too_long_line_goes_to_the_fallback(self, gateway, tmp_path):
        requests, _replies, spoken = gateway
        result = await tts.speak("word " * 900, str(tmp_path / "a.wav"))
        assert result["engine"] == "piper" and requests == []
