"""
generators/carousel_gen.py
───────────────────────────
Renders Gemini-generated slide dicts into a visually rich multi-page PDF
suitable for LinkedIn native document (carousel) posts.

Design system: VB Exports — premium coffee & spice export brand
  • Deep espresso background  (#1A0A00)
  • Gold accent bar           (#C8961E)
  • Forest green callout box  (#0D2215 / border #4ADE80)
  • Montserrat font family    (downloadable via setup_fonts.py)
  • Square 1:1 pages (595×595 pt) — renders perfectly on LinkedIn mobile

Each slide layout adapts to its TYPE:
  HOOK        → large headline + stat pillbox + forward arrow
  CONTEXT     → left-accent bar + body paragraphs
  STAT        → centred gold stat callbox + supporting body
  INSIGHT     → green callout box with lightbulb icon
  IMPLICATION → numbered step layout
  TIP         → numbered tip card with bold intro
  CTA/BRAND   → centred VB Exports logo text + follow prompt
"""

from __future__ import annotations

import logging
import math
import os
import pathlib
from typing import Optional

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

from config import (
    COLOR_BG_DARK, COLOR_BG_MID, COLOR_ACCENT_GOLD, COLOR_ACCENT_GREEN,
    COLOR_ACCENT_RED, COLOR_TEXT_WHITE, COLOR_TEXT_CREAM, COLOR_TEXT_MUTED,
    COLOR_STAT_BOX_BG, COLOR_CALLOUT_BG, COLOR_CALLOUT_BORDER,
    FOOTER_BG, CAROUSEL_PAGE_SIZE, CAROUSEL_MARGIN, FOOTER_HEIGHT,
    BUSINESS_NAME, BUSINESS_TAGLINE, BUSINESS_WEBSITE,
    FONTS_DIR, OUTPUT_DIR,
)

log = logging.getLogger(__name__)

# ── Page dimensions ──────────────────────────────────────────────────────────
W, H     = CAROUSEL_PAGE_SIZE          # 595×595 pt (square)
M        = CAROUSEL_MARGIN             # 36 pt margin
FH       = FOOTER_HEIGHT               # 42 pt footer band
CONTENT_W = W - (2 * M)               # 523 pt
CONTENT_H = H - FH - (2 * M)          # slide body height

# ── Color helpers ────────────────────────────────────────────────────────────
def _c(hex_str: str) -> Color:
    return HexColor(hex_str)

BG       = _c(COLOR_BG_DARK)
BG_MID   = _c(COLOR_BG_MID)
GOLD     = _c(COLOR_ACCENT_GOLD)
GREEN    = _c(COLOR_ACCENT_GREEN)
GREEN_BG = _c(COLOR_CALLOUT_BG)
GREEN_BD = _c(COLOR_CALLOUT_BORDER)
RED      = _c(COLOR_ACCENT_RED)
WHITE    = _c(COLOR_TEXT_WHITE)
CREAM    = _c(COLOR_TEXT_CREAM)
MUTED    = _c(COLOR_TEXT_MUTED)
STAT_BG  = _c(COLOR_STAT_BOX_BG)
FOOTER   = _c(FOOTER_BG)


# ══════════════════════════════════════════════════════════════════════════════
# FONT REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

_FONTS_REGISTERED = False

