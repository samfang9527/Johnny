from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from inspect import signature

import pytest

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
from src.application.training_targets import build_pace_profile
from src.application.training_plan_generation import build_plan_skeleton
from src.application.training_analytics import BuildTodayContextHandler
from src.application.interfaces.training_plan_store import TrainingPlanStore
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.recommendation_approval import Recommendation
from src.domain.training_plan import DomainValidationError, TrainingPlan, Workout


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

    def get_race_goal_for_user(self, user_id: str, race_goal_id: str | None) -> RaceGoal | None:
        return next(
            (goal for goal in self.goals if goal.user_id == user_id and goal.id == race_goal_id),
            None,
        )


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
        self.active_plans: list[TrainingPlan] = [plan] if plan is not None and plan.status == "active" else []

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        return self.plan

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        if self.plan is None or self.plan.user_id != user_id or self.plan.id != plan_id:
            return None
        return self.plan

    def create_active_plan(
        self,
        user_id: str,
        plan: TrainingPlan,
        replace_all_active: bool = False,
    ) -> TrainingPlan:
        if replace_all_active:
            self.active_plans = [
                replace(existing, status="superseded") if existing.status == "active" else existing
                for existing in self.active_plans
            ]
        saved = TrainingPlan.create(
            id=f"plan-{len(self.active_plans) + 1}",
            user_id=user_id,
            race_id=plan.race_id,
            name=plan.name,
            status="active",
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
            workouts=plan.workouts,
            metadata=plan.metadata,
        )
        self.active_plans.append(saved)
        self.plan = saved
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


def _profile(user_id: str = "user-1", training_preferences: dict | None = None) -> AthleteProfile:
    return AthleteProfile.create(
        user_id=user_id,
        timezone="Asia/Taipei",
        experience_level="intermediate",
        current_weekly_mileage_km=42,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=5,
        training_preferences=training_preferences,
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


def _eight_week_skeleton():
    return build_plan_skeleton(
        starts_on=date(2027, 1, 4),
        ends_on=date(2027, 2, 28),
        plan_type="maintenance",
        race_date=None,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=3,
        max_hard_sessions_per_week=0,
    )


def _skeleton_payload(skeleton) -> dict:
    return {
        "starts_on": skeleton.starts_on.isoformat(),
        "ends_on": skeleton.ends_on.isoformat(),
        "phase_segments": [dict(segment) for segment in skeleton.phase_segments],
        "workouts": [
            {
                "scheduled_for": workout.scheduled_for.isoformat(),
                "workout_type": workout.workout_type,
                "phase": workout.phase,
                "planned_duration_minutes": workout.planned_duration_minutes,
                "planned_distance_meters": workout.planned_distance_meters,
            }
            for workout in skeleton.workouts
        ],
    }


def _model_workout_payload(workout, *, purpose: str, scheduled_for: date | None = None) -> dict:
    return {
        "id": f"model-{workout.scheduled_for.isoformat()}",
        "scheduled_for": (scheduled_for or workout.scheduled_for).isoformat(),
        "workout_type": workout.workout_type,
        "purpose": purpose,
        "planned_duration_minutes": workout.planned_duration_minutes,
        "planned_distance_meters": workout.planned_distance_meters,
        "phase": workout.phase,
    }


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


def test_athlete_context_tool_lists_all_future_races_and_scopes_an_explicit_race_to_its_owner() -> None:
    past_race = replace(_goal(), id="past-race", race_date=date(2027, 1, 1))
    future_secondary = replace(_goal(), id="future-secondary", race_date=date(2027, 2, 7), priority="secondary")
    future_primary = replace(_goal(), id="future-primary", race_date=date(2027, 3, 7))
    tool = AthleteContextTool(
        profiles=FakeAthleteProfileStore(_profile()),
        race_goals=FakeRaceGoalStore((past_race, future_secondary, future_primary, _goal(user_id="user-2"))),
    )

    future_payload = tool.run(user_id="user-1", arguments={"race_date_from": "2027-01-28"})
    explicit_payload = tool.run(user_id="user-1", arguments={"race_id": "future-secondary"})

    assert [goal["id"] for goal in future_payload["race_goals"]] == ["future-secondary", "future-primary"]
    assert [goal["id"] for goal in explicit_payload["race_goals"]] == ["future-secondary"]


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
            "metadata": {
                "phase_segments": [
                    {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-28"}
                ]
            },
            "workouts": [
                {
                    "scheduled_for": "2027-01-03",
                    "workout_type": "easy_run",
                    "purpose": "Aerobic base",
                    "planned_duration_minutes": 40,
                    "phase": "base",
                }
            ],
        },
    )

    assert payload["training_plan"]["id"] == "plan-1"
    assert payload["training_plan"]["status"] == "active"
    assert plan_store.active_plans[0].status == "active"


