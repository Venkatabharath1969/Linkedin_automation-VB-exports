"""
publishers/linkedin_publisher.py
──────────────────────────────────
Posts carousel slides to LinkedIn via the REST API.

Strategy: multi-image post using individual slide PNGs.
  - No "Documents API" product approval needed
  - Only requires w_member_social scope (standard)
  - LinkedIn allows up to 20 images per post

Endpoints used:
  POST /rest/images?action=initializeUpload  — get upload URL per image
  PUT  <uploadUrl>                           — binary upload
  POST /rest/posts                           — create multi-image post
  GET  /rest/posts?author=<urn>&count=1      — get latest post URN
  POST /rest/socialActions/<urn>/comments    — post first comment

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
# Image upload helpers + multi-image carousel post
# ══════════════════════════════════════════════════════════════════════════════

def _upload_image(png_path: str, access_token: str, author_urn: str) -> str:
    """
    Uploads a single PNG to LinkedIn using the v2 assets API.
    Returns asset URN (e.g. urn:li:digitalmediaAsset:...).
    The v2 API is used because the REST /rest/images endpoint is blocked
    from GitHub Actions IP ranges.
    """
    headers_v2 = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    # Step 1: Register upload (v2 assets API)
    init_resp = _retry(
        requests.post,
        f"{BASE}/v2/assets",
        params={"action": "registerUpload"},
        headers=headers_v2,
        json={
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": author_urn,
                "serviceRelationships": [
                    {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                ],
            }
        },
        timeout=30,
        verify=_VERIFY_SSL,
    )
    data = init_resp.json()["value"]
    upload_url = data["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset_urn  = data["asset"] if "asset" in data else data.get("mediaArtifact", "").split(",")[0].lstrip("(")

    # Extract clean asset URN from mediaArtifact if needed
    media_artifact = data.get("mediaArtifact", "")
    if "asset" not in data and media_artifact:
        # Format: urn:li:digitalmediaMediaArtifact:(urn:li:digitalmediaAsset:...,...)
        import re
        m = re.search(r"(urn:li:digitalmediaAsset:[^,)]+)", media_artifact)
        asset_urn = m.group(1) if m else media_artifact

    # Step 2: Upload binary
    with open(png_path, "rb") as f:
        img_bytes = f.read()
    _retry(
        requests.put,
        upload_url,
        data=img_bytes,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/png"},
        timeout=120,
        verify=_VERIFY_SSL,
    )
    log.info("  Uploaded %s (%d KB) → %s", pathlib.Path(png_path).name, len(img_bytes) // 1024, asset_urn)
    return asset_urn


def _find_slide_pngs(pdf_path: str) -> list[str]:
    """Finds sorted slide PNGs in the same output dir as the PDF."""
    output_dir = pathlib.Path(pdf_path).parent
    pngs = sorted(output_dir.glob("slide_*.png"))
    if not pngs:
        log.warning("No slide PNGs found in %s", output_dir)
    return [str(p) for p in pngs]


def post_document(
    caption: str,
    pdf_path: str,
    access_token: str,
    author_urn: Optional[str] = None,
) -> str:
    """
    Uploads slide PNGs and creates a LinkedIn multi-image carousel post.
    (Uses /rest/images — only requires w_member_social, no Documents API approval needed.)

    Returns the created post URN.
    """
    urn = author_urn or _get_author_urn()
    if not urn:
        raise ValueError("LinkedIn author URN not configured (LINKEDIN_PERSON_URN or LINKEDIN_ORG_URN)")

    slide_pngs = _find_slide_pngs(pdf_path)
    if not slide_pngs:
        raise RuntimeError(f"No slide PNGs found alongside {pdf_path}")

    log.info("Uploading %d slide images to LinkedIn…", len(slide_pngs))
    image_urns: list[str] = []
    for i, png in enumerate(slide_pngs, 1):
        log.info("  Slide %d/%d", i, len(slide_pngs))
        image_urns.append(_upload_image(png, access_token, urn))

    from config import API_CDN_WAIT_SECONDS
    log.info("Waiting %ds for CDN propagation…", API_CDN_WAIT_SECONDS)
    time.sleep(API_CDN_WAIT_SECONDS)

    # Use v2 UGC Posts API — consistent with v2 asset upload
    headers_v2 = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    media_list = [
        {
            "status": "READY",
            "description": {"text": f"Slide {i + 1}"},
            "media": u,
            "title": {"text": f"Slide {i + 1}"},
        }
        for i, u in enumerate(image_urns)
    ]

    body = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption},
                "shareMediaCategory": "IMAGE",
                "media": media_list,
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = _retry(
        requests.post,
        f"{BASE}/v2/ugcPosts",
        headers=headers_v2,
        json=body,
        timeout=30,
        verify=_VERIFY_SSL,
    )
    post_urn = resp.headers.get("x-restli-id", "") or resp.json().get("id", "")
    log.info("LinkedIn post created: %s (%d images)", post_urn, len(image_urns))
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
