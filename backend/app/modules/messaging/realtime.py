"""Real-time messaging over WebSocket: live message delivery, presence, typing.

An in-process :class:`ConnectionManager` fans out events to a user's open
sockets. This is single-instance (dev / one worker); horizontal scale-out needs
a Redis pub/sub relay in front of the same manager API — a documented follow-up.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from starlette.websockets import WebSocket

log = structlog.get_logger("app.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}

    def add(self, user_id: uuid.UUID, websocket: WebSocket) -> bool:
        """Register a socket. Returns True if this is the user's first socket."""
        sockets = self._connections.setdefault(user_id, set())
        was_offline = len(sockets) == 0
        sockets.add(websocket)
        return was_offline

    def remove(self, user_id: uuid.UUID, websocket: WebSocket) -> bool:
        """Deregister a socket. Returns True if the user now has no sockets."""
        sockets = self._connections.get(user_id)
        if not sockets:
            return True
        sockets.discard(websocket)
        if not sockets:
            self._connections.pop(user_id, None)
            return True
        return False

    def is_online(self, user_id: uuid.UUID) -> bool:
        return bool(self._connections.get(user_id))

    def online_among(self, user_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        return [uid for uid in user_ids if self.is_online(uid)]

    async def send_to_users(
        self, user_ids: list[uuid.UUID], payload: dict[str, Any]
    ) -> None:
        for uid in user_ids:
            for websocket in list(self._connections.get(uid, ())):
                try:
                    await websocket.send_json(payload)
                except Exception:  # pragma: no cover - broken socket
                    self.remove(uid, websocket)


# Process-wide singleton.
manager = ConnectionManager()
