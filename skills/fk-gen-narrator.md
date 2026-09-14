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

## Step 2: Check the TTS engine is ready

The server's `TTS_ENGINE` speaks the narration:

| `TTS_ENGINE` | Voice | Languages |
|--------------|-------|-----------|
| `gemini` (default) | Gemini TTS, needs `GEMINI_API_KEY` | Most, including Korean |
| `mindlogic` | The same Gemini voices through the Mindlogic API gateway (`MINDLOGIC_API_KEY`, billed in gateway credits) | Most, including Korean |
| `kokoro` | A self-hosted Kokoro-82M server (`KOKORO_URL`) | English, Spanish, French, Hindi, Italian, Portuguese (Japanese, Mandarin if the server has their extras) |

Each line goes to an engine that knows its language. A Korean or Khmer line under `kokoro` is spoken by
`TTS_FALLBACK_ENGINE` instead (Piper for Korean, gTTS for Khmer), and so is any line while
Gemini is out of quota or the Kokoro server is down. The reply's `engine` says which one spoke.

Probe with one short line:
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 120 -X POST "$FK/api/tts/generate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test.", "with_timings": false}'
```

- `500 ... GEMINI_API_KEY is not set` → **ABORT**. Tell the user to add `GEMINI_API_KEY=<key>` to `.env` (from https://aistudio.google.com/apikey) and restart the agent.
- `"engine"` is not the server's `TTS_ENGINE` → read `fallback_reason` (see **When the main engine can't speak** below). Tell the user before narrating the whole video. Probe with a line in the video's language, since routing depends on it.
- `429 ... no fallback engine is set` → wait for the quota to reset, or ask the admin to set `TTS_FALLBACK_ENGINE=piper,google`.
- `503 ... no engine in TTS_FALLBACK_ENGINE ... can` → no configured engine speaks this language; the admin adds `google` to `TTS_FALLBACK_ENGINE`.
- `503 ... the fallback voice failed too` → print the message; usually the admin needs `pip install piper-tts` on the server, or the Kokoro server is down.

### When the main engine can't speak

The server does not fail when `TTS_ENGINE` can't speak a line: Gemini out of quota (it then stops
calling Gemini until the limit resets, 1 hour for a daily quota), the Kokoro server down, or a
language the engine doesn't know. It narrates with `TTS_FALLBACK_ENGINE` (Piper, a free voice on the
server, then gTTS). Every reply says which engine spoke and why: `engine` and `fallback_reason` on
`/api/tts/generate`, `scenes[].engine` plus `fallback_scenes` on `/api/videos/<VID>/narrate`.

A fallback voice sounds different and ignores `voice` and `style`. When scenes come back with another engine:

1. Tell the user which scenes and why, e.g. "3 scenes were narrated with the free local voice: Gemini is out of quota."
2. If the reason is the language (`can't speak 'ko'`), that is permanent for this engine — every line in that language will use the fallback voice.
3. Otherwise ask whether to keep the fallback voice (fine for drafts) or redo those scenes later: call `/api/tts/generate`
   again for them, or narrate the whole video with `"redo_fallback": true` (only fallback scenes the main engine can speak are redone).

### Pick the voice

**With `TTS_ENGINE=kokoro`**, voices are Kokoro names whose first letter is the language. The server's
`KOKORO_VOICE` is the default; pass `voice` to change it. A voice for the wrong language is ignored.

Grades are Kokoro's own quality ratings (A best). Suggest the top ones:

| Voice | Accent, gender | Grade |
|-------|----------------|-------|
| `af_heart` | American, female | A (default) |
| `af_bella` | American, female | A- |
| `af_nicole` | American, female (soft, close to the mic) | B- |
| `bf_emma` | British, female | B- |
| `am_fenrir`, `am_michael`, `am_puck` | American, male | C+ |
| `af_aoede`, `af_kore`, `af_sarah` | American, female | C+ |
| `bm_george`, `bm_fable` | British, male | C |
| `ef_dora`, `ff_siwis` (B-), `if_sara`, `pf_dora`, `hf_alpha` | Spanish, French, Italian, Portuguese, Hindi | — |

Full list: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md. `style` does nothing on Kokoro.

**With `TTS_ENGINE=gemini` or `mindlogic`**, Gemini uses prebuilt voices — there is no voice template or `ref_audio` to prepare. Use `--voice` if given, otherwise ask the user, suggesting a few:

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

**Length: every line must fit the 8-second Veo clip.** Flow generates each scene as an 8s clip. The render drops the clip's static first second and keeps a 0.5s pause after the line, so the spoken narration gets **6.5s at most**:

```
8.0s Veo clip − 1.0s skipped head − 0.5s pause = 6.5s of speech
```

Write every line for this, whatever the scene's look & feel is today: a line that fits a Veo clip also fits a pan/zoom still, and the scene can switch to Veo later without re-voicing. Only write longer lines (up to ~15s) when the user has said explicitly that the scene stays a still.

**Length limits per line (HARD MAX — never exceed):**

Speaking speed depends on the voice. Kokoro and calm Gemini voices speak English at ~2.8 words/s, not 3.5, so these limits assume the slower voices:

