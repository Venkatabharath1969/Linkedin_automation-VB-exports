"""
fetchers/topic_generator.py
────────────────────────────
Combines fetched export data and news headlines into a structured
topic object that drives today's carousel generation.

Flow:
  get_data_for_category(category)
    → fetch_apeda / UN Comtrade data
    → fetch latest news headline
    → return {topic, data, headline, category}
"""

from __future__ import annotations

import logging
from typing import Any

from config import SCHEDULE, COMTRADE_HS_CODES
from fetchers.export_data_fetcher import (
    get_apeda_coffee_data, get_apeda_spice_data, fetch_comtrade,
    FALLBACK_DATA,
)
from fetchers.news_fetcher import get_best_headline

log = logging.getLogger(__name__)


def get_data_for_category(category: str) -> dict[str, Any]:  # noqa: C901
    """
    Returns a combined data dict for AI prompt enrichment.
    Includes APEDA/Comtrade export stats + latest relevant news headline.

    Args:
        category : One of the schedule category strings (e.g. "coffee_market")

    Returns:
        {
          "export": {...},          # APEDA / Comtrade figures
          "news": {...} | None,     # Most recent relevant headline
          "general": {...},         # General India agri export context
        }
    """
    data: dict[str, Any] = {
        "export":  {},
        "news":    None,
        "general": FALLBACK_DATA["general"],
    }

    # ── Export data based on category ─────────────────────────────────────
    if category in ("coffee_market", "price_trends", "farm_origin", "export_guide"):
        apeda = get_apeda_coffee_data()
        comtrade = fetch_comtrade(COMTRADE_HS_CODES.get("coffee", "0901"))
        data["export"] = {**apeda, **comtrade} if comtrade else apeda

    elif category in ("spice_trade", "export_compliance"):
        apeda = get_apeda_spice_data()
        comtrade = fetch_comtrade(COMTRADE_HS_CODES.get("spices", "0904"))
        data["export"] = {**apeda, **comtrade} if comtrade else apeda

    elif category == "global_buyers":
        coffee  = get_apeda_coffee_data()
        spices  = get_apeda_spice_data()
        data["export"] = {
            "coffee":  coffee,
            "spices":  spices,
        }

    else:
        # Default: coffee data
        data["export"] = get_apeda_coffee_data()

    # ── Latest news headline ───────────────────────────────────────────────
    headline = get_best_headline(category)
    if headline:
        data["news"] = headline
        log.info("News hook: %s (age %.1fd)", headline["title"][:60], float(headline.get("age_days", 0)))

    return data


def build_topic_string(category: str, data: dict[str, Any]) -> str:
    """
    Builds the topic string sent to Gemini for carousel content generation.
    Derives from live data when available; falls back to schedule hint.
    """
    from config import SCHEDULE
    import datetime

    # Find today's schedule entry for the category
    day_name = datetime.datetime.now().strftime("%A")
    schedule_entry = SCHEDULE.get(day_name) or {}
    hint = schedule_entry.get("topic_hint", category.replace("_", " ").title()) if schedule_entry else category.replace("_", " ").title()

    # If we have live news, use it to make the topic more specific
    news = data.get("news")
    if news and news.get("title"):
        # Combine schedule hint + news for a grounded topic
        return f"{hint} — {news['title'][:80]}"

    return hint


