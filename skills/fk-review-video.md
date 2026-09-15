Review AI-generated scene videos for quality with a vision model.

Usage: `/fk-review-video <video_id> [--mode light|deep] [--provider claude|agy]`

Default mode: `light`. The server turns each scene's clip into timestamped contact sheets; a vision model scores them. **Who does the vision analysis:**

1. **Your own AI agent (preferred)** — the agent running this skill (Claude Code, Codex, Gemini CLI, ...) looks at the contact sheets itself and sends its JSON back. Uses your agent, not the server.
2. **The host's CLI (fallback)** — when your agent cannot view images, the server runs `claude` or `agy` on its own machine.

## Connection

These commands work against a local agent or a shared server. The Flow Kit
installer (`<server>/install.sh` or `install.ps1`) writes `~/.flowkit/env` with
`FLOWKIT_URL` and `FLOWKIT_API_KEY`; without that file they default to
`http://127.0.0.1:8100` and no key. Shell state does not carry
over between commands, so **start every command with this line**:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
```

## Prerequisites

- Scenes must have completed videos (`${ori}_video_status = COMPLETED`). Pan/zoom (ffmpeg) scenes have no Veo clip and are skipped.
- Signed video links expire after a few hours — run `/fk-refresh-urls` first if the videos are old.
- No API key is needed for either path.

## Step 1: Pre-check

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"                 # project_id → <PID>, orientation → ${ORI}
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"        # which scenes have a completed ${ori} video
```

**ABORT** if the video is not found. List scenes without a completed video and tell the user to run `/fk-gen-videos` for them; review the rest.

## Step 2: Choose who analyses

