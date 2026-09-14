# fk-gen-narrator — Generate Narrator Text + TTS for All Scenes

Auto-generate documentary-style narrator text from scene video_prompts, speak it with Gemini TTS, and time every word for subtitles.

Usage: `/fk-gen-narrator <video_id> [--force] [--language ko] [--voice Kore] [--style "..."] [--speed 1.0]`

Produces, per narrated scene, on the server (`output/<project>/tts/`):
- `scene_{IDX3}_{scene_id}.wav` — the narration
- `scene_{IDX3}_{scene_id}.words.json` — word timings (`word`, `start`, `end` in seconds)

Everything is generated and stored by the agent, so this works from another computer too.

Then feeds `/fk-review-board` (narration length sets each scene's length) and `/fk-concat-fit-narrator`.

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

## Step 1: Load project, video, scenes

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>" -H "$KEY"
curl -s "$FK/api/projects/<PID>" -H "$KEY"
curl -s "$FK/api/scenes?video_id=<VID>" -H "$KEY"
```

Note: project name, language, story context.
Sort scenes by `display_order`.

### Classify scenes: cinematic vs interview

Detect interview scenes by checking if the scene's `prompt` contains "interview" (case-insensitive) or if `character_names` includes "Documentary Interview Studio" or similar interview-setting entities.

- **Cinematic scenes** → generate narrator TTS (voiceover describing action/context)
- **Interview scenes** → **SKIP narrator entirely** — these scenes keep their original video audio (the character "speaks" naturally). No narrator_text, no TTS file.

Print classification:
```
Scene 00 [INTERVIEW] The Surgeon — skip narrator
Scene 01 [CINEMATIC] JSA Checkpoint — will narrate
Scene 02 [CINEMATIC] North Korean Barracks — will narrate
...
Interview scenes (skipped): N
Cinematic scenes (will narrate): M
```

## Step 2: Check Gemini TTS is ready

Narration uses **Gemini TTS** (`TTS_ENGINE=gemini`, the default). It needs `GEMINI_API_KEY` in `.env`.

Probe with one short line:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 120 -X POST "$FK/api/tts/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test.", "with_timings": false}'
```

- `500 ... GEMINI_API_KEY is not set` → **ABORT**. Tell the user to add `GEMINI_API_KEY=<key>` to `.env` (from https://aistudio.google.com/apikey) and restart the agent.
- `500 ... HTTP 429` → rate limited; wait a minute and retry, or lower `GEMINI_TTS_CONCURRENCY`.

### Pick the voice

Gemini uses prebuilt voices — there is no voice template or `ref_audio` to prepare. Use `--voice` if given, otherwise ask the user, suggesting a few:

| Voice | Character |
|-------|-----------|
| `Kore` | Firm, clear (default) |
| `Charon` | Informative, steady — good documentary narrator |
| `Fenrir` | Excitable, energetic |
| `Orus` | Firm, deeper |
| `Aoede` | Breezy, warm |
| `Puck` | Upbeat |
| `Enceladus` | Breathy, intimate |
| `Gacrux` | Mature |

(30 voices total — any name from the Gemini TTS voice list works.) Gemini detects the language from the text, so the same voice works for English and Korean.

**Use the SAME voice and style for every scene** — that is what keeps the narration consistent.

### Style (optional)

`--style` is a delivery direction Gemini reads before the line, e.g.:
- `Say as a calm, authoritative documentary narrator`
- `Say with rising tension, brisk pace`
- `차분하고 신뢰감 있는 다큐멘터리 내레이터 톤으로 말하세요`

Keep it short and phrased as an instruction; it is not spoken aloud.

## Step 3: Generate narrator text for each scene

For each scene (sorted by display_order):

### Skip logic:
- If scene is classified as **INTERVIEW** → always skip (no narrator for interview scenes)
- If scene already has `narrator_text` AND not --force → skip

### Read the scene's `video_prompt` and `prompt`

The `video_prompt` describes what happens in the 8s video (sub-clip timing).
The `prompt` describes the still image (frame 0).
The project `story` provides overall narrative context.

### Generate narrator_text following these rules:

**Language:** Use `--language` flag or project's `language` field.

**Length depends on how the scene will be rendered** (set in `/fk-review-board` → Look & feel):

- **Veo scenes** (default) — the clip is 8s, and `/fk-concat-fit-narrator` skips its first second, so narration must fit in **~6.5s**. Use the word limits below.
- **ffmpeg scenes** — the scene is rendered from the keyframe and runs as long as the narration. Lines can be longer (up to ~15s), but keep them punchy.

If the user hasn't chosen yet, write for Veo — a short line fits either mode.

**Word count limits for Veo scenes (HARD MAX — never exceed):**

| Language | Max Words | ~Duration | Words/sec | Notes |
|----------|-----------|-----------|-----------|-------|
| English | 22 | ~6.5s | ~3.5 | Standard baseline |
| Korean | 22 | ~6.5s | ~3.5 | Agglutinative, long compound words = fewer needed |
| Vietnamese | 22 | ~6.5s | ~3.5 | Tonal, diacritics slow TTS. 2-3 punchy sentences |
| Japanese | 33 | ~6.5s | ~5.0 | Short words, particles add up fast (は、を、に) |
| Thai | 24 | ~6.5s | ~3.8 | Tonal like Vietnamese, no spaces between words |
| Chinese (ZH) | 28 | ~6.5s | ~4.3 | Each character = 1 syllable, very dense |
| Spanish | 24 | ~6.5s | ~3.8 | Slightly faster than English |
| French | 24 | ~6.5s | ~3.8 | Liaison makes speech flow faster |
| Arabic | 20 | ~6.5s | ~3.0 | Long words, formal style = slower delivery |
| Hindi | 22 | ~6.5s | ~3.5 | Compound verbs take time |

**Rule of thumb for unlisted languages:** MAX 22 words. Adjust down for languages with long compound words (German, Finnish), adjust up for languages with short particles (Japanese, Chinese). Under ~15 words leaves dead air on a Veo scene.

Actual durations are measured after TTS (Step 6) — the review board flags any Veo scene whose narration is longer than its clip.

**Documentary narrator style:**

DO:
- Add context the viewer CAN'T see: historical facts, stakes, motivations
- Add emotion and tension: "One wrong move — and it's war"
- Use short punchy sentences, varied rhythm
- Build narrative arc across scenes (setup → rising → climax → resolution)
- Match the story's genre and tone
- Reference character names from the scene's `character_names`
- End sentences with punctuation — subtitles break cues at `.`, `!`, `?`

DON'T:
- Describe what's visually obvious: "We see a ship sailing" (viewer sees it)
- Use filler phrases: "In this scene...", "Meanwhile...", "As we can see..."
- Exceed the word count on a Veo scene (too long = cut off mid-sentence)
- Use passive voice: "The ship was attacked" → "Iran attacked the ship"

### Example (military documentary, English):

Scene video_prompt: `0-3s: Captain Harris stands on the bridge scanning the horizon. 3-6s: Radar shows multiple fast contacts approaching. 6-8s: Captain grabs radio and orders battle stations.`

narrator_text: `Colonel Harris detects unusual radar signatures. Dozens of Iranian fast boats racing toward the convoy.`
(15 words, ~5s — adds Iran context, punchy)

### Example (military documentary, Korean):

narrator_text: `해리스 대령이 이상한 레이더 신호를 포착합니다. 수십 척의 이란 고속정이 호송대를 향해 돌진합니다.`
(13 words, ~5.5s — same context, natural Korean documentary register)

## Step 4: Save narrator_text to each scene

For each scene with generated text:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -X PATCH "$FK/api/scenes/<SID>" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"narrator_text": "<generated_text>"}'
```

## Step 5: Show all narrator texts for review

Print a table:

```
Scene | Words | Est. Duration | Narrator Text
------|-------|---------------|---------------
  000 |    15 |         5.0s  | Colonel Harris detects unusual radar...
  001 |    18 |         6.0s  | The tanker Meridian Star pushes...
  ...
Total: 40 scenes, ~700 words, ~230s narration
```

Ask user: "Review OK? Type 'yes' to generate TTS, or 'edit N' to modify scene N's text."

## Step 6: Generate TTS + word timings for all scenes

### 6a. Generate per scene (via `/api/tts/generate`)

Per-scene calls are the reliable path for long videos. Each call speaks the line **and** times its words (a second Gemini call). Pass the `scene_id` and the server saves the wav and its `.words.json` sidecar where the review board, subtitles and the final render look for them.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# for each narrated scene
curl -s -m 300 -X POST "$FK/api/tts/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<scene_narrator_text>",
    "voice": "<VOICE>",
    "style": "<STYLE or omit>",
    "speed": 1.0,
    "scene_id": "<SID>"
  }'
```

Response:
```json
{
  "audio_path": ".../tts/scene_003_<id>.wav",
  "duration": 5.42,
  "words": [{"word": "Colonel", "start": 0.08, "end": 0.51}, ...],
  "timing_source": "gemini",
  "timings_path": ".../tts/scene_003_<id>.words.json"
}
```

**Run these one scene at a time** (the server allows 2 TTS jobs at once and Gemini preview models have low rate limits). This is a sequence of single calls, not a script loop over the batch API.

Alternative for short videos — one call for the whole video (same voice/style for every scene, skips wavs that already exist):
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 1800 -X POST "$FK/api/videos/<VID>/narrate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<PID>", "voice": "<VOICE>", "style": "<STYLE>", "mix": false}'
```

### Key rules:
- Same `voice` + `style` for ALL scenes = consistent narration
- Always pass `scene_id` — the server then names the file `scene_{IDX3}_{scene_id}.wav`, which the render, the review board and subtitles all look for
- `--force` regenerates: pass the new text; if a wav already exists it is overwritten by `/api/tts/generate`
- `speed` other than 1.0 is applied with ffmpeg `atempo` after Gemini speaks; timings are measured on the final wav, so they stay correct
- **mix: false** — mixing happens in `/fk-concat-fit-narrator`

### `timing_source`
- `gemini` — timings from Gemini's audio model, mapped onto the script's own words (subtitles always show the written text)
- `estimated` — the timing call failed (reason in `timing_error`); words are spread across the audio by length. Fine for sentence-level captions. To retry, re-run `/api/tts/generate` for that scene.

## Step 7: Build subtitles

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -X POST "$FK/api/videos/<VID>/subtitles" -H "$KEY" \
  -H "Content-Type: application/json" -d '{}'
```

