from __future__ import annotations

import json
import logging

from ...application.interfaces.task_queue import TaskEnvelope, TaskQueue


logger = logging.getLogger(__name__)


class InMemoryTaskQueue(TaskQueue):
    """Prototype publisher used by the generated template.

    Replace this with a concrete SQS or broker-backed implementation.
    """

    def publish(self, task: TaskEnvelope) -> None:
        logger.info("Publishing task: %s", json.dumps({"task_type": task.task_type, "payload": task.payload}))
