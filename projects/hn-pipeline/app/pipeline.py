"""Pipeline orchestrator - scrape HN, summarize, save to DB."""

import asyncio
import sys

from app.scraper import get_top_stories
from app.summarizer import summarize_story
from app.database import init_db, upsert_stories, update_summary


async def run_pipeline(limit: int = 30, summarize: bool = True):
    """Run the full pipeline: scrape -> (summarize) -> save."""
    import time as _time
    start = _time.time()

    print(f"[pipeline] Initializing database...")
    init_db()

    print(f"[pipeline] Fetching top {limit} stories from HN...")
    stories = await get_top_stories(limit=limit)
    print(f"[pipeline] Got {len(stories)} stories in {_time.time() - start:.1f}s")

    if summarize:
        print("[pipeline] Generating summaries via Ollama (this may take a moment)...")
        t1 = _time.time()
        for story in stories:
            try:
                story["summary"] = summarize_story(story["title"], story.get("url"))
                print(f"  ✓ [{story['score']:>4}] {story['title'][:70]}")
            except Exception as e:
                story["summary"] = None
                print(f"  ✗ [{story['score']:>4}] {story['title'][:70]} — {e}")
        print(f"[pipeline] Summaries done in {_time.time() - t1:.1f}s")
    else:
        for story in stories:
            story["summary"] = None

    print("[pipeline] Saving to SQLite...")
    upsert_stories(stories)

    elapsed = _time.time() - start
    print(f"[pipeline] Done! {len(stories)} stories saved in {elapsed:.1f}s")


def main():
    """CLI entry point."""
    limit = 30
    skip_summary = "--no-summary" in sys.argv

    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    asyncio.run(run_pipeline(limit=limit, summarize=not skip_summary))


if __name__ == "__main__":
    main()
