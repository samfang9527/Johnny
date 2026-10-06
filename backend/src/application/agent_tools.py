from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Iterable
from uuid import uuid4

from src.application.training_plan_generation import (
    PlanSkeleton,
    SkeletonWorkout,
    _race_rpe,
    repair_generated_plan,
    validate_generated_plan,
)
from src.application.training_targets import TargetProfile, enrich_workout_steps
from src.application.training_analytics import BuildTodayContextHandler
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, validate_phase_segments, workout_coach_note_zh, workout_purpose_zh


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
        workouts = []
        parse_errors = []
        name = arguments.get("name")
        if skeleton is not None and (not isinstance(name, str) or not name.strip()):
            parse_errors.append("plan name is invalid")
            name = "Generated Training Plan"
        if skeleton is not None:
            starts_on, ends_on = skeleton.starts_on, skeleton.ends_on
            for key, expected in (("starts_on", starts_on), ("ends_on", ends_on)):
                try:
                    if _date_arg(arguments, key) != expected:
                        parse_errors.append(f"plan {key} does not match the skeleton")
                except (ValueError, KeyError, TypeError):
                    parse_errors.append(f"plan {key} is invalid")
        else:
            starts_on, ends_on = _date_arg(arguments, "starts_on"), _date_arg(arguments, "ends_on")
        for payload in arguments.get("workouts", ()):
            try:
                if skeleton is not None and payload.get("workout_type") == "race":
                    expected_race = next(
                        (
                            item for item in skeleton.workouts
                            if item.workout_type == "race"
                            and item.scheduled_for == _date_arg(payload, "scheduled_for")
                            and item.race_goal_id == payload.get("race_goal_id")
                        ),
                        None,
                    )
                    if expected_race is not None:
                        payload = {
                            **payload,
                            "race_name": expected_race.race_name,
                            "race_priority": expected_race.race_priority,
                        }
                workout = _workout_from_payload({**payload, "id": str(uuid4()), "_pace_profile": pace_profile})
                if skeleton is not None and not skeleton.starts_on <= workout.scheduled_for <= skeleton.ends_on:
                    raise ValueError("workout is outside skeleton date range")
                workouts.append(workout)
            except (ValueError, KeyError, TypeError) as error:
                if skeleton is None:
                    raise
                parse_errors.append(str(error))
        plan = TrainingPlan.create(
            user_id=user_id,
            race_id=trusted_context.get("race_id", arguments.get("race_id")),
            name=name,
            status="active",
            starts_on=starts_on,
            ends_on=ends_on,
            metadata=_plan_metadata(arguments=arguments, trusted_context=trusted_context),
            workouts=tuple(workouts),
        )
        completion_repair = None
        if skeleton is not None:
            validation_errors = parse_errors + validate_generated_plan(plan, skeleton)
            if validation_errors:
                if trusted_context.get("model_repair_pending") is True:
                    raise IncompleteTrainingPlan(plan, "; ".join(validation_errors))
                preserved = trusted_context.get("preserved_generation") or {}
                preserved_workouts = tuple(
                    _workout_from_payload({**workout, "_pace_profile": pace_profile})
                    for workout in preserved.get("workouts", ())
                )
                repair_result = repair_generated_plan(
                    plan, skeleton, "; ".join(validation_errors), preserved_workouts=preserved_workouts,
                )
                plan = repair_result.plan
                completion_repair = {
                    "repaired_week_indexes": repair_result.repaired_week_indexes,
                    "repaired_workout_ids": repair_result.repaired_workout_ids,
                    "reason": repair_result.reason,
                }
                repaired_errors = validate_generated_plan(plan, skeleton)
                if repaired_errors:
                    raise ValueError(f"completion repair did not produce a valid plan: {'; '.join(repaired_errors)}")
        canonical_target_profile = TargetProfile.from_payload(
            trusted_context.get("target_profile") if isinstance(trusted_context.get("target_profile"), dict) else pace_profile,
        )
        plan = replace(plan, workouts=tuple(
            replace(
                workout,
                steps=enrich_workout_steps(
                    workout.steps, workout_type=workout.workout_type,
                    target_profile=canonical_target_profile,
                    race_rpe=next(
                        (
                            _race_rpe(expected) for expected in skeleton.workouts
                            if expected.workout_type == "race" and expected.race_goal_id == workout.race_goal_id
                            and expected.scheduled_for == workout.scheduled_for
                        ),
                        None,
                    ) if skeleton is not None and workout.workout_type == "race" else None,
                ),
            )
            for workout in plan.workouts
        ))
        if skeleton is not None:
            plan = replace(
                plan,
                name=plan.name if _has_chinese(plan.name) else "Johnny 訓練計畫",
                workouts=tuple(_localize_workout_copy(workout) for workout in plan.workouts),
            )
        if trusted_context.get("model_repair_reason"):
            internal = dict(plan.metadata.get("internal") or {})
            internal["model_repair"] = {"attempted": True, "reason": trusted_context["model_repair_reason"]}
            plan = replace(plan, metadata={**plan.metadata, "internal": internal})
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


