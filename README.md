# Johnny

Johnny is an AI running companion web app. The MVP has a daily coaching loop and a separate approval path for proposed plan changes:

```text
Training data -> Analytics -> Daily Advice -> Athlete executes the existing workout
Separate plan-change proposal -> Athlete approval -> Training adjustment
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

OpenAI is the first production LLM provider for the Running Companion Agent and Daily Advice. To enable OpenAI-backed agent execution locally, keep `LLM_PROVIDER=openai`, set `LLM_MODEL` to the model you want Johnny to use, and provide either `OPENAI_API_KEY` or `LLM_API_KEY` in your shell or uncommitted `backend/.env`. Without an API key, queued runs use the deterministic local model.

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
npm ci
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

The frontend dev server defaults to `http://localhost:5173` and reads `VITE_API_BASE_URL` from `frontend/.env`. If `VITE_API_BASE_URL` is unset in local development, the frontend derives the backend origin from the page host: `localhost` pages call `http://localhost:8000`, and `127.0.0.1` pages call `http://127.0.0.1:8000`.

Google sign-in navigates through the backend OAuth start route so the backend can set OAuth state cookies before redirecting to Google. Google sees the exact `GOOGLE_OAUTH_REDIRECT_URI` value from `backend/.env`. In local loopback development, if the browser starts on the other loopback host spelling, Johnny first hops to the configured callback host so OAuth state and app session cookies stay on the same host. If Vite falls back to another local port, the backend's default local CORS/origin list covers `localhost` and `127.0.0.1` ports `5173` through `5179`; if you set `CORS_ALLOW_ORIGINS` or `FRONTEND_ORIGINS`, include the exact frontend origin you are using.

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

Run the async local agent runtime:

```bash
make agent-schedule-once
make agent-work-drain
```

The async runtime stores queued work in the local database `agent_tasks` table. API triggers create a queued `agent_runs` row and a queued task in one transaction, then return a poll URL. The local worker drains tasks and updates the linked run status:

```bash
curl -s -H "Content-Type: application/json" \
  -H "X-Johnny-User-Id: local-user" \
  -d '{"anchor_date":"2027-01-28"}' \
  http://127.0.0.1:8000/api/v1/agent-runs/daily-recommendation

curl -s -H "Content-Type: application/json" \
  -H "X-Johnny-User-Id: local-user" \
  -d '{"plan_type":"base","starts_on":"2027-01-01"}' \
  http://127.0.0.1:8000/api/v1/agent-runs/training-plan-generation
```

Useful local runtime targets:

```bash
make agent-schedule-loop
make agent-work-one
make agent-work-loop
make smoke-agent-local
```

For unattended daily advice, keep `make agent-schedule-loop` and `make agent-work-loop`
running as separately supervised processes against the same database as the API. The
scheduler checks each athlete's timezone every 60 seconds and queues that date's
advice after 04:00 local time only when a Plan Version owns the date. On startup it
checks immediately, so a restart after 04:00 catches up for the current local date.
The queue keeps one scheduled task per athlete and local date, even after a completed
task or a timezone change. The worker syncs activities before generating advice.

Daily Advice summarizes the owning Plan Version's seven-day block, recommends how to
execute today's existing workout, and explains its purpose and expected feel. It is
read-only: it does not edit the planned workout or create a pending Recommendation.
`GET /api/v1/today?anchor_date=YYYY-MM-DD` returns the one current advice for that
athlete and local date. A successful manual Garmin sync queues a refresh; a successful
newer run replaces the visible advice while run history remains available. The
frontend observes the returned run and refreshes Today. A separate proposed plan
adjustment remains a Recommendation that requires athlete approval.

If no activity connection is active, Johnny uses already stored activities and marks
advice data coverage limited. An activity sync failure or required reauthentication
blocks fresh advice and leaves earlier text visible with its original generation time,
`stale` freshness, and a failure state. A health-only sync failure may still generate
advice from newly synced activities, marked `limited` because recovery data is missing.
If an advice run finds no Plan Version owning the date, Today reports a no-plan state
rather than inventing a workout. Check the athlete's Data view for connection and sync errors.

Monitor both processes for restarts and errors, and monitor `agent_tasks` for growing
queued or failed work. The current Terraform template provisions only the API service;
a production rollout must separately provision and supervise the scheduler and worker
with the same database and LLM configuration. Running only the API will not deliver
unattended 04:00 advice.

Run the optional live OpenAI smoke after configuring OpenAI settings:

```bash
make smoke-openai
```

The async smoke defaults to deterministic local model behavior. Live OpenAI smoke is opt-in:

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-5-nano
export OPENAI_API_KEY=...
make smoke-agent-openai
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

Garmin Connect schema verification is opt-in because it calls a real user account through `garminconnect==0.3.11`. Keep Garmin passwords and local token-store files outside the database for the live probe. Private/self-hosted Garmin sync may store encrypted session/token payloads in a dedicated database credential store when that mode is configured; Garmin passwords are used only once in memory for session exchange and then discarded. Raw passwords, cookies, unencrypted token-store JSON, and unencrypted provider tokens must never be stored. The probe loads `backend/.env` automatically, and shell environment variables override `.env` values.

```bash
JOHNNY_GARMINCONNECT_SESSION_FILE=/path/to/local/garmin_tokens.json \
PYTHONPATH=backend ./.venv/bin/python -m src.infrastructure.integrations.garminconnect_schema_probe --date 2026-08-19
```

The `JOHNNY_GARMINCONNECT_SESSION_FILE` name is retained for compatibility, but the value is now passed to `garminconnect` as its token-store path. If no valid token-store file exists, the probe can log in with `JOHNNY_GARMINCONNECT_EMAIL` and `JOHNNY_GARMINCONNECT_PASSWORD` and let `garminconnect` write refreshed tokens to that local path. Probe credentials are local-only. Application sync stores either non-sensitive credential references or encrypted private-mode credential payloads, never the raw Garmin password, cookies, unencrypted token-store JSON, or unencrypted provider token values.

Manual end-to-end local testing is documented in `docs/manual_test_runbook.md`.

Training plan integration verification has separate opt-in runbooks:

- [PostgreSQL verification](docs/training_plan_postgresql_verification.md)
- [Live LLM verification](docs/training_plan_live_llm_verification.md)

Recoverable local cleanup archives are kept under the gitignored
`.local-backups/` directory. The 2026-09-27 archive includes a manifest, original
duplicate files, and the previous frontend dependency tree; do not delete or
restore these blindly. Rebuilding the existing frontend lockfile restored tests
and builds in the original project directory without a temporary source copy.
