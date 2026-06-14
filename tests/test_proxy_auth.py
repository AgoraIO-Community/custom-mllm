import pytest

from src.proxy_auth import (
    derive_session_token,
    derive_side_token,
    format_bearer,
    is_auth_enabled,
    verify_bearer,
)
from src.settings import settings

CROSS_CHECK_SECRET = "test-secret-for-cross-check"
SIDE_PRO_HEX = "dc31be4b05899e6e5ef6e5d060036a5db6bbbe0f028ba6b4390e9b27d21bb7a6"
SESSION_HEX = "a846a57a323925d0035f5d20e9ce1da2aeadbdd76e0e3363574f5193678948b7"


@pytest.fixture
def clear_auth(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", "")
    yield


@pytest.fixture
def hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_master_secret", CROSS_CHECK_SECRET)
    yield


def test_is_auth_enabled_false_when_empty(clear_auth):
    assert is_auth_enabled() is False


def test_is_auth_enabled_true_with_master_secret(hmac_secret):
    assert is_auth_enabled() is True


def test_cross_lang_side_token_vector(hmac_secret):
    assert derive_side_token("debate-abc", "pro") == SIDE_PRO_HEX


def test_cross_lang_session_token_vector(hmac_secret):
    assert derive_session_token("debate-abc") == SESSION_HEX


def test_side_tokens_differ_by_side(hmac_secret):
    assert derive_side_token("debate-abc", "pro") != derive_side_token("debate-abc", "con")


def test_verify_bearer_skips_when_auth_disabled(clear_auth):
    assert verify_bearer("") is True


def test_verify_bearer_side_token(hmac_secret):
    token = format_bearer(derive_side_token("debate-abc", "pro"))
    assert verify_bearer(token, debate_session_id="debate-abc", side="pro") is True
    assert verify_bearer(token, debate_session_id="debate-abc", side="con") is False


def test_verify_bearer_session_token(hmac_secret):
    token = format_bearer(derive_session_token("debate-abc"))
    assert verify_bearer(token, debate_session_id="debate-abc") is True
    assert verify_bearer(token, debate_session_id="debate-xyz") is False


def test_verify_bearer_hmac_requires_debate_context(hmac_secret):
    token = format_bearer(derive_side_token("debate-abc", "pro"))
    assert verify_bearer(token) is False
