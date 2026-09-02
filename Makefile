PYTHON ?= ./.venv/bin/python
DATABASE_URL ?= postgresql+psycopg://johnny:johnny@localhost:5432/johnny

.PHONY: install test run-api db-up db-down migrate seed-demo agent-schedule-once agent-schedule-loop agent-work-one agent-work-drain agent-work-loop smoke-local smoke-openai smoke-agent-local smoke-agent-openai

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

agent-schedule-once:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py schedule-once

agent-schedule-loop:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py schedule-loop

agent-work-one:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py work-one

agent-work-drain:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py work-drain

agent-work-loop:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py work-loop

smoke-local:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/ai_companion_smoke.py

smoke-openai:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/ai_companion_smoke.py --live-openai

smoke-agent-local:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py smoke --workflow all

smoke-agent-openai:
	DATABASE_URL=$(DATABASE_URL) PYTHONPATH=backend $(PYTHON) scripts/agent_runtime.py smoke --workflow conversation --live-openai
