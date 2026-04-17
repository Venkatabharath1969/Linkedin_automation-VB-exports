import requests, json, os
from dotenv import load_dotenv
load_dotenv()

KEY  = os.environ.get("DATA_GOV_API_KEY", "")
BASE = "https://api.data.gov.in/resource"

print(f"Key prefix: {KEY[:12]}...\n")

# These visualization UUIDs were found in the dataset pages earlier
# Try them as the actual API resource IDs (different from URL slugs)
uuid_candidates = {
    "coffee_exports_uuid":      "5e23b7c3-d4df-4a65-ac46-ba4b4e2d4ecb",
    "coffee_statewise_uuid":    "c8cdea60-94b6-46be-8b7f-3c6f2d734d72",
    "spice_exports_uuid":       "9481b8ec-099c-4baa-b94a-f288f44cc223",
    "spice_horticulture_uuid":  "ac1a1477-94c6-4620-89a2-7d5f7a3bd1f4",
}

for name, rid in uuid_candidates.items():
    url = f"{BASE}/{rid}"
    r = requests.get(url, params={"api-key": KEY, "format": "json", "limit": 5}, timeout=15)
    body = r.json()
    count   = body.get("count", 0)
    total   = body.get("total", 0)
    records = body.get("records", [])
    msg     = body.get("message", "")
    print(f"[HTTP {r.status_code}] {name}")
    print(f"  total={total}  count={count}  msg={msg!r}")
    if records:
        print(f"  Fields: {list(records[0].keys())}")
        print(f"  First:  {json.dumps(records[0], ensure_ascii=False)}")
    print()
