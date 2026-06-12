from unittest.mock import patch

import pytest

from src.upstream import resolve_chat_upstream, resolve_upstream


@pytest.fixture
def mock_settings():
    with patch("src.upstream.settings") as s:
        s.xai_api_key = "xai-test-key"
        s.xai_model = "grok-voice-latest"
        s.openai_api_key = "sk-test-key"
        s.openai_model = "gpt-realtime"
        s.openai_chat_model = "gpt-4o-mini"
        s.xai_chat_model = "grok-4.3"
        yield s


def test_resolve_openai(mock_settings):
    config = resolve_upstream("openai")
    assert config.provider == "openai"
    assert config.model == "gpt-realtime"
    assert config.url == "wss://api.openai.com/v1/realtime?model=gpt-realtime"
    assert config.headers == {"Authorization": "Bearer sk-test-key"}


def test_resolve_xai(mock_settings):
    config = resolve_upstream("xai")
    assert config.provider == "xai"
    assert config.model == "grok-voice-latest"
    assert config.url == "wss://api.x.ai/v1/realtime?model=grok-voice-latest"
    assert config.headers == {"Authorization": "Bearer xai-test-key"}


def test_resolve_missing_provider_defaults_to_xai(mock_settings):
    config = resolve_upstream(None)
    assert config.provider == "xai"
    assert config.url == "wss://api.x.ai/v1/realtime?model=grok-voice-latest"


def test_resolve_openai_missing_api_key(mock_settings):
    mock_settings.openai_api_key = ""
    with pytest.raises(ValueError, match="OPENAI_API_KEY not configured"):
        resolve_upstream("openai")


def test_resolve_xai_missing_api_key(mock_settings):
    mock_settings.xai_api_key = ""
    with pytest.raises(ValueError, match="XAI_API_KEY not configured"):
        resolve_upstream("xai")


def test_resolve_unknown_provider(mock_settings):
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_upstream("gemini")


def test_resolve_chat_openai(mock_settings):
    config = resolve_chat_upstream("openai", "gpt-4o-mini")
    assert config.provider == "openai"
    assert config.model == "gpt-4o-mini"
    assert config.url == "https://api.openai.com/v1/chat/completions"
    assert config.headers == {"Authorization": "Bearer sk-test-key"}


def test_resolve_chat_xai_default_model(mock_settings):
    config = resolve_chat_upstream("xai", None)
    assert config.provider == "xai"
    assert config.model == "grok-4.3"
    assert config.url == "https://api.x.ai/v1/chat/completions"


def test_resolve_chat_unknown_provider(mock_settings):
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_chat_upstream("gemini", "model")
