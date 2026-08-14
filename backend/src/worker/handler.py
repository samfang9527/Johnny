from __future__ import annotations

import logging

from ..infrastructure.queue.task_message import TaskMessage


logger = logging.getLogger(__name__)


def process_task(message: TaskMessage) -> None:
    logger.info("Processing task type=%s payload_keys=%s", message.task_type, sorted(message.payload.keys()))
