"""make agent run started_at nullable

Revision ID: 0006_agent_run_started_nullable
Revises: 0005_add_async_agent_flows
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_agent_run_started_nullable"
down_revision = "0005_add_async_agent_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.alter_column(
            "started_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.alter_column(
            "started_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
