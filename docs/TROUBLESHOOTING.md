# Troubleshooting

Start with `/fk-doctor`. It knows everything on this page and checks the live
agent for you. This page is the reference behind it.

Errors come from four layers: Google Flow, the Chrome extension, the FastAPI
layer and the worker. The worker (`_handle_failure` in `agent/worker/processor.py`)
decides how to recover from the **text of `error_message`, not the HTTP status**,
because Flow returns many different failures as HTTP 400 with a different
`details.reason`.

## Common symptoms

| Problem | Fix |
|---------|-----|
| Extension says "Agent disconnected" | Start the agent (`python -m agent.main`, or `docker compose up -d`) |
| Extension says "No token" | Expected. The batch path has no bearer token |
| `/health` shows `extension_connected: false` in Docker | Sign in on the browser desktop and load `/extension`; if the browser container restarted, `docker compose restart agent` |
| `CAPTCHA_FAILED: NO_FLOW_TAB` | Open a `flow.google.com` tab and leave it open |
| `NO_FLOW_PROJECT` | Set `FLOW_PROJECT_ID`, or pass `flow_project_id` to `POST /api/projects` |
| `UNSUPPORTED_ON_BATCH_API` | 4K upscale, r2v, chaining, or Omni references / first+last frames: not ported yet (see `docs/CAPTURE.md`) |
| `INVALID_MODEL_CONFIG: Omni Flash has no Ns clip` / `… not an Omni model the batch path knows` | `omni_flash_duration_s` or `omni_flash_models.frame_to_video` in `agent/models.json` is wrong. Use 4/6/8/10 and an `abra_i2v_<N>s` key |
| Clips are 10 s, narration limits feel off | The project uses Omni Flash. Check `effective_video_model_family` and `video_clip_seconds` on `GET /api/projects/<PID>` |
| 403 `MODEL_ACCESS_DENIED` | Tier mismatch. Check `GET /api/flow/credits` and pick an allowed model with `/fk-change-model` |
| 403 `PUBLIC_ERROR_UNUSUAL_ACTIVITY` | See [Unusual activity](#unusual-activity) |
| Scene images don't match the references | Every ref needs a UUID `media_id`. Run `/fk-fix-uuids` |
| `media_id` starts with `CAMS...` | Run `/fk-fix-uuids` |
| Thumbnails broken, render fails on old media | Signed URLs expired. Run `/fk-refresh-urls <video_id>` |
| Request stuck in `PROCESSING` | Check its `error_message`. Stale rows are recovered after `STALE_PROCESSING_TIMEOUT` (600 s) |
| "Requested entity was not found" over and over | Uploaded media expired. The worker re-uploads it; `POST /api/flow/upload-image` does it by hand (admin) |
| A poll says "Media not found." | Not a failure. Finished jobs report it |
| 401 on every `/api` call | Keys are on. Send `X-API-Key` |

## Flow errors

These come back in the response body as `data.error.details[].reason`. The
worker appends the reason to `error_message` as `"<msg> [<reason>]"`.

| Reason | Meaning | What happens |
|--------|---------|--------------|
| `PUBLIC_ERROR_UNSAFE_GENERATION` | The prompt tripped the safety filter | FAILED. Rewrite the prompt (alias names, remove triggers) |
| `PUBLIC_ERROR_USER_QUOTA_REACHED` | Daily credits used up | FAILED. Wait for the reset or upgrade |
| `PUBLIC_ERROR_MODEL_ACCESS_DENIED` | The model needs a higher tier | FAILED. Pick an allowed model |
| `Requested entity was not found` | An uploaded `media_id` expired | `_recover_entity_not_found` re-uploads from `image_url` and re-queues |
| `Internal error encountered` | Transient Flow 500 | Retried with backoff: `2^retry * 10 s`, capped at 300 s |
| `reCAPTCHA failed` / `captcha` | The extension couldn't mint a token | Retried up to 10 times without counting against `MAX_RETRIES` |
| `PUBLIC_ERROR_UNUSUAL_ACTIVITY` | Google flagged the session as bot-like | Not recoverable automatically |

### Unusual activity

403 with the message `reCAPTCHA evaluation failed`. Usually bursts of submits, a
VPN, shared or cloud IP, or stale cookies.

1. Stop submitting.
2. In the Flow browser, clear cookies for `google.com` and sign in to
   `https://flow.google.com/` again.
3. Resubmit with at least a second between requests and no more than 5 at once.
4. Still blocked: switch network, or wait 1–6 hours.

## HTTP status codes

| Status | From | Meaning | What happens |
|--------|------|---------|--------------|
| 400 | Flow | Bad payload, unsafe generation, sometimes entity not found | Decided by `details.reason` |
| 401 | Agent | Missing or wrong `X-API-Key` (with `AUTH_ENABLED=1`) | Send the key |
| 401 | Flow, legacy path | Bearer expired. Post-migration it is never minted | Use the batch path (`USE_BATCH_RPC=1`) |
| 403 | Extension | `CAPTCHA_FAILED`, `NO_FLOW_TAB` or `MODEL_ACCESS_DENIED` | CAPTCHA retries; the others fail |
| 403 | Agent | The key has no grant for that project, or the route is admin-only | Grant the project with `python -m agent.users grant` |
| 404 | Flow | `media_id` not found (expired upload) | Re-upload, as above |
| 429 | Flow | Rate limited or out of quota | Backoff; `USER_QUOTA_REACHED` fails |
| 500 | Flow or extension | Server error, or the network dropped during the fetch | Retried with backoff |
| 502 | Agent | The extension returned an error without a status | Retried; check the extension |
| 503 | Agent | Extension not connected | The request goes back to PENDING and waits |
| 504 | Agent | No reply from the extension in 60 s | Treated as transient and re-queued |

A result counts as an error when `result.error` is set, `status >= 400`, or
`data.error` is present (`_is_error` in `agent/worker/_parsing.py`).

## Extension and transport errors

| `error_message` contains | Cause | What happens |
|--------------------------|-------|--------------|
| `Extension not connected` | Extension offline or socket dropped | Re-queued, waits for reconnect |
| `extension reconnected` / `extension disconnected` | Socket bounced mid-request | Re-queued without counting a retry |
| `extension_switched` | Flow tab changed mid-generation | Re-queued |
| `NO_AT_TOKEN` | Flow tab signed out, on an interstitial, or still loading | Open `flow.google.com`, sign in, let it load |
| `NO_FLOW_PROJECT` | No project to scope the RPC to | Terminal. Set `FLOW_PROJECT_ID` |
| `UNSUPPORTED_ON_BATCH_API` | Payload never captured | Terminal. See `docs/CAPTURE.md` |
| `INVALID_MODEL_CONFIG` | Bad Omni length or key in `models.json` | Terminal, not retried. Fix `omni_flash_duration_s` / `omni_flash_models` |
| `NO_FLOW_TAB` | No Flow tab for reCAPTCHA | Open a Flow tab |
| `NO_FLOW_KEY` | No bearer token | Legacy path only (`USE_BATCH_RPC=0`) |
| `Failed to fetch` | Network drop in the service worker | Retried with backoff |
| `timeout` | Extension hung | Re-queued |

## Retry policy

In order:

1. Message contains `not found` → re-upload the media and re-queue.
2. Socket bounce (`reconnected`, `disconnected`, `switched`) → re-queue, keep `retry_count`.
3. CAPTCHA → retry up to 10 times without counting against `MAX_RETRIES`.
4. Anything else → `retry_count + 1`; below `MAX_RETRIES` (5) it retries after
   `2^retry * 10 s` (max 300 s), otherwise FAILED.

## YouTube upload errors

From the YouTube Data API v3, in the gitignored `youtube/` code.

| Error | Cause | Fix |
|-------|-------|-----|
| `invalidTags` (400) | Tags over 500 characters, counting quotes around tags with spaces | Trim tags: `sum(len(t) + (2 if ' ' in t else 0) for t in tags) + len(tags) - 1 <= 500` |
| `invalidCategoryId` (400) | Unknown category | Use `22` (People & Blogs) or `24` (Entertainment) |
| `quotaExceeded` (403) | Daily 10,000-unit quota used (an upload costs 1,600) | Wait for the Pacific midnight reset |
| `uploadLimitExceeded` (400) | Channel's daily upload cap | Wait 24 h or use another channel |
| `invalid_grant` | Token revoked or expired | `python youtube/auth.py <channel>` |
| `scheduledPublishTimeInPast` | `publishAt` is not in the future | Schedule later |
