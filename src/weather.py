"""Weather retrieval: one primary API, with a freshness check in front of it.

This module is pure product logic (failure modes #2 and #4 in the build
brief) — no AI involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from .models import WeatherSnapshot


class WeatherFetchError(Exception):
    """Raised when the primary weather API cannot be reached or parsed."""


class WeatherProvider(Protocol):
    def fetch(self) -> WeatherSnapshot: ...


@dataclass
class OpenMeteoProvider:
    """Primary weather API: Open-Meteo (no API key required)."""

    latitude: float
    longitude: float
    temperature_unit: str = "fahrenheit"
    _base_url: str = "https://api.open-meteo.com/v1/forecast"

    def fetch(self) -> WeatherSnapshot:
        import requests  # local import keeps this module importable without the dep in unit tests

        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "temperature_2m,precipitation_probability,weathercode,windspeed_10m",
            "temperature_unit": self.temperature_unit,
            "wind_speed_unit": "mph",
        }
        try:
            resp = requests.get(self._base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]
        except Exception as exc:  # network, timeout, bad payload, etc.
            raise WeatherFetchError(f"failed to fetch weather: {exc}") from exc

        return WeatherSnapshot(
            temperature_f=float(current["temperature_2m"]),
            condition=_condition_from_weathercode(int(current.get("weathercode", 0))),
            precipitation_chance=float(current.get("precipitation_probability", 0)) / 100.0,
            wind_mph=float(current.get("windspeed_10m", 0)),
            fetched_at=datetime.now(timezone.utc),
        )


def _condition_from_weathercode(code: int) -> str:
    """Maps Open-Meteo WMO weather codes to our coarse condition buckets."""
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "clouds"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    return "clouds"


class WeatherCache:
    """Holds the last fetched snapshot and enforces the freshness threshold.

    Failure mode #4 (stale forecast shown as current): a cached snapshot is
    only handed back if it's within `max_age_seconds`; otherwise a refresh
    is attempted, and a failed refresh is surfaced as WeatherFetchError so
    the caller can send the "weather data currently unavailable" fallback.
    """

    def __init__(self, provider: WeatherProvider, max_age_seconds: int):
        self._provider = provider
        self._max_age_seconds = max_age_seconds
        self._snapshot: Optional[WeatherSnapshot] = None

    def get_fresh(self, now: Optional[datetime] = None) -> WeatherSnapshot:
        now = now or datetime.now(timezone.utc)

        if self._snapshot is not None and self._snapshot.age_seconds(now) <= self._max_age_seconds:
            return self._snapshot

        # Stale or never fetched — refresh. Let WeatherFetchError propagate;
        # the caller is responsible for the "unavailable" fallback.
        snapshot = self._provider.fetch()
        self._snapshot = snapshot
        return snapshot
