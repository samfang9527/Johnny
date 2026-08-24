import pytest

from src.application.integrations import (
    AdminImportGarminTokenCommand,
    AdminImportGarminTokenHandler,
    ConnectGarminAccountCommand,
    ConnectGarminAccountHandler,
    DisconnectGarminConnectionCommand,
    DisconnectGarminConnectionHandler,
    GarminAccountProfile,
    ProviderAccountAlreadyConnectedError,
)
from src.domain.integrations_notifications import IntegrationConnectionRef, IntegrationCredential


def test_garmin_connect_discovers_account_stores_encrypted_session_and_discards_password() -> None:
    integrations = _FakeIntegrationStore()
    credentials = _FakeCredentialStore()
    garmin = _FakeGarminLoginAdapter(
        GarminAccountProfile(
            provider_account_id="garmin-account-1",
            display_name="Garmin Runner",
            session_payload='{"oauth2_token":"secret-token"}',
        )
    )
    cipher = _FakeCipher()

    connection = ConnectGarminAccountHandler(
        integrations=integrations,
        credentials=credentials,
        garmin=garmin,
        cipher=cipher,
    ).handle(
        ConnectGarminAccountCommand(
            user_id="user-1",
            email="runner@example.com",
            password="garmin-password",
            region="global",
        )
    )

    assert connection.provider == "garmin_connect"
    assert connection.provider_account_id == "garmin-account-1"
    assert connection.provider_display_name == "Garmin Runner"
    assert connection.credential_secret_ref is None
    assert connection.credential_format == "garminconnect-session-json"
    assert garmin.calls == [
        {"email": "runner@example.com", "password": "garmin-password", "region": "global"},
    ]
    assert credentials.saved is not None
    assert credentials.saved.connection_id == connection.id
    assert credentials.saved.encrypted_payload == "fernet:encrypted-session"
    assert credentials.saved.lifecycle_metadata == {"region": "global", "display_name": "Garmin Runner"}
    assert "garmin-password" not in repr(connection)
    assert "runner@example.com" not in repr(connection)


def test_garmin_connect_reactivates_same_user_and_rejects_cross_user_account() -> None:
    integrations = _FakeIntegrationStore()
    credentials = _FakeCredentialStore()
    handler = ConnectGarminAccountHandler(
        integrations=integrations,
        credentials=credentials,
        garmin=_FakeGarminLoginAdapter(
            GarminAccountProfile(
                provider_account_id="garmin-account-1",
                display_name="Garmin Runner",
                session_payload="session-json",
            )
        ),
        cipher=_FakeCipher(),
    )

    first = handler.handle(
        ConnectGarminAccountCommand(
            user_id="user-1",
            email="runner@example.com",
            password="first-password",
            region="global",
        )
    )
    reconnected = handler.handle(
        ConnectGarminAccountCommand(
            user_id="user-1",
            email="runner@example.com",
            password="new-password",
            region="china",
        )
    )
    with pytest.raises(ProviderAccountAlreadyConnectedError):
        handler.handle(
            ConnectGarminAccountCommand(
                user_id="user-2",
                email="other@example.com",
                password="other-password",
                region="global",
            )
        )

    assert reconnected.id == first.id
    assert integrations.reset_cursor_ids == [first.id]
    assert credentials.saved is not None
    assert credentials.saved.connection_id == first.id
    assert credentials.saved.lifecycle_metadata["region"] == "china"


def test_garmin_disconnect_marks_connection_disconnected() -> None:
    integrations = _FakeIntegrationStore()
    connection = integrations.create_connection(
        user_id="user-1",
        provider="garmin_connect",
        provider_account_id="garmin-account-1",
        credential_format="garminconnect-session-json",
    )

    disconnected = DisconnectGarminConnectionHandler(integrations=integrations).handle(
        DisconnectGarminConnectionCommand(user_id="user-1", connection_id=connection.id)
    )

    assert disconnected.status == "disconnected"
    assert disconnected.credential_status == "deleted"


def test_admin_token_import_encrypts_payload_and_reactivates_credentials_without_leaking_raw_session() -> None:
    integrations = _FakeIntegrationStore()
    credentials = _FakeCredentialStore()
    connection = integrations.create_connection(
        user_id="user-1",
        provider="garmin_connect",
        provider_account_id="garmin-account-1",
        credential_format="garminconnect-session-json",
    )
    integrations.connection_requires_reauth(connection.id)

    imported = AdminImportGarminTokenHandler(
        integrations=integrations,
        credentials=credentials,
        cipher=_FakeCipher(),
    ).handle(
        AdminImportGarminTokenCommand(
            user_id="user-1",
            connection_id=connection.id,
            session_payload='{"oauth2_token":"imported-secret-token"}',
        )
    )

    assert imported.status == "active"
    assert imported.credential_status == "active"
    assert credentials.saved is not None
    assert credentials.saved.encrypted_payload == "fernet:encrypted-session"
    assert credentials.saved.lifecycle_metadata == {"source": "admin_import"}
    assert "imported-secret-token" not in repr(imported)
    assert "imported-secret-token" not in repr(credentials.saved.to_safe_summary())


