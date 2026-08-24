"""add auth sessions

Revision ID: 0003_add_auth_sessions
Revises: 0002_add_race_goal_metadata
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_auth_sessions"
down_revision = "0002_add_race_goal_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "password_credentials" not in table_names:
        op.create_table(
            "password_credentials",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(length=500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_password_credentials_user_id_users")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_password_credentials")),
            sa.UniqueConstraint("email", name=op.f("uq_password_credentials_email")),
            sa.UniqueConstraint("user_id", name=op.f("uq_password_credentials_user_id")),
        )
    if "auth_sessions" not in table_names:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
            sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
        )


def downgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "auth_sessions" in table_names:
        op.drop_table("auth_sessions")
    if "password_credentials" in table_names:
        op.drop_table("password_credentials")
