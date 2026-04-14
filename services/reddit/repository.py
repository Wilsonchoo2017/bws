"""Persistence for Reddit mentions and scrape cursors."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.reddit.types import RedditMention

logger = logging.getLogger("bws.reddit.repository")


def save_mentions(conn: Any, mentions: list[RedditMention]) -> int:
    """Insert mention rows, ignoring duplicates.

    Duplicates are identified by the `(subreddit, post_id, comment_id,
    set_number)` UNIQUE constraint on `reddit_mentions`. We rely on the
    constraint so we don't have to pre-check every row.

    Returns the number of rows actually inserted.
    """
    if not mentions:
        return 0

    inserted = 0
    for mention in mentions:
        row_id = conn.execute(
            "SELECT nextval('reddit_mentions_id_seq')"
        ).fetchone()[0]
        try:
            conn.execute(
                """
                INSERT INTO reddit_mentions (
                    id, set_number, subreddit, post_id, comment_id,
                    created_at, score, num_comments, author_hash,
                    title, body_preview, permalink, is_comment,
                    scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (subreddit, post_id, comment_id, set_number)
                DO NOTHING
                """,
                [
                    row_id,
                    mention.set_number,
                    mention.subreddit,
                    mention.post_id,
                    mention.comment_id,
                    mention.created_at,
                    mention.score,
                    mention.num_comments,
                    mention.author_hash,
                    mention.title,
                    mention.body_preview,
                    mention.permalink,
                    mention.is_comment,
                    datetime.now(tz=timezone.utc),
                ],
            )
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to insert mention for %s in r/%s: %s",
                mention.set_number,
                mention.subreddit,
                exc,
            )
    return inserted


def get_cursor(conn: Any, subreddit: str, listing: str) -> str | None:
    """Fetch the last-seen fullname for a subreddit listing, or None."""
    row = conn.execute(
        """
        SELECT last_fullname FROM reddit_scrape_cursors
        WHERE subreddit = ? AND listing = ?
        """,
        [subreddit, listing],
    ).fetchone()
    return row[0] if row else None


def upsert_cursor(
    conn: Any,
    subreddit: str,
    listing: str,
    *,
    last_fullname: str | None,
    last_created_utc: datetime | None,
    posts_seen: int,
    mentions_saved: int,
) -> None:
    """Upsert the checkpoint for a (subreddit, listing) pair."""
    conn.execute(
        """
        INSERT INTO reddit_scrape_cursors (
            subreddit, listing, last_fullname, last_created_utc,
            last_run_at, posts_seen, mentions_saved
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (subreddit, listing) DO UPDATE SET
            last_fullname = COALESCE(EXCLUDED.last_fullname,
                                     reddit_scrape_cursors.last_fullname),
            last_created_utc = COALESCE(EXCLUDED.last_created_utc,
                                        reddit_scrape_cursors.last_created_utc),
            last_run_at = EXCLUDED.last_run_at,
            posts_seen = reddit_scrape_cursors.posts_seen + EXCLUDED.posts_seen,
            mentions_saved = reddit_scrape_cursors.mentions_saved
                + EXCLUDED.mentions_saved
        """,
        [
            subreddit,
            listing,
            last_fullname,
            last_created_utc,
            datetime.now(tz=timezone.utc),
            posts_seen,
            mentions_saved,
        ],
    )


def count_mentions(conn: Any) -> dict[str, int]:
    """Return per-subreddit mention counts (for coverage reporting)."""
    rows = conn.execute(
        """
        SELECT subreddit, COUNT(*) FROM reddit_mentions
        GROUP BY subreddit ORDER BY 2 DESC
        """
    ).fetchall()
    return {row[0]: row[1] for row in rows}
