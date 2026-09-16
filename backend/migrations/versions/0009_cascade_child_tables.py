"""cascade agent run child tables

Revision ID: 0009_agent_run_child_cascade
Revises: 0008_training_plan_metadata
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_agent_run_child_cascade"
down_revision = "0008_training_plan_metadata"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    _replace_fk("agent_run_steps", "agent_runs", "agent_run_id", ondelete="CASCADE")
    _replace_fk("agent_context_sources", "agent_runs", "agent_run_id", ondelete="CASCADE")


def downgrade() -> None:
    _replace_fk("agent_context_sources", "agent_runs", "agent_run_id", ondelete=None)
    _replace_fk("agent_run_steps", "agent_runs", "agent_run_id", ondelete=None)


def _replace_fk(table_name: str, referred_table: str, column_name: str, *, ondelete: str | None) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return

    current_fk = _matching_fk(inspector, table_name, referred_table, column_name)
    if current_fk is None or _current_ondelete(current_fk) == ondelete:
        return

    constraint_name = f"fk_{table_name}_{column_name}_{referred_table}"
    with op.batch_alter_table(table_name, naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint(
            current_fk["name"] or constraint_name,
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            constraint_name,
            referred_table,
            [column_name],
            ["id"],
            ondelete=ondelete,
        )


def _matching_fk(inspector: sa.Inspector, table_name: str, referred_table: str, column_name: str) -> dict | None:
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key["referred_table"] == referred_table and foreign_key["constrained_columns"] == [column_name]:
            return foreign_key
    return None


def _current_ondelete(foreign_key: dict) -> str | None:
    ondelete = foreign_key.get("options", {}).get("ondelete")
    return ondelete.upper() if isinstance(ondelete, str) else ondelete
