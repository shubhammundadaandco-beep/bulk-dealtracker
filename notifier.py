"""
Sends alerts via Telegram Bot API. Requires TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID environment variables (see README setup steps).
"""

import os

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


def _send_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as "
            "environment variables (or GitHub Actions secrets)."
        )

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    resp.raise_for_status()


def send_watchlist_hit(hit: dict) -> None:
    deal = hit["deal"]
    text = (
        f"🔔 <b>Watchlist hit</b>\n"
        f"Investor: {hit['matched_investor']} (match {hit['match_score']}%)\n"
        f"Stock: {deal.get('symbol')} — {deal.get('security_name')}\n"
        f"Exchange: {deal.get('exchange')} | Type: {deal.get('deal_type')}\n"
        f"Action: {deal.get('buy_sell')}\n"
        f"Qty: {deal.get('quantity')} | Price: {deal.get('price')}\n"
        f"Date: {deal.get('date')}"
    )
    _send_message(text)


def send_daily_summary(total_deals: int, total_hits: int) -> None:
    text = (
        f"✅ Daily deal check complete.\n"
        f"Total deals scanned: {total_deals}\n"
        f"Watchlist hits: {total_hits}"
    )
    _send_message(text)


def send_failure_alert(error_message: str) -> None:
    text = f"⚠️ Bulk/block deal tracker FAILED:\n{error_message}"
    _send_message(text)


if __name__ == "__main__":
    # Manual test: python notifier.py
    # Requires env vars to be set first.
    send_daily_summary(total_deals=0, total_hits=0)
    print("Test message sent (check your Telegram chat).")