def _register_fonts() -> bool:
    """
    Register Montserrat TTF fonts. Falls back to Helvetica if not installed.
    Returns True if custom fonts registered, False if using built-in fallback.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return True

    bold_path    = FONTS_DIR / "Montserrat-Bold.ttf"
    regular_path = FONTS_DIR / "Montserrat-Regular.ttf"
    light_path   = FONTS_DIR / "Montserrat-Light.ttf"

    if all(p.exists() for p in [bold_path, regular_path, light_path]):
        try:
            pdfmetrics.registerFont(TTFont("Montserrat-Bold",    str(bold_path)))
            pdfmetrics.registerFont(TTFont("Montserrat-Regular", str(regular_path)))
            pdfmetrics.registerFont(TTFont("Montserrat-Light",   str(light_path)))
            _FONTS_REGISTERED = True
            log.info("Montserrat fonts registered")
            return True
        except Exception as e:
            log.warning("Font registration failed: %s — falling back to Helvetica", e)

    log.info("Montserrat fonts not found at %s — using Helvetica", FONTS_DIR)
    return False


def _font(style: str, custom: bool) -> str:
    """Returns font name: Montserrat-XX if registered, else Helvetica equivalent."""
    if custom:
        return f"Montserrat-{style}"
    mapping = {"Bold": "Helvetica-Bold", "Regular": "Helvetica", "Light": "Helvetica"}
    return mapping.get(style, "Helvetica")


# ══════════════════════════════════════════════════════════════════════════════
# TEXT UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _wrap_text(c_obj: canvas.Canvas, text: str, font: str, size: float,
               max_width: float) -> list[str]:
    """Word-wrap text to fit within max_width at the given font size."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if c_obj.stringWidth(test, font, size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_wrapped_text(c_obj: canvas.Canvas, text: str, font: str, size: float,
                       color: Color, x: float, y: float, max_width: float,
                       line_spacing: float = 1.35, align: str = "left") -> float:
    """
    Draws word-wrapped text. Returns the y coordinate after the last line.
    align: 'left' | 'center'
    """
    c_obj.setFont(font, size)
    c_obj.setFillColor(color)
    lines = _wrap_text(c_obj, text, font, size, max_width)
    line_h = size * line_spacing

    for line in lines:
        if align == "center":
            c_obj.drawCentredString(x, y, line)
        else:
            c_obj.drawString(x, y, line)
        y -= line_h

    return y


# ══════════════════════════════════════════════════════════════════════════════
# SHARED SLIDE ELEMENTS
# ══════════════════════════════════════════════════════════════════════════════

def _draw_background(c_obj: canvas.Canvas) -> None:
    """Full-page espresso gradient background."""
    # Base dark fill
    c_obj.setFillColor(BG)
    c_obj.rect(0, 0, W, H, fill=1, stroke=0)

    # Subtle warm gradient overlay (bottom half warmer)
    for i in range(20):
        ratio   = i / 20
        r       = 0x1A + int(0x23 * ratio)
        g       = 0x0A + int(0x10 * ratio)
        b       = 0x00
        alpha   = 0.06
        c_obj.setFillColorRGB(r / 255, g / 255, b / 255, alpha)
        band_h  = H / 20
        c_obj.rect(0, i * band_h, W, band_h + 1, fill=1, stroke=0)


def _draw_header_bar(c_obj: canvas.Canvas, slide_num: int, total: int, custom_fonts: bool) -> None:
    """Top gold accent bar with slide counter."""
    bar_h = 5
    c_obj.setFillColor(GOLD)
    c_obj.rect(0, H - bar_h, W, bar_h, fill=1, stroke=0)

    # Slide counter — top right
    counter_text = f"{slide_num} / {total}"
    c_obj.setFont(_font("Bold", custom_fonts), 9)
    c_obj.setFillColor(MUTED)
    c_obj.drawRightString(W - M, H - bar_h - 16, counter_text)


def _draw_footer(c_obj: canvas.Canvas, custom_fonts: bool, swipe_arrow: bool = False) -> None:
    """Footer band with VB Exports branding."""
    c_obj.setFillColor(FOOTER)
    c_obj.rect(0, 0, W, FH, fill=1, stroke=0)

    # Thin gold top border
    c_obj.setStrokeColor(GOLD)
    c_obj.setLineWidth(0.5)
    c_obj.line(0, FH, W, FH)

    c_obj.setFont(_font("Bold", custom_fonts), 9)
    c_obj.setFillColor(GOLD)
    c_obj.drawString(M, FH - 14, BUSINESS_NAME.upper())

    c_obj.setFont(_font("Light", custom_fonts), 8)
    c_obj.setFillColor(MUTED)
    c_obj.drawString(M, FH - 26, BUSINESS_WEBSITE)

    if swipe_arrow:
        c_obj.setFont(_font("Bold", custom_fonts), 10)
        c_obj.setFillColor(GOLD)
        c_obj.drawRightString(W - M, FH - 20, "SWIPE →")


