Find and fix any non-UUID media_ids (CAMS... format) across all scenes and entities.

Usage: `/fix-uuids <project_id> <video_id>`

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

## Step 1: Check entities

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects/<PID>/characters" -H "$KEY"
```

For each entity, check if `media_id` is UUID format (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
If it starts with `CAMS` or doesn't match UUID pattern:
- Extract UUID from `reference_image_url` (URL contains `/image/{UUID}?...`)
- Patch: `PATCH /api/characters/<CID>` with `{"media_id": "<extracted_uuid>"}`

## Step 2: Check scenes

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

Detect orientation from project `meta.json` (`${ori}` = `horizontal` or `vertical`).

For each scene, check these fields:
- `${ori}_image_media_id`
- `${ori}_video_media_id`
- `${ori}_upscale_media_id`

If any starts with `CAMS` or doesn't match UUID:
- Extract UUID from the corresponding URL field (`${ori}_image_url`, `${ori}_video_url`, etc.)
- URL format: `https://storage.googleapis.com/ai-sandbox-videofx/{type}/{UUID}?...`
- Patch: `PATCH /api/scenes/<SID>` with `{"<field>": "<extracted_uuid>"}`

## Step 3: Output

Print table of all fixes applied:
| Resource | Field | Old (CAMS...) | New (UUID) |
|----------|-------|---------------|-----------|

If no fixes needed, print "All media_ids are already UUID format."
