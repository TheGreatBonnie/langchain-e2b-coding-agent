"""SQLite storage layer for HN stories."""

import sqlite3

DB_PATH = "/home/user/projects/hn-pipeline/data/hn_stories.db"


def get_conn() -> sqlite3.Connection:
    """Create a new SQLite connection per call (safe for threaded use)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create the stories table if it doesn't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id          INTEGER PRIMARY KEY,
                title       TEXT NOT NULL,
                url         TEXT,
                score       INTEGER DEFAULT 0,
                by          TEXT,
                time        INTEGER,
                descendants INTEGER DEFAULT 0,
                summary     TEXT,
                updated_at  INTEGER DEFAULT (strftime('%s','now'))
            )
        """)


def upsert_stories(stories: list[dict]):
    """Bulk upsert stories into the database."""
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO stories (id, title, url, score, by, time, descendants, summary)
            VALUES (:id, :title, :url, :score, :by, :time, :descendants, :summary)
            ON CONFLICT(id) DO UPDATE SET
                title       = excluded.title,
                url         = excluded.url,
                score       = excluded.score,
                by          = excluded.by,
                time        = excluded.time,
                descendants = excluded.descendants,
                summary     = COALESCE(excluded.summary, stories.summary),
                updated_at  = strftime('%s','now')
            """,
            stories,
        )


def update_summary(story_id: int, summary: str):
    """Update the summary for a single story."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE stories SET summary = ?, updated_at = strftime('%s','now') WHERE id = ?",
            (summary, story_id),
        )


def get_stories(limit: int = 30) -> list[dict]:
    """Fetch stories ordered by score descending."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM stories ORDER BY score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_unlimited_count() -> int:
    """Return the total count of stored stories."""
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM stories").fetchone()
        return row["cnt"] if row else 0