def _draw_gold_pill_stat(c_obj: canvas.Canvas, stat: str, cx: float, y: float,
                          custom_fonts: bool) -> float:
    """
    Draws a gold pill-shaped callout box with the stat value inside.
    Returns y coordinate below the pill.
    """
    font   = _font("Bold", custom_fonts)
    size   = 28
    pad_x  = 22
    pad_y  = 10
    radius = 10

    text_w = c_obj.stringWidth(stat, font, size)
    pill_w = text_w + (2 * pad_x)
    pill_h = size + (2 * pad_y)
    pill_x = cx - pill_w / 2
    pill_y = y - pill_h

    # Gold filled rounded rect
    c_obj.setFillColor(GOLD)
    c_obj.roundRect(pill_x, pill_y, pill_w, pill_h, radius, fill=1, stroke=0)

    # Dark text inside
    c_obj.setFont(font, size)
    c_obj.setFillColor(BG)
    c_obj.drawCentredString(cx, pill_y + pad_y + 2, stat)

    return pill_y - 12


def _draw_green_callout(c_obj: canvas.Canvas, text: str, x: float, y: float,
                         width: float, custom_fonts: bool) -> float:
    """
    Green insight callout box. Returns new y after box.
    """
    font     = _font("Regular", custom_fonts)
    size     = 13
    pad      = 14
    radius   = 8
    lines    = _wrap_text(c_obj, text, font, size, width - (2 * pad) - 8)
    line_h   = size * 1.4
    box_h    = len(lines) * line_h + (2 * pad)

    # Dark green fill
    c_obj.setFillColor(GREEN_BG)
    c_obj.roundRect(x, y - box_h, width, box_h, radius, fill=1, stroke=0)

    # Green left border
    c_obj.setFillColor(GREEN_BD)
    c_obj.roundRect(x, y - box_h, 4, box_h, 2, fill=1, stroke=0)

    # Text
    c_obj.setFont(font, size)
    c_obj.setFillColor(CREAM)
    ty = y - pad - size
    for line in lines:
        c_obj.drawString(x + pad + 8, ty, line)
        ty -= line_h

    return y - box_h - 10


def _draw_icon(c_obj: canvas.Canvas, icon: str, x: float, y: float,
               size: float, custom_fonts: bool) -> None:
    """Draws a single emoji glyph. Uses Helvetica (PDF doesn't need font for basic emoji text)."""
    c_obj.setFont("Helvetica", size)
    c_obj.setFillColor(GOLD)
    c_obj.drawString(x, y, icon)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_hook(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool) -> None:
    """
    HOOK slide — first slide. Must stop the scroll.
    Layout: Category label → large title → stat pill → body → swipe prompt
    """
    _draw_background(c_obj)
    _draw_header_bar(c_obj, slide["slide_num"], total, cf)
    _draw_footer(c_obj, cf, swipe_arrow=True)

    cx = W / 2
    y  = H - 40  # start below top bar

    # Slide type label
    c_obj.setFont(_font("Bold", cf), 9)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, y - 10, "📊 DAILY EXPORT INSIGHT")

    y -= 30

    # Icon
    icon = slide.get("icon", "☕")
    c_obj.setFont("Helvetica", 32)
    c_obj.setFillColor(CREAM)
    c_obj.drawCentredString(cx, y - 10, icon)
    y -= 50

    # Main title — large, bold, white, wrapped
    title = slide.get("title", "")
    font  = _font("Bold", cf)
    size  = 30
    # Dynamically shrink if title is long
    while c_obj.stringWidth(title, font, size) > CONTENT_W * 1.5 and size > 18:
        size -= 2
    y = _draw_wrapped_text(c_obj, title, font, size, WHITE, cx, y,
                            CONTENT_W, line_spacing=1.25, align="center")
    y -= 10

    # Stat callout pill
    stat = slide.get("stat_callout", "")
    if stat:
        y = _draw_gold_pill_stat(c_obj, stat, cx, y, cf)
        y -= 8

    # Body text
    body = slide.get("body", "")
    if body:
        _draw_wrapped_text(c_obj, body, _font("Regular", cf), 13, CREAM,
                           cx, y, CONTENT_W, line_spacing=1.5, align="center")

    # Swipe cue (above footer)
    swipe_y = FH + 12
    c_obj.setFont(_font("Bold", cf), 10)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, swipe_y, "Swipe to see the numbers that matter →")


