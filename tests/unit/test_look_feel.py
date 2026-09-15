"""Look & feel parsing, the assembly timeline, and the ffmpeg motion filter."""
import pytest

from agent.models.look_feel import LookFeel, camera_direction, parse_look_feel
from agent.services import assembly
from agent.services.motion import build_motion_command, build_motion_filter, zoompan_expressions


def _item(order, narration=None, clip=None, **look):
    return assembly.SceneTiming(scene_id=f"s{order}", display_order=order, look=LookFeel(**look),
                                narration_duration=narration, clip_duration=clip)


class TestParseLookFeel:
    def test_json_text(self):
        look = parse_look_feel('{"mode": "ffmpeg", "motion": "zoom_in"}')
        assert look.mode == "ffmpeg" and look.motion == "zoom_in" and look.transition == "cut"

    @pytest.mark.parametrize("raw", [None, "", "not json", '{"motion": "spin"}', 5])
    def test_unset_or_invalid_is_none(self, raw):
        assert parse_look_feel(raw) is None

    def test_camera_direction(self):
        assert camera_direction(LookFeel(motion="pan_left", strength="subtle")) == \
            "Camera direction: The camera very slowly and subtly pans to the left."


class TestSceneDuration:
    def test_follows_narration_plus_buffer(self):
        assert assembly.scene_duration(_item(0, narration=5.86)) == 6.36

    def test_fixed_length_stretches_a_veo_clip_in_slow_motion(self):
        item = _item(0, narration=9.3, duration=10.0)
        assert assembly.scene_duration(item) == 10.0
        assert assembly.clip_speed(item, 10.0) == 0.7
        # Never slower than VEO_MIN_SPEED: 7s usable / 0.6 = 11.667s at most.
        assert assembly.scene_duration(_item(0, duration=20.0)) == 11.667
        # Narration alone still caps, and ffmpeg scenes never change speed.
        assert assembly.clip_speed(_item(0, narration=5.0), 5.5) == 1.0
        assert assembly.clip_speed(_item(0, mode="ffmpeg", duration=10.0), 10.0) == 1.0
        segment = assembly.plan_timeline([item])[0]
        assert segment["speed"] == 0.7 and segment["duration"] == 10.0

    def test_veo_scene_is_capped_at_usable_clip(self):
        assert assembly.scene_duration(_item(0, narration=9.0)) == 7.0
        assert assembly.scene_duration(_item(0, narration=9.0, clip=10.0)) == 9.0

    def test_ffmpeg_scene_can_run_long(self):
        assert assembly.scene_duration(_item(0, narration=11.5, mode="ffmpeg")) == 12.0

    def test_fixed_duration_wins(self):
        assert assembly.scene_duration(_item(0, narration=3.0, mode="ffmpeg", duration=9.0)) == 9.0

    def test_no_narration_defaults(self):
        assert assembly.scene_duration(_item(0)) == 7.0
        assert assembly.scene_duration(_item(0, mode="ffmpeg")) == assembly.DEFAULT_MOTION_SECONDS


class TestPlanTimeline:
    def test_transitions_overlap_and_shift_starts(self):
        segs = assembly.plan_timeline([
            _item(0, narration=5.5, mode="ffmpeg", transition="fade", transition_duration=0.5),
            _item(1, narration=4.5, transition="cut"),
            _item(2, narration=3.5, mode="ffmpeg", transition="dissolve"),
        ])
        assert [s["start"] for s in segs] == [0.0, 5.5, 10.5]
        assert segs[0]["transition_duration"] == 0.5
        assert segs[1]["transition_duration"] == 0.0
        # The last scene has nothing to transition into.
        assert segs[2]["transition"] == "cut"
        assert assembly.total_duration(segs) == 14.5
        assert segs[1]["trim_start"] == 1.0 and segs[0]["trim_start"] == 0.0

    def test_overlap_capped_at_half_the_shorter_scene(self):
        segs = assembly.plan_timeline([
            _item(0, mode="ffmpeg", duration=1.0, transition="fade", transition_duration=2.0),
            _item(1, mode="ffmpeg", duration=6.0),
        ])
        assert segs[0]["transition_duration"] == 0.5

    def test_sorted_by_display_order(self):
        segs = assembly.plan_timeline([_item(2), _item(0), _item(1)])
        assert [s["display_order"] for s in segs] == [0, 1, 2]