def test_create_training_plan_tool_repairs_eight_week_output_and_preserves_valid_weeks() -> None:
    skeleton = _eight_week_skeleton()
    skeleton_payload = _skeleton_payload(skeleton)
    valid_weeks = [workout for workout in skeleton.workouts if workout.scheduled_for < date(2027, 1, 18)]
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=FakeTrainingPlanStore(None))

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Model supplied first two weeks",
            "starts_on": skeleton.starts_on.isoformat(),
            "ends_on": skeleton.ends_on.isoformat(),
            "metadata": {"phase_segments": skeleton.phase_segments},
            "workouts": [
                _model_workout_payload(workout, purpose="Model coaching detail") for workout in valid_weeks
            ],
            "trusted_context": {"plan_skeleton": skeleton_payload},
        },
    )

    saved = payload["training_plan"]
    repair = payload["completion_repair"]
    assert len(saved["workouts"]) == len(skeleton.workouts)
    assert [workout["purpose"] for workout in saved["workouts"][: len(valid_weeks)]] == [
        "Model coaching detail"
    ] * len(valid_weeks)
    assert repair["repaired_week_indexes"] == [2, 3, 4, 5, 6, 7]
    assert repair == saved["metadata"]["internal"]["completion_repair"]


def test_create_training_plan_tool_persists_skeleton_load_and_planned_state_over_model_values() -> None:
    skeleton = _eight_week_skeleton()
    model_workouts = [_model_workout_payload(workout, purpose="Model coaching detail") for workout in skeleton.workouts]
    model_workouts[0].update(
        {
            "id": "model-workout-id",
            "status": "completed",
            "planned_duration_minutes": (model_workouts[0]["planned_duration_minutes"] or 0) + 30,
            "planned_distance_meters": (model_workouts[0]["planned_distance_meters"] or 0) + 1_000,
        }
    )
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=FakeTrainingPlanStore(None))

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Inflated model plan",
            "starts_on": skeleton.starts_on.isoformat(),
            "ends_on": skeleton.ends_on.isoformat(),
            "metadata": {"phase_segments": skeleton.phase_segments},
            "workouts": model_workouts,
            "trusted_context": {"plan_skeleton": _skeleton_payload(skeleton)},
        },
    )

    saved_first_workout = payload["training_plan"]["workouts"][0]
    skeleton_first_workout = _skeleton_payload(skeleton)["workouts"][0]
    assert saved_first_workout["id"] != "model-workout-id"
    assert saved_first_workout["status"] == "planned"
    assert saved_first_workout["planned_duration_minutes"] == skeleton_first_workout["planned_duration_minutes"]
    assert saved_first_workout["planned_distance_meters"] == skeleton_first_workout["planned_distance_meters"]
    assert payload["completion_repair"]["repaired_week_indexes"] == [0]


@pytest.mark.parametrize(
    "skeleton_workouts",
    (
        lambda payload: [],
        lambda payload: [
            workout
            for workout in payload["workouts"]
            if not date(2027, 1, 18) <= date.fromisoformat(workout["scheduled_for"]) <= date(2027, 1, 24)
        ],
    ),
    ids=("empty-multi-week-skeleton", "week-without-expected-workouts"),
)
def test_create_training_plan_tool_rejects_incomplete_trusted_skeleton_before_persistence(skeleton_workouts) -> None:
    skeleton = _skeleton_payload(_eight_week_skeleton())
    skeleton["workouts"] = skeleton_workouts(skeleton)
    plan_store = FakeTrainingPlanStore(None)
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=plan_store)

    with pytest.raises(ValueError, match="trusted plan skeleton must include workouts for every week"):
        tool.run(
            user_id="user-1",
            arguments={
                "name": "Malformed trusted skeleton",
                "starts_on": skeleton["starts_on"],
                "ends_on": skeleton["ends_on"],
                "metadata": {"phase_segments": skeleton["phase_segments"]},
                "workouts": [],
                "trusted_context": {"plan_skeleton": skeleton},
            },
        )

    assert plan_store.active_plans == []


def test_training_plan_store_exposes_replace_all_active_contract() -> None:
    parameter = signature(TrainingPlanStore.create_active_plan).parameters["replace_all_active"]

    assert parameter.default is False
    assert parameter.kind.name == "POSITIONAL_OR_KEYWORD"


