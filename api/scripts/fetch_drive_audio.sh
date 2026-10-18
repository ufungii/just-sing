#!/usr/bin/env bash
# Pull a shared Google Drive folder onto the server machine, into ml/data/downloads/.
# Usage: api/scripts/fetch_drive_audio.sh [folder-url-or-id]   (folder must be "anyone with the link")
# Then move/rename each song's files into ml/data/<song_id>/ (instrumental.mp3, vocals.mp3, song.json).
set -euo pipefail
FOLDER="${1:-1ol-1DKF_Y5NqpsjiiLk-wBcAF8ReHgpA}"
FOLDER="${FOLDER##*/folders/}"; FOLDER="${FOLDER%%\?*}"
OUT="$(dirname "$0")/../../ml/data/downloads"
mkdir -p "$OUT"
pipx run gdown --folder "https://drive.google.com/drive/folders/$FOLDER" -O "$OUT"
find "$OUT" -type f | sort
