from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.training_plan import TrainingPlan, Workout


READINESS_LABELS = frozenset({"unknown", "ready", "caution", "rest"})
SNAPSHOT_TYPES = frozenset({"training_load", "recovery_context", "today_context"})
RUN_SPORT_TYPES = frozenset({"run", "running"})
SLEEP_TARGET_MINUTES = 480


@dataclass(frozen=True)
class MetricWindow:
    starts_on: date
    ends_on: date

    def contains(self, value: date) -> bool:
        return self.starts_on <= value <= self.ends_on


@dataclass(frozen=True)
class UnavailableSignal:
    name: str
    reason: str


@dataclass(frozen=True)
class TrainingLoadSummary:
    user_id: str
    anchor_date: date
    weekly_distance_meters: float
    previous_weekly_distance_meters: float
    mileage_ramp_percentage: float | None
    acute_load: float
    chronic_load: float | None
    acute_chronic_ratio: float | None
    unavailable_signals: tuple[str, ...] = ()
    evidence: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "anchor_date": self.anchor_date.isoformat(),
            "weekly_distance_meters": self.weekly_distance_meters,
            "previous_weekly_distance_meters": self.previous_weekly_distance_meters,
            "mileage_ramp_percentage": self.mileage_ramp_percentage,
            "acute_load": self.acute_load,
            "chronic_load": self.chronic_load,
            "acute_chronic_ratio": self.acute_chronic_ratio,
            "unavailable_signals": list(self.unavailable_signals),
            "evidence": self.evidence or {},
        }


@dataclass(frozen=True)
class RecoveryContext:
    user_id: str
    anchor_date: date
    readiness_label: str
    sleep_debt_minutes: float | None
    hrv_delta_percentage: float | None
    resting_heart_rate_baseline: float | None
    resting_heart_rate_delta_bpm: float | None
    stress_score: float | None
    body_battery_score: float | None
    unavailable_signals: tuple[str, ...] = ()
    evidence: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "anchor_date": self.anchor_date.isoformat(),
            "readiness_label": self.readiness_label,
            "sleep_debt_minutes": self.sleep_debt_minutes,
            "hrv_delta_percentage": self.hrv_delta_percentage,
            "resting_heart_rate_baseline": self.resting_heart_rate_baseline,
            "resting_heart_rate_delta_bpm": self.resting_heart_rate_delta_bpm,
            "stress_score": self.stress_score,
            "body_battery_score": self.body_battery_score,
            "unavailable_signals": list(self.unavailable_signals),
            "evidence": self.evidence or {},
        }


@dataclass(frozen=True)
class TodayContext:
    user_id: str
    anchor_date: date
    scheduled_workouts: tuple[dict[str, Any], ...]
    recent_activities: tuple[dict[str, Any], ...]
    training_load: TrainingLoadSummary
    recovery: RecoveryContext
    unavailable_signals: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "anchor_date": self.anchor_date.isoformat(),
            "scheduled_workouts": list(self.scheduled_workouts),
            "recent_activities": list(self.recent_activities),
            "training_load": self.training_load.to_payload(),
            "recovery": self.recovery.to_payload(),
            "unavailable_signals": list(self.unavailable_signals),
        }


@dataclass(frozen=True)
class TrainingMetricSnapshot:
    user_id: str
    snapshot_type: str
    captured_at: datetime
    metrics: dict[str, Any]
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user id is required")
        if self.snapshot_type not in SNAPSHOT_TYPES:
            raise ValueError("snapshot type is not supported")
        object.__setattr__(self, "metrics", dict(self.metrics))

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        snapshot_type: str,
        captured_at: datetime,
        metrics: dict[str, Any],
        id: str | None = None,
    ) -> TrainingMetricSnapshot:
        return cls(
            id=id,
            user_id=user_id,
            snapshot_type=snapshot_type,
            captured_at=captured_at,
            metrics=metrics,
        )


