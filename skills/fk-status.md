Show full status dashboard for a project.

Usage: `/fk-status <project_id>` or `/fk-status` (lists all projects)

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

## If no project_id: list all projects

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects" -H "$KEY"
```

Print table: ID | Name | Tier | Status

## With project_id: full dashboard

### 1. Server health
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/health" -H "$KEY"
```

### 2. Project info
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects/<PID>" -H "$KEY"
```

### 3. Entities (references)
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects/<PID>/characters" -H "$KEY"
```

Print table:
| Entity | Type | media_id | ref_url | Ready? |
|--------|------|----------|---------|--------|

### 4. Videos + Orientation Detection
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos?project_id=<PID>" -H "$KEY"
```

**CRITICAL:** Read the `orientation` field from the video response. This determines which scene fields to read:
- `HORIZONTAL` → use `horizontal_image_status`, `horizontal_video_status`, `horizontal_upscale_status`
- `VERTICAL` → use `vertical_image_status`, `vertical_video_status`, `vertical_upscale_status`
- `null` → auto-detect: check first scene's fields, prefer whichever has a non-PENDING status

Set `ORI` = the detected orientation (lowercase: `horizontal` or `vertical`). Display it in the header.

### 5. For each video — scenes
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

Print table (sorted by display_order), using `${ORI}_*` prefix fields:
| # | Prompt (50 chars) | Refs | Image (${ORI}) | Video (${ORI}) | Upscale (${ORI}) |
|---|-------------------|------|----------------|----------------|------------------|

Where Image/Video/Upscale show: `OK`, `PENDING`, `PROCESSING`, `FAILED`
Read from: `${ORI}_image_status`, `${ORI}_video_status`, `${ORI}_upscale_status`

### 6. Pending/processing requests
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/requests/pending" -H "$KEY"
```

### 7. Summary

Print orientation and counts: `Orientation: ${ORI}` then X/Y refs ready, X/Y images done, X/Y videos done, X/Y upscaled.
Use `${ORI}_image_status`, `${ORI}_video_status`, `${ORI}_upscale_status` for counting.

Suggest next action:
- If refs missing → "Run /fk-gen-refs <PID>"
- If images missing → "Run /fk-gen-images <PID> <VID>"
- If videos missing → "Run /fk-gen-videos <PID> <VID>"
- If all done → "Run /fk-concat <VID>"

## Statusline Integration

The `/fk-status` output is available in Claude Code's statusline at the bottom, showing live project progress:

```
GLA: ✓ext Operation Hormu 40sc img:40 vid:40 4K:26 ▶0/5
```

**Note:** Default orientation for TTS narration is **HORIZONTAL** (landscape, 16:9). For VERTICAL (portrait, 9:16) projects, explicitly pass `orientation: "VERTICAL"` to `/fk-gen-narrator`.
