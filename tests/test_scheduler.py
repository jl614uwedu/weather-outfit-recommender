from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import PipelineConfig
from src.scheduler import WindowStatus, scheduled_time_today, window_status

config = PipelineConfig()  # 7:00 AM America/New_York, 15 minute window


def _scheduled_today():
    now_base = datetime.now(config.timezone)
    return scheduled_time_today(now_base, config)


def test_before_scheduled_time_is_before():
    scheduled = _scheduled_today()
    now = scheduled - timedelta(minutes=5)
    assert window_status(now, config) == WindowStatus.BEFORE


def test_within_window_right_at_scheduled_time():
    scheduled = _scheduled_today()
    assert window_status(scheduled, config) == WindowStatus.WITHIN


def test_within_window_a_few_minutes_after():
    scheduled = _scheduled_today()
    now = scheduled + timedelta(minutes=10)
    assert window_status(now, config) == WindowStatus.WITHIN


def test_window_passed_after_threshold():
    scheduled = _scheduled_today()
    now = scheduled + timedelta(minutes=20)  # past the 15 minute window
    assert window_status(now, config) == WindowStatus.PASSED


def test_timezone_conversion_is_respected():
    scheduled_local = _scheduled_today()
    # Same instant, expressed in UTC — should still resolve to WITHIN.
    now_utc = scheduled_local.astimezone(ZoneInfo("UTC"))
    assert window_status(now_utc, config) == WindowStatus.WITHIN
