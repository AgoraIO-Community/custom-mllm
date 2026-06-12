from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.kb import kb_store
from src.logging import get_logger
from src.session import parse_session_scope

log = get_logger(__name__)


def _validate_side_point(value: object, field: str) -> tuple[str, str] | JSONResponse:
    if not isinstance(value, dict):
        return JSONResponse({"detail": f"{field} must be an object"}, status_code=400)

    point_id = value.get("id")
    text = value.get("text")
    if not point_id or not isinstance(point_id, str):
        return JSONResponse({"detail": f"{field}.id is required"}, status_code=400)
    if not text or not isinstance(text, str):
        return JSONResponse({"detail": f"{field}.text is required"}, status_code=400)

    return point_id, text


async def kb_ingest(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    debate_session_id = body.get("debate_session_id")
    if not debate_session_id or not isinstance(debate_session_id, str):
        return JSONResponse({"detail": "debate_session_id is required"}, status_code=400)

    _, _, scope_error = parse_session_scope(debate_session_id, "pro")
    if scope_error:
        return JSONResponse({"detail": scope_error}, status_code=400)

    stored_pro = False
    stored_con = False

    if "pro" in body:
        result = _validate_side_point(body["pro"], "pro")
        if isinstance(result, JSONResponse):
            return result
        point_id, text = result
        kb_store.ingest(debate_session_id, "pro", point_id, text)
        stored_pro = True

    if "con" in body:
        result = _validate_side_point(body["con"], "con")
        if isinstance(result, JSONResponse):
            return result
        point_id, text = result
        kb_store.ingest(debate_session_id, "con", point_id, text)
        stored_con = True

    if not stored_pro and not stored_con:
        return JSONResponse({"detail": "pro and/or con is required"}, status_code=400)

    log.info(
        "kb.ingest",
        debate_session_id=debate_session_id,
        stored_pro=stored_pro,
        stored_con=stored_con,
    )

    return JSONResponse(
        {
            "ok": True,
            "debate_session_id": debate_session_id,
            "stored": {"pro": stored_pro, "con": stored_con},
        }
    )
