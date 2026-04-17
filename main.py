"""
main.py — VB Exports Daily Carousel Automation Agent
══════════════════════════════════════════════════════
Entry point for GitHub Actions daily cron and local testing.

Daily flow:
  1. Auto-select account (personal Mon/Wed/Fri, company Tue/Thu)
  2. Validate LinkedIn token + warn if expiring soon
  3. Resolve daily design theme (384 unique visual combos, date-driven)
  4. Fetch coffee export data + latest news headline
  5. Get today's topic from Google Sheets queue (or auto-generate)
  6. Generate carousel slides via Gemini AI (account-specific persona)
  7. Render 1080x1350 portrait carousel PDF (Pillow v2 engine)
  8. Generate LinkedIn post caption + first comment
  9. Post PDF carousel to LinkedIn (for the selected account)
  10. Post PNG images to Instagram + Facebook (for the same account)
  11. Mark topic as Posted in Google Sheets

Run modes:
  python main.py                        — auto-detect account for today
  python main.py --account personal     — force personal account (Bharath S)
  python main.py --account company      — force company account (VB Expo)
  python main.py --dry-run              — generate locally, do NOT post
  python main.py --account personal --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import pytz

# ── Local imports ─────────────────────────────────────────────────────────────
from config import (
    SCHEDULE, TIMEZONE, GOOGLE_SHEET_ID,
    POST_TO_LINKEDIN, POST_TO_FACEBOOK, POST_TO_INSTAGRAM,
    FIRST_COMMENT_DELAY_SECONDS, OUTPUT_DIR,
    BUSINESS_NAME, ACCOUNT_PROFILES, get_account_for_today,
    pick_hashtags,
)
from auth.token_manager import get_access_token, validate_token, DRY_RUN_TOKEN
from state.sheets_manager import get_todays_topic, mark_in_progress, mark_as_posted
from fetchers.topic_generator import get_data_for_category, build_topic_string
from generators.content_gen import generate_carousel_slides, generate_caption, generate_first_comment
from generators.slide_renderer import render_carousel
from generators.bg_fetcher import fetch_photos
from config_carousel import get_carousel_theme
from config import pick_hashtags


# ══════════════════════════════════════════════════════════════════════════════
# Logging setup
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _today_ist() -> datetime:
    return datetime.now(pytz.timezone(TIMEZONE))


def _get_todays_schedule() -> tuple[str, dict | None]:
    """Returns (day_name, schedule_entry_or_None) for today in IST."""
    day   = _today_ist().strftime("%A")
    entry = SCHEDULE.get(day)
    return day, entry


def _separator(msg: str = "") -> None:
    log.info("-" * 60 + ("  " + msg if msg else ""))


def _check_token_expiry(access_token: str) -> None:
    """Warn if LinkedIn token is expiring within 30 days."""
    try:
        import base64
        import json as _json
        parts = access_token.split(".")
        if len(parts) >= 2:
            padded  = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(padded))
            exp     = payload.get("exp", 0)
            if exp:
                remaining = (exp - time.time()) / 86400
                if remaining < 30:
                    log.warning(
                        "⚠️  LinkedIn token expires in %.0f days! "
                        "Renew at: linkedin.com/developers/tools/oauth/token-generator",
                        remaining,
                    )
                else:
                    log.info("LinkedIn token valid for ~%.0f more days", remaining)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Platform post functions
# ══════════════════════════════════════════════════════════════════════════════

def _post_linkedin(caption: str, pdf_path: str, first_comment: str,
                   access_token: str, author_urn: str, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY RUN] LinkedIn: would post PDF carousel (%s)", pdf_path)
        log.info("[DRY RUN] Caption preview:\n%s", caption[:400])
        return True
    try:
        from publishers.linkedin_publisher import post_document, post_first_comment
        post_urn = post_document(caption, pdf_path, access_token, author_urn=author_urn)
        log.info("LinkedIn carousel posted: %s", post_urn)
        if first_comment:
            time.sleep(FIRST_COMMENT_DELAY_SECONDS)
            post_first_comment(first_comment, access_token,
                               post_urn=post_urn, author_urn=author_urn)
        return True
    except Exception as e:
        log.error("LinkedIn post FAILED: %s", e)
        return False


def _post_facebook(caption: str, pdf_path: str,
                   page_id: str, page_token: str, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY RUN] Facebook: would post carousel from %s", pdf_path)
        return True
    if not page_id or not page_token:
        log.info("Facebook: skipped (credentials not configured for this account)")
        return False
    try:
        from publishers.facebook_publisher import post_carousel
        post_id = post_carousel(caption, pdf_path, page_id=page_id, page_token=page_token)
        log.info("Facebook post created: %s", post_id)
        return True
    except Exception as e:
        log.error("Facebook post FAILED: %s", e)
        return False


def _post_instagram(caption: str, pdf_path: str,
                    ig_user_id: str, access_token: str, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY RUN] Instagram: would post carousel from %s", pdf_path)
        return True
    if not ig_user_id or not access_token:
        log.info("Instagram: skipped (credentials not configured for this account)")
        return False
    try:
        from publishers.instagram_publisher import post_carousel
        media_id = post_carousel(caption, pdf_path,
                                 ig_user_id=ig_user_id, access_token=access_token)
        log.info("Instagram post created: %s", media_id)
        return True
    except Exception as e:
        log.error("Instagram post FAILED: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Main orchestrator
# ══════════════════════════════════════════════════════════════════════════════

def main(dry_run: bool = False, account_key: str | None = None, category_override: str | None = None) -> int:
    """
    Runs the full daily posting pipeline.

    Args:
        dry_run           : If True, generate content but do NOT post.
        account_key       : "personal" | "company" | None (auto-detect by weekday)
        category_override : Force a specific category regardless of weekday schedule

    Returns 0 on success, 1 on fatal failure.
    """
    today = _today_ist()
    log.info("=" * 60)
    log.info("  VB Exports — Daily Carousel Agent  %s", today.strftime("%Y-%m-%d"))
    log.info("  DRY RUN: %s", dry_run)
    log.info("=" * 60)

    # ── 1. Schedule + account auto-selection ──────────────────────────────
    day_name, schedule_entry = _get_todays_schedule()

    if schedule_entry is None and account_key is None:
        log.info("Today is %s — no posting scheduled (weekend). Exiting.", day_name)
        return 0

    if account_key and account_key in ACCOUNT_PROFILES:
        account = ACCOUNT_PROFILES[account_key]
    elif schedule_entry:
        account_key = schedule_entry.get("account", "personal")
        account     = ACCOUNT_PROFILES.get(account_key, get_account_for_today())
    else:
        account = get_account_for_today()

    category = category_override or (schedule_entry or {}).get("category", "coffee_market")
    label    = (schedule_entry or {}).get("label", "☕ Coffee Carousel")
    _separator(f"STEP 1 — {day_name} → {label} | Account: {account['label']}")
    log.info("Category: %s | Persona: %s", category, account["ai_persona"])

    # ── 2. LinkedIn token + expiry check ──────────────────────────────────
    _separator("STEP 2 — LinkedIn token")
    person_urn_env = os.environ.get("LINKEDIN_PERSON_URN", "")
    org_urn_env    = os.environ.get("LINKEDIN_ORG_URN", "")
    log.info("PERSON_URN type: %s len=%d", person_urn_env.split(":")[2] if person_urn_env.count(":") >= 2 else "EMPTY", len(person_urn_env))
    log.info("ORG_URN    type: %s len=%d", org_urn_env.split(":")[2] if org_urn_env.count(":") >= 2 else "EMPTY", len(org_urn_env))
    if dry_run:
        access_token = DRY_RUN_TOKEN
        log.info("DRY RUN — using fake token")
    else:
        try:
            access_token = get_access_token()
            if not validate_token(access_token):
                log.error("LinkedIn token invalid — run python setup_auth.py to renew.")
                return 1
            _check_token_expiry(access_token)
        except ValueError as e:
            log.error(str(e))
            return 1

    # ── 3. Category theme (fixed per topic — never random) ────────────────
    _separator("STEP 3 — Category theme")
    theme = get_carousel_theme(category)
    log.info("Theme: bg=%s accent=%s template=%s", theme["bg"], theme["accent"], theme["template"])

    # ── 4. Fetch coffee data + news ────────────────────────────────────────
    _separator("STEP 4 — Fetching coffee data & news")
    data_category = {
        "personal_journey": "coffee_market",
        "personal_lesson":  "coffee_market",
        "personal_origin":  "farm_origin",
    }.get(category, category)
    data = get_data_for_category(data_category)
    log.info("Data keys fetched: %s", list(data.keys()))

    # ── 5. Topic queue ─────────────────────────────────────────────────────
    _separator("STEP 5 — Topic queue")
    if GOOGLE_SHEET_ID == "YOUR_SHEET_ID_HERE":
        log.warning("Google Sheet not configured — using auto-generated topic")
        topic_str = build_topic_string(category, data)
        row_num   = None
    else:
        try:
            topic_obj = get_todays_topic(category)
            topic_str = topic_obj["topic"]
            row_num   = topic_obj["row_num"]
        except RuntimeError as e:
            log.warning("Sheets error (%s) — falling back to auto topic", e)
            topic_str = build_topic_string(category, data)
            row_num   = None
    log.info("Topic: %s", topic_str)
    if row_num and not dry_run:
        mark_in_progress(row_num)

    # ── 6. Generate carousel slides (Gemini AI, persona-aware) ────────────
    _separator("STEP 6 — Generating carousel slides (Gemini AI)")
    headline = data.get("news")
    slides   = generate_carousel_slides(
        topic      = topic_str,
        category   = category,
        data       = data.get("export", {}),
        headline   = headline,
        ai_persona = account["ai_persona"],
    )
    log.info("Slides: %d | Persona: %s", len(slides), account["ai_persona"])

    # ── 7. Fetch background photos + Render carousel (Playwright + Jinja2) ──
    _separator("STEP 7 — Fetching photos + rendering carousel (Playwright engine)")
    pexels_query = theme.get("pexels_query", "coffee beans dark roast")
    photo_urls   = fetch_photos(query=pexels_query, count=len(slides), category=category)
    log.info("Photos fetched: %d for query: %r", len(photo_urls), pexels_query)
    try:
        pdf_path = render_carousel(
            slides     = slides,
            category   = category,
            topic      = topic_str,
            account    = account,
            photo_urls = photo_urls,
        )
        log.info("PDF ready: %s", pdf_path)
    except Exception as e:
        log.error("PDF generation failed: %s", e)
        if row_num and not dry_run:
            from state.sheets_manager import _get_sheet
            _get_sheet().update_cell(row_num, 3, "Pending")
        return 1

    # ── 8. Generate caption + first comment ───────────────────────────────
    _separator("STEP 8 — Generating post caption")
    hashtags      = pick_hashtags(category)
    caption       = generate_caption(topic_str, category, slides, hashtags)
    first_comment = generate_first_comment(caption, category)
    log.info("Caption length: %d chars", len(caption))
    log.info("First comment: %s", first_comment[:100])

    caption_path = str(OUTPUT_DIR / f"caption_{account['key']}_{category}.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(f"=== ACCOUNT: {account['label']} ===\n")
        f.write(f"=== TOPIC: {topic_str} ===\n")
        f.write(f"=== THEME: {theme} ===\n\n")
        f.write(caption)
        f.write(f"\n\n=== FIRST COMMENT ===\n{first_comment}")
    log.info("Caption saved: %s", caption_path)

    # ── 9–11. Publish to all platforms for this account ───────────────────
    _separator("STEP 9–11 — Publishing to platforms")
    results    = {}
    author_urn = account.get("author_urn", "")

    if POST_TO_LINKEDIN:
        results["linkedin"] = _post_linkedin(
            caption, pdf_path, first_comment, access_token, author_urn, dry_run)

    if POST_TO_FACEBOOK:
        results["facebook"] = _post_facebook(
            caption, pdf_path,
            account.get("facebook_page_id", ""),
            account.get("facebook_token", ""),
            dry_run,
        )

    if POST_TO_INSTAGRAM:
        results["instagram"] = _post_instagram(
            caption, pdf_path,
            account.get("instagram_user_id", ""),
            account.get("facebook_token", ""),
            dry_run,
        )

    # ── 12. Mark as posted ─────────────────────────────────────────────────
    _separator("STEP 12 — Finalising")
    if row_num and not dry_run:
        if any(results.values()):
            mark_as_posted(row_num)
            log.info("Topic marked as Posted in Google Sheets ✓")
        else:
            log.error("All platform posts failed — topic NOT marked as Posted")

    # ── Summary ────────────────────────────────────────────────────────────
    _separator("SUMMARY")
    log.info("  Account:  %s", account["label"])
    log.info("  Theme:    %s", theme)
    for platform, ok in results.items():
        log.info("  %-12s %s", platform.upper(), "✓ posted" if ok else "✗ FAILED")
    log.info("PDF: %s", pdf_path)
    log.info("Day: %s | Topic: %s", day_name, topic_str[:60])

    overall_ok = any(results.values()) if results else dry_run
    return 0 if overall_ok else 1


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VB Exports Daily Carousel Agent")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate carousel and caption but do NOT post",
    )
    parser.add_argument(
        "--account", choices=["personal", "company"], default=None,
        help="Force a specific account (default: auto-detect by weekday)",
    )
    parser.add_argument(
        "--category",
        choices=["coffee_market", "price_trends", "global_buyers", "farm_origin",
                 "export_guide", "personal_journey"],
        default=None,
        help="Force a specific content category regardless of weekday schedule",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
        log.info("Loaded .env file")
    except ImportError:
        pass

    sys.exit(main(dry_run=args.dry_run, account_key=args.account, category_override=args.category))


