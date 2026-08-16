"""Message delivery. A pluggable Sender so the pipeline doesn't care how
the recommendation actually goes out.

ConsoleSender is the default (safe, no external side effects). OutlookEmailSender
sends via the Microsoft Graph API but requires credentials/a cached token to
be configured explicitly — it is never wired up automatically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger("weather_outfit.messaging")

GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
GRAPH_MAIL_SEND_SCOPES = ["Mail.Send"]

DEFAULT_TOKEN_CACHE_PATH = Path(__file__).resolve().parent.parent / "config" / "outlook_token_cache.json"


class SendError(Exception):
    pass


class Sender(Protocol):
    def send(self, to: str, message: str) -> None: ...


class ConsoleSender:
    """Default sender: logs the message instead of delivering it.
    Useful for local runs, dry-runs, and tests.
    """

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, message: str) -> None:
        self.sent.append((to, message))
        logger.info("[console-sender] to=%s message=%r", to, message)


class OutlookEmailSender:
    """Sends the recommendation as an email via the Microsoft Graph API
    (works for both outlook.com/hotmail.com personal accounts and Microsoft
    365 work/school accounts).

    Auth is MSAL device-code flow with a cached token: run
    scripts/outlook_auth_setup.py once interactively, and this class reuses
    (and silently refreshes) the cached token on every subsequent send —
    no client secret required, so it's safe for a cron job.

    Requires OUTLOOK_CLIENT_ID to be configured (an Azure app registration —
    see scripts/outlook_auth_setup.py docstring for the one-time setup).
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        tenant: Optional[str] = None,
        token_cache_path: Optional[Path] = None,
        subject: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("OUTLOOK_CLIENT_ID")
        self.tenant = tenant or os.environ.get("OUTLOOK_TENANT", "common")
        self.token_cache_path = Path(
            token_cache_path or os.environ.get("OUTLOOK_TOKEN_CACHE_PATH", DEFAULT_TOKEN_CACHE_PATH)
        )
        self.subject = subject or "Today's outfit"
        if not self.client_id:
            raise SendError(
                "OutlookEmailSender requires OUTLOOK_CLIENT_ID to be configured "
                "(see scripts/outlook_auth_setup.py)."
            )

    def _acquire_access_token(self) -> str:
        import msal  # local import: optional dependency

        cache = msal.SerializableTokenCache()
        if self.token_cache_path.exists():
            cache.deserialize(self.token_cache_path.read_text())

        app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant}",
            token_cache=cache,
        )

        accounts = app.get_accounts()
        result = app.acquire_token_silent(GRAPH_MAIL_SEND_SCOPES, account=accounts[0]) if accounts else None

        if cache.has_state_changed:
            self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_path.write_text(cache.serialize())

        if not result or "access_token" not in result:
            error = (result or {}).get("error_description", "no cached credentials")
            raise SendError(
                f"could not silently acquire an Outlook token ({error}). "
                "Run scripts/outlook_auth_setup.py once to (re)authenticate."
            )
        return result["access_token"]

    def send(self, to: str, message: str) -> None:
        import requests  # local import: optional dependency

        access_token = self._acquire_access_token()
        payload = {
            "message": {
                "subject": self.subject,
                "body": {"contentType": "Text", "content": message},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": False,
        }
        try:
            resp = requests.post(
                GRAPH_SEND_MAIL_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise SendError(f"failed to send email via Outlook/Graph: {exc}") from exc
