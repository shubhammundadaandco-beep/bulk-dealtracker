"""
Orchestrator: scrape NSE + BSE, log all deals to history, match against
watchlist, send Telegram alerts.

Run manually: python main.py
Run via GitHub Actions: see .github/workflows/daily-check.yml
"""

import csv
import os
from datetime import date

from matcher import find_watchlist_hits, load_watchlist
from notifier import send_daily_summary, send_failure_alert, send_watchlist_hit
from scraper_bse import fetch_all_bse_deals
from scraper_nse import fetch_all_nse_deals

HISTORY_PATH = os.path.join("data", "history.csv")
HISTORY_FIELDS = [
    "date",
    "exchange",
    "deal_type",
    "symbol",
    "security_name",
    "client_name",
    "buy_sell",
    "quantity",
    "price",
]


def append_to_history(deals: list[dict]) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    file_exists = os.path.isfile(HISTORY_PATH)

    with open(HISTORY_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if not file_exists:
            writer.writeheader()
        for deal in deals:
            writer.writerow({k: deal.get(k, "") for k in HISTORY_FIELDS})


def main() -> None:
    all_deals: list[dict] = []
    errors: list[str] = []

    try:
        nse_deals = fetch_all_nse_deals()
        all_deals.extend(nse_deals)
        print(f"NSE: fetched {len(nse_deals)} deals")
    except Exception as e:
        errors.append(f"NSE scrape error: {e}")
        print(f"NSE scrape failed: {e}")

    try:
        today_str = date.today().strftime("%Y%m%d")  # confirm BSE's expected format
        bse_deals = fetch_all_bse_deals(today_str)
        all_deals.extend(bse_deals)
        print(f"BSE: fetched {len(bse_deals)} deals")
    except Exception as e:
        errors.append(f"BSE scrape error: {e}")
        print(f"BSE scrape failed: {e}")

    # If BOTH scrapers failed, treat this as a hard failure — don't log an
    # empty "no deals today" that could be mistaken for a real quiet day.
    if not all_deals and errors:
        error_summary = "; ".join(errors)
        try:
            send_failure_alert(error_summary)
        except Exception as notify_err:
            print(f"Also failed to send failure alert: {notify_err}")
        raise SystemExit(f"Both scrapers failed: {error_summary}")

    # Log every deal for historical analysis, even if one exchange's
    # scraper partially failed.
    append_to_history(all_deals)

    watchlist = load_watchlist()
    hits = find_watchlist_hits(all_deals, watchlist)

    for hit in hits:
        send_watchlist_hit(hit)

    send_daily_summary(total_deals=len(all_deals), total_hits=len(hits))

    # Surface partial scraper failures even if we got some data and could
    # still send alerts — don't let a silent partial failure go unnoticed.
    if errors:
        send_failure_alert(
            "Partial failure — some deals may be missing:\n" + "; ".join(errors)
        )

    print(f"Done. {len(all_deals)} deals scanned, {len(hits)} watchlist hits.")


if __name__ == "__main__":
    main()
