"""
BSE bulk/block deal scraper.

BSE's bulk_deals.aspx page loads data via a JavaScript fetch to a JSON API,
not directly in the HTML — confirmed via browser DevTools on 17-Aug-2026.
The response wraps the row list in a "Table" key.
"""

import requests

BSE_BULK_URL = "https://api.bseindia.com/BseIndiaAPI/api/BulkDeal_Beta/w"
BSE_BLOCK_URL = "https://api.bseindia.com/BseIndiaAPI/api/BlockDeal_Beta/w"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}


def fetch_bse_deals(deal_type: str) -> list[dict]:
    """
    deal_type: 'bulk' or 'block'.
    Raises on failure — do not silently return an empty list on error.
    """
    url = BSE_BULK_URL if deal_type == "bulk" else BSE_BLOCK_URL
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    raw_rows = payload.get("Table", [])
    return [_normalize_row(row, deal_type) for row in raw_rows]


def _normalize_row(row: dict, deal_type: str) -> dict:
    return {
        "date": row.get("DEAL_DATE", ""),
        "exchange": "BSE",
        "deal_type": deal_type,
        "symbol": row.get("SCRIP_CODE", ""),
        "security_name": row.get("ScripName", ""),
        "client_name": row.get("CLIENT_NAME", ""),
        "buy_sell": row.get("TRANSACTION_TYPE", ""),
        "quantity": row.get("QUANTITY", 0),
        "price": row.get("PRICE", 0),
    }


def fetch_all_bse_deals(date_str: str = "") -> list[dict]:
    """
    date_str kept for compatibility with main.py's call signature but
    unused — this endpoint returns current-day data by default.
    """
    all_deals = []
    for deal_type in ("bulk", "block"):
        try:
            all_deals.extend(fetch_bse_deals(deal_type))
        except Exception as e:
            raise RuntimeError(f"BSE scrape failed for {deal_type}: {e}") from e
    return all_deals


if __name__ == "__main__":
    deals = fetch_all_bse_deals()
    print(f"Fetched {len(deals)} BSE deals")
    for d in deals[:5]:
        print(d)