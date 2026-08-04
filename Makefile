.PHONY: dev test lint format deploy

# Stamps the running image with its commit so /health can prove what is live.
deploy:
	fly deploy --build-arg GIT_SHA=$$(git rev-parse --short HEAD)
	@echo "deployed $$(git rev-parse --short HEAD) — verifying:"
	@curl -s https://adq-pipeline.fly.dev/health

dev:
	uv run uvicorn app.main:app --reload --port 8080

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
