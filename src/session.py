from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

_VALID_SCOPE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_VALID_SIDES = frozenset({"pro", "con"})


def parse_session_scope(
    debate_session_id: str | None,
    side: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Return (debate_session_id, side, error_message)."""
    if debate_session_id is None and side is None:
        return None, None, None

    if not debate_session_id or not side:
        return None, None, "debate_session_id and side must both be provided"

    if not _VALID_SCOPE_ID.match(debate_session_id):
        return None, None, "invalid debate_session_id"

    if side not in _VALID_SIDES:
        return None, None, "side must be pro or con"

    return debate_session_id, side, None


@dataclass
class ProxySession:
    session_id: str
    downstream_ws: WebSocket
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    upstream_ws: Any | None = None
    debate_session_id: str | None = None
    side: str | None = None

    @property
    def upstream_connected(self) -> bool:
        return self.upstream_ws is not None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ProxySession] = {}

    async def create(
        self,
        downstream_ws: WebSocket,
        model: str,
        session_id: str,
        *,
        debate_session_id: str | None = None,
        side: str | None = None,
    ) -> ProxySession:
        session = ProxySession(
            session_id=session_id,
            downstream_ws=downstream_ws,
            model=model,
            debate_session_id=debate_session_id,
            side=side,
        )
        self._sessions[session_id] = session
        return session

    async def connect_upstream(self, session: ProxySession, upstream_ws: Any) -> None:
        session.upstream_ws = upstream_ws

    def get(self, session_id: str) -> ProxySession | None:
        return self._sessions.get(session_id)

    def has_active_scope(self, debate_session_id: str, side: str) -> bool:
        return any(
            s.debate_session_id == debate_session_id and s.side == side
            for s in self._sessions.values()
        )

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

    def list_active(self, debate_session_id: str | None = None) -> list[ProxySession]:
        sessions = list(self._sessions.values())
        if debate_session_id is None:
            return sessions
        return [s for s in sessions if s.debate_session_id == debate_session_id]

    def count(self) -> int:
        return len(self._sessions)
