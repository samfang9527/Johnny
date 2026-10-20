from datetime import date, datetime, timezone

from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.domain.training_review import review_period
from src.domain.activity_health import CompletedActivity
from src.domain.agent_runtime import ModelResponse
from src.domain.training_plan import Workout
from src.domain.training_review import PrescriptionSnapshot


def test_daily_review_uses_closed_dates_and_never_creates_proposal() -> None:
    class Store:
        def __init__(self):
            self.published = None
        def reserve_review(self, user_id, publication_date, timezone_name, run_id):
            return type("Reservation", (), {"user_id": user_id, "workflow_kind": "daily_review",
                "run_id": run_id})()
        def publish_review(self, reservation, payload):
            self.published = payload
            return True
    class EvidenceStore:
        def list_review_activities(self, *args): return ()
        def list_prescriptions(self, *args): return ()
        def covered_review_dates(self, *args): return frozenset()
    store = Store()
    result = GenerateTrainingReviewHandler(coaching=store, evidence=EvidenceStore(),
        now=lambda: datetime(2026, 10, 16, 1, tzinfo=timezone.utc)).handle(
        user_id="athlete", publication_date=date(2026, 10, 16),
        timezone_name="Asia/Taipei", run_id="run-1")
    assert result["reviewed_date"] == "2026-10-15"
    assert result["starts_on"] == "2026-10-09"
    assert result["ends_on"] == "2026-10-15"
    assert result["score"]["value"] is None
    assert "proposal" not in result
    assert store.published == result


def test_review_explains_matched_execution_when_week_score_is_withheld() -> None:
    day = date(2026, 10, 15)
    workout = Workout.create(id="w1", scheduled_for=day, workout_type="easy_run",
                             purpose="輕鬆有氧", planned_duration_minutes=40)
    snapshot = PrescriptionSnapshot("athlete", "plan", "w1", workout,
                                    datetime(2026, 10, 1, tzinfo=timezone.utc),
                                    "generation", "known")
    activity = CompletedActivity.create(id="a1", user_id="athlete", source="manual",
                                        started_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                        sport_type="running", duration_seconds=3000,
                                        distance_meters=7000, matched_workout_id="w1",
                                        match_reviewed=True)

    class Store:
        def reserve_review(self, *args): return object()
        def publish_review(self, *args): return True
        def list_review_activities(self, *args): return (activity,)
        def list_prescriptions(self, *args): return (snapshot,)
        def covered_review_dates(self, *args): return frozenset()

    result = GenerateTrainingReviewHandler(coaching=Store(), evidence=Store(),
        now=lambda: datetime(2026, 10, 16, 1, tzinfo=timezone.utc)).handle(
            user_id="athlete", publication_date=date(2026, 10, 16),
            timezone_name="Asia/Taipei", run_id="run-1")
    assert result["score"]["value"] is None
    assert "40 分鐘" in result["narrative"]
    assert "50 分鐘" in result["narrative"]
    assert "多 10 分鐘" in result["narrative"]


def test_review_model_can_interpret_execution_without_changing_score() -> None:
    day = date(2026, 10, 15)
    workout = Workout.create(id="w1", scheduled_for=day, workout_type="easy_run",
                             purpose="輕鬆有氧", planned_duration_minutes=40)
    snapshot = PrescriptionSnapshot("athlete", "plan", "w1", workout,
                                    datetime(2026, 10, 1, tzinfo=timezone.utc),
                                    "generation", "known")
    activity = CompletedActivity.create(id="a1", user_id="athlete", source="manual",
                                        started_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
                                        sport_type="running", duration_seconds=3000,
                                        distance_meters=7000, matched_workout_id="w1",
                                        match_reviewed=True)

    class Store:
        def reserve_review(self, *args): return object()
        def publish_review(self, *args): return True
        def list_review_activities(self, *args): return (activity,)
        def list_prescriptions(self, *args): return (snapshot,)
        def covered_review_dates(self, *args): return frozenset()

    class Gateway:
        def complete(self, request):
            assert request.context["yesterday"][0]["purpose"] == "輕鬆有氧"
            assert request.context["yesterday"][0]["actual_duration_seconds"] == 3000
            return ModelResponse(content="實際時間比原定稍長，可留意是否仍維持輕鬆感。")

    result = GenerateTrainingReviewHandler(coaching=Store(), evidence=Store(), gateway=Gateway(),
        now=lambda: datetime(2026, 10, 16, 1, tzinfo=timezone.utc)).handle(
            user_id="athlete", publication_date=date(2026, 10, 16),
            timezone_name="Asia/Taipei", run_id="run-1")
    assert "實際時間比原定稍長" in result["narrative"]
    assert "40 分鐘" in result["narrative"]
    assert result["score"]["value"] is None
