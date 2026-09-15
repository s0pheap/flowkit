# Skills — Flow Kit

Workflow skills for AI agents and humans. Each skill is a step-by-step recipe for generating high-quality AI videos.

## Quick Start

**First time?** Run these skills in order to create your first video:

```bash
/fk-research "your topic"           # Research your topic
/fk-create-project                  # Create project (interactive)
/fk-gen-refs <project_id>           # Generate entity references
/fk-gen-images <project_id> <video_id>  # Generate scene images
/fk-gen-narrator <video_id>         # Add narration (optional)
/fk-review-board <video_id>         # Set look & feel
/fk-gen-videos <project_id> <video_id>  # Generate video clips
/fk-concat-fit-narrator <video_id>  # Render final video
```

Use `/fk-status` anytime to see what's done and what to run next.

## Complete Video Generation Workflow (run in this order)

| # | Skill | File | Description |
|---|-------|------|-------------|
| 1 | `fk-research` | [fk-research.md](fk-research.md) | Research and fact-check your topic before creating the project |
| 2 | `fk-create-project` | [fk-create-project.md](fk-create-project.md) | Create project + entities + video + scenes |
| 3 | `fk-gen-refs` | [fk-gen-refs.md](fk-gen-refs.md) | Generate reference images for all entities (characters, locations, props) |
| 4 | `fk-gen-images` | [fk-gen-images.md](fk-gen-images.md) | Generate keyframe images for every scene using entity references |
| 5 | `fk-gen-narrator` | [fk-gen-narrator.md](fk-gen-narrator.md) | Generate narrator text + TTS voiceover + word timings for subtitles |
| 5b | `fk-gen-text-overlays` | [fk-gen-text-overlays.md](fk-gen-text-overlays.md) | Extract key facts as on-screen text overlays (optional) |
| 6 | `fk-review-board` | [fk-review-board.md](fk-review-board.md) | Set look & feel for each scene: Veo vs ffmpeg, transitions, timing |
| 7 | `fk-gen-videos` | [fk-gen-videos.md](fk-gen-videos.md) | Generate video clips (Veo for AI motion, ffmpeg for pan/zoom effects) |
| 8 | `fk-review-video` | [fk-review-video.md](fk-review-video.md) | Score clips for quality, find scenes to regenerate (optional) |
| 8b | `fk-review-board` | [fk-review-board.md](fk-review-board.md) | Mark clips as Good/Redo/Skip, write notes |
| 9 | `fk-gen-music` | [fk-gen-music.md](fk-gen-music.md) | Generate background music with Suno (optional) |
| 10 | `fk-concat-fit-narrator` | [fk-concat-fit-narrator.md](fk-concat-fit-narrator.md) | Render final video with narration timing, music, transitions, subtitles |

**For videos without narration:** Skip steps 5-5b and 9, use `fk-concat` instead of `fk-concat-fit-narrator` in step 10.

### Why this order matters

