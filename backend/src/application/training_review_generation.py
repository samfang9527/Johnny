"""Publish a retrospective review from committed, closed-day training evidence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Callable

from src.application.coaching_evidence import build_review_evidence
from src.domain.execution_score import score_execution
from src.domain.training_review import review_period


class GenerateTrainingReviewHandler:
    def __init__(self, *, coaching, evidence, now: Callable[[], datetime] | None = None) -> None:
        self._coaching = coaching
        self._evidence = evidence
        self._now = now or (lambda: datetime.now(timezone.utc))

    def handle(self, *, user_id: str, publication_date: date, timezone_name: str,
               run_id: str) -> dict:
        reservation = self._coaching.reserve_review(user_id, publication_date, timezone_name, run_id)
        period = review_period(publication_date)
        evidence = build_review_evidence(user_id=user_id, period=period,
            timezone_name=timezone_name, as_of=self._now(), store=self._evidence)
        score = score_execution(evidence)
        week_rows = []
        for snapshot in evidence.prescriptions:
            workout = snapshot.workout
            matched = tuple(session for session in evidence.sessions if session.workout_id == snapshot.workout_id)
            if workout.status == "skipped" and snapshot.source == "approved_adjustment":
                state = "approved_skip"
            elif matched:
                state = "completed"
            elif snapshot.confidence != "known":
                state = "uncertain_prescription"
            elif any(session.local_date == workout.scheduled_for and session.status == "needs_review"
                     for session in evidence.sessions):
                state = "needs_pairing"
            elif workout.scheduled_for not in evidence.covered_dates:
                state = "unknown_coverage"
            else:
                state = "missed"
            week_rows.append({"workout_id": snapshot.workout_id,
                "scheduled_for": workout.scheduled_for.isoformat(),
                "workout_type": workout.workout_type, "planned_duration_minutes": workout.planned_duration_minutes,
                "planned_distance_meters": workout.planned_distance_meters,
                "actual_duration_seconds": sum(item.duration_seconds for item in matched),
                "actual_distance_meters": sum(item.distance_meters for item in matched),
                "state": state})
        yesterday = [item for item in week_rows if item["scheduled_for"] == period.reviewed_date.isoformat()]
        if yesterday:
            completed_yesterday = sum(item["state"] == "completed" for item in yesterday)
            unknown_yesterday = sum(item["state"] in {
                "needs_pairing", "unknown_coverage", "uncertain_prescription"} for item in yesterday)
            if unknown_yesterday:
                yesterday_summary = "昨天有課表尚未能可靠判定，請確認活動同步與配對。"
            elif completed_yesterday:
                yesterday_summary = f"昨天完成 {completed_yesterday} 堂排定課表。"
            elif all(item["state"] == "approved_skip" for item in yesterday):
                yesterday_summary = "昨天依照已同意的調整略過課表。"
            else:
                yesterday_summary = "昨天有排定課表未完成。"
        else:
            extra_yesterday = sum(session.local_date == period.reviewed_date
                                  for session in evidence.sessions)
            yesterday_summary = (f"昨天有 {extra_yesterday} 組跑步活動，沒有排定課表。"
                                 if extra_yesterday else "昨天沒有已排定的跑步課表。")
        if score.reason == "no_prescribed_sessions":
            narrative = f"{yesterday_summary} 過去七天沒有可評分的跑步課表。"
        elif score.value is None:
            narrative = f"{yesterday_summary} 資料尚不足以可靠計算七日執行分數，請確認同步與活動配對。"
        else:
            narrative = (f"{yesterday_summary} 過去七天課表執行分數 {score.value} 分；"
                         f"完成 {score.completed_count} 堂、確認未完成 {score.missed_count} 堂。")
        result = {
            "kind": "daily_review", "publication_date": publication_date.isoformat(),
            "reviewed_date": period.reviewed_date.isoformat(),
            "starts_on": period.starts_on.isoformat(), "ends_on": period.ends_on.isoformat(),
            "timezone_name": timezone_name, "generated_at": self._now().isoformat(),
            "score": asdict(score), "yesterday": yesterday, "week": week_rows,
            "narrative": narrative,
            "coverage": {"covered_dates": [day.isoformat() for day in sorted(evidence.covered_dates)],
                         "cutoff_at": evidence.cutoff_at.isoformat()},
        }
        if not self._coaching.publish_review(reservation, result):
            raise ValueError("review inputs changed or a newer generation owns this date")
        return result
