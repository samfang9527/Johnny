from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from src.application.training_plan_generation import (
    PlanSkeleton,
    SkeletonWorkout,
    repair_generated_plan,
    validate_generated_plan,
)
from src.application.training_targets import PaceProfile, enrich_workout_steps
from src.application.training_analytics import BuildTodayContextHandler
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, validate_phase_segments


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
        profile = self._profiles.get_profile_for_user(user_id)
        race_id = arguments.get("race_id")
        if race_id is not None:
            goal = self._race_goals.get_race_goal_for_user(user_id, str(race_id))
            goals = [goal] if goal is not None else []
        else:
            race_date_from = _optional_date_arg(arguments, "race_date_from")
            limit = arguments.get("limit", None if race_date_from is not None else 5)
            goals = self._race_goals.list_race_goals_for_user(
                user_id,
                race_date_from=race_date_from,
                limit=limit,
                offset=arguments.get("offset", 0),
            )
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
        plan = (
            self._training_plans.get_plan_for_user(user_id, plan_id)
            if plan_id
            else self._training_plans.get_current_plan_for_user(user_id)
        )
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


class CreateTrainingPlanTool:
    name = "createTrainingPlan"

    def __init__(self, *, training_plans) -> None:
        self._training_plans = training_plans

    def run(self, *, user_id: str, arguments: dict) -> dict:
        trusted_context = arguments.get("trusted_context") if isinstance(arguments.get("trusted_context"), dict) else {}
        pace_profile = trusted_context.get("pace_profile")
        skeleton = _trusted_plan_skeleton(trusted_context)
        workouts = tuple(
            _workout_from_payload({**payload, "id": None, "_pace_profile": pace_profile})
            for payload in arguments.get("workouts", ())
        )
        plan = TrainingPlan.create(
            user_id=user_id,
            race_id=trusted_context.get("race_id", arguments.get("race_id")),
            name=arguments["name"],
            status="active",
            starts_on=_date_arg(arguments, "starts_on"),
            ends_on=_date_arg(arguments, "ends_on"),
            metadata=_plan_metadata(arguments=arguments, trusted_context=trusted_context),
            workouts=workouts,
        )
        completion_repair = None
        if skeleton is not None:
            validation_errors = validate_generated_plan(plan, skeleton)
            if validation_errors:
                repair_result = repair_generated_plan(plan, skeleton, "; ".join(validation_errors))
                plan = repair_result.plan
                completion_repair = {
                    "repaired_week_indexes": repair_result.repaired_week_indexes,
                    "repaired_workout_ids": repair_result.repaired_workout_ids,
                    "reason": repair_result.reason,
                }
                repaired_errors = validate_generated_plan(plan, skeleton)
                if repaired_errors:
                    raise ValueError(f"completion repair did not produce a valid plan: {'; '.join(repaired_errors)}")
        validate_phase_segments(plan)
        saved = self._training_plans.create_active_plan(
            user_id,
            plan,
            replace_all_active=(
                trusted_context.get("manual_regeneration") is True
                or trusted_context.get("plan_type") == "maintenance"
                or trusted_context.get("replace_active_projection") is True
            ),
        )
        payload = {"training_plan": _plan_payload(saved), "applied": True}
        if completion_repair is not None:
            payload["completion_repair"] = completion_repair
        return payload


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


def _optional_date_arg(arguments: dict, name: str) -> date | None:
    if arguments.get(name) is None:
        return None
    return _date_arg(arguments, name)


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
    steps = tuple(
        step if isinstance(step, WorkoutStep) else WorkoutStep.from_payload(step)
        for step in payload.get("steps", ())
    )
    pace_profile = PaceProfile.from_payload(payload.get("_pace_profile"))
    workout_steps = enrich_workout_steps(steps, pace_profile=pace_profile) if pace_profile is not None else steps
    return Workout.create(
        id=payload.get("id"),
        scheduled_for=_date_arg(payload, "scheduled_for"),
        workout_type=payload["workout_type"],
        purpose=payload["purpose"],
        planned_duration_minutes=payload.get("planned_duration_minutes"),
        planned_distance_meters=payload.get("planned_distance_meters"),
        pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
        heart_rate_zone=payload.get("heart_rate_zone"),
        phase=payload.get("phase"),
        coach_note=payload.get("coach_note"),
        steps=tuple(workout_steps),
        status=payload.get("status", "planned"),
    )