Writes scene-local SRTs and a whole-video `captions.srt` on the server (`output/<project>/subtitles/`). Cues break at sentence ends, ~42 characters (English) or ~20 (Korean), and 4 seconds. Override with `{"max_chars": 30}`.

`captions.srt` is placed on the current assembly plan. After changing look & feel (lengths, transitions) in `/fk-review-board`, `/fk-concat-fit-narrator` rebuilds it — no need to re-run here.

## Step 8: Verify and output

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/assembly-plan" -H "$KEY"
curl -s "$FK/api/videos/<VID>/captions.srt" -H "$KEY" | head -20
```

In the plan, count the segments with a `narration_path` (should match the narrated scenes) and with a `timings_path` (same count).

Print:
```
Narrator generation complete: <project_name>
  Cinematic scenes narrated: N/M
  Interview scenes (skipped): K
  Language: Korean
  Voice: Charon  (Gemini TTS, gemini-3.1-flash-tts-preview)
  Style: "Say as a calm documentary narrator"
  Total narration: XXXs
  Word timings: N gemini, K estimated
  Output: on the server, output/<project>/tts/
  Subtitles: captions.srt (C cues)

  Next step: /fk-review-board — set look & feel (Veo or ffmpeg, motion, transitions)
  Then: /fk-gen-videos, /fk-concat-fit-narrator <video_id>
  Note: Interview scenes keep original video audio (no narrator overlay).
