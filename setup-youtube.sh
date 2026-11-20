#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
"${PYTHON:-python3}" -c 'import sys; sys.exit("YouTube setup requires Python 3.11 or newer") if sys.version_info < (3, 11) else None'
"${PYTHON:-python3}" -m venv .venv
.venv/bin/python -m pip install --upgrade "yt-dlp[default]"
printf '\nYouTube support installed. Run ./start.sh again.\n'
