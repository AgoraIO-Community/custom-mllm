import json
from pathlib import Path

import pytest

from src.kb import kb_store
from src.kb_audit import (
    append_debate_audit_record,
    audit_chat_completion,
    audit_kb_ingest,
    audit_path_for_debate_side,
    extract_assistant_reply_from_sse,
    normalize_openai_messages,
)
from src.settings import settings


@pytest.fixture
def audit_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "kb_audit_log_dir", str(tmp_path))
    return tmp_path


def test_append_debate_audit_record_noop_when_dir_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "kb_audit_log_dir", "")
    append_debate_audit_record("debate-abc", "pro", {"event": "test"})
    assert list(tmp_path.iterdir()) == []


def test_audit_paths_are_per_debate_and_side(audit_dir: Path):
    assert audit_path_for_debate_side("debate-abc", "pro") == audit_dir / "debate-abc" / "pro.json"
    assert audit_path_for_debate_side("debate-abc", "con") == audit_dir / "debate-abc" / "con.json"


def test_normalize_openai_messages_strips_agora_fields():
    messages = [
        {"role": "system", "content": "persona"},
        {
            "role": "user",
            "content": "hello",
            "turn_id": 2,
            "timestamp": 123,
            "metadata": {"source": "asr"},
        },
    ]
    assert normalize_openai_messages(messages) == [
        {"role": "system", "content": "persona"},
        {"role": "user", "content": "hello"},
    ]


def test_audit_kb_ingest_writes_pretty_json_array(audit_dir: Path):
    audit_kb_ingest("debate-abc", "pro", "tweet-1", "hello world", 1)

    pro_path = audit_dir / "debate-abc" / "pro.json"
    records = json.loads(pro_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["event"] == "kb.ingest"
    assert records[0]["point_id"] == "tweet-1"
    assert "\n" in pro_path.read_text(encoding="utf-8")
    assert not (audit_dir / "debate-abc" / "con.json").exists()


def test_audit_kb_ingest_con_goes_to_con_file(audit_dir: Path):
    audit_kb_ingest("debate-abc", "con", "tweet-2", "con text", 1)
    assert (audit_dir / "debate-abc" / "con.json").exists()
    assert not (audit_dir / "debate-abc" / "pro.json").exists()


def test_audit_chat_completion_writes_openai_request_shape(audit_dir: Path):
    kb_store.ingest("debate-abc", "pro", "tweet-1", "alpha")
    thread, points = kb_store.format_live_thread("debate-abc", "pro")
    upstream_messages = [
        {"role": "system", "content": thread},
        {"role": "user", "content": "debate me", "turn_id": 1},
    ]

    audit_chat_completion(
        debate_session_id="debate-abc",
        side="pro",
        turn_id=3,
        agora_timestamp=123,
        provider="openai",
        model="gpt-4o-mini",
        injected_thread=thread,
        points=points,
        upstream_messages=upstream_messages,
        assistant_reply="Ethanol helps reduce imports.",
    )

    records = json.loads((audit_dir / "debate-abc" / "pro.json").read_text(encoding="utf-8"))
    record = records[0]
    assert record["event"] == "chat.completion"
    assert record["request"] == {
        "model": "gpt-4o-mini",
        "stream": True,
        "messages": [
            {"role": "system", "content": thread},
            {"role": "user", "content": "debate me"},
        ],
    }
    assert record["response"]["assistant_reply"] == "Ethanol helps reduce imports."
    assert record["kb"]["injected"] is True
    assert record["kb"]["point_ids"] == ["tweet-1"]


def test_audit_appends_multiple_records(audit_dir: Path):
    audit_kb_ingest("debate-abc", "pro", "tweet-1", "one", 1)
    audit_kb_ingest("debate-abc", "pro", "tweet-2", "two", 2)

    records = json.loads((audit_dir / "debate-abc" / "pro.json").read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[1]["point_id"] == "tweet-2"


def test_extract_assistant_reply_from_sse():
    raw = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    assert extract_assistant_reply_from_sse(raw) == "Hello world"