def _plan_metadata(*, arguments: dict, trusted_context: dict) -> dict:
    model_metadata = arguments.get("metadata") if isinstance(arguments.get("metadata"), dict) else {}
    skeleton = trusted_context.get("plan_skeleton")
    if not isinstance(skeleton, dict) or not isinstance(skeleton.get("phase_segments"), list):
        metadata = dict(model_metadata)
        for key in ("plan_series_id", "previous_plan_id", "version", "continuity_summary"):
            if key in trusted_context:
                metadata[key] = trusted_context[key]
        metadata["generation_mode"] = trusted_context.get(
            "generation_mode",
            arguments.get("generation_mode", "generated"),
        )
        return metadata

    metadata: dict = {}
    weekly_rationales = model_metadata.get("weekly_rationales")
    if _has_valid_weekly_rationales(weekly_rationales):
        metadata["weekly_rationales"] = weekly_rationales
    metadata["phase_segments"] = [dict(segment) for segment in skeleton["phase_segments"]]
    for key in ("plan_series_id", "previous_plan_id", "version", "continuity_summary"):
        if key in trusted_context:
            metadata[key] = trusted_context[key]
    metadata["generation_mode"] = trusted_context.get("generation_mode", "generated")
    return metadata


def _has_valid_weekly_rationales(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(rationale, dict)
        and isinstance(rationale.get("week_index"), int)
        and isinstance(rationale.get("phase"), str)
        and isinstance(rationale.get("focus"), str)
        and isinstance(rationale.get("load_progression"), str)
        and isinstance(rationale.get("key_workouts"), list)
        and all(isinstance(workout, str) for workout in rationale["key_workouts"])
        for rationale in value
    )


def _trusted_plan_skeleton(trusted_context: dict) -> PlanSkeleton | None:
    payload = trusted_context.get("plan_skeleton")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("trusted plan skeleton is invalid")
    try:
        workouts = [
            SkeletonWorkout(
                scheduled_for=_date_arg(workout, "scheduled_for"),
                workout_type=str(workout["workout_type"]),
                phase=str(workout["phase"]),
                planned_duration_minutes=workout.get("planned_duration_minutes"),
                planned_distance_meters=workout.get("planned_distance_meters"),
            )
            for workout in payload["workouts"]
        ]
        phase_segments = [dict(segment) for segment in payload["phase_segments"]]
        skeleton = PlanSkeleton(
            starts_on=_date_arg(payload, "starts_on"),
            ends_on=_date_arg(payload, "ends_on"),
            phase_segments=phase_segments,
            workouts=workouts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("trusted plan skeleton is invalid") from exc
    _require_skeleton_workouts_for_every_week(skeleton)
    return skeleton


def _require_skeleton_workouts_for_every_week(skeleton: PlanSkeleton) -> None:
    if skeleton.ends_on < skeleton.starts_on:
        raise ValueError("trusted plan skeleton is invalid")
    week_start = skeleton.starts_on
    while week_start <= skeleton.ends_on:
        week_ends_on = min(week_start + timedelta(days=6), skeleton.ends_on)
        if not any(week_start <= workout.scheduled_for <= week_ends_on for workout in skeleton.workouts):
            raise ValueError("trusted plan skeleton must include workouts for every week")
        week_start += timedelta(weeks=1)


def _profile_payload(profile) -> dict | None:
    if profile is None:
        return None
    hard_constraints = {
        "max_runs_per_week": profile.preferences.max_runs_per_week,
        "unit_preference": profile.preferences.unit_preference,
        "injury_status": profile.preferences.injury_status,
        "injury_areas": list(profile.preferences.injury_areas),
        "injury_notes": profile.preferences.injury_notes,
        "current_weekly_mileage_km": profile.current_weekly_mileage_km,
    }
    soft_preferences = {
        "preferred_training_days": list(profile.preferences.preferred_training_days),
        "preferred_long_run_day": profile.preferences.preferred_long_run_day,
        "experience_level": profile.experience_level,
    }
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "timezone": profile.timezone,
        "experience_level": profile.experience_level,
        "current_weekly_mileage_km": profile.current_weekly_mileage_km,
        "preferred_training_days": list(profile.preferences.preferred_training_days),
        "preferred_long_run_day": profile.preferences.preferred_long_run_day,
        "max_runs_per_week": profile.preferences.max_runs_per_week,
        "max_hard_sessions_per_week": profile.preferences.max_hard_sessions_per_week,
        "unit_preference": profile.preferences.unit_preference,
        "training_preferences": dict(profile.preferences.training_preferences),
        "injury_status": profile.preferences.injury_status,
        "injury_areas": list(profile.preferences.injury_areas),
        "injury_notes": profile.preferences.injury_notes,
        "hard_constraints": hard_constraints,
        "soft_preferences": soft_preferences,
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
        "metadata": dict(plan.metadata),
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
