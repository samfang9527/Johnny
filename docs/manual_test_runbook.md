# Johnny Manual Test Runbook

This runbook verifies the local MVP companion loop:

```text
Seed training data -> API analytics context -> companion conversation -> pending recommendation -> user decision -> local smoke evidence
```

## Prerequisites

- Python environment installed at `./.venv`
- Frontend dependencies installed under `frontend/node_modules`
- Docker Desktop or compatible `docker compose`
- Optional for live model smoke: `OPENAI_API_KEY` or `LLM_API_KEY`

## 1. Start Local PostgreSQL

```bash
make db-up
```

Expected:

- `johnny-postgres` container is healthy.
- PostgreSQL is reachable at `postgresql+psycopg://johnny:johnny@localhost:5432/johnny`.

## 2. Apply Migrations And Seed Demo Data

```bash
make migrate
make seed-demo
```

Expected:

- Alembic upgrades to the latest revision.
- Seed command prints `Seeded Johnny demo data for user local-user`.

## 3. Start Backend

```bash
make run-api
```

Expected:

- FastAPI runs at `http://127.0.0.1:8000`.
- `curl http://127.0.0.1:8000/health` returns `status: ok`, `service: Johnny-api`, and `worker_contract` with a build (`unknown` locally) and supported versions `[0,1]`.
- `curl http://127.0.0.1:8000/ready` returns `status: ready` and the same declared worker contract.

## 4. Start Frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Expected:

- Vite runs at `http://localhost:5173`, or a nearby fallback port if `5173` is already in use.
- The app loads without browser CORS errors.
- Google sign-in uses the same local host spelling for the browser, API, and OAuth callback. For example, if the app is opened on `http://localhost:5173`, authorize `http://localhost:8000/api/v1/auth/google/callback` in Google Cloud and leave `VITE_API_BASE_URL` unset or set it to `http://localhost:8000`.

## 5. Verify Backend-Backed UI Hydration

Open `http://localhost:5173`.

Expected:

- Today page shows seeded backend data such as `Local Half Marathon`, `Demo Build Block` workout context, and `Review today's training context`.
- Calendar shows seeded workouts from `/api/v1/training-plans`.
- Agent Inbox shows backend recommendations from `/api/v1/recommendations`.

## 6. Verify Conversation Companion Path

Go to `對話`, enter:

```text
How should I adjust today's training?
```

Expected:

- The composer shows `Johnny 已收到問題 · <run id>`.
- A Johnny response appears in the message thread.
- Backend creates an `agent_runs` row and a pending recommendation through the `RunningCompanionAgent` tool path.

API check:

```bash
curl -s -H "Content-Type: application/json" \
  -H "X-Johnny-User-Id: local-user" \
  -d '{"content":"How should I adjust today'\''s training?"}' \
  http://127.0.0.1:8000/api/v1/conversations/messages
```

Expected:

- Response `data.run_ref` is a real agent run id.
- Response `data.message.agent_status` is `completed`.

## 7. Verify Recommendation Decision

On Today or Agent Inbox, click `接受調整`.

Expected:

- Button enters a busy state briefly.
- Recommendation status changes to accepted.
- `GET /api/v1/recommendations` shows the recommendation with `decision: accepted`.

## 8. Run Local Companion Smoke

```bash
make smoke-local
```

Expected:

- Prints `status=completed`.
- Prints `provider=local`.
- Prints a non-empty `run_id`.
- Prints a `recommendation_id`.

## 9. Verify Async Agent Runtime

Queue async runs through the API:

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

Expected:

- Each response returns `status: queued`, a `workflow_name`, and a `poll_url`.
- Repeating the same daily recommendation request without `force` returns the same queued run.
- Sending `force: true` creates a distinct daily rerun.

Drain local work:

```bash
make agent-work-drain
```

Poll the returned run URLs:

```bash
curl -s -H "X-Johnny-User-Id: local-user" \
  http://127.0.0.1:8000/api/v1/agent-runs/<run-id>

curl -s -H "X-Johnny-User-Id: local-user" \
  http://127.0.0.1:8000/api/v1/agent-runs/<run-id>/steps
```

Expected:

- Run status becomes `completed`.
- Run steps show ordered tool calls.
- `GET /api/v1/recommendations` includes a daily recommendation.
- `GET /api/v1/training-plans` includes a generated `active` plan.

Run the deterministic end-to-end async smoke:

```bash
make smoke-agent-local
```

## 10. Optional Live OpenAI Smoke

Set live model variables in your shell or `backend/.env`:

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-5-nano
export OPENAI_API_KEY=...
```

Then run:

```bash
make smoke-openai
```

For the async runtime command, use:

```bash
make smoke-agent-openai
```

Expected:

- Prints `status=completed`.
- Prints `provider=openai`.
- Records token usage on the `agent_runs` row when OpenAI returns usage.

If the command exits with code `2`, required OpenAI settings are missing.

## Coaching Detail Acceptance

Use a disposable PostgreSQL database whose name contains `test`; do not point `JOHNNY_TEST_DATABASE_URL` at the live `johnny` database. Apply Alembic through head, then run:

```bash
JOHNNY_TEST_DATABASE_URL='postgresql+psycopg://johnny:johnny@localhost:5432/johnny_test_coaching' \
  PYTHONPATH=.:backend ./.venv/bin/python -m pytest backend/tests -q -rs
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run verify:tokens
```

The integration acceptance test exercises five historical Daily Review slots, a user-requested Workout Advice, three detail resources, replay after a worker interruption, one late changed batch and one coalesced successor. The PostgreSQL migration suite checks the `0012_coaching_history` to head upgrade and legacy activity/pairing preservation. Rehearse a `pg_dump -Fc`/`pg_restore --exit-on-error` into a separate disposable database, comparing Alembic revision, table and representative row counts before considering release. Inspect task rows whose type/version is unsupported; they must remain queued. The flag-off check confirms detail tasks defer while legacy advice stays readable. See [release runbook](deployment-v1.md#coaching-detail-cutover-additive-release) for production sequencing and [verification record](verification/2026-10-22-coaching-detail-acceptance.md) for measured local results and remaining live gates.

## 11. Cleanup

Stop app processes with `Ctrl+C`.

Stop PostgreSQL without deleting data:

```bash
make db-down
```

Delete the Docker volume only when you intentionally want a clean database:

```bash
docker volume rm johnny_johnny-postgres-data
```

## Current Manual-Test Limits

- Local mode is deterministic and network-free; it proves runtime wiring, not model quality.
- Live OpenAI smoke is opt-in and depends on the configured model and API key.
- The local queue is database-backed and AWS-shaped, but it is not SQS.
- Notification delivery still verifies at application/unit-test level only; no production LINE delivery worker is part of this runbook.
- Conversation history is currently client-local after submit; persisted conversation threads remain future work.
