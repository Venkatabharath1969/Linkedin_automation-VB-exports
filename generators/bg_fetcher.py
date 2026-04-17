"""
generators/bg_fetcher.py
─────────────────────────
Background photo fetcher with layered sources:

1. Pexels API       — primary, if API key + network available
2. Curated Unsplash CDN URLs — always works, no API key needed
   (direct images.unsplash.com links, downloaded once and cached)
3. Gradient placeholder — renders via Pillow if all downloads fail

Photos are cached in assets/photo_cache/ — downloaded once, served forever.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import random
import urllib.error
import urllib.parse
import urllib.request
import json
from typing import Optional

log = logging.getLogger(__name__)

PHOTO_CACHE = pathlib.Path(__file__).parent.parent / "assets" / "photo_cache"
PHOTO_CACHE.mkdir(parents=True, exist_ok=True)

POOL_SIZE = 30

# ─────────────────────────────────────────────────────────────────────────────
# CURATED PHOTO POOLS — hand-picked Unsplash CDN URLs per category
# Format: direct images.unsplash.com URLs, no API key required
# Collected from Unsplash for commercial/B2B use (Unsplash license)
# ─────────────────────────────────────────────────────────────────────────────
CURATED_PHOTOS: dict[str, list[str]] = {
    "coffee_market": [
        "https://images.unsplash.com/photo-1447933601403-0c6688de566e?w=1080&q=85",  # dark roasted beans
        "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=1080&q=85",  # espresso pour
        "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=1080&q=85",  # black coffee overhead
        "https://images.unsplash.com/photo-1498804103079-a6351b050096?w=1080&q=85",  # coffee beans close
        "https://images.unsplash.com/photo-1465146344425-f00d5f5c8f07?w=1080&q=85",  # coffee bag burlap
        "https://images.unsplash.com/photo-1559525839-b184a4d698c7?w=1080&q=85",  # roastery dark
        "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=1080&q=85",  # café latte art
        "https://images.unsplash.com/photo-1442512595331-e89e73853f31?w=1080&q=85",  # coffee sack warehouse
        "https://images.unsplash.com/photo-1474546652694-a33dd8161d66?w=1080&q=85",  # cupping quality
        "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1080&q=85",  # coffee texture dark
        "https://images.unsplash.com/photo-1611689342806-0863700ce1e4?w=1080&q=85",  # coffee plantation rows
        "https://images.unsplash.com/photo-1562158074-e65c4f625561?w=1080&q=85",     # red coffee cherries
    ],
    "price_trends": [
        "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1080&q=85",  # trading screens
        "https://images.unsplash.com/photo-1518186285589-2f7649de83e0?w=1080&q=85",  # stock market graph
        "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1080&q=85",  # analytics laptop
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1080&q=85",  # data dashboard
        "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=1080&q=85",  # commodity charts
        "https://images.unsplash.com/photo-1535320903710-d993d3d77d29?w=1080&q=85",  # coffee price trading
        "https://images.unsplash.com/photo-1622547748225-3fc4abd2cca0?w=1080&q=85",  # market data dark
    ],
    "global_buyers": [
        "https://images.unsplash.com/photo-1494412651409-8963ce7935a7?w=1080&q=85",  # cargo port aerial
        "https://images.unsplash.com/photo-1510511459019-5dda7724fd87?w=1080&q=85",  # shipping containers
        "https://images.unsplash.com/photo-1578575437130-527eed3abbec?w=1080&q=85",  # container port night
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1080&q=85",  # global trade vessel
        "https://images.unsplash.com/photo-1516738901171-8eb4fc13bd20?w=1080&q=85",  # logistics warehouse
        "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1080&q=85",  # cargo plane
        "https://images.unsplash.com/photo-1504917595217-d4dc5ebe6122?w=1080&q=85",  # international airport
        "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=1080&q=85",  # supply chain
    ],
    "farm_origin": [
        "https://images.unsplash.com/photo-1611689342806-0863700ce1e4?w=1080&q=85",  # coffee plantation rows
        "https://images.unsplash.com/photo-1562158074-e65c4f625561?w=1080&q=85",  # coffee cherries red
        "https://images.unsplash.com/photo-1459755486867-b55449bb39ff?w=1080&q=85",  # coffee farm hills
        "https://images.unsplash.com/photo-1599058917765-a780eda07a3e?w=1080&q=85",  # coffee harvesting hand
        "https://images.unsplash.com/photo-1541167760496-1628856ab772?w=1080&q=85",  # coffee drying beds
        "https://images.unsplash.com/photo-1474546652694-a33dd8161d66?w=1080&q=85",  # cupping quality lab
        "https://images.unsplash.com/photo-1447933601403-0c6688de566e?w=1080&q=85",  # roasted beans farm
    ],
    "export_guide": [
        "https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=1080&q=85",  # customs inspection
        "https://images.unsplash.com/photo-1553413077-190dd305871c?w=1080&q=85",  # warehouse logistics
        "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1080&q=85",  # export cargo
        "https://images.unsplash.com/photo-1423666639041-f56000c27a9a?w=1080&q=85",  # document signing
        "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=1080&q=85",  # compliance paperwork
        "https://images.unsplash.com/photo-1600880292089-90a7e086ee0c?w=1080&q=85",  # business meeting
        "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=1080&q=85",  # handshake deal
    ],
    "personal": [
        "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=1080&q=85",  # black coffee cup
        "https://images.unsplash.com/photo-1484723091739-30a097e8f929?w=1080&q=85",  # morning coffee
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1080&q=85",  # coffee and notebook
        "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=1080&q=85",  # business team
        "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=1080&q=85",  # entrepreneur desk
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1080&q=85",  # India landscape
        "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=1080&q=85",  # professional portrait
    ],
}

# Map categoeries to curated pool keys
CATEGORY_POOL_MAP = {
    "coffee_market":    "coffee_market",
    "price_trends":     "price_trends",
    "global_buyers":    "global_buyers",
    "farm_origin":      "farm_origin",
    "export_guide":     "export_guide",
    "export_compliance":"export_guide",
    "personal_journey": "personal",
    "personal_lesson":  "personal",
    "personal_origin":  "farm_origin",
}


# ─────────────────────────────────────────────────────────────────────────────
# Pexels (optional — only used if key is set AND network allows)
# ─────────────────────────────────────────────────────────────────────────────

def _pexels_search(query: str, count: int, api_key: str) -> list[str]:
    urls: list[str] = []
    params = urllib.parse.urlencode({
        "query": query, "per_page": min(count, 15),
        "page": 1, "orientation": "portrait", "size": "large",
    })
    req = urllib.request.Request(
        f"https://api.pexels.com/v1/search?{params}",
        headers={"Authorization": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for p in data.get("photos", []):
            url = p.get("src", {}).get("large2x") or p.get("src", {}).get("large") or ""
            if url:
                urls.append(url)
    except Exception as e:
        log.debug("Pexels unavailable: %s", e)
    return urls[:count]


# ─────────────────────────────────────────────────────────────────────────────
# Download + cache
# ─────────────────────────────────────────────────────────────────────────────

def _download_photo(url: str, cache_key: str) -> Optional[str]:
    ext = ".png" if ".png" in url.lower() else ".jpg"
    cache_file = PHOTO_CACHE / f"{cache_key}{ext}"
    if cache_file.exists() and cache_file.stat().st_size > 5000:
        return cache_file.as_uri()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 VBExports-Automation/3.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 5000:
            return None  # not a real image
        cache_file.write_bytes(data)
        log.debug("Cached photo: %s (%d KB)", cache_file.name, len(data) // 1024)
        return cache_file.as_uri()
    except Exception as e:
        log.warning("Photo download failed %s: %s", url[:50], e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Gradient placeholder (Pillow) — looks intentional, not like a failure
# ─────────────────────────────────────────────────────────────────────────────

def _make_gradient_placeholder(bg_color: str = "#1A0A00", accent: str = "#C8961E") -> str:
    """Creates a gradient PNG that matches the slide theme. Looks like a design choice."""
    key = f"gradient_{bg_color.strip('#')}_{accent.strip('#')}"
    cache_file = PHOTO_CACHE / f"{key}.png"
    if cache_file.exists():
        return cache_file.as_uri()
    try:
        from PIL import Image
        import numpy as np

        def hex_to_rgb(h: str):
            h = h.strip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        bg  = hex_to_rgb(bg_color)
        acc = hex_to_rgb(accent)

        w, h = 1080, 480
        img = Image.new("RGB", (w, h))
        pixels = img.load()
        for y in range(h):
            t = y / h
            r = int(bg[0] * (1 - t) + acc[0] * t * 0.25)
            g = int(bg[1] * (1 - t) + acc[1] * t * 0.25)
            b = int(bg[2] * (1 - t) + acc[2] * t * 0.25)
            for x in range(w):
                pixels[x, y] = (r, g, b)

        img.save(str(cache_file), "PNG")
        log.info("Gradient placeholder created: %s", cache_file.name)
        return cache_file.as_uri()
    except Exception as e:
        log.warning("Pillow gradient failed: %s", e)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_photos(query: str, count: int = 9, category: str = "coffee_market") -> list[str]:
    """
    Returns a list of local file:// URIs for background photos.

    Priority:
      1. Pexels API (if key set + network allows)
      2. Curated Unsplash CDN pool (direct image URLs, always works)
      3. Gradient placeholder (Pillow-generated, matches theme)
    """
    remote_urls: list[str] = []

    # ── Try Pexels first ────────────────────────────────────────────────
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if pexels_key:
        remote_urls = _pexels_search(query, POOL_SIZE, pexels_key)

    # ── Fall back to curated Unsplash pool ──────────────────────────────
    if not remote_urls:
        pool_key = CATEGORY_POOL_MAP.get(category, "coffee_market")
        remote_urls = list(CURATED_PHOTOS.get(pool_key, CURATED_PHOTOS["coffee_market"]))
        log.info("Using curated Unsplash pool for category=%s (%d URLs)", category, len(remote_urls))

    # Shuffle for variety
    random.shuffle(remote_urls)
    selected = remote_urls[:count]

    # Download + cache
    local_uris: list[str] = []
    cached_list = list(PHOTO_CACHE.glob("*.jpg")) + list(PHOTO_CACHE.glob("*.png"))

    for i, url in enumerate(selected):
        cache_key = hashlib.md5(url.encode()).hexdigest()[:16]
        uri = _download_photo(url, cache_key)
        if uri:
            local_uris.append(uri)
        elif cached_list:
            local_uris.append(random.choice(cached_list).as_uri())

    # Pad to count if needed
    while len(local_uris) < count:
        if local_uris:
            local_uris.append(local_uris[len(local_uris) % len(local_uris)])
        else:
            fallback = _make_gradient_placeholder()
            if fallback:
                local_uris.append(fallback)
            else:
                break

    log.info("Photos ready: %d URIs for category=%s", len(local_uris), category)
    return local_uris
