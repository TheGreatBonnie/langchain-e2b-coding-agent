"""SQLite database module for storing Hacker News stories and summaries."""

import aiosqlite
from contextlib import asynccontextmanager

DATABASE_PATH = "data/stories.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    by TEXT NOT NULL,
    time INTEGER NOT NULL,
    descendants INTEGER DEFAULT 0,
    summary TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stories_score ON stories(score DESC);
CREATE INDEX IF NOT EXISTS idx_stories_time ON stories(time DESC);
"""


async def init_db():
    """Initialize the database schema."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db():
    """Async context manager yielding a database connection."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def upsert_story(db: aiosqlite.Connection, story: dict):
    """Insert or update a story record."""
    await db.execute(
        """
        INSERT INTO stories (id, title, url, score, by, time, descendants)
        VALUES (:id, :title, :url, :score, :by, :time, :descendants)
        ON CONFLICT(id) DO UPDATE SET
            score = excluded.score,
            descendants = excluded.descendants,
            updated_at = CURRENT_TIMESTAMP
        """,
        story,
    )
    await db.commit()


async def update_summary(db: aiosqlite.Connection, story_id: int, summary: str):
    """Update the summary for a given story."""
    await db.execute(
        "UPDATE stories SET summary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (summary, story_id),
    )
    await db.commit()


async def get_stories(db: aiosqlite.Connection, limit: int = 20) -> list[dict]:
    """Retrieve top stories ordered by score descending."""
    cursor = await db.execute(
        "SELECT * FROM stories ORDER BY score DESC LIMIT ?", (limit,)
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_story_by_id(db: aiosqlite.Connection, story_id: int) -> dict | None:
    """Retrieve a single story by its ID."""
    cursor = await db.execute("SELECT * FROM stories WHERE id = ?", (story_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_stories_without_summaries(
    db: aiosqlite.Connection, limit: int = 10
) -> list[dict]:
    """Retrieve stories that don't have a summary yet."""
    cursor = await db.execute(
        "SELECT * FROM stories WHERE summary IS NULL ORDER BY score DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
