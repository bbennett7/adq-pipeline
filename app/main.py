import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cron.scheduler import start_scheduler
from app.db import close_pool
from app.routes import choose, generate, health, resources, run, style

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    await close_pool()


app = FastAPI(title="adq-pipeline", lifespan=lifespan)

app.include_router(health.router)
app.include_router(run.router)
app.include_router(generate.router)
app.include_router(style.router)
app.include_router(choose.router)
app.include_router(resources.router)
