import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.chat_completions import _build_upstream_payload, _inject_kb_messages
from src.kb import kb_store
from src.main import app
from src.proxy_auth import derive_side_token, format_bearer
from src.settings import settings


@pytest.fixture(autouse=True)
def clear_kb():
    kb_store.clear()
    yield
    kb_store.clear()


@pytest.fixture(autouse=True)
def clear_auth(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "")


def _chat_url(**params: str) -> str:
    defaults = {
        "pipeline_mode": "llm",
        "debate_session_id": "debate-abc",
        "side": "pro",
        "provider": "openai",
        "model": "gpt-4o-mini",
    }
    defaults.update(params)
    query = "&".join(f"{key}={value}" for key, value in defaults.items())
    return f"/v1/chat/completions?{query}"


def _mock_upstream_stream(chunks: list[bytes] | None = None):
    if chunks is None:
        chunks = [b'data: {"id":"1"}\n\n']

    async def fake_aiter_bytes():
        for chunk in chunks:
            yield chunk

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.aiter_bytes = fake_aiter_bytes
    mock_response.aread = AsyncMock(return_value=b"")
    mock_response.request = MagicMock()

    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_cm)

    return mock_client, mock_stream_cm


def test_build_upstream_payload_strips_agora_fields():
    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "turn_id": 3,
        "timestamp": 1234567890,
        "context": {"foo": "bar"},
        "interruptable": True,
        "stream": False,
    }
    payload = _build_upstream_payload(body, "gpt-4o-mini")
    assert payload["model"] == "gpt-4o-mini"
    assert payload["stream"] is True
    assert "turn_id" not in payload
    assert "timestamp" not in payload
    assert "context" not in payload
    assert "interruptable" not in payload


def test_inject_kb_messages_prepends_live_thread():
    kb_store.ingest("debate-abc", "pro", "tweet-1", "live x summary")
    messages = [{"role": "user", "content": "hello"}]
    injected = _inject_kb_messages(messages, "debate-abc", "pro")
    assert injected[0]["role"] == "system"
    assert injected[0]["content"] == "[LIVE THREAD] live x summary"
    assert injected[1] == messages[0]


@pytest.mark.asyncio
async def test_chat_completions_rejects_wrong_pipeline_mode():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            _chat_url(pipeline_mode="mllm"),
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_completions_rejects_non_streaming():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            _chat_url(),
            json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_completions_streams_sse():
    mock_client, _ = _mock_upstream_stream([b"data: {\"id\":\"1\"}\n\n"])

    transport = ASGITransport(app=app)
    with patch("src.chat_completions.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                _chat_url(),
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            ) as response:
                assert response.status_code == 200
                body = b"".join([chunk async for chunk in response.aiter_bytes()])

    assert b"data:" in body
    assert b"[DONE]" in body


@pytest.mark.asyncio
async def test_chat_completions_forwards_kb_injection_to_upstream():
    kb_store.ingest("debate-abc", "pro", "tweet-1", "breaking news")
    mock_client, mock_stream_cm = _mock_upstream_stream()

    transport = ASGITransport(app=app)
    with patch("src.chat_completions.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                _chat_url(),
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                    "turn_id": 2,
                    "timestamp": 999,
                },
            )

    _, kwargs = mock_client.stream.call_args
    payload = kwargs["json"]
    assert payload["messages"][0]["content"] == "[LIVE THREAD] breaking news"
    assert "turn_id" not in payload
    assert "timestamp" not in payload
    assert payload["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_chat_completions_no_kb_forwards_unchanged():
    mock_client, _ = _mock_upstream_stream()

    transport = ASGITransport(app=app)
    with patch("src.chat_completions.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                _chat_url(),
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

    _, kwargs = mock_client.stream.call_args
    payload = kwargs["json"]
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


@pytest.fixture
def hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "test-secret-for-cross-check")
    yield


def _side_bearer(debate_session_id: str, side: str) -> dict[str, str]:
    return {"Authorization": format_bearer(derive_side_token(debate_session_id, side))}


@pytest.mark.asyncio
async def test_chat_completions_unauthorized_without_bearer(hmac_secret):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            _chat_url(),
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_completions_authorized_with_side_token(hmac_secret):
    mock_client, _ = _mock_upstream_stream()

    transport = ASGITransport(app=app)
    with patch("src.chat_completions.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                _chat_url(),
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
                headers=_side_bearer("debate-abc", "pro"),
            )

    assert response.status_code == 200
