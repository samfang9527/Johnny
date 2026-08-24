from __future__ import annotations

import os
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionConfigurationError(RuntimeError):
    pass


class CredentialCipher(Protocol):
    key_id: str

    def encrypt(self, plaintext: str) -> str:
        ...

    def decrypt(self, encrypted_payload: str) -> str:
        ...


class FernetCredentialCipher:
    payload_scheme = "fernet:"

    def __init__(self, *, key: str, key_id: str = "local-fernet") -> None:
        self.key_id = key_id
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except Exception as exc:  # noqa: BLE001
            raise CredentialEncryptionConfigurationError("GARMIN_CREDENTIAL_MASTER_KEY is invalid") from exc

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{self.payload_scheme}{token}"

    def decrypt(self, encrypted_payload: str) -> str:
        if not encrypted_payload.startswith(self.payload_scheme):
            raise CredentialEncryptionConfigurationError("encrypted credential payload has unsupported scheme")
        token = encrypted_payload.removeprefix(self.payload_scheme)
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialEncryptionConfigurationError("encrypted credential payload cannot be decrypted") from exc


def load_garmin_credential_cipher() -> CredentialCipher:
    key = os.getenv("GARMIN_CREDENTIAL_MASTER_KEY")
    if not key:
        raise CredentialEncryptionConfigurationError("GARMIN_CREDENTIAL_MASTER_KEY is required for Garmin credentials")
    key_id = os.getenv("GARMIN_CREDENTIAL_KEY_ID", "local-fernet")
    return FernetCredentialCipher(key=key, key_id=key_id)
