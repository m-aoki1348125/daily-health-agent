FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY infra/sql ./infra/sql
COPY alembic ./alembic

RUN python -m pip install --upgrade pip && \
    python -m pip install .

ENTRYPOINT ["python", "-m", "app.batch.run_daily_job"]
