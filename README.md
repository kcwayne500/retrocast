# RetroCast — portable analog TV video lab

A tiny, browser-controlled, headless-friendly **local video → HackTV → HackRF One → NTSC-M TV** project. No OBS, Node, React, database, or required Python packages.

**Two modes**
- **Preview** (default): Upload a video or download one YouTube video, and preview it in the built-in monochrome browser display. **No radio signal is emitted.** The built-in test-card preview works with no video files.
- **HackRF TX** (opt-in): Launch HackTV to encode a stored video or test pattern as NTSC-M channel 3 or 4 (video carrier at 61.25 / 67.25 MHz). Requires an installed, working **HackTV binary**, an attached HackRF One, and a lawful, properly attenuated, DC-isolated RF test setup.

Actual TV hardware output **has not been tested here** because no HackRF/Quasar is attached to this environment. The UI and API can be tested without hardware.

## Quick start

### Linux (Ubuntu, Debian, Raspberry Pi OS)

1. Install **Python 3.10+**: `sudo apt update && sudo apt install python3` (and optionally `ffmpeg`).
2. Unzip the folder anywhere, open a terminal inside `RetroCast`.
3. Run `./start.sh` (or `sh start.sh`). **No pip install is needed.**
4. Visit **http://127.0.0.1:8765**. Select the included **retrocast_demo.mp4** from the library and press **START** in preview mode.

### Windows 10/11

1. Install Python **3.10+** from python.org (with Python launcher / PATH enabled).
2. Unzip the folder anywhere. Double-click **`start.bat`**, or run it in a terminal.
3. Visit **http://127.0.0.1:8765**.
4. Preview works on Windows. **HackTV RF output** requires a compatible Windows `hacktv.exe` and HackRF USB driver. Native Windows RF output and WSL2 USB passthrough have not been validated for this project. Preview needs only Python; verify your external HackTV build and driver separately before hardware use.

Moving the application: copy the entire `RetroCast` folder (including `media/` and optional `.env`). Delete `.venv/` first when changing operating systems, then run the appropriate launcher again. Start scripts use regular Python unless a local `.venv` was created for optional YouTube support. Recreate `.venv` with `setup-youtube` after moving between operating systems.

## What the controls do

- **FILE:** Upload MP4, MKV, AVI, MOV, WebM and other common files, or select a stored video from the library.
- **YOUTUBE:** Paste a single ordinary YouTube video URL and click **SAVE TO LIBRARY**. RetroCast uses **yt-dlp** to download a copy, usually at 480p or lower, then selects it from the library. Install the optional YouTube helper first: run `./setup-youtube.sh` on Linux or double-click `setup-youtube.bat` on Windows. Requires internet; YouTube may reject/limit downloads. Only download material you're authorized to use, and respect the service's terms and copyright.
- **TEST:** Built-in HackTV `test:colourbars` input (no video file required).
- **TV CHANNEL:** Choose NTSC-M channel 3 or 4.
- **OUTPUT MODE:** Browser preview, or opt-in RF hardware output.
- **LOOP VIDEO:** Automatically repeat playback in HackTV. Browser preview also loops by default.
- **START / STOP:** Control preview or HackTV subprocess.

**Note:** the preview approximates a black-and-white CRT; it isn't an actual decoded RF capture. Real TV reception is only verified by the physical television.

## HackTV / HackRF setup on Linux

