from datetime import timedelta

from src.config import PipelineConfig
from src.daily_state import already_handled_today, record_if_terminal
from src.models import RunStatus

config = PipelineConfig()


def _now():
    from datetime import datetime

    return datetime.now(config.timezone)


def test_no_file_means_not_handled(tmp_path):
    path = tmp_path / "state.json"
    assert not already_handled_today(path, _now(), config)


def test_terminal_status_recorded_and_detected(tmp_path):
    path = tmp_path / "state.json"
    now = _now()
    record_if_terminal(path, now, config, RunStatus.SENT)
    assert already_handled_today(path, now, config)


def test_skipped_window_passed_also_marks_day_handled(tmp_path):
    path = tmp_path / "state.json"
    now = _now()
    record_if_terminal(path, now, config, RunStatus.SKIPPED_WINDOW_PASSED)
    assert already_handled_today(path, now, config)


def test_not_yet_time_is_not_recorded_and_allows_retry(tmp_path):
    path = tmp_path / "state.json"
    now = _now()
    record_if_terminal(path, now, config, RunStatus.NOT_YET_TIME)
    assert not path.exists()
    assert not already_handled_today(path, now, config)


def test_next_day_is_not_handled(tmp_path):
    path = tmp_path / "state.json"
    now = _now()
    record_if_terminal(path, now, config, RunStatus.SENT)
    tomorrow = now + timedelta(days=1)
    assert not already_handled_today(path, tomorrow, config)


def test_corrupt_state_file_is_treated_as_not_handled(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not valid json")
    assert not already_handled_today(path, _now(), config)
