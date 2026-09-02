from __future__ import annotations

from datetime import date
from typing import Iterable

from src.application.training_analytics import BuildTodayContextHandler
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_plan import TrainingPlan, Workout


class AgentToolRegistry:
    def __init__(self, tools: Iterable) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name: str):
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Agent tool not registered: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


class AthleteContextTool:
    name = "getAthleteContext"

    def __init__(self, *, profiles, race_goals) -> None:
        self._profiles = profiles
        self._race_goals = race_goals

    def run(self, *, user_id: str, arguments: dict) -> dict:
        limit = arguments.get("limit", 5)
        profile = self._profiles.get_profile_for_user(user_id)
        goals = self._race_goals.list_race_goals_for_user(user_id, limit=limit, offset=arguments.get("offset", 0))
        return {
            "profile": _profile_payload(profile),
            "race_goals": [_race_goal_payload(goal) for goal in goals if goal.user_id == user_id],
        }


class TrainingPlanTool:
    name = "getTrainingPlan"

    def __init__(self, *, training_plans) -> None:
        self._training_plans = training_plans

    def run(self, *, user_id: str, arguments: dict) -> dict:
        plan_id = arguments.get("training_plan_id")
        plan = self._training_plans.get_plan_for_user(user_id, plan_id)
        return {"training_plan": _plan_payload(plan)}


class TodayWorkoutTool:
    name = "getTodayWorkout"

    def __init__(self, *, today_context: BuildTodayContextHandler) -> None:
        self._today_context = today_context

    def run(self, *, user_id: str, arguments: dict) -> dict:
        context = self._today_context.handle(user_id=user_id, anchor_date=_date_arg(arguments, "anchor_date"))
        return {
            "anchor_date": context.anchor_date.isoformat(),
            "scheduled_workouts": list(context.scheduled_workouts),
            "unavailable_signals": list(context.unavailable_signals),
        }


class RecentActivitiesTool:
    name = "getRecentActivities"

    def __init__(self, *, activities) -> None:
        self._activities = activities

    def run(self, *, user_id: str, arguments: dict) -> dict:
        start_date = _date_arg(arguments, "start_date")
        end_date = _date_arg(arguments, "end_date")
        activities = self._activities.list_activities_for_user_between(
            user_id,
            start_date,
            end_date,
            limit=arguments.get("limit"),
            offset=arguments.get("offset", 0),
        )
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "activities": [_activity_payload(activity) for activity in activities if activity.user_id == user_id],
        }


class RecoveryStateTool:
    name = "getRecoveryState"

    def __init__(self, *, today_context: BuildTodayContextHandler) -> None:
        self._today_context = today_context

    def run(self, *, user_id: str, arguments: dict) -> dict:
        context = self._today_context.handle(user_id=user_id, anchor_date=_date_arg(arguments, "anchor_date"))
        return {
            "anchor_date": context.anchor_date.isoformat(),
            "recovery": context.recovery.to_payload(),
            "unavailable_signals": list(context.recovery.unavailable_signals),
        }


class TrainingMetricsTool:
    name = "getTrainingMetrics"

    def __init__(self, *, today_context: BuildTodayContextHandler) -> None:
        self._today_context = today_context

    def run(self, *, user_id: str, arguments: dict) -> dict:
        context = self._today_context.handle(user_id=user_id, anchor_date=_date_arg(arguments, "anchor_date"))
        return {
            "anchor_date": context.anchor_date.isoformat(),
            "training_load": context.training_load.to_payload(),
            "unavailable_signals": list(context.training_load.unavailable_signals),
        }


class CreateRecommendationTool:
    name = "createRecommendation"

    def __init__(self, *, recommendations) -> None:
        self._recommendations = recommendations

    def run(self, *, user_id: str, arguments: dict) -> dict:
        recommendation = Recommendation.create(
            user_id=user_id,
            recommendation_type=arguments.get("recommendation_type", "informational"),
            priority=arguments.get("priority", "medium"),
            title=arguments["title"],
            rationale=arguments["rationale"],
            evidence=_evidence_items(arguments.get("evidence", ())),
            proposed_action=_proposed_action(arguments.get("action", {"type": "no_plan_change", "reason": "No action."})),
            agent_run_id=arguments.get("agent_run_id"),
        )
        saved = self._recommendations.create_recommendation(user_id, recommendation)
        return {"recommendation": saved.to_payload(), "applied": False}


class WorkoutAdjustmentProposalTool:
    name = "proposeWorkoutAdjustment"

    def __init__(self, *, recommendations) -> None:
        self._recommendations = recommendations

    def run(self, *, user_id: str, arguments: dict) -> dict:
        action = ProposedAction.adjust_workout(
            training_plan_id=arguments["training_plan_id"],
            workout_id=arguments["workout_id"],
            before_payload=arguments["before_payload"],
            after_payload=arguments["after_payload"],
            reason=arguments["reason"],
        )
        recommendation = Recommendation.create(
            user_id=user_id,
            recommendation_type="workout_adjustment",
            priority=arguments.get("priority", "medium"),
            title=arguments["title"],
            rationale=arguments["rationale"],
            evidence=_evidence_items(arguments.get("evidence", ())),
            proposed_action=action,
            training_plan_id=arguments["training_plan_id"],
            workout_id=arguments["workout_id"],
            agent_run_id=arguments.get("agent_run_id"),
        )
        saved = self._recommendations.create_recommendation(user_id, recommendation)
        return {"recommendation": saved.to_payload(), "applied": False}


