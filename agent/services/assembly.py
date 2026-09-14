"""The assembly timeline: how long each scene runs, where it starts, how it hands off.

Pure functions only. The review board, the subtitle writer and
/fk-concat-fit-narrator all read the same plan, so captions land where the
narration actually plays.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent.models.look_feel import LookFeel

#: /fk-concat-fit-narrator seeks past Veo's static first second (`-ss 1`).
VEO_SKIP_HEAD = 1.0
VEO_CLIP_SECONDS = 8.0
#: An ffmpeg scene with no narration and no fixed length.
DEFAULT_MOTION_SECONDS = 5.0
NARRATION_BUFFER = 0.5
#: A Veo scene given a fixed length longer than its clip plays the clip slower, down to this speed.
VEO_MIN_SPEED = 0.6


@dataclass
class SceneTiming:
    scene_id: str
    display_order: int
    look: LookFeel
    narration_duration: Optional[float] = None
    #: Length of the Veo clip on disk, when known.
    clip_duration: Optional[float] = None


def scene_duration(item: SceneTiming, buffer: float = NARRATION_BUFFER) -> float:
    """Seconds this scene occupies before any transition overlap is taken off."""
    look = item.look
    if look.duration:
        duration = look.duration
    elif item.narration_duration:
        duration = item.narration_duration + buffer
    elif look.mode == "generate":
        duration = (item.clip_duration or VEO_CLIP_SECONDS) - VEO_SKIP_HEAD
    else:
        duration = DEFAULT_MOTION_SECONDS

    if look.mode == "generate":
        # Narration alone never stretches a Veo clip. A fixed length does, in slow motion,
        # as far as VEO_MIN_SPEED allows.
        usable = _usable(item)
        duration = min(duration, usable / VEO_MIN_SPEED if look.duration else usable)
    return round(max(duration, 0.5), 3)


def _usable(item: SceneTiming) -> float:
    return (item.clip_duration or VEO_CLIP_SECONDS) - VEO_SKIP_HEAD


def clip_speed(item: SceneTiming, duration: float) -> float:
    """Playback speed of the scene's clip: below 1.0 when a Veo clip is stretched to a fixed length."""
    if item.look.mode != "generate" or duration <= 0:
        return 1.0
    return round(min(1.0, _usable(item) / duration), 4)


def plan_timeline(items: list[SceneTiming], buffer: float = NARRATION_BUFFER) -> list[dict]:
    """Ordered segments with start offsets on the final timeline.

    A transition overlaps the tail of one scene with the head of the next, so
    each overlap is capped at half of either scene to keep a transition from
    swallowing a short shot.
    """
    ordered = sorted(items, key=lambda i: i.display_order)
    durations = [scene_duration(i, buffer) for i in ordered]
    segments = []
    start = 0.0
    for idx, item in enumerate(ordered):
        duration = durations[idx]
        is_last = idx == len(ordered) - 1
        transition = "cut" if is_last else item.look.transition
        overlap = 0.0
        if transition != "cut":
            overlap = round(min(item.look.transition_duration, duration / 2, durations[idx + 1] / 2), 3)
        segments.append({
            "scene_id": item.scene_id,
            "display_order": item.display_order,
            "mode": item.look.mode,
            "motion": item.look.motion,
            "strength": item.look.strength,
            "start": round(start, 3),
            "duration": duration,
            "end": round(start + duration, 3),
            "trim_start": VEO_SKIP_HEAD if item.look.mode == "generate" else 0.0,
            "speed": clip_speed(item, duration),
            "narration_duration": item.narration_duration,
            "transition": transition,
            "transition_duration": overlap,
        })
        start += duration - overlap
    return segments


def total_duration(segments: list[dict]) -> float:
    return segments[-1]["end"] if segments else 0.0


def group_segments(segments: list[dict]) -> list[list[int]]:
    """Runs of segment indexes joined by transitions; hard cuts start a new run."""
    groups: list[list[int]] = []
    current: list[int] = []
    for idx, seg in enumerate(segments):
        current.append(idx)
        if seg["transition"] == "cut":
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def xfade_filter(segments: list[dict]) -> Optional[str]:
    """filter_complex joining one group's trimmed clips (inputs 0..N-1) into [vout]/[aout].

    None for a single-scene group, which needs no filter.
    """
    if len(segments) < 2:
        return None
    video, audio = [], []
    elapsed = segments[0]["duration"]
    last = len(segments) - 2
    for i in range(len(segments) - 1):
        overlap = segments[i]["transition_duration"]
        offset = round(elapsed - overlap, 3)
        v_in = "[0:v][1:v]" if i == 0 else f"[v{i}][{i + 1}:v]"
        a_in = "[0:a][1:a]" if i == 0 else f"[a{i}][{i + 1}:a]"
        v_out = "[vout]" if i == last else f"[v{i + 1}]"
        a_out = "[aout]" if i == last else f"[a{i + 1}]"
        video.append(
            f"{v_in}xfade=transition={segments[i]['transition']}:duration={overlap}:offset={offset}{v_out}"
        )
        audio.append(f"{a_in}acrossfade=d={overlap}{a_out}")
        elapsed = offset + segments[i + 1]["duration"]
    return ";".join(video + audio)
