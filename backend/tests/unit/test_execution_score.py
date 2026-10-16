from datetime import date, datetime, timezone

from src.domain.activity_health import CompletedActivity
from src.domain.activity_sessions import match_sessions
from src.domain.execution_score import score_execution
from src.domain.training_plan import Workout
from src.domain.training_review import PrescriptionSnapshot, ReviewEvidence, review_period


PERIOD = review_period(date(2026, 10, 16))


def workout(identity: str, minutes: int = 40, *, kind: str = "easy_run") -> PrescriptionSnapshot:
    item = Workout.create(id=identity, scheduled_for=date(2026, 10, 15), workout_type=kind,
                          purpose="Training", planned_duration_minutes=minutes)
    return PrescriptionSnapshot("athlete", "plan", identity, item,
                                datetime(2026, 10, 1, tzinfo=timezone.utc), "generation", "known")


def activity(identity: str, minutes: int, workout_id: str | None) -> CompletedActivity:
    return CompletedActivity.create(id=identity, user_id="athlete", source="manual",
                                    started_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                    sport_type="running", duration_seconds=minutes * 60,
                                    distance_meters=6000, matched_workout_id=workout_id,
                                    match_reviewed=True)


def evidence(prescriptions, activities=(), *, covered=True):
    sessions = match_sessions(tuple(activities), tuple(p.workout for p in prescriptions), "UTC")
    return ReviewEvidence(PERIOD, "UTC", datetime(2026, 10, 16, tzinfo=timezone.utc),
                          tuple(prescriptions), sessions,
                          frozenset(PERIOD.starts_on.fromordinal(day) for day in range(PERIOD.starts_on.toordinal(), PERIOD.ends_on.toordinal()+1)) if covered else frozenset())


def test_execution_scores_exact_missed_and_overlong() -> None:
    first = workout("one")
    assert score_execution(evidence((first,), (activity("a", 40, "one"),))).value == 100
    second = workout("two")
    scored = score_execution(evidence((first, second), (activity("a", 40, "one"),)))
    assert (scored.value, scored.completed_count, scored.missed_count) == (50, 1, 1)
    assert score_execution(evidence((first,), (activity("a", 60, "one"),))).value == 83


def test_unknown_coverage_and_ambiguous_pairing_withhold_score() -> None:
    planned = workout("one")
    assert score_execution(evidence((planned,), covered=False)).reason == "incomplete_activity_coverage"
    pending = CompletedActivity.create(id="pending", user_id="athlete", source="manual",
                                       started_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                       sport_type="running", duration_seconds=2400, distance_meters=6000)
    ambiguous = evidence((planned, workout("two")), (pending,))
    assert score_execution(ambiguous).reason == "ambiguous_pairing"


def test_rest_week_has_no_denominator_and_extra_does_not_fill_missing() -> None:
    assert score_execution(evidence(())).reason == "no_prescribed_sessions"
    planned = workout("one", 30)
    extra = activity("extra", 60, None)
    scored = score_execution(evidence((planned,), (extra,)))
    assert scored.value == 0
    assert scored.extra_count == 1


def test_uncertain_legacy_and_uncomparable_workout_are_unscorable() -> None:
    item = workout("one")
    uncertain = PrescriptionSnapshot(item.user_id, item.plan_id, item.workout_id, item.workout,
                                     item.effective_at, item.source, "legacy_uncertain")
    assert score_execution(evidence((uncertain,))).reason == "uncertain_prescription"
    distance_only = Workout.create(id="distance", scheduled_for=date(2026, 10, 15), workout_type="race",
                                   purpose="Race", planned_distance_meters=10000,
                                   race_goal_id="goal", race_name="10K", race_priority="primary")
    unknown = PrescriptionSnapshot("athlete", "plan", "distance", distance_only,
                                   item.effective_at, "generation", "known")
    recording = CompletedActivity.create(id="distance-unknown", user_id="athlete", source="manual",
                                         started_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                         sport_type="running", duration_seconds=2400, distance_meters=0,
                                         matched_workout_id="distance", match_reviewed=True)
    assert score_execution(evidence((unknown,), (recording,))).reason == "missing_comparison_metric"
