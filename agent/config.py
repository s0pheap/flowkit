"""Configuration constants."""
import json
import os
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────
BASE_DIR = Path(os.environ.get("FLOW_AGENT_DIR", Path(__file__).parent.parent))
DB_PATH = BASE_DIR / "flow_agent.db"

# ─── Load .env file ──────────────────────────────────────────
def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and k not in os.environ:
                    os.environ[k] = v

_load_env()

# ─── API Server ──────────────────────────────────────────────
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8100"))

# ─── API keys (multi-user) ───────────────────────────────────
# Off by default: a local agent trusts every caller. Turn on before exposing
# :8100 to anyone else. Then every /api and /ws call needs `X-API-Key` (or
# `Authorization: Bearer`), users see only the Flow projects granted to them,
# and settings that apply to the whole server are admin-only.
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "0") == "1"
# Bootstrap admin key, so there is a way in before any user exists. Users and
# their keys are then managed with `python -m agent.users` or /api/admin/users.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
# The address users reach this agent at (https://flowkit.example.com). Written
# into the install scripts; derived from the request when unset.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")
# Built dashboard (cd dashboard && npm run build). Served at / when present.
DASHBOARD_DIST = Path(os.environ.get("DASHBOARD_DIST", Path(__file__).parent.parent / "dashboard" / "dist"))

# ─── Server-side final render ────────────────────────────────
# Font file for burned-in text overlays and font name for burned subtitles.
# Empty = pick one for the OS (Malgun Gothic on Windows, Noto CJK on Linux).
OVERLAY_FONT = os.environ.get("OVERLAY_FONT", "")
SUBTITLE_FONT = os.environ.get("SUBTITLE_FONT", "")

# ─── WebSocket Server (extension connects here) ─────────────
WS_HOST = os.environ.get("WS_HOST", "127.0.0.1")
WS_PORT = int(os.environ.get("WS_PORT", "9222"))

# ─── Google Flow API ────────────────────────────────────────
# Legacy REST host. Flow moved to flow.google.com in September 2026 and stopped
# minting the `Bearer ya29.…` this host needs, so these are only reachable with
# USE_BATCH_RPC=0 on a browser profile that still has an old token.
GOOGLE_FLOW_API = "https://aisandbox-pa.googleapis.com"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY")
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV")

# ─── Flow batchexecute (the current path) ───────────────────
# Every call is signed in the page with the session cookie plus a per-page `at`
# token, so the extension runs it inside a signed-in flow.google.com tab. Set
# USE_BATCH_RPC=0 only to fall back to the dead REST path for a post-mortem.
USE_BATCH_RPC = os.environ.get("USE_BATCH_RPC", "1") == "1"

# The Flow project every RPC is scoped to. Project creation went with the old
# labs.google tRPC endpoint, so a project is made once in the Flow UI and its
# uuid pinned here; POST /api/projects falls back to it when no id is given.
FLOW_PROJECT_ID = os.environ.get("FLOW_PROJECT_ID", "c44bcef5-de99-4b52-b8a5-27f0fe67bc67")

# Capabilities whose payloads were never captured off the new UI (4K upscale,
# reference-to-video, start+end-frame chaining) fail loudly by default. With
# this on, the two that have a sane fallback degrade instead: chaining and r2v
# both drop to plain i2v off the start frame. Upscale has no fallback.
FLOW_ALLOW_DEGRADED = os.environ.get("FLOW_ALLOW_DEGRADED", "0") == "1"

# The tier no longer picks a model — aspect is its own slot and the model names
# are fixed — so it is only carried for the DB column and the dashboard.
DEFAULT_PAYGATE_TIER = os.environ.get("DEFAULT_PAYGATE_TIER", "PAYGATE_TIER_TWO")

# ─── Worker ──────────────────────────────────────────────────
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
VIDEO_POLL_INTERVAL = int(os.environ.get("VIDEO_POLL_INTERVAL", "10"))  # polling interval for video/upscale status
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
VIDEO_POLL_TIMEOUT = int(os.environ.get("VIDEO_POLL_TIMEOUT", "420"))
API_COOLDOWN = int(os.environ.get("API_COOLDOWN", "10"))  # seconds between API calls (anti-spam)
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "5"))  # Google Flow max parallel requests
STALE_PROCESSING_TIMEOUT = int(os.environ.get("STALE_PROCESSING_TIMEOUT", "600"))  # 10 min

# ─── Model Keys (loaded from models.json for easy updates) ──
_MODELS_FILE = Path(__file__).parent / "models.json"
with open(_MODELS_FILE) as _f:
    _MODELS = json.load(_f)

VIDEO_MODELS = _MODELS["video_models"]
UPSCALE_MODELS = _MODELS["upscale_models"]
IMAGE_MODELS = _MODELS["image_models"]
# Nickname from image_models. The batch path accepts GEM_PIX_2 (Nano Banana Pro)
# and NARWHAL (Banana 2) and rejects everything else.
DEFAULT_IMAGE_MODEL = _MODELS.get("default_image_model", "NANO_BANANA_PRO")

