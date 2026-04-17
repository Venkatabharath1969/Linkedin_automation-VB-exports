"""
publishers/facebook_publisher.py
──────────────────────────────────
Posts to a Facebook Page using the Graph API (v21.0).
Uploads carousel slide images as a multi-photo post.

Free tier: no cost per call, no credit card required.
  ✦ Page posting rate: 4,800 calls per 24 hours
  ✦ Requires: FACEBOOK_PAGE_ID, FACEBOOK_ACCESS_TOKEN (long-lived page token)

How it works:
  1. Extract individual slide images from the carousel PDF as PNGs
  2. Upload each image to the page's photo library (unpublished=true)
  3. Create a multi-photo post referencing all photo IDs

To obtain a long-lived Page Access Token:
  1. Create a Facebook App at developers.facebook.com
  2. Add the Page as a managed page
  3. Generate Page Access Token with:
     pages_manage_posts, pages_read_engagement permissions
  4. Exchange for a 60-day long-lived token
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Optional

import requests

from config import (
    FACEBOOK_PAGE_ID, FACEBOOK_ACCESS_TOKEN,
    API_MAX_RETRIES, API_INITIAL_DELAY,
)

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ══════════════════════════════════════════════════════════════════════════════
# PDF → PNG slide extraction
# ══════════════════════════════════════════════════════════════════════════════

def _extract_slide_images(pdf_path: str) -> list[bytes]:
    """
    Converts each page of the carousel PDF to a PNG image (bytes).
    Uses PyMuPDF (fitz) if available, falls back to pdf2image.

    Returns list of PNG bytes in slide order.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        images = []
        for page in doc:
            # 2x scale = 144dpi — good quality for social media
            mat  = fitz.Matrix(2.0, 2.0)
            pix  = page.get_pixmap(matrix=mat, alpha=False)
            images.append(pix.tobytes("png"))
        doc.close()
        log.info("Extracted %d slide images via PyMuPDF", len(images))
        return images
    except ImportError:
        pass

    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=144)
        images = []
        for page in pages:
            buf = io.BytesIO()
            page.save(buf, format="PNG")
            images.append(buf.getvalue())
        log.info("Extracted %d slide images via pdf2image", len(images))
        return images
    except ImportError:
        pass

    log.error(
        "No PDF-to-image library found. Install PyMuPDF: pip install pymupdf\n"
        "Facebook posting requires image files extracted from the PDF."
    )
    return []


# ══════════════════════════════════════════════════════════════════════════════
# Graph API helpers
# ══════════════════════════════════════════════════════════════════════════════

def _retry_post(url: str, **kwargs) -> requests.Response:
    """POST with exponential backoff retry."""
    delay = API_INITIAL_DELAY
    for attempt in range(1, API_MAX_RETRIES + 1):
        resp = requests.post(url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == API_MAX_RETRIES:
                resp.raise_for_status()
            log.warning("Attempt %d/%d → HTTP %d, retrying in %ds",
                        attempt, API_MAX_RETRIES, resp.status_code, delay)
            time.sleep(delay)
            delay *= 2
        else:
            resp.raise_for_status()
            return resp
    raise RuntimeError("Facebook retry exhausted")


def _upload_photo_unpublished(
    image_bytes: bytes,
    page_id: str,
    page_token: str,
) -> str:
    """
    Uploads a single PNG to the page's photo library (unpublished).
    Returns the photo ID.
    """
    resp = _retry_post(
        f"{GRAPH_BASE}/{page_id}/photos",
        data={
            "access_token": page_token,
            "published":    "false",
        },
        files={"source": ("slide.png", image_bytes, "image/png")},
        timeout=60,
    )
    photo_id = resp.json().get("id", "")
    log.debug("Uploaded photo: %s", photo_id)
    return photo_id


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def post_carousel(
    caption: str,
    pdf_path: str,
    page_id: Optional[str] = None,
    page_token: Optional[str] = None,
) -> str:
    """
    Posts a carousel (multi-photo) to a Facebook Page.

    Args:
        caption    : Post message text
        pdf_path   : Path to the generated carousel PDF
        page_id    : Facebook Page ID (defaults to config.FACEBOOK_PAGE_ID)
        page_token : Long-lived Page Access Token (defaults to config.FACEBOOK_ACCESS_TOKEN)

    Returns the created post ID string.
    Raises RuntimeError on failure.
    """
    pid   = page_id    or FACEBOOK_PAGE_ID
    token = page_token or FACEBOOK_ACCESS_TOKEN

    if not pid or not token:
        raise ValueError(
            "FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN must be set. "
            "See .env.example for setup instructions."
        )

    # ── Extract slides as images ──────────────────────────────────────────
    images = _extract_slide_images(pdf_path)
    if not images:
        raise RuntimeError("No images extracted from PDF — cannot post to Facebook")

    # Limit to 10 images (Facebook max per multi-photo post)
    images = images[:10]
    log.info("Uploading %d slide images to Facebook...", len(images))

    # ── Upload each image unpublished ─────────────────────────────────────
    photo_ids: list[str] = []
    for i, img_bytes in enumerate(images, 1):
        photo_id = _upload_photo_unpublished(img_bytes, pid, token)
        if photo_id:
            photo_ids.append(photo_id)
            log.info("Slide %d/%d uploaded: %s", i, len(images), photo_id)

    if not photo_ids:
        raise RuntimeError("All Facebook photo uploads failed")

    # ── Create multi-photo post ───────────────────────────────────────────
    attached_media = [{"media_fbid": pid_val} for pid_val in photo_ids]

    resp = _retry_post(
        f"{GRAPH_BASE}/{pid}/feed",
        json={
            "message":        caption,
            "attached_media": attached_media,
            "access_token":   token,
        },
        timeout=30,
    )

    post_id = resp.json().get("id", "")
    log.info("Facebook post created: %s (%d photos)", post_id, len(photo_ids))
    return post_id
