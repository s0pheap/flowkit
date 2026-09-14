"""Per-scene look & feel: how a scene moves, how long it lasts, how it hands off.

A scene is either animated by Veo (``mode="generate"``, where the motion is
written into the video prompt as a camera direction) or rendered locally from
its keyframe with an ffmpeg pan/zoom (``mode="ffmpeg"``, which never touches
Flow and costs nothing). Either way the transition and length are applied when
the clips are assembled.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

LookFeelMode = Literal["generate", "ffmpeg"]

MotionType = Literal["static", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]

MotionStrength = Literal["subtle", "medium", "strong"]

#: "cut" is a hard cut; everything else is an ffmpeg xfade transition name.
TransitionType = Literal[
    "cut", "fade", "fadeblack", "fadewhite", "dissolve",
    "wipeleft", "wiperight", "slideleft", "slideright",
    "smoothleft", "smoothright", "circleopen", "zoomin",
]

MOTIONS: tuple[str, ...] = MotionType.__args__
STRENGTHS: tuple[str, ...] = MotionStrength.__args__
TRANSITIONS: tuple[str, ...] = TransitionType.__args__


class LookFeel(BaseModel):
    mode: LookFeelMode = "generate"
    motion: MotionType = "static"
    strength: MotionStrength = "medium"
    #: Transition from this scene into the next one.
    transition: TransitionType = "cut"
    transition_duration: float = Field(0.5, ge=0.1, le=2.0)
    #: Fixed scene length in seconds. None follows the narration.
    duration: Optional[float] = Field(None, gt=0.5, le=60)


_PACE = {"subtle": "very slowly and subtly", "medium": "slowly", "strong": "steadily"}

_CAMERA = {
    "static": "The camera holds a locked-off static shot.",
    "zoom_in": "The camera {pace} pushes in toward the subject.",
    "zoom_out": "The camera {pace} pulls back to reveal more of the scene.",
    "pan_left": "The camera {pace} pans to the left.",
    "pan_right": "The camera {pace} pans to the right.",
    "pan_up": "The camera {pace} tilts up.",
    "pan_down": "The camera {pace} tilts down.",
}


def camera_direction(look: LookFeel) -> str:
    """The sentence appended to a Veo prompt for this look."""
    return "Camera direction: " + _CAMERA[look.motion].format(pace=_PACE[look.strength])


def parse_look_feel(raw: Any) -> Optional[LookFeel]:
    """Read a stored look_feel (JSON text, dict, or model). None when unset or unreadable."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, LookFeel):
        return raw
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    try:
        return LookFeel.model_validate(raw)
    except ValidationError:
        return None
