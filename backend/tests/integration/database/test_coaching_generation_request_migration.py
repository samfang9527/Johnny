"""The request table is additive on a deployed 0013 schema."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_upgrade_from_0013_adds_request_table_without_dropping_reviews(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'coaching-0013.db'}"
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('backend/alembic.ini')
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, '0013_activity_details')
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            # 0001 creates today's model tables on fresh installs. Simulate an
            # actual deployed 0013 database before applying the additive DDL.
            connection.exec_driver_sql('DROP TABLE coaching_generation_requests')
        command.upgrade(config, 'head')
        names = set(inspect(engine).get_table_names())
        assert {'training_reviews', 'workout_advices',
                'coaching_generation_requests'} <= names
        constraints = inspect(engine).get_unique_constraints('coaching_generation_requests')
        assert any(set(item['column_names']) == {'user_id', 'kind', 'slot_id'}
                   for item in constraints)
    finally:
        engine.dispose()
