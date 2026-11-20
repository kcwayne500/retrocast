# RetroCast — Product specification and engineering brief

## 1. What are we building?

**RetroCast** is a tiny, portable, browser-controlled, optionally headless service that takes an ordinary video file (or a downloaded YouTube clip) and makes it displayable on a vintage analog NTSC television via **HackTV + a HackRF One**. Initial target is the user's small **Quasar black-and-white portable television** shown in `references/quasar-original.webp`. The user wants to put a source device beside the TV, load a demo video and see it on the CRT.

The owner initially wanted an extremely inexpensive self-contained video RF transmitter module, something analogous in simplicity to a CC1101 board, not an expensive general-purpose SDR. We discussed cheap RF modulators/transmitters, then chose HackRF One **for the proof of concept** because it can generate analog TV waveforms; the architecture should permit a cheaper dedicated transmitter or wired modulator backend later.

**Current engineering focus is the repository/handoff**, not purchasing hardware or transmitting over the air.

## 2. Product principles

- **Lightweight:** Python standard library core; HTML/CSS/vanilla JS frontend. No mandatory Flask/Node/React/OBS/DB/Docker.
- **Portable:** Everything in a moveable directory; no hardcoded absolute paths; `.env.example`; on Windows use `start.bat`; on Linux use `start.sh`. Optional Python virtual environment is local and recreated per OS.
- **Headless:** Runs without desktop GUI; browser manages it locally or on a restricted LAN. Default bind is `127.0.0.1`; do not open it publicly.
- **Simple operator experience:** upload/select MP4 and other media, choose test card or YouTube URL, channel 3 or 4, loop, start/stop, and see status/logs.
- **Works without SDR:** preview mode must be fully usable without HackRF or HackTV.
- **Safety:** RF output opt-in; isolate and attenuate lab RF; no claim of license-free OTA broadcasting.
- **Future-proof RF interface:** keep HackTV/HackRF as a swappable output adapter; later could drive an inexpensive NTSC-M modulator/transmitter that has validated inputs and legally compliant use.

## 3. Intended workflow

1. Copy RetroCast to Windows laptop or Ubuntu mini-PC.
2. Execute `start.bat` or `./start.sh` (or `python app.py`).
3. Open `http://127.0.0.1:8765`; optionally grant trusted-LAN access only when appropriately protected.
4. Upload a video or select the bundled demo; alternatively paste a single YouTube video link and let optional yt-dlp download it.
5. Select **Preview** to check source and UI without any radio emission.
6. For a permitted isolated bench setup with attached HackRF and working HackTV, explicitly enable hardware TX and select RF mode.
7. Tune the vintage NTSC TV to the matching channel; verify image/audio physically (pending hardware test).

### Signal chain

```text
Local file  ────────────────┐
                            ├→ Python HTTP service/media library
YouTube URL → yt-dlp → file ┘         │
                                      ├→ Browser monochrome preview (no RF)
                                      └→ HackTV NTSC-M encoding → HackRF USB
                                                    → attenuated & DC-isolated RF test path
                                                    → Quasar analog TV tuner
```

NOT a normal FM receiver. The TV expects NTSC-M analog TV waveform, including picture carrier and audio subcarrier if sound is desired. Channel 3 nominal video carrier **61.25 MHz**; channel 4 **67.25 MHz**. RF engineering/TV input details must be validated physically; do not assume what antenna socket the photographed set has.

## 4. v1 features (already present in supplied source)

- HTTP backend on Python 3.10+ with no mandatory pip packages, using `ThreadingHTTPServer`.
- Local media directory, upload, list, delete, playback selection.
- Main responsive browser dashboard with grayscale TV preview and health/status.
- `test:colourbars` built-in source for HackTV and preview.
- NTSC-M channel 3/4 controls and a repeat option.
- Optional yt-dlp single-video download into the library; it does not relay live YouTube.
- Preview vs RF modes; opt-in `.env` gate and confirmation before launching RF.
- HackTV subprocess start/stop/log capture and basic diagnostics.
- Linux and Windows entry scripts, optional yt-dlp installers, tests.
- Included demo MP4 in original ZIP (but check Git ignore behavior before pushing).

## 5. Current source layout

```text
source/RetroCast/
  app.py
  README.md
  .env.example
  .gitignore
  templates/index.html
  static/app.js
  static/style.css
  start.sh
  start.bat
  setup-youtube.sh
  setup-youtube.bat
  media/.gitkeep
  media/retrocast_demo.mp4
  tests/test_app.py
```

