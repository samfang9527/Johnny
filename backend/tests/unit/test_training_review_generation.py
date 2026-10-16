from datetime import date, datetime, timezone

from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.domain.training_review import review_period


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
