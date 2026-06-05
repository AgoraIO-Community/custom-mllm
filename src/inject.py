"""HTTP side-channel context injection — wired in Milestone 4."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.session import ProxySession


async def inject_text(
    session: ProxySession,
    text: str,
    role: str = "user",
    trigger_response: bool = False,
) -> None:
    if session.upstream_ws is None:
        raise RuntimeError("upstream not connected")

    await session.upstream_ws.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
    )

    if trigger_response:
        await session.upstream_ws.send(json.dumps({"type": "response.create"}))
