"""Virtual MIDI output for DAW / Antares Harmony Engine."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PORT_NAME = "Hand Vocoder"


class MidiEmitter:
    """Send MIDI notes + CC from hand gestures to a virtual MIDI port."""

    def __init__(self, port_name: str = PORT_NAME) -> None:
        self.port_name = port_name
        self.enabled = False
        self._out = None
        self._current_note: int | None = None
        self._channel = 0

        try:
            import rtmidi

            self._out = rtmidi.MidiOut()
            ports = self._out.get_ports()
            for i, name in enumerate(ports):
                if port_name in name:
                    self._out.open_port(i)
                    self.enabled = True
                    logger.info("MIDI: connected to %s", name)
                    break
            if not self.enabled:
                self._out.open_virtual_port(port_name)
                self.enabled = True
                logger.info("MIDI: created virtual port '%s'", port_name)
        except Exception as exc:
            logger.warning("MIDI unavailable (%s). Install: pip install python-rtmidi", exc)

    def _note_off(self) -> None:
        if self._out is None or self._current_note is None:
            return
        self._out.send_message([0x80 | self._channel, self._current_note, 0])
        self._current_note = None

    def _note_on(self, midi: int, velocity: int = 100) -> None:
        if self._out is None:
            return
        if self._current_note == midi:
            return
        self._note_off()
        self._out.send_message([0x90 | self._channel, midi, max(1, min(127, velocity))])
        self._current_note = midi

    def _cc(self, cc: int, value: int) -> None:
        if self._out is None:
            return
        self._out.send_message([0xB0 | self._channel, cc, max(0, min(127, value))])

    def update(
        self,
        *,
        active: bool,
        midi: int,
        position: float,
        brightness: float,
        finger_count: int,
    ) -> None:
        if not self.enabled:
            return

        self._cc(1, int(position * 127))       # hand height
        self._cc(2, int(brightness * 127))     # pinch / brightness
        self._cc(3, int(finger_count / 5 * 127))  # finger count

        if active:
            vel = int(70 + brightness * 57)
            self._note_on(midi, vel)
        else:
            self._note_off()

    def close(self) -> None:
        self._note_off()
        self._out = None
