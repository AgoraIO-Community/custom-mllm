import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, session_manager
from src.proxy_auth import derive_side_token, format_bearer
from src.session import ProxySession, parse_session_scope
from src.settings import settings


@pytest.fixture(autouse=True)
def clear_sessions():
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def _make_session(
    session_id: str,
    *,
    debate_session_id: str | None = None,
    side: str | None = None,
    upstream_connected: bool = True,
) -> ProxySession:
    upstream = AsyncMock() if upstream_connected else None
    session = ProxySession(
        session_id=session_id,
        downstream_ws=AsyncMock(),
        model="grok-voice-latest",
        upstream_ws=upstream,
        debate_session_id=debate_session_id,
        side=side,
    )
    session_manager._sessions[session_id] = session
    return session


@pytest.mark.asyncio
async def test_inject_success():
    session = _make_session("sess-1", debate_session_id="room-abc", side="pro")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inject/sess-1",
            json={"text": "[LIVE X - PRO] tweet", "trigger_response": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["injected"] is True
    assert data["session_id"] == "sess-1"
    assert data["debate_session_id"] == "room-abc"
    assert data["side"] == "pro"
    assert data["trigger_response"] is False
    assert session.upstream_ws.send.await_count == 1


@pytest.mark.asyncio
async def test_inject_triggers_response():
    session = _make_session("sess-2")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inject/sess-2",
            json={"text": "hello", "trigger_response": True},
        )

    assert response.status_code == 200
    assert session.upstream_ws.send.await_count == 2
    second = json.loads(session.upstream_ws.send.await_args_list[1].args[0])
    assert second["type"] == "response.create"


@pytest.mark.asyncio
async def test_inject_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/inject/missing", json={"text": "hello"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_inject_upstream_not_ready():
    _make_session("sess-3", upstream_connected=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/inject/sess-3", json={"text": "hello"})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_inject_missing_text():
    _make_session("sess-4")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/inject/sess-4", json={})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_sessions_filter_by_debate_session_id():
    _make_session("pro-1", debate_session_id="room-abc", side="pro")
    _make_session("con-1", debate_session_id="room-abc", side="con")
    _make_session("pro-2", debate_session_id="room-xyz", side="pro")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sessions", params={"debate_session_id": "room-abc"})

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 2
    assert {s["session_id"] for s in sessions} == {"pro-1", "con-1"}


def test_parse_session_scope_optional():
    debate_id, side, err = parse_session_scope(None, None)
    assert debate_id is None
    assert side is None
    assert err is None


def test_parse_session_scope_valid():
    debate_id, side, err = parse_session_scope("room-abc-123", "pro")
    assert debate_id == "room-abc-123"
    assert side == "pro"
    assert err is None


def test_parse_session_scope_requires_both():
    _, _, err = parse_session_scope("room-abc", None)
    assert err is not None


def test_parse_session_scope_invalid_side():
    _, _, err = parse_session_scope("room-abc", "moderator")
    assert err is not None


def test_has_active_scope():
    _make_session("a", debate_session_id="room-1", side="pro")
    assert session_manager.has_active_scope("room-1", "pro") is True
    assert session_manager.has_active_scope("room-1", "con") is False


@pytest.fixture
def hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "test-secret-for-cross-check")
    yield


def _side_bearer(debate_session_id: str, side: str) -> dict[str, str]:
    return {"Authorization": format_bearer(derive_side_token(debate_session_id, side))}


@pytest.mark.asyncio
async def test_inject_unauthorized_without_bearer(hmac_secret):
    _make_session("sess-1", debate_session_id="debate-abc", side="pro")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inject/sess-1",
            json={"text": "hello", "trigger_response": False},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inject_authorized_with_side_token(hmac_secret):
    _make_session("sess-1", debate_session_id="debate-abc", side="pro")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/inject/sess-1",
            json={"text": "hello", "trigger_response": False},
            headers=_side_bearer("debate-abc", "pro"),
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_inject_missing_session_unauthorized_with_hmac_only(hmac_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/inject/missing", json={"text": "hello"})

    assert response.status_code == 401
