from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user
from src.domain.activity_health import DomainValidationError
from src.main import create_app


def test_me_endpoint_uses_local_user_header_and_exposes_capabilities() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/me",
        headers={
            "X-Johnny-User-Id": "user-123",
            "X-Johnny-User-Email": "runner@example.com",
            "X-Johnny-User-Display-Name": "Runner One",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "id": "user-123",
            "email": "runner@example.com",
            "display_name": "Runner One",
            "capabilities": [
                "athlete-profile",
                "races",
                "training-plans",
                "activities",
                "today",
                "recommendations",
                "conversations",
                "integrations",
            ],
        }
    }


def test_validation_errors_use_structured_error_envelope() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/races",
        headers={"X-Johnny-User-Id": "user-123"},
        json={"name": "Missing date"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert any("race_date" in ".".join(str(part) for part in detail["loc"]) for detail in body["error"]["details"])


def test_domain_validation_errors_use_structured_error_envelope() -> None:
    router = APIRouter()

    @router.get("/api/test-domain-error")
    def domain_error_route() -> None:
        raise DomainValidationError("distance must be greater than zero")

    app = create_app()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/test-domain-error", headers={"X-Johnny-User-Id": "user-123"})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "domain_validation_error",
            "message": "distance must be greater than zero",
            "details": [],
        }
    }


def test_current_user_dependency_can_be_overridden_for_tenant_scope_tests() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="override-user",
        email="override@example.com",
        display_name="Override User",
    )
    client = TestClient(app)

    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "override-user"
