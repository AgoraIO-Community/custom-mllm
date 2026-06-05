"""Bidirectional WebSocket relay between Agora (downstream) and xAI (upstream)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.logging import redact_payload_for_log
from src.session import ProxySession


def parse_event_type(raw: str) -> tuple[str | None, dict | str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, raw
    return payload.get("type"), payload


def log_ws_message(
    session_id: str,
    direction: str,
    raw: str,
    log: Any,
) -> None:
    event_type, payload = parse_event_type(raw)
    payload_size = len(raw.encode("utf-8"))

    if isinstance(payload, dict):
        logged_payload = redact_payload_for_log(event_type, payload)
    else:
        logged_payload = payload if len(str(payload)) <= 500 else str(payload)[:500]

    log.info(
        "ws.message",
        session_id=session_id,
        direction=direction,
        type=event_type,
        payload_size_bytes=payload_size,
        payload=logged_payload,
    )


async def _relay_downstream_to_upstream(session: ProxySession, log: Any) -> None:
    downstream = session.downstream_ws
    upstream = session.upstream_ws
    if upstream is None:
        raise RuntimeError("upstream not connected")

    while True:
        message = await downstream.receive()
        msg_type = message.get("type")

        if msg_type == "websocket.disconnect":
            break

        if msg_type != "websocket.receive":
            continue

        raw = message.get("text")
        if raw is None and message.get("bytes") is not None:
            log.warning(
                "ws.binary",
                session_id=session.session_id,
                direction="downstream_to_upstream",
                payload_size_bytes=len(message["bytes"]),
            )
            await upstream.send(message["bytes"])
            continue

        if raw is None:
            continue

        log_ws_message(session.session_id, "downstream_to_upstream", raw, log)
        await upstream.send(raw)


async def _relay_upstream_to_downstream(session: ProxySession, log: Any) -> None:
    upstream = session.upstream_ws
    downstream = session.downstream_ws
    if upstream is None:
        raise RuntimeError("upstream not connected")

    async for raw in upstream:
        if isinstance(raw, bytes):
            log.warning(
                "ws.binary",
                session_id=session.session_id,
                direction="upstream_to_downstream",
                payload_size_bytes=len(raw),
            )
            await downstream.send_bytes(raw)
            continue

        log_ws_message(session.session_id, "upstream_to_downstream", raw, log)
        await downstream.send_text(raw)


async def relay_loop(session: ProxySession, log: Any) -> None:
    """Run downstream→upstream and upstream→downstream until one side closes."""
    downstream_task = asyncio.create_task(_relay_downstream_to_upstream(session, log))
    upstream_task = asyncio.create_task(_relay_upstream_to_downstream(session, log))

    done, pending = await asyncio.wait(
        [downstream_task, upstream_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    for task in done:
        if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
            raise task.exception()
