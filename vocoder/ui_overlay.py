"""OpenCV UI overlay."""

from __future__ import annotations

import cv2

from vocoder.hand_tracker import DualControl


def draw_overlay(frame, dual: DualControl, audio, fps, scale, song):
    overlay = frame.copy()
    snap = audio.snapshot()
    p = dual.play

    cv2.rectangle(overlay, (10, 10), (460, 118), (20, 20, 20), -1)
    note = p.note_name if p.active else "—"
    expr = f"vol {snap['expr_vol']*100:.0f}%"
    oct_lbl = p.octave if p.detected else "3"
    lines = [
        f"HAND VOCODER  |  {fps:.0f} fps  |  {scale}",
        f"R: {note}  oct {oct_lbl}  |  L: {expr}",
        f"Out {snap['volume']*100:.0f}%  |  {dual.gesture_label or ('PLAYING' if snap['hand_active'] else 'silent')}",
    ]
    y = 32
    for i, line in enumerate(lines):
        cv2.putText(overlay, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55 if i else 0.65, (0, 255, 255) if i == 0 else (220, 220, 220),
                    2 if i == 0 else 1, cv2.LINE_AA)
        y += 22 if i == 0 else 20

    cv2.putText(overlay, "R=notes  L=vol(sticky)  1-6=scale  [ ]=octave  Q quit",
                (12, overlay.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 140, 140), 1, cv2.LINE_AA)
    return overlay