def _render_context(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool) -> None:
    """
    CONTEXT slide — macro market driver explanation.
    Layout: left gold accent bar + title + body paragraphs
    """
    _draw_background(c_obj)
    _draw_header_bar(c_obj, slide["slide_num"], total, cf)
    _draw_footer(c_obj, cf, swipe_arrow=True)

    # Gold left accent bar
    bar_x, bar_y, bar_w, bar_h = M, FH + 24, 4, H - FH - 60
    c_obj.setFillColor(GOLD)
    c_obj.rect(bar_x, bar_y, bar_w, bar_h, fill=1, stroke=0)

    x = M + 18
    y = H - 56

    icon = slide.get("icon", "")
    if icon:
        c_obj.setFont("Helvetica", 22)
        c_obj.setFillColor(GOLD)
        c_obj.drawString(x, y, icon)
        x += 32

    # Title
    y = H - 60
    y = _draw_wrapped_text(c_obj, slide.get("title", ""), _font("Bold", cf), 22,
                            WHITE, M + 22, y, CONTENT_W - 22, line_spacing=1.3)
    y -= 16

    # Gold underline
    c_obj.setStrokeColor(GOLD)
    c_obj.setLineWidth(1)
    c_obj.line(M + 22, y + 6, M + 22 + min(180, CONTENT_W - 22), y + 6)
    y -= 20

    # Body text
    _draw_wrapped_text(c_obj, slide.get("body", ""), _font("Regular", cf), 14,
                       CREAM, M + 22, y, CONTENT_W - 22, line_spacing=1.6)


def _render_stat(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool) -> None:
    """
    STAT slide — centred around one dominant stat.
    Layout: icon → stat callbox (large) → title → body
    """
    _draw_background(c_obj)
    _draw_header_bar(c_obj, slide["slide_num"], total, cf)
    _draw_footer(c_obj, cf, swipe_arrow=True)

    cx = W / 2
    y  = H - 55

    icon = slide.get("icon", "📊")
    c_obj.setFont("Helvetica", 26)
    c_obj.setFillColor(MUTED)
    c_obj.drawCentredString(cx, y, icon)
    y -= 38

    # Stat > title > body layout
    stat = slide.get("stat_callout", "")
    if stat:
        # Large centred stat — dark box
        font   = _font("Bold", cf)
        size   = 42
        pad    = 20
        tw     = c_obj.stringWidth(stat, font, size)
        bw     = min(tw + (2 * pad), CONTENT_W)
        bh     = size + (2 * pad)
        bx     = cx - bw / 2
        by     = y - bh
        c_obj.setFillColor(STAT_BG)
        c_obj.roundRect(bx, by, bw, bh, 10, fill=1, stroke=0)
        c_obj.setStrokeColor(GOLD)
        c_obj.setLineWidth(1.5)
        c_obj.roundRect(bx, by, bw, bh, 10, fill=0, stroke=1)
        c_obj.setFont(font, size)
        c_obj.setFillColor(GOLD)
        c_obj.drawCentredString(cx, by + pad + 2, stat)
        y = by - 20
    else:
        y -= 10

    # Title
    y = _draw_wrapped_text(c_obj, slide.get("title", ""), _font("Bold", cf), 20,
                            WHITE, cx, y, CONTENT_W, line_spacing=1.3, align="center")
    y -= 14

    # Body
    _draw_wrapped_text(c_obj, slide.get("body", ""), _font("Regular", cf), 13,
                       CREAM, cx, y, CONTENT_W, line_spacing=1.5, align="center")


