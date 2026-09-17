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
VID="<video_id>"
PID=$(curl -s "$FK/api/videos/${VID}" -H "$KEY" | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")
echo "Project: $PID"
```

## Step 2: Bulk re-sign every stored media id

This walks the project's scenes and entities, asks Flow's media rpc to re-sign
each `*_media_id` it holds, and writes the fresh urls back to the DB. It is a
call per media id, so a large project takes a moment.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/flow/refresh-urls/${PID}" -H "$KEY" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f\"Refreshed: {r.get('refreshed', 0)} URLs (found {r.get('found', 0)} total)\")
if r.get('error'):
    print(f\"ERROR: {r['error']}\")
"
```

**What gets updated:**
- `horizontal_image_url` / `vertical_image_url` — scene images
- `horizontal_video_url` / `vertical_video_url` — scene videos (original)
- `horizontal_upscale_url` / `vertical_upscale_url` — 4K upscaled videos
- `reference_image_url` — character/entity reference images

The server matches each URL's media_id against `*_media_id` fields on scenes and characters, updating whichever orientation/type matches.

## Step 3: Verify refresh worked

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# Check a few scenes have valid URLs
curl -s "$FK/api/scenes?video_id=${VID}" -H "$KEY" | python3 -c "
import sys, json
scenes = sorted(json.load(sys.stdin), key=lambda s: s['display_order'])

# Auto-detect orientation
ori = 'horizontal'
for s in scenes:
    if s.get('horizontal_video_status') == 'COMPLETED' and s.get('horizontal_video_url'):
        ori = 'horizontal'; break
    if s.get('vertical_video_status') == 'COMPLETED' and s.get('vertical_video_url'):
        ori = 'vertical'; break

ok = 0; expired = 0
for s in scenes:
    url = s.get(f'{ori}_video_url') or ''
    if url and 'Expires=' in url:
        import re, time
        m = re.search(r'Expires=(\d+)', url)
        if m and int(m.group(1)) > time.time():
            ok += 1
        else:
            expired += 1
    elif url:
        ok += 1
    else:
        expired += 1

print(f'Orientation: {ori.upper()}')
print(f'Valid URLs: {ok}/{len(scenes)}')
if expired:
    print(f'Still expired: {expired} — may need to open Flow tab in Chrome for flow key')
else:
    print('All URLs refreshed successfully!')
"
```

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
