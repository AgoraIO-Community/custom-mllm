from src.logging import redact_payload_for_log
from src.relay import log_ws_message, parse_event_type


def test_parse_event_type_json():
    event_type, payload = parse_event_type('{"type":"session.created","session":{"id":"abc"}}')
    assert event_type == "session.created"
    assert isinstance(payload, dict)


def test_parse_event_type_invalid_json():
    event_type, payload = parse_event_type("not-json")
    assert event_type is None
    assert payload == "not-json"


def test_redact_audio_delta():
    raw = {"type": "response.output_audio.delta", "delta": "base64audiodata" * 10}
    redacted = redact_payload_for_log(raw["type"], raw)
    assert redacted["delta"].startswith("<redacted:")


def test_log_ws_message_redacts_audio(capfd):
    import structlog
    from structlog.testing import LogCapture

    cap = LogCapture()
    structlog.configure(processors=[cap], logger_factory=structlog.PrintLoggerFactory())
    logger = structlog.get_logger("test")

    big_delta = "A" * 1000
    log_ws_message(
        "sess-1",
        "upstream_to_downstream",
        f'{{"type":"response.output_audio.delta","delta":"{big_delta}"}}',
        logger,
    )

    assert cap.entries
    entry = cap.entries[0]
    assert entry["payload"]["delta"].startswith("<redacted:")
