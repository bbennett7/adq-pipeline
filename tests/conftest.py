import os

os.environ.setdefault("PIPELINE_SECRET", "test-secret")
os.environ.setdefault("GROUND_CTRL_URL", "https://ground-ctrl.test")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all client singletons between tests."""
    import app.clients.anthropic as anth_mod
    import app.clients.gemini as gem_mod
    import app.clients.ground_ctrl as gc_mod
    import app.clients.openai as oai_mod

    gc_mod._instance = None
    anth_mod._client = None
    oai_mod._client = None
    gem_mod._client = None
    yield
    gc_mod._instance = None
    anth_mod._client = None
    oai_mod._client = None
    gem_mod._client = None


@pytest.fixture()
def _no_scheduler():
    """Prevent scheduler from starting during tests."""
    with patch("app.cron.scheduler.start_scheduler"):
        yield


@pytest.fixture()
def _no_db():
    """Prevent DB pool from connecting during tests."""
    with patch("app.db.close_pool", new_callable=AsyncMock):
        yield


@pytest.fixture()
def client(_no_scheduler, _no_db):
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def client_no_raise(_no_scheduler, _no_db):
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-secret"}
