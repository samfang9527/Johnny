from datetime import date, datetime, timezone

from src.application import agent_tools as agent_tools_module
from src.application.agent_tools import (
    AgentToolRegistry,
    AthleteContextTool,
    CreateRecommendationTool,
    MemoryCandidateTool,
    RecentActivitiesTool,
    RecoveryStateTool,
    TodayWorkoutTool,
    TrainingMetricsTool,
    TrainingPlanTool,
    WorkoutAdjustmentProposalTool,
)
from src.application.training_analytics import BuildTodayContextHandler
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.recommendation_approval import Recommendation
from src.domain.training_plan import TrainingPlan, Workout


ANCHOR = date(2027, 1, 28)


class FakeAthleteProfileStore:
    def __init__(self, profile: AthleteProfile | None) -> None:
        self.profile = profile

    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None:
        if self.profile is None or self.profile.user_id != user_id:
            return None
        return self.profile


class FakeRaceGoalStore:
    def __init__(self, goals: tuple[RaceGoal, ...]) -> None:
        self.goals = goals

    def list_race_goals_for_user(
        self,
        user_id: str,
        *,
        race_date_from: date | None = None,
        race_date_to: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RaceGoal]:
        goals = [
            goal
            for goal in self.goals
            if goal.user_id == user_id
            and (race_date_from is None or goal.race_date >= race_date_from)
            and (race_date_to is None or goal.race_date <= race_date_to)
        ]
        return goals[offset : offset + limit if limit is not None else None]


class LeakyActivityStore:
    def __init__(
        self,
        *,
        activities: tuple[CompletedActivity, ...],
        health_metrics: tuple[DailyHealthMetrics, ...],
    ) -> None:
        self.activities = activities
        self.health_metrics = health_metrics

    def list_activities_for_user_between(
        self,
        user_id: str,
        started_on_or_after: date,
        started_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CompletedActivity]:
        return list(self.activities)[offset : offset + limit if limit is not None else None]

    def list_daily_health_metrics_for_user_between(
        self,
        user_id: str,
        measured_on_or_after: date,
        measured_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DailyHealthMetrics]:
        return list(self.health_metrics)[offset : offset + limit if limit is not None else None]


class FakeTrainingPlanStore:
    def __init__(self, plan: TrainingPlan | None) -> None:
        self.plan = plan
        self.active_plans: list[TrainingPlan] = []

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        return self.plan

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        if self.plan is None or self.plan.user_id != user_id or self.plan.id != plan_id:
            return None
        return self.plan

    def create_active_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        saved = TrainingPlan.create(
            id=f"plan-{len(self.active_plans) + 1}",
            user_id=user_id,
            race_id=plan.race_id,
            name=plan.name,
            status="active",
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
            workouts=plan.workouts,
        )
        self.active_plans.append(saved)
        return saved


class FakeRecommendationStore:
    def __init__(self) -> None:
        self.recommendations: list[Recommendation] = []
        self.next_id = 1

    def create_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation:
        saved = Recommendation.create(
            id=f"recommendation-{self.next_id}",
            user_id=user_id,
            recommendation_type=recommendation.recommendation_type,
            priority=recommendation.priority,
            title=recommendation.title,
            rationale=recommendation.rationale,
            evidence=recommendation.evidence,
            proposed_action=recommendation.proposed_action,
            training_plan_id=recommendation.training_plan_id,
            workout_id=recommendation.workout_id,
            agent_run_id=recommendation.agent_run_id,
        )
        self.next_id += 1
        self.recommendations.append(saved)
        return saved


class FakeMemoryCandidateStore:
    def __init__(self) -> None:
        self.candidates: list[dict] = []

    def store_memory_candidate(self, user_id: str, candidate: dict) -> dict:
        saved = {"id": f"memory-candidate-{len(self.candidates) + 1}", "user_id": user_id, **candidate}
        self.candidates.append(saved)
        return saved


def _profile(user_id: str = "user-1") -> AthleteProfile:
    return AthleteProfile.create(
        user_id=user_id,
        timezone="Asia/Taipei",
        experience_level="intermediate",
        current_weekly_mileage_km=42,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=5,
        injury_status="recent",
        injury_areas=("shin",),
        injury_notes="Previous shin soreness.",
    )