# Which model makes scene videos: "veo" or "omni_flash". A project's own
# video_model_family wins over this. Omni picks its wire key from
# omni_flash_models by clip length (4, 6, 8 or 10 seconds).
VIDEO_MODEL_FAMILIES = ("veo", "omni_flash")
OMNI_FLASH_DURATIONS = (4, 6, 8, 10)
DEFAULT_VIDEO_MODEL_FAMILY = _MODELS.get("default_video_model_family", "veo")
OMNI_FLASH_MODELS = _MODELS.get("omni_flash_models", {})
OMNI_FLASH_DURATION_S = int(_MODELS.get("omni_flash_duration_s", 10))

# ─── API Endpoints ───────────────────────────────────────────
ENDPOINTS = {
    "generate_images": "/v1/projects/{project_id}/flowMedia:batchGenerateImages",
    "generate_video": "/v1/video:batchAsyncGenerateVideoStartImage",
    "generate_video_start_end": "/v1/video:batchAsyncGenerateVideoStartAndEndImage",
    "generate_video_references": "/v1/video:batchAsyncGenerateVideoReferenceImages",
    "upscale_video": "/v1/video:batchAsyncGenerateVideoUpsampleVideo",
    "upscale_image": "/v1/flow/upsampleImage",
    "upload_image": "/v1/flow/uploadImage",
    "check_video_status": "/v1/video:batchCheckAsyncVideoGenerationStatus",
    "get_credits": "/v1/credits",
    "get_media": "/v1/media/{media_id}",
}

# ─── Output Directories ─────────────────────────────────────
OUTPUT_DIR = BASE_DIR / "output"
SHARED_OUTPUT_DIR = OUTPUT_DIR / "_shared"
# Font files for burned subtitles that the OS doesn't have (e.g. KantumruyPro-Bold.ttf for Khmer).
SUBTITLE_FONTS_DIR = Path(os.environ.get("SUBTITLE_FONTS_DIR", "") or SHARED_OUTPUT_DIR / "fonts")
TTS_TEMPLATES_DIR = SHARED_OUTPUT_DIR / "tts_templates"
MUSIC_OUTPUT_DIR = SHARED_OUTPUT_DIR / "music"

# ─── TTS (Gemini / Mindlogic / Kokoro / Piper / Google TTS / OmniVoice) ───
TTS_ENGINE = os.environ.get("TTS_ENGINE", "gemini")  # "gemini" (default), "mindlogic" (Gemini via the Mindlogic gateway), "kokoro" (your Kokoro server), "piper" (free, local), "google" (free gTTS) or "omnivoice"
# Engines to try, in order, when TTS_ENGINE can't speak a line (its language, quota, server down). "none" turns this off.
TTS_FALLBACK_ENGINE = os.environ.get("TTS_FALLBACK_ENGINE", "piper")
TTS_LANG = os.environ.get("TTS_LANG", "en")          # default language (e.g. "en", "vi", "ja", "fr")
TTS_TLD = os.environ.get("TTS_TLD", "com")           # domain/accent: "com" (US), "co.uk" (UK), "ca", "co.in"
TTS_MODEL = os.environ.get("TTS_MODEL", "k2-fsa/OmniVoice")
TTS_DEVICE = os.environ.get("TTS_DEVICE", "cpu")     # MPS produces gibberish; CPU+fp32 works
TTS_SAMPLE_RATE = int(os.environ.get("TTS_SAMPLE_RATE", "24000"))

# Gemini TTS speaks the narration; a second Gemini audio model reports word
# timings for subtitles (Gemini TTS itself returns audio only).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
GEMINI_TTS_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")
GEMINI_TIMING_MODEL = os.environ.get("GEMINI_TIMING_MODEL", "gemini-2.5-flash")
GEMINI_TTS_CONCURRENCY = int(os.environ.get("GEMINI_TTS_CONCURRENCY", "2"))
# After a daily quota runs out, skip Gemini for this long before trying it again.
GEMINI_QUOTA_COOLDOWN = int(os.environ.get("GEMINI_QUOTA_COOLDOWN", "3600"))

# Word timings for subtitles, tried in order until one works: "gemini" (GEMINI_TIMING_MODEL)
# and/or "whisper" (local faster-whisper, no quota), e.g. "whisper,gemini".
TIMING_ENGINE = os.environ.get("TIMING_ENGINE", "gemini")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")  # size name, or a model folder (relative to the repo)
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")  # "auto" (GPU, else CPU), "cuda" or "cpu"
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "")  # empty: float16 on cuda, int8 on cpu

