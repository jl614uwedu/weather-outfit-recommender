"""Rule-based consistency check: does the recommendation text match the
actual weather data? (Failure mode #1.)

This is deliberately simple keyword-band logic, not a model call — the
brief calls for this to be built as plain rules, not "hoped" from the AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .config import PipelineConfig
from .models import WeatherSnapshot

_COLD_REQUIRED = {"jacket", "coat", "layer", "layers", "warm", "sweater", "thermal", "fleece", "beanie", "gloves"}
_COLD_FORBIDDEN = {"shorts", "tank top", "sandals", "sundress", "flip-flops", "flip flops"}

_HOT_FORBIDDEN = {"parka", "heavy coat", "thermal", "fleece", "winter coat"}

_RAIN_REQUIRED = {"umbrella", "rain jacket", "raincoat", "waterproof", "rain boots"}

_SNOW_REQUIRED = {"boots", "waterproof", "insulated", "snow"}


@dataclass
class ConsistencyResult:
    passed: bool
    reasons: List[str] = field(default_factory=list)


def check_consistency(weather: WeatherSnapshot, recommendation_text: str, config: PipelineConfig) -> ConsistencyResult:
    text = recommendation_text.lower()
    reasons: List[str] = []

    if weather.temperature_f < config.cold_threshold_f:
        if not any(word in text for word in _COLD_REQUIRED):
            reasons.append(
                f"temperature is {weather.temperature_f:g}F (cold) but recommendation doesn't mention warm layers"
            )
        if any(word in text for word in _COLD_FORBIDDEN):
            reasons.append(
                f"temperature is {weather.temperature_f:g}F (cold) but recommendation suggests warm-weather items"
            )

    if weather.temperature_f > config.hot_threshold_f:
        if any(word in text for word in _HOT_FORBIDDEN):
            reasons.append(
                f"temperature is {weather.temperature_f:g}F (hot) but recommendation suggests heavy cold-weather items"
            )

    if weather.condition == "rain" or weather.precipitation_chance >= config.rain_precip_threshold:
        if not any(word in text for word in _RAIN_REQUIRED):
            reasons.append(
                f"precipitation chance is {weather.precipitation_chance:.0%} but recommendation doesn't "
                "mention rain protection"
            )

    if weather.condition == "snow":
        if not any(word in text for word in _SNOW_REQUIRED):
            reasons.append("condition is snow but recommendation doesn't mention snow-appropriate footwear/gear")

    return ConsistencyResult(passed=len(reasons) == 0, reasons=reasons)
