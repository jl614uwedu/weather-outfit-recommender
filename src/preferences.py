"""Preference storage and lookup (Failure mode #5).

Preferences are explicit, user-set data only — no behavior inference, no
learning from what the user actually wears. Missing data yields a neutral
UserPreferences object rather than an assumed style.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .models import UserPreferences


class PreferencesStore:
    """Simple JSON-file-backed preference store, keyed by user_id."""

    def __init__(self, path: Path):
        self._path = path
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({}))

    def _read_all(self) -> Dict[str, dict]:
        return json.loads(self._path.read_text() or "{}")

    def get(self, user_id: str) -> UserPreferences:
        data = self._read_all().get(user_id)
        if not data:
            return UserPreferences(user_id=user_id)  # neutral: all fields unset
        return UserPreferences(
            user_id=user_id,
            style=data.get("style"),
            comfort=data.get("comfort"),
            dress_code=data.get("dress_code"),
            owned_items=list(data.get("owned_items", [])),
        )

    def set(self, prefs: UserPreferences) -> None:
        all_data = self._read_all()
        all_data[prefs.user_id] = {
            "style": prefs.style,
            "comfort": prefs.comfort,
            "dress_code": prefs.dress_code,
            "owned_items": prefs.owned_items,
        }
        self._path.write_text(json.dumps(all_data, indent=2))


class InMemoryPreferencesStore:
    """In-memory store for tests — avoids touching the filesystem."""

    def __init__(self):
        self._data: Dict[str, UserPreferences] = {}

    def get(self, user_id: str) -> UserPreferences:
        return self._data.get(user_id, UserPreferences(user_id=user_id))

    def set(self, prefs: UserPreferences) -> None:
        self._data[prefs.user_id] = prefs
