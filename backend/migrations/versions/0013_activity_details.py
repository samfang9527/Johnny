"""Add append-only activity detail and batch evidence tables.

Revision ID: 0013_activity_details
Revises: 0012_coaching_history
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_activity_details'
down_revision = '0012_coaching_history'
branch_labels = None
depends_on = None


def _timestamps():
    return (sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def _ensure_table(name, *columns):
    if not sa.inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns)


def _ensure_index(name, table, columns):
    if name not in {item['name'] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    # 0001 creates tables from current Base.metadata. A fresh install already has
    # these tables, while an existing 0012 database needs the additive DDL below.
    _ensure_table('activity_detail_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('activity_id', sa.String(36), sa.ForeignKey('activities.id'), nullable=False),
        sa.Column('resource', sa.String(32), nullable=False),
        sa.Column('schema_version', sa.String(80), nullable=False),
        sa.Column('semantic_hash', sa.String(64), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('coverage', sa.JSON(), nullable=False),
        sa.Column('source_payload', sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('activity_id', 'resource', 'schema_version', 'semantic_hash',
                            name='uq_activity_detail_snapshot_content'))
    _ensure_index('ix_activity_detail_snapshots_user_id', 'activity_detail_snapshots', ['user_id'])
    _ensure_index('ix_activity_detail_snapshots_activity_id', 'activity_detail_snapshots', ['activity_id'])

    _ensure_table('activity_segments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot_id', sa.String(36), sa.ForeignKey('activity_detail_snapshots.id'), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('snapshot_id', 'ordinal', name='uq_activity_segment_ordinal'))
    _ensure_index('ix_activity_segments_snapshot_id', 'activity_segments', ['snapshot_id'])

    _ensure_table('activity_sample_chunks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot_id', sa.String(36), sa.ForeignKey('activity_detail_snapshots.id'), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('samples', sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('snapshot_id', 'ordinal', name='uq_activity_sample_chunk_ordinal'))
    _ensure_index('ix_activity_sample_chunks_snapshot_id', 'activity_sample_chunks', ['snapshot_id'])

    _ensure_table('activity_execution_analyses',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('activity_id', sa.String(36), sa.ForeignKey('activities.id'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('algorithm_version', sa.String(80), nullable=False),
        sa.Column('prescription_revision_id', sa.String(36),
                  sa.ForeignKey('workout_prescription_revisions.id')),
        sa.Column('snapshot_ids', sa.JSON(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('user_id', 'fingerprint', name='uq_activity_execution_analysis_content'))
    _ensure_index('ix_activity_execution_analyses_activity_id', 'activity_execution_analyses', ['activity_id'])

    _ensure_table('activity_detail_fetches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('activity_id', sa.String(36), sa.ForeignKey('activities.id'), nullable=False),
        sa.Column('resource', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('current_snapshot_id', sa.String(36), sa.ForeignKey('activity_detail_snapshots.id')),
        sa.Column('last_successful_sync_at', sa.DateTime(timezone=True)),
        sa.Column('last_error_type', sa.String(120)),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('next_retry_at', sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint('user_id', 'activity_id', 'resource', name='uq_activity_detail_fetch_slot'))
    _ensure_index('ix_activity_detail_fetches_activity_id', 'activity_detail_fetches', ['activity_id'])

    _ensure_table('activity_detail_batches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_sync_run_id', sa.String(36)),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
        *_timestamps())
    _ensure_index('ix_activity_detail_batches_user_id', 'activity_detail_batches', ['user_id'])
    _ensure_index('ix_activity_detail_batches_status', 'activity_detail_batches', ['status'])

    _ensure_table('activity_detail_batch_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('activity_detail_batches.id'), nullable=False),
        sa.Column('activity_id', sa.String(36), sa.ForeignKey('activities.id'), nullable=False),
        sa.Column('resource', sa.String(32), nullable=False),
        sa.Column('fetch_id', sa.String(36), sa.ForeignKey('activity_detail_fetches.id')),
        sa.Column('status', sa.String(32), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('batch_id', 'activity_id', 'resource', name='uq_activity_detail_batch_item'))
    _ensure_index('ix_activity_detail_batch_items_batch_id', 'activity_detail_batch_items', ['batch_id'])
    _ensure_index('ix_activity_detail_batch_items_activity_id', 'activity_detail_batch_items', ['activity_id'])
    _ensure_index('ix_activity_detail_batch_items_status', 'activity_detail_batch_items', ['status'])


def downgrade() -> None:
    op.drop_table('activity_detail_batch_items')
    op.drop_table('activity_detail_batches')
    op.drop_table('activity_detail_fetches')
    op.drop_table('activity_execution_analyses')
    op.drop_table('activity_sample_chunks')
    op.drop_table('activity_segments')
    op.drop_table('activity_detail_snapshots')
