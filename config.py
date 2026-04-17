"""
config.py — VB Exports Automation Configuration
──────────────────────────────────────────────────
Single source of truth for ALL configurable values.
Central place to update branding, schedule, topics, and behaviour.
Environment variables (GitHub Secrets) override where applicable.
"""

from __future__ import annotations

import os
import pathlib
import random

# ── Paths (defined first — used by ACCOUNT_PROFILES below) ───────────────────
BASE_DIR     = pathlib.Path(__file__).parent
ASSETS_DIR   = BASE_DIR / "assets"
FONTS_DIR    = ASSETS_DIR / "fonts"
OUTPUT_DIR   = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
FONTS_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🏢 BUSINESS BRANDING — VB Exports
# ══════════════════════════════════════════════════════════════════════════════
BUSINESS_NAME        = "VB Exports"
BUSINESS_TAGLINE     = "Premium Indian Coffee Exports"
BUSINESS_LOCATION    = "Karnataka, India"
BUSINESS_PRODUCTS    = ["Robusta Coffee", "Arabica Coffee", "Single Origin Coffee", "Specialty Coffee"]
BUSINESS_WEBSITE     = "vb-exports.com"
BUSINESS_EMAIL       = ""          # Add your contact email here
BUSINESS_LINKEDIN    = ""          # LinkedIn company page handle
BUSINESS_INSTAGRAM   = ""          # Instagram handle
BUSINESS_FACEBOOK    = ""          # Facebook page name

# What VB Exports stands for (used in AI prompts for brand voice)
BRAND_POSITIONING = (
    "VB Exports is a premium B2B exporter of Robusta and Arabica coffee beans "
    "sourced directly from Karnataka, India. "
    "We serve international buyers across Europe, the Middle East, and Southeast Asia "
    "with certified, traceable, farm-fresh coffee. Our LinkedIn presence educates "
    "buyers, traders, and procurement managers about Indian coffee export opportunities, "
    "market trends, and compliance requirements — positioning us as the trusted "
    "knowledge authority in the Indian coffee export space."
)

PERSONAL_BRAND_POSITIONING = (
    "Bharath S is a first-generation Indian coffee exporter based in Karnataka. "
    "He shares his real journey — from learning the trade to shipping premium Robusta and "
    "Arabica coffee to buyers in Europe and the Middle East. Authentic, data-backed, "
    "and written to help other small exporters and international buyers navigate the "
    "Indian coffee market."
)

# ══════════════════════════════════════════════════════════════════════════════
# 🎨 BRAND COLORS
# ══════════════════════════════════════════════════════════════════════════════
# Coffee-themed dark palette
COLOR_BG_DARK      = "#1A0A00"   # Deep espresso (slide background)
COLOR_BG_MID       = "#3D1A00"   # Warm espresso (gradient mid)
COLOR_ACCENT_GOLD  = "#C8961E"   # Gold (primary accent, stats, highlights)
COLOR_ACCENT_GREEN = "#2D7A3C"   # Forest green (positive stats, growth)
COLOR_ACCENT_RED   = "#C0392B"   # Red (negative stats, warnings)
COLOR_TEXT_WHITE   = "#FFFFFF"   # Primary text
COLOR_TEXT_CREAM   = "#F5F0E8"   # Body text
COLOR_TEXT_MUTED   = "#A89070"   # Muted text, captions
COLOR_STAT_BOX_BG  = "#2D1400"   # Stat box background
COLOR_CALLOUT_BG   = "#0D2215"   # Insight box (dark green)
COLOR_CALLOUT_BORDER = "#4ADE80" # Insight box border
FOOTER_BG          = "#0D0600"   # Footer band

# RGB tuples for ReportLab (0.0-1.0 scale)
def hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]

