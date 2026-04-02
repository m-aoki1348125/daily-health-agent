PYTHON ?= python3

.PHONY: install lint format typecheck test run-daily run-weekly run-monthly

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

typecheck:
	$(PYTHON) -m mypy app tests

test:
	$(PYTHON) -m pytest

run-daily:
	$(PYTHON) -m app.batch.run_daily_job

run-weekly:
	$(PYTHON) -m app.batch.run_weekly_job

run-monthly:
	$(PYTHON) -m app.batch.run_monthly_job
