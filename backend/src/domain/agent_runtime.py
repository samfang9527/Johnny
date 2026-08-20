from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any


RUN_STATUSES = frozenset({"started", "completed", "failed"})
STEP_STATUSES = frozenset({"started", "completed", "failed"})
STEP_TYPES = frozenset({"model", "tool", "safety"})
INJURY_TERMS = frozenset(
    {
        "ache",
        "aches",
        "chest pain",
        "dizzy",
        "dizziness",
        "doctor",
        "hurt",
        "hurts",
        "illness",
        "injury",
        "medical",
        "pain",
        "sick",
        "shin splints",
        "symptom",
        "symptoms",
    }
)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.input_tokens is not None and self.input_tokens < 0:
            raise ValueError("input tokens cannot be negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("output tokens cannot be negative")
        if self.total_tokens is not None and self.total_tokens < 0:
            raise ValueError("total tokens cannot be negative")
        if self.total_tokens is None and self.input_tokens is not None and self.output_tokens is not None:
            object.__setattr__(self, "total_tokens", self.input_tokens + self.output_tokens)

    def to_payload(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class AgentRun:
    user_id: str
    trigger_type: str
    workflow_name: str
    prompt_version: str
    status: str = "started"
    provider: str | None = None
    model: str | None = None
    correlation_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    recommendation_id: str | None = None
    trace_ref: str | None = None
    trace: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user id is required")
        if not self.trigger_type:
            raise ValueError("trigger type is required")
        if not self.workflow_name:
            raise ValueError("workflow name is required")
        if not self.prompt_version:
            raise ValueError("prompt version is required")
        if self.status not in RUN_STATUSES:
            raise ValueError("run status is not supported")
        object.__setattr__(self, "started_at", self.started_at or _utc_now())
        object.__setattr__(self, "trace", dict(self.trace or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @classmethod
    def start(
        cls,
        *,
        user_id: str,
        trigger_type: str,
        workflow_name: str,
        prompt_version: str,
        provider: str | None = None,
        model: str | None = None,
        correlation_id: str | None = None,
        input_summary: str | None = None,
        trace_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        id: str | None = None,
    ) -> AgentRun:
        return cls(
            id=id,
            user_id=user_id,
            trigger_type=trigger_type,
            workflow_name=workflow_name,
            prompt_version=prompt_version,
            provider=provider,
            model=model,
            correlation_id=correlation_id,
            input_summary=input_summary,
            trace_ref=trace_ref,
            metadata=metadata,
            started_at=started_at,
        )

    def complete(
        self,
        *,
        finished_at: datetime | None = None,
        output_summary: str | None = None,
        token_usage: TokenUsage | None = None,
        recommendation_id: str | None = None,
    ) -> AgentRun:
        finished = finished_at or _utc_now()
        usage = token_usage or TokenUsage()
        return replace(
            self,
            status="completed",
            finished_at=finished,
            latency_ms=_latency_ms(self.started_at, finished),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            output_summary=output_summary,
            recommendation_id=recommendation_id,
            error_type=None,
            error_message=None,
        )

    def fail(
        self,
        *,
        finished_at: datetime | None = None,
        error_type: str,
        error_message: str,
    ) -> AgentRun:
        finished = finished_at or _utc_now()
        return replace(
            self,
            status="failed",
            finished_at=finished,
            latency_ms=_latency_ms(self.started_at, finished),
            error_type=error_type,
            error_message=_summary(error_message),
            recommendation_id=None,
        )


@dataclass(frozen=True)
class AgentRunStep:
    agent_run_id: str
    sequence_number: int
    step_type: str
    name: str
    status: str
    tool_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    payload: dict[str, Any] | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_run_id:
            raise ValueError("agent run id is required")
        if self.sequence_number < 1:
            raise ValueError("sequence number must be positive")
        if self.step_type not in STEP_TYPES:
            raise ValueError("step type is not supported")
        if self.status not in STEP_STATUSES:
            raise ValueError("step status is not supported")
        if not self.name:
            raise ValueError("step name is required")
        object.__setattr__(self, "started_at", self.started_at or _utc_now())
        object.__setattr__(self, "payload", dict(self.payload or {}))

    @classmethod
    def complete_tool_call(
        cls,
        *,
        agent_run_id: str,
        sequence_number: int,
        tool_name: str,
        input_summary: str | None,
        output_summary: str | None,
        payload: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> AgentRunStep:
        return cls(
            agent_run_id=agent_run_id,
            sequence_number=sequence_number,
            step_type="tool",
            name=tool_name,
            status="completed",
            tool_name=tool_name,
            input_summary=_summary(input_summary),
            output_summary=_summary(output_summary),
            payload=payload,
            latency_ms=latency_ms,
            finished_at=_utc_now(),
        )

    @classmethod
    def failed(
        cls,
        *,
        agent_run_id: str,
        sequence_number: int,
        step_type: str,
        name: str,
        error_type: str,
        error_message: str,
        tool_name: str | None = None,
    ) -> AgentRunStep:
        return cls(
            agent_run_id=agent_run_id,
            sequence_number=sequence_number,
            step_type=step_type,
            name=name,
            status="failed",
            tool_name=tool_name,
            error_type=error_type,
            error_message=_summary(error_message),
            finished_at=_utc_now(),
        )


@dataclass(frozen=True)
class AgentContextSource:
    agent_run_id: str
    source_type: str
    source_id: str | None = None
    source_summary: str | None = None
    relevance_score: float | None = None
    metadata: dict[str, Any] | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_run_id:
            raise ValueError("agent run id is required")
        if not self.source_type:
            raise ValueError("source type is required")
        object.__setattr__(self, "source_summary", _summary(self.source_summary))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @classmethod
    def create(
        cls,
        *,
        agent_run_id: str,
        source_type: str,
        source_id: str | None = None,
        source_summary: str | None = None,
        relevance_score: float | None = None,
        metadata: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> AgentContextSource:
        return cls(
            id=id,
            agent_run_id=agent_run_id,
            source_type=source_type,
            source_id=source_id,
            source_summary=source_summary,
            relevance_score=relevance_score,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ToolCallRequest:
    tool_name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool name is required")
        object.__setattr__(self, "arguments", dict(self.arguments))

    def to_payload(self) -> dict[str, Any]:
        return {"tool_name": self.tool_name, "arguments": dict(self.arguments)}


@dataclass(frozen=True)
class ModelRequest:
    user_id: str
    workflow_name: str
    prompt_version: str
    messages: tuple[dict[str, str], ...]
    tools: tuple[str, ...] = ()
    context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user id is required")
        if not self.workflow_name:
            raise ValueError("workflow name is required")
        if not self.prompt_version:
            raise ValueError("prompt version is required")
        object.__setattr__(self, "messages", tuple(dict(message) for message in self.messages))
        object.__setattr__(self, "tools", tuple(self.tools))
        object.__setattr__(self, "context", dict(self.context or {}))

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "workflow_name": self.workflow_name,
            "prompt_version": self.prompt_version,
            "messages": list(self.messages),
            "tools": list(self.tools),
            "context": dict(self.context or {}),
        }


@dataclass(frozen=True)
class ModelResponse:
    content: str
    tool_calls: tuple[ToolCallRequest, ...] = ()
    token_usage: TokenUsage | None = None
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "token_usage", self.token_usage or TokenUsage())

    def to_payload(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [tool_call.to_payload() for tool_call in self.tool_calls],
            "token_usage": self.token_usage.to_payload() if self.token_usage else {},
            "provider": self.provider,
            "model": self.model,
        }


@dataclass(frozen=True)
class SafetyDecision:
    category: str
    requires_conservative_response: bool
    blocks_aggressive_training_change: bool
    guidance: str

    @classmethod
    def classify(cls, text: str) -> SafetyDecision:
        normalized = text.lower()
        matched = any(term in normalized for term in INJURY_TERMS)
        if matched:
            return cls(
                category="medical_or_injury_adjacent",
                requires_conservative_response=True,
                blocks_aggressive_training_change=True,
                guidance=(
                    "This may involve pain, injury, illness, or another medical concern. "
                    "Avoid diagnosis, reduce or stop training if symptoms are concerning, "
                    "and consult a medical professional for severe, persistent, or unusual symptoms."
                ),
            )
        return cls(
            category="training",
            requires_conservative_response=False,
            blocks_aggressive_training_change=False,
            guidance="Training guidance may proceed within normal proposal boundaries.",
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _latency_ms(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _summary(value: str | None, *, max_length: int = 2000) -> str | None:
    if value is None:
        return None
    return value[:max_length]
