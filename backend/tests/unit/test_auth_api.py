from __future__ import annotations

from urllib import parse

from tests.unit.api_test_helpers import create_sqlite_test_client


def test_protected_me_requires_session_when_auth_is_required(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    client = create_sqlite_test_client()

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_protected_me_requires_session_when_test_env_leaks_outside_pytest(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("JOHNNY_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    client = create_sqlite_test_client()

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_email_signup_creates_user_session_and_me_returns_display_name(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    client = create_sqlite_test_client()

    signup = client.post(
        "/api/v1/auth/signup",
        json={"display_name": "Johnny Chen", "email": "runner@example.com", "password": "password123"},
    )
    me = client.get("/api/v1/me")

    assert signup.status_code == 200
    assert signup.json()["data"]["user"]["email"] == "runner@example.com"
    assert signup.json()["data"]["user"]["display_name"] == "Johnny Chen"
    assert "johnny_session=" in signup.headers["set-cookie"]
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "runner@example.com"
    assert me.json()["data"]["display_name"] == "Johnny Chen"


def test_email_login_uses_generic_error_and_does_not_leak_account_existence(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    client = create_sqlite_test_client()
    client.post(
        "/api/v1/auth/signup",
        json={"display_name": "Johnny Chen", "email": "runner@example.com", "password": "password123"},
    )
    client.post("/api/v1/auth/logout")

    bad_password = client.post("/api/v1/auth/login", json={"email": "runner@example.com", "password": "wrong-password"})
    missing_user = client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong-password"})
    valid = client.post("/api/v1/auth/login", json={"email": "runner@example.com", "password": "password123"})

    assert bad_password.status_code == 401
    assert missing_user.status_code == 401
    assert bad_password.json() == missing_user.json()
    assert bad_password.json()["error"]["message"] == "Email or password is incorrect"
    assert valid.status_code == 200
    assert "johnny_session=" in valid.headers["set-cookie"]


def test_google_start_returns_configured_authorization_url(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")
    client = create_sqlite_test_client()

    response = client.get("/api/v1/auth/google/start?callback_url=%23inbox")

    assert response.status_code == 200
    assert "accounts.google.com/o/oauth2/v2/auth" in response.json()["data"]["authorization_url"]
    assert "client_id=google-client-id" in response.json()["data"]["authorization_url"]
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fv1%2Fauth%2Fgoogle%2Fcallback" in response.json()["data"]["authorization_url"]
    assert "johnny_oauth_state=" in response.headers["set-cookie"]


def test_google_start_allows_vite_fallback_port_to_preserve_oauth_cookies(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    client = create_sqlite_test_client()

    response = client.get(
        "/api/v1/auth/google/start?callback_url=%23today",
        headers={"Origin": "http://127.0.0.1:5175"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5175"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "johnny_oauth_state=" in response.headers["set-cookie"]
    assert "johnny_auth_callback=" in response.headers["set-cookie"]


def test_google_start_redirect_mode_sets_state_before_google_redirect(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    client = create_sqlite_test_client()

    response = client.get(
        "/api/v1/auth/google/start?callback_url=%23today&redirect=true&frontend_origin=http%3A%2F%2Flocalhost%3A5173",
        follow_redirects=False,
    )
    query = parse.parse_qs(parse.urlparse(response.headers["location"]).query)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["redirect_uri"] == ["http://localhost:8000/api/v1/auth/google/callback"]
    assert query["state"][0]
    assert "johnny_oauth_state=" in response.headers["set-cookie"]
    assert 'johnny_auth_callback="http://localhost:5173/#today"' in response.headers["set-cookie"]


def test_google_start_redirect_mode_uses_configured_redirect_uri_without_host_rewrite(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")
    client = create_sqlite_test_client()

    response = client.get(
        "http://localhost:8000/api/v1/auth/google/start?callback_url=%23today&redirect=true&frontend_origin=http%3A%2F%2Flocalhost%3A5173",
        follow_redirects=False,
    )
    query = parse.parse_qs(parse.urlparse(response.headers["location"]).query)

    assert response.status_code == 307
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/api/v1/auth/google/callback"]
    assert 'johnny_auth_callback="http://localhost:5173/#today"' in response.headers["set-cookie"]


def test_google_callback_returns_to_origin_that_started_login(monkeypatch) -> None:
    import src.api.routes.auth as auth_routes

    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    monkeypatch.setattr(
        auth_routes,
        "_exchange_google_code",
        lambda code: {
            "iss": "https://accounts.google.com",
            "sub": "google-user-123",
            "email": "runner@example.com",
            "name": "Runner Chen",
        },
    )
    client = create_sqlite_test_client()

    start = client.get(
        "/api/v1/auth/google/start?callback_url=%23today",
        headers={"Origin": "http://localhost:5173"},
    )
    authorization_url = start.json()["data"]["authorization_url"]
    state = parse.parse_qs(parse.urlparse(authorization_url).query)["state"][0]
    callback = client.get(
        f"/api/v1/auth/google/callback?state={state}&code=oauth-code",
        follow_redirects=False,
    )

    assert callback.status_code == 307
    assert callback.headers["location"] == "http://localhost:5173/#today"
    assert "johnny_session=" in callback.headers["set-cookie"]


def test_google_callback_creates_default_athlete_profile_with_browser_timezone(monkeypatch) -> None:
    import src.api.routes.auth as auth_routes

    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
    monkeypatch.setattr(
        auth_routes,
        "_exchange_google_code",
        lambda code: {
            "iss": "https://accounts.google.com",
            "sub": "google-user-123",
            "email": "runner@example.com",
            "name": "Runner Chen",
        },
    )
    client = create_sqlite_test_client()

    start = client.get(
        "/api/v1/auth/google/start?callback_url=%23today&timezone=Asia%2FTaipei",
        headers={"Origin": "http://localhost:5173"},
    )
    state = parse.parse_qs(parse.urlparse(start.json()["data"]["authorization_url"]).query)["state"][0]
    callback = client.get(
        f"/api/v1/auth/google/callback?state={state}&code=oauth-code",
        follow_redirects=False,
    )
    profile = client.get("/api/v1/athlete/profile")

    assert callback.status_code == 307
    assert profile.status_code == 200
    assert profile.json()["data"]["timezone"] == "Asia/Taipei"
    assert profile.json()["data"]["experience_level"] is None


def test_google_callback_exchanges_code_with_configured_redirect_uri(monkeypatch) -> None:
    import src.api.routes.auth as auth_routes

    captured: dict[str, str] = {}

    def fake_exchange(code: str) -> dict:
        captured["code"] = code
        return {
            "iss": "https://accounts.google.com",
            "sub": "google-user-123",
            "email": "runner@example.com",
            "name": "Runner Chen",
        }

    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/v1/auth/google/callback")
    monkeypatch.setattr(auth_routes, "_exchange_google_code", fake_exchange)
    client = create_sqlite_test_client()

    start = client.get(
        "http://localhost:8000/api/v1/auth/google/start?callback_url=%23today&redirect=true&frontend_origin=http%3A%2F%2Flocalhost%3A5173",
        follow_redirects=False,
    )
    state = parse.parse_qs(parse.urlparse(start.headers["location"]).query)["state"][0]
    callback = client.get(
        f"http://localhost:8000/api/v1/auth/google/callback?state={state}&code=oauth-code",
        follow_redirects=False,
    )

    assert callback.status_code == 307
    assert captured["code"] == "oauth-code"
    assert callback.headers["location"] == "http://localhost:5173/#today"


def test_google_callback_uses_127_frontend_default_for_local_redirect(monkeypatch) -> None:
    monkeypatch.setenv("JOHNNY_AUTH_REQUIRED", "true")
    client = create_sqlite_test_client()

    response = client.get("/api/v1/auth/google/callback?state=bad-state&code=oauth-code", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://127.0.0.1:5173/?auth_error=oauth_state"
