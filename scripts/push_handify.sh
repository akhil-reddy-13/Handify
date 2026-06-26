#!/usr/bin/env bash
# Build Handify repo with many small commits + pushes for GitHub activity.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="/tmp/handify_push.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Handify push started $(date) ==="

commit_push() {
  local msg="$1"
  shift
  if [[ $# -gt 0 ]]; then
    git add -- "$@"
  fi
  if git diff --cached --quiet; then
    echo "[skip] nothing staged: $msg"
    return 0
  fi
  git commit -m "$msg"
  git push origin main
  echo "[ok] $msg"
  sleep 0.8
}

git init
git branch -M main

if git remote get-url origin >/dev/null 2>&1; then
  echo "remote origin already set"
else
  gh repo create Handify --public \
    --description "Handify — hand-controlled music synth (camera + MediaPipe + OpenCV)" \
    --source=. --remote=origin --push=false || \
  gh repo create Handify --public \
    --description "Handify — hand-controlled music synth" \
    --source=. --remote=origin --push=false
fi

# 1–18: scaffold the project file-by-file
commit_push "chore: add gitignore" .gitignore
commit_push "chore: pin python dependencies" requirements.txt
commit_push "feat: create vocoder package" vocoder/__init__.py
commit_push "feat: add music theory and scale mapping" vocoder/music_theory.py
commit_push "feat: add clean supersaw synthesizer" vocoder/clean_synth.py
commit_push "feat: add polyphonic synth helper" vocoder/poly_synth.py
commit_push "feat: add synthesized drum patterns" vocoder/drum_engine.py
commit_push "feat: add wakanda and rise gesture detector" vocoder/gesture_detector.py
commit_push "feat: add real-time audio engine" vocoder/audio_engine.py
commit_push "feat: add camera hud overlay" vocoder/ui_overlay.py
commit_push "feat: add midi and osc output helpers" vocoder/midi_out.py vocoder/osc_out.py
commit_push "feat: add mediapipe dual-hand tracker" vocoder/hand_tracker.py
commit_push "feat: add main application entrypoint" hand_vocoder.py
commit_push "chore: add setup script with model download" setup.sh
commit_push "chore: add run launcher" run.sh
commit_push "docs: add harmony setup notes" HARMONY_SETUP.md
mkdir -p models
touch models/.gitkeep
commit_push "chore: add models directory placeholder" models/.gitkeep

# README built up across several commits
cat > README.md <<'EOF'
# Handify

Hand-controlled music synth. Move your hands, play notes.
EOF
commit_push "docs: seed readme" README.md

cat >> README.md <<'EOF'

```bash
./setup.sh
./run.sh
```
EOF
commit_push "docs: add quick start commands" README.md

cat >> README.md <<'EOF'

## Right hand — notes

- Index fingertip selects pitch across on-screen note bars (C→C octave)
- `[` `]` shift octave range
- Keys `1`–`6` switch scale live
EOF
commit_push "docs: document right-hand note controls" README.md

cat >> README.md <<'EOF'

## Left hand — volume

- Up/down = volume fader (sticks when hand leaves frame)
EOF
commit_push "docs: document left-hand volume" README.md

cat >> README.md <<'EOF'

## Mute

- Bring both hands together
- Move right hand off screen
EOF
commit_push "docs: document mute gestures" README.md

cat >> README.md <<'EOF'

## Drum gestures

| Gesture | Sound |
|---------|-------|
| Cross arms | WAKANDA FOREVER |
| Both hands up | Rise + drop |
EOF
commit_push "docs: document drum gestures" README.md

cat >> README.md <<'EOF'

## Audio

Clean supersaw lead + synthesized drums — no mic, no grainy vocoder processing.
EOF
commit_push "docs: document audio engine" README.md

cat > LICENSE <<'EOF'
MIT License

Copyright (c) 2026 Akhil Reddy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
commit_push "chore: add MIT license" LICENSE

# Touch a few files for final polish commits (tiny comment headers)
python3 - <<'PY'
from pathlib import Path
p = Path("vocoder/__init__.py")
text = p.read_text()
if "Handify" not in text:
    p.write_text('"""Handify — hand-controlled music synth."""\n' + text.lstrip())
PY
commit_push "chore: brand vocoder package as Handify" vocoder/__init__.py

python3 - <<'PY'
from pathlib import Path
p = Path("hand_vocoder.py")
t = p.read_text()
if not t.startswith("# Handify"):
    t = "# Handify — hand-controlled music synth\n" + t
p.write_text(t)
PY
commit_push "chore: tag main app as Handify" hand_vocoder.py

cat >> README.md <<'EOF'

## Requirements

- Python 3.10+
- Webcam
- macOS / Linux (tested on macOS)
EOF
commit_push "docs: add requirements section" README.md

cat >> README.md <<'EOF'

---

Made with MediaPipe, OpenCV, and sounddevice.
EOF
commit_push "docs: finalize readme footer" README.md

# Ensure everything is committed
commit_push "chore: sync working tree" .

echo "=== Done: $(git log --oneline | wc -l | tr -d ' ') commits on main ==="
gh repo view --web 2>/dev/null || gh repo view
echo "=== Log: $LOG ==="
