import json
from unittest.mock import AsyncMock

import pytest

from src.inject import inject_text
from src.session import ProxySession


@pytest.mark.asyncio
async def test_inject_does_not_trigger_response_by_default():
    upstream = AsyncMock()
    session = ProxySession(
        session_id="test",
        downstream_ws=AsyncMock(),
        model="grok-voice-latest",
        upstream_ws=upstream,
    )

    await inject_text(session, "hello", trigger_response=False)

    assert upstream.send.await_count == 1
    payload = json.loads(upstream.send.await_args.args[0])
    assert payload["type"] == "conversation.item.create"


@pytest.mark.asyncio
async def test_inject_triggers_response_when_requested():
    upstream = AsyncMock()
    session = ProxySession(
        session_id="test",
        downstream_ws=AsyncMock(),
        model="grok-voice-latest",
        upstream_ws=upstream,
    )

    await inject_text(session, "hello", trigger_response=True)

    assert upstream.send.await_count == 2
    second = json.loads(upstream.send.await_args_list[1].args[0])
    assert second["type"] == "response.create"
