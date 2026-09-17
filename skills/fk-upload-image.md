Upload a local image file to Google Flow and get a media_id (UUID).

Usage: `/fk-upload-image <file_path> [--project <project_id>] [--entity <entity_id>]`

Useful for: setting channel icons, covers, or any local image as an entity reference or scene image.

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

## Step 1: Check health

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/health" -H "$KEY"
```
Must have `extension_connected: true`. Abort if not.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/flow/status" -H "$KEY"
# Must return: {"connected": true, "transport": "batch", "flow_project_id": "<uuid>"}
# flow_key_present is a legacy-path signal — false is expected here.
```

The upload is scoped to a Flow project: pass `project_id`, or leave it out to
use the pinned `FLOW_PROJECT_ID`. Without either you get `NO_FLOW_PROJECT`.

## Step 2: Upload image

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/flow/upload-image" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/absolute/path/to/image.png",
    "project_id": "<PID>",
    "file_name": "descriptive_name.png"
  }'
```

**Parameters:**
- `file_path` (required): Absolute path to local image file (PNG, JPG, WebP)
- `project_id` (optional): Project to associate the upload with
- `file_name` (optional): Descriptive filename, defaults to `image.png`

**Response:**
```json
{
  "media_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "raw": { "media": { "name": "uuid", ... } }
}
```

The `media_id` is the UUID you use everywhere (entity refs, scene images, video start frames).

## Step 3: Apply the media_id

### Option A: Set as entity reference image

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X PATCH "$FK/api/characters/<ENTITY_ID>" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"media_id": "<MEDIA_ID>"}'
```

### Option B: Set as scene image

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X PATCH "$FK/api/scenes/<SCENE_ID>" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "horizontal_image_media_id": "<MEDIA_ID>",
    "horizontal_image_status": "COMPLETED"
  }'
```
(Use `${ori}_image_media_id` / `${ori}_image_status` matching project orientation.)

### Option C: Create new entity with uploaded image

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# 1. Create entity
curl -s -X POST "$FK/api/characters" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Asset Name",
    "entity_type": "visual_asset",
    "description": "What the image shows",
    "media_id": "<MEDIA_ID>"
  }'

# 2. Link to project
curl -s -X POST "$FK/api/projects/<PID>/characters/<ENTITY_ID>" -H "$KEY"
```

## Step 4: Verify

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# For entity:
curl -s "$FK/api/characters/<ENTITY_ID>" -H "$KEY" | python3 -c "
import sys,json; c=json.load(sys.stdin)
print(f'{c[\"name\"]}: media_id={c.get(\"media_id\",\"none\")}')"

# For scene:
curl -s "$FK/api/scenes/<SCENE_ID>" -H "$KEY" | python3 -c "
import sys,json; s=json.load(sys.stdin)
print(f'img_status={s.get(\"horizontal_image_status\")} mid={s.get(\"horizontal_image_media_id\")}')"
```

## Common Workflows

### Upload channel branding assets
```bash
# Upload icon
/fk-upload-image youtube/channels/<channel>/<channel>_icon.png --project <PID>
# Upload cover
/fk-upload-image youtube/channels/<channel>/<channel>_cover.png --project <PID>
```

### Replace a scene image with a local file
```bash
# Upload the image
/fk-upload-image /path/to/better_image.png --project <PID>
# Patch the scene with the returned media_id
# Then regenerate video from the new image
```

## Notes

- The upload goes through the Chrome extension's `uploadImage` API to Google Flow
- Extension must be connected with a valid flow key
- Supported formats: PNG, JPG, JPEG, WebP (auto-detected from file extension)
- The uploaded image becomes available as a media_id for use in video generation, edit operations, or as reference images
- If `media_id` returns `null`, check that the flow key is present (`GET /api/flow/status`)
