"""One-time LOCAL script to generate an OAuth refresh token for Drive
uploads. Not part of the scheduled worker — run this once on your own
machine, then throw the output into Render and forget about it.

Why this exists: service accounts have zero storage quota on a personal
(non-Workspace) Google account, so main.py's Drive uploads need to run as
a real Google account instead (see README "OAuth setup for Drive
uploads").

Usage:
    pip install google-auth-oauthlib
    python get_oauth_refresh_token.py

This opens a browser for you to sign in as whichever Google account
should own the uploaded files (e.g. the same one that owns the Drive
Master Folder), then prints a refresh token to paste into Render.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def main():
    client_id = input("OAuth Client ID: ").strip()
    client_secret = input("OAuth Client Secret: ").strip()
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nSuccess! Add these three env vars in Render (Environment tab):\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID={client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
