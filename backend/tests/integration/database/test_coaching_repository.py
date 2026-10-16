from datetime import date

from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_review_and_advice_publication_are_independent(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="independent@example.com", display_name="Independent")
        uow.session.add(user)
        uow.session.flush()
        store = SqlAlchemyCoachingRepository(uow.session)
        review = store.reserve_review(user.id, date(2026, 10, 16), "Asia/Taipei", "review-run")
        advice = store.reserve_advice(user.id, date(2026, 10, 16), "no-workout", "advice-run", {})
        assert review.workflow_kind == "daily_review"
        assert advice.workflow_kind == "workout_advice"
        assert store.publish_review(review, {"narrative": "R1", "score": 50, "fingerprint": "r1"})
        review_before = store.get_review_slot(user.id, date(2026, 10, 16))
        assert store.publish_advice(advice, {"guidance": "A1", "fingerprint": "a1"}, None)
        assert store.get_review_slot(user.id, date(2026, 10, 16)) == review_before
        assert store.get_advice_slot(user.id, date(2026, 10, 16), "no-workout")["current"]["guidance"] == "A1"
        advice2 = store.reserve_advice(user.id, date(2026, 10, 16), "no-workout", "advice-run-2", {})
        assert store.publish_advice(advice2, {"guidance": "A2", "fingerprint": "a2"}, None)
        assert store.get_review_slot(user.id, date(2026, 10, 16)) == review_before
        review2 = store.reserve_review(user.id, date(2026, 10, 16), "Asia/Taipei", "review-run-2")
        assert store.publish_review(review2, {"narrative": "R2", "score": 75, "fingerprint": "r2"})
        assert store.get_advice_slot(user.id, date(2026, 10, 16), "no-workout")["current"]["guidance"] == "A2"
        assert store.get_review_slot(user.id, date(2026, 10, 16))["current"]["narrative"] == "R2"


def test_stale_or_failed_attempt_preserves_last_success(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="stale@example.com", display_name="Stale")
        uow.session.add(user)
        uow.session.flush()
        store = SqlAlchemyCoachingRepository(uow.session)
        old = store.reserve_review(user.id, date(2026, 10, 16), "UTC", "old")
        fresh = store.reserve_review(user.id, date(2026, 10, 16), "UTC", "fresh")
        assert not store.publish_review(old, {"narrative": "old", "fingerprint": "old"})
        assert store.publish_review(fresh, {"narrative": "fresh", "fingerprint": "fresh"})
        store.mark_attempt_failed(old, "generation_failed", "late_failure")
        slot = store.get_review_slot(user.id, date(2026, 10, 16))
        assert slot["current"]["narrative"] == "fresh"
        assert slot["attempt_state"] == "ready"
        retry = store.reserve_review(user.id, date(2026, 10, 16), "UTC", "retry")
        store.mark_attempt_failed(retry, "generation_failed", "model_failed")
        slot = store.get_review_slot(user.id, date(2026, 10, 16))
        assert slot["current"]["narrative"] == "fresh"
        assert slot["attempt_state"] == "generation_failed"


def test_changed_inputs_block_publication_without_erasing_other_stream(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="input-change@example.com", display_name="Changed")
        uow.session.add(user)
        uow.session.flush()
        store = SqlAlchemyCoachingRepository(uow.session)
        review = store.reserve_review(user.id, date(2026, 10, 16), "UTC", "review")
        assert store.publish_review(review, {"narrative": "R1"})
        advice = store.reserve_advice(user.id, date(2026, 10, 16), "w", "advice", {})
        store.bump_input_version(user.id)
        assert not store.publish_advice(advice, {"guidance": "stale"}, None)
        assert store.get_advice_slot(user.id, date(2026, 10, 16), "w")["current"] is None
        assert store.get_review_slot(user.id, date(2026, 10, 16))["current"]["narrative"] == "R1"
