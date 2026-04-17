"""
auth/token_manager.py
──────────────────────
Validates and manages the LinkedIn OAuth 2.0 access token.

LinkedIn tokens expire after 60 days. This module:
  1. Validates the token is set and not obviously expired
  2. On 401 errors, logs a clear human-readable message with renewal steps
  3. For GitHub Actions: optionally updates the LINKEDIN_ACCESS_TOKEN secret
     so the next run continues to work (requires GITHUB_TOKEN + PyNaCl)

Token renewal is manual — LinkedIn's API requires re-authorisation in a browser.
Run setup_auth.py to generate a new token when needed.
"""

from __future__ import annotations

import logging
import os
import time

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)

TOKEN_VERIFY_URL = "https://api.linkedin.com/v2/me"
DRY_RUN_TOKEN    = "DRY_RUN_FAKE_TOKEN"


# ══════════════════════════════════════════════════════════════════════════════
# Token validation
# ══════════════════════════════════════════════════════════════════════════════

def get_access_token() -> str:
    """
    Returns the LinkedIn access token from environment.
    Raises ValueError if not set.
    """
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "LINKEDIN_ACCESS_TOKEN is not set.\n"
            "Run: python setup_auth.py\n"
            "Then add the generated token to GitHub Secrets."
        )
    return token


def validate_token(access_token: str) -> bool:
    """
    Calls LinkedIn /v2/userinfo to verify the token is valid and not expired.
    Returns True if valid, False otherwise.
    """
    if access_token == DRY_RUN_TOKEN:
        log.info("DRY RUN mode — skipping token validation")
        return True

    try:
        resp = requests.get(
            TOKEN_VERIFY_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
            verify=False,
        )
        if resp.status_code == 200:
            user_info = resp.json()
            name = (
                user_info.get("localizedFirstName", "")
                or (user_info.get("firstName", {}).get("localized", {}) or {}).get(
                    list((user_info.get("firstName", {}).get("localized", {}) or {}).keys() or [""])[0], ""
                )
                or "Bharath S"
            )
            log.info("LinkedIn token valid — authenticated as: %s", name)
            return True
        elif resp.status_code == 401:
            log.error(
                "LinkedIn token EXPIRED or INVALID (HTTP 401).\n"
                "To renew:\n"
                "  1. Run: python setup_auth.py\n"
                "  2. Copy the new token to GitHub Secrets → LINKEDIN_ACCESS_TOKEN\n"
                "  Token expires every 60 days."
            )
            return False
        else:
            # 403 = wrong scope for this endpoint but token itself is valid
            # Any non-401 means the token is accepted by LinkedIn servers
            log.info("LinkedIn token check: HTTP %d — token accepted (not 401)", resp.status_code)
            return True
    except requests.RequestException as e:
        log.warning("Token validation failed (network): %s — assuming valid", e)
        return True   # Network failure ≠ invalid token; let the post attempt proceed


# ══════════════════════════════════════════════════════════════════════════════
# GitHub Secrets updater (for CI token refresh workflows)
# ══════════════════════════════════════════════════════════════════════════════

def update_github_secret(secret_name: str, secret_value: str) -> bool:
    """
    Updates a GitHub Actions repository secret programmatically.
    Requires GITHUB_REPO (owner/repo) and GITHUB_TOKEN env vars.

    Returns True on success. Uses PyNaCl for encryption.
    """
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    github_repo  = os.environ.get("GITHUB_REPO", "").strip()

    if not github_token or not github_repo:
        log.warning("GITHUB_TOKEN or GITHUB_REPO not set — cannot update secret")
        return False

    try:
        from nacl import encoding, public

        # Get the repo's public key for secret encryption
        key_resp = requests.get(
            f"https://api.github.com/repos/{github_repo}/actions/secrets/public-key",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        key_resp.raise_for_status()
        key_data   = key_resp.json()
        public_key = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())

        # Encrypt the secret value
        sealed_box     = public.SealedBox(public_key)
        encrypted      = sealed_box.encrypt(secret_value.encode())
        encrypted_b64  = encrypted.decode("utf-8") if isinstance(encrypted, bytes) else \
                         __import__("base64").b64encode(encrypted).decode("utf-8")

        # Store the secret
        put_resp = requests.put(
            f"https://api.github.com/repos/{github_repo}/actions/secrets/{secret_name}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            json={
                "encrypted_value": encrypted_b64,
                "key_id":          key_data["key_id"],
            },
            timeout=10,
        )
        if put_resp.status_code in (201, 204):
            log.info("GitHub secret '%s' updated successfully", secret_name)
            return True
        else:
            log.warning("GitHub secret update returned HTTP %d", put_resp.status_code)
            return False

    except ImportError:
        log.warning("PyNaCl not installed — cannot update GitHub secret. pip install PyNaCl")
        return False
    except Exception as e:
        log.warning("GitHub secret update failed: %s", e)
        return False
