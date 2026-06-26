#!/usr/bin/env python3
"""Hand Vocoder — right=notes, left=expression."""

from __future__ import annotations

import argparse
import sys
import time

import cv2

from vocoder.audio_engine import AudioState, HandSynthEngine
from vocoder.hand_tracker import DualControl, HandTracker
from vocoder.music_theory import SCALE_LABELS, MelodyGuide, PitchMapper, SONG_PRESETS
from vocoder.ui_overlay import draw_overlay

SCALE_HOTKEYS: dict[int, str] = {
    ord("1"): "c_major",
    ord("2"): "d_major",
    ord("3"): "f_minor",
    ord("4"): "minor",
    ord("5"): "pentatonic",
    ord("6"): "dorian",
}


def list_cameras(max_probe: int = 2) -> list[int]:
    found: list[int] = []
    for i in range(max_probe):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found or [0]


def screen_size() -> tuple[int, int]:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return w, h
    except Exception:
        return 1920, 1080


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--height", type=int, default=540)
    p.add_argument("--windowed", action="store_true",
                   help="Fixed-size window instead of fullscreen")
    p.add_argument("--scale", default="c_major",
                     choices=list(SCALE_LABELS.keys()))
    p.add_argument("--song", default="none", choices=["none", "stay"])
    p.add_argument("--low-midi", type=int, default=36, help="Low note (default C2)")
    p.add_argument("--high-midi", type=int, default=84, help="High note (default C6)")
    return p.parse_args()


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def apply_dual(audio: AudioState, dual: DualControl) -> None:
    p = dual.play
    if p.detected and p.active:
        audio.set_play(
            midi=p.midi, brightness=p.brightness, active=True,
            height=p.position, fingers=p.finger_count,
            degree=p.degree, octave=p.octave,
        )
    else:
        audio.clear_play()

    m = dual.mod
    audio.set_mod(m.height, m.detected)


def scale_label(key: str) -> str:
    return SCALE_LABELS.get(key, key)


def main() -> int:
    args = parse_args()
    fullscreen = not args.windowed
    if fullscreen:
        disp_w, disp_h = screen_size()
    else:
        disp_w, disp_h = args.width, args.height

    song = SONG_PRESETS.get(args.song) if args.song != "none" else None
    scale_key = song.scale_key if song else args.scale
    low, high = args.low_midi, args.high_midi

    pitch_mapper = PitchMapper(scale_key, low, high)
    melody = MelodyGuide(song.melody_midi if song else ())
    audio = AudioState()
    engine = HandSynthEngine(audio)
    tracker = HandTracker(pitch_mapper)
    scale_flash = ""

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, disp_w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, disp_h)
    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        return 1

    win = "Hand Vocoder"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    if fullscreen:
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(win, disp_w, disp_h)

    print("=" * 60)
    print("  HAND VOCODER")
    print("=" * 60)
    print(f"  Range: MIDI {low}–{high}  |  Scale: {scale_label(scale_key)}")
    print()
    print("  RIGHT — index finger selects notes (always plays when hand visible)")
    print("  MUTE: bring both hands together, or move right hand off screen")
    print("  LEFT — UP/DOWN = volume (sticks when hand leaves frame)")
    print("  [ ] keys = shift octave (notes on screen stay C→C within that octave)")
    print()
    print("  GESTURES:")
    print("    Cross arms = WAKANDA FOREVER")
    print("    Both hands up = rise + drop")
    print()
    print("  SCALE KEYS: 1=C  2=D  3=Fm  4=Cm  5=pent  6=dorian")
    print("  Q quit | V camera | M melody | +/- base volume")
    print("=" * 60)

    engine.start()
    cam_idx = args.camera
    cams = list_cameras()
    if cam_idx not in cams:
        cam_idx = cams[0]
    fps, n, t0 = 0.0, 0, time.time()
    scale_flash_until = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            if fh != disp_h or fw != disp_w:
                frame = cv2.resize(frame, (disp_w, disp_h), interpolation=cv2.INTER_LINEAR)
            frame, dual = tracker.process(frame)
            apply_dual(audio, dual)
            if dual.gesture:
                engine.trigger_drum(dual.gesture)

            if melody.enabled:
                with audio.lock:
                    audio.melody_mode = True
                    audio.melody_midi = melody.current_midi()

            n += 1
            now = time.time()
            if now - t0 >= 1.0:
                fps, n, t0 = n / (now - t0), 0, now

            display_scale = scale_flash if now < scale_flash_until else scale_label(scale_key)
            cv2.imshow(win, draw_overlay(
                frame, dual, audio, fps, display_scale,
                song.name if song else None,
            ))

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("v"), ord("V")) and len(cams) > 1:
                i = cams.index(cam_idx)
                cam_idx = cams[(i + 1) % len(cams)]
                cap.release()
                cap = cv2.VideoCapture(cam_idx)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, disp_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, disp_h)
            if key in (ord("m"), ord("M")):
                melody.enabled = not melody.enabled
                melody.reset()
                with audio.lock:
                    audio.melody_mode = melody.enabled
            if key == ord(" "):
                melody.advance()
            if key in (ord("+"), ord("=")):
                with audio.lock:
                    audio.volume = clamp(audio.volume + 0.05, 0.1, 1.0)
            if key == ord("-"):
                with audio.lock:
                    audio.volume = clamp(audio.volume - 0.05, 0.1, 1.0)
            if key == ord("["):
                tracker.bump_octave(-1)
            if key == ord("]"):
                tracker.bump_octave(1)
            if key in SCALE_HOTKEYS:
                scale_key = SCALE_HOTKEYS[key]
                tracker.set_scale(scale_key, low, high)
                scale_flash = scale_label(scale_key)
                scale_flash_until = time.time() + 1.5
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        tracker.close()
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
