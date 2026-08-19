from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class DueSchedule:
    schedule_id: str
    task_type: str
    payload: dict
    next_run_at: datetime


class ScheduleProvider(Protocol):
    def list_due(
        self,
        now: datetime,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DueSchedule]:
        ...