def test_create_training_plan_tool_repairs_a_shifted_but_self_consistent_model_plan() -> None:
    skeleton = _eight_week_skeleton()
    skeleton_payload = _skeleton_payload(skeleton)
    shifted_starts_on = skeleton.starts_on + timedelta(days=1)
    shifted_ends_on = skeleton.ends_on + timedelta(days=1)
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=FakeTrainingPlanStore(None))

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Shifted model plan",
            "starts_on": shifted_starts_on.isoformat(),
            "ends_on": shifted_ends_on.isoformat(),
            "metadata": {
                "phase_segments": [
                    {
                        "phase": "maintenance",
                        "starts_on": shifted_starts_on.isoformat(),
                        "ends_on": shifted_ends_on.isoformat(),
                    }
                ]
            },
            "workouts": [
                _model_workout_payload(
                    workout,
                    purpose="Shifted model detail",
                    scheduled_for=workout.scheduled_for + timedelta(days=1),
                )
                for workout in skeleton.workouts
            ],
            "trusted_context": {"plan_skeleton": skeleton_payload},
        },
    )

    saved = payload["training_plan"]
    assert (saved["starts_on"], saved["ends_on"]) == (
        skeleton.starts_on.isoformat(),
        skeleton.ends_on.isoformat(),
    )
    assert [workout["scheduled_for"] for workout in saved["workouts"]] == [
        workout.scheduled_for.isoformat() for workout in skeleton.workouts
    ]
    assert payload["completion_repair"]["repaired_week_indexes"] == list(range(8))


@pytest.mark.parametrize(
    "replacement_context",
    (
        {"manual_regeneration": True, "plan_type": "race"},
        {"plan_type": "maintenance"},
        {"plan_type": "race", "replace_active_projection": True},
    ),
    ids=("manual-regeneration", "maintenance-replacement", "scheduled-replacement"),
)
def test_create_training_plan_tool_supersedes_all_active_projections_when_replacing(
    replacement_context: dict,
) -> None:
    existing = _plan()
    plan_store = FakeTrainingPlanStore(existing)
    skeleton = _eight_week_skeleton()
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=plan_store)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Manual maintenance replacement",
            "starts_on": skeleton.starts_on.isoformat(),
            "ends_on": skeleton.ends_on.isoformat(),
            "metadata": {"phase_segments": skeleton.phase_segments},
            "workouts": [
                _model_workout_payload(workout, purpose="Manual plan detail") for workout in skeleton.workouts
            ],
            "trusted_context": {
                "plan_skeleton": _skeleton_payload(skeleton),
                **replacement_context,
            },
        },
    )

    assert payload["training_plan"]["status"] == "active"
    assert [plan.status for plan in plan_store.active_plans] == ["superseded", "active"]


@pytest.mark.parametrize(
    ("arguments", "error_message"),
    [
        (
            {
                "name": "Missing Phase Segments",
                "starts_on": "2027-01-01",
                "ends_on": "2027-01-28",
                "workouts": [],
            },
            "phase segments are required",
        ),
        (
            {
                "name": "Mismatched Workout Phase",
                "starts_on": "2027-01-01",
                "ends_on": "2027-01-28",
                "metadata": {
                    "phase_segments": [
                        {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-14"},
                        {"phase": "build", "starts_on": "2027-01-15", "ends_on": "2027-01-28"},
                    ]
                },
                "workouts": [
                    {
                        "scheduled_for": "2027-01-20",
                        "workout_type": "easy_run",
                        "purpose": "Aerobic base",
                        "planned_duration_minutes": 40,
                        "phase": "base",
                    }
                ],
            },
            "workout phase does not match phase segment",
        ),
        (
            {
                "name": "Missing Workout Phase",
                "starts_on": "2027-01-01",
                "ends_on": "2027-01-28",
                "metadata": {
                    "phase_segments": [
                        {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-28"}
                    ]
                },
                "workouts": [
                    {
                        "scheduled_for": "2027-01-03",
                        "workout_type": "easy_run",
                        "purpose": "Aerobic base",
                        "planned_duration_minutes": 40,
                    }
                ],
            },
            "workout phase is required",
        ),
    ],
)
def test_create_training_plan_tool_does_not_persist_invalid_generated_active_plans(
    arguments: dict, error_message: str
) -> None:
    plan_store = FakeTrainingPlanStore(None)
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=plan_store)

    with pytest.raises(DomainValidationError, match=error_message):
        tool.run(user_id="user-1", arguments=arguments)

    assert plan_store.active_plans == []


def test_create_training_plan_tool_enriches_workout_steps_from_trusted_pace_profile() -> None:
    plan_store = FakeTrainingPlanStore(None)
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=plan_store)
    pace_profile = build_pace_profile(profile=_profile(training_preferences={"threshold_pace_seconds_per_km": 300}))

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Generated Detailed Plan",
            "race_id": "race-1",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-28",
            "metadata": {
                "phase_segments": [
                    {"phase": "build", "starts_on": "2027-01-01", "ends_on": "2027-01-28"}
                ]
            },
            "trusted_context": {"pace_profile": pace_profile.to_payload()},
            "workouts": [
                {
                    "scheduled_for": "2027-01-05",
                    "workout_type": "interval",
                    "purpose": "Improve 5K-specific aerobic power",
                    "planned_duration_minutes": 55,
                    "phase": "build",
                    "steps": [
                        {"type": "warmup", "duration_seconds": 900, "target": {"kind": "rpe", "rpe": 3}},
                        {
                            "type": "repeat",
                            "repeat_count": 4,
                            "steps": [
                                {
                                    "type": "work",
                                    "distance_meters": 800,
                                    "target": {"kind": "pace", "zone": "interval", "rpe": 8},
                                },
                                {
                                    "type": "recovery",
                                    "distance_meters": 400,
                                    "target": {"kind": "pace", "zone": "easy", "rpe": 3},
                                },
                            ],
                        },
                        {"type": "cooldown", "duration_seconds": 600, "target": {"kind": "rpe", "rpe": 2}},
                    ],
                }
            ],
        },
    )

    work_target = payload["training_plan"]["workouts"][0]["steps"][1]["steps"][0]["target"]
    assert work_target["pace_range_seconds_per_km"] == [276, 291]
    assert work_target["confidence"] == "high"


