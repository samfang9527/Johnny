PYTHON ?= python3

.PHONY: install test run-api

install:
	$(PYTHON) -m pip install -r backend/requirements/dev.txt

test:
	$(PYTHON) -m pytest backend/tests

run-api:
	cd backend && PYTHONPATH=src $(PYTHON) -m Johnny
