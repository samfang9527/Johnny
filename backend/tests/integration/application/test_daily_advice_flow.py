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
            } for activity_id, activity_day, duration in sessions], pagination_complete=True)
        return GarminResourceFetchResult()


def test_schedule_review_and_manual_advice_remain_visible_through_approval(tmp_path, monkeypatch) -> None:
    from uuid import uuid4

    day = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    feed = GarminFeed(day)
    monkeypatch.setattr(runtime, "_build_garmin_sync_adapter", lambda session, integrations: feed)
    engine = create_engine(f"sqlite:///{tmp_path / 'coaching-flow.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

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
    client = TestClient(app)
    headers = {"X-Johnny-User-Id": "athlete"}
    profile = client.put("/api/v1/athlete/profile", headers=headers, json={
        "timezone": "Asia/Taipei", "current_weekly_mileage_km": 20,
        "preferred_training_days": ["monday"], "preferred_long_run_day": "monday",
        "max_runs_per_week": 3,
    })
    assert profile.status_code == 200, profile.text
    workout = lambda scheduled, minutes: {
        "scheduled_for": scheduled.isoformat(), "workout_type": "easy_run",
        "purpose": "有氧基礎", "planned_duration_minutes": minutes,
        "steps": [{"type": "free_run", "duration_seconds": minutes * 60,
                   "target": {"kind": "rpe", "rpe": 3}}],
    }
    plan_response = client.post("/api/v1/training-plans", headers=headers, json={
        "name": "Base", "starts_on": (day - timedelta(days=3)).isoformat(),
        "ends_on": (day + timedelta(days=18)).isoformat(),
        "workouts": [workout(day - timedelta(days=2), 70),
                     workout(day - timedelta(days=1), 40), workout(day, 40)],
    })
    assert plan_response.status_code == 200, plan_response.text
    today_workout_id = plan_response.json()["data"]["workouts"][2]["id"]
    with factory() as session:
        SqlAlchemyIntegrationRepository(session).create_connection(
            user_id="athlete", provider="garmin_connect", provider_account_id="garmin-athlete")
        session.commit()

    at_four = datetime.combine(day, time(4), tzinfo=ZoneInfo("Asia/Taipei")).astimezone(timezone.utc)
    with factory() as session:
        assert schedule_once(session, now=at_four) >= 1
        session.commit()
    with factory() as session:
        assert work_drain(session) >= 2
        session.commit()
    first = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert first["daily_review"]["current"]["kind"] == "daily_review"
    assert first["daily_review"]["current"]["reviewed_date"] == (day - timedelta(days=1)).isoformat()
    assert first["workout_advices"] == []
    assert client.get(f"/api/v1/today?anchor_date={day}", headers=headers).json()["data"]["daily_advice"] is None

    requested = client.post("/api/v1/johnny/workout-advice", headers=headers, json={
        "client_request_id": str(uuid4()), "workout_id": today_workout_id,
        "constraints": {"available_minutes": 25},
    })
    assert requested.status_code == 202, requested.text
    with factory() as session:
        assert work_drain(session) >= 2
        session.commit()
    second = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert second["daily_review"]["revision_id"] == first["daily_review"]["revision_id"]
    assert second["workout_advices"][0]["current"]["mode"] == "propose_shorten_easy_run"
    assert len(second["actionable_proposals"]) == 1
    proposal_id = second["actionable_proposals"][0]["id"]
    before = client.get(f"/api/v1/training-plans/{plan_response.json()['data']['id']}", headers=headers).json()["data"]
    assert before["workouts"][2]["planned_duration_minutes"] == 40
    accepted = client.post(f"/api/v1/recommendations/{proposal_id}/accept", headers=headers)
    assert accepted.status_code == 200, accepted.text
    after = client.get(f"/api/v1/training-plans/{plan_response.json()['data']['id']}", headers=headers).json()["data"]
    assert after["workouts"][2]["planned_duration_minutes"] == 25
    third = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert third["daily_review"]["revision_id"] == first["daily_review"]["revision_id"]
    assert third["workout_advices"][0]["freshness"] == "stale"
    assert third["actionable_proposals"] == []


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
