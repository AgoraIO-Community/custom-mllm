import pytest
from httpx import ASGITransport, AsyncClient

from src.kb import kb_store
from src.main import app


@pytest.fixture(autouse=True)
def clear_kb():
    kb_store.clear()
    yield
    kb_store.clear()


@pytest.mark.asyncio
async def test_kb_ingest_pro_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "pro": {"id": "tweet-1", "text": "pro summary"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["stored"] == {"pro": True, "con": False}
    assert kb_store.latest("debate-abc", "pro").text == "pro summary"


@pytest.mark.asyncio
async def test_kb_ingest_con_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "con": {"id": "tweet-2", "text": "con summary"},
            },
        )

    assert response.status_code == 200
    assert response.json()["stored"] == {"pro": False, "con": True}


@pytest.mark.asyncio
async def test_kb_ingest_both_sides():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "pro": {"id": "tweet-1", "text": "pro summary"},
                "con": {"id": "tweet-2", "text": "con summary"},
            },
        )

    assert response.status_code == 200
    assert response.json()["stored"] == {"pro": True, "con": True}


@pytest.mark.asyncio
async def test_kb_ingest_missing_debate_session_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/kb/ingest",
            json={"pro": {"id": "tweet-1", "text": "pro summary"}},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_kb_ingest_requires_pro_or_con():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/kb/ingest",
            json={"debate_session_id": "debate-abc"},
        )

    assert response.status_code == 400
