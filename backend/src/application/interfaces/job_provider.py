from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ScheduledJobRecord:
    job_id: str
    task_type: str
    cron_expression: str
    next_run_at: datetime
    payload: dict


class DueJobProvider(Protocol):
    def list_due_jobs(
        self,
        now: datetime,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ScheduledJobRecord]:
        ...
