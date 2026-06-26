"""Synthesized EDM drums — triggered by hand gestures."""

from __future__ import annotations

import math

import numpy as np

TWO_PI = 2.0 * math.pi
BPM = 108.0


def _synth_kick(sr: int, dur: float = 0.22) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    pitch = 90.0 * np.exp(-t * 28.0) + 42.0
    phase = np.cumsum(TWO_PI * pitch / sr)
    body = np.sin(phase) * np.exp(-t * 11.0)
    click = np.sin(TWO_PI * 800.0 * t) * np.exp(-t * 80.0) * 0.25
    return (body * 0.95 + click) * 0.9


def _synth_snare(sr: int, dur: float = 0.16) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n) * np.exp(-t * 22.0)
    tone = np.sin(TWO_PI * 190.0 * t) * np.exp(-t * 18.0)
    return (noise * 0.65 + tone * 0.45) * 0.75


def _synth_hat(sr: int, dur: float = 0.05) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(11)
    return rng.standard_normal(n) * np.exp(-t * 55.0) * 0.35


def _synth_clap(sr: int, dur: float = 0.12) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(3)
    return rng.standard_normal(n) * np.exp(-t * 35.0) * 0.7


def _synth_808(sr: int, dur: float = 0.55) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    return np.sin(TWO_PI * 44.0 * t) * np.exp(-t * 3.8) * 0.98


def _synth_crash(sr: int, dur: float = 1.4) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(19)
    noise = rng.standard_normal(n)
    env = np.exp(-t * 2.8)
    tone = np.sin(TWO_PI * 320.0 * t) * np.exp(-t * 5.0)
    return (noise * 0.55 + tone * 0.35) * env * 0.85


def _synth_tom(sr: int, freq: float = 120.0, dur: float = 0.2) -> np.ndarray:
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    pitch = freq * np.exp(-t * 18.0) + 50.0
    phase = np.cumsum(TWO_PI * pitch / sr)
    return np.sin(phase) * np.exp(-t * 14.0) * 0.7


def _step_samples(sr: int, steps: int = 1) -> int:
    beat = 60.0 / BPM
    return int(sr * beat * 0.25 * steps)


def _build_wakanda(sr: int) -> list[tuple[int, str, float]]:
    """Tribal driving beat — original Wakanda feel."""
    events: list[tuple[int, str, float]] = []
    beat = 60.0 / 128.0
    s = int(sr * beat * 0.25)
    grid = (
        "k...k...k...k..."
        "....s.......s..."
        "hhhhhhhhhhhhhhhh"
        ".k...k...k...k.."
        "....s...s...s...s"
        "hhhhhhhhhhhhhhhh"
    )
    for i, ch in enumerate(grid):
        t = i * s // 4
        if ch == "k":
            events.append((t, "kick", 1.0))
        elif ch == "s":
            events.append((t, "snare", 0.9))
        elif ch == "h":
            events.append((t, "hat", 0.55))
    return events


def _build_rise(sr: int) -> list[tuple[int, str, float]]:
    events: list[tuple[int, str, float]] = []
    s = _step_samples(sr, steps=1)
    beat = int(s * 4)
    for i in range(12):
        events.append((i * beat // 12, "hat", 0.3 + i * 0.04))
        if i > 6:
            events.append((i * beat // 12, "snare", 0.35 + (i - 6) * 0.08))
    drop = beat * 2
    events.append((drop, "808", 1.0))
    events.append((drop, "kick", 1.0))
    events.append((drop, "clap", 1.0))
    for i in range(6):
        events.append((drop + i * beat // 2, "kick", 0.9))
        events.append((drop + i * beat // 2 + beat // 4, "snare", 0.8))
    return events



PATTERNS: dict[str, list[tuple[int, str, float]]] = {}


def _ensure_patterns(sr: int) -> None:
    if PATTERNS:
        return
    PATTERNS["wakanda"] = _build_wakanda(sr)
    PATTERNS["rise"] = _build_rise(sr)


class DrumEngine:
    def __init__(self, sample_rate: int = 44100) -> None:
        self.sr = sample_rate
        self._clock = 0
        self._hits: list[tuple[int, np.ndarray]] = []
        self._oneshots: dict[str, np.ndarray] = {}
        _ensure_patterns(sample_rate)

    def _sample(self, name: str) -> np.ndarray:
        if name not in self._oneshots:
            makers = {
                "kick": _synth_kick, "snare": _synth_snare, "hat": _synth_hat,
                "clap": _synth_clap, "808": _synth_808, "crash": _synth_crash,
                "tom": lambda sr: _synth_tom(sr, 110.0),
            }
            self._oneshots[name] = makers[name](self.sr)
        return self._oneshots[name]

    def trigger(self, pattern: str, volume: float = 0.85) -> None:
        if pattern not in PATTERNS:
            return
        base = self._clock
        for offset, drum, vel in PATTERNS[pattern]:
            hit = self._sample(drum) * (vel * volume)
            self._hits.append((base + offset, hit))

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float64)
        end = self._clock + n
        keep: list[tuple[int, np.ndarray]] = []
        for start, hit in self._hits:
            if start >= end:
                keep.append((start, hit))
                continue
            offset = start - self._clock
            if offset < 0:
                hit = hit[-offset:]
                offset = 0
            if offset >= n:
                keep.append((start, hit))
                continue
            ln = min(len(hit), n - offset)
            out[offset : offset + ln] += hit[:ln]
            if ln < len(hit):
                keep.append((start + ln, hit[ln:]))
        self._hits = keep
        self._clock += n
        return out
