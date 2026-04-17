"""
publishers/linkedin_publisher.py
──────────────────────────────────
Posts PDF carousels and text captions to LinkedIn via the REST API.

Endpoints used:
  POST /rest/documents?action=initializeUpload  — get upload URL
  PUT  <uploadUrl>                              — binary upload
  POST /rest/posts                              — create document post
  GET  /rest/posts?author=<urn>&count=1         — get latest post URN
  POST /rest/socialActions/<urn>/comments       — post first comment

All calls use exponential-backoff retry (3 attempts, skip 4xx except 429).
"""

from __future__ import annotations

import logging
import os
import pathlib
import time
from typing import Optional

import requests
import urllib3
import os
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import LINKEDIN_API_VERSION, LINKEDIN_AUTHOR_URN, API_MAX_RETRIES, API_INITIAL_DELAY

# Corporate SSL proxy workaround — disable cert verification
_VERIFY_SSL = False


def _get_author_urn() -> str:
    """Read LinkedIn URN fresh from env (dotenv loads after config import)."""
    return (
        os.environ.get("LINKEDIN_ORG_URN", "").strip()
        or os.environ.get("LINKEDIN_PERSON_URN", "").strip()
        or LINKEDIN_AUTHOR_URN
    )

log = logging.getLogger(__name__)

BASE    = "https://api.linkedin.com"
HEADERS_BASE = {"LinkedIn-Version": LINKEDIN_API_VERSION, "X-Restli-Protocol-Version": "2.0.0"}


# ══════════════════════════════════════════════════════════════════════════════
# Retry wrapper
# ══════════════════════════════════════════════════════════════════════════════

def _retry(fn, *args, **kwargs):
    delay = API_INITIAL_DELAY
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            resp = fn(*args, **kwargs)
            # Non-retryable 4xx (except 429 rate-limit)
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                log.error("LinkedIn API %d — not retrying: %s", resp.status_code, resp.text[:300])
                resp.raise_for_status()
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            if attempt == API_MAX_RETRIES:
                raise
            log.warning("Attempt %d/%d failed (%s) — retrying in %ds",
                        attempt, API_MAX_RETRIES, e, delay)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("_retry exhausted — should not reach here")


# ══════════════════════════════════════════════════════════════════════════════
# Document (PDF carousel) upload + post
# ══════════════════════════════════════════════════════════════════════════════

def _upload_document(pdf_path: str, access_token: str, author_urn: str) -> str:
    """
    Uploads a PDF to LinkedIn's asset store.
    Returns the document URN (e.g. urn:li:document:...).
    """
    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    # Step 1: Initialize upload
    init_resp = _retry(
        requests.post,
        f"{BASE}/rest/documents",
        params={"action": "initializeUpload"},
        headers=headers,
        json={
            "initializeUploadRequest": {
                "owner": author_urn,
            }
        },
        timeout=30,
        verify=_VERIFY_SSL,
    )
    upload_data = init_resp.json()
    upload_url  = upload_data["value"]["uploadUrl"]
    document_urn = upload_data["value"]["document"]

    log.info("LinkedIn document URN: %s", document_urn)

    # Step 2: Upload binary
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    upload_resp = _retry(
        requests.put,
        upload_url,
        data=pdf_bytes,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/octet-stream",
        },
        timeout=120,
        verify=_VERIFY_SSL,
    )
    log.info("PDF uploaded: %d bytes → HTTP %d", len(pdf_bytes), upload_resp.status_code)
    return document_urn


def post_document(
    caption: str,
    pdf_path: str,
    access_token: str,
    author_urn: Optional[str] = None,
) -> str:
    """
    Uploads a PDF and creates a LinkedIn document (carousel) post.

    Args:
        caption     : Post caption text (LinkedIn allows up to 3,000 chars)
        pdf_path    : Absolute path to the generated PDF file
        access_token: LinkedIn OAuth 2.0 access token
        author_urn  : Override author URN (defaults to config.LINKEDIN_AUTHOR_URN)

    Returns the created post URN.
    """
    urn = author_urn or _get_author_urn()
    if not urn:
        raise ValueError("LinkedIn author URN not configured (LINKEDIN_PERSON_URN or LINKEDIN_ORG_URN)")

    document_urn = _upload_document(pdf_path, access_token, urn)

    # Brief wait to ensure CDN propagation
    from config import API_CDN_WAIT_SECONDS
    time.sleep(API_CDN_WAIT_SECONDS)

    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    body = {
        "author":     urn,
        "commentary": caption,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {
            "media": {
                "title": pathlib.Path(pdf_path).stem.replace("_", " ")[:200],
                "id":    document_urn,
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    resp = _retry(
        requests.post,
        f"{BASE}/rest/posts",
        headers=headers,
        json=body,
        timeout=30,
        verify=_VERIFY_SSL,
    )

    post_urn = resp.headers.get("x-restli-id", "")
    log.info("LinkedIn post created: %s", post_urn)
    return post_urn


# ══════════════════════════════════════════════════════════════════════════════
# First comment (boosts early engagement signal)
# ══════════════════════════════════════════════════════════════════════════════

def _get_latest_post_urn(access_token: str, author_urn: str) -> str | None:
    """Fetches the URN of the most recently published post by this author."""
    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {access_token}",
    }
    try:
        resp = requests.get(
            f"{BASE}/rest/posts",
            params={"author": author_urn, "count": 1, "q": "author"},
            headers=headers,
            timeout=15,
            verify=_VERIFY_SSL,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if elements:
            return elements[0].get("id", "")
    except Exception as e:
        log.warning("Could not fetch latest post URN: %s", e)
    return None


def post_first_comment(
    comment_text: str,
    access_token: str,
    post_urn: Optional[str] = None,
    author_urn: Optional[str] = None,
) -> bool:
    """
    Posts a first comment on the latest LinkedIn post.
    Returns True on success.

    Args:
        comment_text : The comment to post
        access_token : LinkedIn OAuth token
        post_urn     : URN of the specific post (from post_document return value)
        author_urn   : Override author; defaults to config.LINKEDIN_AUTHOR_URN
    """
    urn = author_urn or _get_author_urn()
    if not post_urn:
        from config import FIRST_COMMENT_DELAY_SECONDS
        log.info("Waiting %ds before first comment...", FIRST_COMMENT_DELAY_SECONDS)
        time.sleep(FIRST_COMMENT_DELAY_SECONDS)
        post_urn = _get_latest_post_urn(access_token, urn)

    if not post_urn:
        log.warning("Cannot find latest post URN — skipping first comment")
        return False

    headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    try:
        import urllib.parse
        encoded_urn = urllib.parse.quote(post_urn, safe="")
        resp = _retry(
            requests.post,
            f"{BASE}/rest/socialActions/{encoded_urn}/comments",
            headers=headers,
            json={
                "actor":   urn,
                "message": {"text": comment_text},
            },
            timeout=20,
            verify=_VERIFY_SSL,
        )
        log.info("First comment posted (HTTP %d)", resp.status_code)
        return True
    except Exception as e:
        log.warning("First comment failed: %s", e)
        return False
