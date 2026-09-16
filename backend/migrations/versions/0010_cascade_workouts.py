"""cascade workouts from training plans

Revision ID: 0010_cascade_workouts
Revises: 0009_agent_run_child_cascade
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_cascade_workouts"
down_revision = "0009_agent_run_child_cascade"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    _replace_workouts_fk(ondelete="CASCADE")


def downgrade() -> None:
    _replace_workouts_fk(ondelete=None)


def _replace_workouts_fk(*, ondelete: str | None) -> None:
    inspector = sa.inspect(op.get_bind())
    if "workouts" not in inspector.get_table_names():
        return

    current_fk = _workouts_training_plan_fk(inspector)
    if current_fk is None or _current_ondelete(current_fk) == ondelete:
        return

    constraint_name = "fk_workouts_training_plan_id_training_plans"
    with op.batch_alter_table("workouts", naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint(
            current_fk["name"] or constraint_name,
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            constraint_name,
            "training_plans",
            ["training_plan_id"],
            ["id"],
            ondelete=ondelete,
        )


def _workouts_training_plan_fk(inspector: sa.Inspector) -> dict | None:
    for foreign_key in inspector.get_foreign_keys("workouts"):
        if foreign_key["referred_table"] == "training_plans" and foreign_key["constrained_columns"] == [
            "training_plan_id"
        ]:
            return foreign_key
    return None


def _current_ondelete(foreign_key: dict) -> str | None:
    ondelete = foreign_key.get("options", {}).get("ondelete")
    return ondelete.upper() if isinstance(ondelete, str) else ondelete
