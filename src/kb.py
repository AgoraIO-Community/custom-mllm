# TODO: Redis persistence for multi-instance / restart survival

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class KbPoint:
    id: str
    text: str
    ingested_at: datetime


class KnowledgeBase:
    def __init__(self) -> None:
        self._points: dict[tuple[str, str], list[KbPoint]] = {}

    def ingest(self, debate_session_id: str, side: str, point_id: str, text: str) -> None:
        key = (debate_session_id, side)
        points = self._points.setdefault(key, [])
        now = datetime.now(timezone.utc)

        for point in points:
            if point.id == point_id:
                point.text = text
                point.ingested_at = now
                return

        points.append(KbPoint(id=point_id, text=text, ingested_at=now))

    def latest(self, debate_session_id: str, side: str) -> KbPoint | None:
        points = self._points.get((debate_session_id, side))
        if not points:
            return None
        return max(points, key=lambda point: point.ingested_at)

    def list_side(self, debate_session_id: str, side: str) -> list[KbPoint]:
        points = self._points.get((debate_session_id, side), [])
        return sorted(points, key=lambda point: point.ingested_at, reverse=True)

    def list_side_chronological(self, debate_session_id: str, side: str) -> list[KbPoint]:
        points = self._points.get((debate_session_id, side), [])
        return sorted(points, key=lambda point: point.ingested_at)

    def side_point_count(self, debate_session_id: str, side: str) -> int:
        return len(self._points.get((debate_session_id, side), []))

    def format_live_context(
        self,
        debate_session_id: str,
        side: str,
        *,
        max_points: int | None = None,
    ) -> tuple[str | None, list[KbPoint]]:
        points = self.list_side_chronological(debate_session_id, side)
        if max_points is not None and max_points > 0 and len(points) > max_points:
            points = points[-max_points:]
        if not points:
            return None, []

        header = f"[LIVE CONTEXT - {side.upper()}]"
        bullets = "\n".join(f"- {point.text}" for point in points)
        block = (
            f"{header}\n"
            "Use ONLY the facts below from the live timeline for your side. "
            "Paraphrase one as your own hot take in spoken English.\n"
            "Do not read bullets aloud. Do not cite @handles or poster display names.\n"
            "Do not invent facts beyond this context.\n"
            "\n"
            f"Context:\n{bullets}\n"
            "\n"
            "Reply to your co-host in 1-2 spoken sentences (~30 words): "
            "one thread fact plus one sharp push-back."
        )
        return block, points

    def format_live_thread(
        self,
        debate_session_id: str,
        side: str,
        *,
        max_points: int | None = None,
    ) -> tuple[str | None, list[KbPoint]]:
        return self.format_live_context(debate_session_id, side, max_points=max_points)

    def get_debate(self, debate_session_id: str) -> dict[str, list[KbPoint]]:
        return {
            "pro": self.list_side(debate_session_id, "pro"),
            "con": self.list_side(debate_session_id, "con"),
        }

    def list_debates(self) -> list[str]:
        debate_ids: set[str] = set()
        for debate_session_id, _side in self._points:
            debate_ids.add(debate_session_id)
        return sorted(debate_ids)

    def clear(self) -> None:
        self._points.clear()


def merge_user_turn_with_context(context_block: str, cohost_line: str) -> str:
    return f'{context_block}\n\nCo-host just said:\n"{cohost_line.strip()}"'


def merge_user_turn_without_cohost(context_block: str) -> str:
    return (
        f"{context_block}\n\n"
        "Your co-host has not spoken yet. Give a short take using one context fact."
    )


def point_to_dict(point: KbPoint) -> dict[str, str]:
    return {
        "id": point.id,
        "text": point.text,
        "ingested_at": point.ingested_at.isoformat(),
    }


def debate_kb_to_dict(debate_session_id: str, sides: dict[str, list[KbPoint]]) -> dict:
    return {
        "debate_session_id": debate_session_id,
        "pro": [point_to_dict(point) for point in sides["pro"]],
        "con": [point_to_dict(point) for point in sides["con"]],
    }


kb_store = KnowledgeBase()
