<p align="center">
  <img src="docs/images/flowkit_banner.svg" width="720" alt="FLOW KIT" />
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"/></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/Chrome-MV3-4285F4?logo=googlechrome&logoColor=white" alt="Chrome MV3"/>
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/ffmpeg-required-007808?logo=ffmpeg&logoColor=white" alt="ffmpeg"/>
  <img src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose"/>
  <a href="CLAUDE.md"><img src="https://img.shields.io/badge/Docs-CLAUDE.md-8A2BE2" alt="Documentation"/></a>
  <a href="https://github.com/s0pheap/flowkit/stargazers"><img src="https://img.shields.io/github/stars/s0pheap/flowkit?style=flat&logo=github" alt="GitHub stars"/></a>
  <a href="https://github.com/s0pheap/flowkit/issues"><img src="https://img.shields.io/github/issues/s0pheap/flowkit?logo=github" alt="GitHub issues"/></a>
  <a href="https://deepwiki.com/tuannguyenhoangit-droid/google-flow-agent"><img src="https://img.shields.io/badge/DeepWiki-AI%20Docs-6A3BC9" alt="DeepWiki"/></a>
</p>

Flow Kit turns a story into a finished, narrated video with Google Flow (Veo and
Nano Banana). You drive it from an AI coding tool with `/fk-*` skills; it keeps the
project in SQLite, queues every generation, and renders the final cut with ffmpeg.

Run it on your own computer, or put it on a server and give other people a URL and
an API key.

## Contents

