"""
setup_fonts.py
───────────────
Downloads Oswald Bold + Montserrat font family from Google Fonts/GitHub
and saves them to assets/fonts/ for use in carousel generation.

Run once before deploying:
  python setup_fonts.py

In GitHub Actions, this is run automatically in the workflow before main.py.
Fonts are NOT committed to the repo (in .gitignore) to keep the repo small.
"""

from __future__ import annotations

import pathlib
import sys
import urllib.request

FONTS_DIR = pathlib.Path(__file__).parent / "assets" / "fonts"

# Primary font: Oswald Bold — the exact heavy condensed font in reference designs
# Fallback font: Montserrat — used for body text and captions

TTF_FALLBACK_URLS = {
    # Oswald Bold — primary display/headline font (matches the reference carousel design)
    "Oswald-Bold.ttf":        "https://github.com/googlefonts/OswaldFont/raw/main/fonts/ttf/Oswald-Bold.ttf",
    # Montserrat — body text and bullet points
    "Montserrat-Bold.ttf":    "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf",
    "Montserrat-Regular.ttf": "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf",
    "Montserrat-Light.ttf":   "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Light.ttf",
}


def download_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for filename, fallback_url in TTF_FALLBACK_URLS.items():
        dest = FONTS_DIR / filename
        if dest.exists():
            print(f"  ✓ {filename} already present")
            continue

        print(f"  ↓ Downloading {filename}...")
        try:
            urllib.request.urlretrieve(fallback_url, dest)
            size = dest.stat().st_size
            if size < 10_000:
                print(f"    ⚠ File too small ({size}B) — may be corrupt")
                dest.unlink(missing_ok=True)
                all_ok = False
            else:
                print(f"    ✓ Saved {filename} ({size // 1024} KB)")
        except Exception as e:
            print(f"    ✗ Failed to download {filename}: {e}")
            all_ok = False

    if all_ok:
        print("\nAll Montserrat fonts downloaded successfully.")
    else:
        print(
            "\nSome fonts failed to download. The carousel generator will fall back "
            "to Helvetica (standard PDF font). Posts will still work."
        )


if __name__ == "__main__":
    print("Downloading Montserrat fonts to assets/fonts/ ...")
    download_fonts()