# A self-hosted Kokoro-82M server: POST {text, voice, speed, lang_code} returns a wav.
# It speaks English, Spanish, French, Hindi, Italian, Portuguese, Japanese and Mandarin.
KOKORO_URL = os.environ.get("KOKORO_URL", "")  # e.g. http://10.255.78.58:9013/tts
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "")  # e.g. af_heart; used for lines in that voice's language
KOKORO_TIMEOUT = float(os.environ.get("KOKORO_TIMEOUT", "300"))

# Gemini TTS through the Mindlogic API gateway (TTS_ENGINE=mindlogic): billed in gateway
# credits instead of Google quota. Same prebuilt voices as Gemini; returns raw 24 kHz PCM.
MINDLOGIC_API_KEY = os.environ.get("MINDLOGIC_API_KEY", "")
MINDLOGIC_TTS_URL = os.environ.get("MINDLOGIC_TTS_URL", "https://factchat-cloud.mindlogic.ai/v1/gateway/audio/speech/")
MINDLOGIC_TTS_MODEL = os.environ.get("MINDLOGIC_TTS_MODEL", "gemini-3.1-flash-tts-preview")
MINDLOGIC_TTS_VOICE = os.environ.get("MINDLOGIC_TTS_VOICE", "")  # empty: GEMINI_TTS_VOICE
MINDLOGIC_TIMEOUT = float(os.environ.get("MINDLOGIC_TIMEOUT", "180"))

# Piper runs on this machine for free. A voice is a name from
# https://huggingface.co/rhasspy/piper-voices ("en_US-ryan-high") or a path to an
# .onnx file; empty picks one for the project's language. Voices download on first use.
PIPER_VOICE = os.environ.get("PIPER_VOICE", "")
PIPER_VOICES_DIR = Path(os.environ.get("PIPER_VOICES_DIR", "") or SHARED_OUTPUT_DIR / "piper_voices")

# ─── Review / Claude Vision ──────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "claude-haiku-4-5-20251001")
REVIEW_FPS_LIGHT = float(os.environ.get("REVIEW_FPS_LIGHT", "4"))
REVIEW_FPS_DEEP = float(os.environ.get("REVIEW_FPS_DEEP", "8"))
REVIEW_MAX_FRAMES = int(os.environ.get("REVIEW_MAX_FRAMES", "64"))
REVIEW_SHEET_COLS = int(os.environ.get("REVIEW_SHEET_COLS", "3"))
REVIEW_SHEET_ROWS = int(os.environ.get("REVIEW_SHEET_ROWS", "3"))

# ─── CLI Providers (video review vision analysis) ────────────
_PROVIDERS_FILE = Path(__file__).parent / "providers.json"
with open(_PROVIDERS_FILE) as _pvf:
    CLI_PROVIDERS = json.load(_pvf)  # mutable dict, hot-reloaded like VIDEO_MODELS
REVIEW_CLI_TIMEOUT_S = float(os.environ.get("REVIEW_CLI_TIMEOUT_S", "120"))

# ─── Suno (Music Generation) — sunoapi.org ──────────────────
def _load_suno_key() -> str:
    """Load Suno API key: env var first, then channel_rules.json fallback."""
    key = os.environ.get("SUNO_API_KEY", "")
    if key:
        return key
    channels_dir = BASE_DIR / "youtube" / "channels"
    if channels_dir.exists():
        for rules_file in channels_dir.glob("*/channel_rules.json"):
            try:
                rules = json.loads(rules_file.read_text())
                key = rules.get("api_keys", {}).get("suno", "")
                if key:
                    return key
            except (json.JSONDecodeError, OSError):
                continue
    return ""

SUNO_API_KEY = _load_suno_key()
SUNO_BASE_URL = os.environ.get("SUNO_BASE_URL", "https://api.sunoapi.org")
SUNO_MODEL = os.environ.get("SUNO_MODEL", "V4")
SUNO_CALLBACK_URL = os.environ.get("SUNO_CALLBACK_URL", f"http://{API_HOST}:{API_PORT}/api/music/callback")
SUNO_POLL_INTERVAL = int(os.environ.get("SUNO_POLL_INTERVAL", "5"))
SUNO_POLL_TIMEOUT = int(os.environ.get("SUNO_POLL_TIMEOUT", "600"))

# ─── Header Randomization Pools ─────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
]

CHROME_VERSIONS = [
    '"Google Chrome";v="109", "Chromium";v="109"',
    '"Google Chrome";v="110", "Chromium";v="110"',
    '"Google Chrome";v="111", "Chromium";v="111"',
    '"Google Chrome";v="113", "Not-A.Brand";v="24"',
    '"Google Chrome";v="120", "Not-A.Brand";v="24"',
    '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
]

BROWSER_VALIDATIONS = [
    "SgDQo8mvrGRdD61Pwo8wyWVgYgs=",
]

CLIENT_DATA = [
    "CKi1yQEIh7bJAQiktskBCKmdygEIvorLAQiUocsBCIagzQEYv6nKARjRp88BGKqwzwE=",
]
