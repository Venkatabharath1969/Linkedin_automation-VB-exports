"""
setup_sheets.py
────────────────
One-time script to initialise the Google Sheets topic queue with
VB Exports carousel topics for all 7 posting categories.

Run once after creating your Google Sheet:
  python setup_sheets.py

The script will:
  1. Open the Google Sheet configured in your .env / environment
  2. Create a 'Topics' worksheet (or clear and recreate it)
  3. Pre-populate 52+ topics (one per week per category)

Add your own topics by editing the TOPIC_SEEDS dict below.
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import gspread
from google.oauth2.service_account import Credentials

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Topic seed data — 8 topics per category (52 weeks of content) ─────────────
TOPIC_SEEDS: dict[str, list[str]] = {
    "coffee_market": [
        "India's Robusta Coffee Export Surge: 2024 Data",
        "Why Italy Buys More Indian Coffee Than Any Other Country",
        "Karnataka Coffee: 71% of India's Exports from One State",
        "How Brazil's Supply Crisis Created Opportunity for Indian Coffee Exporters",
        "India Coffee Board Export Statistics: 5-Year Growth Trend",
        "Arabica vs Robusta Split in India's 2023–24 Export Volume",
        "Indian Coffee's Rising Share in European Specialty Markets",
        "Which Grades of Indian Coffee Command the Highest FOB Prices",
    ],
    "spice_trade": [
        "India's $4.3B Spice Export Industry: 2024 Overview",
        "Turmeric Exports from India: 34% Growth and Why It's Happening",
        "Pepper Trade: India vs Vietnam — Who's Winning the Global Market",
        "Cardamom from Kerala & Karnataka: Export Premium and Buyer Profile",
        "Why India Supplies 75% of the World's Spice Demand",
        "Organic Spice Exports: The Premium Market Opportunity for Indian Farmers",
        "Top 5 Importing Countries for Indian Spices: Volume and Value",
        "Chilli Exports: India's #1 Spice by Volume and Key Markets",
    ],
    "export_compliance": [
        "The 5 Documents Every Indian Food Exporter Must Have",
        "APEDA Registration: What It Unlocks and How to Get It",
        "FSSAI Export Certificate: Which Products Require It",
        "IEC Code: The Starting Point for Every Indian Exporter",
        "EU Deforestation Regulation 2024: Impact on Indian Coffee Exporters",
        "Organic Certification for Indian Coffee: Cost vs. Price Premium",
        "How Certifications Directly Correlate to Export Price Premiums",
        "Rainforest Alliance vs UTZ: Which Certification Do EU Buyers Prefer",
    ],
    "global_buyers": [
        "India's Top 10 Coffee Importing Countries: 2024 Rankings",
        "What European Coffee Buyers Specifically Require from Indian Exporters",
        "UAE as India's Growing Coffee Market: Rising Demand Data",
        "USA Coffee Import Requirements: FDA Prior Notice and Labelling",
        "Southeast Asia: The Underserved Market for Indian Coffee",
        "How to Find Verified International Buyers for Indian Coffee",
        "What Makes a Buyer Choose Indian Coffee Over Brazilian or Vietnamese",
        "Payment Terms: L/C vs Bank Transfer — What First-Time Buyers Prefer",
    ],
    "price_trends": [
        "Indian Robusta vs ICO Benchmark Price: 2024 Analysis",
        "MCX Coffee Futures: What Indian Exporters Need to Watch",
        "How Brazil Drought in 2023 Impacted Indian Coffee Pricing",
        "Arabica Price Premium: Is India Commanding Market Rate?",
        "Pepper Price Volatility 2024: What Caused the 40% Swing",
        "Forward Contract Timing: When to Lock In Your Export Price",
        "FOB vs CIF Pricing: Which Incoterm Protects Indian Exporters More",
        "Coffee Price Outlook for Q3 2025: Supply and Demand Signals",
    ],
    "farm_origin": [
        "Coorg Arabica: India's Most Sought-After Single-Origin Coffee",
        "Chikkamagaluru Coffee Belt: Altitude, Rainfall, and Flavour Profile",
        "GI Tag Coffee from India: Wayanad Robusta and What It Means for Buyers",
        "Shade-Grown vs Sun-Grown Indian Coffee: Quality Difference Explained",
        "Why Karnataka Produces 71% of India's Coffee in 3 Districts",
        "Traceability in Indian Coffee: How Farm-to-Port Documentation Works",
        "The Story of a Coffee Bean: From Karnataka Estate to European Cup",
        "Monsoon Malabar: India's Unique Processed Coffee and Export Appeal",
    ],
    "export_guide": [
        "How Long Does It Really Take to Start Exporting from India? (Honest Answer)",
        "Step-by-Step: Getting Your IEC Code in 3 Days Online",
        "The Most Common Reason Your First Shipment Gets Rejected at Customs",
        "FOB vs CIF vs CFR: Incoterms Explained for Indian Agricultural Exporters",
        "Which Ports in India Are Best for Coffee & Spice Exports",
        "How to Write a Pro Forma Invoice That European Buyers Will Accept",
        "Phytosanitary Certificate: When You Need It and How to Get It",
        "Export Packing Requirements: What Humidity, Weight, and Labelling Rules Apply",
    ],
}


def run() -> None:
    print("=" * 60)
    print("  VB Exports — Google Sheets Topic Queue Setup")
    print("=" * 60)

    import json

    creds_json = os.environ.get("GOOGLE_SHEETS_CREDS", "").strip()
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds_file = os.path.join(os.path.dirname(__file__), "service_account.json")
        if not os.path.exists(creds_file):
            print("ERROR: No credentials found.")
            print("Set GOOGLE_SHEETS_CREDS env var OR provide service_account.json")
            sys.exit(1)
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)

    if not GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID not set in environment or .env")
        sys.exit(1)

    client = gspread.authorize(creds)
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    except Exception as e:
        print(f"ERROR: Cannot open sheet {GOOGLE_SHEET_ID}: {e}")
        sys.exit(1)

    # Get or create Topics worksheet
    try:
        ws = spreadsheet.worksheet("Topics")
        print("Found existing 'Topics' worksheet")
        confirm = input("Clear and re-populate it? (y/n): ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("Topics", rows=500, cols=4)
        print("Created 'Topics' worksheet")

    # Write header
    ws.append_row(["Category", "Topic", "Status", "Posted Date"],
                  value_input_option="RAW")

    # Write rows
    rows = []
    for category, topics in TOPIC_SEEDS.items():
        for topic in topics:
            rows.append([category, topic, "Pending", ""])

    ws.append_rows(rows, value_input_option="RAW")

    print(f"\n✓ Loaded {len(rows)} topics across {len(TOPIC_SEEDS)} categories")
    print(f"  Sheet: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}")
    print("\nYou can add more topics manually to the sheet at any time.")
    print("The agent will cycle through all topics before repeating.")


if __name__ == "__main__":
    run()
