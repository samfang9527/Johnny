"""Backfill planning selects closed local dates without provider calls."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.application.activity_detail_backfill import ActivityDetailBackfill
from src.application.activity_detail_sync import ActivityDetailSyncService
from src.infrastructure.database.models import (
    ActivityDetailBatchModel, ActivityModel, AgentTaskModel, AthleteProfileModel, Base,
    IntegrationConnectionModel, UserModel,
)

NOW = datetime(2026, 10, 22, 16, 30, tzinfo=timezone.utc)  # Oct 23 in Taipei.


def test_backfill_prioritizes_recent_seven_closed_dates_and_skips_manual_foreign_current(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'backfill.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all([
            UserModel(id='owner', email='owner@example.invalid', display_name='Owner'),
            UserModel(id='foreign', email='foreign@example.invalid', display_name='Foreign'),
        ])
        session.flush()
        session.add(AthleteProfileModel(user_id='owner', timezone='Asia/Taipei'))
        session.add_all([
            IntegrationConnectionModel(id='conn', user_id='owner', provider='garmin_connect'),
            IntegrationConnectionModel(id='foreign-conn', user_id='foreign', provider='garmin_connect'),
        ])
        session.flush()
        for aid, day, hour, owner, connection, provider_id in [
            ('recent', 22, 15, 'owner', 'conn', 'p-recent'),
            ('older', 1, 15, 'owner', 'conn', 'p-older'),
            ('too-old', 24, 15, 'owner', 'conn', 'p-old'),
            ('current', 22, 17, 'owner', 'conn', 'p-current'),
            ('manual', 22, 14, 'owner', None, None),
            ('other-user', 22, 14, 'foreign', 'foreign-conn', 'p-other'),
        ]:
            month = 9 if aid == 'too-old' else 10
            session.add(ActivityModel(id=aid, user_id=owner, provider_connection_id=connection,
                provider_activity_id=provider_id, started_at=datetime(2026, month, day, hour,
                    tzinfo=timezone.utc), activity_type='running'))
        session.commit()

    backfill = ActivityDetailBackfill(factory)
    plan = backfill.plan(user_id='owner', days=28, now=NOW)
    assert plan.activity_ids == ('recent', 'older')
    assert (plan.recent_count, plan.older_count) == (1, 1)
    from scripts.backfill_activity_details import main
    assert main(['--database-url', str(engine.url), '--user-id', 'owner',
                 '--days', '28', '--dry-run', '--as-of', NOW.isoformat()]) == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentTaskModel)) == 0

    class Provider:
        def fetch_activity_detail(self, **kwargs):
            raise AssertionError('planning/enqueue must not call Garmin')

    service = ActivityDetailSyncService(factory, lambda session: Provider(), resources=('fit',))
    batch_ids = backfill.enqueue(plan, service=service, now=NOW)
    assert len(batch_ids) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentTaskModel)) == 3
    assert main(['--database-url', str(engine.url), '--user-id', 'owner',
                 '--pause', batch_ids[0]]) == 0
    with factory() as session:
        assert session.get(ActivityDetailBatchModel, batch_ids[0]).status == 'paused'
    assert main(['--database-url', str(engine.url), '--user-id', 'owner',
                 '--resume', batch_ids[0]]) == 0
    with factory() as session:
        assert session.get(ActivityDetailBatchModel, batch_ids[0]).status == 'pending'
    engine.dispose()
