PYTHON ?= ./.venv/bin/python
DATABASE_URL ?= postgresql+psycopg://johnny:johnny@localhost:5432/johnny

.PHONY: install test run-api db-up db-down migrate seed-demo smoke-local smoke-openai

install:
	$(PYTHON) -m pip install -r backend/requirements/dev.txt

test:
	$(PYTHON) -m pytest backend/tests

run-api:
	PYTHONPATH=backend $(PYTHON) -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) -m alembic -c backend/alembic.ini upgrade head

seed-demo:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/seed_demo_data.py

smoke-local:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/ai_companion_smoke.py

smoke-openai:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/ai_companion_smoke.py --live-openai
