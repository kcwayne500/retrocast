# Codex development instructions for RetroCast

- Read `README.md` and `docs/PROJECT_SPEC.md` when available before major changes.
- Priority is a **portable, small, headless-capable analog TV video lab**, not a general streaming platform.
- Keep the backend Python standard-library-first; frontend vanilla HTML/CSS/JavaScript; do not introduce Node/React/OBS/DB/Docker by default.
- Preserve Windows and Linux launchers and relative paths. Any optional dependency should have clear installation and error reporting.
- Implement and test preview features without requiring any HackRF hardware. Keep hardware features injectable/mockable and RF output **disabled by default**.
- Never silently enable RF, attach an antenna, or run an unshielded broadcast test. The HackRF output requires lawful, properly attenuated and DC-isolated bench setup. Do not assume minimum TX gain is zero power.
- Treat hardware status accurately: no claim of actual TV reception or audio without a documented physical test.
- YouTube ingestion must only use media the user is authorized to access/download. v1 is download-to-library, not live rebroadcast.
- Protect local data and credentials: never commit `.env`, downloaded media, `venv`, keys, GitHub tokens, or user photo references unless the user explicitly authorizes it.
- Keep a tracked demonstration video reachable after a fresh clone (fix original `media/*` ignore issue).
- Write/run tests for substantive changes (`python -m unittest discover -s tests -v`), and report what is verified vs not.
- Validate HackTV arguments against the installed version; official upstream location: https://codeberg.org/fsphil/hacktv.
- Avoid unrelated refactors during the first repository publication; first get a clean verified repository and push it to GitHub if authorized credentials are available.
