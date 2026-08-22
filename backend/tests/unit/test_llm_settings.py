import pytest

from src.infrastructure.llm.settings import LlmSettingsError, load_llm_settings


def test_load_llm_settings_returns_none_when_provider_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert load_llm_settings() is None


def test_load_llm_settings_requires_model_for_openai(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")

    with pytest.raises(LlmSettingsError, match="LLM_MODEL is required"):
        load_llm_settings()


def test_load_llm_settings_requires_key_for_openai(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-5")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(LlmSettingsError, match="OPENAI_API_KEY or LLM_API_KEY is required"):
        load_llm_settings()


def test_load_llm_settings_accepts_openai_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", " OpenAI ")
    monkeypatch.setenv("LLM_MODEL", "gpt-5")
    monkeypatch.setenv("LLM_API_KEY", "sk-local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-standard")

    settings = load_llm_settings()

    assert settings is not None
    assert settings.provider == "openai"
    assert settings.model == "gpt-5"
    assert settings.api_key == "sk-local"


def test_load_llm_settings_rejects_unsupported_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude")
    monkeypatch.setenv("LLM_API_KEY", "secret")

    with pytest.raises(LlmSettingsError, match="Unsupported LLM_PROVIDER"):
        load_llm_settings()