def test_create_training_plan_tool_preserves_trusted_continuity_metadata() -> None:
    plan_store = FakeTrainingPlanStore(None)
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=plan_store)

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Generated Continuation",
            "race_id": "race-1",
            "starts_on": "2027-02-01",
            "ends_on": "2027-03-01",
            "metadata": {
                "phase_segments": [
                    {"phase": "build", "starts_on": "2027-02-01", "ends_on": "2027-03-01"}
                ],
                "weekly_rationales": [
                    {
                        "week_index": 1,
                        "phase": "build",
                        "focus": "Build threshold durability.",
                        "load_progression": "Increase controlled work.",
                        "key_workouts": ["Tempo"],
                    }
                ],
            },
            "trusted_context": {
                "plan_series_id": "series-1",
                "previous_plan_id": "plan-previous",
                "version": 3,
                "continuity_summary": "Continue the existing threshold-first build.",
            },
            "workouts": [],
        },
    )

    assert payload["training_plan"]["metadata"]["plan_series_id"] == "series-1"
    assert payload["training_plan"]["metadata"]["previous_plan_id"] == "plan-previous"
    assert payload["training_plan"]["metadata"]["version"] == 3
    assert payload["training_plan"]["metadata"]["generation_mode"] == "generated"
    assert payload["training_plan"]["metadata"]["weekly_rationales"] == [
        {
            "week_index": 1,
            "phase": "build",
            "focus": "Build threshold durability.",
            "load_progression": "Increase controlled work.",
            "key_workouts": ["Tempo"],
        }
    ]


def test_create_training_plan_tool_keeps_only_supported_model_metadata_and_overwrites_system_metadata() -> None:
    skeleton = _eight_week_skeleton()
    tool = agent_tools_module.CreateTrainingPlanTool(training_plans=FakeTrainingPlanStore(None))

    payload = tool.run(
        user_id="user-1",
        arguments={
            "name": "Metadata ownership",
            "starts_on": skeleton.starts_on.isoformat(),
            "ends_on": skeleton.ends_on.isoformat(),
            "metadata": {
                "weekly_rationales": [
                    {
                        "week_index": 1,
                        "phase": "maintenance",
                        "focus": "Maintain aerobic consistency.",
                        "load_progression": "Hold steady volume.",
                        "key_workouts": ["Long run"],
                    }
                ],
                "plan_series_id": "model-series",
                "previous_plan_id": "model-previous",
                "version": 999,
                "continuity_summary": "Model-owned continuity.",
                "generation_mode": "model-mode",
                "phase_segments": [],
                "internal": {"completion_repair": {"repaired_week_indexes": [99]}},
                "unsupported": "discard me",
            },
            "workouts": [_model_workout_payload(workout, purpose="Model coaching detail") for workout in skeleton.workouts],
            "trusted_context": {
                "plan_skeleton": _skeleton_payload(skeleton),
                "plan_series_id": "trusted-series",
                "previous_plan_id": None,
                "version": 3,
                "continuity_summary": "Application-owned continuity.",
            },
        },
    )

    assert payload["training_plan"]["metadata"] == {
        "weekly_rationales": [
            {
                "week_index": 1,
                "phase": "maintenance",
                "focus": "Maintain aerobic consistency.",
                "load_progression": "Hold steady volume.",
                "key_workouts": ["Long run"],
            }
        ],
        "phase_segments": _skeleton_payload(skeleton)["phase_segments"],
        "plan_series_id": "trusted-series",
        "previous_plan_id": None,
        "version": 3,
        "continuity_summary": "Application-owned continuity.",
        "generation_mode": "generated",
    }


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
