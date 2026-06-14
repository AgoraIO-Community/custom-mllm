import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, session_manager
from src.proxy_auth import derive_session_token, format_bearer
from src.session import ProxySession
from src.settings import settings


@pytest.fixture(autouse=True)
def clear_sessions():
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.fixture
def hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "test-secret-for-cross-check")
    yield


def _session_bearer(debate_session_id: str) -> dict[str, str]:
    return {"Authorization": format_bearer(derive_session_token(debate_session_id))}


@pytest.mark.asyncio
async def test_list_sessions_unauthorized_without_bearer(hmac_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sessions", params={"debate_session_id": "debate-abc"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_sessions_authorized_with_session_token(hmac_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/sessions",
            params={"debate_session_id": "debate-abc"},
            headers=_session_bearer("debate-abc"),
        )

    assert response.status_code == 200
    assert response.json() == {"sessions": []}


@pytest.mark.asyncio
async def test_list_sessions_list_all_blocked_when_hmac_only(hmac_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sessions")

    assert response.status_code == 401
