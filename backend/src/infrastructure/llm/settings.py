from __future__ import annotations

import os
from dataclasses import dataclass


class LlmSettingsError(ValueError):
    pass


@dataclass(frozen=True)
class LlmSettings:
    provider: str
    model: str
    api_key: str


def resolve_queued_training_plan_provider() -> tuple[str, str]:
    provider = _normalized_env("LLM_PROVIDER")
    if provider and provider not in ("openai", "local"):
        raise LlmSettingsError(f"Unsupported LLM_PROVIDER: {provider}")

    api_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    if not api_key:
        return "local", "deterministic-local-companion"

    model = _env("LLM_MODEL")
    if not model:
        raise LlmSettingsError("LLM_MODEL is required when an API key is configured")
    return "openai", model


def resolve_queued_daily_advice_provider() -> tuple[str, str]:
    """Freeze the configured model when a daily advice run is queued."""
    return resolve_queued_training_plan_provider()


def load_openai_settings_for_queued_model(model: str) -> LlmSettings:
    persisted_model = model.strip() if model else None
    if not persisted_model:
        raise LlmSettingsError("Queued OpenAI model is required")

    api_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    if not api_key:
        raise LlmSettingsError("OPENAI_API_KEY or LLM_API_KEY is required for queued OpenAI runs")
    return LlmSettings(provider="openai", model=persisted_model, api_key=api_key)


def load_llm_settings() -> LlmSettings | None:
    provider = _normalized_env("LLM_PROVIDER")
    if not provider:
        return None
    if provider != "openai":
        raise LlmSettingsError(f"Unsupported LLM_PROVIDER: {provider}")

    model = _env("LLM_MODEL")
    if not model:
        raise LlmSettingsError("LLM_MODEL is required when LLM_PROVIDER=openai")

    api_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    if not api_key:
        raise LlmSettingsError("OPENAI_API_KEY or LLM_API_KEY is required when LLM_PROVIDER=openai")

    return LlmSettings(provider=provider, model=model, api_key=api_key)


def _normalized_env(name: str) -> str | None:
    value = _env(name)
    return value.lower() if value else None


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
