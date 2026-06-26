"""Hand-controlled synth audio engine."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd

from vocoder.clean_synth import CleanNoteSynth
from vocoder.drum_engine import DrumEngine
from vocoder.hand_tracker import height_to_expression
from vocoder.music_theory import midi_to_hz


@dataclass
class AudioState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: bool = False
    midi: int = 60
    hz: float = midi_to_hz(60)
    brightness: float = 0.35
    height: float = 0.5
    finger_count: int = 0
    degree: str = "—"
    octave: str = "—"
    volume: float = 0.65
    melody_mode: bool = False
    melody_midi: int | None = None
    mod_detected: bool = False
    mod_height: float = 0.65
    expr_vol_latched: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.expr_vol_latched <= 0:
            self.expr_vol_latched = height_to_expression(0.65)[0]

    def set_play(
        self,
        *,
        midi: int,
        brightness: float,
        active: bool,
        height: float,
        fingers: int,
        degree: str,
        octave: str,
    ) -> None:
        with self.lock:
            self.active = active
            self.midi = midi
            self.hz = midi_to_hz(midi)
            self.brightness = brightness
            self.height = height
            self.finger_count = fingers
            self.degree = degree
            self.octave = octave

    def clear_play(self) -> None:
        with self.lock:
            self.active = False
            self.finger_count = 0

    def set_mod(self, height: float, detected: bool) -> None:
        with self.lock:
            self.mod_detected = detected
            if detected:
                self.mod_height = height
                self.expr_vol_latched = height_to_expression(height)[0]

    def snapshot(self) -> dict:
        with self.lock:
            playing = self.active or (self.melody_mode and self.melody_midi is not None)
            hz = midi_to_hz(self.melody_midi) if self.melody_mode and self.melody_midi else self.hz
            expr_vol = self.expr_vol_latched
            eff_volume = self.volume * expr_vol
            return {
                "hand_active": playing,
                "hand_detected": self.active,
                "target_midi": self.midi,
                "target_hz": hz,
                "brightness": self.brightness,
                "volume": eff_volume,
                "detune_cents": 0.0,
                "mod_detected": self.mod_detected,
                "mod_height": self.mod_height,
                "expr_vol": expr_vol,
                "melody_mode": self.melody_mode,
                "melody_midi": self.melody_midi,
                "degree": self.degree,
                "octave": self.octave,
                "finger_count": self.finger_count,
            }


class HandSynthEngine:
    def __init__(self, state: AudioState, sample_rate: int = 44100, hop: int = 512) -> None:
        self.state = state
        self.hop = hop
        self.synth = CleanNoteSynth(sample_rate)
        self.drums = DrumEngine(sample_rate)
        self._stream: sd.OutputStream | None = None

    def trigger_drum(self, pattern: str, volume: float = 0.9) -> None:
        snap = self.state.snapshot()
        self.drums.trigger(pattern, volume=min(1.0, snap["volume"] * 1.1))

    def _callback(self, outdata, frames, time_info, status) -> None:
        del time_info, status
        snap = self.state.snapshot()
        playing = snap["hand_active"] and snap["hand_detected"]
        hz = snap["target_hz"]

        self.synth.set_target(
            hz, snap["brightness"], playing, detune_cents=snap["detune_cents"],
        )
        out = self.synth.render(frames, snap["volume"])
        out += self.drums.render(frames)
        out = np.clip(out, -1.0, 1.0)
        outdata[:, 0] = out
        if outdata.shape[1] > 1:
            outdata[:, 1] = out

    def start(self) -> None:
        if self._stream:
            return
        self._stream = sd.OutputStream(
            samplerate=44100, blocksize=self.hop, channels=2,
            dtype="float32", callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
