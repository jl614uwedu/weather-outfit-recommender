"""Deterministic configuration: thresholds, windows, and timezone settings.

Every value here is a plain rule the product layer enforces — nothing here
is decided by the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PipelineConfig:
    timezone: ZoneInfo = ZoneInfo("America/Los_Angeles")
    send_hour: int = 7
    send_minute: int = 0
    send_window_minutes: int = 15  # retry within this window; skip if passed

    forecast_max_age_seconds: int = 60 * 60  # 1 hour freshness threshold

    max_recommendation_attempts: int = 2  # 1 generate + 1 regenerate on inconsistency

    cold_threshold_f: float = 45.0
    hot_threshold_f: float = 80.0
    rain_precip_threshold: float = 0.4
    wind_threshold_mph: float = 20.0
