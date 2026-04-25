.PHONY: dev dev-watch lint format e2e

dev:
	.venv/bin/python src/server.py

dev-watch:
	.venv/bin/uvicorn server:app --app-dir src --host 0.0.0.0 --port 8321 --reload

lint:
	ruff check .

format:
	ruff format .

e2e:
	OTEL_ENABLED=false .venv/bin/python -m pytest e2e -v -s
