from __future__ import annotations

from src.application.agent_runtime import RunningCompanionAgent
from src.infrastructure.llm.openai_gateway import OpenAIModelGateway
from src.infrastructure.llm.settings import LlmSettings, LlmSettingsError


def build_running_companion_agent(
    *,
    run_store,
    tools,
    prompt_version: str,
    settings: LlmSettings,
    openai_client=None,
    transaction_factory=None,
) -> RunningCompanionAgent:
    if settings.provider != "openai":
        raise LlmSettingsError(f"Unsupported LLM_PROVIDER: {settings.provider}")
    gateway = OpenAIModelGateway(model=settings.model, api_key=settings.api_key, client=openai_client)
    return RunningCompanionAgent(
        run_store=run_store,
        model_gateway=gateway,
        tools=tools,
        prompt_version=prompt_version,
        provider=settings.provider,
        model=settings.model,
        transaction_factory=transaction_factory,
    )
