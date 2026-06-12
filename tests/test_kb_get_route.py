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
async def test_kb_get_after_ingest():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "pro": {"id": "tweet-1", "text": "pro summary"},
                "con": {"id": "tweet-2", "text": "con summary"},
            },
        )
        response = await client.get("/kb", params={"debate_session_id": "debate-abc"})

    assert response.status_code == 200
    data = response.json()
    assert data["debate_session_id"] == "debate-abc"
    assert len(data["pro"]) == 1
    assert data["pro"][0]["id"] == "tweet-1"
    assert data["pro"][0]["text"] == "pro summary"
    assert "ingested_at" in data["pro"][0]
    assert len(data["con"]) == 1
    assert data["con"][0]["id"] == "tweet-2"


@pytest.mark.asyncio
async def test_kb_get_empty_debate():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/kb", params={"debate_session_id": "debate-empty"})

    assert response.status_code == 200
    data = response.json()
    assert data["pro"] == []
    assert data["con"] == []


@pytest.mark.asyncio
async def test_kb_get_list_all_debates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-one",
                "pro": {"id": "p1", "text": "pro one"},
            },
        )
        await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-two",
                "con": {"id": "c1", "text": "con two"},
            },
        )
        response = await client.get("/kb")

    assert response.status_code == 200
    debates = response.json()["debates"]
    assert len(debates) == 2
    by_id = {item["debate_session_id"]: item for item in debates}
    assert by_id["debate-one"]["pro"][0]["text"] == "pro one"
    assert by_id["debate-two"]["con"][0]["text"] == "con two"


@pytest.mark.asyncio
async def test_kb_get_invalid_debate_session_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/kb", params={"debate_session_id": "bad id!"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_kb_ingest_then_get_reflects_dedupe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "pro": {"id": "tweet-1", "text": "first"},
            },
        )
        await client.post(
            "/kb/ingest",
            json={
                "debate_session_id": "debate-abc",
                "pro": {"id": "tweet-1", "text": "updated"},
            },
        )
        response = await client.get("/kb", params={"debate_session_id": "debate-abc"})

    data = response.json()
    assert len(data["pro"]) == 1
    assert data["pro"][0]["text"] == "updated"
