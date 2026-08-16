from src.models import UserPreferences
from src.recommender import StubRecommenderBackend, sanitize_ai_temperature_mentions
from tests.fakes import make_weather


def test_sanitize_strips_degree_mentions():
    text = "It's 72°F today so wear a t-shirt, maybe 22 degrees C if you prefer."
    cleaned = sanitize_ai_temperature_mentions(text)
    assert "72" not in cleaned
    assert "22" not in cleaned
    assert "degrees" not in cleaned.lower()


def test_sanitize_leaves_normal_text_untouched():
    text = "Wear a light jacket and bring an umbrella."
    assert sanitize_ai_temperature_mentions(text) == text


def test_stub_backend_fn_controls_output_and_is_sanitized():
    def fn(weather, preferences, call_count):
        return f"It's {weather.temperature_f}°F, wear layers."

    backend = StubRecommenderBackend(fn=fn)
    weather = make_weather(temperature_f=40.0)
    text = backend.generate(weather, UserPreferences(user_id="u"))
    assert "40" not in text
    assert backend.call_count == 1


def test_stub_backend_default_respects_temperature_band():
    backend = StubRecommenderBackend()
    cold_text = backend.generate(make_weather(temperature_f=20.0), UserPreferences(user_id="u"))
    hot_text = backend.generate(make_weather(temperature_f=95.0), UserPreferences(user_id="u"))
    assert "jacket" in cold_text.lower() or "layer" in cold_text.lower()
    assert "light" in hot_text.lower() or "breathable" in hot_text.lower()
