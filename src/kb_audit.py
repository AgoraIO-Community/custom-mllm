from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.kb import KbPoint
from src.settings import settings

_SIDE_AUDIT_FILENAMES = {
    "pro": "pro.json",
    "con": "con.json",
}


def audit_log_dir() -> str:
    return settings.kb_audit_log_dir.strip()


def audit_path_for_debate_side(debate_session_id: str, side: str) -> Path | None:
    directory = audit_log_dir()
    if not directory:
        return None
    filename = _SIDE_AUDIT_FILENAMES.get(side)
    if filename is None:
        return None
    return Path(directory) / debate_session_id / filename


def normalize_openai_messages(messages: list) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if isinstance(role, str) and isinstance(content, str):
            normalized.append({"role": role, "content": content})
    return normalized


def _load_audit_array(audit_path: Path) -> list:
    if not audit_path.is_file():
        return []
    try:
        data = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def append_debate_audit_record(debate_session_id: str, side: str, record: dict) -> None:
    audit_path = audit_path_for_debate_side(debate_session_id, side)
    if audit_path is None:
        return

    payload = dict(record)
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())

    records = _load_audit_array(audit_path)
    records.append(payload)

    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def audit_kb_ingest(
    debate_session_id: str,
    side: str,
    point_id: str,
    text: str,
    side_point_count: int,
) -> None:
    append_debate_audit_record(
        debate_session_id,
        side,
        {
            "event": "kb.ingest",
            "point_id": point_id,
            "text": text,
            "side_point_count": side_point_count,
        },
    )


def audit_chat_completion(
    *,
    debate_session_id: str,
    side: str,
    turn_id: object,
    agora_timestamp: object,
    provider: str,
    model: str,
    injected_thread: str | None,
    points: list[KbPoint],
    upstream_messages: list,
    assistant_reply: str,
) -> None:
    append_debate_audit_record(
        debate_session_id,
        side,
        {
            "event": "chat.completion",
            "turn_id": turn_id,
            "agora_timestamp": agora_timestamp,
            "provider": provider,
            "request": {
                "model": model,
                "stream": True,
                "messages": normalize_openai_messages(upstream_messages),
            },
            "response": {
                "assistant_reply": assistant_reply,
            },
            "kb": {
                "injected": injected_thread is not None,
                "point_count": len(points),
                "point_ids": [point.id for point in points],
            },
        },
    )


def extract_assistant_reply_from_sse(raw: bytes) -> str:
    text_parts: list[str] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        for choice in event.get("choices", []):
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue
            content = delta.get("content")
            if isinstance(content, str) and content:
                text_parts.append(content)
    return "".join(text_parts)
