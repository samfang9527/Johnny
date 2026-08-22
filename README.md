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

The API loads `backend/.env` when present, while shell environment variables still take precedence.

OpenAI is the first production LLM provider for the Running Companion Agent. To enable OpenAI-backed agent execution locally, keep `LLM_PROVIDER=openai`, set `LLM_MODEL` to the model you want Johnny to use, and provide either `OPENAI_API_KEY` or `LLM_API_KEY` in your shell or uncommitted `backend/.env`.

LLM inputs and outputs are treated as untrusted. Johnny exposes only workflow-allowed tools, sends dynamic context as data rather than elevated instructions, validates OpenAI function-call arguments against strict schemas, and performs server-side policy checks before executing any model-requested tool.

Normal backend tests stay network-free by using fake model gateways. Any live OpenAI smoke check should be opt-in and run only when an API key, model, and explicit smoke command are configured for the local environment.

Run the API locally:

```bash
make run-api
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

Start local PostgreSQL:

```bash
make db-up
```

Apply migrations:

```bash
make migrate
```

Seed demo data for the local manual runbook:

```bash
make seed-demo
```

Run the deterministic local companion smoke:

```bash
make smoke-local
```

Run the optional live OpenAI smoke after configuring OpenAI settings:

```bash
make smoke-openai
```

Check the current migration revision:

```bash
DATABASE_URL=postgresql+psycopg://johnny:johnny@localhost:5432/johnny ./.venv/bin/alembic -c backend/alembic.ini current
```

View migration history:

```bash
./.venv/bin/alembic -c backend/alembic.ini history
```

Downgrade one revision:

```bash
DATABASE_URL=postgresql+psycopg://johnny:johnny@localhost:5432/johnny ./.venv/bin/alembic -c backend/alembic.ini downgrade -1
```

Persistence integration tests use `JOHNNY_TEST_DATABASE_URL` when a PostgreSQL test database is available. The default local test suite also runs metadata, repository, constraint, and migration workflow checks against isolated SQLite databases so schema regressions are caught without starting the API server.

Garmin Connect schema verification is opt-in because it calls a real user account through `garminconnect==0.3.11`. Keep Garmin credentials and local token-store files outside the database. The probe loads `backend/.env` automatically, and shell environment variables override `.env` values.

```bash
JOHNNY_GARMINCONNECT_SESSION_FILE=/path/to/local/garmin_tokens.json \
PYTHONPATH=backend ./.venv/bin/python -m src.infrastructure.integrations.garminconnect_schema_probe --date 2026-08-19
```

The `JOHNNY_GARMINCONNECT_SESSION_FILE` name is retained for compatibility, but the value is now passed to `garminconnect` as its token-store path. If no valid token-store file exists, the probe can log in with `JOHNNY_GARMINCONNECT_EMAIL` and `JOHNNY_GARMINCONNECT_PASSWORD` and let `garminconnect` write refreshed tokens to that local path. The persistence schema stores only credential references such as `credential_secret_ref`, never the raw Garmin password, cookies, token-store JSON, or provider token values.

Manual end-to-end local testing is documented in `docs/manual_test_runbook.md`.
