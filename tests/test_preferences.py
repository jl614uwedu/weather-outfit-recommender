import json

from src.models import UserPreferences
from src.preferences import InMemoryPreferencesStore, PreferencesStore


def test_missing_user_returns_neutral_preferences(tmp_path):
    store = PreferencesStore(tmp_path / "preferences.json")
    prefs = store.get("someone-not-stored")
    assert prefs.is_empty()
    assert prefs.style is None
    assert prefs.owned_items == []


def test_stored_preferences_round_trip(tmp_path):
    path = tmp_path / "preferences.json"
    store = PreferencesStore(path)
    store.set(
        UserPreferences(
            user_id="alice",
            style="casual",
            comfort="runs cold",
            dress_code="business casual",
            owned_items=["navy raincoat"],
        )
    )

    reloaded_store = PreferencesStore(path)  # simulate a fresh process
    prefs = reloaded_store.get("alice")
    assert not prefs.is_empty()
    assert prefs.style == "casual"
    assert prefs.owned_items == ["navy raincoat"]

    on_disk = json.loads(path.read_text())
    assert "alice" in on_disk


def test_in_memory_store_defaults_to_neutral():
    store = InMemoryPreferencesStore()
    assert store.get("nobody").is_empty()