# ══════════════════════════════════════════════════════════════════════════════
# 📐 CAROUSEL PAGE DIMENSIONS
# ══════════════════════════════════════════════════════════════════════════════
# Square 1:1 format — best for LinkedIn carousel rendering on mobile
CAROUSEL_PAGE_SIZE = (595, 595)   # points (≈ 20.9 × 20.9 cm at 72dpi)
CAROUSEL_MARGIN    = 36           # points — 6% margin all sides
CAROUSEL_MIN_SLIDES = 7
CAROUSEL_MAX_SLIDES = 10
FOOTER_HEIGHT      = 42           # points — footer band at bottom of every slide

# ══════════════════════════════════════════════════════════════════════════════
# � DUAL ACCOUNT PROFILES
# ══════════════════════════════════════════════════════════════════════════════
# Each profile defines the branding, LinkedIn URN, content voice, and
# cross-platform credentials for one posting account.
# The system auto-selects by weekday: Mon/Wed/Fri = personal, Tue/Thu = company.

ACCOUNT_PROFILES: dict[str, dict] = {
    "personal": {
        "key":           "personal",
        "label":         "Bharath S (Personal)",
        "author_urn":    os.environ.get("LINKEDIN_PERSON_URN", ""),
        "brand_name":    "Bharath S",
        "tagline":       "Coffee Exporter | Karnataka, India",
        "footer_name":   "Bharath S",
        "footer_title":  "Coffee Exporter | VB Exports",
        "monogram":      "BS",
        # Path to circular profile photo (auto-downloaded if avatar_url is provided)
        "avatar_path":   str(ASSETS_DIR / "avatar_personal.jpg") if False else "",
        "avatar_url":    "",   # Set to LinkedIn photo URL to auto-download
        # Cross-platform credentials (personal accounts)
        "facebook_page_id":      os.environ.get("PERSONAL_FACEBOOK_PAGE_ID", ""),
        "facebook_token":        os.environ.get("PERSONAL_FACEBOOK_TOKEN", ""),
        "instagram_user_id":     os.environ.get("PERSONAL_INSTAGRAM_USER_ID", ""),
        # Content generation persona
        "ai_persona":    "personal",
        # Days this account posts (0=Mon … 4=Fri)
        "post_days":     [0, 2, 4],   # Mon, Wed, Fri
    },
    "company": {
        "key":           "company",
        "label":         "VB Exports (Company Page)",
        "author_urn":    os.environ.get("LINKEDIN_ORG_URN", "") or os.environ.get("LINKEDIN_PERSON_URN", ""),
        "brand_name":    "VB Exports",
        "tagline":       "Premium Indian Coffee | B2B Exports",
        "footer_name":   "VB Exports",
        "footer_title":  "Premium Indian Coffee B2B",
        "monogram":      "VB",
        "avatar_path":   str(ASSETS_DIR / "avatar_company.jpg") if False else "",
        "avatar_url":    "",   # Set to LinkedIn company logo URL to auto-download
        # Cross-platform credentials (company/business accounts)
        "facebook_page_id":      os.environ.get("FACEBOOK_PAGE_ID", ""),
        "facebook_token":        os.environ.get("FACEBOOK_ACCESS_TOKEN", ""),
        "instagram_user_id":     os.environ.get("INSTAGRAM_USER_ID", ""),
        # Content generation persona
        "ai_persona":    "company",
        # Days this account posts (0=Mon … 4=Fri)
        "post_days":     [1, 3],       # Tue, Thu
    },
}


def get_account_for_today() -> dict:
    """Returns the account profile that should post today (by weekday)."""
    import pytz
    from datetime import datetime
    weekday = datetime.now(pytz.timezone(TIMEZONE)).weekday()  # 0=Mon, 6=Sun
    for profile in ACCOUNT_PROFILES.values():
        if weekday in profile["post_days"]:
            return profile
    # Fallback — personal on unexpected days
    return ACCOUNT_PROFILES["personal"]


