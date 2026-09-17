"""Model configuration API — view and update video/image/upscale model keys."""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agent import auth, config

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)

_MODELS_FILE = Path(__file__).parent.parent / "models.json"


def _read_models() -> dict:
    with open(_MODELS_FILE) as f:
        return json.load(f)


def _write_models(data: dict):
    with open(_MODELS_FILE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _reload_config(data: dict):
    """Hot-reload model keys into the running config module."""
    config.VIDEO_MODELS.clear()
    config.VIDEO_MODELS.update(data["video_models"])
    config.UPSCALE_MODELS.clear()
    config.UPSCALE_MODELS.update(data["upscale_models"])
    config.IMAGE_MODELS.clear()
    config.IMAGE_MODELS.update(data["image_models"])
    config.DEFAULT_IMAGE_MODEL = data.get("default_image_model", "NANO_BANANA_PRO")
    config.OMNI_FLASH_MODELS.clear()
    config.OMNI_FLASH_MODELS.update(data.get("omni_flash_models", {}))
    config.DEFAULT_VIDEO_MODEL_FAMILY = data.get("default_video_model_family", "veo")
    config.OMNI_FLASH_DURATION_S = int(data.get("omni_flash_duration_s", 10))


@router.get("")
async def get_models():
    """Return current model configuration, plus what PATCH will accept.

    The `choices` block mirrors the enums PATCH validates against, so a UI can
    offer exactly the values that will be accepted instead of hardcoding a copy
    that drifts when config changes.
    """
    data = _read_models()
    data["choices"] = {
        "default_video_model_family": list(config.VIDEO_MODEL_FAMILIES),
        "omni_flash_duration_s": list(config.OMNI_FLASH_DURATIONS),
        "default_image_model": sorted(data.get("image_models", {})),
        "batch_video_models": list(data.get("batch_video_models", {}).get("accepted", [])),
    }
    return data


@router.patch("")
async def patch_models(body: dict):
    """Update model keys. Merges provided keys into existing config.

    Example body to change video model for TIER_TWO i2v portrait:
    {
      "video_models": {
        "PAYGATE_TIER_TWO": {
          "frame_2_video": {
            "VIDEO_ASPECT_RATIO_PORTRAIT": "veo_3_1_i2v_s_fast_portrait_ultra"
          }
        }
      }
    }

    Make Omni Flash the server default for scene videos (a project's own
    video_model_family still wins), with 10-second clips:
    {"default_video_model_family": "omni_flash", "omni_flash_duration_s": 10}

    Omni Flash duration keys are configurable too:
    {
      "omni_flash_models": {
        "reference_to_video": {"10": "abra_r2v_10s"}
      }
    }
    """
    auth.require_admin()
    current = _read_models()

    if "default_image_model" in body:
        current["default_image_model"] = body["default_image_model"]
    if "default_video_model_family" in body:
        if body["default_video_model_family"] not in config.VIDEO_MODEL_FAMILIES:
            raise HTTPException(400, f"default_video_model_family must be one of {list(config.VIDEO_MODEL_FAMILIES)}")
        current["default_video_model_family"] = body["default_video_model_family"]
    if "omni_flash_duration_s" in body:
        if body["omni_flash_duration_s"] not in config.OMNI_FLASH_DURATIONS:
            raise HTTPException(400, f"omni_flash_duration_s must be one of {list(config.OMNI_FLASH_DURATIONS)}")
        current["omni_flash_duration_s"] = body["omni_flash_duration_s"]

    # Deep merge: only update keys that are provided.
    for section in (
        "video_models",
        "omni_flash_models",
        "image_models",
        "upscale_models",
    ):
        if section not in body:
            continue
        if section in ("upscale_models", "image_models"):
            # Flat dict — direct merge.
            current.setdefault(section, {}).update(body[section])
        elif section == "omni_flash_models":
            # Nested by generation mode -> duration -> model key.
            target = current.setdefault(section, {})
            for mode, durations in body[section].items():
                target.setdefault(mode, {}).update(durations)
        else:
            # Nested dict — merge per tier, per gen_type.
            for tier, gen_types in body[section].items():
                if tier not in current[section]:
                    current[section][tier] = {}
                for gen_type, ratios in gen_types.items():
                    if gen_type not in current[section][tier]:
                        current[section][tier][gen_type] = {}
                    current[section][tier][gen_type].update(ratios)

    _write_models(current)
    _reload_config(current)
    logger.info("Models updated and hot-reloaded: %s", list(body.keys()))

    return {"status": "updated", "models": current}
