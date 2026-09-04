"""add training plan metadata

Revision ID: 0008_training_plan_metadata
Revises: 0007_nullable_profile_experience
Create Date: 2026-09-03
"""

import sqlalchemy as sa
from alembic import op


revision = "0008_training_plan_metadata"
down_revision = "0007_nullable_profile_experience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "training_plans" not in table_names:
        return
    column_names = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("training_plans")}
    if "metadata_json" not in column_names:
        op.add_column("training_plans", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "training_plans" not in table_names:
        return
    column_names = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("training_plans")}
    if "metadata_json" in column_names:
        op.drop_column("training_plans", "metadata_json")
