# fk-gen-music — Generate Music via Suno

Generate background music (or songs) for a video with the Suno API (sunoapi.org) and save it to the project, where `/fk-concat-fit-narrator` lays it under the final video.

Usage: `/fk-gen-music <video_id> [description] [--template <id>] [--vocals]`

Suno runs with the **server's** `SUNO_API_KEY`, so every generation uses the server owner's Suno credits.

## Connection

These commands work against a local agent or a shared server. The Flow Kit
installer (`<server>/install.sh` or `install.ps1`) writes `~/.flowkit/env` with
`FLOWKIT_URL` and `FLOWKIT_API_KEY`; without that file they default to
`http://127.0.0.1:8100` and no key. Shell state does not carry
over between commands, so **start every command with this line**:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
```

Then call the API as `curl -s "$FK/api/..." -H "$KEY"`. A `401` means the key is
missing or wrong; a `404` on an id you were given means it belongs to another user.
In PowerShell use `$env:FLOWKIT_URL` and `-Headers @{"X-API-Key"=$env:FLOWKIT_API_KEY}`.

## Step 1: Find the project

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"
curl -s "$FK/api/videos/<VID>/music" -H "$KEY"
```

Note `project_id` (`<PID>`) from the video. If the project already has tracks, show them and ask whether a new one is still wanted.

For the mood, read the project's `story` (`GET $FK/api/projects/<PID>`) and the video's total length (`total_duration` from `GET $FK/api/videos/<VID>/assembly-plan`). A track shorter than the video loops, so aim for at least the video's length where the model allows (see **Models**).

## Step 2: Describe the music

Background music under narration should be **instrumental** (vocals fight the narrator) and calm enough to sit under speech. Unless `--vocals` was given, always send `"instrumental": true`.

Propose a one-line description from the story and ask the user to confirm or change it, e.g.:

- "tense, slow-building orchestral underscore for a naval documentary, low strings and soft percussion, no vocals"
- "warm, gentle piano and strings for a heartfelt family story"
- "light, curious electronic pulse for a science explainer"

Or use a template's style. List them:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/music/templates" -H "$KEY"
```

For background music `cinematic_epic` and `cinematic_emotional` work well; for children's content `lullaby_gentle` or `children_adventure`.

## Step 3: Generate

**Description mode** (recommended for background music — Suno writes the music from the description):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 700 -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "<description>",
    "instrumental": true,
    "custom_mode": false,
    "poll": true
  }'
```

**Template style**:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 700 -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"template_id": "cinematic_emotional", "title": "<short title>", "instrumental": true, "poll": true}'
```

**Custom mode** (a song with lyrics, only with `--vocals`): send `"prompt"` as lyrics with `[Verse]`/`[Chorus]` markers, plus `"style"` and `"title"`, and `"instrumental": false`.

Each generation makes **2 variations** and takes about 30-120 s. With `"poll": true` the reply waits and contains `task_id` and `task.status`. If the call times out, check later:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/music/tasks/<TASK_ID>/poll" -H "$KEY"
```

Statuses: `PENDING` → `GENERATING` → `SUCCESS` or `FAILED`.

## Step 4: Save it to the project

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/music/tasks/<TASK_ID>/download?project_id=<PID>" -H "$KEY"
```

Always pass `project_id`: the tracks land in the project's music folder, which the render reads. Suno deletes its copies after 15 days, so save promptly.

Then list them with their names and lengths:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/music" -H "$KEY"
```

To listen to one on this computer before choosing:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -fL "$FK<track.url>" -H "$KEY" -o "<track.name>"
```

Delete the variation the user doesn't want (URL-encode spaces as `%20`):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X DELETE "$FK<track.url>" -H "$KEY"
```

Print:

```
Music ready: <project_name>
  Tracks: <name> (2:41), <name> (3:05)
  Next:   /fk-concat-fit-narrator <VID>  — pick a track and a volume (0.15 sits under narration)
```

## Extend a track

When the track is much shorter than the video, extend it instead of letting it loop:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 700 -X POST "$FK/api/music/extend" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"audio_id": "<clip id from task.response>", "continue_at": 120, "poll": true}'
```

Then save it with Step 4 using the new `task_id`.

## Other Suno tools

All take `"poll": true` and return a new task; save results with Step 4.

| Endpoint | Body | Does |
|----------|------|------|
| `POST /api/music/vocal-removal` | `{"task_id", "audio_id"}` | Splits vocals from the instrumental — use it to make a song usable under narration |
| `POST /api/music/convert-to-wav` | `{"task_id", "audio_id"}` | Lossless WAV of a clip |
| `POST /api/music/generate-lyrics` | `{"prompt", "template_id"?}` | Lyrics only |
| `GET /api/music/credits` | — | Suno credits left on the server's account |
| `GET /api/music/tasks/<TASK_ID>` | — | Task status and clips |

## Models

| Model | Max Duration | Notes |
|-------|-------------|-------|
| V4 | 4 min | Highest audio quality |
| V4_5 | 8 min | Superior genre blending |
| V4_5PLUS | 8 min | Richer sound |
| V4_5ALL | 8 min | Better song structure |
| V5 | 8 min | Faster generation |
| V5_5 | 8 min | Custom model tailoring |

Default: `V4` (the server's `SUNO_MODEL`). Pass `"model": "V4_5"` in the generate body for videos longer than 4 minutes.

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `503` "SUNO_API_KEY" | The server has no Suno key | Admin adds `SUNO_API_KEY` to `.env` (https://sunoapi.org/api-key) and restarts |
| `400` "Task not complete" on download | Still generating | Poll the task, then download |
| `504` on generate | Suno took longer than the server waits | Poll `task_id` later |
| Credits error from Suno | Server's Suno account is empty | Tell the admin; or upload a royalty-free track in `/fk-concat-fit-narrator` |
| Vocals under the narration | Generated without `instrumental` | Generate again with `"instrumental": true`, or use vocal removal |

## Notes

- Each generation costs about 10 credits (5 per clip).
- Commercial use of generated music depends on the Suno plan behind the server's API key. Check it before monetizing.
- Style: max 200 chars (V4) or 1000 (V4.5+). Title: max 80-100 chars. Prompt: max 3000 chars (V4) or 5000 (V4.5+).
