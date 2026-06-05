import logging
import sys

import structlog

from src.settings import settings

AUDIO_EVENT_TYPES = frozenset(
    {"input_audio_buffer.append", "response.output_audio.delta"}
)


def redact_payload_for_log(event_type: str | None, payload: dict) -> dict:
    """Redact base64 audio fields unless LOG_AUDIO is enabled."""
    if settings.log_audio or event_type not in AUDIO_EVENT_TYPES:
        return payload

    redacted = dict(payload)
    for key in ("delta", "audio"):
        if key in redacted and isinstance(redacted[key], str):
            redacted[key] = f"<redacted:{len(redacted[key])} chars>"
    return redacted


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
