"""OSC output for TouchDesigner integration."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OscEmitter:
    """Broadcast hand data to TouchDesigner (or any OSC listener)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7000) -> None:
        self.host = host
        self.port = port
        self.enabled = False
        self._client = None

        try:
            from pythonosc.udp_client import SimpleUDPClient

            self._client = SimpleUDPClient(host, port)
            self.enabled = True
            logger.info("OSC → %s:%d (TouchDesigner)", host, port)
        except Exception as exc:
            logger.warning("OSC unavailable (%s). pip install python-osc", exc)

    def update(
        self,
        *,
        detected: bool,
        active: bool,
        midi: int,
        position: float,
        brightness: float,
        finger_count: int,
        x: float,
        y: float,
    ) -> None:
        if not self.enabled or self._client is None:
            return
        c = self._client
        c.send_message("/hand/detected", int(detected))
        c.send_message("/hand/active", int(active))
        c.send_message("/hand/note", midi)
        c.send_message("/hand/fingers", finger_count)
        c.send_message("/hand/y", float(position))
        c.send_message("/hand/x", float(x))
        c.send_message("/hand/pinch", float(brightness))
        c.send_message("/hand/brightness", float(brightness))

    def close(self) -> None:
        self._client = None
