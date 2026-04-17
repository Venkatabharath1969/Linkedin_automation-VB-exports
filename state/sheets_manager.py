"""
state/sheets_manager.py
─────────────────────────
Manages the Google Sheets topic queue for VB Exports daily posting.

Sheet structure (one tab per category — or all in one "Topics" sheet):
  A: Category    | B: Topic          | C: Status       | D: Posted_Date
  coffee_market  | Karnataka coffee  | Pending         |
  spice_trade    | India pepper...   | In Progress     |
  export_guide   | How to start...   | Posted          | 2026-04-07

Status lifecycle:  Pending → In Progress → Posted
  • If all rows in a category are "Posted" → reset them all to "Pending" (cycle)
  • If a row is stuck "In Progress" > 2 hours → reset to "Pending" (crash recovery)

Authentication: Reads GOOGLE_SHEETS_CREDS env var (JSON string of service account).
Fallback: reads service_account.json file in the project root.

Setup:
  1. Create a Google Sheet and share it with your service account email
  2. Add GOOGLE_SHEET_ID and GOOGLE_SHEETS_CREDS to GitHub Secrets
  3. Run python setup_sheets.py to pre-populate topic rows
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEET_ID, SCHEDULE, TIMEZONE

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Column indices (1-based for gspread)
COL_CATEGORY    = 1   # A
COL_TOPIC       = 2   # B
COL_STATUS      = 3   # C
COL_POSTED_DATE = 4   # D

STATUS_PENDING     = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_POSTED      = "Posted"

# If a row has been "In Progress" for longer than this, it's a crashed run → reset
IN_PROGRESS_TIMEOUT_HOURS = 2


# ══════════════════════════════════════════════════════════════════════════════
# Authentication
# ══════════════════════════════════════════════════════════════════════════════

def _get_client() -> gspread.Client:
    """Returns an authenticated gspread client."""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDS", "").strip()

    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            log.info("Google Sheets auth: using GOOGLE_SHEETS_CREDS env var")
            return gspread.authorize(creds)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("GOOGLE_SHEETS_CREDS parse error: %s", e)

    # Fallback to local file
    creds_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "service_account.json")
    if os.path.exists(creds_file):
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        log.info("Google Sheets auth: using service_account.json")
        return gspread.authorize(creds)

    raise RuntimeError(
        "No Google Sheets credentials found. Set GOOGLE_SHEETS_CREDS env var or "
        "provide service_account.json in the project root."
    )


def _get_sheet() -> gspread.Worksheet:
    """Returns the 'Topics' worksheet from the configured spreadsheet."""
    client = _get_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        return spreadsheet.worksheet("Topics")
    except gspread.WorksheetNotFound:
        # Create it if missing
        ws = spreadsheet.add_worksheet("Topics", rows=500, cols=4)
        ws.append_row(["Category", "Topic", "Status", "Posted Date"])
        log.info("Created 'Topics' worksheet in spreadsheet")
        return ws


# ══════════════════════════════════════════════════════════════════════════════
# Topic retrieval
# ══════════════════════════════════════════════════════════════════════════════

def get_todays_topic(category: str) -> dict:
    """
    Finds the next pending topic for the given category.

    Returns:
      {"row_num": int, "topic": str, "category": str}

    Raises RuntimeError if no topics are available.
    """
    ws       = _get_sheet()
    all_rows = ws.get_all_values()   # includes header

    # Skip header row (index 0 = row 1)
    data_rows = all_rows[1:]

    pending_candidates: list[tuple[int, str]] = []
    in_progress_rows:   list[int]             = []

    for i, row in enumerate(data_rows):
        row_num  = i + 2   # gspread is 1-based; +2 for header skip
        cat      = (row[COL_CATEGORY - 1] if len(row) > COL_CATEGORY - 1 else "").strip()
        topic    = (row[COL_TOPIC    - 1] if len(row) > COL_TOPIC    - 1 else "").strip()
        status   = (row[COL_STATUS   - 1] if len(row) > COL_STATUS   - 1 else "").strip()

        if cat != category:
            continue

        if status == STATUS_PENDING and topic:
            pending_candidates.append((row_num, topic))

        elif status == STATUS_IN_PROGRESS:
            # Crash recovery: if stuck too long, reset to Pending
            posted_date = row[COL_POSTED_DATE - 1] if len(row) > COL_POSTED_DATE - 1 else ""
            if _is_stuck_in_progress(posted_date):
                log.warning("Row %d stuck In Progress — resetting to Pending", row_num)
                ws.update_cell(row_num, COL_STATUS, STATUS_PENDING)
                if topic:
                    pending_candidates.append((row_num, topic))
            else:
                in_progress_rows.append(row_num)

    # All rows for this category are Posted → reset cycle
    category_rows = [
        r for r in data_rows
        if (r[COL_CATEGORY - 1] if len(r) > 0 else "").strip() == category
    ]
    all_posted = all(
        (r[COL_STATUS - 1] if len(r) > COL_STATUS - 1 else "").strip() == STATUS_POSTED
        for r in category_rows
        if (r[COL_TOPIC - 1] if len(r) > COL_TOPIC - 1 else "").strip()
    )

    if all_posted and not pending_candidates:
        log.info("All %s topics posted — resetting cycle", category)
        pending_candidates = _reset_category(ws, all_rows, category)

    if not pending_candidates:
        raise RuntimeError(
            f"No pending topics found for category '{category}'. "
            "Add topics to the Google Sheet 'Topics' tab."
        )

    row_num, topic = pending_candidates[0]
    log.info("Today's topic [%s]: %s (row %d)", category, topic, row_num)
    return {"row_num": row_num, "topic": topic, "category": category}


def _is_stuck_in_progress(posted_date_str: str) -> bool:
    """Returns True if the In Progress timestamp is older than the timeout."""
    if not posted_date_str:
        return True  # no timestamp = clearly stuck
    try:
        # Stored as ISO format when mark_in_progress is called
        dt = datetime.fromisoformat(posted_date_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        return age > timedelta(hours=IN_PROGRESS_TIMEOUT_HOURS)
    except ValueError:
        return True


def _reset_category(ws: gspread.Worksheet, all_rows: list, category: str) -> list[tuple[int, str]]:
    """Resets all Posted rows for a category back to Pending. Returns new pending list."""
    pending: list[tuple[int, str]] = []
    for i, row in enumerate(all_rows[1:], start=2):
        cat    = (row[COL_CATEGORY - 1] if len(row) > COL_CATEGORY - 1 else "").strip()
        topic  = (row[COL_TOPIC    - 1] if len(row) > COL_TOPIC    - 1 else "").strip()
        status = (row[COL_STATUS   - 1] if len(row) > COL_STATUS   - 1 else "").strip()
        if cat == category and status == STATUS_POSTED and topic:
            ws.update_cell(i, COL_STATUS, STATUS_PENDING)
            ws.update_cell(i, COL_POSTED_DATE, "")
            pending.append((i, topic))
    log.info("Reset %d topics in '%s' to Pending", len(pending), category)
    return pending


# ══════════════════════════════════════════════════════════════════════════════
# Status updates
# ══════════════════════════════════════════════════════════════════════════════

def mark_in_progress(row_num: int) -> None:
    """
    Marks a topic row as 'In Progress'.
    Also stores current timestamp in Posted_Date column as crash-recovery marker.
    """
    ws = _get_sheet()
    ws.update_cell(row_num, COL_STATUS,      STATUS_IN_PROGRESS)
    ws.update_cell(row_num, COL_POSTED_DATE, datetime.now(timezone.utc).isoformat())
    log.info("Row %d → In Progress", row_num)


def mark_as_posted(row_num: int) -> None:
    """Marks a topic row as 'Posted' with today's IST date."""
    import pytz
    ws  = _get_sheet()
    ist = pytz.timezone(TIMEZONE)
    date_str = datetime.now(ist).strftime("%Y-%m-%d")
    ws.update_cell(row_num, COL_STATUS,      STATUS_POSTED)
    ws.update_cell(row_num, COL_POSTED_DATE, date_str)
    log.info("Row %d → Posted (%s)", row_num, date_str)


# ══════════════════════════════════════════════════════════════════════════════
# Recent topic lookup (for deduplication)
# ══════════════════════════════════════════════════════════════════════════════

def get_recent_topics(count: int = 7) -> list[str]:
    """Returns the last N posted topics across all categories, most recent first."""
    ws       = _get_sheet()
    all_rows = ws.get_all_values()[1:]   # skip header

    posted = [
        row for row in all_rows
        if (row[COL_STATUS - 1] if len(row) > COL_STATUS - 1 else "").strip() == STATUS_POSTED
        and (row[COL_TOPIC - 1] if len(row) > COL_TOPIC - 1 else "").strip()
    ]

    # Sort by posted date descending
    def _sort_key(r: list) -> str:
        return r[COL_POSTED_DATE - 1] if len(r) > COL_POSTED_DATE - 1 else ""

    posted.sort(key=_sort_key, reverse=True)
    return [r[COL_TOPIC - 1] for r in posted[:count]]
