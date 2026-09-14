"""SRT cue building from word timings."""
from agent.services import subtitles as sub


def _words(text: str, step: float = 0.4, start: float = 0.0):
    return [{"word": w, "start": start + i * step, "end": start + i * step + step * 0.9}
            for i, w in enumerate(text.split())]


class TestBuildCues:
    def test_breaks_at_sentence_end(self):
        cues = sub.build_cues(_words("Iran attacked. The convoy turned."), max_chars=42)
        assert [c["text"] for c in cues] == ["Iran attacked.", "The convoy turned."]

    def test_breaks_on_length(self):
        cues = sub.build_cues(_words("one two three four five six seven eight nine ten"), max_chars=15)
        assert all(len(c["text"]) <= 15 for c in cues)
        assert " ".join(c["text"] for c in cues) == "one two three four five six seven eight nine ten"

    def test_last_word_of_sentence_is_not_orphaned(self):
        cues = sub.build_cues(_words("Colonel Harris detects unusual radar signatures."), max_chars=42)
        assert [c["text"] for c in cues] == ["Colonel Harris detects unusual radar signatures."]

    def test_breaks_on_duration(self):
        cues = sub.build_cues(_words("a b c d e f g h i j k l", step=1.0), max_chars=80, max_seconds=4.0)
        assert all(c["end"] - c["start"] <= 4.0 for c in cues)

    def test_short_cue_is_stretched_but_never_overlaps(self):
        words = [{"word": "Go.", "start": 0.0, "end": 0.2}, {"word": "Now.", "start": 0.5, "end": 0.9}]
        cues = sub.build_cues(words)
        assert cues[0]["end"] == 0.5
        assert cues[1]["end"] == 1.2

    def test_empty(self):
        assert sub.build_cues([]) == []


class TestShiftWords:
    def test_offsets_and_drops_words_past_the_cut(self):
        shifted = sub.shift_words(_words("a b c d", step=1.0), offset=10.0, window=2.5)
        assert [w["word"] for w in shifted] == ["a", "b", "c"]
        assert shifted[0]["start"] == 10.0
        assert shifted[-1]["end"] == 12.5


class TestSrt:
    def test_timestamp_format(self):
        assert sub.format_timestamp(3725.5) == "01:02:05,500"
        assert sub.format_timestamp(0) == "00:00:00,000"

    def test_srt_blocks(self):
        srt = sub.to_srt([{"start": 0, "end": 1.2, "text": "Hello."}, {"start": 1.5, "end": 2, "text": "World."}])
        assert srt == "1\n00:00:00,000 --> 00:00:01,200\nHello.\n\n2\n00:00:01,500 --> 00:00:02,000\nWorld.\n"


class TestDefaultMaxChars:
    def test_korean_is_shorter(self):
        assert sub.default_max_chars("북한 병사가 국경을 넘었다") == 20

    def test_english(self):
        assert sub.default_max_chars("The soldier crossed the border") == 42
