"""Musical scales, note mapping, and song presets."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def hz_to_midi(hz: float) -> float:
    if hz <= 0:
        return float("nan")
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def midi_to_name(midi: int) -> str:
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


def build_scale(root_midi: int, intervals: tuple[int, ...], octaves: int = 2) -> list[int]:
    notes: list[int] = []
    for octave in range(octaves + 1):
        for interval in intervals:
            note = root_midi + interval + octave * 12
            notes.append(note)
    return sorted(set(notes))


SCALES: dict[str, tuple[int, tuple[int, ...]]] = {
    "chromatic": (60, tuple(range(12))),
    "c_major": (60, (0, 2, 4, 5, 7, 9, 11)),
    "major": (60, (0, 2, 4, 5, 7, 9, 11)),
    "d_major": (62, (0, 2, 4, 5, 7, 9, 11)),
    "minor": (60, (0, 2, 3, 5, 7, 8, 10)),
    "a_minor": (57, (0, 2, 3, 5, 7, 8, 10)),
    "f_minor": (53, (0, 2, 3, 5, 7, 8, 10)),
    "dorian": (60, (0, 2, 3, 5, 7, 9, 10)),
    "pentatonic": (60, (0, 2, 4, 7, 9)),
}

SCALE_LABELS: dict[str, str] = {
    "c_major": "C major",
    "major": "C major",
    "d_major": "D major",
    "f_minor": "F minor",
    "minor": "C minor",
    "a_minor": "A minor",
    "pentatonic": "C pentatonic",
    "dorian": "D dorian",
    "chromatic": "Chromatic",
}


@dataclass(frozen=True)
class SongPreset:
    name: str
    artist: str
    scale_key: str
    root_midi: int
    low_midi: int
    high_midi: int
    melody_midi: tuple[int, ...]
    description: str


# Approximate chorus melody contour for "Stay" (F minor, Alessia Cara vocal line).
STAY_BY_ZEDD = SongPreset(
    name="Stay",
    artist="Zedd ft. Alessia Cara",
    scale_key="f_minor",
    root_midi=53,
    low_midi=53,
    high_midi=77,
    melody_midi=(
        65, 65, 67, 68, 70, 68, 67, 65,
        63, 65, 67, 68, 70, 72, 70, 68,
        65, 67, 68, 70, 72, 70, 68, 65,
        63, 65, 63, 62, 60, 62, 63, 65,
    ),
    description="F minor — raise your hand to follow the melody while you sing.",
)


SONG_PRESETS: dict[str, SongPreset] = {
    "stay": STAY_BY_ZEDD,
}


class PitchMapper:
    """Map a normalized hand position (0=bottom, 1=top) to scale notes."""

    def __init__(
        self,
        scale_key: str = "f_minor",
        low_midi: int = 53,
        high_midi: int = 77,
    ) -> None:
        self.set_scale(scale_key, low_midi, high_midi)

    def set_scale(self, scale_key: str, low_midi: int, high_midi: int) -> None:
        root, intervals = SCALES.get(scale_key, SCALES["f_minor"])
        self.scale_key = scale_key
        self.low_midi = low_midi
        self.high_midi = high_midi
        self.root = root
        self.intervals = intervals
        self.root_pc = root % 12
        octaves = max(1, (high_midi - low_midi) // 12 + 1)
        all_notes = build_scale(root, intervals, octaves=octaves)
        self.notes = [n for n in all_notes if low_midi <= n <= high_midi]
        if not self.notes:
            self.notes = list(range(low_midi, high_midi + 1))
        self.num_degrees = len(intervals)
        self.min_octave = low_midi // 12
        self.max_octave = high_midi // 12

    def slot_base_c(self, octave_slot: int) -> int:
        """Root note at bottom of the ladder for this octave slot."""
        oct_span = max(0, self.max_octave - self.min_octave)
        octave = self.min_octave + int(round((max(1, min(5, octave_slot)) - 1) / 4.0 * oct_span))
        return octave * 12 + self.root_pc

    def octave_ladder_steps(self) -> list[int]:
        """Bottom root → top octave root (e.g. C→C = 8 notes in major)."""
        return list(self.intervals) + [12]

    def equal_band_index(self, height: float, num_bands: int) -> int:
        """Equal-height bands: each band is exactly 1/n of the ladder."""
        if num_bands <= 1:
            return 0
        h = max(0.0, min(1.0, height))
        return min(num_bands - 1, int(h * num_bands))

    def height_to_octave_ladder(self, height: float, octave_slot: int) -> tuple[int, int]:
        """Map ladder height (0=bottom bar, 1=top bar) to one scale octave."""
        steps = self.octave_ladder_steps()
        idx = self.equal_band_index(height, len(steps))
        midi = self.slot_base_c(octave_slot) + steps[idx]
        return max(self.low_midi, min(self.high_midi, midi)), idx

    def octave_ladder_labels(self, octave_slot: int) -> list[str]:
        base = self.slot_base_c(octave_slot)
        return [midi_to_name(base + s) for s in self.octave_ladder_steps()]

    def height_to_zone(self, height: float) -> int:
        """Equal screen bands: bottom=zone 0, top=zone n-1."""
        h = max(0.0, min(0.999999, height))
        return min(self.num_degrees - 1, int(h * self.num_degrees))

    def zone_labels(self, finger_count: int = 3) -> list[str]:
        fc = max(1, min(5, finger_count))
        return [midi_to_name(self.degree_fingers_to_midi(i, fc)) for i in range(self.num_degrees)]

    def degree_name_at(self, degree_idx: int) -> str:
        idx = max(0, min(self.num_degrees - 1, degree_idx))
        return NOTE_NAMES[(self.root_pc + self.intervals[idx]) % 12]

    def degree_fingers_to_midi(self, degree_idx: int, finger_count: int) -> int:
        """Map locked scale degree + finger octave to MIDI."""
        degree_idx = max(0, min(self.num_degrees - 1, degree_idx))
        fingers = max(1, min(5, finger_count))
        oct_span = max(0, self.max_octave - self.min_octave)
        octave = self.min_octave + int(round((fingers - 1) / 4.0 * oct_span))
        pitch = (self.root_pc + self.intervals[degree_idx]) % 12
        midi = octave * 12 + pitch
        while midi < self.low_midi:
            midi += 12
        while midi > self.high_midi:
            midi -= 12
        return max(self.low_midi, min(self.high_midi, midi))

    def height_octave_to_midi(self, height: float, finger_count: int) -> int:
        """Height → scale note. Fingers 1–5 → octave (low → high)."""
        height = max(0.0, min(1.0, height))
        fingers = max(1, min(5, finger_count))
        degree_idx = int(round(height * (self.num_degrees - 1)))
        degree_idx = max(0, min(self.num_degrees - 1, degree_idx))
        oct_span = max(0, self.max_octave - self.min_octave)
        octave = self.min_octave + int(round((fingers - 1) / 4.0 * oct_span))
        pitch = (self.root_pc + self.intervals[degree_idx]) % 12
        midi = octave * 12 + pitch
        while midi < self.low_midi:
            midi += 12
        while midi > self.high_midi:
            midi -= 12
        return max(self.low_midi, min(self.high_midi, midi))

    def degree_name(self, height: float) -> str:
        height = max(0.0, min(1.0, height))
        idx = int(round(height * (self.num_degrees - 1)))
        idx = max(0, min(self.num_degrees - 1, idx))
        return NOTE_NAMES[(self.root_pc + self.intervals[idx]) % 12]

    def octave_label(self, finger_count: int) -> str:
        fingers = max(1, min(5, finger_count))
        oct_span = max(0, self.max_octave - self.min_octave)
        o = self.min_octave + int(round((fingers - 1) / 4.0 * oct_span))
        return str(o - 1)

    def gesture_to_midi(self, finger_count: int, position: float) -> int:
        """Map finger count (1-5) + hand height to a scale note.

        Fingers pick the chord tone / scale degree; hand height fine-tunes up/down.
        """
        finger_count = max(1, min(5, finger_count))
        position = max(0.0, min(1.0, position))
        n = len(self.notes)
        if n == 1:
            return self.notes[0]

        # 1 finger → lower degrees, 5 fingers → higher degrees.
        base_idx = int((finger_count - 1) / 4.0 * (n - 1))
        # Hand height nudges ±3 scale steps for expression.
        fine = int((position - 0.5) * 6)
        idx = max(0, min(n - 1, base_idx + fine))
        return self.notes[idx]

    def position_to_midi(self, position: float) -> int:
        position = max(0.0, min(1.0, position))
        if len(self.notes) == 1:
            return self.notes[0]
        index = round(position * (len(self.notes) - 1))
        return self.notes[index]

    def position_to_hz(self, position: float) -> float:
        return midi_to_hz(self.position_to_midi(position))

    def nearest_scale_midi(self, hz: float) -> int:
        if not math.isfinite(hz) or hz <= 0:
            return self.notes[len(self.notes) // 2]
        midi = hz_to_midi(hz)
        return min(self.notes, key=lambda n: abs(n - midi))

    def note_name(self, midi: int) -> str:
        return midi_to_name(midi)

    def harmony_intervals(self, midi: int) -> tuple[int, int]:
        """Scale-aware 3rd and 5th for free harmony voices."""
        if midi not in self.notes:
            return midi + 3, midi + 7
        i = self.notes.index(midi)
        i3 = min(i + 2, len(self.notes) - 1)
        i5 = min(i + 4, len(self.notes) - 1)
        return self.notes[i3], self.notes[i5]


class MelodyGuide:
    """Step through a preset melody for guided singing."""

    def __init__(self, melody: Iterable[int]) -> None:
        self.melody = list(melody)
        self.index = 0
        self.enabled = False

    def current_midi(self) -> int | None:
        if not self.enabled or not self.melody:
            return None
        return self.melody[self.index % len(self.melody)]

    def advance(self) -> None:
        if self.melody:
            self.index = (self.index + 1) % len(self.melody)

    def reset(self) -> None:
        self.index = 0