| Language | Max per line | ~Speech | Notes |
|----------|--------------|---------|-------|
| English | 18 words | ≤6.5s | ~2.8 words/s (Kokoro, calm Gemini voices) |
| Korean | 18 words | ≤6.5s | Agglutinative, long compound words = fewer needed |
| Vietnamese | 18 words | ≤6.5s | Tonal, diacritics slow TTS. 1-2 punchy sentences |
| Japanese | 27 words | ≤6.5s | Short words, particles add up fast (は、を、に) |
| Thai | 20 words | ≤6.5s | Tonal like Vietnamese, no spaces between words |
| Chinese (ZH) | 23 characters | ≤6.5s | Each character = 1 syllable, very dense |
| Spanish | 20 words | ≤6.5s | Slightly faster than English |
| French | 20 words | ≤6.5s | Liaison makes speech flow faster |
| Arabic | 16 words | ≤6.5s | Long words, formal style = slower delivery |
| Hindi | 18 words | ≤6.5s | Compound verbs take time |
| Khmer | 75 Khmer characters | ≤6.5s | Count characters without spaces or punctuation (no spaces between words). Measured ~12.5 characters/s with Gemini Charon, brisk style, speed 1.1. Write numbers as words. 1-2 short sentences. |

**Rule of thumb for unlisted languages:** MAX 18 words. Adjust down for languages with long compound words (German, Finnish), adjust up for languages with short particles (Japanese, Chinese). Under ~10 words leaves dead air on a Veo scene.

These limits are estimates — the real length is measured after TTS, and **Step 6b is a required check** that every line is ≤6.5s.

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
- Exceed the length limit — every line must be spoken within 6.5s to fit the 8s Veo clip (too long = cut off mid-sentence)
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
  "timings_path": ".../tts/scene_003_<id>.words.json",
  "engine": "gemini",
  "fallback_reason": null
}
```

Check `engine` on every reply. `piper` means Gemini ran out of quota for this scene — follow **When Gemini runs out of quota** (Step 2).

**Run these one scene at a time** (the server allows 2 TTS jobs at once and Gemini preview models have low rate limits). This is a sequence of single calls, not a script loop over the batch API.

Alternative for short videos — one call for the whole video (same voice/style for every scene, skips wavs that already exist):
```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s -m 1800 -X POST "$FK/api/videos/<VID>/narrate" -H "$KEY" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "<PID>", "voice": "<VOICE>", "style": "<STYLE>", "mix": false}'
```

Add `"redo_fallback": true` to speak again only the scenes the local fallback voice made earlier.

### Key rules:
- Same `voice` + `style` for ALL scenes = consistent narration
- Always pass `scene_id` — the server then names the file `scene_{IDX3}_{scene_id}.wav`, which the render, the review board and subtitles all look for
- `--force` regenerates: pass the new text; if a wav already exists it is overwritten by `/api/tts/generate`
- `speed` other than 1.0 is applied with ffmpeg `atempo` after Gemini speaks; timings are measured on the final wav, so they stay correct
- **mix: false** — mixing happens in `/fk-concat-fit-narrator`

### 6b. Check every line fits the 8-second clip (required)

Do not move on to subtitles or `/fk-gen-videos` until every narrated scene is **≤6.5s**. Read the measured lengths from the plan:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/videos/<VID>/assembly-plan" -H "$KEY" | python -c "
import json,sys
for s in json.load(sys.stdin)['segments']:
    d = s.get('narration_duration') or 0
    print(f\"scene {s['display_order']+1:>3} {d:5.2f}s\", 'OK' if d <= 6.5 else 'TOO LONG for the 8s clip')"
```

For each `TOO LONG` scene:
1. Shorten the line (keep its meaning and names; cut filler, merge sentences). Show the user the old and new text with the old length.
2. Save it (Step 4) and regenerate **only that scene** (Step 6a).
3. Check again. Repeat until every scene is ≤6.5s.

Only if the user refuses to shorten a line: give that scene a fixed length of narration + 0.5s in its look & feel (`look_feel.duration`). The render then plays its Veo clip in slow motion to fit, down to 60% speed (a Veo scene can reach ~11.6s at most). Say which scenes will play slower.

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
  Fallback voice: F scene(s) spoken by the local voice (Gemini out of quota) — omit when 0
  Output: on the server, output/<project>/tts/
  Subtitles: captions.srt (C cues)

  Next step: /fk-review-board — set look & feel (Veo or ffmpeg, motion, transitions)
  Then: /fk-gen-videos, /fk-concat-fit-narrator <video_id>
  Note: Interview scenes keep original video audio (no narrator overlay).
```

Every narrated scene must be ≤6.5s so it fits its 8-second Veo clip. If any scene is longer, go back to Step 6b before finishing — never hand over narration that will be cut off.

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
| `engine: "piper"` in replies | Gemini quota or rate limit used up; the free local voice took over | Keep it for a draft, or redo those scenes later with `redo_fallback: true` |
| `HTTP 429` / `out of quota` error | Quota used up and `TTS_FALLBACK_ENGINE=none` | Wait for the reset, or admin sets `TTS_FALLBACK_ENGINE=piper` |
| `the fallback voice failed too` | Piper isn't installed, or no local voice for the language | Admin runs `pip install piper-tts`; for other languages set `PIPER_VOICE` |
| `No audio in Gemini response ... SAFETY` | Line blocked by safety filters | Rephrase the narrator text (graphic violence, real names) |
| Voice changes between scenes | Different `voice`/`style` per call | Use the same voice and style everywhere |
| Style text is spoken aloud | Style not phrased as an instruction | Start with "Say ..." / "Speak ..." and keep it short |
| `timing_source: estimated` | Timing call failed | Check `timing_error`; captions still work at sentence level |
| Narration cut off in final video | Narration > 6.5s does not fit the 8s Veo clip (1s head skipped, 0.5s pause) | Step 6b: shorten the line and regenerate that scene; or give the scene a fixed look & feel length so the clip plays slower |
| Narration not found by the render | Generated without `scene_id` | Re-run `/api/tts/generate` for that scene with `scene_id` |
| Narrator describes visuals | Bad writing style | Remove "we see", describe context/stakes instead |
| Want a free voice all the time | — | Set `TTS_ENGINE=piper` (local) or `TTS_ENGINE=google` (gTTS) in `.env`; word timings still come from Gemini if a key is set |
