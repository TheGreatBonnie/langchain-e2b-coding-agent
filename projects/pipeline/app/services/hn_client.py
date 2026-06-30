"""Hacker News API client for fetching top stories."""

import httpx

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


async def fetch_top_story_ids(limit: int = 30) -> list[int]:
    """Fetch the top story IDs from Hacker News."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{HN_BASE_URL}/topstories.json")
        response.raise_for_status()
        ids = response.json()
        return ids[:limit]


async def fetch_item(item_id: int) -> dict | None:
    """Fetch a single item (story) from Hacker News by ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{HN_BASE_URL}/item/{item_id}.json")
        response.raise_for_status()
        return response.json()


async def fetch_top_stories(limit: int = 30) -> list[dict]:
    """Fetch full details for the top N stories."""
    story_ids = await fetch_top_story_ids(limit)
    stories = []

    for story_id in story_ids:
        item = await fetch_item(story_id)
        if item and item.get("type") == "story" and not item.get("deleted") and not item.get("dead"):
            stories.append(
                {
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "url": item.get("url"),
                    "score": item.get("score", 0),
                    "by": item.get("by", ""),
                    "time": item.get("time", 0),
                    "descendants": item.get("descendants", 0),
                }
            )

    return stories
