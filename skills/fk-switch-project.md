# fk-switch-project — Switch Active Project

Switch the active project so all skills automatically target the correct project without needing explicit `project_id`.

Usage:
- `/fk-switch-project` — list projects and switch interactively
- `/fk-switch-project <project_id>` — switch to a specific project by ID
- `/fk-switch-project clear` — clear active project (revert to most-recent fallback)

---

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

## Step 1: List Available Projects

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects" -H "$KEY" | python3 -c "
import sys, json
projects = json.load(sys.stdin)
print(f'{'#':>3}  {'Name':40} {'ID':36}  {'Status':8}  Material')
print('-' * 110)
for i, p in enumerate(projects, 1):
    active = ''
    print(f'{i:>3}  {p[\"name\"][:40]:40} {p[\"id\"]:36}  {p.get(\"status\",\"?\"):8}  {p.get(\"material\",\"?\")}')
"
```

## Step 2: Show Current Active Project

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/active-project" -H "$KEY" | python3 -c "
import sys, json
ap = json.load(sys.stdin)
if ap.get('project_id'):
    print(f'Active: {ap[\"project_name\"]} ({ap[\"project_id\"][:8]}...)')
    print(f'Video:  {ap.get(\"video_id\", \"none\")}')
    print(f'Source: {ap[\"source\"]}')
else:
    print('No active project set')
"
```

## Step 3: Switch Project

If the user provided a `project_id` argument, use it directly. Otherwise, present an `AskUserQuestion` selector with up to 4 projects (most recent first, showing name + material + short ID). After user picks, switch:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X PUT "$FK/api/active-project" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<PROJECT_ID>"}'
```

Use `AskUserQuestion` with options like:
- label: project name
- description: `#N · material · project_id_short`

If more than 4 projects exist, show the 4 most recent and let the user type "Other" for older ones.

## Step 4: Verify

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/active-project" -H "$KEY" | python3 -c "
import sys, json
ap = json.load(sys.stdin)
print(f'Switched to: {ap[\"project_name\"]}')
print(f'Project ID:  {ap[\"project_id\"]}')
print(f'Video ID:    {ap.get(\"video_id\", \"none\")}')
"
```

## Step 5: Clear (optional)

To revert to the default behavior (most recently created project):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X DELETE "$FK/api/active-project" -H "$KEY"
```

---

## How It Works

- `PUT /api/active-project` sets the active project (persists across server restarts)
- `GET /api/active-project` returns the active project, or falls back to the most recently created
- Skills that accept optional `project_id` should use `GET /api/active-project` when none is provided
- Statusline reads from this endpoint to show the correct project name

## Notes

- Switching project does NOT affect running requests — only future operations
- If the active project is deleted, the endpoint auto-clears and falls back to most recent
- The `source` field tells you whether the project was explicitly set (`explicit`) or auto-detected (`fallback_most_recent`)
