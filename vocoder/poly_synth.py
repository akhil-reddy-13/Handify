"""Polyphonic hand synth — one voice per hand."""

from __future__ import annotations

import numpy as np

from vocoder.clean_synth import CleanNoteSynth


class PolyHandSynth:
    """Up to two clean voices (left + right hand)."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.voices = {
            "left": CleanNoteSynth(sample_rate),
            "right": CleanNoteSynth(sample_rate),
        }

    def render(
        self,
        n: int,
        volume: float,
        left: tuple[float, float, bool] | None,
        right: tuple[float, float, bool] | None,
    ) -> np.ndarray:
        """Each tuple: (hz, brightness, playing)."""
        out = np.zeros(n, dtype=np.float64)
        active = 0
        for key, state in (("left", left), ("right", right)):
            voice = self.voices[key]
            if state is None:
                voice.force_silent()
                continue
            hz, br, playing = state
            voice.set_target(hz, br, playing)
            if not playing:
                voice.force_silent()
            elif playing:
                active += 1
        per_voice = volume / max(active, 1)
        for key, state in (("left", left), ("right", right)):
            if state is None:
                continue
            _, _, playing = state
            if playing:
                out += self.voices[key].render(n, per_voice)
        return out
