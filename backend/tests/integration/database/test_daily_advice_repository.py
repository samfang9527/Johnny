from datetime import date, datetime, timezone

from sqlalchemy import func, select

from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.models import Base, DailyAdviceModel, UserModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


ADVICE_DAY = date(2026, 10, 12)


def _version(hour: int, run_id: str) -> RefreshVersion:
    return RefreshVersion(datetime(2026, 10, 12, hour, tzinfo=timezone.utc), run_id)


def _advice(
    user_id: str, run_id: str, *, sync_id: str = "sync-1", summary: str = "本週依照計畫完成。"
) -> DailyAdvice:
    return DailyAdvice(
        user_id=user_id,
        advice_date=ADVICE_DAY,
        plan_version_id="plan-1",
        workout_id="workout-1",
        week_start=date(2026, 10, 7),
        week_end=date(2026, 10, 13),
        execution_mode="follow_plan",
        facts=WeekExecution(
            week_start=date(2026, 10, 7),
            week_end=date(2026, 10, 13),
            status="on_plan",
            planned_count=3,
            completed_count=2,
            missed_count=0,
            extra_count=0,
            planned_minutes=120,
            actual_minutes=118,
            planned_distance_meters=24_000,
            actual_distance_meters=23_800,
            today_completed=False,
            evidence={"completed_workout_ids": ["workout-7", "workout-9"]},
        ),
        sections=AdviceSections(
            week_summary=summary,
            today_execution="今天照計畫輕鬆跑。",
            workout_guide=WorkoutGuide(
                purpose="建立有氧基礎",
                expected_feel="結束時仍有餘力",
                if_too_hard="放慢速度或縮短時間",
                if_too_easy="保持輕鬆，不必加速",
            ),
        ),
        generated_at=datetime(2026, 10, 12, 4, 5, tzinfo=timezone.utc),
        source_sync_run_id=sync_id,
        source_run_id=run_id,
        state="ready",
        data_freshness="fresh",
    )


def _users(sqlite_session_factory) -> tuple[str, str]:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        first = UserModel(email="first-advice@example.com", display_name="First")
        second = UserModel(email="second-advice@example.com", display_name="Second")
        uow.session.add_all((first, second))
        uow.commit()
        return first.id, second.id


def test_one_current_row_per_user_and_date_is_owner_scoped(sqlite_session_factory) -> None:
    first_user, second_user = _users(sqlite_session_factory)
    version = _version(4, "run-1")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(first_user, ADVICE_DAY, version, "sync-1") is True
        first = repository.get_for_user_date(first_user, ADVICE_DAY)
        assert first is not None
        assert repository.get_for_user_date(second_user, ADVICE_DAY) is None
        assert repository.get_for_user_date(first_user, date(2026, 10, 11)) is None
        assert repository.begin_refresh(first_user, ADVICE_DAY, version, "sync-1") is True
        assert repository.begin_refresh(second_user, ADVICE_DAY, version, "sync-2") is True
        assert repository.get_for_user_date(first_user, ADVICE_DAY).id == first.id
        assert uow.session.scalar(select(func.count()).select_from(DailyAdviceModel)) == 2
        uow.commit()


def test_failed_initial_refresh_has_no_invented_sections_or_generation_time(sqlite_session_factory) -> None:
    user_id, _ = _users(sqlite_session_factory)
    version = _version(4, "run-1")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(user_id, ADVICE_DAY, version, "sync-1") is True
        assert repository.mark_failed(user_id, ADVICE_DAY, version, "sync_failed") is True
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyDailyAdviceRepository(uow.session).get_for_user_date(user_id, ADVICE_DAY)

    assert loaded is not None
    assert loaded.state == "sync_failed"
    assert loaded.data_freshness == "limited"
    assert loaded.sections is None
    assert loaded.generated_at is None
    assert loaded.source_run_id is None
    assert loaded.refresh_source_sync_run_id == "sync-1"


