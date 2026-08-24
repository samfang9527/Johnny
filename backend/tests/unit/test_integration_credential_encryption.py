import pytest
from cryptography.fernet import Fernet

from src.infrastructure.security.integration_credentials import (
    CredentialEncryptionConfigurationError,
    FernetCredentialCipher,
    load_garmin_credential_cipher,
)


def test_fernet_credential_cipher_round_trips_plaintext_without_echoing_it() -> None:
    cipher = FernetCredentialCipher(key=Fernet.generate_key().decode("ascii"), key_id="local-fernet")

    encrypted = cipher.encrypt('{"oauth2_token":"secret-token"}')

    assert encrypted.startswith("fernet:")
    assert encrypted != '{"oauth2_token":"secret-token"}'
    assert "secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == '{"oauth2_token":"secret-token"}'
    assert cipher.key_id == "local-fernet"


def test_load_garmin_credential_cipher_requires_valid_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("GARMIN_CREDENTIAL_MASTER_KEY", raising=False)

    with pytest.raises(CredentialEncryptionConfigurationError, match="GARMIN_CREDENTIAL_MASTER_KEY"):
        load_garmin_credential_cipher()

    monkeypatch.setenv("GARMIN_CREDENTIAL_MASTER_KEY", "not-a-fernet-key")

    with pytest.raises(CredentialEncryptionConfigurationError, match="GARMIN_CREDENTIAL_MASTER_KEY"):
        load_garmin_credential_cipher()


def test_load_garmin_credential_cipher_uses_configured_key_and_key_id(monkeypatch) -> None:
    monkeypatch.setenv("GARMIN_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("GARMIN_CREDENTIAL_KEY_ID", "local-dev-key")

    cipher = load_garmin_credential_cipher()

    encrypted = cipher.encrypt("session-json")
    assert cipher.key_id == "local-dev-key"
    assert encrypted.startswith("fernet:")
    assert cipher.decrypt(encrypted) == "session-json"
