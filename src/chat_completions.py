from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from src.kb import kb_store, merge_user_turn_with_context, merge_user_turn_without_cohost
from src.kb_audit import audit_chat_completion, extract_assistant_reply_from_sse
from src.logging import get_logger
from src.pipeline import parse_pipeline_mode
from src.proxy_auth import unauthorized_response, verify_bearer
from src.session import parse_session_scope
from src.settings import settings
from src.upstream import normalize_chat_completion_payload, resolve_chat_upstream

log = get_logger(__name__)

_AGORA_ONLY_KEYS = frozenset({"turn_id", "timestamp", "context", "interruptable"})


def _build_upstream_payload(body: dict, model: str) -> dict:
    payload = {key: value for key, value in body.items() if key not in _AGORA_ONLY_KEYS}
    payload["model"] = model
    payload["stream"] = True
    return normalize_chat_completion_payload(payload, model)


def _last_user_index(messages: list) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "user":
            return index
    return None


def _merge_context_into_last_user(messages: list, context_block: str) -> list:
    last_user_idx = _last_user_index(messages)
    if last_user_idx is None:
        return [*messages, {"role": "user", "content": merge_user_turn_without_cohost(context_block)}]

    last_user = messages[last_user_idx]
    cohost_line = last_user.get("content", "")
    if not isinstance(cohost_line, str):
        cohost_line = ""

    merged_user = {**last_user, "content": merge_user_turn_with_context(context_block, cohost_line)}
    return [*messages[:last_user_idx], merged_user, *messages[last_user_idx + 1:]]


def _inject_kb_messages(messages: list, debate_session_id: str, side: str) -> tuple[list, list, str | None]:
    max_points = settings.kb_inject_max_points_per_side
    if max_points == 0:
        max_points = None

    context_block, points = kb_store.format_live_context(
        debate_session_id,
        side,
        max_points=max_points,
    )
    if context_block is None:
        return messages, [], None

    return _merge_context_into_last_user(messages, context_block), points, context_block


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

    if not verify_bearer(
        request.headers.get("authorization", ""),
        debate_session_id=debate_session_id,
        side=side,
    ):
        return unauthorized_response()

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

    injected_messages, kb_points, injected_context = _inject_kb_messages(
        messages,
        debate_session_id,
        side,
    )
    payload = _build_upstream_payload({**body, "messages": injected_messages}, upstream.model)

    injected_thread = injected_context

    log.info(
        "chat_completions.request",
        debate_session_id=debate_session_id,
        side=side,
        provider=upstream.provider,
        model=upstream.model,
        turn_id=turn_id,
        timestamp=timestamp,
        kb_injected=bool(kb_points),
        kb_point_count=len(kb_points),
        kb_thread_chars=len(injected_thread) if injected_thread else 0,
    )

    async def generate() -> AsyncIterator[bytes]:
        stream_buffer = bytearray()
        try:
            async for chunk in _stream_upstream(upstream.url, upstream.headers, payload):
                stream_buffer.extend(chunk)
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
            return
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
            return

        assistant_reply = extract_assistant_reply_from_sse(bytes(stream_buffer))
        audit_chat_completion(
            debate_session_id=debate_session_id,
            side=side,
            turn_id=turn_id,
            agora_timestamp=timestamp,
            provider=upstream.provider,
            model=upstream.model,
            injected_thread=injected_thread,
            points=kb_points,
            upstream_messages=injected_messages,
            assistant_reply=assistant_reply,
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
