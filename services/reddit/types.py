"""Immutable data types for the Reddit scraper."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RedditMention:
    """A single set-number mention extracted from a Reddit post or comment."""

    set_number: str
    subreddit: str
    post_id: str
    comment_id: str | None
    created_at: datetime
    score: int | None
    num_comments: int | None
    author_hash: str | None
    title: str | None
    body_preview: str | None
    permalink: str | None
    is_comment: bool


@dataclass(frozen=True)
class SubredditScrapeResult:
    """Per-subreddit summary returned by the scraper."""

    subreddit: str
    posts_seen: int
    comments_seen: int
    mentions_saved: int
    errors: int
    cursor_fullname: str | None
