#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d venv ]; then
  ./setup.sh
fi

source venv/bin/activate
python hand_vocoder.py "$@"