# ══════════════════════════════════════════════════════════════════════════════
# 📅 POSTING SCHEDULE  (Coffee ONLY — Mon–Fri, alternating accounts)
# ══════════════════════════════════════════════════════════════════════════════
SCHEDULE = {
    # Mon / Wed / Fri = PERSONAL account (Bharath S journey + coffee stories)
    "Monday": {
        "category":   "personal_journey",
        "account":    "personal",
        "topic_hint": "My coffee export journey, first shipment, finding buyers, mistakes and wins",
        "label":      "🧑 My Journey Monday",
    },
    "Wednesday": {
        "category":   "personal_lesson",
        "account":    "personal",
        "topic_hint": "Lessons learned as a coffee exporter, tips, things I wish I knew",
        "label":      "💡 Lessons Wednesday",
    },
    "Friday": {
        "category":   "personal_origin",
        "account":    "personal",
        "topic_hint": "Origin stories, Karnataka coffee farms, Coorg varieties, GI tags, farm visits",
        "label":      "🌱 Origin Story Friday",
    },
    # Tue / Thu = COMPANY account (VB Expo market data + buyer guides)
    "Tuesday": {
        "category":   "coffee_market",
        "account":    "company",
        "topic_hint": "India coffee export data, Coffee Board stats, market trends, country-wise buyers",
        "label":      "☕ Market Intelligence Tuesday",
    },
    "Thursday": {
        "category":   "global_buyers",
        "account":    "company",
        "topic_hint": "International coffee buyers, EU requirements, EUDR compliance, UAE buyers, USA demand",
        "label":      "🌍 Buyer Guide Thursday",
    },
    # Weekend — no posting
    "Saturday": None,
    "Sunday":   None,
}

# Posting time (UTC) — 04:30 UTC = 10:00 AM IST, peak LinkedIn engagement
TIMEZONE = "Asia/Kolkata"
CRON_UTC = "30 4 * * *"

# ══════════════════════════════════════════════════════════════════════════════
# 🏷️ HASHTAG STRATEGY — Extended pools for rotation
# ══════════════════════════════════════════════════════════════════════════════
HASHTAGS_PER_POST = 3   # LinkedIn algorithm: 3 max for best reach

HASHTAG_POOLS: dict[str, list[str]] = {
    "coffee_market": [
        "#IndianCoffee", "#CoffeeExports", "#RobustaCoffee", "#ArabicaCoffee",
        "#IndiaExports", "#CoffeeIndustry", "#CoffeeTrade", "#KarnatakaCoffee",
        "#CoorgCoffee", "#SpecialtyCoffee", "#CoffeeBeans", "#GlobalCoffee",
        "#CoffeeMarket", "#AgriExports", "#IndiaAgriBusiness",
    ],
    "global_buyers": [
        "#IndianCoffee", "#CoffeeExports", "#GlobalTrade",
        "#B2BExports", "#IndiaExports", "#CoffeeTrade",
        "#ProcurementManagers", "#CommodityBuyers", "#EUTrade",
        "#MiddleEastTrade", "#IndianExporters", "#KarnatakaCoffee",
    ],
    "personal_journey": [
        "#CoffeeExporter", "#IndianCoffee", "#ExportJourney",
        "#Entrepreneurship", "#KarnatakaCoffee", "#CoffeeBusiness",
        "#SmallExporter", "#IndiaExports", "#CoffeeLife",
        "#AgriExports", "#FirstGeneration", "#CoffeeStory",
    ],
    "personal_lesson": [
        "#CoffeeExporter", "#ExportTips", "#IndianCoffee",
        "#BusinessLessons", "#KarnatakaCoffee", "#CoffeeTrade",
        "#ExportBusiness", "#IndiaExports", "#LessonsLearned",
        "#B2BExports", "#AgriExports", "#CoffeeIndustry",
    ],
    "personal_origin": [
        "#IndianCoffee", "#CoorgCoffee", "#KarnatakaCoffee",
        "#OriginStory", "#SpecialtyCoffee", "#GITag",
        "#CoffeeFarm", "#SingleOrigin", "#CoffeeOrigin",
        "#CoffeeHarvest", "#FarmToExport", "#ChikkamagaluruCoffee",
    ],
    "price_trends": [
        "#CoffeePrices", "#IndianCoffee", "#CoffeeMarket",
        "#CommodityPrices", "#MCX", "#CoffeeFutures",
        "#CoffeeTrade", "#AgriCommodity", "#KarnatakaCoffee",
    ],
    "farm_origin": [
        "#IndianCoffee", "#KarnatakaCoffee", "#CoorgCoffee",
        "#OriginStory", "#SpecialtyCoffee", "#GITag",
        "#CoffeeFarm", "#CoffeeOrigin", "#ChikkamagaluruCoffee",
    ],
    "export_compliance": [
        "#IndianCoffee", "#CoffeeExports", "#APEDA",
        "#ExportCompliance", "#CoffeeTrade", "#OrganicCoffee",
        "#FoodSafety", "#KarnatakaCoffee", "#CertifiedCoffee",
    ],
    "export_guide": [
        "#CoffeeExporter", "#IndianCoffee", "#ExportFromIndia",
        "#ExportBusiness", "#IndiaExports", "#CoffeeTrade",
        "#AgriExports", "#ExportLogistics", "#B2BExports",
    ],
}


