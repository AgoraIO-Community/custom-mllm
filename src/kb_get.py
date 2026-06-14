from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.kb import debate_kb_to_dict, kb_store
from src.proxy_auth import is_auth_enabled, unauthorized_response, verify_bearer
from src.session import parse_session_scope


async def kb_get(request: Request) -> JSONResponse:
    debate_session_id = request.query_params.get("debate_session_id")

    if is_auth_enabled() and not debate_session_id:
        return unauthorized_response()

    if debate_session_id:
        if not verify_bearer(
            request.headers.get("authorization", ""),
            debate_session_id=debate_session_id,
        ):
            return unauthorized_response()

        _, _, scope_error = parse_session_scope(debate_session_id, "pro")
        if scope_error:
            return JSONResponse({"detail": scope_error}, status_code=400)

        sides = kb_store.get_debate(debate_session_id)
        return JSONResponse(debate_kb_to_dict(debate_session_id, sides))

    debates = []
    for debate_id in kb_store.list_debates():
        sides = kb_store.get_debate(debate_id)
        debates.append(debate_kb_to_dict(debate_id, sides))

    return JSONResponse({"debates": debates})
