"""Shared serialization helpers for DuckDB persistence."""

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class DateValuePoint(Protocol):
    """Any dataclass/namedtuple with .date and .value attributes."""

    @property
    def date(self) -> str: ...

    @property
    def value(self) -> float | int | None: ...


def datapoints_to_json(points: tuple | list) -> str:
    """Serialize a sequence of date/value data points to JSON array of [date, value].

    Works with any object that has .date and .value attributes (KeepaDataPoint,
    TrendsDataPoint, etc.).
    """
    return json.dumps([[p.date, p.value] for p in points])
