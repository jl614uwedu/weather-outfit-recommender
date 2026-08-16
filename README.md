# Weather-Based Outfit Recommender

Daily automated email that tells the user what to wear, based on the day's
weather. Built from `weather-outfit-build-brief_1.md`: a Level 2 AI
integration where the AI writes the outfit text, but every failure mode is
caught by deterministic product-layer code before anything gets sent — the
model gets no unchecked path to the user.

## Architecture (70% code / 30% AI)

```
src/
  config.py        thresholds: freshness window, send time/window, temp bands
  models.py         WeatherSnapshot, UserPreferences, PipelineResult, etc.
  weather.py        Open-Meteo client + freshness-checked cache            (deterministic)
  consistency.py     rule-based check: does the AI text match the weather   (deterministic)
  preferences.py     JSON-backed preference store, neutral default          (deterministic)
  recommender.py     the swappable AI step + temperature-sanitizing guard   (AI + guard)
  fallback.py         generic + "unavailable" fallback message builders      (deterministic)
  messaging.py        Sender abstraction: ConsoleSender (default) / Outlook  (deterministic)
  scheduler.py         timezone-aware send-window logic                      (deterministic)
  pipeline.py           orchestrates steps 1-7 from the build brief          (deterministic)
scripts/run_daily.py    cron entrypoint
tests/                   35 tests, incl. one scenario per failure mode
```

The AI call (`RecommenderBackend.generate`) is the only place a model runs.
It's swappable (`AnthropicRecommenderBackend` for real use, `StubRecommenderBackend`
for tests/offline) and every other module works without it.

## Core flow

1. Cron/launchd fires `scripts/run_daily.py` around the scheduled send time.
2. `scheduler.window_status` checks it's within the send window (timezone-aware);
   skips silently before the window, skips-for-the-day after it closes.
3. `weather.WeatherCache.get_fresh` returns the cached forecast if it's under
   the freshness threshold (default 1hr), otherwise refetches from Open-Meteo.
4. `preferences.PreferencesStore.get` loads stored style/comfort/dress-code/owned
   items, or a neutral default if none are stored.
5. `recommender.generate` asks the model for 1-2 sentences of outfit advice
   (explicitly instructed not to state a temperature figure).
6. `consistency.check_consistency` validates the text against the weather.
   On failure: regenerate once. On a second failure: generic fallback.
7. `fallback.build_final_message` prepends the temperature/precipitation as
   raw API values — the model's text is never trusted for those numbers,
   and `recommender.sanitize_ai_temperature_mentions` strips any degree
   figure the model wrote anyway, as a second line of defense.
8. `messaging.Sender.send` delivers it — by default `ConsoleSender` just logs
   it; `OutlookEmailSender` sends it as an email via the Microsoft Graph API.

## Failure modes and where they're handled

| # | Failure mode | Where |
|---|---|---|
| 1 | Recommendation doesn't match conditions | `consistency.py` + `pipeline.py` (regenerate once, then generic fallback) |
| 2 | Wrong temperature shown | `fallback.build_final_message` always uses the API value; `recommender.sanitize_ai_temperature_mentions` strips model-written numbers |
| 3 | Message arrives too late | `scheduler.window_status` — skip once the window passes, never send late |
| 4 | Stale forecast shown as current | `weather.WeatherCache` — freshness threshold + refresh; failed refresh sends the "unavailable" fallback instead of stale data |
| 5 | Recommendation ignores preferences | `preferences.py` — missing data yields a neutral `UserPreferences`, never an assumption |

Every path above has a dedicated test in `tests/test_pipeline_scenarios.py`.

## Setup

