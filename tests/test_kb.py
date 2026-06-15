import time
from pathlib import Path

from src.kb import KnowledgeBase, _format_line, _parse_line


def test_format_and_parse_line_round_trip():
    line = _format_line("tweet-1", "summary with | pipe inside")
    parsed = _parse_line(line)
    assert parsed == ("tweet-1", "summary with | pipe inside")


def test_ingest_and_latest(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "first point")
    latest = kb.latest("debate-abc", "pro")
    assert latest is not None
    assert latest.id == "tweet-1"
    assert latest.text == "first point"


def test_ingest_writes_id_pipe_text_file(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "first point")
    side_file = kb_data_dir / "debate-abc" / "pro_live_tweets.txt"
    assert side_file.read_text(encoding="utf-8") == "tweet-1 | first point\n"


def test_dedupe_by_id_updates_text_preserves_timestamp(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "first")
    first_at = kb.latest("debate-abc", "pro").ingested_at
    time.sleep(0.01)
    kb.ingest("debate-abc", "pro", "tweet-1", "updated")
    latest = kb.latest("debate-abc", "pro")
    assert latest.text == "updated"
    assert latest.ingested_at == first_at
    assert kb.side_point_count("debate-abc", "pro") == 1


def test_latest_picks_most_recent_by_ingested_at(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "older")
    time.sleep(0.01)
    kb.ingest("debate-abc", "pro", "tweet-2", "newer")
    latest = kb.latest("debate-abc", "pro")
    assert latest.id == "tweet-2"


def test_pro_and_con_are_isolated(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "pro text")
    kb.ingest("debate-abc", "con", "tweet-2", "con text")
    assert kb.latest("debate-abc", "pro").text == "pro text"
    assert kb.latest("debate-abc", "con").text == "con text"


def test_latest_returns_none_when_empty(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    assert kb.latest("debate-missing", "pro") is None


def test_list_side_chronological_oldest_first(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "first")
    time.sleep(0.01)
    kb.ingest("debate-abc", "pro", "tweet-2", "second")
    points = kb.list_side_chronological("debate-abc", "pro")
    assert [point.id for point in points] == ["tweet-1", "tweet-2"]


def test_restart_survival_reads_existing_files(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "alpha")
    kb.ingest("debate-abc", "pro", "tweet-2", "beta")

    reloaded = KnowledgeBase(str(kb_data_dir))
    points = reloaded.list_side_chronological("debate-abc", "pro")
    assert [point.id for point in points] == ["tweet-1", "tweet-2"]


def test_format_live_context_includes_framing_and_points(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "alpha")
    kb.ingest("debate-abc", "pro", "tweet-2", "beta")
    context, points = kb.format_live_context("debate-abc", "pro")
    assert context is not None
    assert context.startswith("[LIVE CONTEXT - PRO]")
    assert "Context:\n- alpha\n- beta" in context
    assert "tweet-1" not in context
    assert "Co-host just said" not in context
    assert [point.id for point in points] == ["tweet-1", "tweet-2"]


def test_format_live_thread_delegates_to_live_context(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "alpha")
    thread, points = kb.format_live_thread("debate-abc", "pro")
    context, context_points = kb.format_live_context("debate-abc", "pro")
    assert thread == context
    assert points == context_points


def test_format_live_thread_own_side_only(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-abc", "pro", "tweet-1", "pro text")
    kb.ingest("debate-abc", "con", "tweet-2", "con text")
    thread, points = kb.format_live_context("debate-abc", "pro")
    assert thread is not None
    assert "con text" not in thread
    assert len(points) == 1


def test_format_live_thread_cap_keeps_newest(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    for index in range(5):
        kb.ingest("debate-abc", "pro", f"tweet-{index}", f"point-{index}")
        time.sleep(0.001)
    thread, points = kb.format_live_thread("debate-abc", "pro", max_points=3)
    assert [point.id for point in points] == ["tweet-2", "tweet-3", "tweet-4"]
    assert "point-0" not in thread
    assert "point-4" in thread


def test_format_live_thread_empty_returns_none(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    thread, points = kb.format_live_context("debate-abc", "pro")
    assert thread is None
    assert points == []


def test_list_debates_scans_directories(kb_data_dir: Path):
    kb = KnowledgeBase(str(kb_data_dir))
    kb.ingest("debate-one", "pro", "tweet-1", "one")
    kb.ingest("debate-two", "con", "tweet-2", "two")
    assert kb.list_debates() == ["debate-one", "debate-two"]
