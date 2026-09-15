from pydantic import BaseModel, Field, computed_field, model_validator
from typing import Optional
from agent import config
from agent.models.enums import ProjectStatus, PaygateTier, EntityType, VideoModelFamily

#: Length of a Veo scene clip. Omni clips are config.OMNI_FLASH_DURATION_S long.
VEO_CLIP_SECONDS = 8


def video_model_family(project) -> str:
    """The model a project's scene videos use: its own choice, else the server default."""
    stored = project.get("video_model_family") if isinstance(project, dict) else getattr(project, "video_model_family", None)
    return stored if stored in config.VIDEO_MODEL_FAMILIES else config.DEFAULT_VIDEO_MODEL_FAMILY


def video_clip_seconds(family: str) -> int:
    """How long a generated scene clip is for a model family."""
    return config.OMNI_FLASH_DURATION_S if family == "omni_flash" else VEO_CLIP_SECONDS


class CharacterInput(BaseModel):
    """Reference entity stub provided at project creation time."""
    name: str
    entity_type: EntityType = "character"
    description: Optional[str] = None
    voice_description: Optional[str] = None  # max ~30 words, characters/creatures only


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    story: Optional[str] = None
    language: str = "en"
    user_paygate_tier: PaygateTier = "PAYGATE_TIER_ONE"
    tool_name: str = "PINHOLE"
    # Flow stopped letting clients create projects in the September 2026
    # migration, so a project is made once in the Flow UI and its uuid supplied
    # here. Falls back to FLOW_PROJECT_ID when omitted.
    flow_project_id: Optional[str] = None
    material: str = Field("realistic", pattern=r"^[a-z0-9][a-z0-9_]{1,63}$")  # material ID from GET /api/materials
    style: Optional[str] = None  # deprecated: use material instead; "3D"→"3d_pixar", "photorealistic"→"realistic"
    allow_music: bool = False  # when True, skip "no background music" suffix in video prompts
    allow_voice: bool = False  # when True, keep character dialogue in video audio (suppress only music/narration)
    video_model_family: Optional[VideoModelFamily] = None  # "veo" or "omni_flash"; None = server default
    characters: Optional[list[CharacterInput]] = None

    @model_validator(mode="before")
    @classmethod
    def map_style_to_material(cls, data):
        if isinstance(data, dict):
            style = data.get("style")
            # Only map if style is provided AND material is not explicitly set
            if style and "material" not in data:
                compat_map = {"3D": "3d_pixar", "3d": "3d_pixar", "photorealistic": "realistic"}
                data["material"] = compat_map.get(style, style.lower().replace(" ", "_"))
        return data


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    story: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: Optional[str] = None
    status: Optional[ProjectStatus] = None
    user_paygate_tier: Optional[PaygateTier] = None
    narrator_voice: Optional[str] = None
    narrator_ref_audio: Optional[str] = None
    material: Optional[str] = None
    allow_music: Optional[bool] = None
    allow_voice: Optional[bool] = None
    video_model_family: Optional[VideoModelFamily] = None  # send null to go back to the server default


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    story: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: str = "en"
    status: str = "ACTIVE"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"
    material: Optional[str] = None
    allow_music: bool = False
    allow_voice: bool = False
    video_model_family: Optional[VideoModelFamily] = None
    narrator_voice: Optional[str] = None
    narrator_ref_audio: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @computed_field
    @property
    def effective_video_model_family(self) -> str:
        """video_model_family, or the server default when the project has none."""
        return video_model_family(self)

    @computed_field
    @property
    def video_clip_seconds(self) -> int:
        """Length of this project's generated scene clips."""
        return video_clip_seconds(self.effective_video_model_family)