class TestGroupsAndXfade:
    def test_cuts_split_groups(self):
        segs = assembly.plan_timeline([
            _item(0, mode="ffmpeg", duration=4, transition="fade"),
            _item(1, mode="ffmpeg", duration=4, transition="cut"),
            _item(2, mode="ffmpeg", duration=4, transition="wipeleft"),
            _item(3, mode="ffmpeg", duration=4),
        ])
        assert assembly.group_segments(segs) == [[0, 1], [2, 3]]

    def test_xfade_offsets_chain(self):
        segs = assembly.plan_timeline([
            _item(0, mode="ffmpeg", duration=4, transition="fade", transition_duration=0.5),
            _item(1, mode="ffmpeg", duration=5, transition="slideleft", transition_duration=1.0),
            _item(2, mode="ffmpeg", duration=6),
        ])
        fc = assembly.xfade_filter(segs)
        assert "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.5[v1]" in fc
        assert "[v1][2:v]xfade=transition=slideleft:duration=1.0:offset=7.5[vout]" in fc
        assert "[0:a][1:a]acrossfade=d=0.5[a1]" in fc and "[a1][2:a]acrossfade=d=1.0[aout]" in fc
        # xfade offsets land exactly where the plan says the next scene starts.
        assert segs[2]["start"] == 7.5

    def test_single_segment_needs_no_filter(self):
        assert assembly.xfade_filter(assembly.plan_timeline([_item(0)])) is None


class TestMotionFilter:
    def test_zoom_in_grows_from_one(self):
        z, x, y = zoompan_expressions("zoom_in", "medium", 121)
        assert z == "1+0.1600*on/120"
        assert x == "iw/2-(iw/zoom/2)"

    def test_pan_left_travels_right_to_left(self):
        z, x, _ = zoompan_expressions("pan_left", "strong", 49)
        assert z == "1.2800" and x == "(iw-iw/zoom)*(1-on/48)"

    def test_filter_frames_and_size(self):
        vf = build_motion_filter(LookFeel(motion="zoom_out"), 5.0, 1080, 1920)
        assert "d=120:s=1080x1920:fps=24" in vf
        assert vf.startswith("scale=3240:5760:force_original_aspect_ratio=increase,crop=3240:5760,")

    def test_command_has_silent_audio_and_duration(self):
        cmd = build_motion_command("in.jpg", "out.mp4", LookFeel(), 6.36, "HORIZONTAL", preview=True)
        assert "anullsrc=r=48000:cl=stereo" in cmd
        assert cmd[cmd.index("-t") + 1] == "6.360"
        assert "s=960x540" in cmd[cmd.index("-filter_complex") + 1]



class TestRemoteClipDurations:
    @pytest.fixture(autouse=True)
    def empty_cache(self, monkeypatch):
        from agent.api import look_feel as api
        monkeypatch.setattr(api, "_remote_clip_seconds", {})
        return api

    async def test_measures_each_clip_once_across_re_signed_urls(self, empty_cache, monkeypatch):
        api = empty_cache
        probed = []
        monkeypatch.setattr(api, "_probe_remote_duration", lambda url: probed.append(url) or 10.005)

        first = await api._remote_clip_durations(["https://flow-content.google/video/m1?sig=a"])
        again = await api._remote_clip_durations(["https://flow-content.google/video/m1?sig=b"])

        assert first == {"https://flow-content.google/video/m1?sig=a": 10.005}
        assert again == {"https://flow-content.google/video/m1?sig=b": 10.005}
        assert len(probed) == 1

    async def test_a_failed_probe_is_left_out_and_tried_again_later(self, empty_cache, monkeypatch):
        api = empty_cache
        results = iter([None, 8.0])
        monkeypatch.setattr(api, "_probe_remote_duration", lambda url: next(results))

        assert await api._remote_clip_durations(["https://x/video/m2?sig=old"]) == {}
        assert await api._remote_clip_durations(["https://x/video/m2?sig=new"]) == {"https://x/video/m2?sig=new": 8.0}
