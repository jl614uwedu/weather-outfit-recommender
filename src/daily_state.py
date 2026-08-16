"""Idempotency guard for scripts/run_daily.py.

launchd is configured to fire a few times across the send window so a
transient failure gets retried (Failure mode #3). Without this guard, a
retry after a successful send would email the recommendation twice. Once a
run reaches a terminal outcome for today, later invocations the same day
are a no-op.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import PipelineConfig
from .models import RunStatus

# NOT_YET_TIME is intentionally excluded: it means "try again later today",
# not "today is handled". An exception during the run also leaves nothing
# recorded, so the next launchd firing retries.
_TERMINAL_STATUSES = {
    RunStatus.SENT,
    RunStatus.SENT_FALLBACK_INCONSISTENT,
    RunStatus.SENT_FALLBACK_UNAVAILABLE,
    RunStatus.SKIPPED_WINDOW_PASSED,
}


def _today_str(now: datetime, config: PipelineConfig) -> str:
    return now.astimezone(config.timezone).date().isoformat()


def already_handled_today(path: Path, now: datetime, config: PipelineConfig) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return data.get("date") == _today_str(now, config)


def record_if_terminal(path: Path, now: datetime, config: PipelineConfig, status: RunStatus) -> None:
    if status not in _TERMINAL_STATUSES:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": _today_str(now, config), "status": status.value}))
