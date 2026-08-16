"""End-to-end synthetic scenarios, one per failure mode in the build brief,
run through the real pipeline with fake weather/AI/sender doubles.

Shipping bar: every fallback path (temperature mismatch, stale data,
consistency failure, missing preferences, late send) has a test case here
that triggers it and confirms the correct fallback fires.
"""

from datetime import timedelta

from src.config import PipelineConfig
from src.messaging import ConsoleSender
from src.models import RunStatus, UserPreferences
from src.pipeline import run_daily_recommendation
from src.preferences import InMemoryPreferencesStore
from src.recommender import StubRecommenderBackend
from src.scheduler import scheduled_time_today
from src.weather import WeatherCache, WeatherFetchError
from tests.fakes import FakeWeatherProvider, make_weather

CONFIG = PipelineConfig()


def _within_window_now():
    return scheduled_time_today(__import__("datetime").datetime.now(CONFIG.timezone), CONFIG) + timedelta(minutes=1)


def _run(*, provider, recommender, preferences_store=None, now=None):
    cache = WeatherCache(provider, max_age_seconds=CONFIG.forecast_max_age_seconds)
    sender = ConsoleSender()
    result = run_daily_recommendation(
        user_id="alice",
        recipient_email="alice@example.com",
        config=CONFIG,
        weather_cache=cache,
        preferences_store=preferences_store or InMemoryPreferencesStore(),
        recommender=recommender,
        sender=sender,
        now=now or _within_window_now(),
    )
    return result, sender


# Failure mode #1: recommendation doesn't match conditions.

def test_consistency_failure_twice_sends_generic_fallback():
    weather = make_weather(temperature_f=25.0, condition="clear")
    provider = FakeWeatherProvider([weather])
    recommender = StubRecommenderBackend(fixed_text="Wear shorts and sandals today.")  # always wrong for 25F

    result, sender = _run(provider=provider, recommender=recommender)

    assert result.status == RunStatus.SENT_FALLBACK_INCONSISTENT
    assert result.regenerated is True
    assert result.message == "25°, clear — dress in layers."
    assert recommender.call_count == 2  # generate + one regenerate, per the brief
    assert sender.sent == [("alice@example.com", result.message)]


def test_consistency_failure_once_then_success_sends_ai_text():
    weather = make_weather(temperature_f=25.0, condition="clear")
    provider = FakeWeatherProvider([weather])

    def fn(w, prefs, call_count):
        if call_count == 1:
            return "Wear shorts and sandals today."
        return "Bundle up in a warm coat and layers."

    recommender = StubRecommenderBackend(fn=fn)
    result, sender = _run(provider=provider, recommender=recommender)

    assert result.status == RunStatus.SENT
    assert result.regenerated is True
    assert result.recommendation_source == "ai"
    assert "coat" in result.message.lower()
    assert result.message.startswith("25°F")


# Failure mode #2: wrong temperature shown — model output is never trusted
# for the numeric value; it's always the raw API value.

def test_temperature_in_message_is_always_the_raw_api_value():
    weather = make_weather(temperature_f=63.0, condition="clear", precipitation_chance=0.1)
    provider = FakeWeatherProvider([weather])
    # Model hallucinates a different, wrong temperature in its text.
    recommender = StubRecommenderBackend(fixed_text="It's 90°F, wear a light layer.")

    result, sender = _run(provider=provider, recommender=recommender)

    assert result.status == RunStatus.SENT
    assert result.message.startswith("63°F")  # raw API value, not the model's "90"
    assert "90" not in result.message


# Failure mode #3: message arrives too late.

def test_before_scheduled_time_does_not_send():
    now = scheduled_time_today(__import__("datetime").datetime.now(CONFIG.timezone), CONFIG) - timedelta(minutes=5)
    weather = make_weather(temperature_f=60.0)
    provider = FakeWeatherProvider([weather])
    recommender = StubRecommenderBackend()

    result, sender = _run(provider=provider, recommender=recommender, now=now)

    assert result.status == RunStatus.NOT_YET_TIME
    assert sender.sent == []


def test_window_passed_skips_instead_of_sending_late():
    now = scheduled_time_today(__import__("datetime").datetime.now(CONFIG.timezone), CONFIG) + timedelta(minutes=30)
    weather = make_weather(temperature_f=60.0)
    provider = FakeWeatherProvider([weather])
    recommender = StubRecommenderBackend()

    result, sender = _run(provider=provider, recommender=recommender, now=now)

    assert result.status == RunStatus.SKIPPED_WINDOW_PASSED
    assert sender.sent == []


# Failure mode #4: stale forecast shown as current.

def test_stale_forecast_refresh_failure_sends_unavailable_message():
    provider = FakeWeatherProvider([WeatherFetchError("api unreachable")])
    recommender = StubRecommenderBackend()

    result, sender = _run(provider=provider, recommender=recommender)

    assert result.status == RunStatus.SENT_FALLBACK_UNAVAILABLE
    assert "unavailable" in result.message.lower()
    assert sender.sent == [("alice@example.com", result.message)]
    assert recommender.call_count == 0  # never even attempted a recommendation


# Failure mode #5: recommendation ignores preferences.

def test_missing_preferences_uses_neutral_fallback_not_an_assumption():
    weather = make_weather(temperature_f=60.0, condition="clear")
    provider = FakeWeatherProvider([weather])

    captured_prefs = {}

    def fn(w, prefs, call_count):
        captured_prefs["prefs"] = prefs
        return "A light layer should do the trick."

    recommender = StubRecommenderBackend(fn=fn)
    result, sender = _run(provider=provider, recommender=recommender, preferences_store=InMemoryPreferencesStore())

    assert result.status == RunStatus.SENT
    assert any("neutral fallback" in note for note in result.notes)
    assert captured_prefs["prefs"].is_empty()


def test_stored_preferences_are_passed_to_recommender():
    weather = make_weather(temperature_f=60.0, condition="clear")
    provider = FakeWeatherProvider([weather])
    store = InMemoryPreferencesStore()
    store.set(UserPreferences(user_id="alice", dress_code="business casual"))

    captured_prefs = {}

    def fn(w, prefs, call_count):
        captured_prefs["prefs"] = prefs
        return "A blazer and slacks should work well today."

    recommender = StubRecommenderBackend(fn=fn)
    result, sender = _run(provider=provider, recommender=recommender, preferences_store=store)

    assert result.status == RunStatus.SENT
    assert not any("neutral fallback" in note for note in result.notes)
    assert captured_prefs["prefs"].dress_code == "business casual"


# Happy path sanity check.

def test_happy_path_sends_ai_recommendation_on_first_try():
    weather = make_weather(temperature_f=68.0, condition="clear", precipitation_chance=0.05)
    provider = FakeWeatherProvider([weather])
    recommender = StubRecommenderBackend()

    result, sender = _run(provider=provider, recommender=recommender)

    assert result.status == RunStatus.SENT
    assert result.regenerated is False
    assert recommender.call_count == 1
    assert result.message.startswith("68°F")
