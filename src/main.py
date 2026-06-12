from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import websockets
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from src import __version__
from src.chat_completions import chat_completions
from src.inject import inject_text
from src.kb_get import kb_get
from src.kb_ingest import kb_ingest
from src.logging import configure_logging, get_logger
from src.pipeline import parse_pipeline_mode
from src.relay import relay_loop
from src.session import SessionManager, parse_session_scope
from src.settings import settings
from src.upstream import resolve_upstream

configure_logging()
log = get_logger(__name__)

session_manager = SessionManager()


def _check_auth_header(auth_header: str) -> bool:
    if not settings.proxy_auth_token:
        return True
    return auth_header == f"Bearer {settings.proxy_auth_token}"


def _check_auth(request: Request) -> JSONResponse | None:
    if _check_auth_header(request.headers.get("authorization", "")):
        return None
    return JSONResponse({"detail": "Unauthorized"}, status_code=401)


def _session_payload(session) -> dict:
    return {
        "session_id": session.session_id,
        "debate_session_id": session.debate_session_id,
        "side": session.side,
        "created_at": session.created_at.isoformat(),
        "upstream_connected": session.upstream_connected,
        "provider": session.provider,
        "model": session.model,
    }


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "active_sessions": session_manager.count(),
        }
    )


async def list_sessions(request: Request) -> JSONResponse:
    if err := _check_auth(request):
        return err

    debate_session_id = request.query_params.get("debate_session_id")
    sessions = session_manager.list_active(debate_session_id=debate_session_id or None)

    return JSONResponse({"sessions": [_session_payload(session) for session in sessions]})


async def inject_session(request: Request) -> JSONResponse:
    if err := _check_auth(request):
        return err

    session_id = request.path_params["session_id"]
    session = session_manager.get(session_id)
    if session is None:
        return JSONResponse({"detail": "Session not found"}, status_code=404)

    if not session.upstream_connected:
        return JSONResponse({"detail": "Upstream not connected"}, status_code=409)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    text = body.get("text")
    if not text or not isinstance(text, str):
        return JSONResponse({"detail": "text is required"}, status_code=400)

    role = body.get("role", "user")
    if not isinstance(role, str):
        return JSONResponse({"detail": "role must be a string"}, status_code=400)

    trigger_response = bool(body.get("trigger_response", False))

    await inject_text(session, text, role=role, trigger_response=trigger_response)

    log.info(
        "inject.sent",
        session_id=session_id,
        debate_session_id=session.debate_session_id,
        side=session.side,
        text_length=len(text),
        text_preview=text[:50],
        trigger_response=trigger_response,
    )

    return JSONResponse(
        {
            "session_id": session_id,
            "debate_session_id": session.debate_session_id,
            "side": session.side,
            "injected": True,
            "trigger_response": trigger_response,
        }
    )


async def realtime_ws(websocket: WebSocket) -> None:
    if not _check_auth_header(websocket.headers.get("authorization", "")):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    pipeline_error = parse_pipeline_mode(websocket.query_params.get("pipeline_mode"), "mllm")
    if pipeline_error:
        await websocket.close(code=1008, reason=pipeline_error)
        return

    debate_session_id, side, scope_error = parse_session_scope(
        websocket.query_params.get("debate_session_id"),
        websocket.query_params.get("side"),
    )
    if scope_error:
        await websocket.close(code=1008, reason=scope_error)
        return

    if debate_session_id and side and session_manager.has_active_scope(debate_session_id, side):
        await websocket.close(code=1008, reason="Session scope already active")
        return

    provider = websocket.query_params.get("provider")
    try:
        upstream = resolve_upstream(provider)
    except ValueError as exc:
        await websocket.close(code=1011, reason=str(exc))
        return

    session_id = str(uuid4())

    await websocket.accept()

    session = await session_manager.create(
        websocket,
        upstream.model,
        session_id,
        debate_session_id=debate_session_id,
        side=side,
        provider=upstream.provider,
    )
    log.info(
        "session.created",
        session_id=session_id,
        provider=upstream.provider,
        model=upstream.model,
        debate_session_id=debate_session_id,
        side=side,
    )

    try:
        async with websockets.connect(
            upstream.url, additional_headers=upstream.headers
        ) as upstream_ws:
            await session_manager.connect_upstream(session, upstream_ws)
            log.info(
                "session.upstream_connected",
                session_id=session_id,
                provider=upstream.provider,
                model=upstream.model,
                upstream_url=upstream.url,
            )
            await relay_loop(session, log)
    except websockets.InvalidStatus as exc:
        log.error(
            "session.error",
            session_id=session_id,
            error=f"upstream HTTP {exc.response.status_code}",
        )
        await websocket.close(code=1011, reason="Upstream connection failed")
    except Exception as exc:  # noqa: BLE001 — close session cleanly
        log.error("session.error", session_id=session_id, error=str(exc))
    finally:
        await session_manager.close(session_id, "disconnect")
        log.info("session.closed", session_id=session_id)


@asynccontextmanager
async def lifespan(_: Starlette):
    log.info(
        "proxy.startup",
        version=__version__,
        host=settings.host,
        port=settings.port,
        xai_model=settings.xai_model,
        openai_model=settings.openai_model,
    )
    yield
    log.info("proxy.shutdown")


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/sessions", list_sessions, methods=["GET"]),
    Route("/inject/{session_id}", inject_session, methods=["POST"]),
    Route("/kb", kb_get, methods=["GET"]),
    Route("/kb/ingest", kb_ingest, methods=["POST"]),
    Route("/v1/chat/completions", chat_completions, methods=["POST"]),
    WebSocketRoute("/realtime", realtime_ws),
]

app = Starlette(routes=routes, debug=False, lifespan=lifespan)
