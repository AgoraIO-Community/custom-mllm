from __future__ import annotations

VALID_PIPELINE_MODES = frozenset({"mllm", "llm"})


def parse_pipeline_mode(value: str | None, expected: str) -> str | None:
    """Return an error message if pipeline_mode is missing or wrong, else None."""
    if expected not in VALID_PIPELINE_MODES:
        raise ValueError(f"invalid expected pipeline mode: {expected}")

    if not value:
        return f"pipeline_mode is required (expected {expected})"

    if value not in VALID_PIPELINE_MODES:
        return f"invalid pipeline_mode: {value}"

    if value != expected:
        return f"pipeline_mode must be {expected}"

    return None
