"""Rate-limited, retrying Reddit API client (PRAW-backed).

Respects Reddit's API rules:
- OAuth via a script-type app (client_id + client_secret).
- Descriptive User-Agent on every request (see config/reddit_env.py).
- Hard rate cap well below the 100 QPM ceiling (token bucket).
- Exponential backoff on 429 / 5xx with Retry-After honored when present.
- No more than one in-flight request per client (PRAW default).

We wrap PRAW's iterators with a `safe_iter` helper so every yielded item
has first been rate-limited and any transient failure has been retried.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar

from config.reddit_env import (
    REDDIT_BACKOFF_INITIAL_SECONDS,
    REDDIT_BACKOFF_MAX_SECONDS,
    REDDIT_BACKOFF_MULTIPLIER,
    REDDIT_MAX_RETRIES,
    REDDIT_RATE_LIMIT_QPM,
    RedditCredentials,
    get_reddit_credentials,
)
from services.reddit.rate_limiter import TokenBucketRateLimiter

if TYPE_CHECKING:
    import praw

logger = logging.getLogger("bws.reddit.client")

T = TypeVar("T")


def _extract_retry_after(exc: Exception) -> float | None:
    """Pull a Retry-After hint out of a PRAW exception, if present."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: Exception) -> bool:
    """Return True for transient errors worth retrying.

    PRAW surfaces HTTP status codes via prawcore exceptions:
    - TooManyRequests (429)
    - ServerError (5xx)
    - RequestException (network/connection)
    - ResponseException (wraps most HTTP errors)
    We retry on these; anything else (401/403/404, parsing, user bugs)
    should propagate immediately.
    """
    try:
        import prawcore
    except ImportError:
        return False

    retryable_types: tuple[type[Exception], ...] = (
        prawcore.TooManyRequests,
        prawcore.ServerError,
        prawcore.RequestException,
    )
    if isinstance(exc, retryable_types):
        return True

    # ResponseException wraps 5xx too; inspect status if available.
    if isinstance(exc, prawcore.ResponseException):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None and (status == 429 or 500 <= status < 600):
            return True

    return False


