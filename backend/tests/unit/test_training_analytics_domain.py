from datetime import date, datetime, timezone

import pytest

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.training_analytics import (
    RecoveryService,
    TrainingLoadService,
)


ANCHOR = date(2027, 1, 28)


def _activity(
    *,
    user_id: str = "user-1",
    activity_date: date = ANCHOR,
    sport_type: str = "run",
    distance_meters: float = 10_000,
    duration_seconds: int = 3_600,
) -> CompletedActivity:
    return CompletedActivity.create(
        user_id=user_id,
        source="manual",
        started_at=datetime(activity_date.year, activity_date.month, activity_date.day, 7, 30, tzinfo=timezone.utc),
        sport_type=sport_type,
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
    )


def _health(
    *,
    user_id: str = "user-1",
    metric_date: date = ANCHOR,
    sleep_duration_minutes: float | None = None,
    hrv_ms: float | None = None,
    hrv_baseline_ms: float | None = None,
    resting_heart_rate: float | None = None,
    stress_score: float | None = None,
    body_battery_score: float | None = None,
) -> DailyHealthMetrics:
    return DailyHealthMetrics.create(
        user_id=user_id,
        metric_date=metric_date,
        sleep_duration_minutes=sleep_duration_minutes,
        hrv_ms=hrv_ms,
        hrv_baseline_ms=hrv_baseline_ms,
        resting_heart_rate=resting_heart_rate,
        stress_score=stress_score,
        body_battery_score=body_battery_score,
    )


def test_training_load_uses_explicit_windows_and_excludes_other_users() -> None:
    summary = TrainingLoadService().calculate(
        user_id="user-1",
        anchor_date=ANCHOR,
        activities=(
            _activity(activity_date=date(2027, 1, 28), distance_meters=10_000, duration_seconds=3_000),
            _activity(activity_date=date(2027, 1, 24), distance_meters=8_000, duration_seconds=2_400),
            _activity(activity_date=date(2027, 1, 21), distance_meters=6_000, duration_seconds=1_800),
            _activity(activity_date=date(2027, 1, 17), distance_meters=4_000, duration_seconds=1_200),
            _activity(activity_date=date(2027, 1, 3), distance_meters=2_000, duration_seconds=600),
            _activity(user_id="user-2", activity_date=date(2027, 1, 28), distance_meters=99_000),
            _activity(activity_date=date(2027, 1, 28), sport_type="ride", distance_meters=99_000),
        ),
    )

    assert summary.weekly_distance_meters == pytest.approx(18_000)
    assert summary.previous_weekly_distance_meters == pytest.approx(10_000)
    assert summary.mileage_ramp_percentage == pytest.approx(80)
    assert summary.acute_load == pytest.approx(90)
    assert summary.chronic_load == pytest.approx(37.5)
    assert summary.acute_chronic_ratio == pytest.approx(2.4)
    assert summary.unavailable_signals == ()


def test_training_load_marks_ratio_metrics_unavailable_when_denominator_is_zero() -> None:
    summary = TrainingLoadService().calculate(
        user_id="user-1",
        anchor_date=ANCHOR,
        activities=(
            _activity(activity_date=date(2027, 1, 28), distance_meters=5_000, duration_seconds=1_500),
        ),
    )

    assert summary.weekly_distance_meters == pytest.approx(5_000)
    assert summary.previous_weekly_distance_meters == pytest.approx(0)
    assert summary.mileage_ramp_percentage is None
    assert summary.acute_chronic_ratio == pytest.approx(4)
    assert "mileage_ramp_percentage" in summary.unavailable_signals


def test_training_load_marks_chronic_ratio_unavailable_when_no_activity_exists() -> None:
    summary = TrainingLoadService().calculate(user_id="user-1", anchor_date=ANCHOR, activities=())

    assert summary.weekly_distance_meters == pytest.approx(0)
    assert summary.previous_weekly_distance_meters == pytest.approx(0)
    assert summary.acute_load == pytest.approx(0)
    assert summary.chronic_load is None
    assert summary.acute_chronic_ratio is None
    assert set(summary.unavailable_signals) == {"mileage_ramp_percentage", "chronic_load", "acute_chronic_ratio"}


def test_recovery_context_uses_health_deltas_load_evidence_and_thresholds() -> None:
    training_load = TrainingLoadService().calculate(
        user_id="user-1",
        anchor_date=ANCHOR,
        activities=(
            _activity(activity_date=date(2027, 1, 28), duration_seconds=3_600),
            _activity(activity_date=date(2027, 1, 27), duration_seconds=3_600),
        ),
    )
    recovery = RecoveryService().calculate(
        user_id="user-1",
        anchor_date=ANCHOR,
        health_metrics=(
            _health(metric_date=date(2027, 1, 24), resting_heart_rate=48),
            _health(metric_date=date(2027, 1, 25), resting_heart_rate=50),
            _health(
                metric_date=ANCHOR,
                sleep_duration_minutes=420,
                hrv_ms=44,
                hrv_baseline_ms=50,
                resting_heart_rate=54,
                stress_score=72,
                body_battery_score=18,
            ),
        ),
        training_load=training_load,
    )

    assert recovery.sleep_debt_minutes == pytest.approx(60)
    assert recovery.hrv_delta_percentage == pytest.approx(-12)
    assert recovery.resting_heart_rate_baseline == pytest.approx(49)
    assert recovery.resting_heart_rate_delta_bpm == pytest.approx(5)
    assert recovery.readiness_label == "rest"
    assert recovery.unavailable_signals == ()
    assert recovery.evidence["stress"]["level"] == "rest"
    assert recovery.body_battery_score == 18
    assert recovery.evidence["body_battery"] == {"value": 18, "level": "rest"}


def test_recovery_context_marks_missing_signals_and_uses_unknown_label() -> None:
    recovery = RecoveryService().calculate(
        user_id="user-1",
        anchor_date=ANCHOR,
        health_metrics=(
            _health(metric_date=ANCHOR, resting_heart_rate=50),
            _health(user_id="user-2", metric_date=ANCHOR, sleep_duration_minutes=300, hrv_ms=20),
        ),
        training_load=None,
    )

    assert recovery.readiness_label == "unknown"
    assert recovery.sleep_debt_minutes is None
    assert recovery.hrv_delta_percentage is None
    assert recovery.resting_heart_rate_delta_bpm is None
    assert recovery.body_battery_score is None
    assert "body_battery" not in recovery.evidence
    assert set(recovery.unavailable_signals) == {
        "sleep_debt_minutes",
        "hrv_delta_percentage",
        "resting_heart_rate_baseline",
        "acute_chronic_ratio",
    }
