"""Load Reddit OAuth credentials and scraper settings from .env file.

Reddit's API requires a descriptive User-Agent per their API rules:
https://github.com/reddit-archive/reddit/wiki/API
Format: "platform:app_id:version (by /u/username)".
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# Reddit OAuth allows up to 100 requests/minute per client for script apps.
# We cap well below that (60 QPM = 1 QPS) to leave headroom for bursts,
# parallel workers, and any shared usage of the same OAuth credentials.
REDDIT_RATE_LIMIT_QPM = int(os.environ.get("REDDIT_RATE_LIMIT_QPM", "60"))

# Exponential backoff parameters for 429/5xx responses.
REDDIT_BACKOFF_INITIAL_SECONDS = float(
    os.environ.get("REDDIT_BACKOFF_INITIAL_SECONDS", "5")
)
REDDIT_BACKOFF_MAX_SECONDS = float(
    os.environ.get("REDDIT_BACKOFF_MAX_SECONDS", "600")
)
REDDIT_BACKOFF_MULTIPLIER = float(
    os.environ.get("REDDIT_BACKOFF_MULTIPLIER", "2.0")
)
REDDIT_MAX_RETRIES = int(os.environ.get("REDDIT_MAX_RETRIES", "5"))

# How deep to page into each listing on each run. Reddit caps listings at
# ~1000 items no matter how many requests you make, so there is no benefit
# to setting this above 10 pages of 100.
REDDIT_MAX_LISTING_PAGES = int(os.environ.get("REDDIT_MAX_LISTING_PAGES", "10"))


@dataclass(frozen=True)
class RedditCredentials:
    """Reddit OAuth credentials for a script-type app."""

    client_id: str
    client_secret: str
    user_agent: str
    username: str | None = None
    password: str | None = None


def get_reddit_credentials() -> RedditCredentials:
    """Load Reddit OAuth credentials from environment variables.

    Script apps only need client_id + client_secret for read-only access
    via application-only OAuth. username/password are optional and are
    only needed if we ever want to act as a user (we don't).

    Raises:
        ValueError: If required credentials are missing.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    user_agent = os.environ.get(
        "REDDIT_USER_AGENT",
        "python:bws-lego-mentions:0.1 (by /u/bws_lego_research)",
    )
    if not client_id or not client_secret:
        raise ValueError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in .env"
        )
    return RedditCredentials(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        username=os.environ.get("REDDIT_USERNAME") or None,
        password=os.environ.get("REDDIT_PASSWORD") or None,
    )
