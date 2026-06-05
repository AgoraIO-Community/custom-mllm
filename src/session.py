from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.websockets import WebSocket


@dataclass
class ProxySession:
    session_id: str
    downstream_ws: WebSocket
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    upstream_ws: Any | None = None

    @property
    def upstream_connected(self) -> bool:
        return self.upstream_ws is not None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ProxySession] = {}

    async def create(self, downstream_ws: WebSocket, model: str, session_id: str) -> ProxySession:
        session = ProxySession(
            session_id=session_id,
            downstream_ws=downstream_ws,
            model=model,
        )
        self._sessions[session_id] = session
        return session

    async def connect_upstream(self, session: ProxySession, upstream_ws: Any) -> None:
        session.upstream_ws = upstream_ws

    def get(self, session_id: str) -> ProxySession | None:
        return self._sessions.get(session_id)

    async def close(self, session_id: str, reason: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return

        if session.upstream_ws is not None:
            try:
                await session.upstream_ws.close()
            except Exception:
                pass
            session.upstream_ws = None

        try:
            await session.downstream_ws.close()
        except Exception:
            pass

    def list_active(self) -> list[ProxySession]:
        return list(self._sessions.values())

    def count(self) -> int:
        return len(self._sessions)
