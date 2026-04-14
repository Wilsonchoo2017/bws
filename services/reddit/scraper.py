"""Reddit subreddit scraper -- extracts set-number mentions into the DB.

Design notes
------------
- One scraper invocation iterates a list of subreddits in sequence (not
  in parallel) to keep the per-client rate budget simple. Parallelism
  across OAuth clients is a future optimization.
- For each subreddit we walk `/new` backwards until we hit either the
  checkpoint fullname or the configured page cap. Reddit listings are
  capped at ~1000 items, so a first-run backfill captures a rolling
  window, not a full archive. That's acceptable for v1 -- the plan is
  PRAW-only, 2018-present, with the understanding that coverage on
  older cohorts is poor.
- Comments on each post are fetched with `replace_more(limit=0)` which
  drops the "load more comments" links. We accept missing some deep
  comment threads in exchange for a bounded request budget.
- Every mention is persisted individually so a mid-run failure doesn't
  lose data (the unique constraint dedupes reruns).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from config.reddit_env import REDDIT_MAX_LISTING_PAGES
from services.reddit.client import RedditClient
from services.reddit.extractor import extract_mentions, load_known_set_numbers
from services.reddit.repository import save_mentions, upsert_cursor
from services.reddit.types import RedditMention, SubredditScrapeResult

logger = logging.getLogger("bws.reddit.scraper")

# Cap the body preview we store -- just enough to eyeball a match
# during debugging, not enough to bloat the table.
_BODY_PREVIEW_CHARS = 400


def _hash_author(author: Any) -> str | None:
    """One-way hash of an author name so we can count unique authors
    without retaining PII. Returns None for `[deleted]` / None inputs.
    """
    name = getattr(author, "name", None) if author else None
    if not name or name == "[deleted]":
        return None
    return hashlib.sha1(name.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _to_utc(epoch_seconds: float | None) -> datetime | None:
    if epoch_seconds is None:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)


def _make_submission_mentions(
    submission: Any,
    subreddit: str,
    known_sets: frozenset[str],
) -> list[RedditMention]:
    """Extract mentions from a submission's title + selftext."""
    title = getattr(submission, "title", "") or ""
    selftext = getattr(submission, "selftext", "") or ""
    combined = f"{title}\n{selftext}"
    matches = extract_mentions(combined, known_sets)
    if not matches:
        return []

    created = _to_utc(getattr(submission, "created_utc", None))
    if created is None:
        return []

    body_preview = (selftext or title)[:_BODY_PREVIEW_CHARS] or None
    permalink = getattr(submission, "permalink", None)
    author_hash = _hash_author(getattr(submission, "author", None))
    score = int(getattr(submission, "score", 0) or 0)
    num_comments = int(getattr(submission, "num_comments", 0) or 0)

    return [
        RedditMention(
            set_number=match.set_number,
            subreddit=subreddit,
            post_id=submission.id,
            comment_id=None,
            created_at=created,
            score=score,
            num_comments=num_comments,
            author_hash=author_hash,
            title=title[:_BODY_PREVIEW_CHARS] or None,
            body_preview=body_preview,
            permalink=permalink,
            is_comment=False,
        )
        for match in matches
    ]


def _make_comment_mentions(
    comment: Any,
    submission: Any,
    subreddit: str,
    known_sets: frozenset[str],
) -> list[RedditMention]:
    """Extract mentions from a single comment body."""
    body = getattr(comment, "body", "") or ""
    matches = extract_mentions(body, known_sets)
    if not matches:
        return []

    created = _to_utc(getattr(comment, "created_utc", None))
    if created is None:
        return []

    author_hash = _hash_author(getattr(comment, "author", None))
    score = int(getattr(comment, "score", 0) or 0)
    permalink = getattr(comment, "permalink", None)

    return [
        RedditMention(
            set_number=match.set_number,
            subreddit=subreddit,
            post_id=submission.id,
            comment_id=comment.id,
            created_at=created,
            score=score,
            num_comments=None,
            author_hash=author_hash,
            title=None,
            body_preview=body[:_BODY_PREVIEW_CHARS] or None,
            permalink=permalink,
            is_comment=True,
        )
        for match in matches
    ]


