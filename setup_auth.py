"""
setup_auth.py
──────────────
Interactive script for obtaining a LinkedIn OAuth 2.0 access token.

LinkedIn uses OAuth 2.0 Authorization Code Flow.
This script:
  1. Guides you to create a LinkedIn Developer App (one-time)
  2. Opens the authorization URL in your browser
  3. Captures the auth code from the redirect
  4. Exchanges it for an access token (valid for 60 days)
  5. Displays the token + URN to copy into GitHub Secrets

Prerequisites:
  - LinkedIn account
  - Create a free Developer App at: https://www.linkedin.com/developers/apps/new
  - Add "Sign In with LinkedIn" and "Share on LinkedIn" products to your app
  - Add http://localhost:8080/callback as an Authorized Redirect URL

Required permissions to request:
  openid, profile, w_member_social  (personal profile posting)
  r_organization_social, w_organization_social  (company page posting — optional)
"""

from __future__ import annotations

import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser

import requests

AUTH_URL        = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL       = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_URI    = "http://localhost:8080/callback"
SCOPES          = ["openid", "profile", "w_member_social"]
ORG_SCOPES      = ["r_organization_social", "w_organization_social"]


def _input(prompt: str) -> str:
    return input(prompt).strip()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Tiny HTTP server to capture the OAuth callback."""
    code: str = ""
    state: str = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code  = params.get("code",  [""])[0]
        _CallbackHandler.state = params.get("state", [""])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authorization successful!</h2>"
            b"<p>You can now close this tab and return to the terminal.</p></body></html>"
        )

    def log_message(self, fmt, *args):
        pass  # suppress HTTP server logs


def run() -> None:
    print("\n" + "=" * 60)
    print("  VB Exports — LinkedIn OAuth Setup")
    print("=" * 60)

    print("""
STEP 1: Create a LinkedIn Developer App (one-time setup)
─────────────────────────────────────────────────────────
1. Go to: https://www.linkedin.com/developers/apps/new
2. Fill in:
     App name:    VB Exports Automation
     LinkedIn page: Your company page (or personal for testing)
     App logo:    Any square image
3. Click "Create app"
4. On the Auth tab, add redirect URL: http://localhost:8080/callback
5. Add these PRODUCTS to the app:
     • "Sign In with LinkedIn using OpenID Connect"
     • "Share on LinkedIn"
6. Copy your Client ID and Client Secret
""")

    client_id     = _input("Enter your LinkedIn App CLIENT ID: ")
    client_secret = _input("Enter your LinkedIn App CLIENT SECRET: ")

    include_org = _input("Include company page posting permissions? (y/n): ").lower() == "y"
    all_scopes  = SCOPES + (ORG_SCOPES if include_org else [])
    scope_str   = " ".join(all_scopes)

    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "state":         state,
        "scope":         scope_str,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\nSTEP 2: Opening browser for authorization...")
    print(f"URL: {auth_url}\n")

    # Start callback server
    server = http.server.HTTPServer(("localhost", 8080), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    webbrowser.open(auth_url)
    print("Waiting for LinkedIn authorization callback (up to 120 seconds)...")

    for _ in range(120):
        time.sleep(1)
        if _CallbackHandler.code:
            break

    server.server_close()

    if not _CallbackHandler.code:
        print("ERROR: No authorization code received within 120 seconds.")
        print("Try manually navigating to the URL above in your browser.")
        sys.exit(1)

    if _CallbackHandler.state != state:
        print("ERROR: State mismatch — possible CSRF attempt. Aborting.")
        sys.exit(1)

    print(f"\nSTEP 3: Exchanging auth code for access token...")

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type":    "authorization_code",
            "code":          _CallbackHandler.code,
            "redirect_uri":  REDIRECT_URI,
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )

    if token_resp.status_code != 200:
        print(f"ERROR: Token exchange failed (HTTP {token_resp.status_code})")
        print(token_resp.text)
        sys.exit(1)

    token_data   = token_resp.json()
    access_token = token_data.get("access_token", "")
    expires_in   = token_data.get("expires_in", 0)
    expires_days = expires_in // 86400

    if not access_token:
        print("ERROR: No access_token in response:", token_data)
        sys.exit(1)

    # Fetch profile info to get URN
    profile_resp = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile      = profile_resp.json() if profile_resp.ok else {}
    person_urn   = f"urn:li:person:{profile.get('sub', '')}"

    print(f"\n{'=' * 60}")
    print("  AUTHORIZATION SUCCESSFUL!")
    print(f"{'=' * 60}")
    print(f"\nToken expires in: {expires_days} days")
    print(f"Authenticated as: {profile.get('name', 'Unknown')}")
    print(f"\n{'─' * 60}")
    print("Copy these values to GitHub Secrets:")
    print(f"{'─' * 60}")
    print(f"\nLINKEDIN_ACCESS_TOKEN = {access_token}")
    print(f"LINKEDIN_PERSON_URN   = {person_urn}")
    print(f"\n{'─' * 60}")
    print("GitHub Secrets path:")
    print("  Your repo → Settings → Secrets and variables → Actions → New repository secret")
    print(f"{'─' * 60}\n")

    # Optionally save to local .env for local testing
    save = _input("Save to local .env file for local testing? (y/n): ")
    if save.lower() == "y":
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nLINKEDIN_ACCESS_TOKEN={access_token}\n")
            f.write(f"LINKEDIN_PERSON_URN={person_urn}\n")
        print(f"Saved to {env_path}")
        print("WARNING: Keep .env out of Git — it's in .gitignore")


if __name__ == "__main__":
    run()
