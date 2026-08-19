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
python -m venv .venv
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

Local development uses PostgreSQL through `DATABASE_URL`. Alembic migration setup is intentionally deferred to `openspec/changes/02-persistence-schema`.
