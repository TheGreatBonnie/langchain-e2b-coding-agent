"""Hacker News scraper - fetches top stories via the official HN API."""

import asyncio
import aiohttp

HN_BASE = "https://hacker-news.firebaseio.com/v0"


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict | None:
    """Fetch a single JSON URL, returning None on error."""
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def get_top_stories(limit: int = 30) -> list[dict]:
    """Fetch the top `limit` stories from Hacker News.

    Returns a list of story dicts with at minimum: id, title, url, score, by, time, descendants.
    """
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        ids = await _fetch_json(session, f"{HN_BASE}/topstories.json")
        if not ids:
            return []

        tasks = [
            _fetch_json(session, f"{HN_BASE}/item/{story_id}.json")
            for story_id in ids[:limit]
        ]
        results = await asyncio.gather(*tasks)

        stories = []
        for item in results:
            if item and item.get("type") == "story" and item.get("title"):
                stories.append(
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "url": item.get("url"),
                        "score": item.get("score", 0),
                        "by": item.get("by", ""),
                        "time": item.get("time", 0),
                        "descendants": item.get("descendants", 0),
                        "text": item.get("text"),
                    }
                )
        return stories


def get_top_stories_sync(limit: int = 30) -> list[dict]:
    """Synchronous wrapper for get_top_stories."""
    return asyncio.run(get_top_stories(limit))
