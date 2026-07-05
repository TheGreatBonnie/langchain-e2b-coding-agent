"""FastAPI endpoint for serving HN stories with summaries."""

from fastapi import FastAPI, Query
from pydantic import BaseModel

from app.database import get_stories, get_unlimited_count

app = FastAPI(title="HN Summaries API", version="1.0.0")


class StoryOut(BaseModel):
    id: int
    title: str
    url: str | None = None
    score: int
    by: str
    time: int
    descendants: int = 0
    summary: str | None = None
    updated_at: int = 0


class StoryList(BaseModel):
    stories: list[StoryOut]
    count: int


@app.get("/")
def root():
    return {"message": "HN Summaries API", "docs": "/docs", "endpoint": "/stories"}


@app.get("/stories", response_model=StoryList)
def list_stories(limit: int = Query(default=30, ge=1, le=200)):
    """Return top stories with summaries, ordered by score descending."""
    stories = get_stories(limit=limit)
    total = get_unlimited_count()
    return StoryList(stories=[StoryOut(**s) for s in stories], count=total)
