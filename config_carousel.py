"""
config_carousel.py — VB Exports Brand & Carousel Configuration
═══════════════════════════════════════════════════════════════
Edit THIS file to change brand identity, themes, footer, or topics.
Python code in main.py / generators never needs to change for brand updates.

To use for a different business: replace everything in the BRAND section.
"""
from __future__ import annotations

import os
import pathlib

BASE_DIR   = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"

# ══════════════════════════════════════════════════════════════════════════════
# BRAND IDENTITY  (edit this section to change brand)
# ══════════════════════════════════════════════════════════════════════════════
BRAND = {
    "name":        "VB Exports",
    "tagline":     "Premium Indian Coffee | B2B Exports",
    "website":     "vb-exports.com",
    "phone":       "+91 9449522395",
    "logo_url":    "https://vb-exports.com/images/products/Home/Logo/logo.jpg",
    "logo_cache":  str(ASSETS_DIR / "vb_logo.png"),   # cached locally after first download
}

# ══════════════════════════════════════════════════════════════════════════════
# FIXED FOOTER (identical on personal + company posts — promotes the brand)
# ══════════════════════════════════════════════════════════════════════════════
FOOTER = {
    "line1": "VB Exports  ·  Premium Indian Coffee",
    "line2": "vb-exports.com  ·  +91 9449522395",
}

# ══════════════════════════════════════════════════════════════════════════════
# EDGE BROWSER PATH (for Playwright — installed at system level)
# ══════════════════════════════════════════════════════════════════════════════
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY → THEME MAPPING  (fixed per topic — never rotates randomly)
# Each category has its own identity. Within a PDF all slides share one theme.
# ══════════════════════════════════════════════════════════════════════════════
CATEGORY_THEMES = {
    "coffee_market": {
        "bg":           "#1A0A00",   # Deep espresso
        "bg2":          "#2D1400",   # Gradient mid
        "accent":       "#C8961E",   # Warm gold
        "text_primary": "#FFFFFF",
        "text_muted":   "#D4B483",
        "badge_text":   "MARKET INSIGHT",
        "pexels_query": "coffee beans dark roast espresso",
        "template":     "slide_coffee_market.html",
    },
    "price_trends": {
        "bg":           "#1C0F00",
        "bg2":          "#2E1A00",
        "accent":       "#D4820A",   # Amber
        "text_primary": "#FFFFFF",
        "text_muted":   "#C89A6A",
        "badge_text":   "PRICE INTELLIGENCE",
        "pexels_query": "commodity trading market analytics business",
        "template":     "slide_price_trends.html",
    },
    "global_buyers": {
        "bg":           "#050F1A",   # Midnight navy
        "bg2":          "#0A1929",
        "accent":       "#4A9EDB",   # Steel blue
        "text_primary": "#FFFFFF",
        "text_muted":   "#7AB0CC",
        "badge_text":   "GLOBAL TRADE",
        "pexels_query": "cargo container ship port shipping export",
        "template":     "slide_global_buyers.html",
    },
    "farm_origin": {
        "bg":           "#0B1E0F",   # Forest green
        "bg2":          "#122A17",
        "accent":       "#7EC89A",   # Leaf green
        "text_primary": "#FFFFFF",
        "text_muted":   "#B8D4BC",
        "badge_text":   "ORIGIN STORY",
        "pexels_query": "coffee plantation farm harvest green nature",
        "template":     "slide_farm_origin.html",
    },
    "export_guide": {
        "bg":           "#111418",   # Graphite
        "bg2":          "#1A1F25",
        "accent":       "#34A853",   # Material green
        "text_primary": "#E8EAED",
        "text_muted":   "#9AA0A6",
        "badge_text":   "EXPORT GUIDE",
        "pexels_query": "logistics warehouse customs inspection supply chain",
        "template":     "slide_export_guide.html",
    },
    # Personal categories → warm cream Tailwind template (Merriweather + Open Sans)
    "personal_journey": {
        "bg":           "#FDFBF7",
        "bg2":          "#F0E8DC",
        "accent":       "#B8860B",   # Dark goldenrod
        "accent2":      "#2D6A4F",   # Deep forest green
        "text_primary": "#2C1810",   # Rich espresso
        "text_muted":   "#7A6652",
        "badge_text":   "MY JOURNEY",
        "pexels_query": "Indian coffee exporter Karnataka farm entrepreneur portrait",
        "template":     "slide_personal.html",
    },
    "personal_lesson": {
        "bg":           "#FDFBF7",
        "bg2":          "#F0E8DC",
        "accent":       "#B8860B",
        "accent2":      "#2D6A4F",
        "text_primary": "#2C1810",
        "text_muted":   "#7A6652",
        "badge_text":   "LESSON LEARNED",
        "pexels_query": "coffee export business lesson entrepreneur desk notebook",
        "template":     "slide_personal.html",
    },
    "personal_origin": {
        "bg":           "#0B1E0F",
        "bg2":          "#122A17",
        "accent":       "#7EC89A",
        "text_primary": "#FFFFFF",
        "text_muted":   "#B8D4BC",
        "badge_text":   "ORIGIN STORY",
        "pexels_query": "coffee plantation Karnataka India farm green",
        "template":     "slide_farm_origin.html",
    },
}

# Default for unknown categories
DEFAULT_THEME = CATEGORY_THEMES["coffee_market"]


