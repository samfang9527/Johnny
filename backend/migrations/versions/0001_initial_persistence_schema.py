"""initial persistence schema

Revision ID: 0001_initial_persistence_schema
Revises:
Create Date: 2026-08-19
"""

from alembic import op

from src.infrastructure.database.models import Base


revision = "0001_initial_persistence_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
