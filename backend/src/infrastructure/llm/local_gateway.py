from __future__ import annotations

from datetime import date

from src.domain.agent_runtime import ModelRequest, ModelResponse, TokenUsage, ToolCallRequest
from src.domain.training_plan import workout_purpose_zh


class LocalCompanionModelGateway:
    """Network-free companion gateway for local development and API tests."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.workflow_name == "daily_recommendation":
            return ModelResponse(
                content="Johnny created a conservative local training recommendation.",
                tool_calls=(
                    ToolCallRequest(
                        tool_name="createRecommendation",
                        arguments=_recommendation_arguments(
                            title="Review today's training context",
                            rationale="Local companion mode reviewed the available context. Connect OpenAI for model-backed analysis.",
                        ),
                    ),
                ),
                token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                provider="local",
                model="deterministic-local-companion",
            )

        if request.workflow_name == "training_plan_generation":
            plan_arguments = _plan_arguments(request.context or {})
            return ModelResponse(
                content="Johnny generated a local deterministic active training plan.",
                tool_calls=(
                    ToolCallRequest(
                        tool_name="createTrainingPlan",
                        arguments=plan_arguments,
                    ),
                ),
                token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                provider="local",
                model="deterministic-local-companion",
            )

        return ModelResponse(
            content="Johnny received your message in local companion mode. Connect OpenAI for model-backed coaching.",
            tool_calls=(
                ToolCallRequest(
                    tool_name="createRecommendation",
                    arguments=_recommendation_arguments(
                        title="Review today's training context",
                        rationale="Local companion mode created a pending recommendation so the approval loop can be tested end to end.",
                    ),
                ),
            ),
            token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            provider="local",
            model="deterministic-local-companion",
        )


def _recommendation_arguments(*, title: str, rationale: str) -> dict:
    return {
        "title": title,
        "rationale": rationale,
        "recommendation_type": "informational",
        "priority": "medium",
        "evidence": [
            {
                "source": "local_companion",
                "metric": "runtime_mode",
                "value": "local",
                "summary": "Network-free local companion mode",
            }
        ],
        "action": {
            "type": "no_plan_change",
            "reason": "Local mode does not apply training changes.",
        },
    }


def _plan_arguments(context: dict) -> dict:
    skeleton = context.get("plan_skeleton")
    if not isinstance(skeleton, dict):
        raise ValueError("plan skeleton is required for local training plan generation")
    starts_on = _date_from_context(skeleton.get("starts_on"))
    ends_on = _date_from_context(skeleton.get("ends_on"))
    if starts_on is None or ends_on is None:
        raise ValueError("plan skeleton dates are required")
    skeleton_workouts = skeleton.get("workouts")
    if not isinstance(skeleton_workouts, list):
        raise ValueError("plan skeleton workouts are required")
    workouts = [
        _workout_payload(
            scheduled_for=_required_skeleton_date(workout),
            workout_type=str(workout["workout_type"]),
            phase=str(workout["phase"]),
            planned_duration_minutes=workout.get("planned_duration_minutes"),
            planned_distance_meters=workout.get("planned_distance_meters"),
            week=(_required_skeleton_date(workout) - starts_on).days // 7,
        )
        for workout in skeleton_workouts
        if isinstance(workout, dict)
    ]
    return {
        "name": "Johnny 訓練計畫",
        "race_id": context.get("selected_race_id"),
        "starts_on": starts_on.isoformat(),
        "ends_on": ends_on.isoformat(),
        "metadata": {
            "phase_segments": skeleton.get("phase_segments", ()),
        },
        "workouts": workouts,
    }


def _date_from_context(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _workout_purpose(workout_type: str) -> str:
    return workout_purpose_zh(workout_type)


def _required_skeleton_date(workout: dict) -> date:
    scheduled_for = _date_from_context(workout.get("scheduled_for"))
    if scheduled_for is None:
        raise ValueError("plan skeleton workout date is required")
    return scheduled_for


def _workout_payload(
    *,
    scheduled_for: date,
    workout_type: str,
    phase: str,
    planned_duration_minutes: int | None,
    planned_distance_meters: int | None,
    week: int,
) -> dict:
    duration_minutes = planned_duration_minutes or 45
    if workout_type == "interval":
        total_seconds = duration_minutes * 60
        warmup_seconds = min(600, total_seconds // 4)
        cooldown_seconds = min(600, total_seconds // 4)
        repetitions = 4 + min(week, 2)
        per_repeat = (total_seconds - warmup_seconds - cooldown_seconds) // repetitions
        cooldown_seconds += total_seconds - warmup_seconds - cooldown_seconds - per_repeat * repetitions
        work_seconds = max(1, round(per_repeat * .6))
        return {
            "scheduled_for": scheduled_for.isoformat(),
            "workout_type": workout_type,
            "purpose": _workout_purpose(workout_type),
            "planned_duration_minutes": duration_minutes,
            "planned_distance_meters": planned_distance_meters,
            "phase": phase,
            "coach_note": "每趟保持穩定，組間以輕鬆慢跑恢復。",
            "steps": [
                {"type": "warmup", "duration_seconds": warmup_seconds, "target": {"kind": "rpe", "rpe": 3}},
                {
                    "type": "repeat",
                    "repeat_count": repetitions,
                    "steps": [
                        {"type": "work", "duration_seconds": work_seconds, "target": {"kind": "pace", "zone": "interval", "rpe": 8}},
                        {"type": "recovery", "duration_seconds": per_repeat - work_seconds, "target": {"kind": "pace", "zone": "easy", "rpe": 3}},
                    ],
                },
                {"type": "cooldown", "duration_seconds": cooldown_seconds, "target": {"kind": "rpe", "rpe": 2}},
            ],
        }
    if workout_type == "tempo":
        warmup_seconds, work_duration_seconds, cooldown_seconds = _tempo_step_durations(duration_minutes, week)
        return {
            "scheduled_for": scheduled_for.isoformat(),
            "workout_type": workout_type,
            "purpose": _workout_purpose(workout_type),
            "planned_duration_minutes": duration_minutes,
            "planned_distance_meters": planned_distance_meters,
            "phase": phase,
            "coach_note": "節奏維持平順，以能穩定完成全程為原則。",
            "steps": [
                {"type": "warmup", "duration_seconds": warmup_seconds, "target": {"kind": "rpe", "rpe": 3}},
                {"type": "work", "duration_seconds": work_duration_seconds, "target": {"kind": "pace", "zone": "threshold", "rpe": 7}},
                {"type": "cooldown", "duration_seconds": cooldown_seconds, "target": {"kind": "rpe", "rpe": 2}},
            ],
        }
    if workout_type == "hill":
        total_seconds = duration_minutes * 60
        warmup_seconds = min(600, total_seconds // 4)
        cooldown_seconds = min(600, total_seconds // 4)
        per_repeat = (total_seconds - warmup_seconds - cooldown_seconds) // 4
        cooldown_seconds += total_seconds - warmup_seconds - cooldown_seconds - per_repeat * 4
        hill_seconds = max(1, round(per_repeat * .4))
        return {
            "scheduled_for": scheduled_for.isoformat(),
            "workout_type": workout_type,
            "purpose": _workout_purpose(workout_type),
            "planned_duration_minutes": duration_minutes,
            "planned_distance_meters": planned_distance_meters,
            "phase": phase,
            "coach_note": "上坡保持穩定出力，留意跑姿不要僵硬。",
            "steps": [
                {"type": "warmup", "duration_seconds": warmup_seconds, "target": {"kind": "rpe", "rpe": 3}},
                {
                    "type": "repeat",
                    "repeat_count": 4,
                    "steps": [
                        {"type": "hill", "duration_seconds": hill_seconds, "target": {"kind": "rpe", "rpe": 8}},
                        {"type": "recovery", "duration_seconds": per_repeat - hill_seconds, "target": {"kind": "pace", "zone": "easy", "rpe": 3}},
                    ],
                },
                {"type": "cooldown", "duration_seconds": cooldown_seconds, "target": {"kind": "rpe", "rpe": 2}},
            ],
        }
    return {
        "scheduled_for": scheduled_for.isoformat(),
        "workout_type": workout_type,
        "purpose": _workout_purpose(workout_type),
        "planned_duration_minutes": duration_minutes,
        "planned_distance_meters": planned_distance_meters,
        "phase": phase,
        "steps": [
            {
                "type": "free_run",
                "duration_seconds": duration_minutes * 60,
                "target": {"kind": "pace", "zone": "easy", "rpe": 3},
            }
        ],
    }


def _tempo_step_durations(duration_minutes: int, week: int) -> tuple[int, int, int]:
    total_seconds = duration_minutes * 60
    warmup_seconds = min(600, total_seconds // 3)
    cooldown_seconds = min(600, (total_seconds - warmup_seconds) // 2)
    work_duration_seconds = total_seconds - warmup_seconds - cooldown_seconds
    return warmup_seconds, work_duration_seconds, cooldown_seconds
