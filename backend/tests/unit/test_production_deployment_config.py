from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("production_secrets", ROOT / "deploy/v1/load_secrets.py")
assert SPEC and SPEC.loader
production_secrets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_secrets)


def test_fetch_secrets_rejects_missing_parameter_without_exposing_values() -> None:
    result = SimpleNamespace(returncode=0, stdout=json.dumps({"Parameters": [], "InvalidParameters": ["/johnny/production/database-password"]}))
    with patch.object(production_secrets.subprocess, "run", return_value=result):
        with pytest.raises(ValueError, match="database-password"):
            production_secrets.fetch_secrets("ap-northeast-1", "/johnny/production")


def test_render_writes_private_per_service_env_files(tmp_path: Path) -> None:
    settings = {
        "ENV": "production",
        "FRONTEND_URL": "https://app.example.com",
        "API_URL": "https://api.example.com",
        "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        "LLM_MODEL": "model-name",
    }
    secrets = {
        "POSTGRES_PASSWORD": "p@ss:$word",
        "OPENAI_API_KEY": "model-secret",
        "GOOGLE_OAUTH_CLIENT_SECRET": "google-secret",
        "GARMIN_CREDENTIAL_MASTER_KEY": "garmin-secret",
        "JOHNNY_ADMIN_TOKEN": "admin-secret",
    }
    production_secrets.render(settings, secrets, tmp_path / "run")
    output = tmp_path / "run"
    api = (output / "api.env").read_text()
    worker = (output / "worker.env").read_text()
    scheduler = (output / "scheduler.env").read_text()
    assert "p%40ss%3A%24word@postgres" in api
    assert "GOOGLE_OAUTH_CLIENT_SECRET=google-secret" in api
    assert "GOOGLE_OAUTH_CLIENT_SECRET" not in worker
    assert "JOHNNY_ADMIN_TOKEN=admin-secret" in api
    assert "JOHNNY_ADMIN_TOKEN" not in worker
    assert "OPENAI_API_KEY=model-secret" in worker
    assert "OPENAI_API_KEY" not in scheduler
    assert stat.S_IMODE((output / "api.env").stat().st_mode) == 0o600
    assert stat.S_IMODE(output.stat().st_mode) == 0o700


def test_settings_reject_http_and_placeholder_origins(tmp_path: Path) -> None:
    path = tmp_path / "settings.env"
    path.write_text("AWS_REGION=ap-northeast-1\nFRONTEND_URL=http://app.example.com\nAPI_URL=https://api.example.com\nGOOGLE_OAUTH_CLIENT_ID=x\nLLM_MODEL=x\n")
    with pytest.raises(ValueError, match="HTTPS"):
        production_secrets.read_settings(path)


def test_production_rejects_missing_or_sqlite_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.database.session import get_database_url

    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        get_database_url()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///accidental.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        get_database_url()
