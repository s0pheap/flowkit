"""The model-config API (`agent/api/models.py`).

The admin dashboard renders its dropdowns from the `choices` block this endpoint
returns, so these tests pin that it mirrors the enums PATCH actually validates
against — a UI built on a hardcoded copy would silently offer values the server
rejects. They also pin that `choices` is a read-time addition and never reaches
models.json, since the dashboard PATCHes back the shape it was given.
"""
import json
import shutil

import pytest
from fastapi import HTTPException

from agent import auth, config
from agent.api import models as models_api


@pytest.fixture
def models_file(tmp_path, monkeypatch):
    """A throwaway copy of models.json, so no test can edit the repo's own."""
    target = tmp_path / "models.json"
    shutil.copy(models_api._MODELS_FILE, target)
    monkeypatch.setattr(models_api, "_MODELS_FILE", target)

    # _reload_config mutates module-level config; put it back afterwards.
    saved = (
        dict(config.VIDEO_MODELS), dict(config.UPSCALE_MODELS), dict(config.IMAGE_MODELS),
        dict(config.OMNI_FLASH_MODELS), config.DEFAULT_IMAGE_MODEL,
        config.DEFAULT_VIDEO_MODEL_FAMILY, config.OMNI_FLASH_DURATION_S,
    )
    token = auth._principal.set(auth.Principal(id="t", name="t", is_admin=True))
    yield target
    auth._principal.reset(token)
    config.VIDEO_MODELS.clear(); config.VIDEO_MODELS.update(saved[0])
    config.UPSCALE_MODELS.clear(); config.UPSCALE_MODELS.update(saved[1])
    config.IMAGE_MODELS.clear(); config.IMAGE_MODELS.update(saved[2])
    config.OMNI_FLASH_MODELS.clear(); config.OMNI_FLASH_MODELS.update(saved[3])
    config.DEFAULT_IMAGE_MODEL = saved[4]
    config.DEFAULT_VIDEO_MODEL_FAMILY = saved[5]
    config.OMNI_FLASH_DURATION_S = saved[6]


def _ui_body(data: dict) -> dict:
    """Exactly what the dashboard's Models tab sends on Save."""
    return {
        "default_video_model_family": data["default_video_model_family"],
        "omni_flash_duration_s": data["omni_flash_duration_s"],
        "default_image_model": data["default_image_model"],
        "video_models": data["video_models"],
        "omni_flash_models": data["omni_flash_models"],
        "image_models": data["image_models"],
        "upscale_models": data["upscale_models"],
    }


class TestChoices:
    async def test_choices_mirror_the_enums_patch_validates(self, models_file):
        choices = (await models_api.get_models())["choices"]
        assert choices["default_video_model_family"] == list(config.VIDEO_MODEL_FAMILIES)
        assert choices["omni_flash_duration_s"] == list(config.OMNI_FLASH_DURATIONS)

    async def test_image_choices_come_from_the_configured_models(self, models_file):
        data = await models_api.get_models()
        assert data["choices"]["default_image_model"] == sorted(data["image_models"])
        assert data["default_image_model"] in data["choices"]["default_image_model"]

    async def test_choices_is_read_only_and_never_written(self, models_file):
        await models_api.get_models()
        assert "choices" not in json.loads(models_file.read_text())

    async def test_patching_back_what_get_returned_changes_nothing(self, models_file):
        before = json.loads(models_file.read_text())
        await models_api.patch_models(_ui_body(await models_api.get_models()))
        after = json.loads(models_file.read_text())
        assert "choices" not in after
        assert after == before


class TestValidation:
    async def test_a_real_edit_is_applied(self, models_file):
        await models_api.patch_models({"omni_flash_duration_s": 8})
        assert json.loads(models_file.read_text())["omni_flash_duration_s"] == 8
        assert config.OMNI_FLASH_DURATION_S == 8  # hot-reloaded, no restart

    async def test_a_duration_outside_the_choices_is_refused(self, models_file):
        before = models_file.read_text()
        with pytest.raises(HTTPException) as e:
            await models_api.patch_models({"omni_flash_duration_s": 7})
        assert e.value.status_code == 400
        assert models_file.read_text() == before  # refused, not half-written

    async def test_an_unknown_video_family_is_refused(self, models_file):
        before = models_file.read_text()
        with pytest.raises(HTTPException) as e:
            await models_api.patch_models({"default_video_model_family": "sora"})
        assert e.value.status_code == 400
        assert models_file.read_text() == before

    async def test_a_non_admin_cannot_patch(self, models_file):
        token = auth._principal.set(auth.Principal(id="u", name="u", is_admin=False))
        try:
            with pytest.raises(HTTPException) as e:
                await models_api.patch_models({"omni_flash_duration_s": 8})
            assert e.value.status_code == 403
        finally:
            auth._principal.reset(token)
