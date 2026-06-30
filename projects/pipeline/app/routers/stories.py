"""FastAPI router for story endpoints."""

from fastapi import APIRouter, Query
from typing import List

from app.database import get_db
from app.models import StoryResponse

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("", response_model=List[StoryResponse])
async def list_stories(limit: int = Query(default=20, ge=1, le=100)):
    """Return the top stories from the database, ordered by score."""
    async with get_db() as db:
        from app.database import get_stories
        stories = await get_stories(db, limit=limit)
    return stories


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(story_id: int):
    """Return a single story by ID."""
    async with get_db() as db:
        from app.database import get_story_by_id
        story = await get_story_by_id(db, story_id)
    if not story:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Story not found")
    return story
