from src.fallback import build_final_message, build_generic_fallback, precip_description
from tests.fakes import make_weather


def test_generic_fallback_format():
    weather = make_weather(temperature_f=58.0, condition="rain", precipitation_chance=0.7)
    message = build_generic_fallback(weather)
    assert message == "58°, 70% chance of rain — dress in layers."


def test_final_message_uses_raw_temperature_not_model_text():
    weather = make_weather(temperature_f=72.0, condition="clear", precipitation_chance=0.05)
    ai_text = "It's actually freezing, wear a parka."  # model could say anything
    message = build_final_message(weather, ai_text)
    assert message.startswith("72°F")
    assert "parka" in message  # recommendation text still included verbatim


def test_precip_description_bands():
    assert precip_description(make_weather(condition="snow")) == "snow"
    assert precip_description(make_weather(condition="storm")) == "storms"
    assert "rain" in precip_description(make_weather(condition="rain", precipitation_chance=0.6))
    assert precip_description(make_weather(condition="clear", precipitation_chance=0.0)) == "clear"
