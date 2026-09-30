import pytest

from src.infrastructure.llm import settings as llm_settings
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


@pytest.mark.parametrize(
    ("provider", "llm_key", "openai_key", "model", "expected"),
    [
        (None, "sk-primary", None, "gpt-5", ("openai", "gpt-5")),
        (" OpenAI ", None, "sk-secondary", " gpt-5 ", ("openai", "gpt-5")),
        ("openai", None, None, "gpt-5", ("local", "deterministic-local-companion")),
        (None, "  ", None, "gpt-5", ("local", "deterministic-local-companion")),
        (None, None, None, None, ("local", "deterministic-local-companion")),
    ],
)
def test_resolve_queued_training_plan_provider(
    monkeypatch, provider, llm_key, openai_key, model, expected
) -> None:
    for name, value in (
        ("LLM_PROVIDER", provider),
        ("LLM_API_KEY", llm_key),
        ("OPENAI_API_KEY", openai_key),
        ("LLM_MODEL", model),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    assert llm_settings.resolve_queued_training_plan_provider() == expected


@pytest.mark.parametrize("model", [None, "  "])
def test_queued_provider_rejects_key_without_model(monkeypatch, model) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-private")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if model is None:
        monkeypatch.delenv("LLM_MODEL", raising=False)
    else:
        monkeypatch.setenv("LLM_MODEL", model)

    with pytest.raises(LlmSettingsError, match="LLM_MODEL is required") as error:
        llm_settings.resolve_queued_training_plan_provider()
    assert "sk-private" not in str(error.value)


def test_queued_provider_rejects_unsupported_explicit_provider_without_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(LlmSettingsError, match="Unsupported LLM_PROVIDER"):
        llm_settings.resolve_queued_training_plan_provider()


@pytest.mark.parametrize(
    ("llm_key", "openai_key", "expected_key"),
    [
        ("sk-primary", "sk-secondary", "sk-primary"),
        ("  ", "sk-secondary", "sk-secondary"),
        (None, "sk-secondary", "sk-secondary"),
    ],
)
def test_queued_openai_settings_use_runtime_key_and_persisted_model(
    monkeypatch, llm_key, openai_key, expected_key
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "worker-model")
    if llm_key is None:
        monkeypatch.delenv("LLM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("LLM_API_KEY", llm_key)
    monkeypatch.setenv("OPENAI_API_KEY", openai_key)

    loaded = llm_settings.load_openai_settings_for_queued_model(" queued-model ")

    assert loaded.provider == "openai"
    assert loaded.model == "queued-model"
    assert loaded.api_key == expected_key


@pytest.mark.parametrize("llm_key, openai_key", [(None, None), ("  ", "  ")])
def test_queued_openai_settings_require_runtime_key(monkeypatch, llm_key, openai_key) -> None:
    for name, value in (("LLM_API_KEY", llm_key), ("OPENAI_API_KEY", openai_key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    with pytest.raises(LlmSettingsError, match="API_KEY is required"):
        llm_settings.load_openai_settings_for_queued_model("queued-model")


@pytest.mark.parametrize("model", ["", "  "])
def test_queued_openai_settings_require_persisted_model_without_leaking_key(
    monkeypatch, model
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-private")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(LlmSettingsError, match="model is required") as error:
        llm_settings.load_openai_settings_for_queued_model(model)
    assert "sk-private" not in str(error.value)