class _FakeGarminLoginAdapter:
    def __init__(self, profile: GarminAccountProfile) -> None:
        self._profile = profile
        self.calls: list[dict[str, str]] = []

    def exchange_credentials(self, *, email: str, password: str, region: str) -> GarminAccountProfile:
        self.calls.append({"email": email, "password": password, "region": region})
        return self._profile


class _FakeCipher:
    key_id = "local-fernet"

    def encrypt(self, plaintext: str) -> str:
        assert plaintext in {'{"oauth2_token":"secret-token"}', '{"oauth2_token":"imported-secret-token"}', "session-json"}
        return "fernet:encrypted-session"

    def decrypt(self, encrypted_payload: str) -> str:
        raise AssertionError("connect should not decrypt credentials")


class _FakeCredentialStore:
    def __init__(self) -> None:
        self.saved: IntegrationCredential | None = None

    def upsert_credential(self, credential: IntegrationCredential) -> IntegrationCredential:
        self.saved = credential
        return credential

    def get_credential_for_connection(self, integration_connection_id: str) -> IntegrationCredential | None:
        return None

    def delete_credential_for_connection(self, integration_connection_id: str) -> None:
        self.saved = None


class _FakeIntegrationStore:
    def __init__(self) -> None:
        self.connections: dict[str, IntegrationConnectionRef] = {}
        self.reset_cursor_ids: list[str] = []

    def get_connection_by_provider_account(self, provider: str, provider_account_id: str) -> IntegrationConnectionRef | None:
        return self.connections.get(f"{provider}:{provider_account_id}")

    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None:
        for connection in self.connections.values():
            if connection.id == connection_id and connection.user_id == user_id:
                return connection
        return None

    def replace_active_connections_for_user(self, user_id: str, *, except_connection_id: str | None = None) -> None:
        return None

    def create_connection(self, **kwargs) -> IntegrationConnectionRef:
        connection = IntegrationConnectionRef.create(id="conn-1", **kwargs)
        self.connections[f"{connection.provider}:{connection.provider_account_id}"] = connection
        return connection

    def reactivate_connection(self, connection_id: str, **kwargs) -> IntegrationConnectionRef:
        existing = next(connection for connection in self.connections.values() if connection.id == connection_id)
        connection = IntegrationConnectionRef.create(
            id=existing.id,
            user_id=existing.user_id,
            provider=existing.provider,
            provider_account_id=existing.provider_account_id,
            provider_display_name=kwargs.get("provider_display_name"),
            auth_scheme=kwargs.get("auth_scheme", "garminconnect_tokenstore"),
            credential_secret_ref=kwargs.get("credential_secret_ref"),
            credential_format=kwargs.get("credential_format"),
            credential_status="active",
            status="active",
            capabilities=kwargs.get("capabilities"),
            provider_metadata=kwargs.get("provider_metadata"),
        )
        self.connections[f"{connection.provider}:{connection.provider_account_id}"] = connection
        return connection

    def reset_resource_cursors(self, integration_connection_id: str) -> None:
        self.reset_cursor_ids.append(integration_connection_id)

    def disconnect_connection(self, connection_id: str) -> IntegrationConnectionRef:
        return self._replace_connection(
            connection_id,
            credential_secret_ref=None,
            credential_status="deleted",
            status="disconnected",
            sync_status="idle",
        )

    def mark_connection_credentials_active(self, connection_id: str, *, credential_format: str) -> IntegrationConnectionRef:
        return self._replace_connection(
            connection_id,
            credential_secret_ref=None,
            credential_format=credential_format,
            credential_status="active",
            status="active",
            sync_status="idle",
        )

    def connection_requires_reauth(self, connection_id: str) -> None:
        self._replace_connection(connection_id, credential_status="requires_reauth", sync_status="failed")

    def _replace_connection(self, connection_id: str, **changes) -> IntegrationConnectionRef:
        existing = next(connection for connection in self.connections.values() if connection.id == connection_id)
        connection = IntegrationConnectionRef.create(
            id=existing.id,
            user_id=existing.user_id,
            provider=existing.provider,
            provider_account_id=existing.provider_account_id,
            provider_display_name=existing.provider_display_name,
            auth_scheme=existing.auth_scheme,
            credential_secret_ref=changes.get("credential_secret_ref", existing.credential_secret_ref),
            credential_format=changes.get("credential_format", existing.credential_format),
            credential_status=changes.get("credential_status", existing.credential_status),
            status=changes.get("status", existing.status),
            sync_status=changes.get("sync_status", existing.sync_status),
            capabilities=existing.capabilities,
            provider_metadata=existing.provider_metadata,
        )
        self.connections[f"{connection.provider}:{connection.provider_account_id}"] = connection
        return connection
