"""Memorable pose triggers — Wakanda, rise."""

from __future__ import annotations

import time

import numpy as np

WRIST, MIDDLE_MCP = 0, 9

GESTURE_COOLDOWN = 2.8

GESTURE_LABELS = {
    "wakanda": "WAKANDA FOREVER",
    "rise": "RISE DROP",
}


class GestureDetector:
    def __init__(self) -> None:
        self._wakanda_streak = 0
        self._rise_streak = 0
        self._cooldown_until: dict[str, float] = {}
        self.flash_name = ""
        self.flash_until = 0.0

    def _ready(self, name: str) -> bool:
        return time.perf_counter() >= self._cooldown_until.get(name, 0.0)

    def _fire(self, name: str) -> str:
        now = time.perf_counter()
        self._cooldown_until[name] = now + GESTURE_COOLDOWN
        self.flash_name = GESTURE_LABELS.get(name, name.upper())
        self.flash_until = now + 1.5
        return name

    @staticmethod
    def _dist(a, b) -> float:
        return float(np.hypot(a.x - b.x, a.y - b.y))

    def _detect_wakanda(self, hands: list) -> bool:
        if len(hands) < 2:
            self._wakanda_streak = 0
            return False
        best = 999.0
        for i in range(len(hands)):
            for j in range(i + 1, len(hands)):
                best = min(best, self._dist(hands[i][WRIST], hands[j][WRIST]))
        if best > 0.16:
            self._wakanda_streak = 0
            return False
        cy = (hands[0][WRIST].y + hands[1][WRIST].y) / 2.0
        if not (0.32 < cy < 0.72):
            self._wakanda_streak = 0
            return False
        self._wakanda_streak += 1
        return self._wakanda_streak >= 6

    def _detect_rise(self, hands: list) -> bool:
        if len(hands) < 2:
            self._rise_streak = 0
            return False
        ys = [h[WRIST].y for h in hands]
        if max(ys) > 0.38:
            self._rise_streak = 0
            return False
        if self._dist(hands[0][WRIST], hands[1][WRIST]) < 0.22:
            self._rise_streak = 0
            return False
        self._rise_streak += 1
        return self._rise_streak >= 5

    def update(self, all_hands: list, play_lm) -> str:
        del play_lm
        now = time.perf_counter()
        if now >= self.flash_until:
            self.flash_name = ""

        if self._detect_wakanda(all_hands) and self._ready("wakanda"):
            self._wakanda_streak = 0
            return self._fire("wakanda")

        if self._detect_rise(all_hands) and self._ready("rise"):
            self._rise_streak = 0
            return self._fire("rise")

        return ""