```bash
cd weather-outfit-recommender
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Copy `config/preferences.example.json` to `config/preferences.json` and edit
it (or write entries via `PreferencesStore.set`).

Environment variables read by `scripts/run_daily.py`:

| Var | Required | Notes |
|---|---|---|
| `WEATHER_LAT`, `WEATHER_LON` | yes | Location for Open-Meteo (no API key needed) |
| `USER_ID` | no | Preference-store key, default `"default"` |
| `RECIPIENT_EMAIL` | for Outlook | Destination email address |
| `PREFERENCES_PATH` | no | Default `config/preferences.json` |
| `SENDER` | no | `console` (default, just logs) or `outlook` |
| `OUTLOOK_CLIENT_ID` | for Outlook | Azure app registration client ID — see below |
| `OUTLOOK_TENANT` | no | Default `"common"` (personal + work/school accounts) |
| `OUTLOOK_TOKEN_CACHE_PATH` | no | Default `config/outlook_token_cache.json` |
| `RECOMMENDER` | no | `anthropic` (default) or `stub` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | for Anthropic | `ANTHROPIC_MODEL` defaults to `claude-sonnet-5` |

`SENDER` defaults to `console` and `RECOMMENDER` defaults to `anthropic`, so
everything runs out of the box against the free Open-Meteo API without any
credentials — the only thing you need for real delivery is a one-time
Outlook auth setup.

### One-time Outlook setup

Sending happens through the Microsoft Graph API (`OutlookEmailSender` in
[src/messaging.py](src/messaging.py)), authenticated via MSAL device-code
flow — no client secret, so it's safe to run unattended from cron after the
one-time interactive step below.

1. In the [Azure Portal](https://portal.azure.com) → App registrations → New
   registration:
   - Supported account types: "Personal Microsoft accounts" for a personal
     outlook.com/hotmail.com address, or "Accounts in this organizational
     directory only" if sending from a work/school account (e.g. a
     university's `@school.edu` address, registered under that org's tenant).
   - Authentication → Add a platform → "Mobile and desktop applications" →
     check the `https://login.microsoftonline.com/common/oauth2/nativeclient`
     redirect URI.
   - Still on the Authentication page → **Settings tab → turn on "Allow
     public client flows"**. This is easy to miss and is *required* — without
     it, the device-code sign-in fails with
     `AADSTS7000218: ... must contain 'client_assertion' or 'client_secret'`
     even though the redirect URI is a public-client one.
   - API permissions → Microsoft Graph → Delegated → add `Mail.Send`. For an
     org/work tenant this usually shows "Admin consent required: No" for
     `Mail.Send`, meaning you can consent yourself at sign-in — no IT ticket
     needed. (If your org *does* require admin consent, you'll hit that
     during step 3 below and need it granted first.)
   - Copy the **"Application (client) ID"** from the Overview page. If you
     picked an org/work account type, also copy the **"Directory (tenant) ID"**.
2. `export OUTLOOK_CLIENT_ID=<client id>` (and `export OUTLOOK_TENANT=<tenant id>`
   for an org/work account — personal accounts can leave this as the default `"common"`).
3. Run the setup script once and follow the printed device-code URL/code:
   ```bash
   python scripts/outlook_auth_setup.py
   ```
   This caches a refresh token to `config/outlook_token_cache.json` (gitignored).
4. From then on, `SENDER=outlook` sends silently — `run_daily.py` acquires a
   fresh access token from the cached refresh token on every run.

## Run

One-shot (intended to be invoked by cron every minute or so between the
scheduled time and the end of the send window — it no-ops outside that
window):

```bash
WEATHER_LAT=47.65655 WEATHER_LON=-122.31256 SENDER=outlook RECIPIENT_EMAIL=you@example.com python scripts/run_daily.py
```

Example crontab entry (fires every minute; the pipeline itself decides
whether it's actually time to send):

```
* * * * * cd /path/to/weather-outfit-recommender && .venv/bin/python scripts/run_daily.py >> run.log 2>&1
```

### Automatic daily run on macOS (launchd)

On macOS, `launchd` is the standard replacement for cron and survives login
sessions. A job is installed at
`~/Library/LaunchAgents/com.janelu.weather-outfit-recommender.plist`, firing
at 7:00, 7:05, 7:10, and 7:15 AM Pacific — multiple firings give a retry
window for transient failures (Failure mode #3), and `daily_state.py`
records the first terminal outcome for the day so a retry-after-success
never double-sends.

```bash
# check status / last exit code
launchctl print gui/501/com.janelu.weather-outfit-recommender

# trigger a run right now, for testing
launchctl kickstart -p gui/501/com.janelu.weather-outfit-recommender

# tail the log
tail -f run.log

# uninstall
launchctl bootout gui/501/com.janelu.weather-outfit-recommender
rm ~/Library/LaunchAgents/com.janelu.weather-outfit-recommender.plist
```

The plist bakes in `WEATHER_LAT`/`WEATHER_LON`/`RECIPIENT_EMAIL`/`OUTLOOK_CLIENT_ID`/
`OUTLOOK_TENANT` as environment variables (none of these are secrets — the
OAuth refresh token itself lives only in the gitignored token cache file).
`RECOMMENDER` is set to `stub` there since no `ANTHROPIC_API_KEY` is
configured; switch it to `anthropic` and add that key to the plist's
`EnvironmentVariables` for real AI-generated recommendation text.

## Test

```bash
python -m pytest -q
```

41 tests: rule-based consistency checks, weather-cache freshness/staleness,
timezone/send-window edges, preference storage, AI-output sanitization,
once-per-day dedup, and one end-to-end scenario per failure mode in
`tests/test_pipeline_scenarios.py`.

## Out of scope (per the build brief)

- Real-time wardrobe inventory tracking
- Learning from what the user actually wears (preferences are explicit, user-set only)
- Multiple weather-source cross-validation