def _render_insight(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool) -> None:
    """
    INSIGHT / IMPLICATION slide — analysis with green callout box.
    """
    _draw_background(c_obj)
    _draw_header_bar(c_obj, slide["slide_num"], total, cf)
    _draw_footer(c_obj, cf, swipe_arrow=True)

    cx = W / 2
    y  = H - 55

    # Type badge
    c_obj.setFont(_font("Bold", cf), 8)
    c_obj.setFillColor(GREEN)
    c_obj.drawCentredString(cx, y, "💡 INSIGHT")
    y -= 22

    # Title
    y = _draw_wrapped_text(c_obj, slide.get("title", ""), _font("Bold", cf), 22,
                            WHITE, cx, y, CONTENT_W, line_spacing=1.25, align="center")
    y -= 20

    # Body in green callout box
    body = slide.get("body", "")
    if body:
        _draw_green_callout(c_obj, body, M, y, CONTENT_W, cf)

    # Stat below if present
    stat = slide.get("stat_callout", "")
    if stat:
        _draw_gold_pill_stat(c_obj, stat, cx, y - (H * 0.05), cf)


def _render_tip(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool) -> None:
    """
    TIP slide — numbered checklist card.
    """
    _draw_background(c_obj)
    _draw_header_bar(c_obj, slide["slide_num"], total, cf)
    _draw_footer(c_obj, cf, swipe_arrow=True)

    y  = H - 55
    cx = W / 2

    # TIP badge + icon
    icon = slide.get("icon", "✅")
    c_obj.setFont("Helvetica", 22)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, y, icon)
    y -= 36

    c_obj.setFont(_font("Bold", cf), 9)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, y, "PRO TIP")
    y -= 24

    # Title
    y = _draw_wrapped_text(c_obj, slide.get("title", ""), _font("Bold", cf), 21,
                            WHITE, cx, y, CONTENT_W, line_spacing=1.3, align="center")
    y -= 18

    # Horizontal rule
    c_obj.setStrokeColor(MUTED)
    c_obj.setLineWidth(0.4)
    c_obj.line(M, y + 6, W - M, y + 6)
    y -= 16

    # Body text left-aligned with bullet
    body = slide.get("body", "")
    parts = [p.strip() for p in body.split(".") if p.strip()]
    for part in parts[:4]:
        # Gold bullet dot
        c_obj.setFillColor(GOLD)
        c_obj.setFont("Helvetica", 14)
        c_obj.drawString(M, y, "•")
        _draw_wrapped_text(c_obj, part + ".", _font("Regular", cf), 13, CREAM,
                           M + 16, y, CONTENT_W - 16, line_spacing=1.45)
        # Estimate height used
        lines_count = max(1, math.ceil(len(part) / 48))
        y -= lines_count * 13 * 1.45 + 8


def _render_cta(c_obj: canvas.Canvas, slide: dict, total: int, cf: bool,
                category_label: str = "") -> None:
    """
    CTA / BRAND slide — last slide. Centred brand focus + follow prompt.
    """
    _draw_background(c_obj)

    # Gold top bar — thicker on CTA
    c_obj.setFillColor(GOLD)
    c_obj.rect(0, H - 8, W, 8, fill=1, stroke=0)

    _draw_footer(c_obj, cf, swipe_arrow=False)

    cx = W / 2
    y  = H - 50

    # VB Exports brand mark (text-based logo)
    c_obj.setFont(_font("Bold", cf), 36)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, y - 10, BUSINESS_NAME.upper())
    y -= 56

    # Tagline
    c_obj.setFont(_font("Light", cf), 12)
    c_obj.setFillColor(CREAM)
    c_obj.drawCentredString(cx, y, BUSINESS_TAGLINE)
    y -= 26

    # Thin gold rule
    c_obj.setStrokeColor(GOLD)
    c_obj.setLineWidth(0.8)
    c_obj.line(cx - 100, y + 6, cx + 100, y + 6)
    y -= 22

    # Body / follow prompt
    body = slide.get("body", f"Follow {BUSINESS_NAME} for daily export insights.")
    y = _draw_wrapped_text(c_obj, body, _font("Regular", cf), 14, CREAM,
                            cx, y, CONTENT_W - 40, line_spacing=1.6, align="center")
    y -= 24

    # CTA pill buttons
    _draw_follow_cta_pill(c_obj, "Follow for Daily Insights →", cx, y, cf)
    y -= 52

    # Stat label if present
    stat = slide.get("stat_callout", "")
    if stat:
        c_obj.setFont(_font("Bold", cf), 11)
        c_obj.setFillColor(MUTED)
        c_obj.drawCentredString(cx, y, stat)


