from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.auth import hash_session_token

from .models import AuthIdentityModel, AuthSessionModel, PasswordCredentialModel, UserModel, utc_now


class SqlAlchemyAuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_password_identity(self, *, user: UserModel, email: str, password_hash: str) -> PasswordCredentialModel:
        identity = AuthIdentityModel(
            user_id=user.id,
            provider="password",
            issuer="johnny",
            subject=email,
            email=email,
            provider_claims={},
        )
        credential = PasswordCredentialModel(user_id=user.id, email=email, password_hash=password_hash)
        self._session.add(identity)
        self._session.add(credential)
        self._session.flush()
        return credential

    def get_password_credential(self, email: str) -> PasswordCredentialModel | None:
        return self._session.scalar(select(PasswordCredentialModel).where(PasswordCredentialModel.email == email))

    def create_or_update_google_identity(
        self,
        *,
        issuer: str,
        subject: str,
        email: str,
        display_name: str,
        claims: dict,
    ) -> UserModel:
        identity = self._session.scalar(
            select(AuthIdentityModel).where(
                AuthIdentityModel.provider == "google",
                AuthIdentityModel.issuer == issuer,
                AuthIdentityModel.subject == subject,
            )
        )
        if identity is not None:
            identity.email = email
            identity.provider_claims = claims
            identity.user.email = email
            if not identity.user.display_name:
                identity.user.display_name = display_name
            self._session.flush()
            return identity.user

        user = self._session.scalar(select(UserModel).where(UserModel.email == email))
        if user is None:
            user = UserModel(email=email, display_name=display_name)
            self._session.add(user)
            self._session.flush()
        self._session.add(
            AuthIdentityModel(
                user_id=user.id,
                provider="google",
                issuer=issuer,
                subject=subject,
                email=email,
                provider_claims=claims,
            )
        )
        self._session.flush()
        return user

    def create_session(self, *, user_id: str, token: str, expires_at: datetime, user_agent: str | None) -> AuthSessionModel:
        session = AuthSessionModel(
            user_id=user_id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
            user_agent=user_agent,
        )
        self._session.add(session)
        self._session.flush()
        return session

    def get_user_by_session_token(self, token: str) -> UserModel | None:
        now = datetime.now(timezone.utc)
        auth_session = self._session.scalar(
            select(AuthSessionModel).where(
                AuthSessionModel.token_hash == hash_session_token(token),
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
            )
        )
        if auth_session is None or auth_session.user.status != "active":
            return None
        return auth_session.user

    def revoke_session(self, token: str) -> None:
        auth_session = self._session.scalar(
            select(AuthSessionModel).where(
                AuthSessionModel.token_hash == hash_session_token(token),
                AuthSessionModel.revoked_at.is_(None),
            )
        )
        if auth_session is not None:
            auth_session.revoked_at = utc_now()
            self._session.flush()