class IncompleteTrainingPlan(ValueError):
    def __init__(self, plan: TrainingPlan, reason: str) -> None:
        super().__init__(f"model repair required: {reason}")
        self.plan_payload = _plan_payload(plan)


def _has_chinese(value: str | None) -> bool:
    return bool(value and any("\u4e00" <= character <= "\u9fff" for character in value))


def _localize_workout_copy(workout: Workout) -> Workout:
    coach_note = workout.coach_note
    if coach_note and not _has_chinese(coach_note):
        coach_note = workout_coach_note_zh(workout.workout_type)
    return replace(
        workout,
        purpose=workout.purpose if _has_chinese(workout.purpose) else workout_purpose_zh(workout.workout_type),
        coach_note=coach_note,
        steps=tuple(_localize_step_copy(step) for step in workout.steps),
    )


def _localize_step_copy(step: WorkoutStep) -> WorkoutStep:
    return replace(
        step,
        notes=step.notes if _has_chinese(step.notes) else None,
        grade_notes=step.grade_notes if _has_chinese(step.grade_notes) else None,
        steps=tuple(_localize_step_copy(nested) for nested in step.steps),
    )


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
        steps=steps,
        status=payload.get("status", "planned"),
        race_goal_id=payload.get("race_goal_id"),
        race_name=payload.get("race_name"),
        race_priority=payload.get("race_priority"),
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
    if trusted_context.get("workload_policy_version"):
        metadata["workload_policy_version"] = trusted_context["workload_policy_version"]
    if isinstance(trusted_context.get("preparation_assessment"), dict):
        metadata["preparation_assessment"] = dict(trusted_context["preparation_assessment"])
    if isinstance(trusted_context.get("capacity_snapshot"), dict):
        metadata["internal"] = {"capacity_snapshot": dict(trusted_context["capacity_snapshot"])}
    if isinstance(trusted_context.get("target_profile"), dict):
        internal = dict(metadata.get("internal") or {})
        internal["target_policy_version"] = trusted_context["target_profile"].get("policy_version")
        internal["pace_source"] = trusted_context["target_profile"].get("pace_source")
        metadata["internal"] = internal
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
                race_goal_id=workout.get("race_goal_id"),
                race_name=workout.get("race_name"),
                race_priority=workout.get("race_priority"),
                race_goal_intent=workout.get("race_goal_intent"),
                is_target_race=workout.get("is_target_race") is True,
                focus_zone=workout.get("focus_zone"),
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
        "resting_heart_rate_bpm": profile.preferences.training_preferences.get("resting_heart_rate_bpm"),
        "max_heart_rate_bpm": profile.preferences.training_preferences.get("max_heart_rate_bpm"),
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
        "ascent_meters": goal.ascent_meters,
        "descent_meters": goal.descent_meters,
        "terrain_difficulty": goal.terrain_difficulty,
        "cutoff_seconds": goal.cutoff_seconds,
        "goal_intent": goal.goal_intent,
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
