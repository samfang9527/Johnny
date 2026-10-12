"""add one current daily advice per athlete and local date

Revision ID: 0011_add_daily_advice
Revises: 0010_cascade_workouts
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_daily_advice"
down_revision = "0010_cascade_workouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "daily_advices" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "daily_advices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("advice_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("data_freshness", sa.String(length=32), nullable=False),
        sa.Column("reserved_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_run_id", sa.String(length=36), nullable=False),
        sa.Column("refresh_source_sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("plan_version_id", sa.String(length=36), nullable=True),
        sa.Column("workout_id", sa.String(length=36), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=True),
        sa.Column("week_end", sa.Date(), nullable=True),
        sa.Column("execution_mode", sa.String(length=32), nullable=True),
        sa.Column("facts", sa.JSON(), nullable=True),
        sa.Column("week_summary", sa.Text(), nullable=True),
        sa.Column("today_execution", sa.Text(), nullable=True),
        sa.Column("workout_guide", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_sync_run_id", sa.String(length=36), nullable=True),
        sa.Column("source_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_advices")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_daily_advices_user_id_users")),
        sa.UniqueConstraint("user_id", "advice_date", name="uq_daily_advice_user_date"),
        sa.CheckConstraint(
            "state IN ('pending', 'ready', 'sync_failed', 'generation_failed', 'no_plan')",
            name=op.f("ck_daily_advices_daily_advice_state"),
        ),
        sa.CheckConstraint(
            "data_freshness IN ('fresh', 'limited', 'stale')",
            name=op.f("ck_daily_advices_daily_advice_freshness"),
        ),
    )


def downgrade() -> None:
    if "daily_advices" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("daily_advices")
