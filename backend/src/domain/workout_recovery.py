"""Dated recovery evidence for requested workout advice; never blend observation dates."""

from __future__ import annotations

from datetime import date, timedelta

from src.domain.activity_health import DailyHealthMetrics
from src.domain.training_analytics import RecoveryService


SIGNAL_LABELS = {"sleep": "睡眠", "hrv": "HRV", "stress": "壓力", "body_battery": "Body Battery"}
RECOVERY_POLICY_VERSION = "workout-recovery-v1"


def build_workout_recovery(*, user_id: str, advice_date: date,
                           health_metrics: tuple[DailyHealthMetrics, ...]) -> dict:
    """Use provider calendar dates, which are already athlete-local daily buckets.

    Reuse RecoveryService thresholds for the four requested signals. Fewer than
    two usable current-day signals remain unknown rather than inheriting yesterday's
    readiness. Yesterday is a fallback only when today's daily record is absent.
    """
    days = []
    observed = None
    for day in (advice_date - timedelta(days=1), advice_date):
        metric = next((item for item in health_metrics
                       if item.user_id == user_id and item.metric_date == day), None)
        inputs = ()
        if metric is not None:
            values = {name: value for name, value in metric.values_by_metric_type().items()
                      if name in {"sleep_duration_minutes", "hrv_ms", "hrv_baseline_ms",
                                  "stress_score", "body_battery_score"}}
            # A zero HRV baseline is missing evidence, not a ratio denominator.
            if values.get("hrv_baseline_ms") == 0:
                del values["hrv_baseline_ms"]
            if values:
                inputs = (DailyHealthMetrics.create(user_id=user_id, metric_date=day,
                                                     source=metric.source, **values),)
        assessment = RecoveryService().calculate(user_id=user_id, anchor_date=day,
                                                 health_metrics=inputs, training_load=None)
        signals = assessment.evidence or {}
        row = {
            "date": day.isoformat(), "readiness_label": assessment.readiness_label,
            "signals": signals,
            "missing_signals": [name for name in SIGNAL_LABELS if name not in signals],
        }
        days.append(row)
        if metric is not None:
            observed = row
    return {
        "policy_version": RECOVERY_POLICY_VERSION,
        "observed_date": observed["date"] if observed else None,
        "readiness_label": observed["readiness_label"] if observed else "unknown",
        "days": days,
    }


def recovery_guidance(recovery: dict) -> str:
    descriptions = []
    for day in recovery["days"]:
        signals = day["signals"]
        parts = []
        if "sleep" in signals:
            parts.append(f"睡眠 {signals['sleep']['value']:g} 分鐘")
        if "hrv" in signals:
            parts.append(f"HRV {signals['hrv']['value']:g} ms（基準 {signals['hrv']['baseline']:g} ms）")
        if "stress" in signals:
            parts.append(f"壓力 {signals['stress']['value']:g}")
        if "body_battery" in signals:
            parts.append(f"Body Battery {signals['body_battery']['value']:g}")
        if day["missing_signals"]:
            parts.append("缺少" + "、".join(SIGNAL_LABELS[name] for name in day["missing_signals"]))
        descriptions.append(f"{day['date']}：" + "、".join(parts))
    return "恢復參考（依資料日期）：" + "；".join(descriptions) + "。"