def pick_hashtags(category: str) -> list[str]:
    """Randomly picks HASHTAGS_PER_POST hashtags from the category pool."""
    pool = HASHTAG_POOLS.get(category, HASHTAG_POOLS["coffee_market"])
    return random.sample(pool, min(HASHTAGS_PER_POST, len(pool)))

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 AI CONFIGURATION — Google Gemini 2.5 Flash (primary) + Groq (fallback)
# ══════════════════════════════════════════════════════════════════════════════
# gemini-2.0-flash is DEPRECATED — shuts down June 1 2026. Migrated to 2.5-flash.
GEMINI_PRIMARY_MODEL  = "gemini-2.5-flash"      # Stable, free tier, 1M context
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash-lite"  # Smaller stable model as Gemini backup
GROQ_FALLBACK_MODEL   = "llama-3.3-70b-versatile" # Groq (open-source, stable, 1000 RPD free)
AI_TEMPERATURE        = 0.78
AI_MAX_OUTPUT_TOKENS  = 8192   # Gemini 2.5 Flash supports up to 65K; 8K covers 9 slides easily
MAX_REGEN_ATTEMPTS    = 2

# POST_TO_* flags — set to False to skip platforms
POST_TO_LINKEDIN  = True
POST_TO_FACEBOOK  = False   # Enable when Facebook credentials are configured
POST_TO_INSTAGRAM = False   # Enable when Instagram credentials are configured

# ══════════════════════════════════════════════════════════════════════════════
# 📡 API CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# --- Google Sheets ---
GOOGLE_SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID",
    "YOUR_SHEET_ID_HERE",   # Replace with your Sheet ID
)

# --- LinkedIn ---
LINKEDIN_API_VERSION = "202503"
LINKEDIN_PERSON_URN  = os.environ.get("LINKEDIN_PERSON_URN", "")
LINKEDIN_ORG_URN     = os.environ.get("LINKEDIN_ORG_URN", "")   # company page URN
# Post on behalf of the company page if ORG_URN is set, else personal profile
LINKEDIN_AUTHOR_URN  = LINKEDIN_ORG_URN or LINKEDIN_PERSON_URN

# --- Facebook ---
FACEBOOK_PAGE_ID     = os.environ.get("FACEBOOK_PAGE_ID", "")
FACEBOOK_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN", "")

# --- Instagram ---
INSTAGRAM_USER_ID    = os.environ.get("INSTAGRAM_USER_ID", "")
# Instagram uses the same long-lived page access token as Facebook

# --- Cloudinary (for Instagram image hosting) ---
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY    = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

# --- data.gov.in ---
DATA_GOV_API_KEY = os.environ.get("DATA_GOV_API_KEY", "")

