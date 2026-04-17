"""
generators/carousel_gen_v2.py
──────────────────────────────
Pillow-based carousel renderer. Produces high-quality 1080×1350 portrait
PNG slides then assembles them into a PDF for LinkedIn upload.

Design DNA (matches reference screenshots):
  ┌─────────────────────────┐
  │   PHOTO (full-width)    │  ← 45% height
  │   gradient fade ↓ black │
  ├─────────────────────────┤
  │  HEADLINE (yellow/bold) │  ← accent color, Oswald/Montserrat
  │  • Bullet (yellow key)  │  ← alternating yellow / white
  │  • Bullet (white desc)  │
  │  ...                    │
  ├─────────────────────────┤
  │ [avatar] Name  |  CTA > │  ← footer bar
  └─────────────────────────┘

All colors, layout variant, photo style, and headline alignment are driven
by the Theme object from theme_engine.py — enabling 384 unique visual
combinations that rotate automatically by date.

Layout variants:
  CLASSIC : Photo 45%, headline + 5 bullets
  BOLD    : Photo 35%, massive 3-line headline, 2-3 bullets
  DATA    : Photo 40%, 3 stat blocks, smaller bullets
  STORY   : Photo 55%, narrative paragraph (no bullets)
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import textwrap
import time
import urllib.request
from typing import Optional

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from generators.theme_engine import Theme, get_theme
from config import OUTPUT_DIR, FONTS_DIR, ASSETS_DIR

log = logging.getLogger(__name__)

# ── Canvas dimensions ─────────────────────────────────────────────────────────
W, H         = 1080, 1350      # 4:5 portrait — native LinkedIn + Instagram format
PHOTO_RATIOS = {               # fraction of H for photo area per layout
    "CLASSIC": 0.45,
    "BOLD":    0.35,
    "DATA":    0.40,
    "STORY":   0.55,
}
MARGIN       = 54              # left/right margin in px
FOOTER_H     = 100             # footer bar height in px

# ── Font paths ────────────────────────────────────────────────────────────────
FONT_OSWALD_BOLD    = FONTS_DIR / "Oswald-Bold.ttf"
FONT_MONTSERRAT_BD  = FONTS_DIR / "Montserrat-Bold.ttf"
FONT_MONTSERRAT_REG = FONTS_DIR / "Montserrat-Regular.ttf"
FONT_MONTSERRAT_LT  = FONTS_DIR / "Montserrat-Light.ttf"

# Photo cache dir (auto-created)
PHOTO_CACHE_DIR = ASSETS_DIR / "photo_cache"
PHOTO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Avatar images cache ───────────────────────────────────────────────────────
_AVATAR_CACHE: dict[str, Image.Image] = {}


# ══════════════════════════════════════════════════════════════════════════════
# Font loader
# ══════════════════════════════════════════════════════════════════════════════

def _load_font(size: int, bold: bool = False, light: bool = False) -> ImageFont.FreeTypeFont:
    """Load custom font with fallback to default."""
    candidates = []
    if bold:
        candidates = [FONT_OSWALD_BOLD, FONT_MONTSERRAT_BD]
    elif light:
        candidates = [FONT_MONTSERRAT_LT, FONT_MONTSERRAT_REG]
    else:
        candidates = [FONT_MONTSERRAT_REG, FONT_MONTSERRAT_BD]

    for path in candidates:
        if pathlib.Path(path).exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue

    # Final fallback — PIL default (no custom style)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ══════════════════════════════════════════════════════════════════════════════
# Photo fetcher (Unsplash Source API — no key required)
# ══════════════════════════════════════════════════════════════════════════════

# ── Picsum photo pool per category (deterministic, curated for coffee/trade) ─
# Picsum IDs confirmed to be high-quality photos suitable per theme.
# IDs rotate by slide number so every slide in a carousel has a different photo.
_PICSUM_POOLS: dict[str, list[int]] = {
    "coffee_market":    [431, 225, 399, 542, 539, 634, 672, 700, 765],
    "global_buyers":    [290, 293, 325, 386, 392, 445, 450, 503, 580],
    "personal_journey": [417, 397, 372, 355, 338, 315, 294, 270, 248],
    "personal_lesson":  [612, 583, 552, 534, 513, 485, 462, 437, 412],
    "personal_origin":  [431, 416, 388, 363, 344, 322, 301, 280, 257],
    "farm_origin":      [429, 421, 404, 381, 357, 333, 310, 287, 261],
    "price_trends":     [281, 298, 319, 337, 356, 374, 393, 411, 430],
    "export_compliance":[200, 222, 244, 267, 291, 312, 330, 351, 371],
    "export_guide":     [324, 346, 368, 390, 413, 435, 457, 479, 501],
    "_default":         [431, 225, 399, 542, 539, 634, 672, 700, 765],
}


def _fetch_photo(keywords: list[str], width: int, height: int,
                 slide_index: int = 0, category: str = "_default") -> Image.Image:
    """
    Downloads a relevant stock photo.

    Strategy:
    1. Use Picsum Photos (picsum.photos) with curated category IDs —
       deterministic, always works, no API key, proxy-safe.
    2. Cache for 7 days per (picsum_id, width, height).
    3. Gradient placeholder if download fails.
    """
    # Pick Picsum ID: category pool → slot by slide index
    pool     = _PICSUM_POOLS.get(category, _PICSUM_POOLS["_default"])
    pic_id   = pool[slide_index % len(pool)]
    cache_key = f"picsum_{pic_id}_{width}x{height}"
    cache_path = PHOTO_CACHE_DIR / f"{cache_key}.jpg"

    # Use cache if < 7 days old
    if cache_path.exists():
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days < 7:
            try:
                return Image.open(cache_path).convert("RGB")
            except Exception:
                cache_path.unlink(missing_ok=True)

    # Download from Picsum (specific image ID, exact dimensions)
    url = f"https://picsum.photos/id/{pic_id}/{width}/{height}"
    try:
        resp = requests.get(url, timeout=15, verify=False, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5_000:
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            img = img.resize((width, height), Image.LANCZOS)
            img.save(cache_path, "JPEG", quality=92)
            log.info("Photo fetched: picsum/%d (%d bytes)", pic_id, len(resp.content))
            return img
    except Exception as e:
        log.debug("Picsum download failed (id=%d): %s", pic_id, e)

    # Gradient placeholder if all downloads failed
    log.warning("Photo unavailable for slide %d — using gradient placeholder", slide_index + 1)
    return _make_gradient_placeholder(width, height)


def _make_gradient_placeholder(width: int, height: int) -> Image.Image:
    """Simple dark gradient placeholder when no photo is available."""
    img = Image.new("RGB", (width, height), (20, 10, 5))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(60 * (1 - ratio) + 10 * ratio)
        g = int(30 * (1 - ratio) + 5 * ratio)
        b = int(10 * (1 - ratio) + 2 * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


# ══════════════════════════════════════════════════════════════════════════════
# Avatar loader
# ══════════════════════════════════════════════════════════════════════════════

def _get_avatar(account: dict) -> Image.Image:
    """Returns a circular avatar image for the footer."""
    avatar_path = account.get("avatar_path", "")
    cache_key   = str(avatar_path)

    if cache_key in _AVATAR_CACHE:
        return _AVATAR_CACHE[cache_key]

    size = 72
    avatar = None

    # Try loading from local file path
    if avatar_path and pathlib.Path(avatar_path).exists():
        try:
            avatar = Image.open(avatar_path).convert("RGBA")
        except Exception:
            pass

    # Try downloading from URL
    if avatar is None:
        avatar_url = account.get("avatar_url", "")
        if avatar_url:
            try:
                resp = requests.get(avatar_url, timeout=10, verify=False)
                if resp.ok:
                    avatar = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            except Exception:
                pass

    # Fallback: monogram circle
    if avatar is None:
        avatar = _make_monogram(account.get("monogram", "VB"), size, account.get("accent_rgb", (200, 150, 30)))

    # Crop to circle
    avatar = avatar.resize((size, size), Image.LANCZOS)
    mask   = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(avatar, (0, 0), mask)

    _AVATAR_CACHE[cache_key] = result
    return result


def _make_monogram(text: str, size: int, color: tuple[int, int, int]) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (*color, 255))
    draw = ImageDraw.Draw(img)
    font = _load_font(size // 3, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - 2), text, fill=(255, 255, 255, 255), font=font)
    return img


# ══════════════════════════════════════════════════════════════════════════════
# Core drawing utilities
# ══════════════════════════════════════════════════════════════════════════════

def _draw_photo_with_gradient(img: Image.Image, photo: Image.Image,
                               photo_h: int, theme: Theme) -> None:
    """Pastes photo into top portion with a smooth gradient fade to bg color."""
    # Scale photo to fill full width x photo_h
    photo_scaled = photo.resize((W, photo_h), Image.LANCZOS)
    img.paste(photo_scaled, (0, 0))

    # Gradient overlay: transparent at top → opaque bg_color at photo_h
    overlay = Image.new("RGBA", (W, photo_h), (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    bg_r, bg_g, bg_b = theme.bg_rgb

    grad_start = int(photo_h * (1 - theme.photo_overlay_alpha))
    for y in range(grad_start, photo_h):
        alpha = int(255 * (y - grad_start) / max(photo_h - grad_start, 1))
        draw.line([(0, y), (W, y)], fill=(bg_r, bg_g, bg_b, alpha))

    img.paste(overlay, (0, 0), overlay)


def _draw_text_wrapped(draw: ImageDraw.ImageDraw, text: str, x: float, y: float,
                        max_width: float, font: ImageFont.FreeTypeFont,
                        color: tuple, align: str = "left",
                        line_spacing: float = 1.35) -> float:
    """
    Wraps text to max_width and draws it. Returns the Y position after last line.
    """
    if not text:
        return y

    # Estimate char width for wrapping
    try:
        sample_bbox = draw.textbbox((0, 0), "A", font=font)
        char_w = max(sample_bbox[2] - sample_bbox[0], 1)
    except Exception:
        char_w = font.size * 0.6

    chars_per_line = max(int(max_width / char_w), 10)
    lines = []
    for paragraph in text.split("\n"):
        wrapped = textwrap.wrap(paragraph, width=chars_per_line) or [""]
        lines.extend(wrapped)

    try:
        bbox   = draw.textbbox((0, 0), "Ay", font=font)
        line_h = (bbox[3] - bbox[1]) * line_spacing
    except Exception:
        line_h = font.size * line_spacing

    cur_y = y
    for line in lines:
        if align == "center":
            try:
                bbox = draw.textbbox((0, 0), line, font=font)
                lw   = bbox[2] - bbox[0]
                lx   = x + (max_width - lw) / 2
            except Exception:
                lx = x
        else:
            lx = x

        draw.text((lx, cur_y), line, font=font, fill=color)
        cur_y += line_h

    return cur_y


def _draw_pill_button(img: Image.Image, text: str, rx: int, cy: int,
                       accent_rgb: tuple, font: ImageFont.FreeTypeFont) -> None:
    """Draws a rounded-rectangle pill button (right-aligned)."""
    draw     = ImageDraw.Draw(img)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * 14, 28

    pad_x, pad_y = 28, 14
    btn_w = tw + pad_x * 2
    btn_h = th + pad_y * 2
    x0    = rx - btn_w
    y0    = cy - btn_h // 2
    x1    = rx
    y1    = cy + btn_h // 2
    radius = btn_h // 2

    # Background pill — dark with accent border
    mask = Image.new("RGBA", (btn_w + 4, btn_h + 4), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((2, 2, btn_w + 1, btn_h + 1), radius=radius,
                             fill=(*accent_rgb, 30), outline=(*accent_rgb, 255), width=2)
    img.paste(mask, (x0 - 2, y0 - 2), mask)
    draw.text((x0 + pad_x, y0 + pad_y), text, font=font, fill=accent_rgb)


def _draw_stat_block(draw: ImageDraw.ImageDraw, stat: str, label: str,
                      cx: int, y: int, width: int, theme: Theme) -> int:
    """Draws a centered stat block (number + label). Returns bottom y."""
    # Stat number — large accent color
    num_font = _load_font(72, bold=True)
    lbl_font = _load_font(28)
    sep_font = _load_font(22)

    try:
        nb = draw.textbbox((0, 0), stat, font=num_font)
        nw = nb[2] - nb[0]
        nh = nb[3] - nb[1]
    except Exception:
        nw, nh = len(stat) * 40, 72

    nx = cx - nw // 2
    draw.text((nx, y), stat, font=num_font, fill=theme.accent_rgb)
    y += nh + 8

    # Thin separator line in accent
    lx = cx - width // 4
    draw.line([(lx, y), (cx + width // 4, y)], fill=theme.accent_rgb, width=2)
    y += 12

    # Label
    try:
        lb = draw.textbbox((0, 0), label, font=lbl_font)
        lw = lb[2] - lb[0]
    except Exception:
        lw = len(label) * 16
    draw.text((cx - lw // 2, y), label, font=lbl_font, fill=theme.white_rgb)
    y += 38

    return y


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT RENDERERS  (one per layout variant)
# ══════════════════════════════════════════════════════════════════════════════

def _render_classic(img: Image.Image, draw: ImageDraw.ImageDraw, slide: dict,
                    photo_h: int, theme: Theme, account: dict) -> None:
    """
    CLASSIC layout: headline + alternating-color bullet list.
    Matches the reference screenshots exactly.
    """
    align = theme.headline_align
    y     = photo_h + 36

    # Headline
    title      = slide.get("title", "")
    title_font = _load_font(72, bold=True)
    title_color = theme.accent_rgb
    y = _draw_text_wrapped(draw, title, MARGIN, y, W - 2 * MARGIN,
                            title_font, title_color, align=align, line_spacing=1.2)
    y += 28

    # Body as alternating bullets
    body  = slide.get("body", "")
    lines = [ln.strip().lstrip("•-– ").strip() for ln in body.split("\n") if ln.strip()]

    # If body is not pre-bulleted, wrap to ~50 chars and split
    if len(lines) <= 1 and lines:
        lines = textwrap.wrap(lines[0], 50) if lines else []

    bullet_font_yl  = _load_font(36, bold=False)   # yellow lines
    bullet_font_wh  = _load_font(36, bold=False)   # white lines

    max_bullets = 5
    for i, line in enumerate(lines[:max_bullets]):
        color = theme.accent_rgb if i % 2 == 1 else theme.white_rgb
        bfont = bullet_font_yl if i % 2 == 1 else bullet_font_wh

        # Bullet dot
        draw.text((MARGIN, y + 4), "•", font=bfont, fill=color)
        y = _draw_text_wrapped(draw, line, MARGIN + 38, y, W - 2 * MARGIN - 38,
                                bfont, color, align="left", line_spacing=1.25)
        y += 10

    # Optional stat callout pill (bottom of content area)
    stat = slide.get("stat_callout", "")
    if stat and y < H - FOOTER_H - 80:
        y += 18
        pill_font = _load_font(40, bold=True)
        try:
            pb = draw.textbbox((0, 0), stat, font=pill_font)
            pw = pb[2] - pb[0]
        except Exception:
            pw = len(stat) * 22
        px = MARGIN
        py = y
        draw.rounded_rectangle([px - 8, py - 8, px + pw + 24, py + 52],
                                radius=12, outline=theme.accent_rgb, width=3)
        draw.text((px + 8, py), stat, font=pill_font, fill=theme.accent_rgb)


def _render_bold(img: Image.Image, draw: ImageDraw.ImageDraw, slide: dict,
                 photo_h: int, theme: Theme, account: dict) -> None:
    """BOLD layout: massive 3-line headline, 2-3 bullets maximum."""
    align = theme.headline_align
    y     = photo_h + 28

    title_font  = _load_font(90, bold=True)
    title_color = theme.accent_rgb
    y = _draw_text_wrapped(draw, slide.get("title", ""), MARGIN, y,
                            W - 2 * MARGIN, title_font, title_color,
                            align=align, line_spacing=1.15)
    y += 32

    # Thin accent rule
    draw.line([(MARGIN, y), (W - MARGIN, y)], fill=theme.accent_rgb, width=3)
    y += 24

    # Up to 3 bullets, white only
    body  = slide.get("body", "")
    lines = [ln.strip().lstrip("•-– ").strip() for ln in body.split("\n") if ln.strip()]
    if len(lines) <= 1 and lines:
        lines = textwrap.wrap(lines[0], 55) if lines else []

    font = _load_font(32)
    for line in lines[:3]:
        draw.text((MARGIN, y + 4), "▸", font=font, fill=theme.accent_rgb)
        y = _draw_text_wrapped(draw, line, MARGIN + 36, y, W - 2 * MARGIN - 36,
                                font, theme.white_rgb, line_spacing=1.3)
        y += 12


def _render_data(img: Image.Image, draw: ImageDraw.ImageDraw, slide: dict,
                 photo_h: int, theme: Theme, account: dict) -> None:
    """DATA layout: 3 large stat blocks + smaller bullet list."""
    y = photo_h + 28

    # Headline (smaller than CLASSIC)
    title_font = _load_font(56, bold=True)
    y = _draw_text_wrapped(draw, slide.get("title", ""), MARGIN, y,
                            W - 2 * MARGIN, title_font, theme.accent_rgb,
                            align=theme.headline_align, line_spacing=1.2)
    y += 20

    # Parse stat_callout and body for stats
    # Format expected: "stat1|label1||stat2|label2||stat3|label3"
    stat_str = slide.get("stat_callout", "")
    stats    = []
    if "|" in stat_str:
        parts = stat_str.split("||")
        for p in parts[:3]:
            s = p.split("|")
            if len(s) >= 2:
                stats.append((s[0].strip(), s[1].strip()))

    # Fallback: extract numbers from body
    if not stats:
        import re
        body   = slide.get("body", "")
        nums   = re.findall(r'[\$₹]?[\d,\.]+\s*(?:Cr|MT|Bn|M|K|%|B|billion|million)?', body)
        labels = re.findall(r'(?:export|volume|value|growth|share|buyers?)\s*\w*', body, re.I)
        for i in range(min(3, len(nums))):
            lbl = labels[i] if i < len(labels) else "Stat"
            stats.append((nums[i], lbl[:15]))

    if not stats:
        stats = [("430K MT", "Coffee Exports"), ("$5.7B", "Export Value"), ("+18%", "YoY Growth")]

    # Draw 3 stat blocks side by side
    stat_y    = y
    col_w     = (W - 2 * MARGIN) // 3
    max_stat_y = stat_y
    for i, (stat_num, stat_lbl) in enumerate(stats[:3]):
        cx      = MARGIN + col_w * i + col_w // 2
        bottom  = _draw_stat_block(draw, stat_num, stat_lbl, cx, stat_y, col_w, theme)
        max_stat_y = max(max_stat_y, bottom)

    y = max_stat_y + 24

    # Separator
    draw.line([(MARGIN, y), (W - MARGIN, y)], fill=theme.accent_rgb, width=2)
    y += 20

    # Small bullets from body
    body  = slide.get("body", "")
    lines = [ln.strip().lstrip("•-– ").strip() for ln in body.split("\n") if ln.strip()]
    if len(lines) <= 1 and lines:
        lines = textwrap.wrap(lines[0], 60) if lines else []

    font = _load_font(30)
    for line in lines[:3]:
        draw.text((MARGIN, y + 2), "•", font=font, fill=theme.accent_rgb)
        y = _draw_text_wrapped(draw, line, MARGIN + 32, y, W - 2 * MARGIN - 32,
                                font, theme.white_rgb, line_spacing=1.25)
        y += 8


def _render_story(img: Image.Image, draw: ImageDraw.ImageDraw, slide: dict,
                  photo_h: int, theme: Theme, account: dict) -> None:
    """STORY layout: immersive photo, narrative paragraph, no bullets."""
    y = photo_h + 28

    # Italic tagline in accent (slide type label)
    tag_font = _load_font(30, light=True)
    tag      = f"— {slide.get('type', 'INSIGHT').capitalize()}"
    draw.text((MARGIN, y), tag, font=tag_font, fill=theme.subtitle_rgb)
    y += 46

    # Headline
    title_font = _load_font(64, bold=True)
    y = _draw_text_wrapped(draw, slide.get("title", ""), MARGIN, y,
                            W - 2 * MARGIN, title_font, theme.accent_rgb,
                            align=theme.headline_align, line_spacing=1.18)
    y += 24

    # Thin rule
    draw.line([(MARGIN, y), (MARGIN + 120, y)], fill=theme.accent_rgb, width=4)
    y += 20

    # Body as flowing paragraph (no bullets)
    body = slide.get("body", "").replace("•", "").replace("-", "").strip()
    body_font = _load_font(34)
    y = _draw_text_wrapped(draw, body, MARGIN, y, W - 2 * MARGIN,
                            body_font, theme.white_rgb, line_spacing=1.45)


# ══════════════════════════════════════════════════════════════════════════════
# Footer renderer
# ══════════════════════════════════════════════════════════════════════════════

def _render_footer(img: Image.Image, theme: Theme, account: dict,
                   slide_num: int, total: int, is_first: bool) -> None:
    """
    Draws footer bar at fixed bottom of slide.
    Left side: circular avatar + name + title
    Right side: "Swipe to know >>>" pill OR slide counter
    """
    draw   = ImageDraw.Draw(img)
    footer_y = H - FOOTER_H

    # Thin separator line at top of footer
    draw.line([(MARGIN, footer_y), (W - MARGIN, footer_y)],
              fill=(*theme.accent_rgb[:3], 80), width=1)

    # Avatar
    avatar = _get_avatar({**account, "accent_rgb": theme.accent_rgb})
    av_y   = footer_y + (FOOTER_H - 72) // 2
    img.paste(avatar, (MARGIN, av_y), avatar)

    # Name + title text
    name_font  = _load_font(28, bold=True)
    title_font = _load_font(24, light=True)
    name_x     = MARGIN + 80
    name_y     = footer_y + 16
    draw.text((name_x, name_y), account.get("footer_name", "VB Exports"),
              font=name_font, fill=theme.accent_rgb)
    draw.text((name_x, name_y + 34), account.get("footer_title", "Premium Indian Coffee"),
              font=title_font, fill=(*theme.subtitle_rgb[:3],))

    # Right: CTA pill on first slide, slide counter on others
    pill_font = _load_font(26, bold=True)
    if is_first:
        cta_text = "Swipe to know  ❯❯❯"
        _draw_pill_button(img, cta_text, W - MARGIN, footer_y + FOOTER_H // 2,
                          theme.accent_rgb, pill_font)
    else:
        counter = f"{slide_num} / {total}"
        try:
            cb    = draw.textbbox((0, 0), counter, font=pill_font)
            cw    = cb[2] - cb[0]
        except Exception:
            cw = len(counter) * 16
        draw.text((W - MARGIN - cw, footer_y + FOOTER_H // 2 - 14),
                  counter, font=pill_font, fill=theme.subtitle_rgb)


# ══════════════════════════════════════════════════════════════════════════════
# Slide type routing
# ══════════════════════════════════════════════════════════════════════════════

def _render_cta_slide(img: Image.Image, draw: ImageDraw.ImageDraw, slide: dict,
                      photo_h: int, theme: Theme, account: dict) -> None:
    """Special CTA/BRAND slide — follow prompt + contact."""
    y = photo_h + 36

    # Large brand name
    brand_font = _load_font(80, bold=True)
    brand_name = account.get("brand_name", "VB Exports")
    y = _draw_text_wrapped(draw, brand_name, MARGIN, y, W - 2 * MARGIN,
                            brand_font, theme.accent_rgb,
                            align=theme.headline_align, line_spacing=1.1)
    y += 16

    # Tagline
    tag_font = _load_font(34, light=True)
    tagline  = account.get("tagline", "Premium Indian Coffee | Karnataka, India")
    y = _draw_text_wrapped(draw, tagline, MARGIN, y, W - 2 * MARGIN,
                            tag_font, theme.subtitle_rgb,
                            align=theme.headline_align, line_spacing=1.3)
    y += 28

    # Accent rule
    mid = W // 2
    draw.line([(mid - 100, y), (mid + 100, y)], fill=theme.accent_rgb, width=3)
    y += 32

    # Follow CTA
    cta_font = _load_font(36)
    cta_text = slide.get("body", f"Follow {brand_name} for daily coffee trade insights.")
    y = _draw_text_wrapped(draw, cta_text, MARGIN, y, W - 2 * MARGIN,
                            cta_font, theme.white_rgb,
                            align="center", line_spacing=1.4)


LAYOUT_RENDERERS = {
    "CLASSIC": _render_classic,
    "BOLD":    _render_bold,
    "DATA":    _render_data,
    "STORY":   _render_story,
}

HOOK_SLIDE_TYPES  = {"HOOK"}
BRAND_SLIDE_TYPES = {"CTA", "BRAND"}


# ══════════════════════════════════════════════════════════════════════════════
# Main slide renderer
# ══════════════════════════════════════════════════════════════════════════════

def _render_slide(slide: dict, slide_num: int, total: int,
                  theme: Theme, account: dict, category: str) -> Image.Image:
    """Render a single slide as a 1080×1350 PIL Image."""
    # Base canvas — bg_color
    img  = Image.new("RGB", (W, H), theme.bg_rgb)
    draw = ImageDraw.Draw(img)

    # Determine photo height for this layout
    layout  = theme.layout
    ratio   = PHOTO_RATIOS.get(layout, 0.45)
    photo_h = int(H * ratio)

    # Fetch and composite photo (slide_num-1 = 0-based index for pool rotation)
    keywords = theme.photo_keywords(category)
    photo    = _fetch_photo(keywords, W, photo_h,
                            slide_index=slide_num - 1, category=category)
    _draw_photo_with_gradient(img, photo, photo_h, theme)

    # Slide-type routing
    stype = slide.get("type", "CONTEXT").upper()

    if stype in BRAND_SLIDE_TYPES:
        _render_cta_slide(img, draw, slide, photo_h, theme, account)
    else:
        renderer = LAYOUT_RENDERERS.get(layout, _render_classic)
        renderer(img, draw, slide, photo_h, theme, account)

    # Footer
    is_first = slide_num == 1
    _render_footer(img, theme, account, slide_num, total, is_first)

    return img


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def create_carousel_v2(
    slides:   list[dict],
    topic:    str,
    category: str,
    account:  dict,
    theme:    Optional[Theme] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Renders a full carousel and saves it as a PDF.

    Args:
        slides      : Generated slide dicts from content_gen
        topic       : Post topic (used for filename)
        category    : Schedule category (coffee_market, etc.)
        account     : Account profile dict from config.ACCOUNT_PROFILES
        theme       : Theme object (defaults to today's theme)
        output_path : Optional explicit output path

    Returns:
        Absolute path to the generated PDF file.
    """
    if theme is None:
        theme = get_theme()

    log.info("Rendering v2 carousel | layout=%s | palette=%s | photo=%s",
             theme.layout, theme.palette_name, theme.photo_style)

    # Render each slide to PNG bytes
    png_images: list[bytes] = []
    total = len(slides)

    for slide in slides:
        slide_num = slide.get("slide_num", slides.index(slide) + 1)
        img       = _render_slide(slide, slide_num, total, theme, account, category)

        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=False)
        png_images.append(buf.getvalue())
        log.info("  Slide %d/%d rendered (%d bytes)", slide_num, total, len(png_images[-1]))

    # Determine output path
    if output_path is None:
        safe_topic = "".join(c if c.isalnum() or c in "_ " else "" for c in topic)[:45]
        safe_topic = safe_topic.replace(" ", "_")
        acct_label = account.get("key", "personal")
        output_path = str(OUTPUT_DIR / f"carousel_{acct_label}_{safe_topic}.pdf")

    # Assemble PNG list into PDF
    try:
        import img2pdf
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(png_images))
        log.info("PDF assembled (img2pdf): %s (%d pages, %.0f KB)",
                 output_path, len(png_images), pathlib.Path(output_path).stat().st_size / 1024)
    except ImportError:
        # Fallback: save as multi-page PDF using Pillow directly
        log.warning("img2pdf not installed — using Pillow save fallback")
        pil_images = [Image.open(io.BytesIO(b)).convert("RGB") for b in png_images]
        first = pil_images[0]
        rest  = pil_images[1:]
        first.save(output_path, "PDF", save_all=True, append_images=rest,
                   resolution=144.0, optimize=False)
        log.info("PDF assembled (Pillow): %s (%d pages, %.0f KB)",
                 output_path, len(png_images), pathlib.Path(output_path).stat().st_size / 1024)

    return output_path