The original archive is preserved at `archives/RetroCast-portable-v1.zip`.

## 6. API contract (current, preserve during repository conversion)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Frontend |
| GET | `/api/health` | Health check |
| GET | `/api/status` | Active playback / diagnostics / jobs / logs |
| GET | `/api/media` | List video files |
| GET | `/api/logs` | Recent log entries |
| GET | `/media/<name>` | Serve video with byte-range support |
| POST | `/api/upload?filename=demo.mp4` | Raw file upload |
| POST | `/api/youtube` | JSON YouTube URL; async save to library |
| POST | `/api/play` | Preview or RF start |
| POST | `/api/stop` | Stop |
| DELETE | `/api/media/<name>` | Remove video |

Example play request, **no RF**:

```sh
curl -X POST http://127.0.0.1:8765/api/play \
  -H 'Content-Type: application/json' \
  -d '{"mode":"preview","source":"test","channel":"3"}'
```

Do not put unsafe or unauthorized RF output in CI tests.

## 7. Hardware-output command (implementation detail; validate against installed HackTV version)

The application currently constructs a command shaped like:

```sh
hacktv -o hackrf -m m -s 13500000 -f 61250000 -g 0 -r /absolute/path/to/file.mp4
```

Mode `m` is the modulated NTSC-M mode documented in the original project. `-g 0` means minimum TX VGA gain; it does **not** mean zero RF output power. The command does not request the `-a` amplifier. Verify with `hacktv --help`/docs for the actual installed version before real use. Hardware is not bundled, and no radio was tested in the authoring environment.

Primary current HackTV project: https://codeberg.org/fsphil/hacktv (the `fsphil/hacktv` GitHub address is an archived move notice as of Oct 2026).  
Additional docs: https://manpages.debian.org/unstable/hacktv/hacktv.1.en.html  
Optional downloader: https://github.com/yt-dlp/yt-dlp

## 8. Acceptance criteria — GitHub handoff milestone

- [ ] Codex has read all handoff docs and reviewed source code.
- [ ] New repository has the app files in repository root and an `AGENTS.md`.
- [ ] Repository is **private by default**, and on the correct GitHub account.
- [ ] `README.md` contains one-command Windows/Linux startup, optional dep setup, limitations and safe hardware handling.
- [ ] `.gitignore` excludes `.env`, local media downloads, virtual environments and scratch artifacts; **demo MP4 survives fresh clone**.
- [ ] On available test machine `python -m unittest discover -s tests -v` passes.
- [ ] With TX disabled, local health/test-card and media preview work.
- [ ] If available, `gh` creates repo, pushes `main`, and remote URL/commit are verified.
- [ ] Any unverified item (Windows native HackTV, actual RF, actual Quasar reception, audio) is clearly labeled pending.

## 9. Roadmap (after initial repo push, not first-push blockers)

**Priority 1: stabilize:** unit tests; health diagnostics; startup portability; yt-dlp/Python version compatibility; sample in fresh clone; crash recovery and subprocess cleanup; limit file uploads/downloads and secure LAN exposure.

**Priority 2: hardware bring-up:** check HackTV build/driver path on Ubuntu and Windows; enumerate HackRF; test signal in isolated RF path at legal levels; capture real photo of Quasar playback and confirm audio.

**Priority 3: useful controls:** real progress feedback, playlists, scheduling/looping, video-to-4:3 handling, error messaging, volume, media diagnostics, optional live source inputs if justified.

**Priority 4: compact device:** investigate a low-cost dedicated NTSC-M modulator/transmitter with composite input. Add a replaceable backend for it without rewriting UI. Check NTSC-M compatibility and legal RF operation before selecting hardware.

**Deferred / out of scope now:** public website, multi-user cloud app, video DRM bypassing, direct desktop mirroring, bespoke RF waveform generation, unlicensed neighborhood-wide broadcast.

## 10. Source usage and publication

- User-provided original reference photo is in this handoff as context. Do **not** automatically commit it to any repo.
- UI screenshots are from the initial prototype and may be copied to repo docs if genuinely useful.
- YouTube videos downloaded at runtime belong in user storage, **not** a Git repo.
- Respect rights and terms for ingested media. Don't fetch unauthorized copyrighted content to add as demos.
- For private GitHub, do not add an arbitrary OSS license without owner's decision.