class TrainingLoadService:
    def calculate(
        self,
        *,
        user_id: str,
        anchor_date: date,
        activities: tuple[CompletedActivity, ...],
    ) -> TrainingLoadSummary:
        current_window = MetricWindow(anchor_date - timedelta(days=6), anchor_date)
        previous_window = MetricWindow(anchor_date - timedelta(days=13), anchor_date - timedelta(days=7))
        chronic_window = MetricWindow(anchor_date - timedelta(days=27), anchor_date)
        user_runs = tuple(
            activity
            for activity in activities
            if activity.user_id == user_id and activity.sport_type.lower() in RUN_SPORT_TYPES
        )

        weekly_distance = _sum_distance(user_runs, current_window)
        previous_weekly_distance = _sum_distance(user_runs, previous_window)
        acute_load = _sum_duration_minutes(user_runs, current_window)
        chronic_total = _sum_duration_minutes(user_runs, chronic_window)
        unavailable: list[str] = []

        mileage_ramp = None
        if previous_weekly_distance > 0:
            mileage_ramp = ((weekly_distance - previous_weekly_distance) / previous_weekly_distance) * 100
        else:
            unavailable.append("mileage_ramp_percentage")

        chronic_load = None
        if chronic_total > 0:
            chronic_load = chronic_total / 4
        else:
            unavailable.append("chronic_load")

        acute_chronic_ratio = None
        if chronic_load is not None and chronic_load > 0:
            acute_chronic_ratio = acute_load / chronic_load
        else:
            unavailable.append("acute_chronic_ratio")

        return TrainingLoadSummary(
            user_id=user_id,
            anchor_date=anchor_date,
            weekly_distance_meters=weekly_distance,
            previous_weekly_distance_meters=previous_weekly_distance,
            mileage_ramp_percentage=mileage_ramp,
            acute_load=acute_load,
            chronic_load=chronic_load,
            acute_chronic_ratio=acute_chronic_ratio,
            unavailable_signals=tuple(unavailable),
            evidence={
                "current_window": _window_payload(current_window),
                "previous_window": _window_payload(previous_window),
                "chronic_window": _window_payload(chronic_window),
                "activity_count": len(user_runs),
            },
        )


class RecoveryService:
    def calculate(
        self,
        *,
        user_id: str,
        anchor_date: date,
        health_metrics: tuple[DailyHealthMetrics, ...],
        training_load: TrainingLoadSummary | None,
    ) -> RecoveryContext:
        user_metrics = tuple(metric for metric in health_metrics if metric.user_id == user_id)
        current = next((metric for metric in user_metrics if metric.metric_date == anchor_date), None)
        unavailable: list[str] = []
        evidence: dict[str, Any] = {}
        available_signal_count = 0
        caution_count = 0
        rest_count = 0

        sleep_debt = None
        if current is not None and current.sleep_duration_minutes is not None:
            sleep_debt = SLEEP_TARGET_MINUTES - current.sleep_duration_minutes
            level = _level_for_sleep_debt(sleep_debt)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["sleep"] = {"value": current.sleep_duration_minutes, "target": SLEEP_TARGET_MINUTES, "level": level}
        else:
            unavailable.append("sleep_debt_minutes")

        hrv_delta = None
        if current is not None and current.hrv_ms is not None and current.hrv_baseline_ms is not None:
            hrv_delta = ((current.hrv_ms - current.hrv_baseline_ms) / current.hrv_baseline_ms) * 100
            level = _level_for_hrv_delta(hrv_delta)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["hrv"] = {"value": current.hrv_ms, "baseline": current.hrv_baseline_ms, "level": level}
        else:
            unavailable.append("hrv_delta_percentage")

        rhr_baseline = _resting_heart_rate_baseline(user_metrics, anchor_date)
        rhr_delta = None
        if current is not None and current.resting_heart_rate is not None and rhr_baseline is not None:
            rhr_delta = current.resting_heart_rate - rhr_baseline
            level = _level_for_resting_heart_rate_delta(rhr_delta)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["resting_heart_rate"] = {
                "value": current.resting_heart_rate,
                "baseline": rhr_baseline,
                "level": level,
            }
        else:
            unavailable.append("resting_heart_rate_baseline")

        stress_score = current.stress_score if current is not None else None
        if stress_score is not None:
            level = _level_for_stress(stress_score)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["stress"] = {"value": stress_score, "level": level}

        body_battery_score = current.body_battery_score if current is not None else None
        if body_battery_score is not None:
            level = _level_for_body_battery(body_battery_score)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["body_battery"] = {"value": body_battery_score, "level": level}

        if training_load is not None and training_load.acute_chronic_ratio is not None:
            level = _level_for_acute_chronic_ratio(training_load.acute_chronic_ratio)
            available_signal_count += 1
            caution_count += int(level == "caution")
            rest_count += int(level == "rest")
            evidence["acute_chronic_ratio"] = {"value": training_load.acute_chronic_ratio, "level": level}
        else:
            unavailable.append("acute_chronic_ratio")

        readiness = _readiness_label(available_signal_count, caution_count, rest_count)
        return RecoveryContext(
            user_id=user_id,
            anchor_date=anchor_date,
            readiness_label=readiness,
            sleep_debt_minutes=sleep_debt,
            hrv_delta_percentage=hrv_delta,
            resting_heart_rate_baseline=rhr_baseline,
            resting_heart_rate_delta_bpm=rhr_delta,
            stress_score=stress_score,
            body_battery_score=body_battery_score,
            unavailable_signals=tuple(unavailable),
            evidence=evidence,
        )


