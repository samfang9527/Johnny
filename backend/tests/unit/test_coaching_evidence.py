from datetime import date, datetime, timezone

from src.application.coaching_evidence import build_review_evidence
from src.domain.activity_health import CompletedActivity
from src.domain.training_plan import Workout
from src.domain.training_review import PrescriptionSnapshot, review_period


def test_evidence_filters_by_athlete_local_start_date_and_cutoff() -> None:
    period = review_period(date(2026, 10, 16))
    recorded = CompletedActivity.create(id="local-15", user_id="athlete", source="manual",
        started_at=datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc),
        sport_type="running", duration_seconds=2400, distance_meters=6000)
    future = CompletedActivity.create(id="future", user_id="athlete", source="manual",
        started_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
        sport_type="running", duration_seconds=2400, distance_meters=6000)
    item = Workout.create(id="w", scheduled_for=date(2026, 10, 15), workout_type="easy_run",
                          purpose="Training", planned_duration_minutes=40)
    snapshot = PrescriptionSnapshot("athlete", "plan", "w", item,
        datetime(2026, 10, 1, tzinfo=timezone.utc), "generation", "known")

    class Store:
        activity_starts = None
        def list_review_activities(self, user_id, starts_on, ends_on):
            assert (starts_on, ends_on) == (date(2026, 10, 8), date(2026, 10, 16))
            return (recorded, future)
        def list_prescriptions(self, user_id, starts_on, ends_on, timezone_name, activity_starts):
            self.activity_starts = activity_starts
            return (snapshot,)
        def covered_review_dates(self, user_id, starts_on, ends_on, timezone_name, as_of):
            return frozenset({date(2026, 10, 15)})

    store = Store()
    result = build_review_evidence(user_id="athlete", period=period, timezone_name="Asia/Taipei",
                                   as_of=datetime(2026, 10, 15, 20, tzinfo=timezone.utc), store=store)
    assert [a.id for s in result.sessions for a in s.activities] == ["local-15"]
    assert result.sessions[0].local_date == date(2026, 10, 15)
    assert result.covered_dates == frozenset({date(2026, 10, 15)})
