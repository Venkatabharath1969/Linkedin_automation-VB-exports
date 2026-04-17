"""
generators/pexels_fetcher.py
─────────────────────────────
Searches Pexels for a topic-specific landscape photo and returns a local
file:// URI (cached by query hash so the same slide topic re-uses the same
image across runs).

Free tier:  200 requests/hour, 20,000/month  — instant API key at pexels.com/api
License:    Free for commercial use in PDFs (no attribution required in PDF body)
Quality:    Real editorial photography — vastly more relevant than AI generation

Set PEXELS_API_KEY in .env to activate.  If the key is absent or the request
fails, the function returns None and image_gen falls back to its Unsplash pool.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

PHOTO_CACHE = pathlib.Path(__file__).parent.parent / "assets" / "photo_cache"
PHOTO_CACHE.mkdir(parents=True, exist_ok=True)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Slide type → Pexels search orientation hint (always landscape for carousel)
_ORIENTATION = "landscape"

# ─────────────────────────────────────────────────────────────────────────────
# Slide-type → refined search terms that add B2B specificity to the prompt
# ─────────────────────────────────────────────────────────────────────────────
_TYPE_SUFFIX: dict[str, str] = {
    "HOOK":        "Karnataka coffee plantation aerial cinematic morning mist",
    "STAT":        "India coffee export bags warehouse sacks",
    "CONTEXT":     "Karnataka coffee plantation shade-grown farm India",
    "INSIGHT":     "coffee beans quality close-up harvest India",
    "IMPLICATION": "coffee export business meeting professionals India",
    "TIP":         "coffee certification quality inspection bags",
    "CTA":         "business handshake partnership professional coffee",
    "BRAND":       "business handshake partnership professional coffee",
    "OPPORTUNITY": "India coffee farm harvest export market growing",
    "GROWTH":      "India coffee exporter trade success farm",
    "PROBLEM":     "coffee supply chain logistics warehouse India",
    "PRICE":       "coffee commodity bags market trade India",
    "COMPLIANCE":  "certification document coffee export quality",
}

# Mandatory anchor appended to every Pexels query to avoid geopolitical/unrelated results
_COFFEE_ANCHOR = "coffee India"


# Words in Gemini prompts that lead Pexels to return finance/stock/data-viz photos
_VISUAL_BLOCKLIST = {
    "chart", "graph", "bar", "pie", "infographic", "visualization", "visualisation",
    "dashboard", "analytics", "statistics", "metrics", "kpi", "trend", "trending",
    "stock", "trading", "market", "financial", "finance", "retail", "sales",
    "percentage", "percent", "growth", "upward", "downward", "arrow", "number",
    "data", "digital", "map", "split", "collage", "composite", "illustration",
    "stylized", "globe", "globe", "icon", "flag", "flags", "world",
}


def _build_pexels_query(gemini_prompt: str, slide_type: str) -> str:
    """
    Converts the Gemini image_prompt into an effective Pexels search query.
    Blocks visualization/finance keywords that cause Pexels to return
    stock-market charts, data graphs, and maps instead of coffee photography.
    Always anchors with 'coffee India' to prevent geopolitical/unrelated results.
    """
    if gemini_prompt and len(gemini_prompt.strip()) > 10:
        # Extract first 8 words, strip AI boilerplate AND visual/chart keywords
        words = gemini_prompt.replace(",", " ").split()
        stop = {
            "no", "text", "watermark", "4k", "photography", "photo", "cinematic",
            "no-text", "high", "resolution", "sharp", "focus", "professional",
            "dramatic", "documentary", "natural", "light", "warm", "close-up",
        }
        keywords = [
            w for w in words
            if w.lower().rstrip(".,") not in stop
            and w.lower().rstrip(".,") not in _VISUAL_BLOCKLIST
        ][:5]
        base_query = " ".join(keywords)
    else:
        base_query = ""

    # If blocklist filtered everything out, fall back to the type-safe suffix alone
    suffix = _TYPE_SUFFIX.get(slide_type.upper(), "coffee farm India")
    if not base_query.strip():
        query = f"{_COFFEE_ANCHOR} {suffix}"
    else:
        query = f"{_COFFEE_ANCHOR} {base_query} {suffix}"
    return query[:90]  # Pexels recommends <=100 chars


def search_pexels(
    gemini_prompt: str,
    slide_type: str,
    slide_index: int = 0,
    api_key: str | None = None,
) -> str | None:
    """
    Search Pexels by topic and return a local file:// URI for the best photo.

    Returns None if:
    - API key is not set / invalid
    - No results found for the query
    - Network error

    Result is cached locally — identical query = no re-fetch.
    """
    key = api_key or os.environ.get("PEXELS_API_KEY", "")
    if not key or key == "your_key_here":
        log.debug("PEXELS_API_KEY not configured — skipping Pexels search")
        return None

    query = _build_pexels_query(gemini_prompt, slide_type)
    cache_key  = f"pexels_{hashlib.md5(query.encode()).hexdigest()[:20]}"
    cache_file = PHOTO_CACHE / f"{cache_key}.jpg"

    # Return cached image if already downloaded and valid
    if cache_file.exists() and cache_file.stat().st_size > 5_000:
        data = cache_file.read_bytes()
        if data[:3] == b'\xff\xd8\xff':  # valid JPEG
            log.debug("Pexels cache hit: %s ← %s", cache_file.name, query[:50])
            return cache_file.as_uri()
        cache_file.unlink(missing_ok=True)

    # Search Pexels — request 5 results, pick by slide_index for variety across slides
    params = urllib.parse.urlencode({
        "query":       query,
        "orientation": _ORIENTATION,
        "per_page":    5,
        "page":        1,
    })
    url = f"{PEXELS_SEARCH_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers={
            "Authorization": key,
            "User-Agent":    "VBExports-Automation/3.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Pexels search failed for '%s': %s", query[:50], e)
        return None

    photos = body.get("photos", [])
    if not photos:
        log.debug("Pexels: no results for '%s'", query[:50])
        return None

    # Pick a photo — rotate by slide_index for visual variety across slides
    photo  = photos[slide_index % len(photos)]
    img_url = photo.get("src", {}).get("landscape") or photo.get("src", {}).get("large")
    if not img_url:
        log.debug("Pexels: no landscape/large URL in response")
        return None

    # Download and cache the photo
    try:
        img_req = urllib.request.Request(img_url, headers={"User-Agent": "VBExports-Automation/3.0"})
        with urllib.request.urlopen(img_req, timeout=20) as resp:
            img_data = resp.read()
        if len(img_data) < 5_000 or img_data[:3] != b'\xff\xd8\xff':
            log.warning("Pexels: downloaded file is not a valid JPEG (%d bytes)", len(img_data))
            return None
        cache_file.write_bytes(img_data)
        log.info("Pexels image saved: %s (%d KB) | query: %s",
                 cache_file.name, len(img_data) // 1024, query[:60])
        return cache_file.as_uri()
    except Exception as e:
        log.warning("Pexels download failed: %s", e)
        return None
