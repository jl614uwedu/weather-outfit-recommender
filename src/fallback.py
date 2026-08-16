"""All fallback messages — plain code, no AI (per the 70% deterministic split).

Every fallback path required by the build brief lives here:
  - generic outfit fallback (consistency check failed twice)
  - "weather data currently unavailable" (freshness refresh failed)
"""

from __future__ import annotations

from .models import WeatherSnapshot

UNAVAILABLE_MESSAGE = "Weather data currently unavailable — check the forecast before heading out."


def precip_description(weather: WeatherSnapshot) -> str:
    if weather.condition == "snow":
        return "snow"
    if weather.condition == "storm":
        return "storms"
    if weather.condition == "rain" or weather.precipitation_chance >= 0.4:
        return f"{weather.precipitation_chance:.0%} chance of rain"
    if weather.condition == "fog":
        return "fog"
    if weather.condition == "clouds":
        return "cloudy"
    return "clear"


def build_generic_fallback(weather: WeatherSnapshot) -> str:
    """"[temp]°, [precip] — dress in layers." — used when the AI
    recommendation fails the consistency check twice in a row."""
    return f"{weather.temperature_f:g}°, {precip_description(weather)} — dress in layers."


def build_final_message(weather: WeatherSnapshot, recommendation_text: str) -> str:
    """Structured temperature + precip (raw API values) prepended to the
    AI-generated recommendation text. The numeric temperature never comes
    from the model (Failure mode #2)."""
    return f"{weather.temperature_f:g}°F, {precip_description(weather)} — {recommendation_text}"
