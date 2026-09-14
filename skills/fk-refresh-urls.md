Re-sign expired media URLs for all scenes in a video (images, videos, upscale videos) and character reference images.

Usage: `/fk-refresh-urls <video_id> [--project-id <PID>]`

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

## When to use

- Before `/fk-review-video` if videos were generated hours ago (GCS signed URLs expire)
- Before `/fk-concat-fit-narrator` if downloading from URLs instead of local files
- After any long gap between generation and consumption of media URLs

## Pre-flight

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/flow/status" -H "$KEY"
# Must show: {"connected": true, "transport": "batch"}
# Ignore flow_key_present — the batch path has no bearer token.
# If connected is false: open https://flow.google.com/ and sign in.
```

## Step 1: Get project_id from video

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"
```

Take `project_id` (`PID`) from the response.

## Step 2: Bulk re-sign every stored media id

This walks the project's scenes and entities, asks Flow's media rpc to re-sign
each `*_media_id` it holds, and writes the fresh urls back to the DB. It is a
call per media id, so a large project takes a moment.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/flow/refresh-urls/<PID>" -H "$KEY"
```

Print `Refreshed: <refreshed> URLs (found <found> total)`, and the `error` if there is one.

**What gets updated:**
- `horizontal_image_url` / `vertical_image_url` — scene images
- `horizontal_video_url` / `vertical_video_url` — scene videos (original)
- `horizontal_upscale_url` / `vertical_upscale_url` — 4K upscaled videos
- `reference_image_url` — character/entity reference images

The server matches each URL's media_id against `*_media_id` fields on scenes and characters, updating whichever orientation/type matches.

## Step 3: Verify refresh worked

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

Use the video's `orientation` (`ori` = lowercase). For each scene, look at `${ori}_video_url`:
- has an `Expires=<unix time>` in the future, or no expiry → valid
- empty, or `Expires` in the past → still expired

Print `Orientation`, `Valid URLs: <ok>/<scenes>`, and either "All URLs refreshed" or how many are still expired. On a shared server, still-expired links usually mean the server's Flow tab is signed out — tell the user to ask the admin.

## Step 4: Per-media fallback (for anything the bulk pass missed)

If a media id was not covered — because it is not stored on a scene or entity
row — re-sign it directly:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/flow/media/<MEDIA_ID>" -H "$KEY"
# Returns: {"video": {"fifeUrl": "https://flow-content.google/video/…"},
#           "image": {"fifeUrl": "https://flow-content.google/image/…"}}
```

A record with only `image` and no `video` means the clip is not finished being
written yet — the poster arrives before the video url does. Wait and retry;
do not save the poster as the video.

Then update the scene manually:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X PATCH "$FK/api/scenes/<SID>" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"horizontal_video_url": "<FRESH_URL>"}'
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `flow_key_present: false` | No bearer token — **expected on the batch path** | Ignore; only meaningful with `USE_BATCH_RPC=0` |
| `Extension not connected` | Chrome extension WS disconnected | Check the extension is enabled, refresh the Flow tab |
| `refreshed: 0`, `found: 0` | No media ids stored for this project | Nothing to refresh — check the project id |
| `refreshed: 0`, `found: N` | Every re-sign failed | Read the agent log; usually `NO_FLOW_TAB` or a signed-out Flow tab |
| Some URLs still expired after refresh | media_id mismatch (upscale overwrote video_media_id) | Use per-media fallback with correct media_id |
| `get_media` returns error for media_id | Media deleted or expired on Google's side | Re-generate the video/image |
