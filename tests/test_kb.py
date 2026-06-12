import time

from src.kb import KnowledgeBase


def test_ingest_and_latest():
    kb = KnowledgeBase()
    kb.ingest("debate-abc", "pro", "tweet-1", "first point")
    latest = kb.latest("debate-abc", "pro")
    assert latest is not None
    assert latest.id == "tweet-1"
    assert latest.text == "first point"


def test_dedupe_by_id_updates_text_and_timestamp():
    kb = KnowledgeBase()
    kb.ingest("debate-abc", "pro", "tweet-1", "first")
    first_at = kb.latest("debate-abc", "pro").ingested_at
    time.sleep(0.01)
    kb.ingest("debate-abc", "pro", "tweet-1", "updated")
    latest = kb.latest("debate-abc", "pro")
    assert latest.text == "updated"
    assert latest.ingested_at >= first_at
    assert len(kb._points[("debate-abc", "pro")]) == 1


def test_latest_picks_most_recent_by_ingested_at():
    kb = KnowledgeBase()
    kb.ingest("debate-abc", "pro", "tweet-1", "older")
    time.sleep(0.01)
    kb.ingest("debate-abc", "pro", "tweet-2", "newer")
    latest = kb.latest("debate-abc", "pro")
    assert latest.id == "tweet-2"


def test_pro_and_con_are_isolated():
    kb = KnowledgeBase()
    kb.ingest("debate-abc", "pro", "tweet-1", "pro text")
    kb.ingest("debate-abc", "con", "tweet-2", "con text")
    assert kb.latest("debate-abc", "pro").text == "pro text"
    assert kb.latest("debate-abc", "con").text == "con text"


def test_latest_returns_none_when_empty():
    kb = KnowledgeBase()
    assert kb.latest("debate-missing", "pro") is None
