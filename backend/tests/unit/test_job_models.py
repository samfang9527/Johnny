from datetime import datetime, timezone
from importlib import import_module


ScheduledJobModel = import_module("Johnny.infrastructure.database.models").ScheduledJobModel


def test_scheduled_job_model_defaults() -> None:
    job = ScheduledJobModel(
        job_id="job-1",
        task_type="sync",
        cron_expression="0 * * * *",
        next_run_at=datetime.now(timezone.utc),
    )

    assert job.status == "ACTIVE"
    assert job.payload == {}