def scrape_subreddit(
    conn: Any,
    client: RedditClient,
    subreddit: str,
    *,
    known_sets: frozenset[str],
    page_limit: int = REDDIT_MAX_LISTING_PAGES * 100,
    include_comments: bool = True,
) -> SubredditScrapeResult:
    """Walk r/<subreddit>/new, extract mentions, persist to DB.

    We use the database as the source of truth for dedup (the UNIQUE
    constraint on `reddit_mentions` protects us), and we maintain a
    cursor row in `reddit_scrape_cursors` so repeat runs can skip
    already-seen pages.

    `page_limit` caps total items inspected in this run to bound the
    request budget. The token bucket enforces QPS under that cap.
    """
    posts_seen = 0
    comments_seen = 0
    mentions_saved = 0
    errors = 0
    newest_fullname: str | None = None
    newest_created: datetime | None = None

    logger.info(
        "Scraping r/%s (limit=%d, include_comments=%s)",
        subreddit,
        page_limit,
        include_comments,
    )

    try:
        for submission in client.iter_subreddit_new(
            subreddit, limit=page_limit
        ):
            posts_seen += 1

            if newest_fullname is None:
                newest_fullname = f"t3_{submission.id}"
                newest_created = _to_utc(
                    getattr(submission, "created_utc", None)
                )

            submission_mentions = _make_submission_mentions(
                submission, subreddit, known_sets
            )
            if submission_mentions:
                mentions_saved += save_mentions(conn, submission_mentions)

            if include_comments:
                try:
                    for comment in client.iter_submission_comments(submission):
                        comments_seen += 1
                        comment_mentions = _make_comment_mentions(
                            comment, submission, subreddit, known_sets
                        )
                        if comment_mentions:
                            mentions_saved += save_mentions(
                                conn, comment_mentions
                            )
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    logger.warning(
                        "Comment fetch failed for %s in r/%s: %s",
                        submission.id,
                        subreddit,
                        exc,
                    )

            if posts_seen % 50 == 0:
                logger.info(
                    "r/%s progress: %d posts, %d comments, %d mentions",
                    subreddit,
                    posts_seen,
                    comments_seen,
                    mentions_saved,
                )

    except Exception as exc:  # noqa: BLE001
        errors += 1
        logger.error(
            "Listing walk failed for r/%s after %d posts: %s",
            subreddit,
            posts_seen,
            exc,
        )

    upsert_cursor(
        conn,
        subreddit,
        listing="new",
        last_fullname=newest_fullname,
        last_created_utc=newest_created,
        posts_seen=posts_seen,
        mentions_saved=mentions_saved,
    )

    logger.info(
        "r/%s done: %d posts, %d comments, %d mentions, %d errors",
        subreddit,
        posts_seen,
        comments_seen,
        mentions_saved,
        errors,
    )
    return SubredditScrapeResult(
        subreddit=subreddit,
        posts_seen=posts_seen,
        comments_seen=comments_seen,
        mentions_saved=mentions_saved,
        errors=errors,
        cursor_fullname=newest_fullname,
    )


def scrape_all(
    conn: Any,
    subreddits: list[str],
    *,
    page_limit: int | None = None,
    include_comments: bool = True,
) -> list[SubredditScrapeResult]:
    """Run `scrape_subreddit` across every subreddit in order.

    Subreddits are processed sequentially so a single token bucket can
    govern all of them. If one subreddit errors out, we continue to
    the next.
    """
    client = RedditClient()
    known_sets = load_known_set_numbers(conn)
    logger.info(
        "Loaded %d known set numbers from lego_items catalog",
        len(known_sets),
    )

    results: list[SubredditScrapeResult] = []
    kwargs: dict[str, Any] = {
        "known_sets": known_sets,
        "include_comments": include_comments,
    }
    if page_limit is not None:
        kwargs["page_limit"] = page_limit

    for subreddit in subreddits:
        try:
            result = scrape_subreddit(conn, client, subreddit, **kwargs)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unrecoverable error scraping r/%s: %s", subreddit, exc
            )
            results.append(
                SubredditScrapeResult(
                    subreddit=subreddit,
                    posts_seen=0,
                    comments_seen=0,
                    mentions_saved=0,
                    errors=1,
                    cursor_fullname=None,
                )
            )
    return results
