"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import init_db
from app.models import PipelineResult
from app.routers import stories
from app.services.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready.")
    yield


app = FastAPI(
    title="HN Summary Pipeline",
    description="Scrapes Hacker News top stories, summarizes them with a local LLM, and serves via API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(stories.router)


@app.get("/")
async def root():
    return {"message": "HN Summary Pipeline API", "docs": "/docs"}


@app.post("/pipeline/run", response_model=PipelineResult)
async def trigger_pipeline(
    story_limit: int = 20,
    summarize_limit: int = 10,
):
    """Manually trigger the pipeline to fetch and summarize stories."""
    result = await run_pipeline(story_limit=story_limit, summarize_limit=summarize_limit)
    return result


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
