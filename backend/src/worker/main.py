from __future__ import annotations

import json
import logging
import os

from ..infrastructure.logging.logger_config import setup_logging
from ..infrastructure.queue.task_message import TaskMessage
from .handler import process_task


logger = logging.getLogger(__name__)


def run_worker() -> None:
    setup_logging()
    sample_payload = os.getenv("WORKER_SAMPLE_MESSAGE")
    if not sample_payload:
        logger.info("Worker started. Set WORKER_SAMPLE_MESSAGE to simulate task processing.")
        return

    message = TaskMessage.from_dict(json.loads(sample_payload))
    process_task(message)


if __name__ == "__main__":
    run_worker()
