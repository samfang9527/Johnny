"""add integration credentials

Revision ID: 0004_add_integration_credentials
Revises: 0003_add_auth_sessions
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_integration_credentials"
down_revision = "0003_add_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "integration_credentials" not in table_names:
        op.create_table(
            "integration_credentials",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("integration_connection_id", sa.String(length=36), nullable=False),
            sa.Column("credential_format", sa.String(length=80), nullable=False),
            sa.Column("encrypted_payload", sa.Text(), nullable=False),
            sa.Column("key_id", sa.String(length=160), nullable=False),
            sa.Column("lifecycle_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["integration_connection_id"],
                ["integration_connections.id"],
                name=op.f("fk_integration_credentials_integration_connection_id_integration_connections"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_credentials")),
            sa.UniqueConstraint(
                "integration_connection_id",
                name=op.f("uq_integration_credentials_connection"),
            ),
        )


def downgrade() -> None:
    table_names = sa.inspect(op.get_bind()).get_table_names()
    if "integration_credentials" in table_names:
        op.drop_table("integration_credentials")
