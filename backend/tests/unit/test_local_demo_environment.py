from __future__ import annotations

from datetime import date, timedelta

from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.session import create_session_factory


def test_seed_demo_data_creates_today_readable_manual_activity(tmp_path, monkeypatch) -> None:
    from scripts.seed_demo_data import DEMO_USER_ID, main

    database_url = f"sqlite:///{tmp_path / 'johnny-demo.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    main()

    session_factory = create_session_factory(database_url)
    with session_factory() as session:
        activities = SqlAlchemyActivityRepository(session).list_activities_for_user_between(
            DEMO_USER_ID,
            date.today() - timedelta(days=7),
            date.today(),
        )

    assert activities
    assert activities[0].source == "manual"
    assert activities[0].provider_connection_id is None