def get_carousel_theme(category: str) -> dict:
    """Returns the fixed theme dict for a category."""
    return CATEGORY_THEMES.get(category, DEFAULT_THEME)


# ══════════════════════════════════════════════════════════════════════════════
# PDF NAMING  (shown to buyers inside LinkedIn PDF viewer)
# ══════════════════════════════════════════════════════════════════════════════
CATEGORY_PDF_NAMES = {
    "coffee_market":    "VB-Exports-Coffee-Market-Intelligence",
    "price_trends":     "VB-Exports-Arabica-Robusta-Price-Trends",
    "global_buyers":    "VB-Exports-International-Buyer-Market-Guide",
    "farm_origin":      "VB-Exports-Karnataka-Farm-Origins",
    "export_guide":     "VB-Exports-Export-Compliance-Guide",
    "personal_journey": "Bharath-S-Coffee-Export-Journey",
    "personal_lesson":  "Bharath-S-Coffee-Trade-Lessons",
    "personal_origin":  "Bharath-S-Karnataka-Coffee-Origin-Story",
}


def get_pdf_filename(category: str, month: str, year: str) -> str:
    """Returns a brand-professional PDF filename visible to LinkedIn viewers."""
    base = CATEGORY_PDF_NAMES.get(category, "VB-Exports-Coffee-Insights")
    return f"{base}-{month}-{year}.pdf"


# ══════════════════════════════════════════════════════════════════════════════
# PERSONAL ACCOUNT — WEEKDAY COLOR PALETTES  (Option B Dynamic Colors)
# ──────────────────────────────────────────────────────────────────────────────
# Each weekday gets its own dark background + two radial bloom colours.
# Gold (#D4A843) and teal (#2DBFBF) accents are FIXED — only the dark base
# and bloom radials change. This keeps bullet cards, badges, and fp-strip
# consistent across all days while the overall mood shifts.
#
# All hex values are dark (luminance < 15%) so text/cards remain readable.
# card_bg / card_bdr are slightly tuned per palette for contrast.
# ══════════════════════════════════════════════════════════════════════════════
PERSONAL_WEEKLY_PALETTES = {
    "Monday": {
        "name":     "Forest Green",
        "bg_base":  "#071510",                       # near-black forest
        "bloom1":   "rgba(30,85,58,0.92)",            # deep forest green NW
        "bloom2":   "rgba(20,75,100,0.65)",           # dark teal SE
        "accent":   "#D4A843",                        # gold
        "accent2":  "#2DBFBF",                        # teal
        "card_bg":  "rgba(255,255,255,0.09)",
        "card_bdr": "rgba(255,255,255,0.13)",
    },
    "Tuesday": {
        "name":     "Midnight Navy",
        "bg_base":  "#060D18",                        # near-black navy
        "bloom1":   "rgba(22,55,100,0.90)",           # deep navy blue NW
        "bloom2":   "rgba(50,20,80,0.60)",            # deep indigo-purple SE
        "accent":   "#D4A843",
        "accent2":  "#2DBFBF",
        "card_bg":  "rgba(255,255,255,0.09)",
        "card_bdr": "rgba(255,255,255,0.13)",
    },
    "Wednesday": {
        "name":     "Deep Teal",
        "bg_base":  "#051410",                        # near-black teal
        "bloom1":   "rgba(15,75,75,0.92)",            # deep teal NW
        "bloom2":   "rgba(20,85,55,0.65)",            # forest green SE
        "accent":   "#D4A843",
        "accent2":  "#2DBFBF",
        "card_bg":  "rgba(255,255,255,0.09)",
        "card_bdr": "rgba(255,255,255,0.13)",
    },
    "Thursday": {
        "name":     "Espresso Burgundy",
        "bg_base":  "#120608",                        # near-black burgundy
        "bloom1":   "rgba(85,20,30,0.88)",            # deep burgundy NW
        "bloom2":   "rgba(20,55,45,0.65)",            # dark forest SE
        "accent":   "#D4A843",
        "accent2":  "#2DBFBF",
        "card_bg":  "rgba(255,255,255,0.09)",
        "card_bdr": "rgba(255,255,255,0.13)",
    },
    "Friday": {
        "name":     "Deep Indigo",
        "bg_base":  "#080810",                        # near-black indigo
        "bloom1":   "rgba(45,30,95,0.90)",            # deep indigo NW
        "bloom2":   "rgba(20,75,80,0.65)",            # dark teal SE
        "accent":   "#D4A843",
        "accent2":  "#2DBFBF",
        "card_bg":  "rgba(255,255,255,0.09)",
        "card_bdr": "rgba(255,255,255,0.13)",
    },
    # Weekends fall back to Monday Forest Green
    "Saturday": None,
    "Sunday":   None,
}

# Default palette (used on weekends or if weekday lookup fails)
_DEFAULT_PERSONAL_PALETTE = PERSONAL_WEEKLY_PALETTES["Monday"]


def get_personal_palette(weekday_name: str | None = None) -> dict:
    """
    Returns the weekday colour palette for the personal carousel template.
    Pass weekday_name as e.g. 'Monday'. If None, uses today's weekday (IST).
    Weekend days fall back to Monday Forest Green.
    """
    if weekday_name is None:
        from datetime import datetime
        import pytz
        weekday_name = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%A")
    palette = PERSONAL_WEEKLY_PALETTES.get(weekday_name)
    return palette if palette else _DEFAULT_PERSONAL_PALETTE
