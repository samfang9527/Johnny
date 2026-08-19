from importlib import import_module


database_models = import_module("src.infrastructure.database.models")
Base = database_models.Base
OutboxEventModel = database_models.OutboxEventModel


def test_outbox_event_model_defaults(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    session = sqlite_session_factory()
    try:
        event = OutboxEventModel(topic="sync.requested")
        session.add(event)
        session.flush()

        assert event.status == "pending"
        assert event.payload == {}
        assert event.created_at is not None
    finally:
        session.close()
