from datetime import datetime, timezone

import pytest

from src.application.integrations import ConnectSyncProviderCommand, ConnectSyncProviderHandler, ProviderAccountAlreadyConnectedError
from src.domain.integrations_notifications import IntegrationCredential, NotificationDelivery, NotificationIntent, OutboxEvent, SyncSummary
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import ActivityModel, Base, IntegrationConnectionModel, IntegrationResourceCursorModel, UserModel
from src.infrastructure.database.notification_repository import SqlAlchemyNotificationRepository
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork
from src.infrastructure.security.integration_credentials import FernetCredentialCipher


def test_integration_repository_tracks_sync_runs_and_resource_cursors(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="sync@example.com", display_name="Sync Runner")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            credential_secret_ref="file:///Users/example/.johnny/garmin_tokens.json",
            credential_format="garminconnect-token-file",
            capabilities={"activities": True, "health": True},
        )
        run = repository.start_sync_run(connection.id)
        repository.upsert_resource_cursor(
            connection.id,
            "activities",
            {"after_activity_id": "garmin-10"},
        )
        completed = repository.complete_sync_run(
            run.id,
            SyncSummary.empty().record_fetched("activities", 2).record_stored("activities", 1),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyIntegrationRepository(uow.session)
        loaded = repository.get_connection_for_user(user.id, connection.id)
        hidden = repository.get_connection_for_user("other-user", connection.id)
        cursor = repository.get_resource_cursor(connection.id, "activities")

        assert loaded is not None
        assert loaded.credential_secret_ref == "file:///Users/example/.johnny/garmin_tokens.json"
        assert loaded.to_safe_summary()["capabilities"] == {"activities": True, "health": True}
        assert hidden is None
        assert cursor == {"after_activity_id": "garmin-10"}
        assert completed.status == "succeeded"
        assert completed.summary.to_payload()["resources"]["activities"]["stored"] == 1


def test_integration_repository_failed_sync_records_safe_error(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="failed-sync@example.com", display_name="Failed Sync")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        connection = repository.create_connection(user_id=user.id, provider="garmin_connect", provider_account_id="acct-2")
        run = repository.start_sync_run(connection.id)
        failed = repository.fail_sync_run(run.id, "token=abc123 expired")
        uow.commit()

        assert failed.status == "failed"
        assert failed.summary.to_payload()["resources"]["sync"]["errors"] == ["credential or token details redacted"]


def test_integration_repository_records_reauth_and_failed_sync_summary(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="reauth-sync@example.com", display_name="Reauth Sync")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        connection = repository.create_connection(user_id=user.id, provider="garmin_connect", provider_account_id="acct-reauth")
        run = repository.start_sync_run(connection.id)
        summary = SyncSummary.empty().record_failed("activities", "Garmin rate limit exceeded", backoff={"retry_after_seconds": 900})
        completed = repository.complete_sync_run(run.id, summary, status="failed")
        marked = repository.mark_connection_requires_reauth(connection.id, "cookie=session-secret expired")
        uow.commit()

        assert completed.status == "failed"
        assert completed.summary.to_payload()["resources"]["activities"]["backoff"] == {"retry_after_seconds": 900}
        assert marked.credential_status == "requires_reauth"

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyIntegrationRepository(uow.session)
        loaded = repository.get_connection_for_user(user.id, connection.id)
        connection_model = uow.session.get(IntegrationConnectionModel, connection.id)

        assert loaded is not None
        assert loaded.credential_status == "requires_reauth"
        assert connection_model.sync_status == "failed"
        assert connection_model.last_sync_started_at is not None
        assert connection_model.last_sync_completed_at is not None
        assert connection_model.last_sync_error == "credential or token details redacted"


def test_integration_repository_stores_encrypted_credentials_separately_from_connection_metadata(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        cipher = FernetCredentialCipher(
            key="KK5cvF9bgFob_Z3qH2gsXU_EJKeRko3W6lJFaw6mSXE=",
            key_id="local-fernet",
        )
        user = UserModel(email="credential-owner@example.com", display_name="Credential Owner")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-credential",
            credential_format="garminconnect-session-json",
        )
        saved = repository.upsert_credential(
            IntegrationCredential.create(
                connection_id=connection.id,
                credential_format="garminconnect-session-json",
                encrypted_payload=cipher.encrypt('{"oauth2_token":"secret-token"}'),
                key_id=cipher.key_id,
                lifecycle_metadata={"region": "global", "display_name": "Garmin Runner", "email": "runner@example.com"},
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyIntegrationRepository(uow.session)
        loaded = repository.get_credential_for_connection(connection.id)
        connection_model = uow.session.get(IntegrationConnectionModel, connection.id)

        assert saved.id is not None
        assert loaded is not None
        assert loaded.connection_id == connection.id
        assert cipher.decrypt(loaded.encrypted_payload) == '{"oauth2_token":"secret-token"}'
        assert loaded.to_safe_summary() == {
            "connection_id": connection.id,
            "credential_format": "garminconnect-session-json",
            "key_id": "local-fernet",
            "lifecycle_metadata": {"region": "global", "display_name": "Garmin Runner"},
        }
        assert connection_model.credential_secret_ref is None
        assert connection_model.provider_metadata == {}


def test_sync_connection_lifecycle_replaces_reactivates_resets_cursors_and_preserves_history(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="owner@example.com", display_name="Owner")
        other = UserModel(email="other@example.com", display_name="Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        handler = ConnectSyncProviderHandler(integrations=repository)

        garmin = handler.handle(
            ConnectSyncProviderCommand(
                user_id=owner.id,
                provider="garmin_connect",
                provider_account_id="garmin-account-1",
            )
        )
        repository.upsert_resource_cursor(garmin.id, "sync", {"after": "garmin-10"})
        historical_activity = ActivityModel(
            user_id=owner.id,
            provider_connection_id=garmin.id,
            provider_activity_id="garmin-activity-1",
            started_at=datetime(2027, 1, 1, 7, tzinfo=timezone.utc),
            activity_type="running",
            distance_meters=5000,
            duration_seconds=1500,
            provider_summary={"source": "garmin_connect"},
        )
        uow.session.add(historical_activity)
        uow.session.flush()

        coros = handler.handle(
            ConnectSyncProviderCommand(user_id=owner.id, provider="coros", provider_account_id="coros-account-1")
        )
        reactivated = handler.handle(
            ConnectSyncProviderCommand(
                user_id=owner.id,
                provider="garmin_connect",
                provider_account_id="garmin-account-1",
            )
        )
        with pytest.raises(ProviderAccountAlreadyConnectedError):
            handler.handle(
                ConnectSyncProviderCommand(
                    user_id=other.id,
                    provider="garmin_connect",
                    provider_account_id="garmin-account-1",
                )
            )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        garmin_model = uow.session.get(IntegrationConnectionModel, garmin.id)
        coros_model = uow.session.get(IntegrationConnectionModel, coros.id)
        cursor = uow.session.query(IntegrationResourceCursorModel).filter_by(integration_connection_id=garmin.id).one()
        activity = uow.session.get(ActivityModel, historical_activity.id)

        assert reactivated.id == garmin.id
        assert garmin_model.status == "active"
        assert coros_model.status == "replaced"
        assert cursor.cursor_value == {}
        assert cursor.status == "stale"
        assert activity.provider_connection_id == garmin.id


def test_outbox_repository_creates_activity_ingested_events_and_pages_pending(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyOutboxRepository(uow.session)
        first = repository.create_event(
            OutboxEvent.activity_ingested(
                user_id="user-1",
                activity_id="activity-1",
                provider_connection_id="conn-1",
                source_activity_id="garmin-1",
            )
        )
        second = repository.create_event(
            OutboxEvent.activity_ingested(
                user_id="user-1",
                activity_id="activity-2",
                provider_connection_id="conn-1",
                source_activity_id="garmin-2",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        pending = SqlAlchemyOutboxRepository(uow.session).list_pending_events(limit=1, offset=1)

        assert [event.id for event in pending] == [second.id]
        assert pending[0].topic == "ActivityIngested"
        assert first.status == "pending"


def test_notification_repository_records_intents_deliveries_and_retry_state_by_tenant(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="notify@example.com", display_name="Notify Runner")
        other = UserModel(email="other-notify@example.com", display_name="Other Notify")
        uow.session.add_all([user, other])
        uow.session.flush()
        repository = SqlAlchemyNotificationRepository(uow.session)
        intent = repository.create_intent(
            NotificationIntent.recommendation(
                user_id=user.id,
                recommendation_id=None,
                channel="line",
                scheduled_for=datetime(2027, 1, 1, 9, tzinfo=timezone.utc),
                payload={"message": "Review recommendation", "approval_url": "https://johnny.example/recommendations/rec-1"},
            )
        )
        repository.record_delivery(
            NotificationDelivery(
                notification_intent_id=intent.id,
                status="failed",
                provider="line",
                provider_message_id=None,
                attempted_at=datetime(2027, 1, 1, 9, 1, tzinfo=timezone.utc),
                response={"status_code": 500, "retryable": True},
            )
        )
        retryable = repository.mark_intent_retryable(intent.id)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyNotificationRepository(uow.session)
        loaded = repository.get_intent_for_user(user.id, intent.id)
        hidden = repository.get_intent_for_user(other.id, intent.id)
        deliveries = repository.list_deliveries_for_intent(intent.id, limit=10, offset=0)

        assert retryable.status == "retryable"
        assert loaded is not None
        assert loaded.status == "retryable"
        assert hidden is None
        assert len(deliveries) == 1
        assert deliveries[0].response["retryable"] is True
