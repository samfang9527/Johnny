from __future__ import annotations

import os
from urllib import parse


_LOCAL_VITE_PORTS = range(5173, 5180)


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS") or os.getenv("FRONTEND_ORIGINS")
    if raw:
        origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
        default_origin = origin_from_url(os.getenv("FRONTEND_URL", ""))
    else:
        origins = [
            origin
            for port in _LOCAL_VITE_PORTS
            for origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")
        ]
        default_origin = origin_from_url(default_frontend_url())
    if default_origin and default_origin not in origins:
        origins.append(default_origin)
    return origins


def default_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")


def origin_from_url(url: str) -> str:
    parsed = parse.urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def is_allowed_frontend_origin(origin: str | None) -> bool:
    return bool(origin) and origin.rstrip("/") in set(cors_origins())
