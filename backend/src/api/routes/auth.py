from __future__ import annotations

import json
import os
from urllib import parse, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Cookie, Query, Request, Response
from fastapi.responses import RedirectResponse

from src.api.dependencies import MVP_CAPABILITIES, SESSION_COOKIE_NAME, SessionDependency
from src.api.errors import ApiConflictError, ApiUnauthorizedError
from src.api.frontend_origins import default_frontend_url, is_allowed_frontend_origin, origin_from_url
from src.api.schemas.auth import (
    AuthUserSessionResponse,
    EmailPasswordLoginRequest,
    EmailPasswordSignupRequest,
    GoogleStartResponse,
)
from src.api.schemas.common import DataEnvelope
from src.api.schemas.me import CurrentUserResponse
from src.application.auth import hash_password, new_session_token, normalize_email, session_expiry, verify_password
from src.domain.athlete_race import AthleteProfile
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
from src.infrastructure.database.user_repository import SqlAlchemyUserRepository


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=DataEnvelope[AuthUserSessionResponse])
def signup(payload: EmailPasswordSignupRequest, request: Request, response: Response, session: SessionDependency) -> DataEnvelope[AuthUserSessionResponse]:
    users = SqlAlchemyUserRepository(session)
    auth = SqlAlchemyAuthRepository(session)
    email = normalize_email(payload.email)
    if users.get_by_email(email) is not None:
        raise ApiConflictError("Email is already registered")

    user = users.create_user(email=email, display_name=payload.display_name)
    auth.create_password_identity(user=user, email=email, password_hash=hash_password(payload.password))
    _issue_session_cookie(auth, response, user_id=user.id, user_agent=request.headers.get("user-agent"))
    return _auth_envelope(user.id, user.email, user.display_name)


@router.post("/login", response_model=DataEnvelope[AuthUserSessionResponse])
def login(payload: EmailPasswordLoginRequest, request: Request, response: Response, session: SessionDependency) -> DataEnvelope[AuthUserSessionResponse]:
    auth = SqlAlchemyAuthRepository(session)
    credential = auth.get_password_credential(normalize_email(payload.email))
    if credential is None or not verify_password(payload.password, credential.password_hash):
        raise ApiUnauthorizedError("Email or password is incorrect")

    _issue_session_cookie(auth, response, user_id=credential.user_id, user_agent=request.headers.get("user-agent"))
    return _auth_envelope(credential.user.id, credential.user.email, credential.user.display_name)


