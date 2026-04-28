"""Refresh token management with env var fallback to .tokens.json."""

import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
_TOKENS_FILE = Path(__file__).parent.parent / ".tokens.json"


def _load_from_file() -> dict | None:
    if _TOKENS_FILE.exists():
        with open(_TOKENS_FILE) as f:
            return json.load(f)
    return None


def get_credentials() -> Credentials:
    """Return valid OAuth credentials, refreshing if needed."""
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Fall back to .tokens.json for local dev
    if not refresh_token:
        tokens = _load_from_file()
        if tokens:
            refresh_token = tokens.get("refresh_token")
            client_id = client_id or tokens.get("client_id")
            client_secret = client_secret or tokens.get("client_secret")

    if not refresh_token:
        raise RuntimeError(
            "No refresh token found. Run auth/oauth_setup.py first, "
            "then set GOOGLE_REFRESH_TOKEN in .env or as a secret."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    if not creds.valid:
        creds.refresh(Request())

    return creds