Install a current HackTV build from [the upstream project](https://codeberg.org/fsphil/hacktv) or your distribution package, if available. On recent Ubuntu/Debian systems, try `sudo apt install hacktv` first. You'll also need libhackrf and FFmpeg libraries / a working HackRF installation. Verify in a terminal:

```sh
hacktv --help
hackrf_info
```

HackTV uses `-m m` for modulated NTSC-M (not `-m ntsc`, which is unmodulated baseband). 13.5 Msps is a documented NTSC sample rate. For channel 3, RetroCast assembles approximately:

```sh
hacktv -o hackrf -m m -s 13500000 -f 61250000 -g 0 -r /path/to/media/video.mp4
```

To enable RF mode, copy `.env.example` to `.env`, then set `RETROCAST_RF_ENABLED=1`. Restart RetroCast. The UI will also ask you to confirm the RF bench setup every time you start transmission. The app defaults to **TX VGA gain 0 dB** with the internal RF amplifier **off**. Explicit server configuration `RETROCAST_TX_GAIN` (0–47 dB) and `RETROCAST_TX_AMP` (0/1) controls these settings. For the confirmed shielded chamber setup, 47 and 1 select the maximum hardware gain settings. This does not specify or measure output wattage, and maximum gain may distort the TV signal. See [HackRF gain controls](https://hackrf.readthedocs.io/en/latest/setting_gain.html). These settings are *not* a guarantee of RF compliance or receiver safety.

### RF safety / legal limits

**Do not simply attach an antenna and broadcast on TV channel 3 or 4.** Television frequencies are regulated, and even low-power transmissions may cause interference. Use an authorized setup and **properly attenuated and DC-isolated RF coupling**, with the receiver's antenna/input characteristics checked. **Do not directly wire the HackRF output to the TV's antenna terminals:** HackTV explicitly warns that AV equipment can supply DC or other signals harmful to the SDR, or receive excessive power from it. Obtain appropriate RF attenuator, DC block and impedance matching as needed, and verify isolation and power before connection.

## Optional YouTube setup

Optional YouTube support requires **Python 3.11+**, while the core app remains Python 3.10+. On Linux, run `./setup-youtube.sh`; on Windows double-click `setup-youtube.bat`. These create a local `.venv` containing yt-dlp and its default extras, then the regular start script detects and uses it. FFmpeg is recommended for merging formats: on Ubuntu install with `sudo apt install ffmpeg`; on Windows place `ffmpeg.exe` on PATH. For full YouTube support, upstream also requires its EJS helper (included in the default extras) and a supported JavaScript runtime; Deno on PATH is the default. See [yt-dlp dependencies](https://github.com/yt-dlp/yt-dlp#dependencies). These dependencies are optional for RetroCast preview and local files. YouTube can change its restrictions at any time.

## Configuration

The application reads `.env` from its own directory. All values are optional; environment variables override `.env` values.

```ini
RETROCAST_RF_ENABLED=0
RETROCAST_HOST=127.0.0.1
RETROCAST_PORT=8765
RETROCAST_HACKTV_BIN=hacktv
RETROCAST_MEDIA_DIR=media
RETROCAST_MAX_UPLOAD_MB=1024
```

For a custom HackTV executable, set an absolute path in `RETROCAST_HACKTV_BIN`. Use `RETROCAST_MEDIA_DIR` to relocate uploaded files. The default media directory is relative to the project folder so everything moves together.

**Local security:** By default, RetroCast binds only to `127.0.0.1`. Do not expose this development-style web server to the public internet. For LAN headless control, you can set `RETROCAST_HOST=0.0.0.0`, **but it has no login/authentication**; allow access only from a trusted, restricted LAN. Consider SSH port forwarding instead.

## Portable project layout

```text
RetroCast/
├── app.py                 # standard-library HTTP API + HackTV controller
├── templates/index.html   # frontend
├── static/style.css       # responsive CRT UI
├── static/app.js          # vanilla JS frontend
├── start.sh               # Linux launcher
├── start.bat              # Windows launcher
├── setup-youtube.sh       # optional yt-dlp installer for Linux
├── setup-youtube.bat      # optional yt-dlp installer for Windows
├── .env.example           # settings template
├── media/                 # local video storage
└── tests/test_app.py      # API / command tests
```

No absolute machine paths are embedded in the project. The app uses only the Python standard library. No `.venv` is needed for uploads, playback preview, or RF control. The optional `setup-youtube` installer creates `.venv` and installs `yt-dlp`, which is imported as a Python module.

## API (useful for scripts)

- `GET /api/health` — health check
- `GET /api/status` — RF status, diagnostics, downloads
- `GET /api/media` — list locally stored files
- `POST /api/upload?filename=demo.mp4` — raw video bytes (header `Content-Type: application/octet-stream`)
- `POST /api/youtube` — JSON `{ "url": "https://youtu.be/..." }` (asynchronous; poll `/api/status` for job status)
- `POST /api/play` — JSON `{ "mode":"preview", "source":"file", "name":"video.mp4", "channel":"3", "repeat":true }`
- `POST /api/play` — JSON `{ "mode":"rf", "source":"test", "channel":"3", "repeat":true, "bench_confirmed":true }` (only after RF opt-in)
- `POST /api/stop` — stop output
- `DELETE /api/media/<name>` — delete a file (not during its playback)

Example local test:

```sh
curl -s http://127.0.0.1:8765/api/health
curl -s -X POST http://127.0.0.1:8765/api/play -H 'Content-Type: application/json' -d '{"mode":"preview","source":"test","channel":"3"}'
```

## Test

With Python 3.10+ installed, no other packages are required for tests:

```sh
python -m unittest discover -s tests -v
```

## Current limitations

- Browser preview is a grayscale representation, not a decoded live RF feed. Some video containers (e.g. MKV and AVI) can work with HackTV but not play in a particular web browser; MP4 is a good preview choice.
- YouTube clips download first; **no direct YouTube live-stream relay yet**.
- This MVP has no streaming playlist, authentication, RF receiver feedback, or transmitter auto-detection.
- The HackTV process command is based on HackTV's documented CLI; individual builds and USB configurations may require adjustments.
- Windows hardware output is not bundled as a native executable, because HackTV and HackRF drivers are external system dependencies.
- A valid media extension does not guarantee the file contains a playable video; FFmpeg/HackTV reports decode failures.

## References

- HackTV upstream: https://codeberg.org/fsphil/hacktv
- HackTV command reference: https://manpages.debian.org/unstable/hacktv/hacktv.1.en.html
- yt-dlp: https://github.com/yt-dlp/yt-dlp

## Included assets and licensing

The bundled demo is a generated SMPTE color-bar test card with a synthesized 440 Hz tone. It contains no third-party video or recorded audio. See `docs/DEMO.md` for the generation command. No project license has been assigned. Inter and Tailwind retain their included third-party licenses. Personal TV photos, handoff archives, credentials, and downloaded videos are excluded from this repository.

## UI styling

The studio uses Tailwind CSS 4.3.5 and the Inter variable font. The compiled stylesheet and font are served locally, so normal startup needs no Node installation, CSS build step, or CDN connection.

To change the design, edit `templates/index.html`, `static/app.js`, or `styles/input.css`. Download the appropriate [Tailwind standalone CLI v4.3.5](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.5) for your development machine, then rebuild from the repository root:

```sh
tailwindcss -i styles/input.css -o static/style.css --minify
```

Commit the generated `static/style.css` along with your source changes. `static/inter.woff2` comes from [Inter](https://github.com/rsms/inter); its SIL Open Font License and Tailwind's MIT license are included in `licenses/`.
