from src.pipeline import parse_pipeline_mode


def test_parse_pipeline_mode_valid():
    assert parse_pipeline_mode("mllm", "mllm") is None
    assert parse_pipeline_mode("llm", "llm") is None


def test_parse_pipeline_mode_missing():
    assert parse_pipeline_mode(None, "llm") is not None


def test_parse_pipeline_mode_wrong_value():
    assert parse_pipeline_mode("mllm", "llm") is not None
    assert parse_pipeline_mode("llm", "mllm") is not None


def test_parse_pipeline_mode_invalid():
    assert parse_pipeline_mode("invalid", "llm") is not None