def workouts_for_date(plan: TrainingPlan | None, anchor_date: date) -> tuple[Workout, ...]:
    if plan is None:
        return ()
    return tuple(workout for workout in plan.workouts if workout.scheduled_for == anchor_date)


def _sum_distance(activities: tuple[CompletedActivity, ...], window: MetricWindow) -> float:
    return sum(activity.distance_meters for activity in activities if window.contains(activity.started_at.date()))


def _sum_duration_minutes(activities: tuple[CompletedActivity, ...], window: MetricWindow) -> float:
    return sum(activity.duration_seconds / 60 for activity in activities if window.contains(activity.started_at.date()))


def _window_payload(window: MetricWindow) -> dict[str, str]:
    return {"starts_on": window.starts_on.isoformat(), "ends_on": window.ends_on.isoformat()}


def _resting_heart_rate_baseline(metrics: tuple[DailyHealthMetrics, ...], anchor_date: date) -> float | None:
    values = [
        metric.resting_heart_rate
        for metric in metrics
        if metric.metric_date < anchor_date and metric.resting_heart_rate is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _level_for_sleep_debt(sleep_debt: float) -> str:
    if sleep_debt >= 120:
        return "rest"
    if sleep_debt > 0:
        return "caution"
    return "ready"


def _level_for_hrv_delta(delta_percentage: float) -> str:
    if delta_percentage <= -10:
        return "rest"
    if delta_percentage <= -5:
        return "caution"
    return "ready"


def _level_for_resting_heart_rate_delta(delta_bpm: float) -> str:
    if delta_bpm >= 5:
        return "rest"
    if delta_bpm >= 3:
        return "caution"
    return "ready"


def _level_for_stress(stress_score: float) -> str:
    if stress_score >= 70:
        return "rest"
    if stress_score >= 50:
        return "caution"
    return "ready"


def _level_for_body_battery(body_battery_score: float) -> str:
    if body_battery_score <= 25:
        return "rest"
    if body_battery_score <= 50:
        return "caution"
    return "ready"


def _level_for_acute_chronic_ratio(ratio: float) -> str:
    if ratio > 1.5:
        return "rest"
    if ratio > 1.2:
        return "caution"
    return "ready"


def _readiness_label(available_signal_count: int, caution_count: int, rest_count: int) -> str:
    if available_signal_count < 2:
        return "unknown"
    if rest_count > 0 or caution_count >= 2:
        return "rest"
    if caution_count == 1:
        return "caution"
    return "ready"
