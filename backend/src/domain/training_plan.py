from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any


SUPPORTED_WORKOUT_STEP_TYPES = frozenset(
    {
        "warmup",
        "work",
        "recovery",
        "cooldown",
        "repeat",
        "drill",
        "stride",
        "hill",
        "free_run",
    }
)
SUPPORTED_TARGET_KINDS = frozenset({"pace", "heart_rate", "rpe"})
SUPPORTED_PACE_ZONES = frozenset(
    {
        "easy",
        "steady",
        "marathon",
        "threshold",
        "interval",
        "repetition",
        "rpe_only",
    }
)
SUPPORTED_TARGET_CONFIDENCE = frozenset({"high", "medium", "low"})
COACH_NOTE_MAX_LENGTH = 500
STEP_DURATION_TOLERANCE_SECONDS = 300
STEP_DISTANCE_TOLERANCE_METERS = 500
SUPPORTED_WORKOUT_TYPES = frozenset(
    {
        "easy_run",
        "long_run",
        "tempo",
        "interval",
        "hill",
        "recovery",
        "rest",
        "strength",
        "cross_training",
    }
)
WORKOUT_TYPE_LABELS = {
    "easy_run": "輕鬆跑", "long_run": "長跑", "tempo": "節奏跑", "interval": "間歇跑",
    "hill": "坡跑", "recovery": "恢復跑", "rest": "休息", "strength": "肌力訓練",
    "cross_training": "交叉訓練",
}
WORKOUT_PURPOSES = {
    "easy_run": "維持有氧基礎", "long_run": "建立長距離耐力", "tempo": "提升持續配速能力",
    "interval": "提升速度與有氧能力", "hill": "建立爬坡力量與跑姿穩定性",
    "recovery": "促進恢復", "rest": "充分休息", "strength": "建立肌力與身體穩定性",
    "cross_training": "以低衝擊活動維持心肺能力",
}
WORKOUT_COACH_NOTES = {
    "easy_run": "以能交談的強度完成，不必追求速度。",
    "long_run": "前段保持保守，留意補水與後段的穩定度。",
    "tempo": "保持可持續的節奏，不要一開始就加速。",
    "interval": "每趟保持穩定，組間以輕鬆慢跑恢復。",
    "hill": "上坡保持穩定出力，留意跑姿不要僵硬。",
    "recovery": "放慢速度，以身體恢復為優先。",
}
STEP_TYPE_LABELS = {
    "warmup": "暖身", "work": "主課表", "recovery": "組間恢復", "cooldown": "緩和",
    "repeat": "重複組", "drill": "跑姿練習", "stride": "加速跑", "hill": "坡跑",
    "free_run": "自由跑",
}
PACE_ZONE_LABELS = {
    "easy": "輕鬆配速", "steady": "穩定配速", "marathon": "馬拉松配速",
    "threshold": "乳酸閾值配速", "interval": "間歇配速", "repetition": "短間歇配速",
    "rpe_only": "體感強度",
}


def workout_purpose_zh(workout_type: str) -> str:
    return WORKOUT_PURPOSES.get(workout_type, "完成本次訓練")


def workout_coach_note_zh(workout_type: str) -> str:
    return WORKOUT_COACH_NOTES.get(workout_type, "依照身體狀態調整，必要時降低強度。")

SUPPORTED_PLAN_PHASES = frozenset({"base", "build", "peak", "taper", "race", "maintenance"})
HARD_SESSION_WORKOUT_TYPES = frozenset({"interval", "tempo", "hill", "long_run"})
VALID_PLAN_STATUSES = frozenset({"active", "completed", "archived", "draft", "superseded"})
VALID_WORKOUT_STATUSES = frozenset({"planned", "adjusted", "completed", "skipped"})
WORKOUT_STATUS_TRANSITIONS = {
    "planned": frozenset({"adjusted", "completed", "skipped"}),
    "adjusted": frozenset({"completed", "skipped"}),
    "completed": frozenset(),
    "skipped": frozenset(),
}
VALID_PROPOSAL_STATUSES = frozenset({"proposed", "approved", "rejected", "applied"})
PROPOSAL_STATUS_TRANSITIONS = {
    "proposed": frozenset({"approved", "rejected"}),
    "approved": frozenset({"applied"}),
    "rejected": frozenset(),
    "applied": frozenset(),
}


