"""The AI-generated 30%: outfit recommendation text given weather + preferences.

This is the single, swappable AI step. It is never trusted with the
temperature that ends up in the final message (see fallback.py /
sanitize_ai_temperature_mentions) — that's inserted separately as a raw
API value (Failure mode #2).
"""

from __future__ import annotations

import os
import re
from typing import Optional, Protocol

from .models import UserPreferences, WeatherSnapshot

_DEGREE_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?(?:°|degrees)\s?F?\b", re.IGNORECASE)


class RecommenderBackend(Protocol):
    def generate(self, weather: WeatherSnapshot, preferences: UserPreferences) -> str: ...


def sanitize_ai_temperature_mentions(text: str) -> str:
    """Defensive strip of any degree figure the model wrote, so a
    hallucinated/rounded number can never leak into the sent message.
    The real temperature is inserted separately, from the API value.
    """
    return _DEGREE_PATTERN.sub("", text).strip()


def _build_prompt(weather: WeatherSnapshot, preferences: UserPreferences) -> tuple[str, str]:
    system = (
        "You recommend a daily outfit in 1-2 short sentences, text-message length. "
        "Use the weather conditions and the user's stored preferences. "
        "Do NOT state a specific temperature number or degree figure — describe "
        "conditions qualitatively (cold, mild, hot, rainy, windy) instead; the exact "
        "temperature is inserted separately by the app. "
        "If a preference field is missing, stay neutral and practical rather than guessing. "
        "Never suggest an item that contradicts the weather (e.g. no shorts when it's cold, "
        "no heavy coat when it's hot, mention rain protection when precipitation is likely)."
    )
    pref_lines = []
    if preferences.style:
        pref_lines.append(f"style: {preferences.style}")
    if preferences.comfort:
        pref_lines.append(f"comfort: {preferences.comfort}")
    if preferences.dress_code:
        pref_lines.append(f"dress code: {preferences.dress_code}")
    if preferences.owned_items:
        pref_lines.append(f"owned items to prefer: {', '.join(preferences.owned_items)}")
    pref_block = "; ".join(pref_lines) if pref_lines else "none stored — use a neutral practical default"

    user = (
        f"Weather: {weather.condition}, {weather.temperature_f:g}F, "
        f"{weather.precipitation_chance:.0%} chance of precipitation, {weather.wind_mph:g} mph wind.\n"
        f"User preferences: {pref_block}.\n"
        "Give the outfit recommendation now."
    )
    return system, user


class AnthropicRecommenderBackend:
    """Real AI backend using the Anthropic API. Lazily imports the SDK so
    the rest of the app (and tests) don't need it installed.
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def generate(self, weather: WeatherSnapshot, preferences: UserPreferences) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        system, user = _build_prompt(weather, preferences)
        response = client.messages.create(
            model=self.model,
            max_tokens=120,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return sanitize_ai_temperature_mentions(text)


class StubRecommenderBackend:
    """Deterministic backend for tests/offline use.

    Accepts an optional callable so test scenarios can control exactly what
    text comes back (including deliberately inconsistent text, to exercise
    the consistency-check retry/fallback path).
    """

    def __init__(self, fixed_text: Optional[str] = None, fn=None):
        self._fixed_text = fixed_text
        self._fn = fn
        self.call_count = 0

    def generate(self, weather: WeatherSnapshot, preferences: UserPreferences) -> str:
        self.call_count += 1
        if self._fn is not None:
            return sanitize_ai_temperature_mentions(self._fn(weather, preferences, self.call_count))
        if self._fixed_text is not None:
            return sanitize_ai_temperature_mentions(self._fixed_text)
        return sanitize_ai_temperature_mentions(_default_stub_text(weather, preferences))


def _default_stub_text(weather: WeatherSnapshot, preferences: UserPreferences) -> str:
    if weather.temperature_f < 45:
        base = "Wear a warm jacket and layer up"
    elif weather.temperature_f > 80:
        base = "Go light and breathable"
    else:
        base = "A light layer should do the trick"
    if weather.condition == "rain" or weather.precipitation_chance >= 0.4:
        base += ", and bring an umbrella or a rain jacket"
    if preferences.dress_code:
        base += f", keeping it {preferences.dress_code}"
    return base + "."
