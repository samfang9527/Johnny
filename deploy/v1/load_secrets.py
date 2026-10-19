#!/usr/bin/env python3
"""Render short-lived Docker env files from SSM without printing secret values."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote, urlsplit


SECRET_NAMES = {
    "database-password": "POSTGRES_PASSWORD",
    "openai-api-key": "OPENAI_API_KEY",
    "google-oauth-client-secret": "GOOGLE_OAUTH_CLIENT_SECRET",
    "garmin-credential-master-key": "GARMIN_CREDENTIAL_MASTER_KEY",
    "admin-token": "JOHNNY_ADMIN_TOKEN",
}


def read_settings(path: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.isidentifier() or key in settings:
            raise ValueError(f"Invalid setting in {path}: {key}")
        settings[key] = value
    for key in ("FRONTEND_URL", "API_URL", "GOOGLE_OAUTH_CLIENT_ID", "LLM_MODEL", "AWS_REGION"):
        if not settings.get(key):
            raise ValueError(f"Missing setting: {key}")
    frontend = urlsplit(settings["FRONTEND_URL"])
    api = urlsplit(settings["API_URL"])
    if frontend.scheme != "https" or api.scheme != "https" or not frontend.hostname or not api.hostname:
        raise ValueError("FRONTEND_URL and API_URL must be HTTPS origins")
    if any((frontend.path not in ("", "/"), api.path not in ("", "/"), frontend.query, api.query, frontend.fragment, api.fragment, frontend.username, api.username)):
        raise ValueError("FRONTEND_URL and API_URL must be bare HTTPS origins")
    return settings


def fetch_secrets(region: str, prefix: str) -> dict[str, str]:
    names = [f"{prefix.rstrip('/')}/{name}" for name in SECRET_NAMES]
    result = subprocess.run(
        ["aws", "ssm", "get-parameters", "--region", region, "--with-decryption", "--names", *names, "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Unable to read required SSM parameters")
    payload = json.loads(result.stdout)
    if payload.get("InvalidParameters"):
        raise ValueError("Missing required SSM parameters: " + ", ".join(payload["InvalidParameters"]))
    found = {item["Name"]: item["Value"] for item in payload["Parameters"]}
    if set(found) != set(names) or any(not value for value in found.values()):
        raise ValueError("A required SSM parameter is missing or empty")
    if any(item.get("Type") != "SecureString" for item in payload["Parameters"]):
        raise ValueError("All backend secrets must be SecureString parameters")
    return {env_key: found[f"{prefix.rstrip('/')}/{name}"] for name, env_key in SECRET_NAMES.items()}


def write_env(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if not key.isidentifier() or "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError(f"Invalid environment value: {key}")
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def render(settings: dict[str, str], secrets: dict[str, str], output_dir: Path) -> None:
    if settings.get("ENV", "production") != "production":
        raise ValueError("Production must run with ENV=production")
    for key, value in secrets.items():
        if not value or "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError(f"Invalid secret value: {key}")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    database_url = (
        "postgresql+psycopg://johnny:"
        + quote(secrets["POSTGRES_PASSWORD"], safe="")
        + "@postgres:5432/johnny"
    )
    common = {"ENV": "production", "DATABASE_URL": database_url}
    write_env(output_dir / "postgres.env", {"POSTGRES_USER": "johnny", "POSTGRES_DB": "johnny", "POSTGRES_PASSWORD": secrets["POSTGRES_PASSWORD"]})
    write_env(output_dir / "api.env", {
        **common,
        "FRONTEND_URL": settings["FRONTEND_URL"],
        "CORS_ALLOW_ORIGINS": settings["FRONTEND_URL"],
        "JOHNNY_AUTH_REQUIRED": "true",
        "JOHNNY_AUTH_ALLOW_HEADER_USER": "false",
        "JOHNNY_SESSION_COOKIE_SECURE": "true",
        "GOOGLE_OAUTH_CLIENT_ID": settings["GOOGLE_OAUTH_CLIENT_ID"],
        "GOOGLE_OAUTH_CLIENT_SECRET": secrets["GOOGLE_OAUTH_CLIENT_SECRET"],
        "GOOGLE_OAUTH_REDIRECT_URI": settings["API_URL"].rstrip("/") + "/api/v1/auth/google/callback",
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": settings["LLM_MODEL"],
        "OPENAI_API_KEY": secrets["OPENAI_API_KEY"],
        "GARMIN_CREDENTIAL_MASTER_KEY": secrets["GARMIN_CREDENTIAL_MASTER_KEY"],
        "GARMIN_CREDENTIAL_KEY_ID": settings.get("GARMIN_CREDENTIAL_KEY_ID", "production-fernet"),
        "JOHNNY_ADMIN_TOKEN": secrets["JOHNNY_ADMIN_TOKEN"],
    })
    write_env(output_dir / "worker.env", {
        **common,
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": settings["LLM_MODEL"],
        "OPENAI_API_KEY": secrets["OPENAI_API_KEY"],
        "GARMIN_CREDENTIAL_MASTER_KEY": secrets["GARMIN_CREDENTIAL_MASTER_KEY"],
        "GARMIN_CREDENTIAL_KEY_ID": settings.get("GARMIN_CREDENTIAL_KEY_ID", "production-fernet"),
    })
    write_env(output_dir / "scheduler.env", common)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=Path("/etc/johnny/production.env"))
    parser.add_argument("--output-dir", type=Path, default=Path("/run/johnny"))
    parser.add_argument("--prefix", default="/johnny/production")
    args = parser.parse_args()
    settings = read_settings(args.settings)
    secrets = fetch_secrets(settings["AWS_REGION"], args.prefix)
    render(settings, secrets, args.output_dir)
    print("Production environment files refreshed")


if __name__ == "__main__":
    main()
