"""Upgrade from 0012 is additive and keeps old activity/prescription bytes."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.infrastructure.database.models import (
    ActivityModel, IntegrationConnectionModel, UserModel, WorkoutPrescriptionRevisionModel,
)

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
DETAIL_TABLES = ('activity_detail_snapshots', 'activity_segments', 'activity_sample_chunks',
                 'activity_execution_analyses', 'activity_detail_fetches',
                 'activity_detail_batches', 'activity_detail_batch_items')


def test_upgrade_from_0012_preserves_history_and_manual_pairing(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('backend/alembic.ini')
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, '0012_coaching_history')
    engine = create_engine(url)
    # Existing deployed 0012 databases predate these ORM models. Revision 0001
    # uses current Base.metadata on a fresh database, so remove the new tables
    # here to exercise the real additive upgrade path.
    with engine.begin() as connection:
        for table in reversed(DETAIL_TABLES):
            connection.exec_driver_sql(f'DROP TABLE {table}')
    original = {'source': 'garmin', 'match_reviewed': True, 'matched_workout_id': 'workout-old',
                'session_group_id': 'manual-group'}
    prescription = {'id': 'workout-old', 'steps': [{'step_type': 'work', 'duration_seconds': 600,
                    'target': {'type': 'rpe', 'value': 3}}], 'purpose': 'Original'}
    with Session(engine) as s:
        s.add(UserModel(id='runner', email='runner@example.invalid', display_name='Runner'))
        s.flush()
        s.add(IntegrationConnectionModel(id='conn-old', user_id='runner', provider='garmin_connect'))
        s.flush()
        s.add(ActivityModel(id='activity-old', user_id='runner', provider_connection_id='conn-old',
                            provider_activity_id='g-old', started_at=NOW, activity_type='running',
                            duration_seconds=600, provider_summary=original))
        s.add(WorkoutPrescriptionRevisionModel(id='prescription-old', user_id='runner', plan_id='old-plan',
            workout_id='workout-old', scheduled_for=date(2026, 10, 22), effective_at=NOW,
            workout_payload=prescription, source='legacy_backfill', confidence='legacy_uncertain'))
        s.commit()
    with engine.connect() as c:
        before = [tuple(row) for row in c.execute(select(ActivityModel.id, ActivityModel.provider_summary,
                  ActivityModel.duration_seconds))]
        raw_before = c.execute(text('SELECT id, provider_summary, duration_seconds FROM activities '
                                    'WHERE id = :id'), {'id': 'activity-old'}).one()
        raw_prescription_before = c.execute(text('SELECT workout_payload FROM workout_prescription_revisions '
                                                 'WHERE id = :id'), {'id': 'prescription-old'}).scalar_one()
    command.upgrade(config, 'head')
    inspector = inspect(engine)
    assert set(DETAIL_TABLES).issubset(set(inspector.get_table_names()))
    with Session(engine) as s:
        assert [tuple(row) for row in s.execute(select(ActivityModel.id, ActivityModel.provider_summary,
            ActivityModel.duration_seconds))] == before
        actual = s.get(WorkoutPrescriptionRevisionModel, 'prescription-old')
        assert json.dumps(actual.workout_payload, sort_keys=True) == json.dumps(prescription, sort_keys=True)
        assert actual.confidence == 'legacy_uncertain'
    with engine.connect() as c:
        assert c.execute(text('SELECT id, provider_summary, duration_seconds FROM activities '
                              'WHERE id = :id'), {'id': 'activity-old'}).one() == raw_before
        assert c.execute(text('SELECT workout_payload FROM workout_prescription_revisions '
                              'WHERE id = :id'), {'id': 'prescription-old'}).scalar_one() == raw_prescription_before
    engine.dispose()


def test_fresh_database_upgrade_to_head_has_detail_tables(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('backend/alembic.ini')
    command.upgrade(config, 'head')
    engine = create_engine(url)
    assert set(DETAIL_TABLES).issubset(set(inspect(engine).get_table_names()))
    engine.dispose()


def test_upgrade_recovers_missing_detail_table_in_partial_sqlite_schema(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'partial.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('backend/alembic.ini')
    command.upgrade(config, '0012_coaching_history')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE activity_detail_batch_items')
    command.upgrade(config, 'head')
    assert set(DETAIL_TABLES).issubset(set(inspect(engine).get_table_names()))
    engine.dispose()


def test_detail_migration_version_id_fits_alembic_default():
    from importlib.util import module_from_spec, spec_from_file_location
    path = Path('backend/migrations/versions/0013_activity_details.py')
    assert path.exists()
    spec = spec_from_file_location('detail_migration', path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == '0012_coaching_history'
    assert len(mod.revision) <= 32


def test_postgresql_upgrade_from_0012_preserves_activity_in_isolated_schema(monkeypatch):
    test_url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not test_url:
        pytest.skip('JOHNNY_TEST_DATABASE_URL is not configured')
    parsed = make_url(test_url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('PostgreSQL migration test requires a disposable test database')
    schema = f'activity_detail_{uuid4().hex[:12]}'
    admin_engine = create_engine(parsed)
    with admin_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
    try:
        schema_url = parsed.update_query_dict({'options': f'-csearch_path={schema}'})
        monkeypatch.setenv('DATABASE_URL', schema_url.render_as_string(hide_password=False))
        config = Config('backend/alembic.ini')
        command.upgrade(config, '0012_coaching_history')
        engine = create_engine(schema_url)
        try:
            with engine.begin() as connection:
                for table in reversed(DETAIL_TABLES):
                    connection.exec_driver_sql(f'DROP TABLE {schema}.{table}')
            with Session(engine) as session:
                session.add(UserModel(id='pg-runner', email='pg-runner@example.invalid', display_name='Runner'))
                session.flush()
                session.add(IntegrationConnectionModel(id='pg-conn', user_id='pg-runner',
                                                       provider='garmin_connect'))
                session.flush()
                session.add(ActivityModel(id='pg-activity', user_id='pg-runner', provider_connection_id='pg-conn',
                                          provider_activity_id='g-pg', started_at=NOW,
                                          activity_type='running', provider_summary={'matched_workout_id': 'w-pg'}))
                session.commit()
            with engine.connect() as connection:
                before = connection.execute(text('SELECT provider_summary FROM activities '
                                                  'WHERE id = :id'), {'id': 'pg-activity'}).scalar_one()
            command.upgrade(config, 'head')
            assert set(DETAIL_TABLES).issubset(set(inspect(engine).get_table_names()))
            with engine.connect() as connection:
                assert connection.execute(text('SELECT provider_summary FROM activities '
                                               'WHERE id = :id'), {'id': 'pg-activity'}).scalar_one() == before
        finally:
            engine.dispose()
    finally:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        admin_engine.dispose()
