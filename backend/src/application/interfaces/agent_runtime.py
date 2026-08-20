from __future__ import annotations

from typing import Protocol

from src.domain.agent_runtime import AgentContextSource, AgentRun, AgentRunStep, ModelRequest, ModelResponse


class AgentRunStore(Protocol):
    def create_run(self, run: AgentRun) -> AgentRun:
        ...

    def get_run_for_user(self, user_id: str, run_id: str | None) -> AgentRun | None:
        ...

    def record_step(self, step: AgentRunStep) -> AgentRunStep:
        ...

    def list_steps_for_run(self, agent_run_id: str) -> list[AgentRunStep]:
        ...

    def record_context_source(self, source: AgentContextSource) -> AgentContextSource:
        ...

    def list_context_sources_for_run(self, agent_run_id: str) -> list[AgentContextSource]:
        ...

    def complete_run(self, run: AgentRun) -> AgentRun:
        ...

    def fail_run(self, run: AgentRun) -> AgentRun:
        ...


class AgentTool(Protocol):
    name: str

    def run(self, *, user_id: str, arguments: dict) -> dict:
        ...


class AgentToolRegistry(Protocol):
    def get(self, name: str) -> AgentTool:
        ...

    def names(self) -> tuple[str, ...]:
        ...


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse:
        ...
