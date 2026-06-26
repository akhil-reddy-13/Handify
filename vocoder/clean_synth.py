"""EDM lead synth — supersaw, filter sweep, clean low end."""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

TWO_PI = 2.0 * math.pi
DETUNE_CENTS = (-9.0, 0.0, 9.0)


class CleanNoteSynth:
    """Supersaw lead with brightness-controlled filter — EDM-style."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sr = sample_rate
        self._phases = [0.0, 0.0, 0.0]
        self._sub_phase = 0.0
        self._hz = 440.0
        self._target_hz = 440.0
        self._env = 0.0
        self._brightness = 0.45
        self._filt_l = 0.0
        self._filt_r = 0.0
        self._cutoff = 1200.0
        self._lp_sos = signal.butter(2, 0.95, btype="low", output="sos")
        self._lp_zi = signal.sosfilt_zi(self._lp_sos)

    def set_target(self, hz: float, brightness: float, playing: bool, detune_cents: float = 0.0) -> None:
        bent = hz * (2.0 ** (detune_cents / 1200.0))
        self._target_hz = max(55.0, min(bent, 2000.0))
        self._brightness = max(0.0, min(1.0, brightness))
        if playing:
            self._env = min(1.0, self._env + 0.055)
        else:
            self._env *= 0.55

    def force_silent(self) -> None:
        self._env = 0.0
        self._filt_l = 0.0
        self._filt_r = 0.0
        self._lp_zi *= 0.0
        self._phases = [0.0, 0.0, 0.0]
        self._sub_phase = 0.0

    def _target_cutoff(self) -> float:
        # Pinch opens the filter — classic EDM brightness sweep.
        return 500.0 + self._brightness**1.4 * 9500.0

    def render(self, n: int, volume: float) -> np.ndarray:
        if self._env < 0.001:
            return np.zeros(n, dtype=np.float64)

        self._hz += 0.1 * (self._target_hz - self._hz)
        self._cutoff += 0.12 * (self._target_cutoff() - self._cutoff)
        alpha = 1.0 - math.exp(-TWO_PI * self._cutoff / self.sr)

        base_inc = self._hz / self.sr

        # Supersaw — 3 detuned voices.
        mix = np.zeros(n, dtype=np.float64)
        for vi, cents in enumerate(DETUNE_CENTS):
            ratio = 2.0 ** (cents / 1200.0)
            inc = base_inc * ratio
            phases = self._phases[vi] + inc * np.arange(1, n + 1, dtype=np.float64)
            self._phases[vi] = phases[-1] % 1.0
            saw = 2.0 * (phases % 1.0) - 1.0
            # Soft saturation per voice.
            mix += np.tanh(saw * 1.15)

        mix /= len(DETUNE_CENTS)
        mix *= 1.45

        # Quiet sub — solid EDM foundation.
        sub_inc = (self._hz * 0.5) / self.sr
        sub_ph = self._sub_phase + sub_inc * np.arange(1, n + 1, dtype=np.float64)
        self._sub_phase = sub_ph[-1] % 1.0
        sub = 0.18 * np.sin(TWO_PI * sub_ph)
        mix = mix * 0.9 + sub

        env = self._env * volume
        shaped = np.tanh(mix * (1.05 + self._brightness * 0.55)) * env

        # Block lowpass to tame saw aliasing.
        shaped, self._lp_zi = signal.sosfilt(self._lp_sos, shaped, zi=self._lp_zi)

        # Per-sample filter envelope for extra sweep character.
        out = np.empty(n, dtype=np.float64)
        fl = self._filt_l
        for i in range(n):
            fl += alpha * (shaped[i] - fl)
            out[i] = fl
        self._filt_l = fl

        return out
