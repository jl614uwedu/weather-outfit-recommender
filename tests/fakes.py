"""Test doubles: synthetic weather scenarios, not raw "what I wore" logs."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from src.models import WeatherSnapshot
from src.weather import WeatherFetchError


def make_weather(
    temperature_f: float = 60.0,
    condition: str = "clear",
    precipitation_chance: float = 0.0,
    wind_mph: float = 5.0,
    fetched_at: Optional[datetime] = None,
) -> WeatherSnapshot:
    from datetime import timezone

    return WeatherSnapshot(
        temperature_f=temperature_f,
        condition=condition,
        precipitation_chance=precipitation_chance,
        wind_mph=wind_mph,
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )


class FakeWeatherProvider:
    """Returns snapshots from a queue, or raises WeatherFetchError if the
    queue is exhausted / a sentinel exception is queued."""

    def __init__(self, snapshots: List[WeatherSnapshot | Exception]):
        self._queue = list(snapshots)
        self.fetch_count = 0

    def fetch(self) -> WeatherSnapshot:
        self.fetch_count += 1
        if not self._queue:
            raise WeatherFetchError("fake provider exhausted")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
