import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.main import app


def test_realtime_rejects_missing_pipeline_mode():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/realtime?debate_session_id=debate-abc&side=pro&provider=xai"
        ):
            pass


def test_realtime_rejects_llm_pipeline_mode():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/realtime?pipeline_mode=llm&debate_session_id=debate-abc&side=pro&provider=xai"
        ):
            pass
