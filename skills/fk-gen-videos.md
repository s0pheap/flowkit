Generate videos for all scenes in a video.

Usage: `/fk-gen-videos <project_id> <video_id>`

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

## Step 0: Detect orientation

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"
```

Read `orientation` from the response: `ORI` is `HORIZONTAL` or `VERTICAL`, and `ori` is the
same in lowercase. If it is `null`, ask the user which one the video is.
**NEVER hardcode VERTICAL or HORIZONTAL.** Use `${ORI}` for API params, `${ori}_*` for DB field lookups.

## Step 1: Pre-check — all scene images must be ready

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

**ABORT** if any scene is missing `${ori}_image_media_id` (UUID) or `${ori}_image_status` != `"COMPLETED"`. Tell user to run `/fk-gen-images` first.

## Step 2: Split scenes by look & feel, then filter

Each scene's `look_feel.mode` (set in `/fk-review-board`; missing = `"generate"`) decides how its video is made:

- **`generate`** → a generated clip, through the request queue (Step 3). The project's `effective_video_model_family` (from `GET /api/projects/<PID>`) says which model makes it: `veo` (8s clips) or `omni_flash` (`video_clip_seconds` long, 10s by default). Tell the user which one before submitting; `/fk-change-model family` switches it. Only scenes where `${ori}_video_status` != `"COMPLETED"` or `${ori}_video_media_id` is missing.
- **`ffmpeg`** → rendered locally from the keyframe with a pan/zoom (Step 3b). **Never submit these to Veo** — the API rejects the batch with 400 if you do, so a clip that will never be used isn't billed.

Print the split before submitting:
```
Veo (generate): 28 scenes — 26 need video
ffmpeg (motion): 12 scenes — 12 need render, no Flow cost
```

The plan says which ffmpeg scenes still need rendering:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/assembly-plan" -H "$KEY"
```

List the `segments` whose `needs_render` is `true` (their `scene_id`, `display_order` and `duration`).

## Step 3: Submit ALL Veo requests at once

The server handles throttling automatically (max 5 concurrent, 10s cooldown). Submit everything in one batch call. Video generation takes 2-5 minutes per scene.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/requests/batch" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"type": "GENERATE_VIDEO", "scene_id": "<SID1>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "${ORI}"},
      {"type": "GENERATE_VIDEO", "scene_id": "<SID2>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "${ORI}"}
    ]
  }'
```

Build the `requests` array from ALL scenes filtered in Step 2. Do NOT manually batch or loop.

Skip this step if every scene is ffmpeg.

Poll aggregate status every 30s until done (videos take longer):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/requests/batch-status?video_id=<VID>&type=GENERATE_VIDEO" -H "$KEY"
# Wait for: "done": true
# If "all_succeeded": false → some failed, check individual failures
```

## Step 3b: Render ffmpeg scenes

For each scene with `needs_render: true`, one call per scene (the server runs two renders at a time; each takes a few seconds to a minute):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 600 -X POST "$FK/api/scenes/<SID>/motion" -H "$KEY"   -H "Content-Type: application/json" -d '{"orientation": "'"${ORI}"'"}'
# → {"path": "output/<slug>/motion/scene_003_<id>.mp4", "duration": 6.36, ...}
```

The clip length comes from the plan (fixed length, or narration + 0.5s), so run `/fk-gen-narrator` first. Clips are 1920x1080 / 1080x1920 at 24fps with a silent stereo track. Re-render after changing a scene's motion or length.

- `409 ... no keyframe yet` → run `/fk-gen-images` for that scene
- `502 ... Could not download the keyframe` → signed URL expired, run `/fk-refresh-urls` then retry

These can run while the Veo batch is processing.

## Step 4: Verify

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

## Step 5: Output

Print results table:
| Scene | Order | Mode | video_status / motion | video_media_id | source |
|-------|-------|------|-----------------------|---------------|--------|

For ffmpeg scenes, show `motion_rendered` and `motion_path` from the assembly plan instead of Veo fields.

Print: "All videos ready — watch them in the dashboard under Projects → Pipeline. On the agent's machine, /fk-concat-fit-narrator <VID> assembles the final video."

## Important rules

- **ffmpeg scenes are never queued:** they have no Veo `media_id`, so skip them for `/fk-review-video` and upscale too.
- **GENERATE vs REGENERATE:** `GENERATE_VIDEO` skips scenes already `COMPLETED`. To force-regenerate, reset `${ori}_video_status` to `PENDING` first, then submit.
- **Cascade on regen:** Regenerating a video auto-clears the upscale status for that scene.
- **Chain video prompt rule (CRITICAL):** Chain scenes with children use `transition_prompt` for video generation, NOT `video_prompt`. This is because the video transitions from the current scene's image to the child scene's image. When fixing chain scene videos, always update `transition_prompt`. `video_prompt` is only used for ROOT scenes or leaf scenes (no children).
- **Chain cascade (CRITICAL):** When regenerating a scene that has CONTINUATION children, you MUST also regenerate images + videos for all descendants in the chain. The child's image was EDIT_IMAGE'd from the parent's old image — if the parent's video changes, the child's start frame won't match the parent's end frame.
  - Walk the full chain to the leaf: `parent_scene_id` links form the chain
  - Regen child images **sequentially** (each child depends on parent completing first)
  - **Update `end_scene_media_id`**: After each child image regen completes, PATCH parent's `${ori}_end_scene_media_id` = child's new `${ori}_image_media_id`. This is CRITICAL — without it, video gen uses stale end frame and the video won't transition to the child's image.
  - After all images complete + end_scene_media_ids updated, regen the **parent video too** (so its end frame matches child's new start image)
  - Then batch regen videos for all children (parent + children can be parallel)
  - **Always proactively propose this cascade to the user** — don't wait for them to notice the mismatch
