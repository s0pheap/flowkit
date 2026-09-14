# Deploying Flow Kit for other users

This puts the agent and the dashboard behind one public HTTPS address on a cloud
VM. Your users get a URL and an API key. They install the skills on their own
computer with one command, drive generation from Claude Code, Codex or
Antigravity, and watch the results in the dashboard.

```
user's AI tool ──HTTPS + X-API-Key──┐
user's browser ──HTTPS──────────────┤
                                    ▼
                    Caddy :443 (TLS, the only open port)
                                    ▼
                  agent 127.0.0.1:8100  (API + dashboard + installer)
                                    ▲
                  Chrome extension ─┘ ws://127.0.0.1:9222 (never exposed)
                                    │
                  signed-in flow.google.com tab (your Google account)
```

## Before you start

- **It runs on your Google account.** Every user's images and videos are made by
  the Flow account signed in on the VM and count against its quota. Heavy or
  bot-like use can get that account challenged or blocked, for everyone at once.
- **Cloud IPs are more likely to be challenged** (`PUBLIC_ERROR_UNUSUAL_ACTIVITY`,
  extra CAPTCHAs) than a home connection. Start with a few users and watch for it.
- **The VM needs a desktop.** Only a real, signed-in Chrome tab can sign Flow
  requests, so there is no headless mode.
- **One queue for everyone.** The worker runs at most `MAX_CONCURRENT_REQUESTS`
  (5) generations at a time across all users. There are no per-user quotas yet.

## 1. Create the VM

- **OS:** Windows Server 2022/2025 with Desktop Experience. This guide uses it;
  Ubuntu Desktop works too (see the end).
- **Size:** 4 vCPU, 8 GB RAM, 60 GB disk. ffmpeg renders are the heaviest load.
- **Network:** a static public IP. In the provider's firewall allow **TCP 80 and
  443 only** (plus RDP 3389 restricted to your own IP). Never open 8100 or 9222.
- **Domain:** point an `A` record such as `flowkit.example.com` at the IP.

## 2. Install the tools

On the VM, in PowerShell as Administrator:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Gyan.FFmpeg -e
winget install --id Google.Chrome -e
winget install --id CaddyServer.Caddy -e
```

Open a new PowerShell so the tools are on `PATH`.

## 3. Get Flow Kit and build the dashboard

```powershell
cd C:\
git clone <your repo url> flowkit
cd C:\flowkit
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
cd dashboard; npm ci; npm run build; cd ..
```

The agent serves `dashboard\dist` at `/` by itself, so no separate web server is
needed for the dashboard.

## 4. Configure `.env`

```powershell
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # use as ADMIN_API_KEY
```

Set at least:

```ini
AUTH_ENABLED=1
ADMIN_API_KEY=<the random string>
PUBLIC_URL=https://flowkit.example.com
API_HOST=127.0.0.1
WS_HOST=127.0.0.1
FLOW_PROJECT_ID=<a Flow project for your own admin use>
GEMINI_API_KEY=<optional, only for narration>
```

Keep the admin key private. It can do everything, including changing models for
all users.

## 5. Sign in to Flow and load the extension

1. Open Chrome on the VM desktop and sign in to `https://flow.google.com/` with the
   Google account that will do the generating.
2. Go to `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**
   and choose `C:\flowkit\extension`.
3. **Pin** the Flow tab (right-click → Pin) and leave it open.
4. In `chrome://settings/performance`, turn **Memory Saver off** so Chrome never
   discards the Flow tab.

## 6. Run the agent at logon

Test it by hand first:

```powershell
cd C:\flowkit
venv\Scripts\python -m agent.main
```

In another window, `curl.exe -s http://127.0.0.1:8100/health` must show
`"extension_connected": true`.

To start it automatically, create a Task Scheduler task that runs **at log on of
your user** (not as a service — it has to share the desktop session with Chrome):

- Program: `C:\flowkit\venv\Scripts\python.exe`
- Arguments: `-m agent.main`
- Start in: `C:\flowkit`
- Settings: restart on failure every minute; do not stop after 3 days

Also add Chrome to the same user's startup (`shell:startup`), and stop the VM
from sleeping:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
```

When you leave, **close the RDP window instead of signing out**. Signing out
closes Chrome, and every request then fails with `NO_FLOW_TAB`.

## 7. HTTPS with Caddy

`C:\caddy\Caddyfile`:

```
flowkit.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8100
}
```

Caddy gets and renews the certificate itself, and forwards WebSockets (the live
dashboard) without extra settings. Run it once to check, then install it as a
Windows service (for example with `nssm install caddy C:\...\caddy.exe run --config C:\caddy\Caddyfile`):

```powershell
caddy run --config C:\caddy\Caddyfile
```

Check from your own computer:

```bash
curl -s https://flowkit.example.com/health
curl -s https://flowkit.example.com/api/projects            # → 401, keys are on
curl -s -H "X-API-Key: <admin key>" https://flowkit.example.com/api/flow/status
```

## 8. Add a user

For each user:

1. In Flow on the VM, create a project for them and copy the uuid from its URL
   (`flow.google.com/project/<uuid>`).
2. Create their key and grant the project:

   ```powershell
   cd C:\flowkit
   venv\Scripts\python -m agent.users create alice --project <flow-project-uuid>
   ```

   The key is printed **once**. Grant more projects later with
   `python -m agent.users grant alice <uuid>`.
3. Send them the address and their key. On their own computer they open
   `https://flowkit.example.com/guide`, sign in with the key, and follow
   **Get started**, which shows the install command for their system:

   ```bash
   curl -fsSL https://flowkit.example.com/install.sh | bash      # macOS / Linux / Git Bash
   ```
   ```powershell
   irm https://flowkit.example.com/install.ps1 | iex             # Windows
   ```

