from __future__ import annotations

import hashlib
import hmac

from starlette.responses import JSONResponse

from src.settings import settings

# Cross-language test vector (must match Next.js):
# PROXY_MASTER_SECRET = "test-secret-for-cross-check"
# derive_side_token("debate-abc", "pro")   -> dc31be4b05899e6e5ef6e5d060036a5db6bbbe0f028ba6b4390e9b27d21bb7a6
# derive_session_token("debate-abc")       -> a846a57a323925d0035f5d20e9ce1da2aeadbdd76e0e3363574f5193678948b7


def _master_secret() -> str:
    return settings.proxy_master_secret.strip()


def is_auth_enabled() -> bool:
    return bool(_master_secret())


def _hmac_hex(message: str) -> str:
    secret = _master_secret()
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def derive_side_token(debate_session_id: str, side: str) -> str:
    return _hmac_hex(f"{debate_session_id}:{side}")


def derive_session_token(debate_session_id: str) -> str:
    return _hmac_hex(debate_session_id)


def bearer_token(auth_header: str) -> str | None:
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def format_bearer(token: str) -> str:
    return f"Bearer {token}"


def unauthorized_response() -> JSONResponse:
    return JSONResponse({"detail": "Unauthorized"}, status_code=401)


def proxy_auth_headers(
    *,
    debate_session_id: str | None = None,
    side: str | None = None,
) -> dict[str, str]:
    """Build Authorization header for scripts and server-side callers."""
    if not _master_secret() or debate_session_id is None:
        return {}
    if side is not None:
        token = derive_side_token(debate_session_id, side)
    else:
        token = derive_session_token(debate_session_id)
    return {"Authorization": format_bearer(token)}


def verify_bearer(
    auth_header: str,
    *,
    debate_session_id: str | None = None,
    side: str | None = None,
) -> bool:
    if not is_auth_enabled():
        return True

    token = bearer_token(auth_header)
    if token is None or not debate_session_id:
        return False

    if side is not None:
        expected = derive_side_token(debate_session_id, side)
    else:
        expected = derive_session_token(debate_session_id)

    return hmac.compare_digest(token, expected)
