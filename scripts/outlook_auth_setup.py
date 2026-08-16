#!/usr/bin/env python3
"""One-time interactive setup for OutlookEmailSender.

Authenticates against Microsoft Graph via MSAL's device-code flow and
caches the resulting token, so scripts/run_daily.py can send mail silently
(and non-interactively) from cron afterward, refreshing the token as needed.

Prereqs — register a free app in the Azure Portal (portal.azure.com >
App registrations > New registration):
  - Supported account types: "Personal Microsoft accounts" if you're
    sending from an outlook.com/hotmail.com address, or "Accounts in any
    organizational directory and personal Microsoft accounts" to support
    both.
  - Platform: Authentication > Add a platform > "Mobile and desktop
    applications" > check the
    https://login.microsoftonline.com/common/oauth2/nativeclient redirect
    URI (this makes it a public client, so no client secret is needed).
  - API permissions: Microsoft Graph > Delegated permissions > Mail.Send
    (admin consent isn't required for a personal Microsoft account).
  - Copy the "Application (client) ID" — that's OUTLOOK_CLIENT_ID below.

Env vars:
  OUTLOOK_CLIENT_ID          - required, from the app registration above
  OUTLOOK_TENANT             - default "common"
  OUTLOOK_TOKEN_CACHE_PATH   - default config/outlook_token_cache.json
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.messaging import DEFAULT_TOKEN_CACHE_PATH, GRAPH_MAIL_SEND_SCOPES


def main() -> int:
    client_id = os.environ.get("OUTLOOK_CLIENT_ID")
    if not client_id:
        print("Set OUTLOOK_CLIENT_ID first — see this script's docstring for how to get one.", file=sys.stderr)
        return 1

    import msal

    tenant = os.environ.get("OUTLOOK_TENANT", "common")
    cache_path = Path(os.environ.get("OUTLOOK_TOKEN_CACHE_PATH", DEFAULT_TOKEN_CACHE_PATH))

    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text())

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )

    flow = app.initiate_device_flow(scopes=GRAPH_MAIL_SEND_SCOPES)
    if "user_code" not in flow:
        print(f"Failed to start device flow: {flow}", file=sys.stderr)
        return 1

    print(flow["message"])  # "To sign in, use a web browser to open https://... and enter the code XXXXXXX"
    result = app.acquire_token_by_device_flow(flow)  # blocks until the browser step completes

    if "access_token" not in result:
        print(f"Auth failed: {result.get('error_description', result)}", file=sys.stderr)
        return 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(cache.serialize())
    print(f"Authenticated as {result.get('id_token_claims', {}).get('preferred_username', '(unknown)')}.")
    print(f"Token cache saved to {cache_path} — scripts/run_daily.py can now send silently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
