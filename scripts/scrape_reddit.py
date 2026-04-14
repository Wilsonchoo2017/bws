"""CLI entrypoint for the Reddit mention scraper.

Usage:
    python scripts/scrape_reddit.py
    python scripts/scrape_reddit.py --subreddits lego legoinvesting
    python scripts/scrape_reddit.py --limit 500 --no-comments
    python scripts/scrape_reddit.py --init-schema

Environment variables (see config/reddit_env.py):
    REDDIT_CLIENT_ID           (required)
    REDDIT_CLIENT_SECRET       (required)
    REDDIT_USER_AGENT          (optional, defaults to bws-lego-mentions UA)
    REDDIT_RATE_LIMIT_QPM      (optional, default 60)
    REDDIT_BACKOFF_*           (optional, see config/reddit_env.py)
"""

from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, ".")


DEFAULT_SUBREDDITS: tuple[str, ...] = (
    "lego",
    "legoinvesting",
    "legodeal",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LEGO set mentions from target subreddits."
    )
    parser.add_argument(
        "--subreddits",
        nargs="+",
        default=list(DEFAULT_SUBREDDITS),
        help="Subreddits to scrape (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max posts per subreddit (default: REDDIT_MAX_LISTING_PAGES * 100).",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Skip comment scraping (faster, fewer mentions).",
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Run init_schema() before scraping (creates reddit_mentions table).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    logging.getLogger("prawcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger = logging.getLogger("bws.reddit.cli")

    from db.connection import get_connection
    from services.reddit.repository import count_mentions
    from services.reddit.scraper import scrape_all

    conn = get_connection()

    if args.init_schema:
        from db.schema import init_schema

        logger.info("Running init_schema() ...")
        init_schema(conn)

    logger.info(
        "Starting scrape of %d subreddit(s): %s",
        len(args.subreddits),
        ", ".join(args.subreddits),
    )
    results = scrape_all(
        conn,
        subreddits=args.subreddits,
        page_limit=args.limit,
        include_comments=not args.no_comments,
    )

    print("\n=== Reddit Scrape Summary ===")
    total_posts = total_comments = total_mentions = 0
    for result in results:
        total_posts += result.posts_seen
        total_comments += result.comments_seen
        total_mentions += result.mentions_saved
        print(
            f"r/{result.subreddit}: "
            f"{result.posts_seen} posts, "
            f"{result.comments_seen} comments, "
            f"{result.mentions_saved} mentions saved, "
            f"{result.errors} errors"
        )
    print(
        f"TOTAL: {total_posts} posts, {total_comments} comments, "
        f"{total_mentions} mentions saved"
    )

    print("\n=== Per-subreddit DB counts (cumulative) ===")
    for subreddit, count in count_mentions(conn).items():
        print(f"r/{subreddit}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
