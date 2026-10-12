"""Gate Daily Advice generation on a usable activity sync."""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.training_analytics import resolve_plan_for_date
from src.domain.daily_advice import RefreshVersion
from src.domain.integrations_notifications import SyncSummary


def activity_sync_usable(summary: SyncSummary, sync_status: str, credential_status: str) -> bool:
    if credential_status != "active" or sync_status not in {"succeeded", "failed"}:
        return False
    activities = summary.resources.get("activities")
    return activities is not None and int(activities.get("failed", 0)) == 0


def recovery_data_limited(summary: SyncSummary) -> bool:
    return any(
        resource_type != "activities" and int(bucket.get("failed", 0)) > 0
        for resource_type, bucket in summary.resources.items()
    )


def queue_after_completed_sync(
    *, user_id: str, anchor_date: date, sync_run, connection,
    training_plans, advice, queue_runs,
):
    """Queue one refresh for a committed activity import in the caller's transaction."""
    if resolve_plan_for_date(training_plans, user_id, anchor_date) is None:
        return None
    if not activity_sync_usable(sync_run.summary, sync_run.status, connection.credential_status):
        version = RefreshVersion(sync_run.finished_at or datetime.now(timezone.utc), sync_run.id)
        if advice.begin_refresh(user_id, anchor_date, version, sync_run.id):
            advice.mark_failed(user_id, anchor_date, version, "sync_failed")
        return None
    run_queue = queue_runs() if callable(queue_runs) else queue_runs
    return run_queue.queue_run(
        user_id=user_id, workflow_name="daily_recommendation", trigger_type="manual",
        idempotency_key=f"daily_advice:sync:{sync_run.id}",
        reuse_terminal=True,
        payload={
            "anchor_date": anchor_date.isoformat(),
            "source_sync_run_id": sync_run.id,
            "limited_recovery": recovery_data_limited(sync_run.summary),
            "refresh_observed_at": (sync_run.finished_at or datetime.now(timezone.utc)).isoformat(),
        },
    )