def _goal(user_id: str = "user-1") -> RaceGoal:
    return RaceGoal.create(
        id="race-1",
        user_id=user_id,
        name="Taipei Half",
        race_date=date(2027, 3, 7),
        distance_meters=21_097,
        priority="primary",
    )


def _activity(user_id: str = "user-1", activity_date: date = ANCHOR, distance_meters: float = 5_000) -> CompletedActivity:
    return CompletedActivity.create(
        id=f"activity-{user_id}-{activity_date.isoformat()}",
        user_id=user_id,
        source="manual",
        started_at=datetime(activity_date.year, activity_date.month, activity_date.day, 7, 30, tzinfo=timezone.utc),
        sport_type="run",
        distance_meters=distance_meters,
        duration_seconds=1_500,
    )


def _health(user_id: str = "user-1", metric_date: date = ANCHOR) -> DailyHealthMetrics:
    return DailyHealthMetrics.create(
        user_id=user_id,
        metric_date=metric_date,
        sleep_duration_minutes=360,
        hrv_ms=40,
        hrv_baseline_ms=55,
        resting_heart_rate=55,
        stress_score=80,
    )


def _plan(user_id: str = "user-1") -> TrainingPlan:
    return TrainingPlan.create(
        id="plan-1",
        user_id=user_id,
        name="Build Plan",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 2, 28),
        workouts=(
            Workout.create(
                id="workout-today",
                scheduled_for=ANCHOR,
                workout_type="easy_run",
                purpose="Aerobic base",
                planned_duration_minutes=45,
            ),
        ),
    )


def _today_context_handler(activity_store: LeakyActivityStore, plan_store: FakeTrainingPlanStore) -> BuildTodayContextHandler:
    return BuildTodayContextHandler(training_data=activity_store, training_plans=plan_store)


def test_athlete_context_tool_returns_profile_and_race_goals_without_domain_objects() -> None:
    tool = AthleteContextTool(
        profiles=FakeAthleteProfileStore(_profile()),
        race_goals=FakeRaceGoalStore((_goal(), _goal(user_id="user-2"))),
    )

    payload = tool.run(user_id="user-1", arguments={"limit": 5})

    assert payload["profile"]["timezone"] == "Asia/Taipei"
    assert payload["profile"]["injury_notes"] == "Previous shin soreness."
    assert payload["profile"]["current_weekly_mileage_km"] == 42
    assert payload["profile"]["hard_constraints"] == {
        "max_runs_per_week": 5,
        "unit_preference": "metric",
        "injury_status": "recent",
        "injury_areas": ["shin"],
        "injury_notes": "Previous shin soreness.",
        "current_weekly_mileage_km": 42,
    }
    assert payload["profile"]["soft_preferences"] == {
        "preferred_training_days": ["tuesday", "thursday", "sunday"],
        "preferred_long_run_day": "sunday",
        "experience_level": "intermediate",
    }
    assert [goal["id"] for goal in payload["race_goals"]] == ["race-1"]
    assert all(not isinstance(value, AthleteProfile) for value in payload.values())


def test_training_tools_filter_leaky_provider_data_by_user_and_use_deterministic_analytics() -> None:
    activity_store = LeakyActivityStore(
        activities=(
            _activity(user_id="user-1", activity_date=ANCHOR, distance_meters=5_000),
            _activity(user_id="user-2", activity_date=ANCHOR, distance_meters=50_000),
        ),
        health_metrics=(
            _health(user_id="user-1"),
            _health(user_id="user-2"),
        ),
    )
    plan_store = FakeTrainingPlanStore(_plan())
    today_context = _today_context_handler(activity_store, plan_store)

    recent_payload = RecentActivitiesTool(activities=activity_store).run(
        user_id="user-1",
        arguments={"start_date": "2027-01-22", "end_date": "2027-01-28"},
    )
    recovery_payload = RecoveryStateTool(today_context=today_context).run(
        user_id="user-1",
        arguments={"anchor_date": "2027-01-28"},
    )
    metrics_payload = TrainingMetricsTool(today_context=today_context).run(
        user_id="user-1",
        arguments={"anchor_date": "2027-01-28"},
    )
    today_workout_payload = TodayWorkoutTool(today_context=today_context).run(
        user_id="user-1",
        arguments={"anchor_date": "2027-01-28"},
    )

    assert [activity["user_id"] for activity in recent_payload["activities"]] == ["user-1"]
    assert recovery_payload["recovery"]["readiness_label"] == "rest"
    assert metrics_payload["training_load"]["weekly_distance_meters"] == 5_000
    assert today_workout_payload["scheduled_workouts"][0]["id"] == "workout-today"