class RedditClient:
    """Facade around PRAW that enforces rate limiting and retries.

    Usage:
        client = RedditClient()
        for submission in client.iter_new("legoinvesting", limit=500):
            ...

    The client is safe to share across threads -- the rate limiter is
    thread-safe and PRAW's Reddit instance is reentrant for read-only
    script-app usage.
    """

    def __init__(
        self,
        credentials: RedditCredentials | None = None,
        rate_limit_qpm: int = REDDIT_RATE_LIMIT_QPM,
    ) -> None:
        self._credentials = credentials or get_reddit_credentials()
        self._rate_limiter = TokenBucketRateLimiter(rate_limit_qpm)
        self._reddit: praw.Reddit | None = None

    def _get_reddit(self) -> praw.Reddit:
        """Lazily initialize the PRAW Reddit instance.

        Deferred so module import doesn't fail when PRAW is not installed.
        """
        if self._reddit is not None:
            return self._reddit
        try:
            import praw
        except ImportError as exc:
            raise RuntimeError(
                "praw is not installed. Run: uv add praw  (or pip install praw)"
            ) from exc

        # check_for_async=False silences PRAW's warning when used from
        # a non-async context. ratelimit_seconds=0 disables PRAW's built-in
        # sleep so our token bucket is the single source of truth.
        self._reddit = praw.Reddit(
            client_id=self._credentials.client_id,
            client_secret=self._credentials.client_secret,
            user_agent=self._credentials.user_agent,
            username=self._credentials.username,
            password=self._credentials.password,
            check_for_async=False,
            ratelimit_seconds=0,
        )
        self._reddit.read_only = (
            self._credentials.username is None
            or self._credentials.password is None
        )
        return self._reddit

    def _compute_backoff(self, attempt: int, hint_seconds: float | None) -> float:
        """Exponential backoff with jitter, clamped to REDDIT_BACKOFF_MAX_SECONDS.

        If the server gave us a Retry-After hint, honor it as a floor.
        """
        base = REDDIT_BACKOFF_INITIAL_SECONDS * (
            REDDIT_BACKOFF_MULTIPLIER ** (attempt - 1)
        )
        jitter = random.uniform(0, base * 0.25)
        delay = min(REDDIT_BACKOFF_MAX_SECONDS, base + jitter)
        if hint_seconds is not None:
            delay = max(delay, hint_seconds)
        return delay

    def call(self, operation: Callable[[], T], *, description: str = "") -> T:
        """Execute `operation` under rate limiting + retry policy.

        `operation` is a thunk that wraps the actual PRAW call; that lets
        us rate-limit *before* the network hit and retry the whole thing
        on failure.
        """
        last_exc: Exception | None = None
        for attempt in range(1, REDDIT_MAX_RETRIES + 1):
            self._rate_limiter.acquire()
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable(exc):
                    raise
                last_exc = exc
                hint = _extract_retry_after(exc)
                if attempt >= REDDIT_MAX_RETRIES:
                    break
                delay = self._compute_backoff(attempt, hint)
                logger.warning(
                    "Reddit %s failed (attempt %d/%d): %s -- backing off %.1fs%s",
                    description or "call",
                    attempt,
                    REDDIT_MAX_RETRIES,
                    exc,
                    delay,
                    f" (hint={hint:.1f}s)" if hint is not None else "",
                )
                time.sleep(delay)

        assert last_exc is not None
        raise last_exc

    def iter_listing(
        self,
        listing_fn: Callable[[], Iterator[Any]],
        *,
        limit: int,
        description: str = "",
    ) -> Iterator[Any]:
        """Yield items from a PRAW listing iterator, rate-limited per item.

        PRAW listings page internally (100 items per HTTP request), so
        acquiring a token per item overcounts slightly -- that's a feature,
        not a bug, since it gives us headroom and smooths bursts. The
        token bucket self-corrects because unused tokens refill.

        We stop early on non-retryable errors. On retryable errors we
        restart the listing: Reddit's listing cursors are not stable
        enough to resume mid-page reliably, and the duplicate-filter in
        the repository handles the overlap.
        """
        for attempt in range(1, REDDIT_MAX_RETRIES + 1):
            yielded = 0
            try:
                iterator = self.call(listing_fn, description=f"{description} init")
                for item in iterator:
                    self._rate_limiter.acquire()
                    yield item
                    yielded += 1
                    if yielded >= limit:
                        return
                return
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable(exc):
                    raise
                hint = _extract_retry_after(exc)
                if attempt >= REDDIT_MAX_RETRIES:
                    raise
                delay = self._compute_backoff(attempt, hint)
                logger.warning(
                    "Reddit listing %s failed after %d items (attempt %d/%d): "
                    "%s -- backing off %.1fs",
                    description,
                    yielded,
                    attempt,
                    REDDIT_MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)

    def iter_subreddit_new(
        self,
        subreddit: str,
        *,
        limit: int,
        before_fullname: str | None = None,
    ) -> Iterator[Any]:
        """Iterate newest submissions in a subreddit, oldest-first within the page.

        `before_fullname` lets us resume from a checkpoint -- PRAW will
        only return items posted *after* that fullname.
        """
        reddit = self._get_reddit()
        sub = reddit.subreddit(subreddit)

        params: dict[str, str] = {}
        if before_fullname:
            params["before"] = before_fullname

        def _listing() -> Iterator[Any]:
            return sub.new(limit=limit, params=params or None)

        yield from self.iter_listing(
            _listing,
            limit=limit,
            description=f"r/{subreddit} new",
        )

    def iter_submission_comments(
        self,
        submission: Any,
    ) -> Iterator[Any]:
        """Flatten every comment on a submission (no "more" expansion)."""

        def _load() -> Iterator[Any]:
            submission.comments.replace_more(limit=0)
            return submission.comments.list()

        yield from self.iter_listing(
            _load,
            limit=10_000,
            description=f"comments on {submission.id}",
        )
