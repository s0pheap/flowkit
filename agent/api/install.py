"""Public installer for users of a shared agent: skills plus a one-line install script.

Nothing here needs a key or reveals one. The scripts ask the user for their key,
check it against /api/auth/me, write ~/.flowkit/env and drop each skill into the
AI tools found on the machine:

    Claude Code   ~/.claude/skills/<name>/SKILL.md
    Codex         ~/.agents/skills/<name>/SKILL.md
    Antigravity   ~/.gemini/config/skills/<name>/SKILL.md
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from agent import config

router = APIRouter(prefix="/install", tags=["install"])

# The repo's skills, not FLOW_AGENT_DIR (which only moves the database and .env).
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

# Skills that work against a remote agent: API calls only, nothing read from the
# server's disk. Keep in step with the `remote` flag in dashboard/src/pages/guide/skills.ts.
REMOTE_SKILLS = (
    "fk-research",
    "fk-create-project",
    "fk-gen-refs",
    "fk-gen-images",
    "fk-gen-videos",
    "fk-status",
    "fk-switch-project",
    "fk-doctor",
    "fk-camera-guide",
    "fk-refresh-urls",
    "fk-gen-narrator",
    "fk-gen-text-overlays",
    "fk-gen-music",
    "fk-review-board",
    "fk-concat-fit-narrator",
    "fk-add-material",
    "fk-upload-image",
    "fk-insert-scene",
    "fk-gen-chain-videos",
    "fk-creative-mix",
    "fk-thumbnail-guide",
)


def _skill_path(name: str):
    if name not in REMOTE_SKILLS:
        raise HTTPException(404, f"Skill {name!r} is not offered by this server")
    path = SKILLS_DIR / f"{name}.md"
    if not path.is_file():
        raise HTTPException(404, f"Skill {name!r} is missing on the server")
    return path


def _description(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first.lstrip("#").strip()


def render_skill(name: str) -> str:
    """The skill with the SKILL.md frontmatter every supported tool reads."""
    body = _skill_path(name).read_text(encoding="utf-8").replace("\r\n", "\n")
    return f"---\nname: {name}\ndescription: {json.dumps(_description(body), ensure_ascii=False)}\n---\n\n{body}"


def public_url(request: Request) -> str:
    return (config.PUBLIC_URL or str(request.base_url)).rstrip("/")


@router.get("/skills.json")
async def list_skills():
    return [{"name": n, "description": _description(_skill_path(n).read_text(encoding="utf-8"))} for n in REMOTE_SKILLS]


@router.get("/skills/{name}/SKILL.md", response_class=PlainTextResponse)
async def skill_file(name: str):
    return PlainTextResponse(render_skill(name), media_type="text/markdown; charset=utf-8")


_SH = r"""#!/usr/bin/env bash
# Flow Kit skills installer for __BASE__
# Usage: curl -fsSL __BASE__/install.sh | bash
# Optional: FLOWKIT_API_KEY=fk_... FLOWKIT_TOOLS="claude codex antigravity"
set -euo pipefail

BASE="__BASE__"
SKILLS="__SKILLS__"
KEY="${FLOWKIT_API_KEY:-}"
TOOLS="${FLOWKIT_TOOLS:-}"

if [ -z "$KEY" ]; then
  if [ -r /dev/tty ]; then
    printf 'Flow Kit API key (ask your admin): ' > /dev/tty
    IFS= read -rs KEY < /dev/tty
    printf '\n' > /dev/tty
  else
    echo "No terminal to ask for the key. Run again with FLOWKIT_API_KEY=fk_... set." >&2
    exit 1
  fi
fi

ME="$(mktemp)"
CODE="$(curl -s -o "$ME" -w '%{http_code}' -H "X-API-Key: $KEY" "$BASE/api/auth/me" || true)"
if [ "$CODE" != "200" ]; then
  echo "The server did not accept that key (HTTP $CODE). Check it with your admin." >&2
  rm -f "$ME"
  exit 1
fi
echo "Key accepted: $(tr -d '\n' < "$ME")"
rm -f "$ME"

if [ -z "$TOOLS" ]; then
  { [ -d "$HOME/.claude" ] || command -v claude >/dev/null 2>&1; } && TOOLS="$TOOLS claude"
  { [ -d "$HOME/.codex" ] || [ -d "$HOME/.agents" ] || command -v codex >/dev/null 2>&1; } && TOOLS="$TOOLS codex"
  { [ -d "$HOME/.gemini" ] || command -v agy >/dev/null 2>&1; } && TOOLS="$TOOLS antigravity"
  [ -z "$TOOLS" ] && TOOLS="claude codex antigravity"
fi

mkdir -p "$HOME/.flowkit"
( umask 077
  printf "export FLOWKIT_URL='%s'\nexport FLOWKIT_API_KEY='%s'\n" "$BASE" "$KEY" > "$HOME/.flowkit/env" )
chmod 600 "$HOME/.flowkit/env"
echo "Saved server and key to ~/.flowkit/env"

