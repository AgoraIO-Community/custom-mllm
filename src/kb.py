from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.settings import settings

_LINE_SEP = " | "
_SIDE_FILENAMES = {
    "pro": "pro_live_tweets.txt",
    "con": "con_live_tweets.txt",
}

_COHOST_ERROR_PATTERNS = re.compile(
    r"having trouble thinking|trouble thinking|please try again|something went wrong",
    re.IGNORECASE,
)


@dataclass
class KbPoint:
    id: str
    text: str
    ingested_at: datetime


def _format_line(point_id: str, text: str) -> str:
    return f"{point_id}{_LINE_SEP}{text}"


def _parse_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or _LINE_SEP not in stripped:
        return None
    point_id, text = stripped.split(_LINE_SEP, 1)
    point_id = point_id.strip()
    text = text.strip()
    if not point_id or not text:
        return None
    return point_id, text


class KnowledgeBase:
    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir_override = base_dir

    def _base_dir(self) -> Path:
        if self._base_dir_override is not None:
            return Path(self._base_dir_override)
        return Path(settings.kb_data_dir)

    def _debate_dir(self, debate_session_id: str) -> Path:
        return self._base_dir() / debate_session_id

    def _side_file(self, debate_session_id: str, side: str) -> Path:
        filename = _SIDE_FILENAMES.get(side)
        if filename is None:
            raise ValueError(f"Unknown side: {side}")
        return self._debate_dir(debate_session_id) / filename

    def _ingested_meta_file(self, debate_session_id: str, side: str) -> Path:
        side_file = self._side_file(debate_session_id, side)
        return side_file.with_suffix(".ingested.json")

    def _load_ingested_meta(self, meta_path: Path) -> dict[str, str]:
        if not meta_path.is_file():
            return {}
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_ingested_meta(self, meta_path: Path, meta: dict[str, str]) -> None:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load_side_points(self, debate_session_id: str, side: str) -> list[KbPoint]:
        side_file = self._side_file(debate_session_id, side)
        if not side_file.is_file():
            return []

        meta = self._load_ingested_meta(self._ingested_meta_file(debate_session_id, side))
        points: list[KbPoint] = []
        for line in side_file.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(line)
            if parsed is None:
                continue
            point_id, text = parsed
            ingested_raw = meta.get(point_id)
            if isinstance(ingested_raw, str):
                ingested_at = datetime.fromisoformat(ingested_raw)
            else:
                ingested_at = datetime.fromtimestamp(side_file.stat().st_mtime, tz=timezone.utc)
            points.append(KbPoint(id=point_id, text=text, ingested_at=ingested_at))
        return points

    def _write_side_points(
        self,
        debate_session_id: str,
        side: str,
        points: list[KbPoint],
    ) -> None:
        side_file = self._side_file(debate_session_id, side)
        side_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [_format_line(point.id, point.text) for point in points]
        content = "\n".join(lines)
        if lines:
            content += "\n"

        temp_path = side_file.with_suffix(".txt.tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(side_file)

        meta = {point.id: point.ingested_at.isoformat() for point in points}
        self._save_ingested_meta(self._ingested_meta_file(debate_session_id, side), meta)

    def ingest(self, debate_session_id: str, side: str, point_id: str, text: str) -> None:
        points = self._load_side_points(debate_session_id, side)
        now = datetime.now(timezone.utc)

        for point in points:
            if point.id == point_id:
                point.text = text
                self._write_side_points(debate_session_id, side, points)
                return

        points.append(KbPoint(id=point_id, text=text, ingested_at=now))
        self._write_side_points(debate_session_id, side, points)

    def latest(self, debate_session_id: str, side: str) -> KbPoint | None:
        points = self._load_side_points(debate_session_id, side)
        if not points:
            return None
        return max(points, key=lambda point: point.ingested_at)

    def list_side(self, debate_session_id: str, side: str) -> list[KbPoint]:
        points = self._load_side_points(debate_session_id, side)
        return sorted(points, key=lambda point: point.ingested_at, reverse=True)

    def list_side_chronological(self, debate_session_id: str, side: str) -> list[KbPoint]:
        return self._load_side_points(debate_session_id, side)

    def side_point_count(self, debate_session_id: str, side: str) -> int:
        return len(self._load_side_points(debate_session_id, side))

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
            "Reply like a live debate: answer your co-host first; use timeline facts only as ammunition.\n"
            "STEP 1 — React directly to what co-host just said (their claim, not a new topic).\n"
            "STEP 2 — Only if ONE bullet below sharpens that reply, weave it in as your own take.\n"
            "STEP 3 — Skip bullets that do not answer their last line. Do not force a random fact.\n"
            "Pick the bullet that best supports your reply to their LAST claim — not the newest by default.\n"
            "Do not read bullets aloud. Do not cite @handles or poster display names.\n"
            "Do not invent facts beyond this context.\n"
            "\n"
            f"Timeline (use at most one that supports your reply to co-host):\n{bullets}\n"
            "\n"
            "1-2 spoken sentences (~30 words). Plain English. No lists or headers."
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
        root = self._base_dir()
        if not root.is_dir():
            return []
        return sorted(
            path.name
            for path in root.iterdir()
            if path.is_dir()
        )

    def clear(self) -> None:
        root = self._base_dir()
        if root.is_dir():
            shutil.rmtree(root)


def sanitize_cohost_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or _COHOST_ERROR_PATTERNS.search(stripped):
        return ""
    return stripped


def _cohost_section(cohost_line: str) -> str:
    cleaned = sanitize_cohost_line(cohost_line)
    if cleaned:
        return f'Co-host just said:\n"{cleaned}"'
    return (
        "Co-host's last line was unclear. Address their most recent substantive point "
        "from the conversation above — do not comment on audio or system errors."
    )


def merge_user_turn_with_context(context_block: str, cohost_line: str) -> str:
    return f"{_cohost_section(cohost_line)}\n\n{context_block}"


def merge_user_turn_without_cohost(context_block: str) -> str:
    return (
        f"{context_block}\n\n"
        "Your co-host has not spoken yet. Give a short take on the topic; "
        "use a timeline fact only if it fits naturally."
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
