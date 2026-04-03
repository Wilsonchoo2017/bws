"""Railway-oriented Result type for composable error handling.

Provides ``Ok[T]`` and ``Err[E]`` types that support functional
composition via ``map``, ``flat_map``, and ``recover``.  This replaces
scattered try/except blocks and boolean-success checks with a single,
chainable pipeline.

Usage::

    result = (
        fetch_data(url)                  # -> Result[RawData, ScrapeError]
        .map(parse)                      # -> Result[Parsed, ScrapeError]
        .flat_map(validate)              # -> Result[Valid, ScrapeError]
        .map(lambda v: persist(conn, v)) # -> Result[None, ScrapeError]
    )

    match result:
        case Ok(value):
            ...
        case Err(error):
            ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, Union, overload

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Represents a successful computation."""

    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def map(self, fn: Callable[[T], U]) -> Result[U, Any]:
        """Apply *fn* to the contained value."""
        return Ok(fn(self.value))

    def flat_map(self, fn: Callable[[T], Result[U, Any]]) -> Result[U, Any]:
        """Apply *fn* that itself returns a Result."""
        return fn(self.value)

    def map_err(self, _fn: Callable[[Any], F]) -> Result[T, F]:
        """No-op on Ok -- error mapper has nothing to transform."""
        return self  # type: ignore[return-value]

    def recover(self, _fn: Callable[[Any], Result[T, Any]]) -> Result[T, Any]:
        """No-op on Ok -- nothing to recover from."""
        return self

    def unwrap(self) -> T:
        """Extract value, raising if this is an Err."""
        return self.value

    def unwrap_or(self, _default: T) -> T:  # type: ignore[override]
        return self.value

    def unwrap_or_else(self, _fn: Callable[[Any], T]) -> T:
        return self.value

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Represents a failed computation."""

    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def map(self, _fn: Callable[[Any], Any]) -> Err[E]:
        """No-op on Err -- value mapper has nothing to transform."""
        return self

    def flat_map(self, _fn: Callable[[Any], Any]) -> Err[E]:
        """No-op on Err -- value mapper has nothing to transform."""
        return self

    def map_err(self, fn: Callable[[E], F]) -> Result[Any, F]:
        """Apply *fn* to the contained error."""
        return Err(fn(self.error))

    def recover(self, fn: Callable[[E], Result[Any, Any]]) -> Result[Any, Any]:
        """Try to recover from the error via *fn*."""
        return fn(self.error)

    def unwrap(self) -> Any:
        """Raise because this is an Err."""
        raise ValueError(f"Called unwrap() on Err({self.error!r})")

    def unwrap_or(self, default: Any) -> Any:
        return default

    def unwrap_or_else(self, fn: Callable[[E], Any]) -> Any:
        return fn(self.error)

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# The union type that all functions return.
Result = Union[Ok[T], Err[E]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def try_call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> Result[T, Exception]:
    """Call *fn* and wrap the outcome in Ok/Err.

    Catches all exceptions and wraps them in ``Err``.  Use at IO
    boundaries to convert exception-based APIs into Result-based ones.
    """
    try:
        return Ok(fn(*args, **kwargs))
    except Exception as exc:
        return Err(exc)


async def try_call_async(
    fn: Callable[..., Any], *args: Any, **kwargs: Any,
) -> Result[Any, Exception]:
    """Async variant of :func:`try_call`."""
    try:
        return Ok(await fn(*args, **kwargs))
    except Exception as exc:
        return Err(exc)
