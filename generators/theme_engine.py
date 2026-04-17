"""
generators/theme_engine.py
───────────────────────────
Date-driven design rotation engine.

Returns a fully-resolved Theme object for any given date. Completely
deterministic — the same date always returns the same theme, forever.

Design rotation layers:
  Layer 1 — Seasonal colour palette   (12 palettes, 1 per month)
  Layer 2 — Slide layout variant      (4 layouts, rotates by ISO week % 4)
  Layer 3 — Photo visual style        (4 styles,  rotates by ISO week % 4)
  Layer 4 — Headline alignment        (2 options, alternates by month parity)

384 unique combinations = no repeat within ~18 months of daily posting.

Usage:
  from generators.theme_engine import get_theme
  theme = get_theme()          # today
  theme = get_theme(some_date) # specific date
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Monthly colour palettes
# ══════════════════════════════════════════════════════════════════════════════

# Each palette: (name, bg_hex, accent_hex, subtitle_hex, photo_overlay_alpha)
# bg_hex       = solid background colour for lower 55% of slide
# accent_hex   = headline colour, stat numbers, CTA pill, bullet highlights
# subtitle_hex = muted secondary text (titles, source lines)
# overlay_alpha = 0.0-1.0 gradient strength over the photo (higher = darker midpoint)

MONTHLY_PALETTES = {
    1:  ("Harvest Gold",   "#0D0800", "#F5A623", "#A07830", 0.75),
    2:  ("Classic Premium","#0A0A0A", "#FFD700", "#888888", 0.72),
    3:  ("Growth Green",   "#020F05", "#4ADE80", "#2D6040", 0.70),
    4:  ("Export Ocean",   "#020812", "#38BDF8", "#2060A0", 0.73),
    5:  ("Dawn Amber",     "#0D0800", "#FCD34D", "#907830", 0.72),
    6:  ("Monsoon Teal",   "#020C0F", "#2DD4BF", "#1A6070", 0.75),
    7:  ("Deep Forest",    "#030F07", "#86EFAC", "#2A5040", 0.72),
    8:  ("Rust Earth",     "#0F0702", "#FB923C", "#904030", 0.74),
    9:  ("Festival Gold",  "#080600", "#FBBF24", "#806020", 0.73),
    10: ("Berry Rich",     "#0C0208", "#C084FC", "#603080", 0.76),
    11: ("Ice Silver",     "#0A0A0A", "#E2E8F0", "#707070", 0.72),
    12: ("Fire Crimson",   "#0F0202", "#F87171", "#A03030", 0.75),
}


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Layout variants (rotates by ISO week number % 4)
# ══════════════════════════════════════════════════════════════════════════════

# CLASSIC : Photo 45% top, headline + bullet list below (matches reference design)
# BOLD    : Photo 35% top, 3-line massive headline dominates, 2-3 bullets
# DATA    : Photo 40% top, 3 stat blocks side-by-side, smaller bullet list
# STORY   : Photo 55% top (immersive), smaller text area, narrative paragraph style

LAYOUT_VARIANTS = ["CLASSIC", "BOLD", "DATA", "STORY"]


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Photo keyword style (rotates by ISO week number % 4)
# ══════════════════════════════════════════════════════════════════════════════

# Lists of Unsplash search keywords per style, in order of preference.
# The system tries each keyword until a photo downloads successfully.

PHOTO_STYLES: dict[str, dict[str, list[str]]] = {
    "LANDSCAPE": {
        "coffee_market":    ["coffee plantation aerial", "coffee farm landscape", "karnataka hills coffee", "india agriculture hills"],
        "global_buyers":    ["container ship port", "cargo export shipping", "international trade port", "freight logistics aerial"],
        "price_trends":     ["commodity market trading", "stock exchange graph", "business finance chart", "economic growth india"],
        "farm_origin":      ["coorg coffee farm", "coffee plantation karnataka", "india hill station farm", "coffee estate landscape"],
        "export_compliance":["customs inspection", "export documentation", "government office india", "business certification"],
        "export_guide":     ["business handshake deal", "export logistics truck", "trade cargo port", "business growth strategy"],
        "personal_journey": ["entrepreneur journey road", "coffee farm sunrise", "business success path", "india countryside sunrise"],
        "personal_lesson":  ["business lesson notebook", "coffee exporter meeting", "trade conference india", "business growth learn"],
        "personal_origin":  ["coorg coffee hills", "karnataka farm dawn", "coffee plantation sunrise", "india estate morning"],
        "_default":         ["coffee export india", "coffee plantation", "agriculture india", "business trade"],
    },
    "MACRO": {
        "coffee_market":    ["coffee beans closeup", "coffee cherry detail", "arabica beans macro", "robusta coffee texture"],
        "global_buyers":    ["coffee cup premium", "espresso shot close", "specialty coffee detail", "coffee aroma steam"],
        "price_trends":     ["coffee beans scale weight", "commodity coffee pile", "green coffee beans", "coffee export quality"],
        "farm_origin":      ["coffee cherry red ripe", "coffee blossom flower", "coffee green cherry", "coffee fruit macro"],
        "export_compliance":["quality check coffee", "laboratory coffee testing", "certification stamp closeup", "food safety inspection"],
        "export_guide":     ["coffee packaging close", "export box coffee brand", "shipping label detail", "business document close"],
        "personal_journey": ["coffee farmer hands", "coffee bean selection hand", "farmer coffee sorting", "hand coffee harvest"],
        "personal_lesson":  ["coffee cupping professional", "coffee tasting expert", "barista coffee detail", "coffee quality test"],
        "personal_origin":  ["coffee cherry harvest hand", "coffee plantation leaf", "coffee farm flower", "india coffee nature"],
        "_default":         ["coffee beans macro", "coffee cherry", "coffee farm", "coffee texture"],
    },
    "PEOPLE": {
        "coffee_market":    ["coffee farmer india", "indian farmer field", "agriculture worker india", "coffee exporter smile"],
        "global_buyers":    ["business handshake deal", "export meeting professional", "buyer seller trade", "international business people"],
        "price_trends":     ["business trader screen", "commodity market professional", "businessman india office", "trade analytics professional"],
        "farm_origin":      ["coffee farmer karnataka", "indian farmer harvest", "coffee picker woman", "agriculture india community"],
        "export_compliance":["business compliance officer", "customs officer inspection", "quality inspector food", "certification business india"],
        "export_guide":     ["entrepreneur india success", "small business owner india", "exporter india professional", "business startup india"],
        "personal_journey": ["young entrepreneur india", "first generation businessman", "coffee farm owner india", "startup founder india"],
        "personal_lesson":  ["business mentor india", "professional learning coffee", "entrepreneur reflection", "business growth person"],
        "personal_origin":  ["farmer karnataka india", "coffee community farmer", "india agriculture people", "farmer family india"],
        "_default":         ["coffee professional", "business india professional", "farmer india", "exporter india"],
    },
    "ABSTRACT": {
        "coffee_market":    ["coffee dark artistic", "coffee light bokeh", "espresso dark abstract", "coffee steam dramatic"],
        "global_buyers":    ["world map dark background", "global trade abstract", "network connection globe", "dark blue trade abstract"],
        "price_trends":     ["dark graph market abstract", "financial chart dark", "commodity wave chart", "economic data visualize"],
        "farm_origin":      ["dark coffee nature artistic", "coffee moody abstract", "coffee atmospheric dark", "forest dark nature"],
        "export_compliance":["document abstract dark", "legal compliance abstract", "business certification dark", "professional abstract dark"],
        "export_guide":     ["dark success abstract", "business growth pattern", "strategic path abstract", "dark professional abstract"],
        "personal_journey": ["journey road dark dramatic", "path forward dark abstract", "success story dark", "entrepreneur dark artistic"],
        "personal_lesson":  ["light bulb dark idea", "learning abstract dark", "knowledge dark creative", "insight abstract professional"],
        "personal_origin":  ["dark forest nature abstract", "earth texture dark", "nature dramatic abstract", "dark rich texture india"],
        "_default":         ["coffee dark abstract", "dark artistic coffee", "dramatic coffee", "dark texture premium"],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — Headline alignment (alternates by month parity)
# ══════════════════════════════════════════════════════════════════════════════

# Odd months  → "left"   (grounded, journalistic feel)
# Even months → "center" (dramatic, premium editorial feel)


# ══════════════════════════════════════════════════════════════════════════════
# Theme dataclass
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Theme:
    # Identity
    date:              date
    palette_name:      str    # e.g. "Classic Premium"
    layout:            str    # "CLASSIC" | "BOLD" | "DATA" | "STORY"
    photo_style:       str    # "LANDSCAPE" | "MACRO" | "PEOPLE" | "ABSTRACT"
    headline_align:    str    # "left" | "center"

    # Colours (hex strings)
    bg_color:          str    # slide background (lower area)
    accent_color:      str    # headlines, stats, highlights
    subtitle_color:    str    # muted secondary text
    photo_overlay_alpha: float  # gradient strength 0.0-1.0

    # Photo keywords — resolved per category
    def photo_keywords(self, category: str) -> list[str]:
        cat_map = PHOTO_STYLES[self.photo_style]
        return cat_map.get(category, cat_map["_default"])

    # Derived RGB tuples (0-255) for Pillow
    @property
    def bg_rgb(self) -> tuple[int, int, int]:
        return _hex_to_rgb(self.bg_color)

    @property
    def accent_rgb(self) -> tuple[int, int, int]:
        return _hex_to_rgb(self.accent_color)

    @property
    def subtitle_rgb(self) -> tuple[int, int, int]:
        return _hex_to_rgb(self.subtitle_color)

    @property
    def white_rgb(self) -> tuple[int, int, int]:
        return (255, 255, 255)

    def __str__(self) -> str:
        return (
            f"Theme({self.date}: {self.palette_name} | "
            f"{self.layout} | {self.photo_style} | align={self.headline_align})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def get_theme(for_date: Optional[date] = None) -> Theme:
    """
    Returns the deterministic Theme for a given date.

    Args:
        for_date: Date to compute theme for. Defaults to today (UTC).

    Returns:
        Theme dataclass with all design parameters resolved.
    """
    if for_date is None:
        for_date = date.today()

    month     = for_date.month
    iso_week  = for_date.isocalendar()[1]   # 1-53

    # Layer 1: palette (by month)
    p = MONTHLY_PALETTES[month]
    palette_name, bg_color, accent_color, subtitle_color, overlay_alpha = p

    # Layer 2: layout (by iso_week % 4)
    layout = LAYOUT_VARIANTS[iso_week % 4]

    # Layer 3: photo style (by (iso_week + 1) % 4 — offset so layout and photo don't sync)
    photo_style = ["LANDSCAPE", "MACRO", "PEOPLE", "ABSTRACT"][(iso_week + 1) % 4]

    # Layer 4: alignment (odd months = left, even months = center)
    headline_align = "left" if month % 2 == 1 else "center"

    return Theme(
        date               = for_date,
        palette_name       = palette_name,
        layout             = layout,
        photo_style        = photo_style,
        headline_align     = headline_align,
        bg_color           = bg_color,
        accent_color       = accent_color,
        subtitle_color     = subtitle_color,
        photo_overlay_alpha = overlay_alpha,
    )


def preview_year(year: int = 2026) -> None:
    """Prints a full-year theme preview — useful for planning."""
    from datetime import timedelta
    d = date(year, 1, 1)
    while d.year == year:
        if d.weekday() < 5:  # Mon-Fri only
            t = get_theme(d)
            print(f"{d.strftime('%a %Y-%m-%d')}  {str(t)}")
        d += timedelta(days=1)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


if __name__ == "__main__":
    # Quick test
    t = get_theme()
    print(t)
    print(f"  BG:     {t.bg_color}  {t.bg_rgb}")
    print(f"  Accent: {t.accent_color}  {t.accent_rgb}")
    print(f"  Keywords (coffee_market): {t.photo_keywords('coffee_market')[:2]}")
