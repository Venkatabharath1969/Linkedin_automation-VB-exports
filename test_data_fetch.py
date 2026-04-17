"""
test_data_fetch.py
───────────────────
Run this to verify what data is actually fetched from each source.
Shows the raw API responses so you see exactly what Gemini receives.

Usage:
  python test_data_fetch.py
"""
import json
import os
import sys

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

DATA_GOV_KEY = os.environ.get("DATA_GOV_API_KEY", "").strip()
BASE = "https://api.data.gov.in/resource"

DATASETS = {
    "Coffee Exports (Year-wise quantity, Coffee Board)": (
        "details-coffee-export-2016-17-2018-19-ministry-commerce-industry"
    ),
    "State-wise Coffee Production 2022-23": (
        "state-wise-details-area-production-and-productivity-coffee-during-2022-23"
    ),
    "Spice Exports by Country (Ministry of Commerce)": (
        "major-itemcountry-wise-export-spices-india-2014-15-2016-17-ministry-commerce-and-industry"
    ),
    "Horticulture Spice Production Data": (
        "horticulture-area-production-yield-and-value-spice-crop"
    ),
}

# UN Comtrade (no API key needed)
COMTRADE_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# RSS (no key needed)
RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/1947462.cms",
    "https://www.thehindubusinessline.com/economy/agri-business/feeder/default.rss",
]


def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_data_gov():
    sep("DATA.GOV.IN — APEDA / Coffee Board Datasets")

    if not DATA_GOV_KEY:
        print("⚠  DATA_GOV_API_KEY not set in .env")
        print("   Showing what the URL would look like:")
        for name, slug in DATASETS.items():
            print(f"\n  Dataset: {name}")
            print(f"  URL: {BASE}/{slug}?api-key=YOUR_KEY&format=json&limit=5")
        print("\n  → Once you add the key, these endpoints return JSON like:")
        print("""  {
    "count": 3,
    "records": [
      {"Year": "2016-17", "Quantity (MT)": "294,400"},
      {"Year": "2017-18", "Quantity (MT)": "316,000"},
      {"Year": "2018-19", "Quantity (MT)": "395,000"}
    ]
  }""")
        return

    for name, slug in DATASETS.items():
        print(f"\n► {name}")
        try:
            resp = requests.get(
                f"{BASE}/{slug}",
                params={"api-key": DATA_GOV_KEY, "format": "json", "limit": 5},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("records", [])
                print(f"  ✓ {len(records)} records returned")
                if records:
                    print(f"  Fields: {list(records[0].keys())}")
                    print(f"  First record: {json.dumps(records[0], indent=4)}")
            else:
                print(f"  ✗ HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"  ✗ Error: {e}")


def test_comtrade():
    sep("UN COMTRADE — India Coffee & Spice Export Stats (No Key Needed)")

    tests = [
        ("Coffee (HS 0901)", "0901"),
        ("Pepper (HS 0904)", "0904"),
        ("Cardamom (HS 0908)", "0908"),
    ]

    for name, hs in tests:
        print(f"\n► {name}")
        try:
            resp = requests.get(
                COMTRADE_URL,
                params={
                    "reporterCode": "356",  # India
                    "cmdCode": hs,
                    "flowCode": "X",        # Exports
                    "period": "2023",
                    "partnerCode": "0",     # World
                    "limit": 3,
                },
                timeout=20,
                verify=False,  # some corporate networks have SSL intercept
            )
            if resp.status_code == 200:
                data = resp.json()
                records = data.get("data", [])
                if records:
                    r = records[0]
                    val = r.get("primaryValue", 0)
                    wgt = r.get("netWgt", 0)
                    print(f"  ✓ Export value: ${val/1e9:.2f}B USD" if val > 1e9 else f"  Value: ${val/1e6:.1f}M USD")
                    print(f"  ✓ Net weight:   {(wgt or 0)/1000:.0f}K MT" if wgt else "  Weight: N/A")
                    print(f"  ✓ Period: {r.get('period')} | Reporter: {r.get('reporterDesc')}")
                else:
                    print(f"  ⚠ No records (API returned empty — using fallback data)")
            else:
                print(f"  ✗ HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ✗ Error: {e} → Using built-in fallback data")


def test_rss():
    sep("RSS NEWS FEEDS — Live Export Headlines")
    try:
        import feedparser
    except ImportError:
        print("  feedparser not installed. Run: pip install feedparser")
        return

    KEYWORDS = {"coffee", "spice", "export", "apeda", "cardamom", "pepper", "turmeric"}
    count = 0
    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:30]:
                title = getattr(entry, "title", "")
                if any(kw in title.lower() for kw in KEYWORDS):
                    print(f"  ✓ [{parsed.feed.get('title', 'RSS')}]")
                    print(f"    {title}")
                    count += 1
                    if count >= 5:
                        break
            if count >= 5:
                break
        except Exception as e:
            print(f"  ✗ {feed_url}: {e}")

    if count == 0:
        print("  No matching headlines in last fetch (RSS content varies by time)")


def test_fallback():
    sep("BUILT-IN FALLBACK DATA (Always Available, No API Key Needed)")
    from fetchers.export_data_fetcher import FALLBACK_DATA
    print("\nCoffee fallback:")
    print(json.dumps(FALLBACK_DATA["coffee"], indent=2))
    print("\nSpices fallback:")
    print(json.dumps(FALLBACK_DATA["spices"], indent=2))
    print("\nGeneral fallback:")
    print(json.dumps(FALLBACK_DATA["general"], indent=2))


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()  # suppress SSL warnings from corporate proxy

    test_fallback()
    test_comtrade()
    test_rss()
    test_data_gov()

    sep("SUMMARY")
    print("""
What happens in the actual daily run:
  1. Try data.gov.in API  → if key set + API responds → use live data
  2. Try UN Comtrade       → if reachable → layer in trade statistics  
  3. Try RSS feeds         → always works → get today's news headline
  4. Fallback data         → ALWAYS available → real 2023-24 verified figures

The AI (Gemini) receives whichever data is available.
Even with ZERO API keys, fallback data is rich enough to generate
high-quality, data-driven carousels.
""")
