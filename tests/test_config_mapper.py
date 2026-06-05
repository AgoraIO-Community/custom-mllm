from src.config_mapper import agora_mllm_to_session_update

SAMPLE_MLLM = {
    "enable": True,
    "vendor": "xai",
    "url": "wss://api.x.ai/v1/realtime",
    "messages": [{"role": "user", "content": "You are a debate moderator."}],
    "params": {"voice": "rex", "language": "en", "sample_rate": 24000},
    "turn_detection": {
        "mode": "server_vad",
        "server_vad_config": {
            "threshold": 0.6,
            "prefix_padding_ms": 700,
            "silence_duration_ms": 800,
        },
    },
}


def test_maps_voice_and_instructions():
    event = agora_mllm_to_session_update(SAMPLE_MLLM)
    assert event["type"] == "session.update"
    assert event["session"]["voice"] == "rex"
    assert event["session"]["instructions"] == "You are a debate moderator."


def test_maps_audio_sample_rate():
    event = agora_mllm_to_session_update(SAMPLE_MLLM)
    assert event["session"]["audio"]["input"]["format"]["rate"] == 24000
    assert event["session"]["audio"]["output"]["format"]["rate"] == 24000


def test_maps_language_hint():
    event = agora_mllm_to_session_update(SAMPLE_MLLM)
    assert event["session"]["audio"]["input"]["transcription"]["language_hint"] == "en"


def test_maps_server_vad():
    event = agora_mllm_to_session_update(SAMPLE_MLLM)
    vad = event["session"]["turn_detection"]
    assert vad["type"] == "server_vad"
    assert vad["threshold"] == 0.6
    assert vad["silence_duration_ms"] == 800