- **Your agent can view image files** (e.g. Claude Code's Read tool opens a `.jpg`) and the user did not pass `--provider` → **Step 3A**.
- Otherwise → **Step 3B** with the host CLI. Check what the host has installed:

  ```bash
  . ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
  curl -s "$FK/api/providers" -H "$KEY"
  ```

  Use `--provider` if given, else `claude` if `installed`, else `agy`. If neither is installed, stop and tell the user a vision-capable agent is needed for Step 3A.

## Step 3A: Review with your own agent

**1. Prepare** — the server downloads each clip and makes its contact sheets (all scenes at once, or one scene with `.../scenes/<SID>/review/prepare`):

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 900 -X POST "$FK/api/videos/<VID>/review/prepare?project_id=<PID>&mode=light&orientation=${ORI}" -H "$KEY" > review_jobs.json
```

Response: `{"reviews": [{"review_id", "scene_id", "display_order", "n_frames", "fps", "sheet_count", "prompt", "sheets": ["/api/videos/<VID>/reviews/<RID>/sheets/1.jpg", ...], "result_url"}], "skipped": [{"scene_id", "reason"}]}`.

**2. For each review, one scene at a time:**

a. Download its sheets into a scratch folder, in order:
   ```bash
   . ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
   curl -sfL "$FK<sheets[i]>" -H "$KEY" -o "scene_<display_order+1>_sheet_<i>.jpg"
   ```
b. **Look at every sheet yourself**, earliest first (each cell is a frame, timestamp in its corner).
c. Follow that review's `prompt` exactly and write **only** the JSON it asks for: `dimensions` (six 0–10 scores), `errors` (`severity`, `time_range`, `description`) and `usable_segments`. Judge honestly from the frames — do not guess scores for frames you did not see.
d. Send it back; the server scores it the same way as a host review:
   ```bash
   . ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
   curl -s -X POST "$FK<result_url>" -H "$KEY" -H "Content-Type: application/json" -d @scene_analysis.json
   ```
   Your full text reply also works: `{"raw": "<reply with the JSON in it>"}`. A `400` means the JSON could not be read — fix it and post again. A `404` means the review expired (24h) or was already scored — prepare it again.

The reply is that scene's `SceneReview` (Step 4). Delete the downloaded sheets when done.

## Step 3B: Review on the host CLI

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 1800 -X POST "$FK/api/videos/<VID>/review?project_id=<PID>&mode=light&orientation=${ORI}&provider=<claude|agy>" -H "$KEY"
```

One call reviews every scene and waits for all of them (about a minute per scene). For one scene use `POST $FK/api/videos/<VID>/scenes/<SID>/review?...&provider=...`. Add `&scene_ids=<SID1>,<SID2>` to review a subset. Leaving out `provider` uses the server's default (`/fk-change-provider`, admin only).

- `400 ... not installed on this server` → pick an installed provider, or use Step 3A.
- `500 Review failed: ... CLI timed out` → review scenes one at a time.

## Step 4: Interpret results

Each scene review (Step 3A per scene; Step 3B returns `{"overall_score", "verdict", "scene_reviews": [...], "scenes_reviewed", "scenes_skipped"}`):

```json
{
  "scene_id": "abc-123",
  "overall_score": 8.1,
  "verdict": "good",
  "dimensions": {
    "character_consistency": 8.0, "prompt_adherence": 7.0, "motion_quality": 9.0,
    "visual_fidelity": 8.0, "temporal_coherence": 8.0, "composition": 7.0
  },
  "errors": [{"severity": "MINOR", "time_range": "2s-3s", "description": "prop count changes"}],
  "usable_segments": [{"time_range": "0s-8s", "score": 8.0}],
  "fix_guide": "Edit video_prompt camera directions, then regenerate",
  "frames_analyzed": 32,
  "fps_used": 4.0,
  "has_critical_errors": false
}
```

### Scoring Dimensions

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Character Consistency | 25% | Characters match refs across frames |
| Prompt Adherence | 20% | Video matches prompt description |
| Motion Quality | 20% | Smooth motion, no artifacts |
| Visual Fidelity | 15% | Resolution, clarity, no banding |
| Temporal Coherence | 10% | Consistent lighting/shadows across frames |
| Composition | 10% | Framing matches camera direction |

`overall_score = sum(dimension_score * weight)`

### Verdict Scale

| Score | Verdict | Action |
|-------|---------|--------|
| 9.0–10.0 | Excellent | Ship as-is |
| 7.5–8.9 | Good | Usable, minor polish optional |
| 6.0–7.4 | Acceptable | Cut usable segments, regen weak parts |
| 4.0–5.9 | Poor | Regen scene image first, then video |
| 0–3.9 | Unusable | Rewrite prompt + regen from scratch |

Any `CRITICAL` error caps `character_consistency` at 3.0 and `overall_score` at 5.9 (`has_critical_errors: true`). See **Known AI Video Errors** below.

## Step 5: Act on results

### Poor / Unusable scenes
Regenerate the scene image first, then the video:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/requests" -H "$KEY" -H "Content-Type: application/json" \
  -d '{"type": "REGENERATE_IMAGE", "scene_id": "<SID>", "project_id": "<PID>", "video_id": "<VID>", "orientation": "'"${ORI}"'"}'
```
Then run `/fk-gen-videos <PID> <VID>` after the image is complete.

### Acceptable with good segments
Note `usable_segments` time ranges; set the scene's length or trim in `/fk-review-board`.

### Character drift (low `character_consistency`)
- Verify all entity ref images have `media_id` (UUID format)
- Use `EDIT_IMAGE` to re-anchor character appearance (same call as above with `"type": "EDIT_IMAGE"`).

### After fixes
Review the regenerated scenes again, with `mode=deep` before final export.

## Modes

- **light** (default): 4 frames/second → 32 frames per 8s video. Fast, good for initial scan to identify problem scenes.
- **deep**: 8 frames/second → 64 frames per 8s video. Thorough, catches subtle artifacts and motion issues. Use before final export.

## Output Summary

Print a table after review completes (number scenes from 1, as the dashboard does):

```
Scene | Score | Verdict    | Errors | Usable Segments        | Analysed by
------|-------|------------|--------|------------------------|------------
1     | 8.5   | good       | 1      | 0s-4s(9.0), 5s-8s(8.5) | own agent
2     | 6.2   | acceptable | 2      | 3s-5s(7.0)             | own agent
3     | 3.8   | unusable   | 5      | none                   | own agent
...
Total: 6.9/10 | 3 scenes reviewed | 0 skipped
```

Then print recommended actions:
- Excellent/Good → "Ready for `/fk-concat-fit-narrator <VID>`"
- Acceptable → "Note usable segments, trim in post"
- Poor/Unusable → "Run `/fk-gen-images <PID> <VID>` to regenerate, then `/fk-gen-videos <PID> <VID>`"

## Known AI Video Errors

Battle-tested error catalog. The vision model reports these in `errors`, each with its `severity`.

### CRITICAL (Auto-fail, score 0–3)

| # | Error | Description | When it happens |
|---|-------|-------------|-----------------|
| 1 | Character Drift | Character morphs mid-video (extra limbs, breed changes) | Common after 3–4s |
| 2 | Breed Swap | Similar characters get mixed up | Common in multi-character scenes |
| 3 | Role Reversal | Wrong character performs the action | ~50% of action scenes |
| 4 | Brand Logo | AI generates real brand logos | Any scene with objects/signage |
| 5 | Character Count | Wrong number of characters rendered | Crowd or paired scenes |

Any CRITICAL error → scene scores 0–3.9 (Unusable). Rewrite prompt + regen from scratch.

### HIGH (Needs trim/regen, score 4–6)

| # | Error | Description | When it happens |
|---|-------|-------------|-----------------|
| 6 | Camera Drift | Sudden unwanted zoom or rotation | ~60% of scenes after 4s |
| 7 | Object Morph | Held items change shape mid-video | Action scenes with props |
| 8 | Reverse Motion | Character does then undoes the action | ~30% of motion scenes |
| 9 | Human Hands | Anthropomorphic characters get human hands | Animal/creature characters |
| 10 | Scale Break | Characters change size relative to environment | Dynamic movement scenes |

HIGH errors → note `usable_segments` before the error timestamp. Trim or regen.

### MINOR (Acceptable, score 7–8)

| # | Error | Description |
|---|-------|-------------|
| 11 | Prop Count | Small props change in number |
| 12 | Clothing Detail | Texture or pattern shifts |
| 13 | Background Blur | Garbled signage or background text |
| 14 | Accessory Loss | Small items (earrings, accessories) appear/disappear |

MINOR errors → acceptable for most use cases. Polish optional.

### Prevention Patterns

| Issue | Fix |
|-------|-----|
| Character drift | Simpler prompts, add "steady camera, minimal movement" |
| Breed swap | Use high color contrast between similar characters |
| Character count | ONE dominant character, others in background |
| Reverse motion | Regen video (luck-based, different seed) |
| Brand logos | Add "no brand logos, no text" to prompt |
| Camera drift | Add "static camera" or "locked-off shot" to video_prompt |
| Human hands | Add "paws, claws, hooves" (or correct anatomy) to prompt |

## Cost Note

- **Own agent (Step 3A):** uses your agent's own model and quota; the server only makes contact sheets (a few seconds per scene).
- **Host CLI (Step 3B):** uses the host's `claude`/`agy` account — one call per scene.
- Deep mode sends twice the frames of light mode. Review light first, then deep only on scenes flagged as poor/acceptable.
