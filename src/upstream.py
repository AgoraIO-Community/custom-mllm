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
