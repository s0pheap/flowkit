# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Flow Kit

Flow Kit generates AI videos through Google Flow. It has three parts: a Python agent (FastAPI + SQLite), a Chrome MV3 extension that runs the actual Flow calls inside a signed-in tab, and `/fk-*` skills that drive the agent's REST API.

Base URL: `http://127.0.0.1:8100`

## Pre-flight

```bash
curl -s http://127.0.0.1:8100/health
# Must return: {"extension_connected": true}

curl -s http://127.0.0.1:8100/api/flow/status
# Must return: {"transport": "batch", "flow_project_id": "<uuid>", ...}
```

Also needed: **one signed-in `https://flow.google.com/` tab left open**. Only the
page can sign a Flow request, so nothing works headless.

## How to work

- Always use `/fk-*` skills — all rules and workflows live inside each skill
- Never write scripts to loop API calls — use `POST /api/requests/batch`
- `media_id` is always UUID format (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`), never `CAMS...` strings
- **On any pipeline error** (request `FAILED`, stuck `PROCESSING`, `extension_connected: false`, HTTP 4xx/5xx from `:8100`, YouTube `HttpError`, error strings like `UNSAFE_GENERATION` / `not found` / `CAPTCHA` / `NO_AT_TOKEN` / `NO_FLOW_PROJECT` / `UNSUPPORTED_ON_BATCH_API`): invoke `/fk-doctor` before guessing a fix
- `flow_key_present: false` is **normal** — the current transport has no bearer token

## Since Flow moved (September 2026)

Flow lives at `flow.google.com` and signs every call in the page. Consequences
that change how you work:

- **Projects are not created by Flow Kit any more.** Make one in the Flow UI and
  pin its uuid as `FLOW_PROJECT_ID`, or pass `flow_project_id` to `POST /api/projects`.
- **Four capabilities are unported** because their payloads were never captured:
  4K upscale, r2v, start+end-frame chaining, and Omni Flash. They fail with
  `UNSUPPORTED_ON_BATCH_API` rather than silently producing the wrong thing.
  `FLOW_ALLOW_DEGRADED=1` drops chaining and r2v to plain i2v; upscale has no
  fallback. To restore one properly, see `docs/CAPTURE.md`.
- **A poll saying "Media not found." is not a failure.** Finished jobs report it.

## Development commands

```bash
pip install -r requirements.txt pytest pytest-asyncio   # pytest isn't in requirements.txt
cp .env.example .env                                     # config.py loads BASE_DIR/.env
python -m agent.main                                     # API :8100 + extension WS :9222 + worker

python -m pytest                                         # asyncio_mode=auto (pytest.ini)
python -m pytest tests/unit/test_flow_batch.py::test_name
node tests/extension_mv3_bootstrap.test.cjs              # extension cold-start test (runs background.js in a vm)

cd dashboard && npm install && npm run dev               # Vite :5173, proxies /api /ws /health to :8100
cd dashboard && npm run lint && npm run build            # tsc -b + vite build
```

After a change to `extension/`, reload the unpacked extension in `chrome://extensions`. The agent does not restart it for you.

**Skills are generated.** `skills/fk-*.md` is the only source. `.claude/commands/fk-*.md`, `.agents/skills/`, `AGENTS.md` and `GEMINI.md` are all written by `setup.py`. Edit the file under `skills/`, then run `python setup.py sync`. The critical rules inlined into AGENTS.md and GEMINI.md live in `_CRITICAL_RULES` inside `setup.py`.

## Architecture

### How a generation request moves through the system

1. `POST /api/requests` or `/api/requests/batch` (`agent/api/requests.py`) inserts a `PENDING` row into the `request` table. It rejects a duplicate active request for the same scene + type.
2. `WorkerController` (`agent/worker/processor.py`) polls the table and throttles with `APIRateLimiter` (`MAX_CONCURRENT_REQUESTS`, `API_COOLDOWN`). Before dispatching it checks prerequisites: every ref has a `media_id`, and the job isn't already completed. It also handles retries with backoff, recovery of stale `PROCESSING` rows, and re-uploading media Flow reports as missing.
3. `_dispatch` routes on request type to `OperationService` (`agent/sdk/services/operations.py`), which builds prompts (material prefix, voice descriptions, no-music suffix) and calls `FlowClient`.
4. `FlowClient` (`agent/services/flow_client.py`) is a singleton that holds the extension WebSocket(s). With `USE_BATCH_RPC=1` (the default), each high-level method builds a payload with `agent/services/flow_batch.py` and sends it through `batch_rpc` → `_send`. Methods prefixed `_legacy_*` are the dead pre-migration REST path.
5. `extension/background.js` receives `{id, method: "batch_rpc", params}` and runs the batchexecute POST in the Flow tab's MAIN world, where the `at` token lives. It swaps the `__CAPTCHA__` placeholder for a freshly minted single-use reCAPTCHA token. The result usually comes back via `POST /api/ext/callback`, authenticated with the secret sent on WS connect, which resolves the pending future by id.
6. `agent/sdk/services/result_handler.py` (`parse_result`, `apply_scene_result`, `apply_character_result`) writes media ids and URLs to the DB and applies cascades: a new image clears video + upscale, and a new video clears upscale. The worker and the direct SDK `execute_*` methods share this code.
7. `agent/services/event_bus.py` pushes changes to `/ws/dashboard`, which the React dashboard and the extension side panel consume.

Video is asynchronous on Flow's side. Generate (`eb1hJf`) returns an operation id. Poll it with `jwpduf`, map the operation to a media id through the project listing (`Zzl0ze`, which is huge, so the extension trims it with `match`), then fetch signed URLs with `as29s`. The table of known RPC ids is in `docs/CAPTURE.md`.

### Things that aren't obvious from a single file

- **Batchexecute payloads are positional and captured, never guessed.** A value in the wrong slot can be accepted and then silently ignored. New RPC shapes go through the `docs/CAPTURE.md` recording procedure, and unported features raise `UNSUPPORTED_ON_BATCH_API` via `_unsupported()` in `flow_client.py`.
- **`flow_batch.py` does no network I/O.** It only builds envelopes and parses responses, so it can be unit-tested directly (`tests/unit/test_flow_batch.py`, `test_flow_client_batch.py`).
- **Model keys live in `agent/models.json`**, and the active review provider lives in `agent/providers.json`. `PATCH /api/models` and `PATCH /api/providers` hot-reload them into `agent.config`, so read them through the module (`_config.X`) rather than binding them at import time.
- **Schema migrations are inline** in `agent/db/schema.py:init_db()`: `CREATE TABLE IF NOT EXISTS` followed by guarded `ALTER TABLE`s. There is no migration tool. The DB is `flow_agent.db` at the repo root, or under `FLOW_AGENT_DIR`.
- **Scenes store everything twice**, once per orientation: `vertical_*` and `horizontal_*` image/video/upscale url, media_id and status columns. Chaining uses `parent_scene_id` + `chain_type` (`ROOT`/`CONTINUATION`/`INSERT`).
- Entities (the `character` table) are standalone and linked to projects M:N through `project_character`. The `entity_type` value decides portrait vs landscape reference images.
- Generated files land under `output/` (gitignored). Low-priority video models return the MP4 inline, and it is saved to `output/_workflow_videos/`, so a scene's video URL can be a `file://` path.
- Video review (`agent/services/video_reviewer.py`) builds ffmpeg contact sheets and shells out to the `claude`, `agy` or `codex` CLI. Music uses the Suno API.
- **Narration → subtitles → assembly share one timeline.** TTS (`agent/services/tts.py`) defaults to Gemini (`TTS_ENGINE=gemini`, needs `GEMINI_API_KEY`); every wav gets a `*.words.json` sidecar of word timings from a second Gemini audio call (`gemini_tts.py`), estimated when that fails. A scene's `look_feel` JSON column (`agent/models/look_feel.py`) picks Veo (`generate`, motion becomes a camera direction in `_build_video_prompt`) or a local ffmpeg pan/zoom (`ffmpeg`, `services/motion.py`; the requests API rejects Veo jobs for these scenes). `services/assembly.py` turns look & feel + narration lengths into start offsets and `xfade` filters, exposed at `GET /api/videos/{vid}/assembly-plan`; `POST /api/videos/{vid}/subtitles` and `/fk-concat-fit-narrator` both read that plan, so change timing rules there, not in the skill.
- `tools/review_board.html` is served by the agent at `/review-board` (behind `/fk-review-board`). It sends the dashboard's stored key, plays clips through `/api/scenes/{sid}/clip.mp4` and `motion.mp4` with a media token, and keeps feedback per video at `/api/videos/{vid}/review-feedback`. YouTube upload code and per-channel credentials live in the gitignored `youtube/` directory.
- **The final cut renders on the server** (`agent/services/render.py`, routes in `agent/api/render.py`): `POST /api/videos/{vid}/render` runs the assembly plan through ffmpeg as a background job (one at a time), then `GET .../final.mp4` and `.../captions.srt` serve it. `/fk-concat-fit-narrator` and the dashboard's Videos tab only drive this. Media URLs that a `<video>` or download link opens take `?token=` from `GET /api/auth/media-token`; only the paths in `auth.MEDIA_PATHS` accept it.
- **API keys are off unless `AUTH_ENABLED=1`** (`agent/auth.py`). When on, `AuthMiddleware` turns `X-API-Key` into a principal, and routers call `auth.require_project/video/scene/character/media` before touching a row. Access follows the Flow project: `user_project` grants Flow uuids, which are also local project ids. Every new route that takes an id needs one of those guards. Server-wide settings (`PATCH /api/models`, `/api/providers`, materials, voice templates, direct `/api/flow/*` calls) use `auth.require_admin()`. Users are managed with `python -m agent.users` or `/api/admin/users`.
- **Shared deployment** (`docs/DEPLOY.md`): the agent serves the built dashboard at `/` and a public installer at `/install.sh`, `/install.ps1` and `/install/skills/<name>/SKILL.md`. Only the skills in `REMOTE_SKILLS` (`agent/api/install.py`) are offered, and they must call `"$FK/api/..." -H "$KEY"` (from `~/.flowkit/env`) and never read the server's disk; `tests/unit/test_install.py` checks the localhost part. With keys on, `/api/ext/callback` also needs the `X-Callback-Secret` the extension gets on connect.
- `ARCHITECTURE.md` still describes the pre-migration bearer-token extension. Trust `flow_client.py` and `flow_batch.py` over it.