def test_publish_round_trips_plan_week_sections_facts_and_provenance(sqlite_session_factory) -> None:
    user_id, _ = _users(sqlite_session_factory)
    version = _version(4, "run-1")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(user_id, ADVICE_DAY, version, "sync-1") is True
        assert repository.publish(user_id, ADVICE_DAY, version, _advice(user_id, "run-1")) is True
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyDailyAdviceRepository(uow.session).get_for_user_date(user_id, ADVICE_DAY)

    assert loaded is not None
    assert loaded.id is not None
    assert loaded.state == "ready"
    assert loaded.data_freshness == "fresh"
    assert (loaded.plan_version_id, loaded.workout_id) == ("plan-1", "workout-1")
    assert (loaded.week_start, loaded.week_end) == (date(2026, 10, 7), date(2026, 10, 13))
    assert loaded.execution_mode == "follow_plan"
    assert loaded.facts is not None
    assert loaded.facts.to_payload() == _advice(user_id, "run-1").facts.to_payload()
    assert loaded.sections is not None
    assert loaded.sections.week_summary == "本週依照計畫完成。"
    assert loaded.sections.workout_guide.expected_feel == "結束時仍有餘力"
    assert loaded.generated_at == datetime(2026, 10, 12, 4, 5, tzinfo=timezone.utc)
    assert (loaded.source_sync_run_id, loaded.source_run_id) == ("sync-1", "run-1")


def test_newer_reservation_and_failure_preserve_old_content_and_reject_late_publish(sqlite_session_factory) -> None:
    user_id, _ = _users(sqlite_session_factory)
    first, older, newer = _version(3, "run-0"), _version(4, "run-1"), _version(5, "run-2")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(user_id, ADVICE_DAY, first, "sync-0") is True
        assert repository.publish(user_id, ADVICE_DAY, first, _advice(user_id, "run-0", sync_id="sync-0", summary="原本的建議")) is True
        assert repository.begin_refresh(user_id, ADVICE_DAY, older, "sync-1") is True
        pending = repository.get_for_user_date(user_id, ADVICE_DAY)
        assert pending is not None
        assert pending.state == "pending"
        assert pending.data_freshness == "stale"
        assert pending.sections.week_summary == "原本的建議"
        assert repository.begin_refresh(user_id, ADVICE_DAY, newer, "sync-2") is True
        assert repository.mark_failed(user_id, ADVICE_DAY, newer, "generation_failed") is True
        assert repository.publish(user_id, ADVICE_DAY, older, _advice(user_id, "run-1", summary="遲到的舊結果")) is False
        assert repository.mark_failed(user_id, ADVICE_DAY, older, "sync_failed") is False
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyDailyAdviceRepository(uow.session).get_for_user_date(user_id, ADVICE_DAY)

    assert loaded is not None
    assert loaded.state == "generation_failed"
    assert loaded.data_freshness == "stale"
    assert loaded.sections.week_summary == "原本的建議"
    assert loaded.source_run_id == "run-0"
    assert loaded.source_sync_run_id == "sync-0"
    assert loaded.refresh_source_sync_run_id == "sync-2"
    assert loaded.generated_at == datetime(2026, 10, 12, 4, 5, tzinfo=timezone.utc)


def test_same_run_is_idempotent_and_older_snapshot_cannot_reopen_ready_content(sqlite_session_factory) -> None:
    user_id, _ = _users(sqlite_session_factory)
    current = _version(4, "run-b")
    older_same_time = _version(4, "run-a")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(user_id, ADVICE_DAY, current, "sync-b") is True
        assert repository.publish(user_id, ADVICE_DAY, current, _advice(user_id, "run-b", sync_id="sync-b")) is True
        assert repository.begin_refresh(user_id, ADVICE_DAY, current, "sync-b") is True
        assert repository.publish(user_id, ADVICE_DAY, current, _advice(user_id, "run-b", sync_id="sync-b", summary="changed")) is True
        assert repository.begin_refresh(user_id, ADVICE_DAY, older_same_time, "sync-a") is False
        assert repository.publish(user_id, ADVICE_DAY, older_same_time, _advice(user_id, "run-a")) is False
        loaded = repository.get_for_user_date(user_id, ADVICE_DAY)
        assert loaded is not None
        assert loaded.state == "ready"
        assert loaded.sections.week_summary == "本週依照計畫完成。"


def test_publish_rejects_wrong_owner_or_unreserved_version(sqlite_session_factory) -> None:
    first_user, second_user = _users(sqlite_session_factory)
    reserved = _version(4, "run-1")
    unreserved = _version(5, "run-2")

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyDailyAdviceRepository(uow.session)
        assert repository.begin_refresh(first_user, ADVICE_DAY, reserved, None) is True
        assert repository.publish(second_user, ADVICE_DAY, reserved, _advice(second_user, "run-1")) is False
        assert repository.publish(first_user, ADVICE_DAY, unreserved, _advice(first_user, "run-2")) is False
        loaded = repository.get_for_user_date(first_user, ADVICE_DAY)
        assert loaded is not None
        assert loaded.state == "pending"
        assert loaded.sections is None
