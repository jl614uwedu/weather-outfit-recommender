from datetime import datetime, timedelta, timezone

import pytest

from src.weather import WeatherCache, WeatherFetchError
from tests.fakes import FakeWeatherProvider, make_weather


def test_fresh_cache_is_reused_without_refetching():
    t0 = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    snapshot = make_weather(temperature_f=55.0, fetched_at=t0)
    provider = FakeWeatherProvider([snapshot])
    cache = WeatherCache(provider, max_age_seconds=3600)

    first = cache.get_fresh(now=t0)
    second = cache.get_fresh(now=t0 + timedelta(minutes=10))  # still within 1hr

    assert first is snapshot
    assert second is snapshot
    assert provider.fetch_count == 1  # no refetch needed


def test_stale_cache_triggers_refresh():
    t0 = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    stale = make_weather(temperature_f=55.0, fetched_at=t0)
    fresh = make_weather(temperature_f=58.0, fetched_at=t0 + timedelta(hours=2))
    provider = FakeWeatherProvider([stale, fresh])
    cache = WeatherCache(provider, max_age_seconds=3600)

    first = cache.get_fresh(now=t0)
    second = cache.get_fresh(now=t0 + timedelta(hours=2))  # past the 1hr threshold

    assert first.temperature_f == 55.0
    assert second.temperature_f == 58.0
    assert provider.fetch_count == 2


def test_failed_refresh_raises_instead_of_serving_stale_data():
    t0 = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    stale = make_weather(temperature_f=55.0, fetched_at=t0)
    provider = FakeWeatherProvider([stale, WeatherFetchError("api down")])
    cache = WeatherCache(provider, max_age_seconds=3600)

    cache.get_fresh(now=t0)
    with pytest.raises(WeatherFetchError):
        cache.get_fresh(now=t0 + timedelta(hours=2))
