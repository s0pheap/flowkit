# fk-gen-narrator — Generate Narrator Text + TTS for All Scenes

Auto-generate documentary-style narrator text from scene video_prompts, then generate TTS audio using a voice template.

Usage: `/fk-gen-narrator <video_id> [--force] [--language vi] [--speed 1.1]`

Prepares audio for `/fk-concat-fit-narrator`.

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

## Step 2: Check voice template

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/tts/templates" -H "$KEY"
```

If NO templates exist:
```
No voice template found. Run /fk-gen-tts-template first to create one.
Voice consistency requires a template — without it, each scene sounds different.
```
**ABORT** — do not proceed without a voice template.

If templates exist, list them and ask user which to use (or default to the first one).

Also check for YouTube channel voice templates:
```bash
# Check YouTube channel for voice files (preferred source for channel-specific voice)
ls youtube/channels/*/voice_template*.wav 2>/dev/null
# Check shared templates
ls output/_shared/tts_templates/*.wav 2>/dev/null
```

**Priority:** YouTube channel voice template > shared template > user-specified ref_audio.
User can specify a template name OR a ref_audio path directly.

## Step 3: Generate narrator text for each scene

For each scene (sorted by display_order):

### Skip logic:
- If scene is classified as **INTERVIEW** → always skip (no narrator for interview scenes)
- If scene already has `narrator_text` AND not --force → skip

### Read the scene's `video_prompt` and `prompt`

The `video_prompt` describes what happens in the generated clip (sub-clip timing).
The `prompt` describes the still image (frame 0).
The project `story` provides overall narrative context.

### Generate narrator_text following these rules:

**Language:** Use `--language` flag or project's `language` field.

**CRITICAL: Narrator MUST be shorter than the clip — and the clip is not always 8s.**

Read the clip length from the project first; do not assume it:

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects/<PID>" -H "$KEY"
```

`effective_video_model_family` says which model makes the clip and
`video_clip_seconds` says how long it is. The render skips the clip's static
first second (`-ss 1`) and keeps a 0.5s pause after the line, so:

```
MAX_SPEECH = video_clip_seconds − 1.0 skipped head − 0.5 pause

Veo          8s clip  → 6.5s of speech
Omni Flash  10s clip  → 8.5s of speech     ← the server default
```

**Omni Flash is the default on this server, so the usual budget is 8.5s, not
6.5s.** Writing every line to 6.5s wastes almost a third of every scene and is a
common reason narration feels clipped and the story feels rushed.

**Word count limits (HARD MAX — never exceed).** Use the column for the project's
model family. Kokoro and the calmer Gemini voices speak English at ~2.8 words/s
rather than 3.5, so these assume the slower voices:

| Language | Veo (≤6.5s) | Omni Flash 10s (≤8.5s) | Notes |
|----------|-------------|------------------------|-------|
| English | 18 words | 23 words | ~2.8 words/s on the calm voices |
| Vietnamese | 18 words | 23 words | Tonal, diacritics slow TTS. 1-2 punchy sentences |
| Korean | 18 words | 23 words | Agglutinative, long compound words = fewer needed |
| Japanese | 27 words | 35 words | Short words, particles add up fast (は、を、に) |
| Thai | 20 words | 26 words | Tonal like Vietnamese, no spaces between words |
| Chinese (ZH) | 23 characters | 30 characters | Each character = 1 syllable, very dense |
| Spanish | 20 words | 26 words | Slightly faster than English |
| French | 20 words | 26 words | Liaison makes speech flow faster |
| Arabic | 16 words | 21 words | Long words, formal style = slower delivery |
| Hindi | 18 words | 23 words | Compound verbs take time |
| Khmer | 75 Khmer characters | 98 Khmer characters | Count characters without spaces or punctuation (Khmer has no spaces between words). ~12.5 characters/s with Gemini Charon, brisk style, speed 1.1. Write numbers as words |

**Why strict?** The clip is a fixed length, so anything past MAX_SPEECH is cut
off mid-sentence. Well under it leaves dead air — below about 10 words (13 on
Omni) a generated scene sits silent at the end.

**Rule of thumb for unlisted languages:** MAX 18 words (23 on Omni). Adjust down
for languages with long compound words (German, Finnish), up for those with short
particles (Japanese, Chinese).

**Documentary narrator style:**

DO:
- Add context the viewer CAN'T see: historical facts, stakes, motivations
- Add emotion and tension: "One wrong move — and it's war"
- Use short punchy sentences, varied rhythm
- Build narrative arc across scenes (setup → rising → climax → resolution)
- Match the story's genre and tone
- Reference character names from the scene's `character_names`

DON'T:
- Describe what's visually obvious: "We see a ship sailing" (viewer sees it)
- Use filler phrases: "In this scene...", "Meanwhile...", "As we can see..."
- Exceed word count (too long = cut off mid-sentence when the clip ends)
- Be too short (< 18 words = dead air, awkward silence)
- Use passive voice: "The ship was attacked" → "Iran attacked the ship"

### Example (military documentary, Vietnamese):

Scene video_prompt (a 10s Omni clip, so the sub-clip timings run to 10): `0-3s: Captain Harris stands on the bridge scanning the horizon. 3-7s: Radar shows multiple fast contacts approaching. 7-10s: Captain grabs radio and orders battle stations.`

narrator_text: `Đại tá Harris phát hiện tín hiệu radar bất thường. Hàng chục tàu cao tốc Iran lao thẳng về phía đoàn hộ tống.`
(20 words, ~7s, inside the 8.5s an Omni clip allows — on Veo this would need trimming to 18)

### Example (military documentary, English):

narrator_text: `Colonel Harris detects unusual radar signatures. Dozens of Iranian fast boats racing toward the convoy.`
(15 words, ~5.5s — fits either family, adds Iran context, punchy)

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
  000 |    20 |         6.0s  | Đại tá Harris phát hiện tín hiệu radar...
  001 |    22 |         6.5s  | Tàu dầu Meridian Star nặng nề tiến...
  002 |    19 |         5.5s  | Eo biển Hormuz — 20% dầu thế giới...
  ...
Total: 40 scenes, ~800 words, ~260s narration
```

Ask user: "Review OK? Type 'yes' to generate TTS, or 'edit N' to modify scene N's text."

## Step 6: Generate TTS for all scenes

**CRITICAL: Always pass BOTH `ref_audio` AND `ref_text` together.**
Without `ref_text`, OmniVoice falls back to generic voice → each scene sounds different.

### Proven workflow (per-scene via `/api/tts/generate`):

The batch endpoint (`/api/videos/<VID>/narrate`) can timeout on large batches (40+ scenes).
Use per-scene generation for reliability:

```python
for scene in scenes:
    curl -s -m 120 -X POST "$FK/api/tts/generate" -H "$KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "text": "<scene_narrator_text>",
        "ref_audio": "<path_to_voice_template.wav>",
        "ref_text": "<exact_transcript_of_voice_template>",
        "speed": 1.1,
        "output_path": "${OUTDIR}/tts/scene_{IDX3}_{scene_id}.wav"
      }'
```

### Where does `ref_text` come from?

The `ref_text` is the **exact transcript** of what's spoken in `ref_audio`.

- If template was created via `/fk-gen-tts-template`: `ref_text` = the standard base transcript used during creation (stored in `templates.json`)
- If template is a user-provided WAV: transcribe it first using whisper, then use that transcript as `ref_text` for all scenes

### Key rules:
- `ref_audio` = the voice template WAV file (voice timbre source)
- `ref_text` = exact transcript of `ref_audio` (phoneme alignment)
- Both MUST be provided together — never just `ref_audio` alone
- Same `ref_audio` + `ref_text` for ALL scenes = consistent voice
- `speed: 1.1` recommended for documentary pacing

**mix: false** — we don't mix here. Mixing happens in `/fk-concat-fit-narrator`.

## Step 7: Setup output directory

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
# Get the project's output directory on the server
PROJ_OUT=$(curl -s "$FK/api/projects/<PID>/output-dir" -H "$KEY")
OUTDIR=$(echo "$PROJ_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")
mkdir -p "${OUTDIR}/tts"
```

Verify file naming matches expected pattern:
```
${OUTDIR}/tts/scene_000_<scene_id>.wav
${OUTDIR}/tts/scene_001_<scene_id>.wav
...
${OUTDIR}/tts/scene_039_<scene_id>.wav
```

## Step 8: Verify and output

```bash
ls "${OUTDIR}/tts/scene_*.wav" | wc -l
# Should match number of scenes with narrator_text

# Check a few durations
for f in $(ls "${OUTDIR}/tts/scene_00*.wav" | head -5); do
  echo "$(basename $f): $(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$f")s"
done
```

Print:
```
Narrator generation complete: <project_name>
  Cinematic scenes narrated: N/M
  Interview scenes (skipped): K
  Language: Vietnamese
  Voice: <template_name or ref_audio>
  Speed: 1.1x
  Total narration: XXXs
  Output: ${OUTDIR}/tts/

  Next step: /fk-concat-fit-narrator <video_id>
  Note: Interview scenes keep original video audio (no narrator overlay).
```

## Narrative Arc Guide

When writing narrator text for 30-40 scenes, follow a narrative arc:

| Phase | Scenes | Tone | Example |
|-------|--------|------|---------|
| **Setup** | 1-5 | Calm, informative | "Eo biển Hormuz — tuyến đường huyết mạch..." |
| **Rising** | 6-15 | Building tension | "Radar phát hiện nhiều tín hiệu bất thường..." |
| **Climax** | 16-25 | Intense, urgent | "Iran tấn công! Hàng chục tàu lao về phía đoàn hộ tống!" |
| **Resolution** | 26-35 | Relief, reflection | "Đoàn tàu đã vượt qua eo biển an toàn..." |
| **Epilogue** | 36-40 | Reflective, closing | "Chiến dịch Hormuz Shield — bài học về sức mạnh răn đe..." |

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| TTS sounds different each scene | No voice template | Run /fk-gen-tts-template first |
| Narrator text too long | Exceeds word count | Keep under 22 VN / 22 EN words |
| Dead air in scene | Narrator text too short | Aim for 18+ VN / 18+ EN words |
| Wrong language | Didn't match project language | Use --language flag or check project.language |
| TTS files not found by concat | Wrong output path | Copy to ${OUTDIR}/tts/ |
| Narrator describes visuals | Bad writing style | Remove "we see", describe context/stakes instead |
