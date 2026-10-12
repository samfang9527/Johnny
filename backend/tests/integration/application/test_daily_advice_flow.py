"""Cross-path proof for one current advice and separate approval-backed proposals."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import scripts.agent_runtime as runtime
from scripts.agent_runtime import schedule_once, work_drain
from src.api.dependencies import CurrentUser, ensure_current_user, get_session
from src.api.routes.integrations import get_garmin_resource_adapter
from src.application.integrations import GarminResourceFetchResult
from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import (
    ActivityModel, AgentRunModel, AthleteProfileModel, Base, DailyAdviceModel,
    RecommendationModel, TrainingPlanModel, WorkoutModel,
)
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.main import create_app


class GarminFeed:
    def __init__(self, day: date) -> None:
        self.day = day
        self.include_today = False
        self.fail_activities = False
        self.calls: list[str] = []

    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        self.calls.append(resource_type)
        if resource_type == "activities":
            if self.fail_activities:
                raise RuntimeError("activity feed unavailable")
            sessions = [
                ("a-1", self.day - timedelta(days=2), 4200),
                ("a-2", self.day - timedelta(days=1), 2400),
            ]
            if self.include_today:
                sessions.append(("a-3", self.day, 1800))
            return GarminResourceFetchResult(items=[{
                "activityId": activity_id, "activityType": {"typeKey": "running"},
                "startTimeGMT": (
                    datetime.combine(activity_day, time(0), tzinfo=ZoneInfo("Asia/Taipei"))
                    .astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                ),
                "distance": 5000, "duration": duration,
            } for activity_id, activity_day, duration in sessions])
        return GarminResourceFetchResult()


def test_schedule_sync_advice_manual_replace_failure_and_independent_approval(tmp_path, monkeypatch) -> None:
    day = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    feed = GarminFeed(day)
    monkeypatch.setattr(runtime, "_build_garmin_sync_adapter", lambda session, integrations: feed)
    engine = create_engine(f"sqlite:///{tmp_path / 'daily-flow.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        session.add(AthleteProfileModel(id="profile-1", user_id="athlete", timezone="Asia/Taipei", metadata_json={}))
        session.add(TrainingPlanModel(
            id="plan-1", user_id="athlete", name="Base", status="active",
            starts_on=day - timedelta(days=3), ends_on=day + timedelta(days=18),
        ))
        for offset, workout_id in ((-2, "past-1"), (-1, "past-2"), (0, "today")):
            session.add(WorkoutModel(
                id=workout_id, training_plan_id="plan-1", scheduled_for=day + timedelta(days=offset),
                workout_type="easy_run", planned_duration_minutes=30, status="planned",
                details={"purpose": "有氧基礎"},
            ))
        connection = SqlAlchemyIntegrationRepository(session).create_connection(
            user_id="athlete", provider="garmin_connect", provider_account_id="garmin-athlete",
        )
        session.commit()

    def override_session():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_garmin_resource_adapter] = lambda: feed
    client = TestClient(app)
    headers = {"X-Johnny-User-Id": "athlete"}

    at_four = datetime.combine(day, time(4), tzinfo=ZoneInfo("Asia/Taipei")).astimezone(timezone.utc)
    with factory() as session:
        assert schedule_once(session, now=at_four) == 2
        assert schedule_once(session, now=at_four + timedelta(minutes=1)) == 0
        session.commit()
    with factory() as session:
        assert work_drain(session) >= 3
        session.commit()
    first = client.get(f"/api/v1/today?anchor_date={day}", headers=headers).json()["data"]["daily_advice"]
    assert first["state"] == "ready"
    assert first["data_freshness"] == "fresh"
    assert first["facts"]["status"] == "above"
    assert first["facts"]["actual_minutes"] == 110
    assert first["plan_week"] == {"starts_on": (day - timedelta(days=3)).isoformat(), "ends_on": (day + timedelta(days=3)).isoformat()}
    assert first["week_summary"] and first["today_execution"] and first["workout_guide"]
    assert feed.calls[0] == "activities"

    feed.include_today = True
    synced = client.post(f"/api/v1/integrations/connections/{connection.id}/sync", headers=headers)
    assert synced.status_code == 200
    manual_run_id = synced.json()["data"]["daily_advice_run"]["run_id"]
    with factory() as session:
        assert len(session.scalars(select(ActivityModel).where(ActivityModel.user_id == "athlete")).all()) == 3
        assert work_drain(session) == 1
        session.commit()
    second = client.get(f"/api/v1/today?anchor_date={day}", headers=headers).json()["data"]["daily_advice"]
    assert second["id"] == first["id"]
    assert second["source_run_id"] == manual_run_id
    assert second["facts"]["actual_minutes"] == 140
    assert second["facts"]["today_completed"] is True
    assert second["execution_mode"] == "completed"
    assert client.get(f"/api/v1/agent-runs/{manual_run_id}", headers=headers).json()["data"]["daily_advice_id"] == second["id"]

    feed.fail_activities = True
    forced = client.post("/api/v1/agent-runs/daily-recommendation", headers=headers, json={"anchor_date": day.isoformat(), "force": True})
    assert forced.status_code == 200
    with factory() as session:
        assert work_drain(session) == 1
        session.commit()
    failed = client.get(f"/api/v1/today?anchor_date={day}", headers=headers).json()["data"]["daily_advice"]
    assert failed["id"] == first["id"]
    assert failed["state"] == "sync_failed"
    assert failed["data_freshness"] == "stale"
    assert failed["generated_at"] == second["generated_at"]
    assert failed["week_summary"] == second["week_summary"]

    with factory() as session:
        workout = SqlAlchemyTrainingPlanRepository(session).get_plan_for_user("athlete", "plan-1").workouts[0]
        before = workout.to_payload()
        after = {**before, "planned_duration_minutes": 20}
    proposed = client.post("/api/v1/recommendations", headers=headers, json={
        "recommendation_type": "workout_adjustment", "priority": "medium", "title": "調整明日課表",
        "rationale": "保守調整", "evidence": [{"source": "training_analytics", "metric": "load", "value": "high"}],
        "proposed_action": {"type": "adjust_workout", "training_plan_id": "plan-1", "workout_id": workout.id,
                            "before_payload": before, "after_payload": after, "reason": "保守執行"},
    })
    assert proposed.status_code == 200
    assert proposed.json()["data"]["status"] == "pending"
    today = client.get(f"/api/v1/today?anchor_date={day}", headers=headers).json()["data"]
    assert today["daily_advice"]["id"] == first["id"]
    assert today["current_recommendation"]["id"] == proposed.json()["data"]["id"]
    with factory() as session:
        assert len(session.scalars(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "athlete")).all()) == 1
        assert len(session.scalars(select(RecommendationModel).where(RecommendationModel.user_id == "athlete")).all()) == 1
        assert session.get(WorkoutModel, workout.id).planned_duration_minutes == 30
        assert len(session.scalars(select(AgentRunModel).where(AgentRunModel.user_id == "athlete")).all()) >= 3


def test_older_input_version_cannot_publish_over_newer_advice(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date(2027, 1, 28)
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        store = SqlAlchemyDailyAdviceRepository(session)
        older = RefreshVersion(datetime(2027, 1, 28, 4, tzinfo=timezone.utc), "older")
        newer = RefreshVersion(datetime(2027, 1, 28, 5, tzinfo=timezone.utc), "newer")
        assert store.begin_refresh("athlete", day, older, None)
        assert store.begin_refresh("athlete", day, newer, None)
        facts = WeekExecution(day, day, "on_plan", 0, 0, 0, 0, 0, 0, None, 0, False)
        def advice(run_id: str) -> DailyAdvice:
            return DailyAdvice(
                user_id="athlete", advice_date=day, plan_version_id="plan", workout_id=None,
                week_start=day, week_end=day, execution_mode="rest", facts=facts,
                sections=AdviceSections(f"週回顧 {run_id}", "今天休息", WorkoutGuide("恢復", "輕鬆", "休息", "維持")),
                generated_at=datetime(2027, 1, 28, 5, tzinfo=timezone.utc),
                source_sync_run_id=None, source_run_id=run_id, state="ready", data_freshness="limited",
            )
        assert store.publish("athlete", day, newer, advice("newer"))
        assert not store.publish("athlete", day, older, advice("older"))
        assert store.get_for_user_date("athlete", day).sections.week_summary == "週回顧 newer"
