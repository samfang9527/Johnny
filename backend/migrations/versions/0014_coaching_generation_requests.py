"""Coalesce coaching generation requests per owner and publication slot.

Revision ID: 0014_coaching_requests
Revises: 0013_activity_details
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_coaching_requests'
down_revision = '0013_activity_details'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('coaching_generation_requests'):
        return
    op.create_table('coaching_generation_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('slot_id', sa.String(36), nullable=False),
        sa.Column('desired_fingerprint', sa.String(64), nullable=False),
        sa.Column('active_fingerprint', sa.String(64)),
        sa.Column('active_request_id', sa.String(36)),
        sa.Column('active_run_id', sa.String(36)),
        sa.Column('completed_fingerprint', sa.String(64)),
        sa.Column('reason', sa.String(120), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'kind', 'slot_id', name='uq_coaching_request_slot'))


def downgrade() -> None:
    op.drop_table('coaching_generation_requests')
