"""add async agent flows

Revision ID: 0005_add_async_agent_flows
Revises: 0004_add_integration_credentials
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_async_agent_flows"
down_revision = "0004_add_integration_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "agent_tasks" not in table_names:
        op.create_table(
            "agent_tasks",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("task_type", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=False),
            sa.Column("idempotency_key", sa.String(length=240), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("last_error_type", sa.String(length=120), nullable=True),
            sa.Column("last_error_message", sa.String(length=2000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('queued', 'processing', 'completed', 'failed', 'dead_lettered')",
                name=op.f("ck_agent_tasks_agent_task_status"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
            sa.UniqueConstraint("idempotency_key", name=op.f("uq_agent_tasks_idempotency_key")),
        )


def downgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "agent_tasks" in table_names:
        op.drop_table("agent_tasks")
