"""
generators/slide_renderer.py — Playwright + Jinja2 HTML→PNG carousel renderer.

Renders each slide as 1080×1350 px PNG using Microsoft Edge (Chromium engine),
assembles into a branded PDF via img2pdf.
"""

from __future__ import annotations

import base64
import io
import logging
import pathlib
import re
import urllib.parse
import urllib.request
from typing import Any

import img2pdf
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import textwrap

from config import OUTPUT_DIR, ASSETS_DIR
from config_carousel import BRAND, FOOTER, EDGE_PATH, get_carousel_theme, get_pdf_filename, get_personal_palette
from generators.image_gen import generate_slide_image

log = logging.getLogger(__name__)

TEMPLATES_DIR = ASSETS_DIR / "templates"

_jinja_env = None


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
        )
    return _jinja_env


# ── Fix 1a: Convert local file:// URI → base64 data URI ──────────────────────
# Playwright's set_content() runs in about:blank context — Chromium blocks
# file:// image loads from about:blank as a cross-origin violation.
# Encoding as data URI embeds the image bytes directly in the HTML string.
_photo_b64_cache: dict[str, str] = {}


def _file_uri_to_data_uri(uri: str) -> str:
    """Converts a local file:// URI or path to an inline base64 data URI."""
    if not uri:
        return ""
    if uri.startswith("data:"):
        return uri  # already a data URI
    if uri in _photo_b64_cache:
        return _photo_b64_cache[uri]
    try:
        if uri.startswith("file:///"):
            path = urllib.request.url2pathname(urllib.parse.urlparse(uri).path)
        else:
            path = uri
        img_bytes = pathlib.Path(path).read_bytes()
        ext  = pathlib.Path(path).suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        result = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
        _photo_b64_cache[uri] = result
        return result
    except Exception as e:
        log.warning("Photo encode failed for %s: %s", str(uri)[:60], e)
        return ""


# ── Fix 1b: Circular logo via Pillow — crop once, cache as base64 PNG ────────
_logo_circle_data_uri: str | None = None


