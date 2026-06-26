"""Dual-hand tracking — right=notes, left=expression (height)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import HandLandmarksConnections

from vocoder.gesture_detector import GestureDetector
from vocoder.music_theory import PitchMapper, midi_to_name

WRIST, THUMB_TIP, THUMB_MCP, THUMB_IP = 0, 4, 2, 3
INDEX_MCP, INDEX_TIP, INDEX_PIP = 5, 8, 6
MIDDLE_MCP, MIDDLE_TIP, MIDDLE_PIP = 9, 12, 10
RING_MCP, RING_TIP, RING_PIP = 13, 16, 14
PINKY_MCP, PINKY_TIP, PINKY_PIP = 17, 20, 18
FINGER_NAMES = ("T", "I", "M", "R", "P")

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

PLAY_BONE, PLAY_JOINT = (0, 255, 0), (0, 0, 255)
MOD_BONE, MOD_JOINT = (255, 140, 0), (255, 0, 220)

DROPOUT_HOLD = 10
PLAY_DROPOUT_HOLD = 2
HANDS_TOGETHER_DIST = 0.14
NOTE_LADDER_TOP_FRAC = 0.02
NOTE_LADDER_BOTTOM_FRAC = 0.05
DEFAULT_OCTAVE_SLOT = 3
PLAY_SIDE_X = 0.5


@dataclass
class HandControl:
    detected: bool
    active: bool
    position: float
    midi: int
    note_name: str
    finger_count: int
    fingers_up: tuple[bool, bool, bool, bool, bool]
    pinch: float
    brightness: float
    degree: str
    octave: str
    x: float
    y: float


@dataclass
class ModHandControl:
    """Left hand — Y=volume only (any pose OK)."""
    detected: bool
    height: float
    x: float
    y: float


@dataclass
class DualControl:
    play: HandControl
    mod: ModHandControl
    gesture: str = ""
    gesture_label: str = ""


def _empty_play() -> HandControl:
    return HandControl(
        detected=False, active=False, position=0.5, midi=60, note_name="—",
        finger_count=0, fingers_up=(False,) * 5, pinch=0.0, brightness=0.35,
        degree="—", octave="—", x=0.75, y=0.5,
    )


def _neutral_mod() -> ModHandControl:
    return ModHandControl(detected=False, height=0.65, x=0.25, y=0.5)


def ensure_model(model_path: Path = DEFAULT_MODEL) -> Path:
    if model_path.is_file():
        return model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request
    print(f"Downloading hand model → {model_path}")
    urllib.request.urlretrieve(MODEL_URL, model_path)
    return model_path


def height_to_expression(height: float) -> tuple[float, float, float]:
    """Left hand height → volume only (simple up/down fader)."""
    h = max(0.0, min(1.0, height))
    return 0.04 + 0.96 * h, 0.0, 0.0


class HandTracker:
    def __init__(self, pitch_mapper: PitchMapper, model_path: Path | None = None) -> None:
        self.pitch_mapper = pitch_mapper
        self._t0 = time.perf_counter()
        self._frame_index = 0
        self._last = DualControl(_empty_play(), _neutral_mod())

        # Play hand (right on screen)
        self._p_p: deque[float] = deque(maxlen=4)
        self._p_was_active = False
        self._p_landmarks = None
        self._p_missed = 0
        self._p_last = _empty_play()
        self._octave_slot = DEFAULT_OCTAVE_SLOT
        self._octave_flash = 0.0

        # Mod hand (left on screen) — volume only
        self._m_y: deque[float] = deque(maxlen=8)
        self._m_landmarks = None
        self._m_missed = 0
        self._m_last = _neutral_mod()
        self._gestures = GestureDetector()

        model_path = ensure_model(model_path or DEFAULT_MODEL)
        opts = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.58,
            min_tracking_confidence=0.62,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(opts)

    def _ts(self) -> int:
        self._frame_index += 1
        return int((time.perf_counter() - self._t0) * 1000)

    @staticmethod
    def _lm_dist(a, b) -> float:
        return float(np.hypot(a.x - b.x, a.y - b.y))

    @staticmethod
    def _ladder_bounds_px(h: int) -> tuple[int, int]:
        top = max(8, int(h * NOTE_LADDER_TOP_FRAC))
        bottom = h - max(16, int(h * NOTE_LADDER_BOTTOM_FRAC))
        return top, bottom

    @staticmethod
    def _ladder_height_from_tip_y(tip_y: float, frame_h: int) -> float:
        """Index tip pixel → 0–1 ladder coordinate (bottom=0, top=1)."""
        top, bottom = HandTracker._ladder_bounds_px(frame_h)
        span = max(1, bottom - top)
        py = max(0.0, min(1.0, tip_y)) * frame_h
        return max(0.0, min(1.0, (bottom - py) / span))

    @staticmethod
    def _mod_height(landmarks) -> float:
        """Works with fist — wrist + palm center."""
        w = landmarks[WRIST]
        mid = landmarks[MIDDLE_MCP]
        y = w.y * 0.55 + mid.y * 0.45
        return max(0.0, min(1.0, 1.0 - y))

    def set_scale(self, scale_key: str, low_midi: int, high_midi: int) -> None:
        self.pitch_mapper.set_scale(scale_key, low_midi, high_midi)

    def bump_octave(self, delta: int) -> None:
        self._octave_slot = max(1, min(5, self._octave_slot + delta))
        self._octave_flash = time.perf_counter() + 1.2

    @property
    def octave_slot(self) -> int:
        return self._octave_slot

    @staticmethod
    def _hands_together(play_lm, mod_lm) -> bool:
        if play_lm is None or mod_lm is None:
            return False
        pw, mw = play_lm[WRIST], mod_lm[WRIST]
        return float(np.hypot(pw.x - mw.x, pw.y - mw.y)) < HANDS_TOGETHER_DIST

    def _parse_play(self, landmarks, frame_h: int, *, hands_together: bool = False) -> HandControl:
        ladder_h = self._ladder_height_from_tip_y(landmarks[INDEX_TIP].y, frame_h)
        active = not hands_together
        pinch = float(np.hypot(
            landmarks[THUMB_TIP].x - landmarks[INDEX_TIP].x,
            landmarks[THUMB_TIP].y - landmarks[INDEX_TIP].y,
        ))
        self._p_p.append(pinch)
        pinch_avg = float(np.mean(self._p_p))

        pm = self.pitch_mapper
        slot = self._octave_slot
        if active:
            midi, zone = pm.height_to_octave_ladder(ladder_h, slot)
            brightness = max(0.05, min(1.0, (pinch_avg - 0.03) / 0.14))
            degree = pm.degree_name_at(min(zone, pm.num_degrees - 1))
            octave = pm.octave_label(slot)
        else:
            midi = self._p_last.midi if self._p_last.active else 60
            brightness = 0.0
            degree = self._p_last.degree
            octave = pm.octave_label(slot)

        self._p_was_active = active
        ctrl = HandControl(
            detected=True, active=active, position=ladder_h, midi=midi,
            note_name=midi_to_name(midi) if active else "—",
            finger_count=slot, fingers_up=(False,) * 5, pinch=pinch_avg,
            brightness=brightness,
            degree=degree if active else "—",
            octave=octave,
            x=landmarks[WRIST].x, y=1.0 - ladder_h,
        )
        self._p_last = ctrl
        return ctrl

    def _parse_mod(self, landmarks) -> ModHandControl:
        raw = self._mod_height(landmarks)
        self._m_y.append(raw)
        height = float(np.mean(self._m_y))
        ctrl = ModHandControl(
            detected=True, height=height,
            x=landmarks[WRIST].x, y=1.0 - height,
        )
        self._m_last = ctrl
        return ctrl

    def _draw_skeleton(self, frame, landmarks, w, h, bone, joint) -> None:
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
        for c in HandLandmarksConnections.HAND_CONNECTIONS:
            cv2.line(frame, pts[c.start], pts[c.end], bone, 2, cv2.LINE_AA)
        for px, py in pts:
            cv2.circle(frame, (px, py), 4, joint, -1, cv2.LINE_AA)

    def _draw_index_aim(self, frame, landmarks, w: int, h: int) -> None:
        tip = landmarks[INDEX_TIP]
        px, py = int(tip.x * w), int(tip.y * h)
        cv2.line(frame, (0, py), (w, py), (0, 255, 255), 1, cv2.LINE_AA)
        cv2.circle(frame, (px, py), 14, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.circle(frame, (px, py), 5, (0, 255, 255), -1, cv2.LINE_AA)

    def _draw_play_hud(self, frame, c: HandControl) -> None:
        if not c.detected:
            return
        if c.active:
            txt = f"RIGHT  {c.note_name}  (oct {c.octave})"
            color = (0, 255, 255)
        elif c.detected:
            txt = "RIGHT  muted"
            color = (140, 140, 140)
        cv2.putText(frame, txt, (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)
        if time.perf_counter() < self._octave_flash:
            cv2.putText(frame, f"octave → {c.octave}", (20, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 220, 80), 1, cv2.LINE_AA)

    def _draw_mod_hud(self, frame, m: ModHandControl) -> None:
        if not m.detected:
            return
        vol = height_to_expression(m.height)[0]
        cv2.putText(frame, f"LEFT  vol {vol*100:.0f}%", (20, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 180, 100), 2, cv2.LINE_AA)
        h, w = frame.shape[:2]
        bar_x, bar_top, bar_bot = 28, max(48, int(h * 0.06)), h - max(16, int(h * 0.05))
        cv2.rectangle(frame, (bar_x, bar_top), (bar_x + 18, bar_bot), (35, 35, 35), -1)
        fill = int(bar_top + (1.0 - m.height) * (bar_bot - bar_top))
        cv2.rectangle(frame, (bar_x, fill), (bar_x + 18, bar_bot), (255, 130, 40), -1)
        cv2.putText(frame, "LOUD", (bar_x + 26, bar_top + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 120), 1)
        cv2.putText(frame, "quiet", (bar_x + 26, bar_bot - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1)

    def _draw_note_ladder(self, frame, play: HandControl) -> None:
        """Split screen into equal scale-note bands — bottom=low, top=high."""
        h, w = frame.shape[:2]
        pm = self.pitch_mapper
        n = len(pm.octave_ladder_steps())
        top, bottom = self._ladder_bounds_px(h)
        zone_h = (bottom - top) / n
        slot = self._octave_slot
        labels = pm.octave_ladder_labels(slot)
        active_zone = -1
        if play.detected and play.active:
            _, active_zone = pm.height_to_octave_ladder(play.position, slot)

        x_lane = int(w * 0.52)
        overlay = frame.copy()

        for i in range(n):
            y0 = int(bottom - (i + 1) * zone_h)
            y1 = int(bottom - i * zone_h)
            is_active = play.active and i == active_zone
            color = (50, 90, 50) if is_active else (28, 28, 28)
            cv2.rectangle(overlay, (x_lane, y0), (w - 8, y1), color, -1)
            label = labels[i]
            ty = y0 + int(zone_h * 0.62)
            cv2.putText(overlay, label, (x_lane + 10, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62 if is_active else 0.5,
                        (0, 255, 255) if is_active else (160, 160, 160),
                        2 if is_active else 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        for i in range(1, n):
            y = int(bottom - i * zone_h)
            cv2.line(frame, (0, y), (w, y), (70, 70, 70), 1, cv2.LINE_AA)

        if play.detected:
            hand_y = int(bottom - play.position * (bottom - top))
            cv2.line(frame, (0, hand_y), (w, hand_y), (0, 255, 255), 1, cv2.LINE_AA)
            cv2.line(frame, (x_lane, hand_y), (w - 8, hand_y), (0, 255, 255), 2, cv2.LINE_AA)

        cv2.putText(frame, "index finger → note", (x_lane + 6, top + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.putText(frame, f"octave {pm.octave_label(slot)}", (w - 118, bottom + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 200, 100), 1)
        cv2.putText(frame, "[ ] = octave", (w - 118, bottom + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (140, 140, 140), 1)

    def _draw_help(self, frame) -> None:
        h, w = frame.shape[:2]
        lines = [
            "RIGHT — index finger = notes  |  mute: hands together or hand away",
            "LEFT — up/down = volume (stays when hand leaves)",
            "Keys 1-6 = scale  |  [ ] = octave",
            "Cross arms = Wakanda  |  Hands up = rise",
        ]
        y = h // 2 - 24
        cv2.rectangle(frame, (w // 2 - 260, y - 24), (w // 2 + 260, y + 96), (15, 15, 15), -1)
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (w // 2 - 240, y + i * 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55 if i == 0 else 0.48,
                        (0, 255, 255) if i == 0 else (190, 190, 190), 2 if i == 0 else 1, cv2.LINE_AA)

    def _draw_gesture_flash(self, frame, label: str) -> None:
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (w // 2 - 200, h // 2 - 40), (w // 2 + 200, h // 2 + 40), (20, 20, 20), -1)
        cv2.putText(frame, label, (w // 2 - 180, h // 2 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2, cv2.LINE_AA)

    def _draw_gesture_hints(self, frame) -> None:
        h, w = frame.shape[:2]
        cv2.putText(frame, "hands-together=mute  hand-away=mute",
                    (12, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "X-arms=Wakanda  hands-up=rise",
                    (12, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 255), 1, cv2.LINE_AA)

    def _draw_legend(self, frame: np.ndarray) -> None:
        pass  # replaced by _draw_note_ladder

    def process(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, DualControl]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self._ts(),
        )
        h, w = frame_bgr.shape[:2]
        play_lm, mod_lm = None, None
        play = _empty_play()
        mod = _neutral_mod()
        saw_play, saw_mod = False, False

        if result.hand_landmarks:
            for landmarks in result.hand_landmarks:
                if landmarks[WRIST].x >= PLAY_SIDE_X:
                    if play_lm is None:
                        play_lm = landmarks
                elif mod_lm is None:
                    mod_lm = landmarks

            if play_lm is not None:
                saw_play = True
                self._p_missed = 0
                self._p_landmarks = play_lm
                together = self._hands_together(play_lm, mod_lm)
                play = self._parse_play(play_lm, h, hands_together=together)
                self._draw_skeleton(frame_bgr, play_lm, w, h, PLAY_BONE, PLAY_JOINT)
                self._draw_index_aim(frame_bgr, play_lm, w, h)
                self._draw_play_hud(frame_bgr, play)

            if mod_lm is not None:
                saw_mod = True
                self._m_missed = 0
                self._m_landmarks = mod_lm
                mod = self._parse_mod(mod_lm)
                self._draw_skeleton(frame_bgr, mod_lm, w, h, MOD_BONE, MOD_JOINT)
                self._draw_mod_hud(frame_bgr, mod)

        if not saw_play:
            self._p_missed += 1
            if self._p_missed < PLAY_DROPOUT_HOLD and self._p_landmarks is not None:
                play = HandControl(
                    detected=True, active=False, position=self._p_last.position,
                    midi=self._p_last.midi, note_name="—",
                    finger_count=self._p_last.finger_count, fingers_up=self._p_last.fingers_up,
                    pinch=self._p_last.pinch, brightness=0.0,
                    degree="—", octave=self._p_last.octave,
                    x=self._p_last.x, y=self._p_last.y,
                )
                self._draw_skeleton(frame_bgr, self._p_landmarks, w, h, PLAY_BONE, PLAY_JOINT)
                self._draw_index_aim(frame_bgr, self._p_landmarks, w, h)
                self._draw_play_hud(frame_bgr, play)
            elif self._p_missed >= PLAY_DROPOUT_HOLD:
                self._reset_play()

        if not saw_mod:
            self._m_missed += 1
            if self._m_missed < DROPOUT_HOLD and self._m_landmarks is not None:
                mod = ModHandControl(
                    detected=True, height=self._m_last.height,
                    x=self._m_last.x, y=self._m_last.y,
                )
                self._draw_skeleton(frame_bgr, self._m_landmarks, w, h, MOD_BONE, MOD_JOINT)
                self._draw_mod_hud(frame_bgr, mod)
            elif self._m_missed >= DROPOUT_HOLD:
                self._reset_mod()

        if not saw_play and not saw_mod and self._p_missed >= DROPOUT_HOLD:
            self._draw_help(frame_bgr)

        all_hands = list(result.hand_landmarks) if result.hand_landmarks else []
        gesture = self._gestures.update(all_hands, play_lm)
        if gesture:
            self._draw_gesture_flash(frame_bgr, self._gestures.flash_name)
        elif time.perf_counter() < self._gestures.flash_until:
            self._draw_gesture_flash(frame_bgr, self._gestures.flash_name)

        self._draw_gesture_hints(frame_bgr)
        self._draw_note_ladder(frame_bgr, play)
        dual = DualControl(
            play=play, mod=mod, gesture=gesture,
            gesture_label=self._gestures.flash_name,
        )
        self._last = dual
        return frame_bgr, dual

    def _reset_play(self) -> None:
        self._p_p.clear()
        self._p_was_active = False
        self._p_landmarks = None

    def _reset_mod(self) -> None:
        self._m_y.clear()
        self._m_landmarks = None

    def close(self) -> None:
        self.landmarker.close()
