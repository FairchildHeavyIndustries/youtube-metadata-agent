"""One-time OAuth 2.0 flow to obtain a refresh token for the YouTube Data API."""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def run_oauth_flow() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0)

    refresh_token = credentials.refresh_token
    print("\n" + "=" * 60)
    print("OAuth flow complete.")
    print(f"Refresh token: {refresh_token}")
    print("=" * 60)
    print("\nAdd this to your .env file:")
    print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
    print("\nOr save as a GitHub Actions secret named GOOGLE_REFRESH_TOKEN")

    tokens_path = os.path.join(os.path.dirname(__file__), "..", ".tokens.json")
    with open(tokens_path, "w") as f:
        json.dump(
            {
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            f,
            indent=2,
        )
    print(f"\nTokens also saved to .tokens.json (gitignored)")


if __name__ == "__main__":
    run_oauth_flow()