for tool in $TOOLS; do
  case "$tool" in
    claude) dir="$HOME/.claude/skills" ;;
    codex) dir="$HOME/.agents/skills" ;;
    antigravity|agy|gemini) dir="$HOME/.gemini/config/skills" ;;
    *) echo "Skipping unknown tool: $tool" >&2; continue ;;
  esac
  for skill in $SKILLS; do
    mkdir -p "$dir/$skill"
    curl -fsSL "$BASE/install/skills/$skill/SKILL.md" -o "$dir/$skill/SKILL.md"
  done
  echo "Installed $(echo $SKILLS | wc -w | tr -d ' ') skills for $tool in $dir"
done

echo
echo "Done. Restart your AI tool, then try /fk-status."
echo "Dashboard: $BASE  (sign in with the same key)"
"""

_PS1 = r"""# Flow Kit skills installer for __BASE__
# Usage: irm __BASE__/install.ps1 | iex
# Optional: $env:FLOWKIT_API_KEY = 'fk_...'; $env:FLOWKIT_TOOLS = 'claude codex antigravity'
function Install-FlowKitSkills {
  $ErrorActionPreference = 'Stop'
  $Base = '__BASE__'
  $Skills = @(__PS_SKILLS__)

  $Key = $env:FLOWKIT_API_KEY
  if (-not $Key) {
    $secure = Read-Host 'Flow Kit API key (ask your admin)' -AsSecureString
    $Key = [System.Net.NetworkCredential]::new('', $secure).Password
  }

  try {
    $me = Invoke-RestMethod -Uri "$Base/api/auth/me" -Headers @{ 'X-API-Key' = $Key }
  } catch {
    Write-Host "The server did not accept that key. Check it with your admin." -ForegroundColor Red
    return
  }
  Write-Host "Key accepted: $($me.name)"

  $tools = @()
  if ($env:FLOWKIT_TOOLS) {
    $tools = $env:FLOWKIT_TOOLS -split '[ ,]+' | Where-Object { $_ }
  } else {
    if ((Test-Path "$HOME\.claude") -or (Get-Command claude -ErrorAction SilentlyContinue)) { $tools += 'claude' }
    if ((Test-Path "$HOME\.codex") -or (Test-Path "$HOME\.agents") -or (Get-Command codex -ErrorAction SilentlyContinue)) { $tools += 'codex' }
    if ((Test-Path "$HOME\.gemini") -or (Get-Command agy -ErrorAction SilentlyContinue)) { $tools += 'antigravity' }
    if (-not $tools) { $tools = @('claude', 'codex', 'antigravity') }
  }

  # Skills run their commands in bash (Git Bash / WSL), which reads ~/.flowkit/env.
  $envDir = Join-Path $HOME '.flowkit'
  New-Item -ItemType Directory -Force -Path $envDir | Out-Null
  $envText = "export FLOWKIT_URL='$Base'`nexport FLOWKIT_API_KEY='$Key'`n"
  [System.IO.File]::WriteAllText((Join-Path $envDir 'env'), $envText)
  # Also as user environment variables, for PowerShell sessions.
  [Environment]::SetEnvironmentVariable('FLOWKIT_URL', $Base, 'User')
  [Environment]::SetEnvironmentVariable('FLOWKIT_API_KEY', $Key, 'User')
  Write-Host "Saved server and key to ~\.flowkit\env and your user environment"

  $targets = @{
    'claude' = '.claude\skills'; 'codex' = '.agents\skills'
    'antigravity' = '.gemini\config\skills'; 'agy' = '.gemini\config\skills'; 'gemini' = '.gemini\config\skills'
  }
  foreach ($tool in $tools) {
    if (-not $targets.ContainsKey($tool)) { Write-Host "Skipping unknown tool: $tool"; continue }
    $dir = Join-Path $HOME $targets[$tool]
    foreach ($skill in $Skills) {
      $target = Join-Path $dir $skill
      New-Item -ItemType Directory -Force -Path $target | Out-Null
      Invoke-WebRequest -UseBasicParsing -Uri "$Base/install/skills/$skill/SKILL.md" -OutFile (Join-Path $target 'SKILL.md')
    }
    Write-Host "Installed $($Skills.Count) skills for $tool in $dir"
  }

  Write-Host ""
  Write-Host "Done. Restart your AI tool, then try /fk-status."
  Write-Host "Dashboard: $Base  (sign in with the same key)"
}
Install-FlowKitSkills
"""


def _script(template: str, request: Request) -> str:
    return (template
            .replace("__BASE__", public_url(request))
            .replace("__SKILLS__", " ".join(REMOTE_SKILLS))
            .replace("__PS_SKILLS__", ", ".join(f"'{s}'" for s in REMOTE_SKILLS)))


def install_sh(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_script(_SH, request), media_type="text/x-shellscript; charset=utf-8")


def install_ps1(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_script(_PS1, request), media_type="text/plain; charset=utf-8")