```

Warn about any Veo scene whose narration duration is > 6.5s — it will be cut off unless the scene is switched to ffmpeg or the line is shortened.

## Narrative Arc Guide

When writing narrator text for 30-40 scenes, follow a narrative arc:

| Phase | Scenes | Tone | Example |
|-------|--------|------|---------|
| **Setup** | 1-5 | Calm, informative | "The Strait of Hormuz — a lifeline for the world's oil..." |
| **Rising** | 6-15 | Building tension | "Radar picks up signals that shouldn't be there..." |
| **Climax** | 16-25 | Intense, urgent | "Iran strikes! Dozens of boats race toward the convoy!" |
| **Resolution** | 26-35 | Relief, reflection | "The convoy clears the strait intact..." |
| **Epilogue** | 36-40 | Reflective, closing | "Operation Hormuz Shield — a lesson in deterrence." |

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `GEMINI_API_KEY is not set` | Key missing from `.env` | Add it, restart the agent |
| `HTTP 429` | Gemini rate limit | Generate scenes one at a time; lower `GEMINI_TTS_CONCURRENCY`; wait and retry |
| `No audio in Gemini response ... SAFETY` | Line blocked by safety filters | Rephrase the narrator text (graphic violence, real names) |
| Voice changes between scenes | Different `voice`/`style` per call | Use the same voice and style everywhere |
| Style text is spoken aloud | Style not phrased as an instruction | Start with "Say ..." / "Speak ..." and keep it short |
| `timing_source: estimated` | Timing call failed | Check `timing_error`; captions still work at sentence level |
| Narration cut off in final video | Veo scene narration > 6.5s | Shorten the line, or set the scene to ffmpeg in `/fk-review-board` |
| Narration not found by the render | Generated without `scene_id` | Re-run `/api/tts/generate` for that scene with `scene_id` |
| Narrator describes visuals | Bad writing style | Remove "we see", describe context/stakes instead |
| Want the old free voice | — | Set `TTS_ENGINE=google` in `.env` (gTTS, word timings still come from Gemini if a key is set) |
