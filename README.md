# Johnny

Johnny is an AI running companion web app. The MVP proves the loop:

```text
Training data -> Analytics -> AI recommendation -> User approval -> Training adjustment -> Notification
```

## Stack

- Backend: Python, FastAPI
- Frontend: Vue, Vite, TypeScript
- Database: PostgreSQL for local and deployed MVP persistence
- Infrastructure: Terraform under `infra/terraform`

## Backend

Create a Python environment and install development dependencies:

```bash
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements/dev.txt
```

Prepare local configuration:

```bash
cp backend/.env.example backend/.env
```

Run the API locally:

```bash
PYTHONPATH=backend ./.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

Run backend tests:

```bash
./.venv/bin/python -m pytest backend/tests -q
```

Smoke-check the backend:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Frontend

Install dependencies:

```bash
cd frontend
npm install
```

Prepare local configuration:

```bash
cp .env.example .env
```

Run the frontend app:

```bash
npm run dev
```

Build and preview the frontend:

```bash
npm run build
npm run preview
```

The frontend dev server defaults to `http://localhost:5173` and reads `VITE_API_BASE_URL` from `frontend/.env`.

## Persistence

Local development uses PostgreSQL through `DATABASE_URL`.

Apply migrations:

```bash
DATABASE_URL=postgresql://johnny:johnny@localhost:5432/johnny ./.venv/bin/alembic -c backend/alembic.ini upgrade head
```

Check the current migration revision:

```bash
DATABASE_URL=postgresql://johnny:johnny@localhost:5432/johnny ./.venv/bin/alembic -c backend/alembic.ini current
```

View migration history:

```bash
./.venv/bin/alembic -c backend/alembic.ini history
```

Downgrade one revision:

```bash
DATABASE_URL=postgresql://johnny:johnny@localhost:5432/johnny ./.venv/bin/alembic -c backend/alembic.ini downgrade -1
```

Persistence integration tests use `JOHNNY_TEST_DATABASE_URL` when a PostgreSQL test database is available. The default local test suite also runs metadata, repository, constraint, and migration workflow checks against isolated SQLite databases so schema regressions are caught without starting the API server.

Garmin Connect schema verification is opt-in because it calls a real user account through `garminconnect==0.3.11`. Keep Garmin credentials and local token-store files outside the database. The probe loads `backend/.env` automatically, and shell environment variables override `.env` values.

```bash
JOHNNY_GARMINCONNECT_SESSION_FILE=/path/to/local/garmin_tokens.json \
PYTHONPATH=backend ./.venv/bin/python -m src.infrastructure.integrations.garminconnect_schema_probe --date 2026-08-19
```

The `JOHNNY_GARMINCONNECT_SESSION_FILE` name is retained for compatibility, but the value is now passed to `garminconnect` as its token-store path. If no valid token-store file exists, the probe can log in with `JOHNNY_GARMINCONNECT_EMAIL` and `JOHNNY_GARMINCONNECT_PASSWORD` and let `garminconnect` write refreshed tokens to that local path. The persistence schema stores only credential references such as `credential_secret_ref`, never the raw Garmin password, cookies, token-store JSON, or provider token values.

This persistence change does not add API routes, frontend UI, agent execution, notification delivery, or Terraform-managed database resources.
