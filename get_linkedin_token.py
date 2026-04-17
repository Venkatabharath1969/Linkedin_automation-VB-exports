"""
get_linkedin_token.py
──────────────────────
One-shot LinkedIn OAuth token retrieval.
Takes Client ID and Secret as CLI args so no manual typing needed.
Writes token directly to .env.

Usage:  
  python get_linkedin_token.py <client_id> <client_secret>

What you need to do:
  1. Script opens a browser tab (LinkedIn authorization page)
  2. You click "Allow" on that page
  3. Script captures the token automatically
  4. Token is written to .env and printed to screen
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser

import requests

AUTH_URL     = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL    = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES       = ["openid", "profile", "w_member_social"]
ENV_FILE     = pathlib.Path(__file__).parent / ".env"

_code_received = {"code": "", "state": ""}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _code_received["code"]  = qs.get("code",  [""])[0]
        _code_received["state"] = qs.get("state", [""])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>
        <h2 style='color:green'>LinkedIn Authorization Successful!</h2>
        <p>You can close this tab now and return to the terminal.</p>
        </body></html>
        """)

    def log_message(self, fmt, *args):
        pass   # suppress HTTP server output


def _update_env(key: str, value: str) -> None:
    """Upserts a key=value pair in the .env file."""
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines   = content.splitlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    if len(sys.argv) < 3:
        print("Usage: python get_linkedin_token.py <client_id> <client_secret>")
        sys.exit(1)

    client_id     = sys.argv[1].strip()
    client_secret = sys.argv[2].strip()
    state         = secrets.token_urlsafe(16)

    # Build auth URL
    params = {
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "state":         state,
        "scope":         " ".join(SCOPES),
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    # Start local callback server
    server = http.server.HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    print("\n" + "="*60)
    print("  VB Exports — LinkedIn Token Generator")
    print("="*60)
    print("\nOpening browser for LinkedIn authorization...")
    print(">> ACTION REQUIRED: Click 'Allow' on the LinkedIn page that opens.")
    print(f"\nIf browser doesn't open, paste this URL manually:\n{auth_url}\n")

    webbrowser.open(auth_url)

    # Wait up to 120 seconds for the callback
    for i in range(120):
        time.sleep(1)
        if _code_received["code"]:
            break
        if i % 10 == 9:
            print(f"  Waiting for authorization... ({i+1}s)")
    
    server.server_close()

    if not _code_received["code"]:
        print("\nERROR: No auth code received within 120 seconds.")
        print("Make sure you clicked 'Allow' on the LinkedIn authorization page.")
        sys.exit(1)

    if _code_received["state"] != state:
        print("\nERROR: State mismatch — security check failed.")
        sys.exit(1)

    print("\nAuthorization code received. Exchanging for access token...")

    # Exchange code for token
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type":    "authorization_code",
            "code":          _code_received["code"],
            "redirect_uri":  REDIRECT_URI,
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )

    if token_resp.status_code != 200:
        print(f"\nERROR: Token exchange failed (HTTP {token_resp.status_code})")
        print(token_resp.text)
        sys.exit(1)

    td           = token_resp.json()
    access_token = td.get("access_token", "")
    expires_days = td.get("expires_in", 0) // 86400

    if not access_token:
        print(f"\nERROR: No access_token in response: {td}")
        sys.exit(1)

    # Get person URN from /userinfo
    profile_resp = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    profile    = profile_resp.json() if profile_resp.ok else {}
    person_urn = f"urn:li:person:{profile.get('sub', '')}"
    name       = profile.get("name", "Unknown")

    # Write to .env
    _update_env("LINKEDIN_ACCESS_TOKEN", access_token)
    _update_env("LINKEDIN_PERSON_URN",   person_urn)

    print("\n" + "="*60)
    print("  SUCCESS! Token written to .env")
    print("="*60)
    print(f"  Authenticated as : {name}")
    print(f"  Person URN       : {person_urn}")
    print(f"  Token expires in : {expires_days} days")
    print(f"  Token preview    : {access_token[:20]}...")
    print("\n  .env has been updated automatically.")
    print("  Next step: python main.py --dry-run")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
