"""
generators/image_gen.py
────────────────────────
Per-slide topic-specific image selection for carousel slides.

Three-tier strategy (best first):
  1. Pexels search (PEXELS_API_KEY in .env) — real editorial photography,
     searched by Gemini’s image_prompt concept. 200 req/hour free. Best quality.
  2. Pollinations.ai (FLUX.1 — free, no key) — AI-generated topic images.
     Falls back automatically if rate-limited or offline.
  3. Type-aware Unsplash pool — curated photos mapped to slide type.
     Always works. Zero external dependencies.

Images are cached locally — same prompt = same image every run.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import time
import urllib.parse
import urllib.request

from generators.pexels_fetcher import search_pexels

log = logging.getLogger(__name__)

PHOTO_CACHE = pathlib.Path(__file__).parent.parent / "assets" / "photo_cache"
PHOTO_CACHE.mkdir(parents=True, exist_ok=True)

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

# ─────────────────────────────────────────────────────────────────────────────
# Slide-type → photographic style (for Pollinations prompt)
# ─────────────────────────────────────────────────────────────────────────────
_TYPE_STYLE: dict[str, str] = {
    "HOOK":        "dramatic cinematic aerial photography, stunning wide shot, golden hour lighting",
    "CONTEXT":     "documentary photography, storytelling scene, warm natural light",
    "STAT":        "industrial scale, measurement, precision, data-driven scene, professional photography",
    "INSIGHT":     "expert analysis, quality inspection, close-up detail, sharp macro photography",
    "IMPLICATION": "logistics and trade, supply chain action, international shipping, port photography",
    "TIP":         "close-up artisan craft, hand detail, premium quality, studio light",
    "CTA":         "premium branding, product showcase, clean professional photography",
    "BRAND":       "premium Indian export brand, professional product packaging, clean white studio",
}

# Category → base subject matter
_CATEGORY_SUBJECT: dict[str, str] = {
    "coffee_market":   "Indian coffee export industry, premium Arabica and Robusta coffee",
    "price_trends":    "commodity trading, market data, coffee futures, price charts",
    "global_buyers":   "international trade, shipping containers, cargo port, global logistics",
    "farm_origin":     "Karnataka coffee plantation, shade-grown coffee farm, lush green hills, India",
    "export_guide":    "export compliance, trade documents, logistics warehouse, customs clearance",
    "personal":        "Indian entrepreneur, coffee professional, business journey, authentic story",
}

# ─────────────────────────────────────────────────────────────────────────────
# Type-aware Unsplash fallback URLs (ordered: most dramatic/relevant first)
# These are picked to visually match the slide's purpose, not just the topic.
# ─────────────────────────────────────────────────────────────────────────────
_TYPE_UNSPLASH: dict[str, list[str]] = {
    "HOOK": [
        "https://images.unsplash.com/photo-1447933601403-0c6688de566e?w=1080&q=85",  # dark dramatic roasted beans
        "https://images.unsplash.com/photo-1611689342806-0863700ce1e4?w=1080&q=85",  # coffee plantation rows aerial
        "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=1080&q=85",  # cinematic espresso pour
    ],
    "STAT": [
        "https://images.unsplash.com/photo-1442512595331-e89e73853f31?w=1080&q=85",  # coffee sack warehouse scale
        "https://images.unsplash.com/photo-1474546652694-a33dd8161d66?w=1080&q=85",  # cupping bowls precision
        "https://images.unsplash.com/photo-1498804103079-a6351b050096?w=1080&q=85",  # coffee beans close-up scale
    ],
    "INSIGHT": [
        "https://images.unsplash.com/photo-1474546652694-a33dd8161d66?w=1080&q=85",  # cupping quality lab
        "https://images.unsplash.com/photo-1498804103079-a6351b050096?w=1080&q=85",  # coffee beans close macro
        "https://images.unsplash.com/photo-1562158074-e65c4f625561?w=1080&q=85",     # red coffee cherries detail
    ],
    "IMPLICATION": [
        "https://images.unsplash.com/photo-1494412651409-8963ce7935a7?w=1080&q=85",  # cargo port aerial
        "https://images.unsplash.com/photo-1510511459019-5dda7724fd87?w=1080&q=85",  # shipping containers
        "https://images.unsplash.com/photo-1578575437130-527eed3abbec?w=1080&q=85",  # port at night
    ],
    "CONTEXT": [
        # VERIFIED coffee/agriculture plantation images — no pineapple/fruit
        "https://images.unsplash.com/photo-1611689342806-0863700ce1e4?w=1080&q=85",  # coffee plantation rows
        "https://images.unsplash.com/photo-1459755486867-b55449bb39ff?w=1080&q=85",  # coffee farm green hills
        "https://images.unsplash.com/photo-1562158074-e65c4f625561?w=1080&q=85",     # red coffee cherries on plant
    ],
    "TIP": [
        "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=1080&q=85",  # black coffee overhead
        "https://images.unsplash.com/photo-1465146344425-f00d5f5c8f07?w=1080&q=85",  # coffee bag burlap artisan
        "https://images.unsplash.com/photo-1559525839-b184a4d698c7?w=1080&q=85",     # roastery craft dark
    ],
    "CTA": [
        # Business partnership imagery — matches "Partner with VB Exports" type slides
        "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=1080&q=85",  # handshake trade deal
        "https://images.unsplash.com/photo-1600880292089-90a7e086ee0c?w=1080&q=85",  # professional B2B meeting
        "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=1080&q=85",  # business team discussion
    ],
    "BRAND": [
        # Business/brand imagery — professional partnership context
        "https://images.unsplash.com/photo-1521791136064-7986c2920216?w=1080&q=85",  # handshake deal
        "https://images.unsplash.com/photo-1600880292089-90a7e086ee0c?w=1080&q=85",  # B2B meeting room
    ],
}
# All type aliases — every Gemini slide type has a guaranteed mapping
_TYPE_UNSPLASH["GENERAL"]     = _TYPE_UNSPLASH["CONTEXT"]
_TYPE_UNSPLASH["PRICE"]       = _TYPE_UNSPLASH["STAT"]
_TYPE_UNSPLASH["COMPLIANCE"]  = _TYPE_UNSPLASH["TIP"]
_TYPE_UNSPLASH["OPPORTUNITY"] = _TYPE_UNSPLASH["INSIGHT"]
_TYPE_UNSPLASH["GROWTH"]      = _TYPE_UNSPLASH["INSIGHT"]
_TYPE_UNSPLASH["PROBLEM"]     = _TYPE_UNSPLASH["STAT"]


# ─────────────────────────────────────────────────────────────────────────────
# Download + cache helper
# ─────────────────────────────────────────────────────────────────────────────

# IDs of known-bad Unsplash photos (verified wrong content: burger, pineapple)
_BANNED_PHOTO_IDS = {
    "1495474472287-4d71bcdd2085",  # shows burger — NOT coffee
    "1504630083234-14187a9df0f5",  # shows pineapple — NOT coffee
}


def _is_valid_image(data: bytes) -> bool:
    """Confirm bytes are an actual JPEG or PNG, not an HTML error page."""
    return data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n'


def _download_and_cache(url: str, cache_key: str) -> str | None:
    # Reject banned photo IDs before downloading
    for bad_id in _BANNED_PHOTO_IDS:
        if bad_id in url:
            log.warning("Skipping banned photo ID: %s", bad_id)
            return None

    ext = ".jpg"
    cache_file = PHOTO_CACHE / f"{cache_key}{ext}"

    # Validate existing cached file — delete and re-download if not a real image
    if cache_file.exists() and cache_file.stat().st_size > 5000:
        cached = cache_file.read_bytes()
        if _is_valid_image(cached):
            return cache_file.as_uri()
        log.warning("Cached file %s is not a valid image — purging", cache_file.name)
        cache_file.unlink(missing_ok=True)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 VBExports/3.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 5000 or not _is_valid_image(data):
            log.warning("Not a valid image (%d bytes): %s", len(data), url[:50])
            return None
        cache_file.write_bytes(data)
        return cache_file.as_uri()
    except Exception as e:
        log.debug("Download failed %s: %s", url[:50], e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pollinations AI fetch
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(slide_title: str, slide_type: str, category: str) -> str:
    subject = _CATEGORY_SUBJECT.get(category, "Indian coffee export business")
    style   = _TYPE_STYLE.get(slide_type.upper(), "professional commercial photography")
    title_anchor = " ".join(slide_title.split()[:8])
    return (
        f"professional photorealistic photograph: {title_anchor}, "
        f"{subject}, {style}, "
        f"high resolution, sharp focus, no text, no watermark, 4K quality. "
        f"Subject MUST BE coffee beans, coffee plantation, or coffee trade logistics only. "
        f"Absolutely no food items, no tropical fruits, no pineapples, no burgers, no unrelated crops."
    )


def _fetch_from_pollinations(prompt: str) -> bytes | None:
    """
    Fetch an AI-generated image from Pollinations.ai (FLUX.1, free tier).
    Sleeps 2s before each call to respect the free-tier rate limit (~1 req/2s).
    Cache hits should be checked BEFORE calling this function.
    """
    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{POLLINATIONS_BASE}/{encoded}?width=1080&height=420&nologo=true&enhance=true&seed=-1"
    log.debug("Pollinations request: %s...", url[:80])
    time.sleep(2)  # respect free-tier rate limit — prevents 429 after slide 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 VBExports/3.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            ct   = resp.headers.get("content-type", "")
            data = resp.read()
        # Must be an actual image (JPEG/PNG), not HTML error page
        if "text" in ct or len(data) < 10_000:
            log.warning("Pollinations: non-image response (%s, %d bytes)", ct, len(data))
            return None
        if not _is_valid_image(data):
            log.warning("Pollinations: response not a valid JPEG/PNG (%d bytes)", len(data))
            return None
        return data
    except Exception as e:
        log.warning("Pollinations fetch failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Type-aware Unsplash fallback
# ─────────────────────────────────────────────────────────────────────────────

def _type_aware_unsplash(slide_type: str, seed: int = 0) -> str | None:
    """Pick a type-matched Unsplash photo and return a local file:// URI."""
    pool = _TYPE_UNSPLASH.get(slide_type.upper(), _TYPE_UNSPLASH["CONTEXT"])
    url  = pool[seed % len(pool)]
    key  = hashlib.md5(url.encode()).hexdigest()[:16]
    return _download_and_cache(url, key)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_slide_image(
    slide_title: str,
    slide_type: str,
    category: str,
    fallback_uri: str = "",
    slide_index: int = 0,
    gemini_prompt: str = "",
) -> str:
    """
    Returns a local file:// URI for a slide-specific background image.

    Priority:
      1. Pexels real photo search using Gemini's image_prompt (requires PEXELS_API_KEY)
         Real editorial photography — always relevant, zero rate-limit issues at 200/hr.
      2. Pollinations AI using Gemini-written image_prompt (semantically correct for slide)
         Falls back to keyword-built prompt if gemini_prompt is empty.
      3. Type-aware Unsplash photo (HOOK=dramatic, STAT=industrial, CTA=partnership...)
      4. fallback_uri passed in by caller (random Unsplash from pool)

    Cache: prompt hash → local JPEG. Same slide topic = same image, zero re-download.
    Rate limit: 2s sleep per Pollinations call (enforced in _fetch_from_pollinations).
    """
    # ── Priority 1: Pexels real photo search (best quality, most relevant) ─────────
    pexels_uri = search_pexels(gemini_prompt, slide_type, slide_index)
    if pexels_uri:
        log.info("Pexels image used   | type=%-12s | slide=%d", slide_type, slide_index + 1)
        return pexels_uri

    # ── Priority 2: Pollinations AI ────────────────────────────────────────────────
    # Prefer Gemini's semantically-aware prompt; fall back to keyword builder
    if gemini_prompt and len(gemini_prompt.strip()) > 15:
        prompt = gemini_prompt.strip()
        log.debug("Using Gemini image_prompt for slide %d", slide_index + 1)
    else:
        prompt = _build_prompt(slide_title, slide_type, category)
        log.debug("Using built prompt for slide %d (no gemini_prompt)", slide_index + 1)

    cache_key  = f"pollinations_{hashlib.md5(prompt.encode()).hexdigest()[:20]}"
    cache_file = PHOTO_CACHE / f"{cache_key}.jpg"

    # Return cached AI image if already generated (no sleep, no network call)
    if cache_file.exists() and cache_file.stat().st_size > 10_000:
        cached = cache_file.read_bytes()
        if _is_valid_image(cached):
            log.debug("AI image cache hit: %s", cache_file.name)
            return cache_file.as_uri()
        cache_file.unlink(missing_ok=True)  # purge corrupt cache

    log.info("Generating AI image | type=%-12s | %s", slide_type, slide_title[:45])

    # Try Pollinations (2s sleep enforced inside _fetch_from_pollinations)
    img_bytes = _fetch_from_pollinations(prompt)
    if img_bytes:
        cache_file.write_bytes(img_bytes)
        log.info("Pollinations image saved: %s (%d KB)", cache_file.name, len(img_bytes) // 1024)
        return cache_file.as_uri()

    # ── Priority 3: Type-aware Unsplash ────────────────────────────────────────────
    ta_uri = _type_aware_unsplash(slide_type, seed=slide_index)
    if ta_uri:
        log.info("Type-aware Unsplash used | type=%s | slide=%d", slide_type, slide_index + 1)
        return ta_uri

    # ── Priority 4: Caller's pre-fetched pool URI ───────────────────────────────────
    if fallback_uri:
        return fallback_uri

    return ""

