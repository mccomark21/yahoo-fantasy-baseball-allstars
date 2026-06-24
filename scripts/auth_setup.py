#!/usr/bin/env python3
"""One-time OAuth setup to obtain a Yahoo refresh token.

Run this locally after creating a Yahoo Developer app and putting
YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET in your .env file:

    python scripts/auth_setup.py

It opens a browser to Yahoo's authorization page. Log in, approve the app,
then paste the verifier code (or the `code=...` value from the redirect URL)
back into the terminal prompt. The script prints your refresh token and
writes it into .env for you.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

import os  # noqa: E402 — after load_dotenv so .env is populated

consumer_key = os.environ.get("YAHOO_CONSUMER_KEY")
consumer_secret = os.environ.get("YAHOO_CONSUMER_SECRET")

if not consumer_key or not consumer_secret:
    print("Error: YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET must be set.")
    print(f"Add them to: {ENV_PATH}")
    print("See .env.example for the format.")
    sys.exit(1)

from yfpy.query import YahooFantasySportsQuery  # noqa: E402

print("Starting Yahoo OAuth2 authorization...")
print("A browser window will open. Log in to Yahoo and approve the app.")
print("Then copy the verifier code Yahoo shows you (or the `code=...` value")
print("from the redirect URL) and paste it at the prompt below.\n")

try:
    query = YahooFantasySportsQuery(
        league_id="0",
        game_code="mlb",
        yahoo_consumer_key=consumer_key,
        yahoo_consumer_secret=consumer_secret,
        browser_callback=True,
    )
except SystemExit:
    print("\nAuthorization failed. Double-check your consumer key and secret.")
    sys.exit(1)

refresh_token = query.oauth.refresh_token

print("\n" + "=" * 60)
print("  Authorization successful!")
print("=" * 60)
print(f"\nYour refresh token:\n\n  {refresh_token}\n")

# Persist it to .env so local runs work immediately.
set_key(str(ENV_PATH), "YAHOO_REFRESH_TOKEN", refresh_token)
print(f"Saved YAHOO_REFRESH_TOKEN to {ENV_PATH}\n")

print("Next: add these three as GitHub repository secrets")
print("(Settings -> Secrets and variables -> Actions -> New repository secret):")
print("  YAHOO_CONSUMER_KEY")
print("  YAHOO_CONSUMER_SECRET")
print("  YAHOO_REFRESH_TOKEN")
