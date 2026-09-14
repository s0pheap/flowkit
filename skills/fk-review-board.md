Open the Scene Review Board for a video: watch every scene, tag it, write notes, and set each scene's look & feel.

Usage: `/fk-review-board [<video_id>]`

The board is a web page served by the agent at `<FLOWKIT_URL>/review-board`, so it works from any computer. In the board you can:
- See all scenes grouped by chain
- Play scene videos inline
- Tag scenes Good / Redo / Skip and write notes per scene (saved on the server, per video)
- **Set each scene's Look & feel** — Veo or ffmpeg, pan/zoom, transition, length (saved straight to the scene)
- Export the feedback as JSON

### Where it sits in the pipeline

```
/fk-gen-images → /fk-gen-narrator → /fk-review-board (look & feel) → /fk-gen-videos → /fk-concat-fit-narrator
```

Run it **after narration** so each scene's length can follow its narration, and **before `/fk-gen-videos`** so ffmpeg scenes never go to Veo. Use it again after videos exist for Good / Redo / Skip feedback.

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

## Steps

### 1. Resolve the `video_id`

a. **Explicit arg** — use the `<video_id>` the user passed.

b. **Active project** — otherwise:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/active-project" -H "$KEY"
```
Use its `video_id` and `project_name`.

c. **Nothing active** — list projects and ask the user to pick one, then set it:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects" -H "$KEY"
curl -s -X PUT "$FK/api/active-project" -H "$KEY" -H "Content-Type: application/json" -d '{"project_id": "<PID>"}'
```

If there is still no video, stop: "No active project. Run /fk-switch-project <PID> first."

### 2. Open the board

The URL is `$FK/review-board?video_id=<VID>`. Open it in the user's browser:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"
URL="$FK/review-board?video_id=<VID>"
open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || cmd.exe /c start "" "$URL" 2>/dev/null || echo "Open: $URL"
```

The board uses the API key the browser signed in with on the dashboard (same address). If the user has not signed in there yet, the board asks for the key once.

### 3. Tell the user

```
Review Board: <URL>
- Project:  <project_name>
- Video ID: <VID>
- Feedback and look & feel are saved on the server as you work.
```

## Look & feel panel

Selecting a scene shows a **Look & feel** panel under its prompts. Every change auto-saves to `PATCH /api/scenes/<SID>` as `look_feel`:

| Control | Values | Effect |
|---------|--------|--------|
| Mode | **Veo** / **ffmpeg** | Veo animates the keyframe (costs a generation). ffmpeg renders a pan/zoom of the keyframe on the server — no Flow call, no cost. |
| Motion | Static, Zoom in/out, Pan left/right, Tilt up/down | ffmpeg: the actual move. Veo: appended to the video prompt as `Camera direction: ...` |
| Strength | Subtle / Medium / Strong | How far the move travels |
| Transition to next | Cut, Crossfade, Fade through black/white, Dissolve, Wipe, Slide, Smooth, Circle open, Zoom in | Applied in the final render (ffmpeg `xfade`) |
| Transition (s) | 0.1–2.0 | Overlap length, capped at half of either scene |
| Length | Follow narration / fixed seconds | Default = narration + 0.5s. Veo scenes can't run past their 7s usable clip |

- **Preview motion** renders a low-res preview of the move and plays it (for Veo scenes it is a reference for the camera direction).
- **Apply to all scenes** copies mode, motion, strength and transition to every scene; lengths stay per scene.
- The header shows planned runtime and the Veo / ffmpeg split; each card shows its mode, motion, transition and length.
- The panel warns when a Veo scene's narration is longer than its clip — switch it to ffmpeg or shorten the line.

The same timeline is available to other skills:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/assembly-plan" -H "$KEY"   # per-scene start, duration, transition, source clip
curl -s "$FK/api/look-feel/options" -H "$KEY"                # allowed values
```

To set look & feel without the board (e.g. when the user describes it in chat):
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X PATCH "$FK/api/scenes/<SID>" -H "$KEY" -H "Content-Type: application/json" \
  -d '{"look_feel": {"mode": "ffmpeg", "motion": "zoom_in", "strength": "medium", "transition": "fade", "transition_duration": 0.5, "duration": null}}'
```

## After feedback

When the user says they are done reviewing, read the saved feedback:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/review-feedback" -H "$KEY"
# {"<scene_id>": {"rating": "good" | "redo" | "skip", "text": "...", "history": [...]}, ...}
```

- `good` / `skip` → no action
- `redo` → read the note: a new picture means `REGENERATE_IMAGE`, a new motion means `REGENERATE_VIDEO`, a small change to the picture means `EDIT_IMAGE` (ask for the edit prompt). Update the scene's prompts from the note first when it asks for different content.

Use `/fk-gen-images` or `/fk-gen-videos` for the actual regeneration.

Look & feel needs no follow-up — it is already saved on the scenes. Next run `/fk-gen-videos` (Veo scenes generate, ffmpeg scenes render) and `/fk-concat-fit-narrator`.
