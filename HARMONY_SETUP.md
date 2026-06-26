# Hand Vocoder — MediaPipe hand tracking + optional MIDI/OSC bridges

## What the TikTok build uses

| Tool | Role | Can we use it? |
|------|------|----------------|
| **MediaPipe** | Hand skeleton tracking | ✅ Already in this project |
| **TouchDesigner** | Visuals + audio routing | ✅ Via **OSC** (`--osc`) |
| **Antares Harmony Engine** | Pro vocal autotune/harmony | ✅ Via **MIDI** (`--midi`) |

We can't bundle TouchDesigner or Antares (paid/commercial), but we can **feed them** exactly what they need from your camera.

---

## Mode 1: Built-in hand synth (default)

```bash
./run.sh
```

Clean synth tone from your hand. No extra software.

---

## Mode 2: Antares Harmony Engine (the real vocal sound)

This is the closest match to the viral demo — **you sing**, Harmony Engine autotunes you, **your hand picks the notes**.

### Setup (Logic / Ableton / Pro Tools)

1. Install [Harmony Engine](https://www.antaresaudio.com/) (or Auto-Tune if you have it).
2. Create an **audio track** with your mic → insert **Harmony Engine**.
3. Set Harmony Source to **MIDI Omni** or **Chord by MIDI** ([Antares guide](https://help.antarestech.com/hc/en-us/articles/41109310429332-Pro-Tools-How-to-configure-MIDI-control-of-Harmony-Engine)).
4. Create a **MIDI track** routed to Harmony Engine.
5. Run hand tracking with MIDI out:

```bash
./run.sh --mode midi --song stay
```

6. Set the MIDI track input to **"Hand Vocoder"** (virtual port).
7. Play the instrumental in headphones, **sing**, move your hand to hit notes.

Your hand sends MIDI note + velocity (pinch = louder/brighter). Fist = note off.

### MIDI mapping

| MIDI | Source |
|------|--------|
| Note | Fingers + hand height → scale note |
| Velocity | Pinch brightness |
| CC 1 | Hand height (0–127) |
| CC 2 | Pinch / brightness |
| CC 3 | Finger count |

---

## Mode 3: TouchDesigner

Inspired by [ejfox/hand-midi-controller](https://github.com/ejfox/hand-midi-controller).

```bash
./run.sh --mode osc
# or both:
./run.sh --mode both --osc-port 7000
```

### TouchDesigner setup

1. Add an **OSC In CHOP** → Network port `7000`.
2. Map channels:

| OSC address | Data |
|-------------|------|
| `/hand/note` | MIDI note number |
| `/hand/active` | 1 = playing, 0 = mute |
| `/hand/fingers` | Finger count |
| `/hand/y` | Hand height (0–1) |
| `/hand/pinch` | Pinch / brightness |
| `/hand/x` | Hand horizontal |

3. Pipe `/hand/note` into your synth or into MIDI Out CHOP → Harmony Engine.
4. Use MediaPipe-style skeleton from the OpenCV window, or rebuild visuals in TD from OSC.

---

## Mode 4: Everything at once

```bash
./run.sh --mode both --song stay
```

- Local synth preview (quiet with `--no-synth`)
- MIDI → DAW / Harmony Engine
- OSC → TouchDesigner

---

## Gestures (all modes)

| Gesture | Effect |
|---------|--------|
| 1–5 fingers | Pick note on scale |
| Hand UP/DOWN | Fine-tune pitch |
| Pinch | Brightness / MIDI velocity |
| Fist | Mute / note off |
| No hand | Silent |

---

## Requirements for MIDI/OSC modes

```bash
pip install python-rtmidi python-osc
```

Already included if you re-run `./setup.sh`.
