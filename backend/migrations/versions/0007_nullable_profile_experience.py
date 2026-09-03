"""make athlete profile experience nullable

Revision ID: 0007_nullable_profile_experience
Revises: 0006_agent_run_started_nullable
Create Date: 2026-09-03
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "0007_nullable_profile_experience"
down_revision = "0006_agent_run_started_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "athlete_profiles" not in table_names:
        return
    with op.batch_alter_table("athlete_profiles") as batch_op:
        batch_op.alter_column(
            "experience_level",
            existing_type=sa.String(length=80),
            nullable=True,
            server_default=None,
        )
    op.execute("UPDATE athlete_profiles SET experience_level = NULL WHERE experience_level = 'unknown'")
    _rename_weekly_mileage_metadata_key()


def downgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "athlete_profiles" not in table_names:
        return
    op.execute("UPDATE athlete_profiles SET experience_level = 'unknown' WHERE experience_level IS NULL")
    with op.batch_alter_table("athlete_profiles") as batch_op:
        batch_op.alter_column(
            "experience_level",
            existing_type=sa.String(length=80),
            nullable=False,
            server_default="unknown",
        )


def _rename_weekly_mileage_metadata_key() -> None:
    connection = op.get_bind()
    athlete_profiles = sa.table(
        "athlete_profiles",
        sa.column("id", sa.String(length=36)),
        sa.column("metadata_json", sa.JSON()),
    )
    rows = connection.execute(sa.select(athlete_profiles.c.id, athlete_profiles.c.metadata_json)).mappings()
    for row in rows:
        metadata = _metadata_dict(row["metadata_json"])
        if "current_weekly_mileage" not in metadata or "current_weekly_mileage_km" in metadata:
            continue
        metadata["current_weekly_mileage_km"] = metadata.pop("current_weekly_mileage")
        connection.execute(
            athlete_profiles.update().where(athlete_profiles.c.id == row["id"]).values(metadata_json=metadata)
        )


def _metadata_dict(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        return dict(json.loads(value))
    return {}