class CreateDraftTrainingPlanTool:
    name = "createDraftTrainingPlan"

    def __init__(self, *, training_plans) -> None:
        self._training_plans = training_plans

    def run(self, *, user_id: str, arguments: dict) -> dict:
        workouts = tuple(_workout_from_payload(payload) for payload in arguments.get("workouts", ()))
        plan = TrainingPlan.create(
            user_id=user_id,
            race_id=arguments.get("race_id"),
            name=arguments["name"],
            status="draft",
            starts_on=_date_arg(arguments, "starts_on"),
            ends_on=_date_arg(arguments, "ends_on"),
            workouts=workouts,
        )
        saved = self._training_plans.create_draft_plan(user_id, plan)
        return {"draft_training_plan": _plan_payload(saved), "applied": False}


class MemoryCandidateTool:
    name = "storeMemoryCandidate"

    def __init__(self, *, memory_candidates) -> None:
        self._memory_candidates = memory_candidates

    def run(self, *, user_id: str, arguments: dict) -> dict:
        candidate = {
            "memory_type": arguments["memory_type"],
            "summary": arguments["summary"],
            "evidence": dict(arguments.get("evidence", {})),
            "status": "pending",
        }
        saved = self._memory_candidates.store_memory_candidate(user_id, candidate)
        return {"memory_candidate": saved, "applied": False}


def _date_arg(arguments: dict, name: str) -> date:
    value = arguments.get(name)
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"{name} is required")


def _evidence_items(payloads) -> tuple[EvidenceItem, ...]:
    return tuple(EvidenceItem.from_payload(payload) for payload in payloads)


def _proposed_action(payload: dict) -> ProposedAction:
    action_type = payload.get("type")
    if action_type == "adjust_workout":
        return ProposedAction.adjust_workout(
            training_plan_id=payload["training_plan_id"],
            workout_id=payload["workout_id"],
            before_payload=payload["before_payload"],
            after_payload=payload["after_payload"],
            reason=payload["reason"],
        )
    if action_type == "no_plan_change":
        return ProposedAction.no_plan_change(reason=payload["reason"])
    return ProposedAction.from_payload(payload)


def _workout_from_payload(payload: dict) -> Workout:
    pace_range = payload.get("pace_range_seconds_per_km")
    return Workout.create(
        id=payload.get("id"),
        scheduled_for=_date_arg(payload, "scheduled_for"),
        workout_type=payload["workout_type"],
        purpose=payload["purpose"],
        planned_duration_minutes=payload.get("planned_duration_minutes"),
        planned_distance_meters=payload.get("planned_distance_meters"),
        pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
        heart_rate_zone=payload.get("heart_rate_zone"),
        status=payload.get("status", "planned"),
    )


def _profile_payload(profile) -> dict | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "timezone": profile.timezone,
        "experience_level": profile.experience_level,
        "current_weekly_mileage": profile.current_weekly_mileage,
        "preferred_training_days": list(profile.preferences.preferred_training_days),
        "preferred_long_run_day": profile.preferences.preferred_long_run_day,
        "max_runs_per_week": profile.preferences.max_runs_per_week,
        "unit_preference": profile.preferences.unit_preference,
        "training_preferences": dict(profile.preferences.training_preferences),
        "injury_notes": profile.preferences.injury_notes,
    }


def _race_goal_payload(goal) -> dict:
    return {
        "id": goal.id,
        "user_id": goal.user_id,
        "name": goal.name,
        "race_date": goal.race_date.isoformat(),
        "distance_meters": goal.distance_meters,
        "target_finish_seconds": goal.target_finish_seconds,
        "priority": goal.priority,
        "status": goal.status,
        "target_pace_seconds_per_km": goal.target_pace_seconds_per_km,
    }


def _plan_payload(plan) -> dict | None:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "race_id": plan.race_id,
        "name": plan.name,
        "status": plan.status,
        "starts_on": plan.starts_on.isoformat(),
        "ends_on": plan.ends_on.isoformat(),
        "workouts": [workout.to_payload() for workout in plan.workouts],
    }


def _activity_payload(activity) -> dict:
    return {
        "id": activity.id,
        "user_id": activity.user_id,
        "source": activity.source,
        "source_activity_id": activity.source_activity_id,
        "provider_connection_id": activity.provider_connection_id,
        "started_at": activity.started_at.isoformat(),
        "sport_type": activity.sport_type,
        "distance_meters": activity.distance_meters,
        "duration_seconds": activity.duration_seconds,
        "average_pace_seconds_per_km": activity.average_pace_seconds_per_km,
        "average_heart_rate": activity.average_heart_rate,
        "elevation_gain_meters": activity.elevation_gain_meters,
        "matched_workout_id": activity.matched_workout_id,
    }
