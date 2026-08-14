from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScheduledJobModel:
    job_id: str
    task_type: str
    cron_expression: str
    next_run_at: datetime
    payload: dict = field(default_factory=dict)
    status: str = "ACTIVE"


@dataclass
class JobRunModel:
    run_id: str
    job_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None


@dataclass
class OutboxEventModel:
    event_id: str
    topic: str
    payload: dict = field(default_factory=dict)
    created_at: datetime | None = None

