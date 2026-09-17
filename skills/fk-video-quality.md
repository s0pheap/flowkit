# Video Quality Guide — Where Effort Actually Changes the Output

Reference for making scene videos look good, not just for making them finish.
Every other `/fk-*` skill tells you *how to run* a step. This one tells you
*which knob is worth turning*, and which ones the agent already turns for you.

Read this before `/fk-gen-images` — by the time `/fk-gen-videos` runs, most of
the quality is already decided.

---

## 1. First: know which model family you are on

This changes almost everything below.

```bash
. ~/.flowkit/env 2>/dev/null; FK="${FLOWKIT_URL:-http://127.0.0.1:8100}"; KEY="X-API-Key: ${FLOWKIT_API_KEY:-}"
curl -s "$FK/api/projects/<PID>" -H "$KEY"
```

Read `effective_video_model_family`. Switch it with `/fk-change-model family`.

| | `omni_flash` (**the default**) | `veo` |
|---|---|---|
| How it works | **Image-to-video** from your keyframe (`abra_i2v_<N>s`) | Text-conditioned generation |
| Clip length | `video_clip_seconds`, 10s default | 8s |
| First frame | **Your image, exactly** | The model invents it |
| Native audio | No | Yes (dialogue, SFX, ambient) |
| Quality comes from | **The image** | The prompt |

**The single most important consequence:** on `omni_flash` the keyframe *is*
the video's first frame. Composition, characters, lighting, wardrobe and style
are locked in before the video model ever runs. The video prompt only adds
motion. A weak keyframe cannot be rescued by a better video prompt — it can
only be re-imaged.

## 2. `fk-camera-guide` is written for Veo 3 — split it by family

`/fk-camera-guide` is excellent, but it predates Omni Flash becoming the
default. On `omni_flash`, only part of it applies.

**Still applies on `omni_flash`:**

- One camera movement per clip, written as its own sentence
- The movement vocabulary (`dolly in`, `pan left`, `tilt up`, `tracking shot`)
- Keeping the prompt to a single clear intent

**Does *not* apply on `omni_flash` — put it in the image prompt instead:**

- Shot type (`wide shot`, `close-up`) — framing is the image's job
- Subject detail (age, hair, wardrobe, identifying features) — already in the
  frame; restating it invites the model to redraw and drift off-model
- Lighting and colour grade — baked into the keyframe
- `Audio:` / `SFX:` / `Music:` labels and dialogue — Omni's i2v model is not
  the Veo audio model. The spoken track comes from `/fk-gen-narrator` (TTS),
  not from the clip

So on `omni_flash`, a good `video_prompt` is **short and about motion only**.
On `veo`, write the full five-component prompt from `/fk-camera-guide`.

## 3. Stop writing boilerplate the agent already appends

`_build_video_prompt` (`agent/sdk/services/operations.py:907`) assembles the
prompt that is actually sent. It already adds, in order:

1. The look & feel camera sentence — but only when `mode` is `generate`
2. The AI fix prompt from `/fk-review-video`, if that scene has one
3. Character voice descriptions — only when the prompt contains a dialogue
   verb (`says`, `whispers`, `asks`, and so on)
4. An `Audio:` line honouring the project's `allow_music` / `allow_voice`
5. `Negative: subtitles, captions, watermark, text on screen, logo, blurry
   faces, distorted hands.`

**Two of these are suppressed if you write your own.** The builder skips its
`Audio:` line when your prompt already contains `audio:` or `music:`, and
skips its `Negative:` line when your prompt already contains `negative:`. So
hand-writing a short negative prompt *replaces* the full one and usually makes
the result worse. Leave both out unless you mean to override them.

## 4. Set look & feel before generating — the biggest cost lever

`/fk-review-board` sets each scene's `mode`, and it decides whether a clip
costs a Flow generation or nothing at all.

| mode | What happens | Cost | Time |
|---|---|---|---|
| `generate` | Flow generates the clip | A generation | ~2–5 min |
| `ffmpeg` | Local pan/zoom over the keyframe | **Free** | Seconds |

**Rule of thumb: if nothing in the frame should physically move, use `ffmpeg`.**
Diagrams, charts, text cards, maps, product stills, logo beats and most
talking-point scenes look *better* as a clean ffmpeg push-in than as a
generative clip — a model asked to animate a static subject invents motion,
warping text, drifting faces and melting hands.

Reserve `generate` for scenes where motion is the point: a character acting,
weather, crowds, vehicles, liquid, fire.

**Also:** `motion` and `strength` in the review board are what produce the
camera sentence (`camera_direction`, `agent/models/look_feel.py`). Setting
`zoom_in` + `medium` appends *"Camera direction: The camera slowly pushes in
toward the subject."* — so writing your own camera move into `video_prompt` on
top of that hands the model two instructions to reconcile. Pick one place; the
review board is the easier one to revise.

## 5. Narration and clip length point in opposite directions

The dependency reverses per mode, which is what trips people up:

- **`generate` scenes** — the clip is a fixed length (10s Omni, 8s Veo), so
  the **narration must fit the clip**. `/fk-gen-narrator` reads
  `video_clip_seconds` and writes to that budget.
- **`ffmpeg` scenes** — the **narration sets the clip length** (narration plus
  0.5s). So `/fk-gen-narrator` has to run *before* `/fk-gen-videos`, or the
  render has no length to target.

If the video has any `ffmpeg` scenes, run the narrator first. Always.

## 6. Run the steps in cost order, so rework stays cheap

```
/fk-gen-refs  →  /fk-gen-images  →  /fk-review-board  →  /fk-gen-narrator
              →  /fk-gen-videos  →  /fk-review-video  →  /fk-concat-fit-narrator
```

Each step is more expensive to redo than the one before it. Measured on a real
project's request history: an image takes about 77s, a character image about
92s, and a video averages about 130s and can reach 250s. Iterate hard at the
image stage, where a miss costs seconds — not at the video stage, where it
costs minutes and a generation.

**Check every image before generating any video.** Characters consistent with
their refs, composition right, no mangled text. A keyframe you would not ship
as a still will not become shippable once it moves.

## 7. `/fk-review-video` feeds itself back in

When the reviewer writes a fix into `<orientation>_ai_fix_prompt`, the next
generation for that scene picks it up automatically — there is no need to paste
it into `video_prompt` by hand. Review, then regenerate the flagged scenes.

## 8. Chain scenes: the two rules that actually bite

- A chain scene **that has children** generates from `transition_prompt`, not
  `video_prompt`. Editing `video_prompt` on such a scene changes nothing.
- Regenerating a parent's image obliges you to regenerate every descendant's
  image *and* re-point the parent's `<orientation>_end_scene_media_id` at the
  child's new image — otherwise the clip transitions toward a frame that no
  longer exists downstream. `/fk-gen-videos` documents the full cascade.

Chaining (start+end frame) is also one of the **unported capabilities**: it
fails with `UNSUPPORTED_ON_BATCH_API` unless its payload has been captured. In
one real project's history it accounted for 5 of 6 video failures. If true
frame-to-frame continuity is not the point of the shot, plain per-scene clips
joined with an `xfade` transition from the review board look nearly as good and
always work.

## 9. When something looks wrong, do not guess

Run `/fk-doctor` — it knows the full error taxonomy. Two quality-specific
patterns worth recognising on sight:

- **Faces or hands degrade only in `generate` scenes** → those scenes probably
  want `ffmpeg` mode, not a better prompt.
- **A scene drifts off-model from its keyframe** → the video prompt is
  re-describing the subject. Cut it back to motion only (see §2).
