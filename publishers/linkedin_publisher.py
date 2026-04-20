"""
publishers/linkedin_publisher.py
──────────────────────────────────
Posts carousel slides to LinkedIn via the REST API.

Strategy: PDF document post using the Documents API.
  - Uploads the generated PDF as a LinkedIn Document carousel
  - Produces the swipeable "Page X of Y" carousel format (not multi-image)
  - Requires w_member_social (personal) or w_organization_social (company)
  - Works from GitLab CI GCP runners (confirmed unblocked)

Endpoints used:
  POST /rest/documents?action=initializeUpload  — get upload URL + document URN
  PUT  <uploadUrl>                              — binary PDF upload
  POST /rest/posts                              — create document carousel post
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

BASE         = "https://api.linkedin.com"
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
# PDF Document carousel post (Documents API)
# ══════════════════════════════════════════════════════════════════════════════

def post_document(
    caption: str,
    pdf_path: str,
    access_token: str,
    author_urn: Optional[str] = None,
) -> str:
    """
    Uploads the PDF via /rest/documents and creates a LinkedIn Document
    carousel post — the swipeable "Page X of Y" format visible on mobile
    and desktop, with download option for viewers.

    Flow:
      1. POST /rest/documents?action=initializeUpload  -> uploadUrl + document URN
      2. PUT  <uploadUrl>  with raw PDF bytes
      3. Wait for LinkedIn CDN to process PDF into carousel pages
      4. POST /rest/posts  with content.media.id = document URN

    Returns the created post URN.
    """
    urn = author_urn or _get_author_urn()
    if not urn:
        raise ValueError("LinkedIn author URN not configured (LINKEDIN_PERSON_URN or LINKEDIN_ORG_URN)")

    pdf_file = pathlib.Path(pdf_path)
    if not pdf_file.exists():
        raise RuntimeError(f"PDF not found: {pdf_path}")

    pdf_size_mb = pdf_file.stat().st_size / (1024 * 1024)
    log.info("Uploading PDF carousel via Documents API | author=%s | file=%s (%.2f MB)",
             urn, pdf_file.name, pdf_size_mb)

    api_headers = {
        **HEADERS_BASE,
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    # Step 1 — initialize document upload
    init_resp = _retry(
        requests.post,
        f"{BASE}/rest/documents",
        params={"action": "initializeUpload"},
        headers=api_headers,
        json={"initializeUploadRequest": {"owner": urn}},
        timeout=30,
        verify=_VERIFY_SSL,
    )
    value        = init_resp.json()["value"]
    upload_url   = value["uploadUrl"]
    document_urn = value["document"]   # urn:li:document:<id>
    log.info("  Document URN: %s", document_urn)

    # Step 2 — upload PDF binary
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    _retry(
        requests.put,
        upload_url,
        data=pdf_bytes,
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/octet-stream"},
        timeout=180,
        verify=_VERIFY_SSL,
    )
    log.info("  PDF uploaded (%d KB)", len(pdf_bytes) // 1024)

    # Step 3 — wait for LinkedIn CDN to process the PDF into carousel pages
    from config import API_CDN_WAIT_SECONDS
    wait = max(API_CDN_WAIT_SECONDS, 10)   # PDF processing needs at least 10s
    log.info("Waiting %ds for document CDN processing...", wait)
    time.sleep(wait)

    # Step 4 — create the document carousel post
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
                "title": pdf_file.name,
                "id":    document_urn,
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    log.info("Posting document carousel | author=%s", urn)
    resp = _retry(
        requests.post,
        f"{BASE}/rest/posts",
        headers=api_headers,
        json=body,
        timeout=30,
        verify=_VERIFY_SSL,
    )
    post_urn = resp.headers.get("x-restli-id", "")
    log.info("LinkedIn document carousel posted: %s", post_urn)
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
    Posts a first comment on the LinkedIn post.
    Returns True on success.
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
                "object":  encoded_urn,
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