def test_training_plan_tool_and_registry_return_expected_tools() -> None:
    registry = AgentToolRegistry(
        (
            TrainingPlanTool(training_plans=FakeTrainingPlanStore(_plan())),
            AthleteContextTool(profiles=FakeAthleteProfileStore(_profile()), race_goals=FakeRaceGoalStore((_goal(),))),
        )
    )

    plan_payload = registry.get("getTrainingPlan").run(user_id="user-1", arguments={"training_plan_id": "plan-1"})

    assert registry.names() == ("getAthleteContext", "getTrainingPlan")
    assert plan_payload["training_plan"]["id"] == "plan-1"
    assert plan_payload["training_plan"]["workouts"][0]["id"] == "workout-today"


def test_recommendation_write_tool_creates_pending_recommendation() -> None:
    recommendations = FakeRecommendationStore()
    tool = CreateRecommendationTool(recommendations=recommendations)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Rest today",
            "rationale": "Recovery context indicates rest.",
            "evidence": [{"source": "agent", "metric": "readiness_label", "value": "rest"}],
            "action": {"type": "no_plan_change", "reason": "No safe workout change."},
            "agent_run_id": "run-1",
        },
    )

    assert payload["recommendation"]["id"] == "recommendation-1"
    assert payload["recommendation"]["status"] == "pending"
    assert recommendations.recommendations[0].agent_run_id == "run-1"


def test_workout_adjustment_tool_creates_proposal_without_mutating_plan() -> None:
    recommendations = FakeRecommendationStore()
    plan = _plan()
    before = plan.workouts[0].to_payload()
    tool = WorkoutAdjustmentProposalTool(recommendations=recommendations)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "title": "Reduce today's run",
            "rationale": "Recovery context indicates rest.",
            "priority": "high",
            "training_plan_id": "plan-1",
            "workout_id": "workout-today",
            "before_payload": before,
            "after_payload": {**before, "planned_duration_minutes": 20},
            "reason": "Recovery is low.",
            "evidence": [{"source": "agent", "metric": "readiness_label", "value": "rest"}],
            "agent_run_id": "run-1",
        },
    )

    assert payload["recommendation"]["status"] == "pending"
    assert payload["recommendation"]["proposed_action"]["type"] == "adjust_workout"


def test_create_training_plan_tool_stores_active_plan_immediately() -> None:
    plan_store = FakeTrainingPlanStore(None)
    tool_class = getattr(agent_tools_module, "CreateTrainingPlanTool", None)

    assert tool_class is not None

    tool = tool_class(training_plans=plan_store)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Generated Four Week Plan",
            "race_id": "race-1",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-28",
            "workouts": [
                {
                    "scheduled_for": "2027-01-03",
                    "workout_type": "easy_run",
                    "purpose": "Aerobic base",
                    "planned_duration_minutes": 40,
                }
            ],
        },
    )

    assert payload["training_plan"]["id"] == "plan-1"
    assert payload["training_plan"]["status"] == "active"
    assert plan_store.active_plans[0].status == "active"


def test_memory_candidate_tool_stores_candidate_without_mutating_profile() -> None:
    profile = _profile()
    memory_candidates = FakeMemoryCandidateStore()
    tool = MemoryCandidateTool(memory_candidates=memory_candidates)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "memory_type": "preference",
            "summary": "Prefers long runs on Sunday.",
            "evidence": {"source": "conversation"},
        },
    )

    assert payload["memory_candidate"]["id"] == "memory-candidate-1"
    assert payload["memory_candidate"]["status"] == "pending"
    assert profile.preferences.preferred_long_run_day == "sunday"
