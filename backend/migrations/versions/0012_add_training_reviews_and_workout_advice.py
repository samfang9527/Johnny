"""Seed append-only history needed by the split coaching workflows.

Revision ID: 0012_coaching_history
Revises: 0011_add_daily_advice
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


revision = "0012_coaching_history"
down_revision = "0011_add_daily_advice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "plan_activation_revisions" not in tables:
        op.create_table(
            "plan_activation_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plan_id", sa.String(36), nullable=False),
            sa.Column("previous_plan_id", sa.String(36)),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("effective_local_date", sa.Date(), nullable=False),
            sa.Column("timezone_name", sa.String(80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "workout_prescription_revisions" not in tables:
        op.create_table(
            "workout_prescription_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plan_id", sa.String(36), nullable=False),
            sa.Column("workout_id", sa.String(36), nullable=False),
            sa.Column("scheduled_for", sa.Date(), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("workout_payload", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(32), nullable=False),
            sa.Column("confidence", sa.String(32), nullable=False),
            sa.Column("recommendation_id", sa.String(36)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    _backfill_existing_plans()


def _backfill_existing_plans() -> None:
    """Capture current structure without pretending old effective times are known."""
    bind = op.get_bind()
    if not {"training_plans", "workouts", "athlete_profiles"}.issubset(
        sa.inspect(bind).get_table_names()
    ):
        return
    metadata = sa.MetaData()
    plans = sa.Table("training_plans", metadata, autoload_with=bind)
    workouts = sa.Table("workouts", metadata, autoload_with=bind)
    profiles = sa.Table("athlete_profiles", metadata, autoload_with=bind)
    activations = sa.Table("plan_activation_revisions", metadata, autoload_with=bind)
    prescriptions = sa.Table("workout_prescription_revisions", metadata, autoload_with=bind)
    now = datetime.now(timezone.utc)
    zones = {row.user_id: row.timezone for row in bind.execute(
        sa.select(profiles.c.user_id, profiles.c.timezone)
    )}
    already_activated = set(bind.scalars(sa.select(activations.c.plan_id)))
    already_snapshotted = set(bind.scalars(sa.select(prescriptions.c.workout_id)))
    for plan in bind.execute(sa.select(plans)).mappings():
        if plan["status"] not in {"active", "superseded", "completed"}:
            continue
        zone_name = zones.get(plan["user_id"], "UTC")
        try:
            local_today = now.astimezone(ZoneInfo(zone_name)).date()
        except ZoneInfoNotFoundError:
            zone_name = "UTC"
            local_today = now.date()
        if plan["id"] not in already_activated:
            bind.execute(activations.insert().values(
                id=str(uuid4()), user_id=plan["user_id"], plan_id=plan["id"],
                previous_plan_id=(plan["metadata_json"] or {}).get("previous_plan_id"),
                effective_at=now, effective_local_date=plan["starts_on"],
                timezone_name=zone_name, created_at=now, updated_at=now,
            ))
        for workout in bind.execute(sa.select(workouts).where(workouts.c.training_plan_id == plan["id"])).mappings():
            if workout["id"] in already_snapshotted:
                continue
            detail = workout["details"] or {}
            payload = {
                "id": workout["id"],
                "scheduled_for": workout["scheduled_for"].isoformat(),
                "workout_type": workout["workout_type"],
                "purpose": detail.get("purpose") or "原課表",
                "planned_duration_minutes": workout["planned_duration_minutes"],
                "planned_distance_meters": detail.get("planned_distance_meters"),
                "pace_range_seconds_per_km": detail.get("pace_range_seconds_per_km"),
                "heart_rate_zone": detail.get("heart_rate_zone"),
                "phase": detail.get("phase"),
                "coach_note": detail.get("coach_note"),
                "steps": detail.get("steps") or [],
                "status": workout["status"],
                "race_goal_id": detail.get("race_goal_id"),
                "race_name": detail.get("race_name"),
                "race_priority": detail.get("race_priority"),
            }
            bind.execute(prescriptions.insert().values(
                id=str(uuid4()), user_id=plan["user_id"], plan_id=plan["id"],
                workout_id=workout["id"], scheduled_for=workout["scheduled_for"],
                effective_at=now, workout_payload=payload, source="legacy_backfill",
                confidence="known" if workout["scheduled_for"] >= local_today else "legacy_uncertain",
                recommendation_id=None, created_at=now, updated_at=now,
            ))


def downgrade() -> None:
    op.drop_table("workout_prescription_revisions")
    op.drop_table("plan_activation_revisions")
