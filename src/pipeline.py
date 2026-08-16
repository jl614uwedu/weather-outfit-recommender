"""Orchestrates the core flow (build brief steps 1-7).

Deterministic scaffolding around a single swappable AI call:
  1. scheduling/timezone check
  2-4. weather fetch + freshness check (refresh or "unavailable" fallback)
  5. preference lookup (neutral fallback if missing)
  6. AI recommendation -> consistency check -> regenerate once -> generic fallback
  7. temperature/precip inserted as raw API values, then send
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Optional

from .config import PipelineConfig
from .consistency import check_consistency
from .fallback import UNAVAILABLE_MESSAGE, build_final_message, build_generic_fallback
from .messaging import Sender
from .models import NEUTRAL_PREFERENCES_NOTE, PipelineResult, RunStatus
from .recommender import RecommenderBackend
from .scheduler import WindowStatus, window_status
from .weather import WeatherCache, WeatherFetchError


def run_daily_recommendation(
    *,
    user_id: str,
    recipient_email: str,
    config: PipelineConfig,
    weather_cache: WeatherCache,
    preferences_store,
    recommender: RecommenderBackend,
    sender: Sender,
    now: Optional[datetime] = None,
) -> PipelineResult:
    now = now or datetime.now(dt_timezone.utc)
    notes: list[str] = []

    # 1. Scheduling + timezone check (Failure mode #3).
    status = window_status(now, config)
    if status == WindowStatus.BEFORE:
        return PipelineResult(status=RunStatus.NOT_YET_TIME, message=None, notes=["scheduled send time hasn't arrived yet"])
    if status == WindowStatus.PASSED:
        return PipelineResult(
            status=RunStatus.SKIPPED_WINDOW_PASSED,
            message=None,
            notes=["send window passed — skipping today rather than sending late"],
        )

    # 2-4. Weather fetch with freshness check (Failure mode #4).
    try:
        weather = weather_cache.get_fresh(now=now)
    except WeatherFetchError as exc:
        notes.append(f"weather fetch/refresh failed: {exc}")
        sender.send(recipient_email, UNAVAILABLE_MESSAGE)
        return PipelineResult(
            status=RunStatus.SENT_FALLBACK_UNAVAILABLE,
            message=UNAVAILABLE_MESSAGE,
            weather=None,
            recommendation_source=None,
            notes=notes,
        )

    # 5. Preferences (Failure mode #5) — neutral fallback if missing.
    preferences = preferences_store.get(user_id)
    if preferences.is_empty():
        notes.append(NEUTRAL_PREFERENCES_NOTE)

    # 6. AI recommendation + rule-based consistency check (Failure mode #1).
    regenerated = False
    recommendation_text = recommender.generate(weather, preferences)
    result = check_consistency(weather, recommendation_text, config)

    if not result.passed:
        notes.extend(f"consistency check failed (attempt 1): {r}" for r in result.reasons)
        regenerated = True
        recommendation_text = recommender.generate(weather, preferences)
        result = check_consistency(weather, recommendation_text, config)

    if not result.passed:
        notes.extend(f"consistency check failed (attempt 2): {r}" for r in result.reasons)
        message = build_generic_fallback(weather)  # already includes raw temp/precip
        sender.send(recipient_email, message)
        return PipelineResult(
            status=RunStatus.SENT_FALLBACK_INCONSISTENT,
            message=message,
            weather=weather,
            recommendation_source="generic_fallback",
            regenerated=regenerated,
            notes=notes,
        )

    # 7. Temperature/precip are raw API values inserted directly — never
    # model-generated (Failure mode #2). `weather` here is the same
    # snapshot just validated for freshness above, so this is guaranteed
    # to match the latest fetch.
    message = build_final_message(weather, recommendation_text)
    sender.send(recipient_email, message)
    return PipelineResult(
        status=RunStatus.SENT,
        message=message,
        weather=weather,
        recommendation_source="ai",
        regenerated=regenerated,
        notes=notes,
    )
