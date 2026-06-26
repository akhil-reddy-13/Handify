#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    minor=$("$candidate" -c 'import sys; print(sys.version_info.minor)')
    major=$("$candidate" -c 'import sys; print(sys.version_info.major)')
    if [ "$major" = "3" ] && [ "$minor" -le 12 ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Need Python 3.10–3.12 (MediaPipe does not support 3.13 yet)."
  echo "Install with: brew install python@3.12"
  exit 1
fi

echo "Using $PYTHON ($($PYTHON --version))"

"$PYTHON" -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# MediaPipe Tasks API requires the hand landmarker model file.
MODEL="models/hand_landmarker.task"
if [ ! -f "$MODEL" ]; then
  mkdir -p models
  echo "Downloading hand landmarker model..."
  curl -fsSL -o "$MODEL" \
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
fi

echo ""
echo "Setup complete. Run: ./run.sh"
