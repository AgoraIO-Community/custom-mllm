"""Map Agora mllm REST config to xAI session.update events."""


def agora_mllm_to_session_update(mllm: dict) -> dict:
    params = mllm.get("params") or {}
    turn_detection = mllm.get("turn_detection") or {}
    vad = turn_detection.get("server_vad_config") or {}

    instructions = "\n".join(
        message["content"]
        for message in mllm.get("messages") or []
        if message.get("content")
    )

    session: dict = {
        "instructions": instructions,
        "voice": params.get("voice", "eve"),
        "turn_detection": {
            "type": "server_vad",
            "threshold": vad.get("threshold", 0.5),
            "prefix_padding_ms": vad.get("prefix_padding_ms", 640),
            "silence_duration_ms": vad.get("silence_duration_ms", 900),
        },
        "audio": {
            "input": {
                "format": {
                    "type": "audio/pcm",
                    "rate": params.get("sample_rate", 24000),
                }
            },
            "output": {
                "format": {
                    "type": "audio/pcm",
                    "rate": params.get("sample_rate", 24000),
                }
            },
        },
    }

    language = params.get("language")
    if language:
        session["audio"]["input"]["transcription"] = {"language_hint": language}

    return {"type": "session.update", "session": session}
