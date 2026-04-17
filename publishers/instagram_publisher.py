"""
publishers/instagram_publisher.py
───────────────────────────────────
Posts a carousel to Instagram via the Instagram Graph API.

Requirements:
  ✦ Instagram Business or Creator account
  ✦ Account linked to a Facebook Page
  ✦ Same long-lived Page Access Token as Facebook publisher

Flow (Instagram Graph API carousel):
  1. Extract PDF pages as PNG images
  2. Upload each PNG to Cloudinary (free tier: 25GB/mo) to get public HTTPS URLs
  3. Create child media containers for each image
  4. Create parent carousel container with children list
  5. Publish the carousel container

Why Cloudinary? Instagram Graph API requires images to be at public HTTPS URLs
accessible to Meta's servers. Cloudinary free tier handles this at no cost.

Rate limit: 25 posts per 24 hours per Instagram account.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Optional

import requests
import cloudinary
import cloudinary.uploader

from config import (
    INSTAGRAM_USER_ID, FACEBOOK_ACCESS_TOKEN,
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET,
    API_MAX_RETRIES, API_INITIAL_DELAY,
)
from publishers.facebook_publisher import _extract_slide_images

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ══════════════════════════════════════════════════════════════════════════════
# Cloudinary setup
# ══════════════════════════════════════════════════════════════════════════════

def _configure_cloudinary() -> None:
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        raise ValueError(
            "Cloudinary credentials not set. Add CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET to your secrets. "
            "Free account at cloudinary.com — no credit card required."
        )
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )


def _upload_to_cloudinary(image_bytes: bytes, public_id: str) -> str:
    """
    Uploads PNG bytes to Cloudinary and returns the secure HTTPS URL.
    Images are tagged for easy cleanup.
    """
    result = cloudinary.uploader.upload(
        image_bytes,
        public_id=public_id,
        folder="vb-exports-carousels",
        tags=["vb-exports", "auto-carousel"],
        resource_type="image",
        format="jpg",            # Convert to JPEG — smaller, IG compatible
        quality="auto:good",     # Cloudinary optimises quality automatically
        overwrite=True,
    )
    url = result.get("secure_url", "")
    log.debug("Cloudinary upload: %s → %s", public_id, url)
    return url


# ══════════════════════════════════════════════════════════════════════════════
# Instagram Graph API helpers
# ══════════════════════════════════════════════════════════════════════════════

def _retry_post(url: str, **kwargs) -> requests.Response:
    """POST with exponential backoff."""
    delay = API_INITIAL_DELAY
    for attempt in range(1, API_MAX_RETRIES + 1):
        resp = requests.post(url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == API_MAX_RETRIES:
                resp.raise_for_status()
            log.warning("Instagram API %d — retrying in %ds", resp.status_code, delay)
            time.sleep(delay)
            delay *= 2
        else:
            resp.raise_for_status()
            return resp
    raise RuntimeError("Instagram retry exhausted")


def _create_child_container(user_id: str, image_url: str, token: str) -> str:
    """Creates an unpublished child media container. Returns container ID."""
    resp = _retry_post(
        f"{GRAPH_BASE}/{user_id}/media",
        data={
            "image_url":        image_url,
            "is_carousel_item": "true",
            "access_token":     token,
        },
        timeout=30,
    )
    container_id = resp.json().get("id", "")
    log.debug("Child container: %s", container_id)
    return container_id


def _create_carousel_container(
    user_id: str,
    children: list[str],
    caption: str,
    token: str,
) -> str:
    """Creates the parent carousel container with all child IDs. Returns container ID."""
    resp = _retry_post(
        f"{GRAPH_BASE}/{user_id}/media",
        data={
            "media_type":   "CAROUSEL",
            "children":     ",".join(children),
            "caption":      caption[:2200],          # Instagram caption limit
            "access_token": token,
        },
        timeout=30,
    )
    container_id = resp.json().get("id", "")
    log.info("Carousel container: %s (%d children)", container_id, len(children))
    return container_id


def _publish_container(user_id: str, container_id: str, token: str) -> str:
    """Publishes a media container. Returns the created media ID."""
    resp = _retry_post(
        f"{GRAPH_BASE}/{user_id}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": token,
        },
        timeout=30,
    )
    media_id = resp.json().get("id", "")
    log.info("Instagram post published: %s", media_id)
    return media_id


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def post_carousel(
    caption: str,
    pdf_path: str,
    ig_user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> str:
    """
    Posts a carousel to Instagram from a PDF.

    Args:
        caption      : Post caption (max 2,200 chars for Instagram)
        pdf_path     : Absolute path to the carousel PDF
        ig_user_id   : Instagram Business User ID (defaults to config.INSTAGRAM_USER_ID)
        access_token : Page Access Token (defaults to config.FACEBOOK_ACCESS_TOKEN)

    Returns the published media ID string.
    """
    uid   = ig_user_id   or INSTAGRAM_USER_ID
    token = access_token or FACEBOOK_ACCESS_TOKEN

    if not uid or not token:
        raise ValueError(
            "INSTAGRAM_USER_ID and FACEBOOK_ACCESS_TOKEN must be set. "
            "See .env.example for setup instructions."
        )

    _configure_cloudinary()

    # ── Extract slides as images ──────────────────────────────────────────
    images = _extract_slide_images(pdf_path)
    if not images:
        raise RuntimeError("No images extracted from PDF — cannot post to Instagram")

    # Instagram carousel: 2–10 items
    images = images[:10]
    log.info("Uploading %d slides to Cloudinary for Instagram...", len(images))

    # ── Upload to Cloudinary ──────────────────────────────────────────────
    import pathlib
    base_name = pathlib.Path(pdf_path).stem

    public_urls: list[str] = []
    for i, img_bytes in enumerate(images, 1):
        public_id = f"{base_name}_slide_{i}"
        url = _upload_to_cloudinary(img_bytes, public_id)
        if url:
            public_urls.append(url)
            log.info("Slide %d/%d → %s", i, len(images), url[:60])

    if len(public_urls) < 2:
        raise RuntimeError("Need at least 2 images for Instagram carousel (got %d)" % len(public_urls))

    # ── Create child containers ───────────────────────────────────────────
    child_ids: list[str] = []
    for url in public_urls:
        cid = _create_child_container(uid, url, token)
        if cid:
            child_ids.append(cid)
        time.sleep(1)   # brief pause between container creations

    if len(child_ids) < 2:
        raise RuntimeError("Failed to create enough child media containers")

    # ── Create and publish carousel ───────────────────────────────────────
    container_id = _create_carousel_container(uid, child_ids, caption, token)

    # Instagram requires a brief pause between container creation and publishing
    log.info("Waiting 5s before publishing Instagram carousel...")
    time.sleep(5)

    media_id = _publish_container(uid, container_id, token)
    return media_id
