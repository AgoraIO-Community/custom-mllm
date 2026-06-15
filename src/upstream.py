from __future__ import annotations

from dataclasses import dataclass

from src.settings import settings


@dataclass(frozen=True)
class UpstreamConfig:
    provider: str
    url: str
    headers: dict[str, str]
    model: str


def resolve_upstream(provider: str | None) -> UpstreamConfig:
    normalized = (provider or "xai").lower()

    if normalized == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        model = settings.openai_model
        return UpstreamConfig(
            provider="openai",
            url=f"wss://api.openai.com/v1/realtime?model={model}",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            model=model,
        )

    if normalized == "xai":
        if not settings.xai_api_key:
            raise ValueError("XAI_API_KEY not configured")
        model = settings.xai_model
        return UpstreamConfig(
            provider="xai",
            url=f"wss://api.x.ai/v1/realtime?model={model}",
            headers={"Authorization": f"Bearer {settings.xai_api_key}"},
            model=model,
        )

    raise ValueError(f"Unknown provider: {provider}")


def resolve_chat_upstream(provider: str | None, model: str | None) -> UpstreamConfig:
    normalized = (provider or "").lower()

    if normalized == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        resolved_model = model or settings.openai_chat_model
        return UpstreamConfig(
            provider="openai",
            url="https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            model=resolved_model,
        )

    if normalized == "xai":
        if not settings.xai_api_key:
            raise ValueError("XAI_API_KEY not configured")
        resolved_model = model or settings.xai_chat_model
        return UpstreamConfig(
            provider="xai",
            url="https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.xai_api_key}"},
            model=resolved_model,
        )

    raise ValueError(f"Unknown provider: {provider}")


def is_openai_restricted_chat_model(model: str) -> bool:
    """GPT-5 and reasoning models reject several standard chat params."""
    normalized = model.lower()
    if normalized.startswith("gpt-5"):
        return True
    if normalized.startswith(("o1", "o3", "o4")):
        return True
    return False


def normalize_chat_completion_payload(payload: dict, model: str) -> dict:
    if not is_openai_restricted_chat_model(model):
        return payload

    normalized = dict(payload)
    if "max_tokens" in normalized:
        if "max_completion_tokens" not in normalized:
            normalized["max_completion_tokens"] = normalized["max_tokens"]
        del normalized["max_tokens"]

    temperature = normalized.get("temperature")
    if temperature is not None and temperature != 1:
        del normalized["temperature"]

    return normalized
