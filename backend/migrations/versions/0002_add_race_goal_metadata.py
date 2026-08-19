"""add race goal metadata

Revision ID: 0002_add_race_goal_metadata
Revises: 0001_initial_persistence_schema
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_race_goal_metadata"
down_revision = "0001_initial_persistence_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    column_names = {column["name"] for column in sa.inspect(bind).get_columns("races")}
    if "metadata_json" not in column_names:
        op.add_column("races", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    bind = op.get_bind()
    column_names = {column["name"] for column in sa.inspect(bind).get_columns("races")}
    if "metadata_json" in column_names:
        op.drop_column("races", "metadata_json")