@router.post("/logout", response_model=DataEnvelope[dict])
def logout(response: Response, session: SessionDependency, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> DataEnvelope[dict]:
    if session_token:
        SqlAlchemyAuthRepository(session).revoke_session(session_token)
    _clear_cookie(response, SESSION_COOKIE_NAME)
    return DataEnvelope(data={"status": "signed_out"})


@router.get("/google/start", response_model=DataEnvelope[GoogleStartResponse])
def google_start(
    request_context: Request,
    response: Response,
    callback_url: str = Query(default="/"),
    display_name: str | None = Query(default=None, max_length=200),
    redirect: bool = Query(default=False),
    frontend_origin: str | None = Query(default=None, max_length=200),
    timezone: str | None = Query(default=None, max_length=100),
) -> DataEnvelope[GoogleStartResponse] | RedirectResponse:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise ApiUnauthorizedError("Google sign-in is not configured")

    state = new_session_token()
    request_origin = frontend_origin or request_context.headers.get("origin")
    safe_callback = _safe_callback_url(callback_url, request_origin=request_origin)
    query = parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    authorization_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    if redirect:
        redirect_response = RedirectResponse(authorization_url)
        _set_google_start_cookies(
            redirect_response,
            state=state,
            callback_url=safe_callback,
            display_name=display_name,
            timezone=_safe_timezone(timezone),
        )
        return redirect_response
    _set_google_start_cookies(response, state=state, callback_url=safe_callback, display_name=display_name, timezone=_safe_timezone(timezone))
    return DataEnvelope(data=GoogleStartResponse(authorization_url=authorization_url))


@router.get("/google/callback")
def google_callback(
    request_context: Request,
    session: SessionDependency,
    state: str,
    code: str | None = None,
    error: str | None = None,
    expected_state: str | None = Cookie(default=None, alias="johnny_oauth_state"),
    callback_url: str | None = Cookie(default=None, alias="johnny_auth_callback"),
    display_name: str | None = Cookie(default=None, alias="johnny_oauth_display_name"),
    timezone_name: str | None = Cookie(default=None, alias="johnny_oauth_timezone"),
) -> RedirectResponse:
    if error:
        return RedirectResponse(_frontend_url(callback_url, error="oauth_cancelled"))
    if not code or not expected_state or state != expected_state:
        return RedirectResponse(_frontend_url(callback_url, error="oauth_state"))

    claims = _exchange_google_code(code)
    email = normalize_email(str(claims.get("email") or ""))
    subject = str(claims.get("sub") or "")
    if not email or not subject:
        return RedirectResponse(_frontend_url(callback_url, error="oauth_profile"))

    auth = SqlAlchemyAuthRepository(session)
    user = auth.create_or_update_google_identity(
        issuer=str(claims.get("iss") or "https://accounts.google.com"),
        subject=subject,
        email=email,
        display_name=str(display_name or claims.get("name") or email.split("@", 1)[0]),
        claims=claims,
    )
    _ensure_default_athlete_profile(session, user_id=user.id, timezone_name=timezone_name)
    response = RedirectResponse(_frontend_url(callback_url))
    _issue_session_cookie(auth, response, user_id=user.id, user_agent=request_context.headers.get("user-agent"))
    _clear_cookie(response, "johnny_oauth_state")
    _clear_cookie(response, "johnny_auth_callback")
    _clear_cookie(response, "johnny_oauth_display_name")
    _clear_cookie(response, "johnny_oauth_timezone")
    return response


def _issue_session_cookie(auth: SqlAlchemyAuthRepository, response: Response, *, user_id: str, user_agent: str | None) -> None:
    token = new_session_token()
    expires_at = session_expiry()
    auth.create_session(user_id=user_id, token=token, expires_at=expires_at, user_agent=user_agent)
    _set_cookie(response, SESSION_COOKIE_NAME, token, max_age=30 * 24 * 60 * 60)


def _set_google_start_cookies(response: Response, *, state: str, callback_url: str, display_name: str | None, timezone: str | None) -> None:
    _set_cookie(response, "johnny_oauth_state", state, max_age=600)
    _set_cookie(response, "johnny_auth_callback", callback_url, max_age=600)
    if display_name and display_name.strip():
        _set_cookie(response, "johnny_oauth_display_name", " ".join(display_name.strip().split()), max_age=600)
    if timezone:
        _set_cookie(response, "johnny_oauth_timezone", timezone, max_age=600)


def _set_cookie(response: Response, key: str, value: str, *, max_age: int) -> None:
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        secure=_secure_cookies(),
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _clear_cookie(response: Response, key: str) -> None:
    response.delete_cookie(key=key, path="/", httponly=True, secure=_secure_cookies(), samesite="lax")


def _auth_envelope(user_id: str, email: str | None, display_name: str | None) -> DataEnvelope[AuthUserSessionResponse]:
    return DataEnvelope(
        data=AuthUserSessionResponse(
            user=CurrentUserResponse(
                id=user_id,
                email=email,
                display_name=display_name,
                capabilities=MVP_CAPABILITIES,
            )
        )
    )


def _exchange_google_code(code: str) -> dict:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise ApiUnauthorizedError("Google sign-in is not configured")

    token_body = parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    token_request = request.Request("https://oauth2.googleapis.com/token", data=token_body, method="POST")
    token_request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with request.urlopen(token_request, timeout=10) as token_response:
        token_payload = json.loads(token_response.read().decode("utf-8"))

    id_token = token_payload.get("id_token")
    if not id_token:
        raise ApiUnauthorizedError("Google sign-in did not return an identity token")

    with request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?id_token={parse.quote(str(id_token))}", timeout=10) as claims_response:
        claims = json.loads(claims_response.read().decode("utf-8"))
    if claims.get("aud") != client_id:
        raise ApiUnauthorizedError("Google sign-in returned an invalid audience")
    return claims


def _frontend_url(callback_url: str | None, *, error: str | None = None) -> str:
    safe_callback = _safe_callback_url(callback_url or "/")
    url = safe_callback if origin_from_url(safe_callback) else _join_frontend_url(default_frontend_url(), safe_callback)
    if error:
        return _append_auth_error(url, error)
    return url


def _safe_callback_url(callback_url: str, *, request_origin: str | None = None) -> str:
    callback_url = callback_url.strip()
    callback_origin = origin_from_url(callback_url)
    if callback_origin:
        return callback_url if is_allowed_frontend_origin(callback_origin) else "/"
    if callback_url.startswith("#") or callback_url.startswith("/"):
        if request_origin and is_allowed_frontend_origin(request_origin):
            return _join_frontend_url(request_origin, callback_url)
        return callback_url
    return "/"


def _join_frontend_url(base_url: str, callback_url: str) -> str:
    base = base_url.rstrip("/")
    if callback_url.startswith("#"):
        return f"{base}/{callback_url}"
    if callback_url.startswith("/"):
        return f"{base}{callback_url}"
    return f"{base}/"


def _append_auth_error(url: str, error: str) -> str:
    parts = parse.urlsplit(url)
    query = parse.parse_qsl(parts.query, keep_blank_values=True)
    query.append(("auth_error", error))
    return parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            parse.urlencode(query),
            parts.fragment,
        )
    )


def _ensure_default_athlete_profile(session, *, user_id: str, timezone_name: str | None) -> None:
    repository = SqlAlchemyAthleteRaceRepository(session)
    if repository.get_profile_for_user(user_id) is not None:
        return
    repository.save_profile(
        user_id,
        AthleteProfile.create(
            user_id=user_id,
            timezone=_safe_timezone(timezone_name) or "UTC",
            experience_level=None,
            current_weekly_mileage_km=0,
            preferred_training_days=("tuesday", "thursday", "sunday"),
            preferred_long_run_day="sunday",
            max_runs_per_week=3,
            max_hard_sessions_per_week=2,
        ),
    )


def _safe_timezone(timezone_name: str | None) -> str | None:
    if not timezone_name:
        return None
    candidate = timezone_name.strip()
    if not candidate or len(candidate) > 100:
        return None
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return None
    return candidate


def _secure_cookies() -> bool:
    configured = os.getenv("JOHNNY_SESSION_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("ENV", "").strip().lower() == "production"