- **Step 1 → 2:** Research before creating ensures factually accurate content
- **Step 3 → 4:** Reference images MUST exist before scene images (ensures visual consistency)
- **Step 4 → 5:** Scene images should exist before narration (narrator can describe what's visible)
- **Step 5 → 6:** Narration length determines each scene's duration for ffmpeg scenes
- **Step 6 → 7:** Look & feel must be set BEFORE generating videos (determines Veo vs ffmpeg)
- **Step 7 → 8:** Review after videos exist to identify clips that need regeneration
- **Step 8 → 10:** Final assembly needs all clips finalized

**Critical:** A new image clears that scene's video. If you regenerate images after videos, you'll need to regenerate those videos too. Always: refs → images → narration (if ffmpeg) → videos → final render.

## Advanced Video

| Skill | File | Description |
|-------|------|-------------|
| `fk-gen-chain-videos` | [fk-gen-chain-videos.md](fk-gen-chain-videos.md) | Auto start+end frame chaining for smooth transitions |
| `fk-insert-scene` | [fk-insert-scene.md](fk-insert-scene.md) | Multi-angle shots, cutaways, close-ups |
| `fk-creative-mix` | [fk-creative-mix.md](fk-creative-mix.md) | Analyze story + suggest all techniques combined |

## Reference

| Skill | File | Description |
|-------|------|-------------|
| `fk-camera-guide` | [fk-camera-guide.md](fk-camera-guide.md) | Camera angles, movements, lighting, DOF for cinematic video prompts |

## Project Management & Troubleshooting

| Skill | File | Description |
|-------|------|-------------|
| `fk-status` | [fk-status.md](fk-status.md) | Show project progress and what to run next |
| `fk-switch-project` | [fk-switch-project.md](fk-switch-project.md) | Set active project (work on multiple projects) |
| `fk-doctor` | [fk-doctor.md](fk-doctor.md) | Diagnose and fix errors across Flow, extension, agent |
| `fk-refresh-urls` | [fk-refresh-urls.md](fk-refresh-urls.md) | Re-sign expired media URLs |
| `fk-fix-uuids` | [fk-fix-uuids.md](fk-fix-uuids.md) | Repair CAMS... media_ids to UUID format |

## Cross-Tool Compatibility

Skills live in `skills/` — the single source of truth. Run `setup.py` to generate configs for your AI tool:

```bash
python setup.py           # Interactive setup
python setup.py --tool all  # Generate for all tools
python setup.py sync      # Re-sync after adding skills
python setup.py clean     # Remove generated configs
```

| Tool | Generated Config | Instruction File | Invocation |
|------|-----------------|------------------|------------|
| Claude Code | `.claude/commands/fk-<name>.md` (stubs) | `CLAUDE.md` (committed) | `/fk-<name>` |
| Antigravity CLI (`agy`) | `.agents/skills/fk-<name>/SKILL.md` | `GEMINI.md` / `AGENTS.md` (generated) | `/fk-<name>` or auto-invoked |
| Codex CLI | — | `AGENTS.md` (generated) | Read `skills/fk-<name>.md` |

**Adding a new skill:** Create `skills/fk-<name>.md`, then run `python setup.py sync`.

---

## Full Example: "Luna the Space Cat" (3 scenes, vertical)

This walkthrough shows exactly how an AI agent uses skills to go from idea to final video.

### 1. `/fk-create-project`

**Agent asks:** What's your project? Characters, locations, key objects, scenes, orientation?

**User says:** "Luna is a small white cat astronaut exploring a candy planet. 3 scenes: she lands on the planet, discovers a chocolate river, and plants a flag on a gummy bear mountain. Vertical, Pixar 3D."

**Agent thinks:** Break the story into visual elements that repeat across scenes:

| Element | entity_type | Why it needs a reference | description (appearance only) |
|---------|-------------|------------------------|-------------------------------|
| Luna | `character` | Main character in all 3 scenes | Small white cat with big blue eyes, wearing a tiny orange space suit with a round glass helmet. Fluffy tail sticking out. Pixar-style 3D. |
| Candy Planet Surface | `location` | Ground/environment in all scenes | Alien planet surface made of colorful hard candies, lollipop trees, cotton candy clouds, pastel pink and purple sky. Pixar-style 3D. |
| Chocolate River | `location` | Key location in scene 2 | Wide flowing river of dark melted chocolate with marshmallow rocks along the banks, steam rising, rich brown tones. Pixar-style 3D. |
| Gummy Bear Mountain | `location` | Key location in scene 3 | Tall mountain made of giant translucent gummy bears stacked together, glowing from inside, rainbow colors. Pixar-style 3D. |

**Agent writes scene prompts** (action + environment, NO character appearance):

| Scene | Prompt | character_names | Chain |
|-------|--------|-----------------|-------|
| 1 | "Luna steps out of a small rocket onto Candy Planet Surface. First footprint in candy dust. Wide shot, dramatic landing moment. Pixar 3D, cinematic." | Luna, Candy Planet Surface | ROOT |
| 2 | "Luna kneels at the edge of Chocolate River on Candy Planet Surface, dipping a paw in. Surprised expression, licking the paw. Warm lighting reflected off chocolate. Pixar 3D." | Luna, Candy Planet Surface, Chocolate River | CONTINUATION ← 1 |
| 3 | "Luna plants a small flag on top of Gummy Bear Mountain, triumphant pose. Candy Planet Surface stretching to the horizon below. Epic wide angle, sunset glow through gummy bears. Pixar 3D." | Luna, Candy Planet Surface, Gummy Bear Mountain | CONTINUATION ← 2 |

**Agent executes:**

```bash
# Create project (gets projectId from Google Flow)
curl -X POST http://127.0.0.1:8100/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Luna the Space Cat",
    "story": "Luna is a small white cat astronaut who lands on a candy planet. She discovers a chocolate river and plants a flag on a gummy bear mountain.",
    "characters": [
      {"name": "Luna", "entity_type": "character", "description": "Small white cat with big blue eyes, wearing a tiny orange space suit with round glass helmet. Fluffy tail. Pixar-style 3D.", "voice_description": "Soft curious childlike voice full of wonder, with a slight purring undertone"},
      {"name": "Candy Planet Surface", "entity_type": "location", "description": "Alien planet surface made of colorful hard candies, lollipop trees, cotton candy clouds, pastel pink and purple sky. Pixar-style 3D."},
      {"name": "Chocolate River", "entity_type": "location", "description": "Wide flowing river of dark melted chocolate with marshmallow rocks along banks, steam rising. Pixar-style 3D."},
      {"name": "Gummy Bear Mountain", "entity_type": "location", "description": "Tall mountain made of giant translucent gummy bears stacked together, glowing from inside, rainbow colors. Pixar-style 3D."}
    ]
  }'
# → project_id: "p-xxx"

# Create video
curl -X POST http://127.0.0.1:8100/api/videos \
  -H "Content-Type: application/json" \
  -d '{"project_id": "p-xxx", "title": "Luna Episode 1"}'
# → video_id: "v-xxx"

# Create 3 scenes
# Scene 1: prompt (image) + video_prompt (8s sub-clip with camera + dialogue)
curl -X POST http://127.0.0.1:8100/api/scenes -H "Content-Type: application/json" \
  -d '{
    "video_id": "v-xxx", "display_order": 0,
    "prompt": "Luna steps out of a small rocket onto Candy Planet Surface. First footprint in candy dust. Wide shot, dramatic landing. Pixar 3D.",
    "video_prompt": "0-3s: Wide crane down shot, Luna emerges from rocket hatch onto Candy Planet Surface. Luna gasps \"Wow!\" 3-6s: Low angle tracking shot, Luna takes first steps on candy ground, looking around in wonder. Luna says \"Everything is made of candy!\" 6-8s: Wide establishing shot, Luna small in frame against vast Candy Planet Surface landscape, cotton candy clouds. Silence, gentle wind.",
    "character_names": ["Luna", "Candy Planet Surface"],
    "chain_type": "ROOT"
  }'
# → scene_id: "s-1"

curl -X POST http://127.0.0.1:8100/api/scenes -H "Content-Type: application/json" \
  -d '{
    "video_id": "v-xxx", "display_order": 1,
    "prompt": "Luna kneels at the edge of Chocolate River on Candy Planet Surface, dipping a paw in. Surprised expression. Warm lighting. Pixar 3D.",
    "video_prompt": "0-3s: Over-the-shoulder shot, Luna kneels at Chocolate River edge on Candy Planet Surface, steam rising. Luna asks \"What is this?\" 3-5s: Close-up Luna paw dipping into chocolate, slow motion. Luna tastes it, eyes widen. Luna says \"It is chocolate! Real chocolate!\" 5-8s: Medium shot, Luna jumps up with arms raised, Chocolate River flowing behind. Luna shouts \"This is the best planet ever!\"",
    "character_names": ["Luna", "Candy Planet Surface", "Chocolate River"],
    "chain_type": "CONTINUATION", "parent_scene_id": "s-1"
  }'
# → scene_id: "s-2"

curl -X POST http://127.0.0.1:8100/api/scenes -H "Content-Type: application/json" \
  -d '{
    "video_id": "v-xxx", "display_order": 2,
    "prompt": "Luna plants a small flag on top of Gummy Bear Mountain. Candy Planet Surface below. Sunset glow through gummy bears. Pixar 3D.",
    "video_prompt": "0-3s: Low angle push in, Luna climbs last steps of Gummy Bear Mountain, determination on face. 3-5s: Medium shot, Luna plants flag on summit, triumphant pose. Luna says \"I did it! Planet Candy is claimed!\" 5-8s: Epic crane up to wide bird eye view, Luna tiny on Gummy Bear Mountain peak, Candy Planet Surface stretching to horizon, golden sunset through translucent gummy bears. Silence, majestic.",
    "character_names": ["Luna", "Candy Planet Surface", "Gummy Bear Mountain"],
    "chain_type": "CONTINUATION", "parent_scene_id": "s-2"
  }'
# → scene_id: "s-3"
```

**Agent says:** "Project created with 4 entities and 3 scenes. Run `/fk-gen-refs p-xxx` to generate reference images."

---

### 2. `/fk-gen-refs p-xxx`

**Agent executes** (one at a time, waits for each):

```
Generating Luna (character, portrait)...
  Request req-1 → PROCESSING → COMPLETED ✓  media_id: a1b2c3d4-...

Generating Candy Planet Surface (location, landscape)...
  Request req-2 → PROCESSING → COMPLETED ✓  media_id: e5f6a7b8-...

Generating Chocolate River (location, landscape)...
  Request req-3 → PROCESSING → COMPLETED ✓  media_id: c9d0e1f2-...

Generating Gummy Bear Mountain (location, landscape)...
  Request req-4 → PROCESSING → COMPLETED ✓  media_id: a3b4c5d6-...

All 4 references ready:
  Luna                  character      media_id=a1b2c3d4-...  ✓
  Candy Planet Surface  location       media_id=e5f6a7b8-...  ✓
  Chocolate River       location       media_id=c9d0e1f2-...  ✓
  Gummy Bear Mountain   location       media_id=a3b4c5d6-...  ✓

Run /fk-gen-images p-xxx v-xxx to generate scene images.
```

---

### 3. `/fk-gen-images p-xxx v-xxx`

**Agent pre-checks:** All 4 refs have UUID media_id ✓

**Agent executes** (one at a time):

```
Scene 1 (Luna + Candy Planet Surface): using 2 reference images
  Request req-5 → PROCESSING → COMPLETED ✓

Scene 2 (Luna + Candy Planet Surface + Chocolate River): using 3 reference images
  Request req-6 → PROCESSING → COMPLETED ✓

Scene 3 (Luna + Candy Planet Surface + Gummy Bear Mountain): using 3 reference images
  Request req-7 → PROCESSING → COMPLETED ✓

All 3 scene images ready:
  Scene 1: image=OK  media_id=f1e2d3c4-...
  Scene 2: image=OK  media_id=b5a6c7d8-...
  Scene 3: image=OK  media_id=e9f0a1b2-...

Run /fk-gen-videos p-xxx v-xxx to generate videos.
```

---

### 4. `/fk-gen-videos p-xxx v-xxx`

**Agent pre-checks:** All 3 scenes have UUID image media_id ✓

**Agent executes** (one at a time, 2-5 min each):

```
Scene 1 video: startImage=f1e2d3c4-...
  Request req-8 → PROCESSING → polling... [30s] [60s] [90s] → COMPLETED ✓

Scene 2 video: startImage=b5a6c7d8-..., endImage=f1e2d3c4-... (chained from scene 1)
  Request req-9 → PROCESSING → polling... [30s] [60s] [90s] [120s] → COMPLETED ✓

Scene 3 video: startImage=e9f0a1b2-..., endImage=b5a6c7d8-... (chained from scene 2)
  Request req-10 → PROCESSING → polling... [30s] [60s] [90s] → COMPLETED ✓

All 3 videos ready:
  Scene 1: video=OK  url=https://storage.googleapis.com/...
  Scene 2: video=OK  url=https://storage.googleapis.com/...
  Scene 3: video=OK  url=https://storage.googleapis.com/...

Run /fk-concat v-xxx to download and merge.
```

---

### 5. `/fk-concat v-xxx`

```
Getting output dir from API...
OUTDIR=output/luna_the_space_cat

Downloading scene 1... 2.1 MB → output/luna_the_space_cat/scenes/scene_1.mp4
Downloading scene 2... 3.4 MB → output/luna_the_space_cat/scenes/scene_2.mp4
Downloading scene 3... 2.8 MB → output/luna_the_space_cat/scenes/scene_3.mp4
Normalizing (720x1280, 24fps, h264) → output/luna_the_space_cat/norm/
Concatenating 3 scenes...

Done!
  output/luna_the_space_cat/luna_the_space_cat_final.mp4
  720x1280 (vertical)
  24 seconds
  8.3 MB
```

---

### Result

A 24-second Pixar-style video of Luna the Space Cat:
- **Scene 1:** Luna lands on the candy planet (8s)
- **Scene 2:** Luna discovers the chocolate river and tastes it (8s)
- **Scene 3:** Luna plants a flag on gummy bear mountain at sunset (8s)

Luna looks the same across all 3 scenes because her reference image was used as `imageInputs` in every scene generation. The candy planet surface is consistent too — same colors, same lollipop trees, same sky.

---

### What the agent needed to know

1. **Break story into visual elements** → characters, locations, assets (with `entity_type`)
2. **Description = appearance only** → what it looks like, not what it does
3. **Scene prompt = action only** → what happens, reference entities by name
4. **`character_names` = which refs to use** → list every entity visible in that scene
5. **Pipeline order** → refs MUST complete before images, images before videos
6. **One request at a time** → 10s cooldown, wait for COMPLETED before next
