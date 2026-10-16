from datetime import date, datetime, timezone

from src.domain.integrations_notifications import SyncSummary
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import Base, IntegrationConnectionModel, SyncRunModel, UserModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_only_complete_activity_import_covers_absent_sessions(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="coverage@example.com", display_name="Coverage")
        uow.session.add(user)
        uow.session.flush()
        connection = IntegrationConnectionModel(user_id=user.id, provider="garmin",
            provider_account_id="coverage", provider_display_name="Coverage", auth_scheme="token",
            sync_status="ready")
        uow.session.add(connection)
        uow.session.flush()
        incomplete = SyncSummary.empty().record_fetched("activities", 10).with_activity_coverage(
            starts_on=date(2026, 10, 9), ends_on=date(2026, 10, 15),
            timezone_name="Asia/Taipei", pagination_complete=False)
        uow.session.add(SyncRunModel(integration_connection_id=connection.id, status="succeeded",
            started_at=datetime(2026, 10, 16, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 16, 1, tzinfo=timezone.utc),
            summary=incomplete.to_payload()))
        uow.session.flush()
        repository = SqlAlchemyCoachingRepository(uow.session)
        assert repository.covered_review_dates(user.id, date(2026, 10, 9), date(2026, 10, 15),
            "Asia/Taipei", datetime(2026, 10, 16, 2, tzinfo=timezone.utc)) == frozenset()
        complete = incomplete.with_activity_coverage(starts_on=date(2026, 10, 9),
            ends_on=date(2026, 10, 15), timezone_name="Asia/Taipei", pagination_complete=True)
        uow.session.add(SyncRunModel(integration_connection_id=connection.id, status="succeeded",
            started_at=datetime(2026, 10, 16, 2, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 16, 3, tzinfo=timezone.utc),
            summary=complete.to_payload()))
        uow.session.flush()
        assert repository.covered_review_dates(user.id, date(2026, 10, 9), date(2026, 10, 15),
            "Asia/Taipei", datetime(2026, 10, 16, 2, tzinfo=timezone.utc)) == frozenset()
        assert len(repository.covered_review_dates(user.id, date(2026, 10, 9), date(2026, 10, 15),
            "Asia/Taipei", datetime(2026, 10, 16, 4, tzinfo=timezone.utc))) == 7