- [What you get](#what-you-get)
- [How it works](#how-it-works)
- [Run it locally](#run-it-locally)
- [Deploy it on a server](#deploy-it-on-a-server)
- [Configuration](#configuration)
- [Making a video](#making-a-video)
- [Skills](#skills)
- [Dashboard](#dashboard)
- [Narration, subtitles and the final render](#narration-subtitles-and-the-final-render)
- [API](#api)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## What you get

**story → entities → reference images → scene images → 8 s video clips → narration → subtitles → final render → thumbnails → YouTube**

| Output | Description |
|--------|-------------|
| Reference images | One per character, location or prop, so they look the same in every scene |
| Scene images | The first frame of each scene, composed from its references |
| Video clips | Omni Flash (10 s, the default) or Veo (8 s) clips with camera motion and sound effects, or a free ffmpeg pan/zoom |
| Narration | TTS per scene (Gemini by default, with free local fallbacks) and word timings |
| Subtitles | SRT from the word timings, burned in or served beside the video |
| Final video | Rendered on the server: clips fitted to the narration, transitions, text overlays, ducked music |
| Thumbnails and YouTube metadata | Thumbnails with text and branding; SEO title, description and tags |

## How it works

```
 AI tool (/fk-* skills) ──┐
 Dashboard (browser) ─────┤ REST + WS :8100
                          ▼
 ┌─────────────────────────────┐   ws://127.0.0.1:9222   ┌───────────────────────┐        ┌──────────────────┐
 │  Agent  (FastAPI + SQLite)  │◄───────────────────────►│  Chrome extension     │───────►│ flow.google.com  │
 │  REST API, queue worker,    │  envelopes / responses  │  mints reCAPTCHA,     │        │ signed-in tab    │
 │  TTS, ffmpeg render         │                         │  runs the RPC in-page │        │ cookie + `at`    │
 └─────────────────────────────┘                         └───────────────────────┘        └──────────────────┘
```

Flow signs every call with the session cookie and a per-page `at` token, and each
generation needs a single-use reCAPTCHA. None of that can be replayed from outside
the browser, so the agent builds the request and a **signed-in Flow tab** sends it.
There is no headless mode: one Flow tab has to stay open.

1. A skill or the dashboard calls the REST API, which queues a request in SQLite.
2. The worker picks it up (at most `MAX_CONCURRENT_REQUESTS` at a time, `API_COOLDOWN`
   apart), checks its prerequisites and builds the prompt.
3. The extension runs the batchexecute call inside the Flow tab and posts the result back.
4. The result is written to the scene or entity, and the change is pushed to the dashboard.

> **Flow moved in September 2026.** It lives at `flow.google.com` now, and the old
> `aisandbox-pa.googleapis.com` REST API no longer works. Flow Kit can't create
> Flow projects any more: make one in the Flow UI and pin its uuid as
> `FLOW_PROJECT_ID`. Upgrading? Reload the extension (v0.3.0+).

## Run it locally

You need Python 3.10+, ffmpeg and Chrome.

```bash
./setup.sh                          # checks tools, creates venv, installs dependencies
# or: pip install -r requirements.txt

cp .env.example .env                # set FLOW_PROJECT_ID (and GEMINI_API_KEY for narration)
python setup.py                     # install the /fk-* skills for Claude Code, Codex or Antigravity
```

1. In Chrome, open `chrome://extensions`, turn on **Developer mode**, click
   **Load unpacked** and pick `extension/`.
2. Sign in at `https://flow.google.com/` and leave the tab open.
3. Create a project in Flow and copy the uuid from its URL
   (`flow.google.com/project/<uuid>`) into `FLOW_PROJECT_ID`.
4. Start the agent:

   ```bash
   python -m agent.main              # API :8100, extension socket :9222, worker
   ```

5. Check it:

   ```bash
   curl -s http://127.0.0.1:8100/health
   # {"status":"ok","extension_connected":true, ...}
   curl -s http://127.0.0.1:8100/api/flow/status
   # {"connected":true,"transport":"batch","flow_project_id":"…","flow_key_present":false}
   ```

`flow_key_present: false` is normal: the current transport has no bearer token.

> **Windows:** the scripts assume a Unix shell. Use Git Bash or WSL.

## Deploy it on a server

On a server, one Google account signed in to Flow does the generating for every
user. Keys are on, each user only sees the Flow projects granted to them, and they
install the skills on their own computer with one command from the server.

### Docker (Linux)

`docker-compose.yml` runs three containers:

| Service | What it is |
|---------|------------|
| `browser` | Chromium with a web desktop. You sign in to Flow and load the extension here |
| `agent` | Built from the `Dockerfile`: API, dashboard, worker, ffmpeg, fonts. Shares the browser's network so the extension reaches it on `127.0.0.1` |
| `caddy` | HTTPS for your domain on ports 80 and 443, the only public ports |

```bash
git clone https://github.com/s0pheap/flowkit.git && cd flowkit
cp .env.example .env
# set DOMAIN, ADMIN_API_KEY, BROWSER_PASSWORD, FLOW_PROJECT_ID
docker compose up -d --build
```

Then sign in to Flow once. The browser desktop is only reachable from the server
itself, so tunnel to it:

```bash
ssh -L 3001:127.0.0.1:3001 you@your-server
# open https://localhost:3001, log in as flowkit / BROWSER_PASSWORD
```

In that Chromium: sign in to `flow.google.com`, load `/extension` as an unpacked
extension, pin the Flow tab and turn off Memory Saver. The profile is kept in a
volume, so this survives restarts.

Add a user and give them their key:

```bash
docker compose exec agent python -m agent.users create alice --project <flow-project-uuid>
```

They open `https://<your domain>/guide`, sign in with the key and run the install
command it shows.

### Windows or Ubuntu desktop VM

If you'd rather run Chrome on a normal desktop, follow the step-by-step VM guide.

**Full guide, including what users can and can't do and day-to-day upkeep:
[`docs/DEPLOY.md`](docs/DEPLOY.md).**

> **Before you open it up:** every user's generations count against the one Flow
> account, and cloud IPs get more CAPTCHAs and "unusual activity" blocks. Start with
> a few users.

## Configuration

Everything is set in `.env`; [`.env.example`](.env.example) documents every variable.
The ones you're most likely to touch:

| Variable | Default | What it does |
|----------|---------|--------------|
| `FLOW_PROJECT_ID` | — | Flow project every RPC is scoped to. **Required** |
| `FLOW_ALLOW_DEGRADED` | `0` | `1` lets chaining and r2v fall back to plain i2v instead of failing |
| `AUTH_ENABLED` | `0` | `1` requires `X-API-Key` on every `/api` and `/ws` call. Turn on before anyone else can reach `:8100` |
| `ADMIN_API_KEY` | — | Bootstrap admin key |
| `PUBLIC_URL` | — | Address users reach the server at, written into the installers |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8100` | REST API bind |
| `WS_HOST` / `WS_PORT` | `127.0.0.1` / `9222` | Extension socket. No key check: keep it on loopback |
| `MAX_CONCURRENT_REQUESTS` | `5` | Generations running at once, across all users |
| `API_COOLDOWN` | `10` | Seconds between Flow calls |
| `TTS_ENGINE` | `gemini` | `gemini`, `mindlogic`, `kokoro`, `piper`, `google` or `omnivoice` |
| `TTS_FALLBACK_ENGINE` | `piper` | Engines to try when the main one can't speak a line |
| `GEMINI_API_KEY` | — | Gemini TTS and word timings |
| `SUNO_API_KEY` | — | Background music |
| `OVERLAY_FONT` / `SUBTITLE_FONT` | OS default | Fonts for burned-in text; needs a CJK font for Korean, Japanese, Chinese |
| `DOMAIN` / `BROWSER_PASSWORD` | — | Docker only: Caddy's domain and the browser desktop login |

Model keys live in `agent/models.json` and the video-review CLI in
`agent/providers.json`. Change them with `/fk-change-model` and
`/fk-change-provider`; both reload without a restart.

### Veo or Omni Flash

Scene videos come from **Omni Flash** by default (`default_video_model_family` in
`agent/models.json`), as 10-second clips (`omni_flash_duration_s`: 4, 6, 8 or 10).
Each project can override it:

```bash
curl -X PATCH http://127.0.0.1:8100/api/projects/<PID> -H "Content-Type: application/json" \
  -d '{"video_model_family": "veo"}'          # null = back to the server default
```

`GET /api/projects/<PID>` reports what the project really uses as
`effective_video_model_family` and `video_clip_seconds`. Narration limits follow the
clip: 6.5 s of speech on an 8 s Veo clip, 8.5 s on a 10 s Omni clip. Omni covers
first-frame video only; only the 10-second model has been proven by a real
generation so far.

### Not ported to the new Flow API yet

These payloads were never captured, so they fail with `UNSUPPORTED_ON_BATCH_API`
instead of silently doing the wrong thing:

| Capability | Workaround |
|------------|------------|
| 4K / 1080p upscale | None. Keep the normal render |
| Reference-to-video (r2v) | `FLOW_ALLOW_DEGRADED=1` → i2v off the first reference |
| Start + end-frame chaining (`/fk-gen-chain-videos`) | `FLOW_ALLOW_DEGRADED=1` → i2v off the start frame |
| Omni Flash references or first + last frames | Use Omni first-frame video (the default), or Veo |

Restoring one starts with a capture, not a guess: [`docs/CAPTURE.md`](docs/CAPTURE.md).

## Making a video

### The mental model

Flow Kit keeps things consistent with **reference images**.

1. **List every visual element that repeats** across scenes, as an entity:
   - characters → `entity_type: "character"` (portrait reference)
   - places → `"location"` (landscape reference)
   - creatures → `"creature"`, important objects → `"visual_asset"`
2. **Describe only appearance** in the entity's `description`. That becomes its reference image.
3. **Write scene prompts as action**, naming the entities:
   `"Pippip arranges fish at Fish Stall"`, not `"A chubby orange cat in a blue apron…"`.
4. **List the entities in the scene** in `character_names`. Their references are passed
   to the model with the prompt.

Each scene has two prompts: `prompt` for the still first frame, and `video_prompt`
for the 8 s of motion, with timing and camera directions:

```
0-3s: Wide crane down, Luna steps out of the rocket onto Candy Planet Surface. Luna gasps "It's beautiful!"
3-6s: Low-angle tracking shot, Luna walks across the candy ground, shallow DOF.
6-8s: Close-up of Luna's face, eyes wide, golden-hour backlight. Ambient wind.
```

The worker adds to every video prompt: the project's **material** style
(`realistic`, `3d_pixar`, `anime`, … from `GET /api/materials`), each character's
`voice_description` (about 30 words), and *"No background music. Keep only natural
sound effects and ambient sounds."*

`media_id` is always a UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`), never a
`CAMS...` string.

### With skills (recommended)

```
/fk-create-project                 asks for the story, creates entities, video and scenes
/fk-gen-refs <project_id>          reference image per entity
/fk-gen-images <pid> <vid>         scene images with the references applied
/fk-gen-videos <pid> <vid>         video clips (2–5 min each, polled for you)
/fk-gen-narrator <vid>             narration, word timings, subtitles
/fk-review-board <vid>             watch every scene, leave notes, set look & feel
/fk-concat-fit-narrator <vid>      render the final cut on the server and download it
/fk-status <pid>                   what's done and what to do next
```

Each skill checks its prerequisites first; `/fk-pipeline` runs the whole chain.

### With the API

<details>
<summary>Example: "Pippip the Fish Merchant" with curl</summary>

With keys on, add `-H "X-API-Key: <key>"` to every call.

```bash
# 1. Project with its entities
curl -X POST http://127.0.0.1:8100/api/projects -H "Content-Type: application/json" -d '{
  "name": "Pippip the Fish Merchant",
  "material": "3d_pixar",
  "story": "Pippip is a chubby orange tabby cat who sells fish at a Southeast Asian open market.",
  "characters": [
    {"name": "Pippip", "entity_type": "character", "description": "Chubby orange tabby cat, big green eyes, blue apron, straw hat. Walks upright."},
    {"name": "Fish Stall", "entity_type": "location", "description": "Rustic wooden market stall, thatched bamboo roof, crushed-ice display, brass scale."},
    {"name": "Open Market", "entity_type": "location", "description": "Southeast Asian open-air market, colorful awnings, hanging lanterns, stone walkway."},
    {"name": "Golden Fish", "entity_type": "visual_asset", "description": "Golden koi, shimmering iridescent scales, slight magical glow."}
  ]
}'

# 2. Video and scenes
curl -X POST http://127.0.0.1:8100/api/videos -H "Content-Type: application/json" \
  -d '{"project_id": "<PID>", "title": "Pippip Episode 1"}'

curl -X POST http://127.0.0.1:8100/api/scenes -H "Content-Type: application/json" -d '{
  "video_id": "<VID>", "display_order": 0, "chain_type": "ROOT",
  "prompt": "Pippip stands behind Fish Stall arranging fresh fish on ice. Sunrise over Open Market.",
  "character_names": ["Pippip", "Fish Stall", "Open Market"]
}'

# 3. Queue the work: all at once, the worker throttles
curl -X POST http://127.0.0.1:8100/api/requests/batch -H "Content-Type: application/json" -d '{"requests": [
  {"type": "GENERATE_CHARACTER_IMAGE", "character_id": "<CID>", "project_id": "<PID>"}
]}'
# then GENERATE_IMAGE, then GENERATE_VIDEO per scene, with orientation VERTICAL or HORIZONTAL

# 4. Watch progress
curl -s "http://127.0.0.1:8100/api/requests/batch-status?video_id=<VID>"

# 5. Render and download
curl -X POST http://127.0.0.1:8100/api/videos/<VID>/render -H "Content-Type: application/json" -d '{"subs": "burn"}'
curl -s http://127.0.0.1:8100/api/videos/<VID>/render      # poll until done
curl -o final.mp4 http://127.0.0.1:8100/api/videos/<VID>/final.mp4
```

Don't write loops that post requests one by one: use `POST /api/requests/batch`.

</details>

## Skills

Skills are Markdown recipes in [`skills/`](skills/). `python setup.py` installs them
as `/fk-*` commands for Claude Code, Codex or Antigravity. A server installs the
remote-ready ones (marked ☁️) on a user's machine via `/install.sh` or `/install.ps1`.

| Stage | Skills |
|-------|--------|
| Project | ☁️ `fk-research`, ☁️ `fk-create-project`, ☁️ `fk-switch-project`, ☁️ `fk-status` |
| Images and video | ☁️ `fk-gen-refs`, ☁️ `fk-gen-images`, ☁️ `fk-gen-videos`, ☁️ `fk-camera-guide`, ☁️ `fk-video-quality`, `fk-gen-chain-videos`, `fk-insert-scene`, `fk-creative-mix`, `fk-pipeline`, `fk-monitor` |
| Narration, music, final video | ☁️ `fk-gen-narrator`, ☁️ `fk-gen-text-overlays`, ☁️ `fk-gen-music`, ☁️ `fk-review-board`, ☁️ `fk-concat-fit-narrator`, `fk-concat`, `fk-gen-tts-template`, `fk-import-voice` |
| Review | `fk-review-video`, `fk-change-provider` |
| YouTube | `fk-youtube-seo`, `fk-thumbnail`, `fk-thumbnail-guide`, `fk-brand-logo`, `fk-youtube-upload` |
| Fixing and settings | ☁️ `fk-refresh-urls`, ☁️ `fk-doctor`, `fk-fix-uuids`, `fk-upload-image`, `fk-add-material`, `fk-change-model`, `fk-dashboard` |

`skills/fk-*.md` is the only source. Edit it there and run `python setup.py sync`;
`.claude/commands/`, `.agents/skills/`, `AGENTS.md` and `GEMINI.md` are generated.

**Video review** (`/fk-review-video`) builds ffmpeg contact sheets and asks a vision
model to score each scene. The model is either the caller's own AI tool
(`POST /api/videos/<vid>/review/prepare`, then post the JSON to the returned
`result_url`) or a CLI on the server (`claude`, `agy` or `codex`, picked with
`/fk-change-provider` or `?provider=` per request). The Docker image has no such
CLI, so there it's always the caller's own tool.

**YouTube** upload and branding use per-channel OAuth credentials in the
gitignored `youtube/` directory and only run on the machine that has them.

## Dashboard

<p align="center">
  <img src="docs/images/dashboard_overview.png" width="800" alt="Flow Kit dashboard" />
</p>

The agent serves the built dashboard at `/` (run `npm run build` in `dashboard/`, or
use Docker, which builds it for you):

- **Dashboard**: extension status, queue and worker slots, live over `/ws/dashboard`
- **Projects**: entities, scenes and videos; render, watch and download the final cut
- **Gallery** and **Logs**
- **Guide**: sign-in with a key, and install commands for users of a shared server

The Scene Review Board lives at `/review-board?video_id=…` (`/fk-review-board`).
The Chrome extension also has a side panel with the request log.

## Narration, subtitles and the final render

```
/fk-gen-narrator         narrator_text → wav per scene + *.words.json word timings + SRT
/fk-gen-text-overlays    dates, places, numbers pulled from the narration
/fk-review-board         per-scene look & feel: Veo or ffmpeg pan/zoom, transition, length
/fk-gen-videos           Veo scenes generate; ffmpeg scenes render from the keyframe (no Flow cost)
/fk-gen-music            background track via Suno (or upload your own)
/fk-concat-fit-narrator  server render: clips fitted to narration, transitions, overlays, music
```

- **TTS.** Gemini by default (`GEMINI_API_KEY`). When it can't speak a line (out of
  quota, unsupported language, server down) the next engine in `TTS_FALLBACK_ENGINE`
  does, and the sidecar records which engine spoke, so those scenes can be redone
  later. Piper is free and runs locally; `google` (gTTS) also speaks Khmer; Kokoro
  is your own Kokoro-82M server; `mindlogic` is Gemini TTS through the Mindlogic
  gateway; `omnivoice` clones a voice template (see `skills/fk-gen-tts-template.md`).
- **Word timings** come from a second Gemini audio call, or from local Whisper
  (`TIMING_ENGINE=whisper`, `pip install faster-whisper`), and are estimated if both fail.
- **One timeline.** `GET /api/videos/{vid}/assembly-plan` turns look & feel and
  narration lengths into start offsets and `xfade` filters. Subtitles and the render
  both read it. A scene lasts as long as its narration plus 0.5 s, unless its look &
  feel sets a length. Veo scenes can't run past their usable 7 s.
- **Render.** `POST /api/videos/{vid}/render` runs in the background, one job at a
  time; then `GET …/final.mp4` and `…/captions.srt`. An optional music track is looped
  under the cut and ducked while the narrator speaks.

## API

Interactive docs: `http://127.0.0.1:8100/docs`.

| Resource | Endpoints |
|----------|-----------|
| Projects | `POST/GET /api/projects`, `GET/PATCH/DELETE /api/projects/{id}`, `/api/projects/{id}/characters` |
| Entities | `POST/GET /api/characters`, `GET/PATCH/DELETE /api/characters/{id}` |
| Videos | `POST/GET /api/videos?project_id=`, `GET/PATCH/DELETE /api/videos/{id}` |
| Scenes | `POST/GET /api/scenes?video_id=`, `GET/PATCH/DELETE /api/scenes/{id}` |
| Requests | `POST /api/requests`, `POST /api/requests/batch`, `GET /api/requests/batch-status`, `GET /api/requests/{id}` |
| Narration | `POST /api/tts/generate`, `POST /api/videos/{vid}/narrate`, `/api/tts/templates` |
| Timeline | `GET /api/videos/{vid}/assembly-plan`, `POST /api/scenes/{sid}/motion`, `POST /api/videos/{vid}/subtitles` |
| Render | `POST/GET /api/videos/{vid}/render`, `GET …/final.mp4`, `GET …/captions.srt`, `PUT …/music/{name}` |
| Review | `POST /api/videos/{vid}/review`, `POST …/review/prepare` |
| Music | `POST /api/music/generate`, `GET /api/music/tasks/{id}` |
| Status | `GET /health`, `GET /api/flow/status`, `POST /api/flow/refresh-urls/{project_id}` |
| Settings (admin) | `GET/PATCH /api/models`, `GET/PATCH /api/providers`, `/api/materials`, `/api/admin/users` |

### Request types

| Type | Required fields | Status |
|------|-----------------|--------|
| `GENERATE_CHARACTER_IMAGE` | `character_id`, `project_id` | Works |
| `GENERATE_IMAGE` | `scene_id`, `project_id`, `video_id`, `orientation` | Works |
| `GENERATE_VIDEO` | `scene_id`, `project_id`, `video_id`, `orientation` | Works (async on Flow's side); Veo or Omni per project |
| `GENERATE_VIDEO_REFS` | same | Unported (r2v) |
| `UPSCALE_VIDEO` | same | Unported |

### What the worker does for you

- Throttles to `MAX_CONCURRENT_REQUESTS` with `API_COOLDOWN` between calls.
- Refuses a duplicate active request for the same scene and type.
- Holds a scene image until every referenced entity has a `media_id`, and skips
  work that's already done.
- Retries with backoff, re-uploads media Flow reports as missing, and recovers
  requests stuck in `PROCESSING`.
- Cascades: a new image clears the scene's video and upscale; a new video clears the upscale.
- Low-priority video models return the MP4 inline; it's saved under
  `output/_workflow_videos/`, so a scene's video URL can be a `file://` path.

## Troubleshooting

Run **`/fk-doctor`** first. It diagnoses the live agent and prescribes a fix.

| Problem | Fix |
|---------|-----|
| `extension_connected: false` | Flow tab open and signed in? Extension loaded? In Docker, also `docker compose restart agent` |
| `NO_FLOW_PROJECT` | Set `FLOW_PROJECT_ID` |
| `UNSUPPORTED_ON_BATCH_API` | Not ported yet, see [above](#not-ported-to-the-new-flow-api-yet) |
| `NO_AT_TOKEN` / `NO_FLOW_TAB` | Open `flow.google.com`, sign in, let it load |
| 403 `PUBLIC_ERROR_UNUSUAL_ACTIVITY` | Stop submitting, clear Google cookies, sign in again, resubmit slower |
| Broken thumbnails, render fails on old projects | `/fk-refresh-urls <video_id>` |
| `media_id` starts with `CAMS...` | `/fk-fix-uuids` |
| A poll says "Media not found." | Normal: finished jobs report it |

The full error reference (Flow reasons, HTTP codes, retry policy, YouTube errors):
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Development

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest                                    # unit tests
node tests/extension_mv3_bootstrap.test.cjs         # extension cold start

cd dashboard && npm install && npm run dev          # Vite :5173, proxies to :8100
cd dashboard && npm run lint && npm run build
```

After changing `extension/`, reload it in `chrome://extensions`.

```
agent/
├── main.py            FastAPI app, extension socket, dashboard WS, serves the dashboard
├── config.py          settings from .env; models.json and providers.json
├── auth.py, users.py  API keys, per-project access, user CLI
├── api/               REST routes
├── db/                SQLite schema (inline migrations) and CRUD
├── models/            Pydantic models
├── sdk/               operations (prompt building) and result handling
├── services/          flow_client + flow_batch (Flow RPCs), tts, assembly, render,
│                      subtitles, motion, video_reviewer, suno
└── worker/            queue processor
dashboard/             React dashboard (Vite)
extension/             Chrome MV3 extension
skills/                /fk-* skill sources
tools/                 review board page
docs/                  DEPLOY, TROUBLESHOOTING, CAPTURE, OMNI_FLASH
Dockerfile, docker-compose.yml, deploy/Caddyfile
```

More detail on internals is in [`CLAUDE.md`](CLAUDE.md). `ARCHITECTURE.md` still
describes the pre-migration extension; trust `flow_client.py` and `flow_batch.py` over it.

## License

MIT

---

## Community & Support

<p align="center">
  <a href="https://www.facebook.com/groups/vibecodeera">
    <img src="https://img.shields.io/badge/Join%20the%20Community-Vibe%20Code%20Era%20on%20Facebook-1877F2?style=for-the-badge&logo=facebook&logoColor=white" alt="Join the Vibe Code Era Facebook Group" />
  </a>
</p>

**Share anything crazy and useful created with Vibe Code.** Drop in to:

- Post the story-video runs and thumbnails you've generated
- Share scene templates, prompt recipes, and reference-image setups
- Ask for help when an output isn't matching what you imagined
- Request features and report bugs you've hit in the wild
- Trade tips on Google Flow plan limits, Veo i2v behaviour, and Chrome extension setup

→ **[facebook.com/groups/vibecodeera](https://www.facebook.com/groups/vibecodeera)**
