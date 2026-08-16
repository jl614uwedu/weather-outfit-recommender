#!/usr/bin/env python3
"""Cron/launchd entrypoint: run once, retrying transient failures within
the send window (Failure mode #3). Intended to be invoked a few times
(e.g. every 5 minutes) between the scheduled time and the end of the
window — it no-ops before the scheduled time, skips once the window has
passed, and is safe to invoke more than once because `daily_state` records
the first terminal outcome for the day and short-circuits later runs so a
retry-after-success never sends a duplicate message.

Env vars:
  WEATHER_LAT, WEATHER_LON        - location for the weather pull (required)
  USER_ID                         - preference-store key (default "default")
  RECIPIENT_EMAIL                 - destination address (required for OutlookEmailSender)
  PREFERENCES_PATH                - path to the JSON preferences file (default ./config/preferences.json)
  DAILY_STATE_PATH                - path to the once-per-day marker file (default ./config/last_run_state.json)
  SENDER                          - "console" (default) or "outlook"
  OUTLOOK_CLIENT_ID, OUTLOOK_TENANT, OUTLOOK_TOKEN_CACHE_PATH
                                   - see scripts/outlook_auth_setup.py (required for SENDER=outlook,
                                     after running that script once)
  RECOMMENDER                     - "anthropic" (default) or "stub"
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PipelineConfig
from src.daily_state import already_handled_today, record_if_terminal
from src.messaging import ConsoleSender, OutlookEmailSender
from src.pipeline import run_daily_recommendation
from src.preferences import PreferencesStore
from src.recommender import AnthropicRecommenderBackend, StubRecommenderBackend
from src.weather import OpenMeteoProvider, WeatherCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weather_outfit.run_daily")


def build_sender():
    kind = os.environ.get("SENDER", "console")
    if kind == "outlook":
        return OutlookEmailSender()
    return ConsoleSender()


def build_recommender():
    kind = os.environ.get("RECOMMENDER", "anthropic")
    if kind == "stub":
        return StubRecommenderBackend()
    return AnthropicRecommenderBackend()


def main() -> int:
    lat = os.environ.get("WEATHER_LAT")
    lon = os.environ.get("WEATHER_LON")
    if not lat or not lon:
        logger.error("WEATHER_LAT and WEATHER_LON must be set")
        return 1

    user_id = os.environ.get("USER_ID", "default")
    recipient_email = os.environ.get("RECIPIENT_EMAIL", "")
    prefs_path = Path(os.environ.get("PREFERENCES_PATH", Path(__file__).resolve().parent.parent / "config" / "preferences.json"))
    state_path = Path(os.environ.get("DAILY_STATE_PATH", Path(__file__).resolve().parent.parent / "config" / "last_run_state.json"))

    config = PipelineConfig()
    now = datetime.now(timezone.utc)

    if already_handled_today(state_path, now, config):
        logger.info("today's run already reached a terminal outcome — skipping (retry no-op)")
        return 0

    weather_cache = WeatherCache(
        provider=OpenMeteoProvider(latitude=float(lat), longitude=float(lon)),
        max_age_seconds=config.forecast_max_age_seconds,
    )
    preferences_store = PreferencesStore(prefs_path)
    recommender = build_recommender()
    sender = build_sender()

    result = run_daily_recommendation(
        user_id=user_id,
        recipient_email=recipient_email,
        config=config,
        weather_cache=weather_cache,
        preferences_store=preferences_store,
        recommender=recommender,
        sender=sender,
        now=now,
    )

    logger.info("status=%s message=%r notes=%s", result.status, result.message, result.notes)
    record_if_terminal(state_path, now, config, result.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