def _get_logo_circle_data_uri() -> str:
    """
    Returns a base64 data URI of the VB Exports logo cropped to a perfect circle.
    Uses Pillow LANCZOS anti-aliasing for smooth edges. Cached after first call.
    """
    global _logo_circle_data_uri
    if _logo_circle_data_uri is not None:
        return _logo_circle_data_uri

    logo_src = pathlib.Path(BRAND["logo_cache"])
    circle_cache = logo_src.parent / "vb_logo_circle.png"

    # Re-use cached circle PNG if it exists
    if circle_cache.exists():
        circle_bytes = circle_cache.read_bytes()
        _logo_circle_data_uri = f"data:image/png;base64,{base64.b64encode(circle_bytes).decode()}"
        return _logo_circle_data_uri

    # Download source logo if needed
    if not logo_src.exists():
        try:
            req = urllib.request.Request(
                BRAND["logo_url"],
                headers={"User-Agent": "Mozilla/5.0 VBExports-Automation/3.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                logo_src.parent.mkdir(parents=True, exist_ok=True)
                logo_src.write_bytes(resp.read())
            log.info("Logo downloaded: %s", logo_src)
        except Exception as e:
            log.warning("Logo download failed: %s", e)
            _logo_circle_data_uri = ""
            return ""

    # Build circular PNG with Pillow
    try:
        from PIL import Image, ImageDraw

        SIZE = 120  # 2× target (60px) for crisp anti-aliasing

        img = Image.open(logo_src).convert("RGBA")

        # Square-crop to the center (so circle captures the logo, not whitespace)
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top  = (h - side) // 2
        img  = img.crop((left, top, left + side, top + side))

        # Resize to target
        img = img.resize((SIZE, SIZE), Image.LANCZOS)

        # Create circular alpha mask
        mask = Image.new("L", (SIZE, SIZE), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([0, 0, SIZE - 1, SIZE - 1], fill=255)

        # Apply mask
        result = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        result.paste(img, (0, 0))
        result.putalpha(mask)

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        circle_bytes = buf.getvalue()
        circle_cache.write_bytes(circle_bytes)

        log.info("Circular logo created: %s (%d bytes)", circle_cache, len(circle_bytes))
        _logo_circle_data_uri = f"data:image/png;base64,{base64.b64encode(circle_bytes).decode()}"
        return _logo_circle_data_uri

    except ImportError:
        log.warning("Pillow not installed — falling back to rectangular logo")
    except Exception as e:
        log.warning("Circular logo creation failed: %s", e)

    # Fallback: rectangular logo as-is
    try:
        img_bytes = logo_src.read_bytes()
        _logo_circle_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode()}"
    except Exception:
        _logo_circle_data_uri = ""
    return _logo_circle_data_uri


# ─────────────────────────────────────────────────────────────────────────────
# Clickable PDF link annotations (URI overlays on the PNG-based PDF)
# Since slides are Playwright screenshots, HTML <a> links are lost.
# PyMuPDF overlays invisible rectangles so PDF viewers open URLs on click/tap.
# ─────────────────────────────────────────────────────────────────────────────
_WEBSITE_URL      = "https://vb-exports.com/"
_WHATSAPP_URL     = (
    "https://wa.me/919449522395"
    "?text=Hi%20VB%20Exports%2C%20I%20am%20interested%20in%20sourcing"
    "%20premium%20Indian%20coffee.%20Please%20share%20your%20catalogue%20and%20pricing%20details."
)
_EMAIL_URL        = (
    "mailto:info@vb-exports.com"
    "?subject=Coffee%20Sourcing%20Enquiry"
    "&body=Hi%20VB%20Exports%2C%0A%0A"
    "I%20am%20interested%20in%20sourcing%20premium%20Indian%20coffee.%0A"
    "Please%20share%20your%20catalogue%20and%20pricing%20details."
)
_LINKEDIN_PERSONAL = "https://www.linkedin.com/in/bharath-s-672923383"
_LINKEDIN_COMPANY  = "https://www.linkedin.com/company/vb-exports"


def _add_pdf_links(pdf_path: str, total_slides: int, is_personal: bool) -> None:
    """
    Post-processes the assembled PDF to add invisible clickable URI annotations.

    Layout coordinates (as fractions of page W/H) are based on the fixed
    template dimensions (1080x1350px) shared by all slide templates:
      - Footer right column (every slide):  website URL + WhatsApp number
      - CTA slide last card row:            LinkedIn, Email, WhatsApp, Website
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("PyMuPDF not installed — clickable PDF links skipped")
        return

    linkedin_url = _LINKEDIN_PERSONAL if is_personal else _LINKEDIN_COMPANY

    doc = fitz.open(pdf_path)
    for page_idx, page in enumerate(doc):
        W = page.rect.width
        H = page.rect.height
        is_cta = (page_idx == total_slides - 1)

        # ── Footer: website + WhatsApp on EVERY slide ───────────────────────────
        # Personal footer: 88px  → top at 93.5% | Company footer: 110px → 91.9%
        # Use 91% as a safe floor that covers both templates.
        ft   = H * 0.910               # footer top
        fmid = ft + (H - ft) * 0.52   # splits website row / phone row

        # Website URL — right portion of footer, top row
        page.insert_link({"kind": fitz.LINK_URI,
                           "from": fitz.Rect(W * 0.52, ft, W * 0.98, fmid),
                           "uri":  _WEBSITE_URL})
        # WhatsApp with pre-filled message — right portion of footer, bottom row
        page.insert_link({"kind": fitz.LINK_URI,
                           "from": fitz.Rect(W * 0.52, fmid, W * 0.98, H * 0.997),
                           "uri":  _WHATSAPP_URL})

        # ── CTA slide: contact card links ──────────────────────────────────
        if is_cta:
            # Photo zone ends at: personal ~26% (350/1350), company ~33% (450/1350)
            # Cards start after badge + headline + divider block (~12% further)
            photo_end  = 0.26 if is_personal else 0.33
            cards_top  = photo_end + 0.125
            cards_bot  = 0.905   # just above footer
            slot       = (cards_bot - cards_top) / 5   # 4 cards + fp-strip

            cta_links = [
                (cards_top + slot * 0, cards_top + slot * 1, linkedin_url),   # LinkedIn
                (cards_top + slot * 1, cards_top + slot * 2, _EMAIL_URL),     # Email
                (cards_top + slot * 2, cards_top + slot * 3, _WHATSAPP_URL),  # WhatsApp
                (cards_top + slot * 3, cards_top + slot * 4, _WEBSITE_URL),   # Website
            ]
            for tf, bf, url in cta_links:
                page.insert_link({"kind": fitz.LINK_URI,
                                   "from": fitz.Rect(W * 0.04, H * tf, W * 0.96, H * bf),
                                   "uri":  url})

    # Atomically replace original PDF with the annotated version
    tmp = pdf_path + ".linked.pdf"
    doc.save(tmp)
    doc.close()
    pathlib.Path(tmp).replace(pathlib.Path(pdf_path))
    log.info("Clickable links added to PDF: %s", pathlib.Path(pdf_path).name)


def render_carousel(
    slides: list[dict[str, Any]],
    category: str,
    topic: str,
    account: dict,
    photo_urls: list[str],
) -> str:
    """
    Renders all slides via Playwright + Jinja2 and assembles into a PDF.

    Returns: Absolute path to the generated PDF file.
    """
    from datetime import datetime
    import pytz

    theme = get_carousel_theme(category)
    jinja = _get_jinja()
    logo_circle_data_uri = _get_logo_circle_data_uri()

    today = datetime.now(pytz.timezone("Asia/Kolkata"))

    # Weekday palette — personal templates only; company templates ignore this
    is_personal_template = theme.get("template", "").startswith("slide_personal")
    personal_palette = get_personal_palette(today.strftime("%A")) if is_personal_template else {}
    month = today.strftime("%b")
    year  = today.strftime("%Y")

    pdf_filename = get_pdf_filename(category, month, year)
    pdf_path = str(OUTPUT_DIR / pdf_filename)

    total_slides = len(slides)
    png_paths: list[str] = []

    log.info("Rendering %d slides | category=%s | template=%s", total_slides, category, theme["template"])

    with sync_playwright() as pw:
        # Browser selection:
        #   Windows (local dev): use Microsoft Edge for best font rendering
        #   Linux (GitHub Actions): Edge is unavailable — use Playwright's Chromium
        import platform
        use_edge = False
        edge = EDGE_PATH
        if platform.system() == "Windows":
            if not pathlib.Path(edge).exists():
                edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
            if pathlib.Path(edge).exists():
                use_edge = True

        if use_edge:
            browser = pw.chromium.launch(
                executable_path=edge,
                channel="msedge",
                args=["--disable-gpu"],
            )
        else:
            # GitHub Actions / Linux: use Playwright's bundled Chromium
            log.info("Edge not found — using Playwright bundled Chromium")
            browser = pw.chromium.launch(
                args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
            )
        page = browser.new_context().new_page()
        page.set_viewport_size({"width": 1080, "height": 1350})

        # Type-aware photo crop positions — biased toward faces/subjects
        _TYPE_POSITIONS = {
            "HOOK":        "center 20%",
            "CONTEXT":     "center 25%",
            "STAT":        "center 30%",
            "INSIGHT":     "center 25%",
            "IMPLICATION": "center 30%",
            "TIP":         "center 25%",
            "OPPORTUNITY": "center 30%",
            "GROWTH":      "center 25%",
            "CTA":         "center center",
            "BRAND":       "center center",
        }

        for idx, slide in enumerate(slides):
            slide_num = idx + 1

            # Per-slide AI image from Pollinations.ai (topic-specific, cached by prompt hash)
            # Gemini writes image_prompt per slide — semantically aware of slide's conceptual message.
            # fallback_uri = Unsplash pool photo for this slide index (pre-fetched, always works)
            fallback_uri  = photo_urls[idx] if idx < len(photo_urls) else (photo_urls[-1] if photo_urls else "")
            slide_title   = slide.get("headline") or slide.get("title", "")
            slide_type    = slide.get("type", "CONTEXT")
            gemini_prompt = slide.get("image_prompt", "")  # Gemini-written visual description
            raw_ai_uri    = generate_slide_image(slide_title, slide_type, category, fallback_uri, idx, gemini_prompt)

            # Convert file:// → base64 data URI so Playwright can embed inline
            photo_url       = _file_uri_to_data_uri(raw_ai_uri)
            object_position = _TYPE_POSITIONS.get(slide_type.upper(), "center 25%")

            # Fix 2: Map Gemini response fields → template variables.
            # Gemini returns: title, body, stat_callout (strings).
            # Templates expect: headline, bullets (list), stat_number, stat_label.
            headline  = slide.get("headline") or slide.get("title", "")
            body_text = slide.get("body", "")

            raw_bullets = slide.get("bullets") or slide.get("body_points")
            if raw_bullets and isinstance(raw_bullets, list):
                bullets = [str(b).strip() for b in raw_bullets if b][:6]
            elif body_text:
                # ── Abbreviation-aware sentence splitter ─────────────────────────────
                # Pre-protect periods inside abbreviations with NUL placeholder so
                # re.split won't break "approx. $800" or "est. 2026" into fragments.
                _ABBREV_RE = re.compile(
                    r'\b(approx|est|MT|USD|Cr|kg|Mr|Mrs|Dr|vs|Inc|Ltd|Rs|no'
                    r'|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.',
                    re.IGNORECASE
                )
                protected = _ABBREV_RE.sub(
                    lambda m: m.group(0).replace('.', '\x00'), body_text.strip()
                )
                # Split only where end-of-sentence punct is followed by space+Capital/digit/symbol
                raw_sents = re.split(
                    r'(?<=[.!?])\s+(?=[A-Z\u20b9\$\d\u2191\u2193])', protected
                )
                sentences = [s.replace('\x00', '.').strip() for s in raw_sents]
                bullets = [s for s in sentences if s][:6]
                # Fallback: one long sentence → split at em-dash / semicolon
                if len(bullets) == 1 and len(bullets[0]) > 80:
                    parts  = re.split(r'[;\u2014\u2013]', bullets[0])
                    bullets = [p.strip() for p in parts if p.strip()][:6]
            else:
                bullets = []

            # Post-filter: drop orphan fragments
            # Orphans = < 20 chars, starts lowercase, starts with ) or $ (parenthetical tail)
            bullets = [
                b for b in bullets
                if len(b) > 20
                and not b[0].islower()
                and b[0] not in (')', '$')
                and not re.match(r'^[A-Z]\.?$', b)
            ]
            # Word-boundary-safe truncation — never cuts mid-word
            bullets = [
                textwrap.shorten(b, width=150, break_long_words=False, placeholder='\u2026')
                if len(b) > 150 else b
                for b in bullets
            ]

            # Append forward_pull as the final bullet (styled via :last-child CSS in template)
            # Only on non-CTA slides and when Gemini supplied it.
            # DEDUP: Gemini often echoes forward_pull as the last sentence of body —
            # compare normalized text (lowercase, stripped punctuation) to avoid duplicates.
            forward_pull = slide.get("forward_pull", "").strip()
            if forward_pull and slide_type.upper() not in ("CTA", "BRAND"):
                _norm = lambda s: re.sub(r'[^a-z0-9 ]', '', s.lower().strip())[:60]
                fp_norm = _norm(forward_pull)
                already_present = any(_norm(b) == fp_norm for b in bullets)
                if not already_present:
                    bullets.append(forward_pull)

            # Type-aware badge text (instead of generic "MARKET INSIGHT" on every slide)
            _BADGE_TEXT = {
                "HOOK":        "MARKET ALERT",
                "STAT":        "BY THE NUMBERS",
                "INSIGHT":     "TRADE ANALYSIS",
                "IMPLICATION": "BUYER SIGNAL",
                "TIP":         "TRADE TIP",
                "CONTEXT":     "ORIGIN STORY",
                "OPPORTUNITY": "GROWTH SIGNAL",
                "GROWTH":      "GROWTH SIGNAL",
                "CTA":         "CONNECT WITH US",
                "BRAND":       "CONNECT WITH US",
                "PROBLEM":     "MARKET CHALLENGE",
                "PRICE":       "PRICE SNAPSHOT",
                "COMPLIANCE":  "COMPLIANCE NOTE",
            }
            badge_text = _BADGE_TEXT.get(slide_type.upper(), theme.get("badge_text", "MARKET INSIGHT"))

            # stat_callout (Gemini) → stat_number / stat_label
            # NOTE: Never fall back to slide 'type' — that produces 'Hook', 'Stat' etc.
            stat_callout = slide.get("stat_callout", "")
            stat_number  = slide.get("stat_number") or stat_callout
            stat_label   = slide.get("stat_label") or ""  # show nothing if not explicit

            badge_location = slide.get("badge_location", "")
            farm_stats     = slide.get("farm_stats", [])
            data_grid      = slide.get("data_grid", [])

            headline_size = 54
            if len(headline) > 70:
                headline_size = 46
            elif len(headline) > 55:
                headline_size = 50

            template = jinja.get_template(theme["template"])
            is_cta = slide_type.upper() in ("CTA", "BRAND")
            is_hook = (slide_num == 1)
            html = template.render(
                theme=theme,
                palette=personal_palette,
                slide_num=slide_num,
                total_slides=total_slides,
                photo_url=photo_url,
                object_position=object_position,
                headline=headline,
                bullets=bullets,
                stat_number=stat_number,
                stat_label=stat_label,
                badge_text=badge_text,
                badge_location=badge_location,
                farm_stats=farm_stats,
                data_grid=data_grid,
                headline_size=headline_size,
                logo_data_uri=logo_circle_data_uri,
                footer=FOOTER,
                is_cta=is_cta,
                is_hook=is_hook,
                slide_type=slide_type.upper(),
            )

            # domcontentloaded fires immediately after HTML+CSS parse — faster and
            # more reliable than "networkidle" which blocks on slow CDN responses.
            # The 1200ms pause gives Google Fonts and Tailwind time to apply before
            # the screenshot is captured.
            page.set_content(html, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            png_path = str(OUTPUT_DIR / f"slide_{category}_{idx+1:02d}.png")
            page.screenshot(path=png_path, type="png", full_page=False)
            png_paths.append(png_path)
            log.info("  Slide %d/%d → %s", slide_num, total_slides, png_path)

        browser.close()

    # Assemble PNG slides → PDF
    png_bytes_list = [open(p, "rb").read() for p in png_paths]
    pdf_bytes = img2pdf.convert(png_bytes_list)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Cleanup PNGs
    for p in png_paths:
        try:
            pathlib.Path(p).unlink()
        except Exception:
            pass

    size_mb = pathlib.Path(pdf_path).stat().st_size / 1_048_576
    log.info("PDF: %s (%.2f MB, %d slides)", pdf_path, size_mb, len(png_paths))

    # Overlay invisible clickable URI annotations: website, WhatsApp, email
    _add_pdf_links(pdf_path, total_slides, is_personal_template)

    return pdf_path
