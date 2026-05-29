.PHONY: dev test lint format

dev:
	uv run uvicorn app.main:app --reload --port 8080

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