class DomainValidationError(ValueError):
    """Raised when training plan domain data cannot support planning."""


@dataclass(frozen=True)
class WorkoutTarget:
    kind: str
    zone: str | None = None
    heart_rate_zone: str | None = None
    rpe: int | None = None
    pace_range_seconds_per_km: tuple[int, int] | None = None
    heart_rate_range_bpm: tuple[int, int] | None = None
    confidence: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_TARGET_KINDS:
            raise DomainValidationError("target kind is not supported")
        if self.kind == "pace":
            if self.zone not in SUPPORTED_PACE_ZONES:
                raise DomainValidationError("pace target zone is not supported")
            _validate_positive_range(self.pace_range_seconds_per_km, "pace range")
        if self.kind == "heart_rate":
            if not self.heart_rate_zone:
                raise DomainValidationError("heart rate target requires zone")
            _validate_positive_range(self.heart_rate_range_bpm, "heart rate range")
        if self.kind == "rpe" and self.rpe is None:
            raise DomainValidationError("rpe target requires rpe")
        if self.rpe is not None and (self.rpe < 1 or self.rpe > 10):
            raise DomainValidationError("rpe must be between 1 and 10")
        if self.confidence is not None and self.confidence not in SUPPORTED_TARGET_CONFIDENCE:
            raise DomainValidationError("target confidence is not supported")

    @classmethod
    def pace(
        cls,
        *,
        zone: str,
        pace_range_seconds_per_km: tuple[int, int] | None = None,
        rpe: int | None = None,
        confidence: str | None = None,
    ) -> WorkoutTarget:
        return cls(
            kind="pace",
            zone=zone,
            pace_range_seconds_per_km=pace_range_seconds_per_km,
            rpe=rpe,
            confidence=confidence,
        )

    @classmethod
    def heart_rate(
        cls,
        *,
        heart_rate_zone: str,
        heart_rate_range_bpm: tuple[int, int] | None = None,
        rpe: int | None = None,
        confidence: str | None = None,
    ) -> WorkoutTarget:
        return cls(
            kind="heart_rate",
            heart_rate_zone=heart_rate_zone,
            heart_rate_range_bpm=heart_rate_range_bpm,
            rpe=rpe,
            confidence=confidence,
        )

    @classmethod
    def rpe(cls, rpe: int) -> WorkoutTarget:
        return cls(kind="rpe", rpe=rpe)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkoutTarget:
        pace_range = payload.get("pace_range_seconds_per_km")
        heart_rate_range = payload.get("heart_rate_range_bpm")
        return cls(
            kind=payload["kind"],
            zone=payload.get("zone"),
            heart_rate_zone=payload.get("heart_rate_zone"),
            rpe=payload.get("rpe"),
            pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
            heart_rate_range_bpm=tuple(heart_rate_range) if heart_rate_range is not None else None,
            confidence=payload.get("confidence"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "zone": self.zone,
            "heart_rate_zone": self.heart_rate_zone,
            "rpe": self.rpe,
            "pace_range_seconds_per_km": list(self.pace_range_seconds_per_km)
            if self.pace_range_seconds_per_km is not None
            else None,
            "heart_rate_range_bpm": list(self.heart_rate_range_bpm)
            if self.heart_rate_range_bpm is not None
            else None,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class WorkoutStep:
    step_type: str
    duration_seconds: int | None = None
    distance_meters: int | None = None
    target: WorkoutTarget | None = None
    repeat_count: int | None = None
    steps: tuple[WorkoutStep, ...] = ()
    notes: str | None = None
    grade_notes: str | None = None

    def __post_init__(self) -> None:
        if self.step_type not in SUPPORTED_WORKOUT_STEP_TYPES:
            raise DomainValidationError("workout step type is not supported")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise DomainValidationError("step duration must be greater than zero")
        if self.distance_meters is not None and self.distance_meters <= 0:
            raise DomainValidationError("step distance must be greater than zero")
        normalized_steps = _normalize_steps(self.steps)
        object.__setattr__(self, "steps", normalized_steps)
        if self.step_type == "repeat":
            if self.repeat_count is None or self.repeat_count < 1:
                raise DomainValidationError("repeat block requires positive repeat count")
            if not normalized_steps:
                raise DomainValidationError("repeat block requires nested steps")
            return
        if self.repeat_count is not None:
            raise DomainValidationError("repeat count is only valid for repeat blocks")
        if normalized_steps:
            raise DomainValidationError("nested steps are only valid for repeat blocks")
        if self.duration_seconds is None and self.distance_meters is None:
            raise DomainValidationError("step requires distance or duration")

    @classmethod
    def create(
        cls,
        *,
        step_type: str,
        duration_seconds: int | None = None,
        distance_meters: int | None = None,
        target: WorkoutTarget | dict[str, Any] | None = None,
        repeat_count: int | None = None,
        steps: tuple[WorkoutStep | dict[str, Any], ...] = (),
        notes: str | None = None,
        grade_notes: str | None = None,
    ) -> WorkoutStep:
        return cls(
            step_type=step_type,
            duration_seconds=duration_seconds,
            distance_meters=distance_meters,
            target=_normalize_target(target),
            repeat_count=repeat_count,
            steps=_normalize_steps(steps),
            notes=notes,
            grade_notes=grade_notes,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WorkoutStep:
        return cls.create(
            step_type=payload["type"],
            duration_seconds=payload.get("duration_seconds"),
            distance_meters=payload.get("distance_meters"),
            target=payload.get("target"),
            repeat_count=payload.get("repeat_count"),
            steps=tuple(payload.get("steps", ())),
            notes=payload.get("notes"),
            grade_notes=payload.get("grade_notes"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.step_type,
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "target": self.target.to_payload() if self.target is not None else None,
            "repeat_count": self.repeat_count,
            "steps": [step.to_payload() for step in self.steps],
            "notes": self.notes,
            "grade_notes": self.grade_notes,
        }

    @property
    def total_duration_seconds(self) -> int | None:
        if self.step_type == "repeat":
            nested_total = _sum_complete_optional(step.total_duration_seconds for step in self.steps)
            return nested_total * int(self.repeat_count or 0) if nested_total is not None else None
        return self.duration_seconds

    @property
    def total_distance_meters(self) -> int | None:
        if self.step_type == "repeat":
            nested_total = _sum_complete_optional(step.total_distance_meters for step in self.steps)
            return nested_total * int(self.repeat_count or 0) if nested_total is not None else None
        return self.distance_meters


@dataclass(frozen=True)
class Workout:
    scheduled_for: date
    workout_type: str
    purpose: str
    planned_duration_minutes: int | None = None
    planned_distance_meters: int | None = None
    pace_range_seconds_per_km: tuple[int, int] | None = None
    heart_rate_zone: str | None = None
    phase: str | None = None
    coach_note: str | None = None
    steps: tuple[WorkoutStep, ...] = field(default_factory=tuple)
    status: str = "planned"
    id: str | None = None

    def __post_init__(self) -> None:
        normalized_steps = _normalize_steps(self.steps)
        object.__setattr__(self, "steps", normalized_steps)
        planned_duration_minutes = self.planned_duration_minutes
        planned_distance_meters = self.planned_distance_meters
        step_duration_seconds = _sum_complete_optional(step.total_duration_seconds for step in normalized_steps)
        step_distance_meters = _sum_complete_optional(step.total_distance_meters for step in normalized_steps)
        if planned_duration_minutes is None and step_duration_seconds is not None:
            planned_duration_minutes = _ceil_minutes(step_duration_seconds)
            object.__setattr__(self, "planned_duration_minutes", planned_duration_minutes)
        if planned_distance_meters is None and step_distance_meters is not None:
            planned_distance_meters = step_distance_meters
            object.__setattr__(self, "planned_distance_meters", planned_distance_meters)
        if self.workout_type not in SUPPORTED_WORKOUT_TYPES:
            raise DomainValidationError("workout type is not supported")
        if self.phase is not None and self.phase not in SUPPORTED_PLAN_PHASES:
            raise DomainValidationError("workout phase is not supported")
        if not self.purpose:
            raise DomainValidationError("workout purpose is required")
        if self.status not in VALID_WORKOUT_STATUSES:
            raise DomainValidationError("workout status is invalid")
        if planned_duration_minutes is None and planned_distance_meters is None:
            raise DomainValidationError("workout requires planned distance or duration")
        if planned_duration_minutes is not None and planned_duration_minutes <= 0:
            raise DomainValidationError("planned duration must be greater than zero")
        if planned_distance_meters is not None and planned_distance_meters <= 0:
            raise DomainValidationError("planned distance must be greater than zero")
        if self.pace_range_seconds_per_km is not None:
            lower, upper = self.pace_range_seconds_per_km
            if lower <= 0 or upper <= 0 or lower > upper:
                raise DomainValidationError("pace range is invalid")
        if self.coach_note is not None and len(self.coach_note) > COACH_NOTE_MAX_LENGTH:
            raise DomainValidationError("coach note is too long")
        _validate_step_totals(
            planned_duration_minutes=planned_duration_minutes,
            planned_distance_meters=planned_distance_meters,
            step_duration_seconds=step_duration_seconds,
            step_distance_meters=step_distance_meters,
        )

    @classmethod
    def create(
        cls,
        *,
        scheduled_for: date,
        workout_type: str,
        purpose: str,
        planned_duration_minutes: int | None = None,
        planned_distance_meters: int | None = None,
        pace_range_seconds_per_km: tuple[int, int] | None = None,
        heart_rate_zone: str | None = None,
        phase: str | None = None,
        coach_note: str | None = None,
        steps: tuple[WorkoutStep | dict[str, Any], ...] = (),
        status: str = "planned",
        id: str | None = None,
    ) -> Workout:
        return cls(
            id=id,
            scheduled_for=scheduled_for,
            workout_type=workout_type,
            purpose=purpose,
            planned_duration_minutes=planned_duration_minutes,
            planned_distance_meters=planned_distance_meters,
            pace_range_seconds_per_km=pace_range_seconds_per_km,
            heart_rate_zone=heart_rate_zone,
            phase=phase,
            coach_note=coach_note,
            steps=_normalize_steps(steps),
            status=status,
        )

    def transition_to(self, status: str) -> Workout:
        if status not in WORKOUT_STATUS_TRANSITIONS[self.status]:
            raise DomainValidationError(f"invalid workout status transition: {self.status} -> {status}")
        return replace(self, status=status)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "workout_type": self.workout_type,
            "display_name": self.display_name,
            "purpose": self.purpose,
            "planned_duration_minutes": self.planned_duration_minutes,
            "planned_distance_meters": self.planned_distance_meters,
            "pace_range_seconds_per_km": list(self.pace_range_seconds_per_km)
            if self.pace_range_seconds_per_km is not None
            else None,
            "heart_rate_zone": self.heart_rate_zone,
            "phase": self.phase,
            "coach_note": self.coach_note,
            "steps": [step.to_payload() for step in self.steps],
            "compact_summary": self.compact_summary,
            "status": self.status,
        }

    @property
    def display_name(self) -> str:
        label = WORKOUT_TYPE_LABELS.get(self.workout_type, "訓練")
        for step in self.steps:
            if step.step_type == "repeat":
                work = next((item for item in step.steps if item.step_type in {"work", "hill", "stride"}), None)
                if work is not None:
                    workload = _format_step_load(work)
                    return f"{label} · {step.repeat_count} 組 × {workload}"
        main = next((step for step in self.steps if step.step_type == "work"), None)
        if main is not None:
            return f"{label} · {_format_step_load(main)}"
        if self.planned_distance_meters is not None:
            return f"{label} · {_format_distance(self.planned_distance_meters)}"
        if self.planned_duration_minutes is not None:
            return f"{label} · {self.planned_duration_minutes} 分鐘"
        return label

    @property
    def compact_summary(self) -> str | None:
        if not self.steps:
            return None
        return format_workout_steps_compact(self.steps)


@dataclass(frozen=True)
class TrainingPlan:
    user_id: str
    name: str
    starts_on: date
    ends_on: date
    race_id: str | None = None
    status: str = "active"
    workouts: tuple[Workout, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.name:
            raise DomainValidationError("training plan name is required")
        if self.status not in VALID_PLAN_STATUSES:
            raise DomainValidationError("training plan status is invalid")
        if self.ends_on < self.starts_on:
            raise DomainValidationError("training plan end date cannot be before start date")
        ordered_workouts = tuple(sorted(self.workouts, key=lambda workout: workout.scheduled_for))
        for workout in ordered_workouts:
            if workout.scheduled_for < self.starts_on or workout.scheduled_for > self.ends_on:
                raise DomainValidationError("workout is outside plan date range")
        object.__setattr__(self, "workouts", ordered_workouts)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        name: str,
        starts_on: date,
        ends_on: date,
        race_id: str | None = None,
        status: str = "active",
        workouts: tuple[Workout, ...] = (),
        metadata: dict[str, Any] | None = None,
        id: str | None = None,
    ) -> TrainingPlan:
        return cls(
            id=id,
            user_id=user_id,
            race_id=race_id,
            name=name,
            status=status,
            starts_on=starts_on,
            ends_on=ends_on,
            workouts=workouts,
            metadata=metadata or {},
        )


def is_hard_session(workout: Workout) -> bool:
    return workout.workout_type in HARD_SESSION_WORKOUT_TYPES


def validate_phase_segments(plan: TrainingPlan) -> None:
    raw_segments = plan.metadata.get("phase_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise DomainValidationError("phase segments are required")

    segments = tuple(_phase_segment_from_payload(segment) for segment in raw_segments)
    ordered_segments = tuple(sorted(segments, key=lambda segment: segment[1]))
    expected_start = plan.starts_on
    for phase, starts_on, ends_on in ordered_segments:
        if starts_on < expected_start:
            raise DomainValidationError("phase segments overlap")
        if starts_on != expected_start:
            raise DomainValidationError("phase segments do not fully cover plan date range")
        expected_start = date.fromordinal(ends_on.toordinal() + 1)
    if expected_start != date.fromordinal(plan.ends_on.toordinal() + 1):
        raise DomainValidationError("phase segments do not fully cover plan date range")

    for workout in plan.workouts:
        if workout.phase is None:
            raise DomainValidationError("workout phase is required")
        segment_phase = next(
            (
                phase
                for phase, starts_on, ends_on in ordered_segments
                if starts_on <= workout.scheduled_for <= ends_on
            ),
            None,
        )
        if segment_phase != workout.phase:
            raise DomainValidationError("workout phase does not match phase segment")


def _phase_segment_from_payload(payload: Any) -> tuple[str, date, date]:
    if not isinstance(payload, dict):
        raise DomainValidationError("phase segment is invalid")
    phase = payload.get("phase")
    if phase not in SUPPORTED_PLAN_PHASES:
        raise DomainValidationError("plan phase is not supported")
    starts_on = _phase_segment_date(payload.get("starts_on"))
    ends_on = _phase_segment_date(payload.get("ends_on"))
    if ends_on < starts_on:
        raise DomainValidationError("phase segment end date cannot be before start date")
    return phase, starts_on, ends_on


def _phase_segment_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise DomainValidationError("phase segment date is invalid") from exc
    raise DomainValidationError("phase segment date is invalid")


@dataclass(frozen=True)
class PlanAdjustmentProposal:
    user_id: str
    training_plan_id: str
    before_payload: dict[str, Any]
    after_payload: dict[str, Any]
    workout_id: str | None = None
    recommendation_id: str | None = None
    status: str = "proposed"
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.training_plan_id:
            raise DomainValidationError("training plan id is required")
        if not self.before_payload:
            raise DomainValidationError("before payload is required")
        if not self.after_payload:
            raise DomainValidationError("after payload is required")
        if self.status not in VALID_PROPOSAL_STATUSES:
            raise DomainValidationError("proposal status is invalid")
        object.__setattr__(self, "before_payload", dict(self.before_payload))
        object.__setattr__(self, "after_payload", dict(self.after_payload))

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        training_plan_id: str,
        before_payload: dict[str, Any],
        after_payload: dict[str, Any],
        workout_id: str | None = None,
        recommendation_id: str | None = None,
        status: str = "proposed",
        id: str | None = None,
    ) -> PlanAdjustmentProposal:
        return cls(
            id=id,
            user_id=user_id,
            training_plan_id=training_plan_id,
            workout_id=workout_id,
            recommendation_id=recommendation_id,
            before_payload=before_payload,
            after_payload=after_payload,
            status=status,
        )

    def transition_to(self, status: str) -> PlanAdjustmentProposal:
        if status not in PROPOSAL_STATUS_TRANSITIONS[self.status]:
            raise DomainValidationError(f"invalid proposal status transition: {self.status} -> {status}")
        return replace(self, status=status)


def format_workout_steps_compact(steps: tuple[WorkoutStep, ...]) -> str:
    return " ＋ ".join(_format_step_compact(step) for step in steps)


def _format_step_compact(step: WorkoutStep) -> str:
    if step.step_type == "repeat":
        nested = "／".join(_format_step_compact(nested_step) for nested_step in step.steps)
        return f"{step.repeat_count} 組（{nested}）"
    load = _format_step_load(step)
    label = _format_step_label(step)
    return f"{label} {load}".strip()


def _format_step_load(step: WorkoutStep) -> str:
    if step.distance_meters is not None:
        return _format_distance(step.distance_meters)
    if step.duration_seconds is not None:
        return _format_duration(step.duration_seconds)
    return ""


def _format_step_label(step: WorkoutStep) -> str:
    step_label = STEP_TYPE_LABELS.get(step.step_type, "訓練")
    if step.target is not None and step.target.kind == "pace" and step.target.zone:
        return f"{step_label}・{PACE_ZONE_LABELS.get(step.target.zone, '指定配速')}"
    if step.target is not None and step.target.kind == "heart_rate" and step.target.heart_rate_zone:
        return f"{step_label}・心率區間 {step.target.heart_rate_zone}"
    return step_label


def _format_distance(distance_meters: int) -> str:
    if distance_meters >= 1000 and distance_meters % 1000 == 0:
        return f"{distance_meters // 1000} 公里"
    return f"{distance_meters} 公尺"


def _format_duration(duration_seconds: int) -> str:
    if duration_seconds % 60 == 0:
        return f"{duration_seconds // 60} 分鐘"
    return f"{duration_seconds} 秒"


def _normalize_target(target: WorkoutTarget | dict[str, Any] | None) -> WorkoutTarget | None:
    if target is None or isinstance(target, WorkoutTarget):
        return target
    return WorkoutTarget.from_payload(target)


def _normalize_steps(steps: tuple[WorkoutStep | dict[str, Any], ...]) -> tuple[WorkoutStep, ...]:
    return tuple(step if isinstance(step, WorkoutStep) else WorkoutStep.from_payload(step) for step in steps)


def _sum_optional(values) -> int | None:
    total = 0
    found = False
    for value in values:
        if value is None:
            continue
        total += int(value)
        found = True
    return total if found else None


def _sum_complete_optional(values) -> int | None:
    total = 0
    found = False
    for value in values:
        if value is None:
            return None
        total += int(value)
        found = True
    return total if found else None


def _ceil_minutes(duration_seconds: int) -> int:
    return max(1, (duration_seconds + 59) // 60)


def _validate_positive_range(value: tuple[int, int] | None, label: str) -> None:
    if value is None:
        return
    lower, upper = value
    if lower <= 0 or upper <= 0 or lower > upper:
        raise DomainValidationError(f"{label} is invalid")


def _validate_step_totals(
    *,
    planned_duration_minutes: int | None,
    planned_distance_meters: int | None,
    step_duration_seconds: int | None,
    step_distance_meters: int | None,
) -> None:
    if planned_duration_minutes is not None and step_duration_seconds is not None:
        planned_seconds = planned_duration_minutes * 60
        if abs(planned_seconds - step_duration_seconds) > STEP_DURATION_TOLERANCE_SECONDS:
            raise DomainValidationError("planned duration does not match workout steps")
    if planned_distance_meters is not None and step_distance_meters is not None:
        if abs(planned_distance_meters - step_distance_meters) > STEP_DISTANCE_TOLERANCE_METERS:
            raise DomainValidationError("planned distance does not match workout steps")