4. They restart their AI tool and run `/fk-status`, then `/fk-create-project`,
   `/fk-gen-refs`, `/fk-gen-images` and `/fk-gen-videos`. Results show up in the
   dashboard under **Projects**.

Manage keys with `python -m agent.users list | revoke | rotate-key | disable | delete`.

## What users can and cannot do

Installed skills (API calls only; the work and the files stay on the server, except
`fk-research`, which only runs web searches and saves its report on the user's machine):

| Stage | Skills |
|-------|--------|
| Project | `fk-research`, `fk-create-project`, `fk-switch-project`, `fk-status` |
| Images and video | `fk-gen-refs`, `fk-gen-images`, `fk-gen-videos`, `fk-camera-guide` |
| Narration, music and final video | `fk-gen-narrator`, `fk-gen-text-overlays`, `fk-gen-music`, `fk-review-board`, `fk-concat-fit-narrator` |
| Fixing | `fk-refresh-urls`, `fk-doctor` |

The list lives in `agent/api/install.py` (`REMOTE_SKILLS`).

- **Narration** uses the server's `GEMINI_API_KEY`, so every user's narration
  counts against your Gemini quota. To avoid that, use the same Gemini voices through
  the Mindlogic gateway (`TTS_ENGINE=mindlogic`, `MINDLOGIC_API_KEY`), or run a Kokoro-82M server and set
  `TTS_ENGINE=kokoro` and `KOKORO_URL` (see `.env.example`); Kokoro has no Korean or
  Khmer, so those lines go to `TTS_FALLBACK_ENGINE=piper,google`. When the quota runs out, narration switches
  to Piper, a free voice that runs on the VM (`TTS_FALLBACK_ENGINE=piper`, the
  default; it comes with `requirements.txt`). Each voice downloads once, about
  60 MB, into `output\_shared\piper_voices`. Replies say which scenes it spoke,
  and users can redo them with Gemini later.
- **Music** from `/fk-gen-music` uses the server's `SUNO_API_KEY` and credits.
  Users can also upload their own tracks. The render lays the chosen track under
  the whole video and turns it down while the narrator speaks.
- **Final videos** are rendered by ffmpeg on the VM, one at a time. Users
  download them with `/fk-concat-fit-narrator`, or watch and download them in the
  dashboard under **Projects → Videos**.
- **The review board** is at `https://flowkit.example.com/review-board?video_id=…`
  and uses the key the browser signed in with on the dashboard.

Not available to remote users:

- Settings (`/fk-change-model`, `/fk-change-provider`), materials, voice
  templates, `/fk-upload-image` and direct `/api/flow/*` calls (admin-only).
- YouTube upload and branding, which use your channel credentials on the VM.
- Skills not in the table above still expect to run on the VM itself.

## Keeping it running

- **Update:** `git pull`, `venv\Scripts\python -m pip install -r requirements.txt`,
  `cd dashboard; npm ci; npm run build`, then restart the agent task. If anything
  under `extension\` changed, click reload on the extension card too. Users re-run
  the install command to get updated skills.
- **Back up** `C:\flowkit\flow_agent.db` (users, grants, projects) regularly,
  ideally while the agent is stopped.
- **Media links expire** after a few hours, so thumbnails in old projects can
  break and renders fail. Users run `/fk-refresh-urls <video_id>` to re-sign them.
- **Disk:** renders keep their intermediate clips in `output\<project>\trimmed`.
  Delete old `trimmed` folders if the disk fills up.
- **Fonts:** burned-in Korean or other non-Latin text needs a font on the VM.
  Windows has Malgun Gothic; on Ubuntu install `fonts-noto-cjk`. Override with
  `OVERLAY_FONT` (a font file) and `SUBTITLE_FONT` (a font name) in `.env`.
- **If generation stalls,** RDP in and check that the Flow tab is still signed in
  and `extension_connected` is true. Then run `/fk-doctor` with the admin key.

## Ubuntu Desktop instead of Windows

The same steps apply, with these differences:

- Use an Ubuntu 24.04 desktop image, and reach it with Chrome Remote Desktop or
  xrdp.
- Install tools with `apt install git python3-venv nodejs npm ffmpeg caddy`, and
  get Chrome from Google's `.deb`.
- Put the site block in `/etc/caddy/Caddyfile` and `systemctl reload caddy`.
- Start the agent from a `systemd --user` service in the desktop user's session.
  Enable lingering (`loginctl enable-linger <user>`) and set `DISPLAY` so it
  shares the session Chrome runs in.
