from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TaskEnvelope:
    task_type: str
    payload: dict


class TaskQueue(Protocol):
    def publish(self, task: TaskEnvelope) -> None:
        ...

