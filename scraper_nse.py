"""
NSE bulk/block deal scraper — uses the nsepython library, which handles
NSE's bot-protection internally (raw requests.get() gets 403'd).
"""

import nsepython


def _normalize_row(row: dict, deal_type: str) -> dict:
    return {
        "date": row.get("Date", ""),
        "exchange": "NSE",
        "deal_type": deal_type,
        "symbol": row.get("Symbol", ""),
        "security_name": row.get("Security Name", ""),
        "client_name": row.get("Client Name", ""),
        "buy_sell": row.get("Buy/Sell", ""),
        "quantity": row.get("Quantity Traded", 0),
        "price": row.get("Trade Price / Wght. Avg. Price", 0),
    }


def fetch_all_nse_deals() -> list[dict]:
    all_deals = []

    try:
        bulk_df = nsepython.get_bulkdeals()
        for row in bulk_df.to_dict(orient="records"):
            all_deals.append(_normalize_row(row, "bulk_deals"))
    except Exception as e:
        raise RuntimeError(f"NSE bulk deals scrape failed: {e}") from e

    try:
        block_df = nsepython.get_blockdeals()
        for row in block_df.to_dict(orient="records"):
            all_deals.append(_normalize_row(row, "block_deals"))
    except Exception as e:
        raise RuntimeError(f"NSE block deals scrape failed: {e}") from e

    return all_deals


if __name__ == "__main__":
    deals = fetch_all_nse_deals()
    print(f"Fetched {len(deals)} NSE deals")
    for d in deals[:5]:
        print(d)