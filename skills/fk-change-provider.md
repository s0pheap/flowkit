# fk-change-provider — View & Switch AI CLI Provider (Video Review)

View or switch which AI CLI backend (`claude`, `agy`, or `codex`) is used for vision analysis during video review.

Usage:
- `/fk-change-provider` — show current provider status
- `/fk-change-provider list` — show current provider status
- `/fk-change-provider set <claude|agy|codex>` — switch active provider

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

## Step 1: Show Current Status

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/providers?live=true" -H "$KEY" | python3 -m json.tool
```

Display in a readable table:

| Provider | Binary | Installed | Tested | Active |
|----------|--------|-----------|--------|--------|
| claude | `claude` | Yes | Yes | ✅ |
| agy | `agy` | Yes | Yes | |
| codex | `codex` | Yes | No | |

- `Installed` reflects whether the binary is found on PATH.
- `Tested` reflects the live `<binary> --version` probe (populated because of `?live=true`); `null`/missing means not yet probed.
- `Active` gets a checkmark on whichever provider matches the top-level `active` field in the response.

## Step 2: Quick Select (Interactive)

If no provider was given as an argument, use `AskUserQuestion` to let the user pick — only offer providers where `installed: true` as selectable options.

For any provider with `installed: false`, list it as unavailable with a note like "install `<binary>` first" instead of offering it as a selectable option.

## Step 3: Change the Provider

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X PATCH "$FK/api/providers" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": "<provider>"}'
```

- Returns `{"status": "updated", "active": "<provider>"}` on success.
- Returns `400` if the provider name is unknown, or if its binary isn't found on PATH.

## Step 4: Verify

After changing, verify the update took effect:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/providers?live=true" -H "$KEY" | python3 -m json.tool
```

Confirm the `active` field now matches the provider you selected.

Changes are **hot-reloaded** — no server restart needed. The new provider is used immediately for all subsequent video review requests.

---

## Notes

- `claude` = Claude Code CLI (default)
- `agy` = Google Antigravity CLI
- `codex` = OpenAI Codex CLI
- Switching is hot-reloaded — no server restart needed.
- **`codex` requires a separate one-time `codex login` (interactive OAuth in a terminal) before it will actually work.** Being listed as `installed: true` only means the binary is present on PATH — it does not mean it's authenticated. If a codex-backed review fails with an auth error, run `codex login` and retry.
- If you set a provider whose binary later goes missing, the next review request will fail clearly (not silently) — switch back via this skill.
