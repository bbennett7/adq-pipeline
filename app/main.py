import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.anthropic import close_client as close_anthropic
from app.clients.gemini import close_client as close_gemini
from app.clients.ground_ctrl import close_ground_ctrl
from app.clients.openai import close_client as close_openai
from app.routes import answers, health, resources, run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.routes.run import wait_for_active_runs

    await wait_for_active_runs()
    await close_anthropic()
    await close_openai()
    await close_gemini()
    await close_ground_ctrl()


app = FastAPI(
    title="adq-pipeline",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(health.router)
app.include_router(run.router)
app.include_router(resources.router)
app.include_router(answers.router)
