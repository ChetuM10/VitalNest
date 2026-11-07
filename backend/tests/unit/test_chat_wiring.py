"""T11 wiring: settings, model default, and how the chat service is built at startup."""
import logging

from fastapi.testclient import TestClient

from app.chat import factory
from app.chat.service import ChatService
from app.config import settings
from app.main import create_app


def test_the_default_model_is_claude_haiku_5_5(monkeypatch):
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    assert settings.claude_model() == "claude-haiku-5-5"
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    assert settings.claude_model() == "claude-sonnet-5-5"


def test_the_no_context_threshold_defaults_to_0_845_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("NO_CONTEXT_MIN_DENSE_SCORE", raising=False)
    assert settings.no_context_min_dense_score() == 0.845
    monkeypatch.setenv("NO_CONTEXT_MIN_DENSE_SCORE", "0.9")
    assert settings.no_context_min_dense_score() == 0.9


def test_no_service_is_built_without_both_keys(caplog):
    caplog.set_level(logging.WARNING, logger="vitalnest")
    assert factory.build_chat_service(bm25=None) is None
    assert any("not configured" in r.getMessage() for r in caplog.records)


def test_a_service_is_built_when_both_keys_exist_without_logging_them(monkeypatch, caplog):
    monkeypatch.setenv("PINECONE_API_KEY", "pcsk_test_key_value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-value")
    seen = {}
    monkeypatch.setattr(factory, "open_dense_retriever", lambda key, index: seen.update(pinecone=key, index=index) or object())
    monkeypatch.setattr(factory.ClaudeClient, "from_settings", classmethod(lambda cls, key: seen.update(anthropic=key) or object()))
    caplog.set_level(logging.DEBUG)
    service = factory.build_chat_service(bm25=None)
    assert isinstance(service, ChatService)
    assert seen == {"pinecone": "pcsk_test_key_value", "index": "vitalnest", "anthropic": "sk-ant-test-key-value"}
    assert "pcsk_test_key_value" not in caplog.text and "sk-ant-test-key-value" not in caplog.text


def test_the_app_has_no_chat_service_when_keys_are_missing_and_health_still_works():
    with TestClient(create_app()) as client:
        assert client.app.state.chat_service is None
        assert client.get("/v1/health").status_code == 200


def test_the_app_builds_the_chat_service_at_startup_when_configured(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("app.main.build_chat_service", lambda bm25: sentinel)
    with TestClient(create_app()) as client:
        assert client.app.state.chat_service is sentinel
