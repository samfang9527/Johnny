from datetime import datetime, timezone

from src.api.dependencies import get_session
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from tests.unit.api_test_helpers import create_sqlite_test_client


def test_overview_keeps_review_and_advice_independent():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "athlete"}
    today = datetime.now(timezone.utc).date()
    assert client.get("/api/v1/johnny/overview", headers=headers).status_code == 200
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review("athlete", today, "UTC", "r1")
    store.publish_review(review, {"narrative": "R1", "score": {"value": 50}})
    advice = store.reserve_advice("athlete", today, "no-workout", "a1", {})
    store.publish_advice(advice, {"guidance": "A1"}, None)
    session.commit()
    first = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert first["daily_review"]["current"]["narrative"] == "R1"
    assert first["workout_advices"][0]["current"]["guidance"] == "A1"
    advice2 = store.reserve_advice("athlete", today, "no-workout", "a2", {})
    store.publish_advice(advice2, {"guidance": "A2"}, None)
    session.commit()
    second = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert second["daily_review"]["current"]["narrative"] == "R1"
    assert second["workout_advices"][0]["current"]["guidance"] == "A2"
    review2 = store.reserve_review("athlete", today, "UTC", "r2")
    store.publish_review(review2, {"narrative": "R2", "score": {"value": 75}})
    session.commit()
    third = client.get("/api/v1/johnny/overview", headers=headers).json()["data"]
    assert third["daily_review"]["current"]["narrative"] == "R2"
    assert third["workout_advices"][0]["current"]["guidance"] == "A2"
    scope.close()


def test_manual_advice_request_is_idempotent_and_never_enqueues_review():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "manual-athlete"}
    body = {"client_request_id": "63e9c25b-1af0-4277-9e6f-710aa3b3fb06",
            "workout_id": None,
            "constraints": {"feeling": "more_tired", "cannot_train_today": False}}
    first = client.post("/api/v1/johnny/workout-advice", headers=headers, json=body)
    assert first.status_code == 202, first.text
    second = client.post("/api/v1/johnny/workout-advice", headers=headers, json=body)
    assert second.status_code == 202
    assert first.json()["data"]["run_id"] == second.json()["data"]["run_id"]
    changed = {**body, "constraints": {"feeling": "usual"}}
    assert client.post("/api/v1/johnny/workout-advice", headers=headers, json=changed).status_code == 409
    assert client.get("/api/v1/johnny/overview", headers=headers).json()["data"]["daily_review"] is None
