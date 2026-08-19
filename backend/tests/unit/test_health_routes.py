from fastapi.testclient import TestClient

from src import main
from src.main import create_app


def test_health_endpoint_identifies_reachable_api() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Johnny-api"}


def test_ready_endpoint_reports_readiness() -> None:
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_run_uses_src_application_import_path(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_uvicorn_run(app_path: str, **kwargs: object) -> None:
        calls.append({"app_path": app_path, **kwargs})

    monkeypatch.setattr(main.uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")

    main.run()

    assert calls == [
        {
            "app_path": "src.main:app",
            "host": "0.0.0.0",
            "port": 9000,
            "reload": True,
        }
    ]
