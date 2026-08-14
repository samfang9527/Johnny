from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskMessage:
    task_type: str
    payload: dict

    @classmethod
    def from_dict(cls, data: dict) -> "TaskMessage":
        return cls(task_type=str(data["task_type"]), payload=dict(data.get("payload", {})))