# --- GNews ---
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ RETRY / RATE LIMITS
# ══════════════════════════════════════════════════════════════════════════════
API_MAX_RETRIES          = 3
API_INITIAL_DELAY        = 2     # seconds  (doubles each retry)
API_CDN_WAIT_SECONDS     = 30    # wait after LinkedIn upload before posting (allow image processing)
FIRST_COMMENT_DELAY_SECONDS = 45 # wait before posting first comment

# Font filenames expected in FONTS_DIR (downloaded in setup)
FONT_BOLD_FILE    = "Oswald-Bold.ttf"
FONT_REGULAR_FILE = "Montserrat-Regular.ttf"
FONT_LIGHT_FILE   = "Montserrat-Light.ttf"

# ══════════════════════════════════════════════════════════════════════════════
# 📰 RSS / NEWS SOURCES — Coffee focused
# ══════════════════════════════════════════════════════════════════════════════
RSS_FEEDS = [
    # Economic Times — commodity / trade news
    "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1947462.cms",
    # Business Standard — Economy
    "https://www.business-standard.com/rss/economy-policy-10201.rss",
    # Hindu Business Line — Agri
    "https://www.thehindubusinessline.com/economy/agri-business/feeder/default.rss",
]

RSS_MAX_AGE_DAYS = 3   # only use articles published in the last N days

GNEWS_QUERY      = "India coffee exports OR India spice exports OR APEDA"
GNEWS_COUNTRY    = "in"
GNEWS_MAX        = 5

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 UN COMTRADE — India export data
# ══════════════════════════════════════════════════════════════════════════════
COMTRADE_REPORTER = "356"              # India
COMTRADE_HS_CODES = {
    "coffee":   "0901",                # HS chapter 09.01 — coffee
    "spices":   "0904",                # HS chapter 09.04 — pepper
    "cardamom": "0908",                # HS chapter 09.08 — cardamom
    "turmeric": "091030",              # HS code — turmeric
}
COMTRADE_FLOW    = "X"                 # X = exports
COMTRADE_FREQ    = "A"                 # A = annual

# ══════════════════════════════════════════════════════════════════════════════
# 🗃️ DATA.GOV.IN — APEDA Datasets
# ══════════════════════════════════════════════════════════════════════════════
DATA_GOV_BASE_URL = "https://api.data.gov.in/resource"
DATA_GOV_DATASETS = {
    # ✓ VERIFIED UUID resource IDs — confirmed live on 2026-04-09
    # API format: GET {DATA_GOV_BASE_URL}/{uuid}?api-key=KEY&format=json&limit=20
    #
    # Coffee Exports 2016-19 (Coffee Board / Rajya Sabha Session 250)
    # Fields: _year, quantity__mt__
    # Live sample: {"_year": "2016-17", "quantity__mt__": 344870}
    "coffee_exports":   "5e23b7c3-d4df-4a65-ac46-ba4b4e2d4ecb",
    #
    # State-wise Coffee Production 2022-23 (Coffee Board / Rajya Sabha Session 263)
    # Fields: state, area__ha__, production__mt_, productivity__kg_ha____robusta, ..._arabica
    # Live sample: Karnataka: area=246550 Ha, production=248020 MT
    "coffee_statewise": "c8cdea60-94b6-46be-8b7f-3c6f2d734d72",
    #
    # Spice Exports by Country — Ministry of Commerce (may timeout intermittently)
    "spice_exports":    "9481b8ec-099c-4baa-b94a-f288f44cc223",
    #
    # Karnataka Horticulture Spice Production (Dept of Horticulture)
    "spice_horticulture": "ac1a1477-94c6-4620-89a2-7d5f7a3bd1f4",
}
DATA_GOV_LIMIT = 20   # records per request

# ══════════════════════════════════════════════════════════════════════════════
# 📊 PLATFORMS TO POST ON
# ══════════════════════════════════════════════════════════════════════════════
# Set False to skip a platform without removing its code
POST_TO_LINKEDIN  = True
POST_TO_FACEBOOK  = True
POST_TO_INSTAGRAM = True
