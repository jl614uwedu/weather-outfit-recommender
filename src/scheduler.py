"""Scheduling + timezone handling (Failure mode #3: message arrives too late).

Fixed send time, timezone-aware. Retries are only valid inside the send
window; once the window has passed, the correct behavior is to skip that
day entirely rather than send late.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from .config import PipelineConfig


class WindowStatus(str, Enum):
    BEFORE = "before"  # scheduled time hasn't arrived yet
    WITHIN = "within"  # ok to send/retry now
    PASSED = "passed"  # window closed — skip, do not send late


def scheduled_time_today(now: datetime, config: PipelineConfig) -> datetime:
    local_now = now.astimezone(config.timezone)
    return local_now.replace(hour=config.send_hour, minute=config.send_minute, second=0, microsecond=0)


def window_status(now: datetime, config: PipelineConfig) -> WindowStatus:
    local_now = now.astimezone(config.timezone)
    scheduled = scheduled_time_today(now, config)
    window_end = scheduled + timedelta(minutes=config.send_window_minutes)

    if local_now < scheduled:
        return WindowStatus.BEFORE
    if local_now <= window_end:
        return WindowStatus.WITHIN
    return WindowStatus.PASSED
