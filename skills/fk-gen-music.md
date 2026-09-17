# fk-gen-music — Generate Music via Suno

Generate background music or songs for video projects using the Suno API (sunoapi.org).

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

## Prerequisites

- GLA server running: `curl "$FK/health`" -H "$KEY"
- Suno API key configured: `export SUNO_API_KEY=your-key`
- Get API key at https://sunoapi.org/api-key

## Workflow

### Step 1: Choose a Template (Optional)

Browse available song templates to find the right style:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# List all templates
curl -s "$FK/api/music/templates" -H "$KEY" | python3 -m json.tool

# Get a specific template (see style, tags, example lyrics)
curl -s "$FK/api/music/templates/cinematic_epic" -H "$KEY"
```

Available categories: Children & Family, Love & Romance, Pop, Rock, Hip-Hop, Electronic, Country & Folk, Cinematic, Motivational.

### Step 2: Generate Music

**Three modes:**

#### Mode A: Template-based (recommended for video projects)

Use a template to auto-fill style tags. Provide custom lyrics or let the template's example lyrics run:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# With custom lyrics + template style
curl -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "cinematic_epic",
    "prompt": "[Verse]\nFrom the shadows they emerge\nAcross the ancient sea\n[Chorus]\nRise, rise to glory\nThe world will hear our story",
    "title": "Rise to Glory",
    "poll": true
  }'

# Template defaults (uses example lyrics + suno_tags)
curl -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "lullaby_gentle",
    "title": "Goodnight Luna",
    "poll": true
  }'
```

#### Mode B: Custom (full control)

Provide your own lyrics and style tags:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "[Verse]\nWalking through the rain\nSearching for the light\n[Chorus]\nWe will find our way\nThrough the darkest night",
    "style": "lo-fi hip hop, chill, piano, rainy, 90 BPM",
    "title": "Rainy Night",
    "poll": true
  }'
```

#### Mode C: Description (AI writes everything)

Just describe what you want in natural language:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "an epic orchestral track for a military documentary about naval battles, dramatic and heroic",
    "instrumental": true,
    "custom_mode": false,
    "poll": true
  }'
```

### Step 3: Check Results

Each generation produces **2 clips** (variations). When `poll: true`, the response waits for completion.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# If poll was false, check status manually:
curl -s "$FK/api/music/tasks/<TASK_ID>" -H "$KEY"

# Poll until complete:
curl -X POST "$FK/api/music/tasks/<TASK_ID>/poll" -H "$KEY"
```

**Task statuses:** `PENDING` → `GENERATING` → `SUCCESS` or `FAILED`

### Step 4: Download

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/tasks/<TASK_ID>/download" -H "$KEY"
# Returns: {"task_id": "...", "downloaded": [{"clip_id": "...", "path": "output/_shared/music/title_abcd1234.mp3", ...}]}
```

### Step 5: Use in Video (Optional)

Add the downloaded music as background for your concat video:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# Get project output directory
PROJ_OUT=$(curl -s "$FK/api/projects/<PID>/output-dir" -H "$KEY")
OUTDIR=$(echo "$PROJ_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")
SLUG=$(echo "$PROJ_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['slug'])")

# Mix music with concat video using ffmpeg
ffmpeg -y -i "${OUTDIR}/${SLUG}_final.mp4" -i output/_shared/music/track.mp3 \
  -filter_complex "[1:a]volume=0.3[bg]; [0:a][bg]amix=inputs=2:duration=first[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac "${OUTDIR}/${SLUG}_with_music.mp4"
```

## Extend a Track

Continue or extend an existing clip from a previous generation:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/extend" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "audio_id": "<AUDIO_ID from clip>",
    "prompt": "[Chorus]\nKeep the fire burning bright",
    "continue_at": 120,
    "poll": true
  }'
```

## Vocal Removal (Stem Separation)

Separate vocals from instrumental:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/vocal-removal" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "<TASK_ID>",
    "audio_id": "<AUDIO_ID>",
    "poll": true
  }'
# Returns: instrumental_url + vocal_url
```

## Convert to WAV

Get lossless WAV from a generated clip:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/convert-to-wav" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "<TASK_ID>",
    "audio_id": "<AUDIO_ID>",
    "poll": true
  }'
```

## Generate Lyrics Only

Ask Suno's AI to write lyrics from a description, optionally guided by a template:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X POST "$FK/api/music/generate-lyrics" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a song about a cat astronaut exploring a candy planet",
    "template_id": "children_adventure",
    "poll": true
  }'
```

## Check Credits

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/music/credits" -H "$KEY"
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/music/templates` | GET | List all song templates |
| `/api/music/templates/{id}` | GET | Get template details |
| `/api/music/generate` | POST | Generate music (returns taskId, 2 clips) |
| `/api/music/tasks/{id}` | GET | Get task status + clips |
| `/api/music/tasks/{id}/poll` | POST | Poll task until complete |
| `/api/music/tasks/{id}/download` | POST | Download all clips to local |
| `/api/music/generate-lyrics` | POST | Generate lyrics from prompt |
| `/api/music/extend` | POST | Extend/continue existing track |
| `/api/music/vocal-removal` | POST | Separate vocals from instrumental |
| `/api/music/convert-to-wav` | POST | Convert clip to WAV format |
| `/api/music/credits` | GET | Check Suno credits/quota |

## Models

| Model | Max Duration | Notes |
|-------|-------------|-------|
| V4 | 4 min | Highest audio quality |
| V4_5 | 8 min | Superior genre blending |
| V4_5PLUS | 8 min | Richer sound |
| V4_5ALL | 8 min | Better song structure |
| V5 | 8 min | Faster generation |
| V5_5 | 8 min | Custom model tailoring |

Default: `V4` (set via `SUNO_MODEL` env var).

## Template → Suno Mapping

| Template Field | Suno API Field | Purpose |
|---------------|---------------|---------|
| `suno_tags` | `style` | Musical style descriptors |
| `example_lyrics` | `prompt` | Lyrics with section markers |
| `vocal_style` | (embedded in style) | Voice character |
| `bpm_range` | (embedded in style) | Tempo |

## Tips

- Each generation costs ~10 credits (5 per clip) and produces 2 variations
- Use `instrumental: true` for background music (no vocals)
- `poll: true` waits for completion (~30-120s) — use for scripted workflows
- `poll: false` returns immediately with taskId — use for interactive/async workflows
- For video background music, `cinematic_epic` or `cinematic_emotional` templates work well
- For children's content, use `lullaby_gentle`, `children_adventure`, or `nursery_rhyme`
- Generated files are stored by Suno for 15 days — download promptly

## Important Notes

- Suno generates ~2-8 min tracks (depends on model). For shorter clips, trim with ffmpeg
- Each generation creates 2 clip variations — listen and pick the best one
- Credits are per-account. Check `/api/music/credits` before batch generation
- The `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]` markers in lyrics control song structure
- Use `[Instrumental]`, `[Soft]`, `[Powerful]`, `[Whispered]` tags for dynamics
- Style field: max 200 chars (V4) or 1000 chars (V4.5+)
- Title field: max 80 chars (V4/V4_5ALL) or 100 chars (others)
- Prompt field: max 3000 chars (V4) or 5000 chars (V4.5+)