def _draw_follow_cta_pill(c_obj: canvas.Canvas, text: str, cx: float, y: float,
                           cf: bool) -> None:
    """Draws a gold outlined CTA pill."""
    font   = _font("Bold", cf)
    size   = 12
    pad_x  = 24
    pad_y  = 10
    radius = 18

    tw     = c_obj.stringWidth(text, font, size)
    pw     = min(tw + (2 * pad_x), CONTENT_W)
    ph     = size + (2 * pad_y)
    px     = cx - pw / 2
    py     = y - ph

    c_obj.setStrokeColor(GOLD)
    c_obj.setLineWidth(1.5)
    c_obj.setFillColor(BG)
    c_obj.roundRect(px, py, pw, ph, radius, fill=1, stroke=1)

    c_obj.setFont(font, size)
    c_obj.setFillColor(GOLD)
    c_obj.drawCentredString(cx, py + pad_y, text)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE ROUTER — dispatches to the correct renderer
# ══════════════════════════════════════════════════════════════════════════════

_SLIDE_RENDERERS = {
    "HOOK":        _render_hook,
    "CONTEXT":     _render_context,
    "STAT":        _render_stat,
    "INSIGHT":     _render_insight,
    "IMPLICATION": _render_insight,   # reuses insight layout
    "TIP":         _render_tip,
    "OPPORTUNITY": _render_insight,   # reuses insight layout
    "CTA":         _render_cta,
    "BRAND":       _render_cta,
}


def _render_slide(c_obj: canvas.Canvas, slide: dict, total: int,
                  cf: bool, category_label: str) -> None:
    """Routes a slide dict to the appropriate renderer."""
    slide_type = slide.get("type", "CONTEXT").upper()
    renderer   = _SLIDE_RENDERERS.get(slide_type, _render_context)

    if slide_type in ("CTA", "BRAND"):
        renderer(c_obj, slide, total, cf, category_label)
    else:
        renderer(c_obj, slide, total, cf)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def create_carousel(
    slides: list[dict],
    topic: str,
    category: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Renders a list of slide dicts into a PDF carousel file.

    Args:
        slides      : List of slide dicts from generators/content_gen.py
        topic       : Post topic (used in filename)
        category    : Schedule category (used for category label)
        output_path : Optional explicit output path; defaults to output/ dir

    Returns:
        Absolute path to the generated PDF file.
    """
    if not slides:
        raise ValueError("slides list is empty — cannot generate carousel")

    custom_fonts = _register_fonts()

    # ── Output path ────────────────────────────────────────────────────────
    if output_path is None:
        safe_topic = "".join(c for c in topic[:40] if c.isalnum() or c in " _-").strip()
        safe_topic = safe_topic.replace(" ", "_")
        output_path = str(OUTPUT_DIR / f"carousel_{safe_topic}.pdf")

    # ── Category display label ─────────────────────────────────────────────
    from config import SCHEDULE
    cat_label = ""
    for day_data in SCHEDULE.values():
        if day_data["category"] == category:
            cat_label = day_data.get("label", category.upper())
            break

    total = len(slides)
    log.info("Rendering %d slides → %s", total, output_path)

    # ── PDF canvas ─────────────────────────────────────────────────────────
    c_obj = canvas.Canvas(output_path, pagesize=CAROUSEL_PAGE_SIZE)
    c_obj.setTitle(f"{topic} — VB Exports")
    c_obj.setAuthor(BUSINESS_NAME)
    c_obj.setSubject(BUSINESS_TAGLINE)

    for slide in slides:
        _render_slide(c_obj, slide, total, custom_fonts, cat_label)
        c_obj.showPage()

    c_obj.save()

    size_kb = pathlib.Path(output_path).stat().st_size // 1024
    log.info("PDF saved: %s (%d KB, %d pages)", output_path, size_kb, total)
    return output_path
