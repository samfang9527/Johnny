from pathlib import Path
import os
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def pytest_configure() -> None:
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
