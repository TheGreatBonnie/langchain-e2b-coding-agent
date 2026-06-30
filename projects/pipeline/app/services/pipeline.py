"""Pipeline orchestrator: fetches HN stories, summarizes them, and stores in SQLite."""

import asyncio
import logging

from app.database import get_db, upsert_story, update_summary, get_stories_without_summaries
from app.services.hn_client import fetch_top_stories
from app.services.llm_client import summarize_story

logger = logging.getLogger(__name__)


async def run_pipeline(story_limit: int = 20, summarize_limit: int = 10):
    """Run the full pipeline: fetch stories, store them, then summarize.

    Args:
        story_limit: Number of top stories to fetch from HN.
        summarize_limit: Maximum number of stories to summarize per run.

    Returns:
        dict with counts of fetched and summarized stories.
    """
    # Step 1: Fetch stories from Hacker News
    logger.info("Fetching top %d stories from Hacker News...", story_limit)
    stories = await fetch_top_stories(limit=story_limit)
    logger.info("Fetched %d stories", len(stories))

    # Step 2: Store stories in database
    fetched_count = 0
    async with get_db() as db:
        for story in stories:
            await upsert_story(db, story)
            fetched_count += 1
    logger.info("Stored %d stories in database", fetched_count)

    # Step 3: Summarize stories without summaries
    async with get_db() as db:
        unsummarized = await get_stories_without_summaries(db, limit=summarize_limit)

    logger.info("Summarizing %d stories...", len(unsummarized))
    summarized_count = 0
    for story in unsummarized:
        summary = await summarize_story(
            title=story["title"],
            url=story["url"],
            score=story["score"],
            descendants=story["descendants"],
        )
        async with get_db() as db:
            await update_summary(db, story["id"], summary)
        summarized_count += 1
        logger.info("Summarized story %d: %s", story["id"], story["title"][:50])

    logger.info("Pipeline complete: %d fetched, %d summarized", fetched_count, summarized_count)
    return {"fetched": fetched_count, "summarized": summarized_count}
