"""Bounded, explainable transformations for an athlete-requested workout decision."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.domain.running import RUNNING_WORKOUT_TYPES
from src.domain.training_plan import Workout


POLICY_VERSION = "adjustment-v1"


@dataclass(frozen=True)
class WorkoutAdviceConstraints:
    available_minutes: int | None = None
    feeling: str = "usual"
    cannot_train_today: bool = False

    def __post_init__(self) -> None:
        if self.available_minutes is not None and (not isinstance(self.available_minutes, int)
                or isinstance(self.available_minutes, bool) or not 1 <= self.available_minutes <= 600):
            raise ValueError("available_minutes must be an integer from 1 to 600")
        if self.feeling not in {"usual", "more_tired"}:
            raise ValueError("feeling must be usual or more_tired")
        if self.cannot_train_today and self.available_minutes is not None:
            raise ValueError("cannot_train_today cannot be combined with available_minutes")


@dataclass(frozen=True)
class AdviceEvidence:
    timezone_name: str
    matched_today: bool = False
    unresolved_today: bool = False
    recovery_label: str | None = None
    recovery_observed_date: date | None = None
    activity_sync_usable: bool = False


@dataclass(frozen=True)
class AdviceDecision:
    mode: str
    reason_code: str
    guidance: str
    after_workout: Workout | None = None
    policy_version: str = POLICY_VERSION


def assess_workout_advice(*, workout: Workout | None, evidence: AdviceEvidence,
                          constraints: WorkoutAdviceConstraints, now: datetime) -> AdviceDecision:
    today = now.astimezone(ZoneInfo(evidence.timezone_name)).date()
    if workout is None:
        return AdviceDecision("no_supported_adjustment", "no_workout", "今天沒有需要調整的跑步課表。")
    if workout.scheduled_for != today:
        return AdviceDecision("no_supported_adjustment", "request_date_expired", "這份課表已不是今天的課表，請重新取得建議。")
    if workout.status in {"completed", "skipped"} or evidence.matched_today:
        return AdviceDecision("no_supported_adjustment", "already_completed", "今天已有完成紀錄，請以恢復為主。")
    if evidence.unresolved_today:
        return AdviceDecision("no_supported_adjustment", "needs_pairing", "今天有尚未配對的活動，請先確認活動與課表的關係。")
    if workout.workout_type not in RUNNING_WORKOUT_TYPES or workout.workout_type == "race":
        return AdviceDecision("no_supported_adjustment", "unsupported_workout", "這類課表目前不提供自動調整，請依身體狀態保守執行。")
    if not evidence.activity_sync_usable:
        return AdviceDecision("no_supported_adjustment", "activity_sync_unavailable", "活動同步尚未完成，暫不提出可套用的課表調整。")
    if constraints.cannot_train_today:
        return AdviceDecision("propose_skip_today", "athlete_cannot_train", "如果今天無法訓練，可以略過本堂課，不必補做。",
                              replace(workout, status="skipped"))
    if evidence.recovery_label == "rest" and evidence.recovery_observed_date == today:
        return AdviceDecision("propose_skip_today", "same_day_recovery_rest", "今天的恢復資料建議休息，可以略過本堂課。",
                              replace(workout, status="skipped"))
    if constraints.available_minutes is not None and workout.planned_duration_minutes is not None \
            and constraints.available_minutes < workout.planned_duration_minutes:
        if (workout.workout_type == "easy_run" and len(workout.steps) == 1
                and workout.steps[0].step_type == "free_run"
                and workout.steps[0].duration_seconds is not None):
            step = replace(workout.steps[0], duration_seconds=constraints.available_minutes * 60)
            updated = replace(workout, planned_duration_minutes=constraints.available_minutes,
                              planned_distance_meters=None, steps=(step,), status="adjusted")
            return AdviceDecision("propose_shorten_easy_run", "less_available_time",
                                  "可將今天的輕鬆跑縮短到可用時間；原課表要等你接受後才會更新。", updated)
        return AdviceDecision("no_supported_adjustment", "unsupported_structure",
                              "這堂課有較複雜的結構，暫不自動改寫；若時間不足，請保守處理。")
    if constraints.feeling == "more_tired":
        return AdviceDecision("no_supported_adjustment", "more_tired",
                              "今天感到較疲倦，請放慢並留意身體狀態；目前沒有可靠的數值調整建議。")
    return AdviceDecision("no_supported_adjustment", "follow_plan",
                          "目前可照原課表保守執行，留意身體感受。")
