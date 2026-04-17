"""
fetchers/news_fetcher.py
─────────────────────────
Fetches the latest Indian export & commodity news from:
  ✦ RSS feeds — Economic Times, Business Standard, Hindu BusinessLine (free, unlimited)
  ✦ GNews API  — keyword news (100 requests/day free, no credit card)

Returns the freshest relevant headline to use as the carousel's
"news hook" and contextual anchor for AI content generation.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests

from config import RSS_FEEDS, RSS_MAX_AGE_DAYS, GNEWS_API_KEY, GNEWS_QUERY, GNEWS_COUNTRY, GNEWS_MAX

log = logging.getLogger(__name__)


def _age_days(entry: Any) -> float:
    """Returns the age of an RSS entry in days. Returns 999 if unparseable."""
    published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if published is None:
        return 999.0
    try:
        pub_dt  = datetime(*published[:6], tzinfo=timezone.utc)
        age     = datetime.now(timezone.utc) - pub_dt
        return age.total_seconds() / 86400.0
    except Exception:
        return 999.0


def fetch_rss_headlines(max_age_days: int = RSS_MAX_AGE_DAYS) -> list[dict[str, str]]:
    """
    Parses all configured RSS feeds and returns fresh articles about
    Indian exports, coffee, or spices.

    Returns a list of {"title": str, "summary": str, "link": str, "source": str}
    sorted by recency (newest first).
    """
    relevant_keywords = {
        "coffee", "spice", "export", "india export", "apeda",
        "commodity", "agri", "coffee board", "spice board",
        "pepper", "cardamom", "turmeric", "chilli",
    }

    results: list[dict[str, str]] = []

    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:20]:
                age = _age_days(entry)
                if age > max_age_days:
                    continue

                title   = getattr(entry, "title",   "").strip()
                summary = getattr(entry, "summary", "").strip()
                link    = getattr(entry, "link",    "").strip()

                combined = (title + " " + summary).lower()
                if not any(kw in combined for kw in relevant_keywords):
                    continue

                results.append({
                    "title":   title,
                    "summary": summary[:300],
                    "link":    link,
                    "source":  parsed.feed.get("title", feed_url),
                    "age_days": f"{age:.1f}",
                })

        except Exception as e:
            log.warning("RSS feed failed (%s): %s", feed_url, e)

    # Sort by recency
    results.sort(key=lambda x: float(x.get("age_days", 999)))
    log.info("RSS: found %d relevant articles (max age %dd)", len(results), max_age_days)
    return results


def fetch_gnews_headlines() -> list[dict[str, str]]:
    """
    Fetches headlines from GNews API.
    Free tier: 100 requests/day, no credit card required.
    Returns [] if API key is not configured.
    """
    api_key = GNEWS_API_KEY
    if not api_key:
        log.info("GNEWS_API_KEY not set — skipping GNews fetch")
        return []

    url = "https://gnews.io/api/v4/search"
    params = {
        "q":        GNEWS_QUERY,
        "country":  GNEWS_COUNTRY,
        "lang":     "en",
        "max":      GNEWS_MAX,
        "apikey":   api_key,
        "sortby":   "publishedAt",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        log.info("GNews: fetched %d articles", len(articles))
        return [
            {
                "title":   a["title"],
                "summary": a.get("description", "")[:300],
                "link":    a["url"],
                "source":  a.get("source", {}).get("name", "GNews"),
                "age_days": "0",
            }
            for a in articles
        ]
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status == 429:
            log.warning("GNews daily limit reached (100/day free cap)")
        else:
            log.warning("GNews HTTP %d: %s", status, e)
    except Exception as e:
        log.warning("GNews fetch failed: %s", e)

    return []


def get_best_headline(category: str) -> dict[str, str] | None:
    """
    Returns the single best, most relevant recent headline for the
    given posting category. Used as news anchor in AI prompts.

    Returns None if no relevant news is found.
    """
    category_keywords: dict[str, list[str]] = {
        "coffee_market": ["coffee"],
        "spice_trade":   ["spice", "pepper", "cardamom", "turmeric", "chilli"],
        "export_compliance": ["apeda", "export", "certification", "fssai"],
        "global_buyers": ["export", "import", "trade", "buyer"],
        "price_trends":  ["price", "mcx", "commodity", "coffee price"],
        "farm_origin":   ["coffee", "origin", "farm", "karnataka", "coorg"],
        "export_guide":  ["export", "logistics", "customs", "documentation"],
    }

    target_kws = category_keywords.get(category, ["export", "india"])

    # Gather from both sources
    all_articles = fetch_rss_headlines() + fetch_gnews_headlines()

    # Score each article by keyword relevance
    scored: list[tuple[int, dict]] = []
    for art in all_articles:
        combined = (art["title"] + " " + art["summary"]).lower()
        score = sum(1 for kw in target_kws if kw in combined)
        if score > 0:
            scored.append((score, art))

    if not scored:
        log.info("No relevant news found for category '%s'", category)
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    log.info("Best headline for '%s': %s", category, best["title"][:80])
    return best
