Build the final video on the server — each scene fitted to its narration, with text overlays, transitions and subtitles — then download it.

Usage: `/fk-concat-fit-narrator <video_id> [--buffer 0.5] [--subs soft|burn|none]`

Everything runs on the agent (ffmpeg on the server), so this works the same on the agent's own machine and from another computer. All timing comes from one source — `GET /api/videos/<VID>/assembly-plan` — so captions land exactly where the narration plays. By default each scene runs `narrator_duration + 0.5s` unless its look & feel (set in `/fk-review-board`) fixes a length.

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

## Step 1: Check the plan

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/assembly-plan?buffer=0.5" -H "$KEY"
```

Key fields:

| Field | Meaning |
|-------|---------|
| `segments[]` | One per scene, sorted by `display_order` |
| `segments[].mode` | `generate` (Veo clip) or `ffmpeg` (pan/zoom of the keyframe) |
| `segments[].video_source` | The clip that will be used (null = no video yet) |
| `segments[].needs_render` | An ffmpeg scene with no clip yet — the render makes it, nothing to do |
| `segments[].start`, `duration` | Where the scene starts in the final video and how long it runs |
| `segments[].narration_duration` | Narration length, or null |
| `segments[].transition`, `transition_duration` | Hand-off into the next scene (`cut` = none) |
| `total_duration` | Final runtime |

**Stop** if a `generate` segment has `video_source: null`: "Scene N has no video. Run /fk-gen-videos first."

A Veo scene whose narration is longer than its clip is capped at the clip — warn: "Scene N narration (8.1s) is longer than its Veo clip; it will be cut off. Shorten the line or switch the scene to ffmpeg."

Print the plan and ask the user to confirm:

```
Scene | Mode   | Start   | Length | Narration | Transition
------|--------|---------|--------|-----------|-----------
  001 | veo    | 0:00.0  |  6.80s |    6.30s  | fade 0.5s
  002 | ffmpeg | 0:06.3  | 11.20s |   10.70s  | cut
  ...
Total: 5:12.4  (Veo 28 scenes, ffmpeg 12 scenes)
```

## Step 2: Start the render

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/videos/<VID>/render" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"buffer": 0.5, "subs": "soft"}'
```

| `subs` | Result | Use for |
|--------|--------|---------|
| `soft` (default) | Subtitles as a track viewers can turn off, plus a separate `.srt` | YouTube long-form |
| `burn` | Subtitles drawn into the picture | Shorts, social |
| `none` | No subtitles | — |

Text overlays saved by `/fk-gen-text-overlays` are burned in automatically. ffmpeg scenes without a clip are rendered as part of the job.

Responses:
- `202` → the job started; go to Step 3.
- `409` with `detail.problems` → print each problem and fix it (usually `/fk-gen-videos` or `/fk-refresh-urls`), then start again.
- `409` "already running" → go to Step 3 and wait for that render.

## Step 3: Wait for it

Poll every 20 seconds:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/render" -H "$KEY"
```

Show `step` and `done_steps`/`total_steps` as progress. Only one render runs on the server at a time, so `queued` means another video is rendering. Expect a few minutes for a long video.

- `status: done` → Step 4.
- `status: failed` → print `error`. If it mentions an expired link or `403`, run `/fk-refresh-urls <VID>` and start again. Otherwise run `/fk-doctor` with the error text.

## Step 4: Download

`<SLUG>` is the file name stem from `output_path` (for example `moon_base_narrator_cut`).

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -fL "$FK/api/videos/<VID>/final.mp4?download=1" -H "$KEY" -o "<SLUG>.mp4"
# Only when the job has a captions_url:
curl -fL "$FK/api/videos/<VID>/captions.srt?download=1" -H "$KEY" -o "<SLUG>.srt"
```

Save into the user's current folder unless they asked for another one. The files also stay on the server, and the dashboard plays the video under **Projects → the project → Videos**.

Print:

```
Final video ready: <project_name>
  File:      ./<SLUG>.mp4  (<size> MB)
  Duration:  X:XX  (plan X:XX)
  Subtitles: soft track + ./<SLUG>.srt
  Warnings:  <job.warnings, if any>
  Watch:     <FLOWKIT_URL>/projects/<PID>
```

Keep the `.srt` — `/fk-youtube-upload` can upload it as a caption track.

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `409` "has no video yet" | A Veo scene was never generated | `/fk-gen-videos` |
| `409` or failure about an expired link | Flow's signed video links expire after a few hours | `/fk-refresh-urls <VID>`, then render again |
| Narration cut off mid-sentence | Veo clip shorter than the narration | Shorten the line, or set the scene to ffmpeg in `/fk-review-board`; a bigger `buffer` only helps ffmpeg scenes |
| Captions drift | Look & feel changed after the render | Render again — lengths and captions are recomputed from the plan every time |
| Warning "Text overlays skipped: no font found" | The server has no font for the overlay language | Admin sets `OVERLAY_FONT` in `.env` |
| Korean captions show as boxes (`burn`) | Server font lacks Hangul | Admin sets `SUBTITLE_FONT` (e.g. `Malgun Gothic`, `Noto Sans CJK KR`) |
| `404` on `final.mp4` | No finished render for this video | Steps 2-3 |
