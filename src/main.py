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
from src.logging import configure_logging, get_logger
from src.relay import relay_loop
from src.session import SessionManager
from src.settings import settings

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

    return JSONResponse(
        {
            "sessions": [
                {
                    "session_id": session.session_id,
                    "created_at": session.created_at.isoformat(),
                    "upstream_connected": session.upstream_connected,
                    "model": session.model,
                }
                for session in session_manager.list_active()
            ]
        }
    )


async def inject_session(request: Request) -> JSONResponse:
    if err := _check_auth(request):
        return err

    return JSONResponse(
        {"detail": "Not implemented until Milestone 4"},
        status_code=501,
    )


async def realtime_ws(websocket: WebSocket) -> None:
    if not _check_auth_header(websocket.headers.get("authorization", "")):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    if not settings.xai_api_key:
        await websocket.close(code=1011, reason="XAI_API_KEY not configured")
        return

    model = websocket.query_params.get("model") or settings.xai_model
    session_id = str(uuid4())

    await websocket.accept()

    session = await session_manager.create(websocket, model, session_id)
    log.info("session.created", session_id=session_id, model=model)

    upstream_url = f"wss://api.x.ai/v1/realtime?model={model}"
    upstream_headers = {"Authorization": f"Bearer {settings.xai_api_key}"}

    try:
        async with websockets.connect(upstream_url, additional_headers=upstream_headers) as upstream:
            await session_manager.connect_upstream(session, upstream)
            log.info("session.upstream_connected", session_id=session_id, upstream_url=upstream_url)
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
    )
    yield
    log.info("proxy.shutdown")


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/sessions", list_sessions, methods=["GET"]),
    Route("/inject/{session_id}", inject_session, methods=["POST"]),
    WebSocketRoute("/realtime", realtime_ws),
]

app = Starlette(routes=routes, debug=False, lifespan=lifespan)
