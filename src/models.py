"""Shared data structures for the weather-outfit pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


@dataclass
class WeatherSnapshot:
    temperature_f: float
    condition: str  # "clear" | "clouds" | "rain" | "snow" | "storm" | "fog"
    precipitation_chance: float  # 0.0-1.0
    wind_mph: float
    fetched_at: datetime  # when this snapshot was pulled from the API

    def age_seconds(self, now: datetime) -> float:
        return (now - self.fetched_at).total_seconds()


@dataclass
class UserPreferences:
    user_id: str
    style: Optional[str] = None  # "casual" | "business" | "athletic" | ...
    comfort: Optional[str] = None  # "runs cold" | "runs hot" | "neutral"
    dress_code: Optional[str] = None  # "business casual" | "casual" | ...
    owned_items: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.style, self.comfort, self.dress_code, self.owned_items])


NEUTRAL_PREFERENCES_NOTE = "no stored preferences — neutral fallback used"


class RunStatus(str, Enum):
    SENT = "sent"
    SENT_FALLBACK_INCONSISTENT = "sent_fallback_inconsistent"
    SENT_FALLBACK_UNAVAILABLE = "sent_fallback_unavailable"
    SKIPPED_WINDOW_PASSED = "skipped_window_passed"
    NOT_YET_TIME = "not_yet_time"


@dataclass
class PipelineResult:
    status: RunStatus
    message: Optional[str]
    weather: Optional[WeatherSnapshot] = None
    recommendation_source: Optional[str] = None  # "ai" | "generic_fallback" | None
    regenerated: bool = False
    notes: List[str] = field(default_factory=list)
