from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..application.interfaces.schedule_repository import DueSchedule
from ..application.interfaces.task_queue import TaskEnvelope
from ..infrastructure.queue.publisher import InMemoryTaskQueue


logger = logging.getLogger(__name__)


def get_due_schedules(now: datetime) -> list[DueSchedule]:
    return [
        DueSchedule(
            schedule_id="example-schedule",
            task_type="example_task",
            payload={"scheduled_for": now.isoformat()},
            next_run_at=now,
        )
    ]


def handler(event: dict, context: object) -> dict:
    now = datetime.now(timezone.utc)
    queue = InMemoryTaskQueue()
    due_schedules = get_due_schedules(now)

    for schedule in due_schedules:
        queue.publish(TaskEnvelope(task_type=schedule.task_type, payload=schedule.payload))

    logger.info("Dispatched %s schedules", len(due_schedules))
    return {
        "status": "ok",
        "dispatched_count": len(due_schedules),
        "event_keys": sorted(event.keys()),
    }
