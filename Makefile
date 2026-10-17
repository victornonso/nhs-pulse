.PHONY: install migrate collect train api web test
install:
	uv sync --frozen
	npm --prefix apps/web ci
migrate:
	uv run python -m tools.migrate
	uv run alembic upgrade head
collect:
	uv run python -m tools.seed_sources
	uv run python -m pipelines.orchestration.collect --source ae --backfill 36
	uv run python -m pipelines.orchestration.collect --source diagnostics --backfill 12
	uv run python -m pipelines.orchestration.collect --source beds_overnight --backfill 4
	uv run python -m pipelines.orchestration.collect --source beds_day --backfill 4
train:
	uv run python -m services.forecasting.train
api:
	uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8020
web:
	npm --prefix apps/web run dev
test:
	uv run pytest -q
	npm --prefix apps/web run typecheck
