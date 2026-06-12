from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from src.kb import kb_store
from src.logging import get_logger
from src.pipeline import parse_pipeline_mode
from src.session import parse_session_scope
from src.upstream import resolve_chat_upstream

log = get_logger(__name__)

_AGORA_ONLY_KEYS = frozenset({"turn_id", "timestamp", "context"})


def _build_upstream_payload(body: dict, model: str) -> dict:
    payload = {key: value for key, value in body.items() if key not in _AGORA_ONLY_KEYS}
    payload["model"] = model
    payload["stream"] = True
    return payload


def _inject_kb_messages(messages: list, debate_session_id: str, side: str) -> list:
    point = kb_store.latest(debate_session_id, side)
    if point is None:
        return messages

    kb_message = {"role": "system", "content": f"[LIVE THREAD] {point.text}"}
    return [kb_message, *messages]


async def _stream_upstream(
    upstream_url: str,
    headers: dict[str, str],
    payload: dict,
) -> AsyncIterator[bytes]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        async with client.stream(
            "POST",
            upstream_url,
            json=payload,
            headers={**headers, "Content-Type": "application/json"},
        ) as response:
            if response.status_code >= 400:
                error_body = await response.aread()
                detail = error_body.decode("utf-8", errors="replace")
                raise httpx.HTTPStatusError(
                    f"upstream HTTP {response.status_code}: {detail}",
                    request=response.request,
                    response=response,
                )

            saw_done = False
            async for chunk in response.aiter_bytes():
                if b"[DONE]" in chunk:
                    saw_done = True
                yield chunk

            if not saw_done:
                yield b"data: [DONE]\n\n"


async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    pipeline_error = parse_pipeline_mode(request.query_params.get("pipeline_mode"), "llm")
    if pipeline_error:
        return JSONResponse({"detail": pipeline_error}, status_code=400)

    debate_session_id, side, scope_error = parse_session_scope(
        request.query_params.get("debate_session_id"),
        request.query_params.get("side"),
    )
    if scope_error:
        return JSONResponse({"detail": scope_error}, status_code=400)

    provider = request.query_params.get("provider")
    model = request.query_params.get("model")
    if not provider:
        return JSONResponse({"detail": "provider is required"}, status_code=400)
    if not model:
        return JSONResponse({"detail": "model is required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if body.get("stream") is False:
        return JSONResponse({"detail": "chat completions require streaming"}, status_code=400)

    turn_id = body.get("turn_id")
    timestamp = body.get("timestamp")

    messages = body.get("messages")
    if not isinstance(messages, list):
        return JSONResponse({"detail": "messages is required"}, status_code=400)

    try:
        upstream = resolve_chat_upstream(provider, model)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    injected_messages = _inject_kb_messages(messages, debate_session_id, side)
    payload = _build_upstream_payload({**body, "messages": injected_messages}, upstream.model)

    log.info(
        "chat_completions.request",
        debate_session_id=debate_session_id,
        side=side,
        provider=upstream.provider,
        model=upstream.model,
        turn_id=turn_id,
        timestamp=timestamp,
        kb_injected=injected_messages is not messages,
    )

    async def generate() -> AsyncIterator[bytes]:
        try:
            async for chunk in _stream_upstream(upstream.url, upstream.headers, payload):
                yield chunk
        except httpx.HTTPStatusError as exc:
            log.error(
                "chat_completions.upstream_error",
                debate_session_id=debate_session_id,
                side=side,
                error=str(exc),
            )
            error_payload = json.dumps({"detail": str(exc)})
            yield f"data: {error_payload}\n\n".encode()
            yield b"data: [DONE]\n\n"
        except Exception as exc:  # noqa: BLE001
            log.error(
                "chat_completions.error",
                debate_session_id=debate_session_id,
                side=side,
                error=str(exc),
            )
            error_payload = json.dumps({"detail": str(exc)})
            yield f"data: {error_payload}\n\n".encode()
            yield b"data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
