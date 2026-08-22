"""
generate_dashboard.py (v2 - full table, sort/filter, time-range selector)

Reads data/history.csv and watchlist.json, computes summary stats, and
writes a single self-contained HTML dashboard to docs/index.html.

All filtering/sorting/time-range selection happens client-side in the
browser against an embedded JSON dataset - no rebuild needed to change
views, works as a static file served via GitHub Pages.

Usage: python generate_dashboard.py
"""

import csv
import json
import os
from datetime import datetime

from rapidfuzz import fuzz

HISTORY_PATH = os.path.join("data", "history.csv")
WATCHLIST_PATH = "watchlist.json"
PRICE_PERF_PATH = os.path.join("data", "price_performance.csv")
OUTPUT_DIR = "docs"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")

MATCH_THRESHOLD = 85  # kept in sync with matcher.py manually


def load_history() -> list[dict]:
    if not os.path.isfile(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, newline="") as f:
        return list(csv.DictReader(f))


def load_watchlist() -> list[str]:
    if not os.path.isfile(WATCHLIST_PATH):
        return []
    with open(WATCHLIST_PATH) as f:
        data = json.load(f)
    return data.get("investors", [])


def parse_date_iso(date_str: str) -> str:
    """Converts whatever date format is in the CSV to ISO (YYYY-MM-DD) for
    reliable JS date parsing/sorting. Falls back to the raw string if
    unparseable."""
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return date_str or ""


def load_price_performance() -> dict:
    """
    Returns a dict keyed by (date, exchange, symbol, client_name, buy_sell,
    deal_price) -> performance dict, for merging into the deals list.
    Returns {} if price_performance.csv doesn't exist yet (feature not run).
    """
    if not os.path.isfile(PRICE_PERF_PATH):
        return {}
    index = {}
    with open(PRICE_PERF_PATH, newline="") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("date", ""),
                row.get("exchange", ""),
                row.get("symbol", ""),
                row.get("client_name", ""),
                row.get("buy_sell", ""),
                row.get("deal_price", ""),
            )
            index[key] = row
    return index


def _to_float_or_none(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None



def match_client_to_watchlist(client_name: str, watchlist: list[str]) -> str:
    best_name, best_score = "", 0
    for watch_name in watchlist:
        score = fuzz.token_sort_ratio(client_name, watch_name)
        if score > best_score:
            best_score, best_name = score, watch_name
    return best_name if best_score >= MATCH_THRESHOLD else ""


def normalize_buy_sell(raw: str) -> str:
    """BUY/B -> BUY, SELL/S -> SELL, anything else -> '' (unclassified).
    Previously unclassified values (e.g. 'nan') were silently falling into
    the SELL bucket wherever code checked `buy_sell !== 'BUY'`. Fixed here
    so unclassified rows are excluded from buy/sell value aggregation
    instead of being miscounted as sells."""
    r = (raw or "").strip().upper()
    if r in ("BUY", "B"):
        return "BUY"
    if r in ("SELL", "S"):
        return "SELL"
    return ""


def is_junk_row(row: dict) -> bool:
    """Some scraped rows are sentinel/placeholder rows for a day with no
    data (date='NO RECORDS', all other fields 'nan') rather than real
    deals. Drop these before they reach any calculation."""
    date_val = (row.get("date") or "").strip().upper()
    symbol_val = (row.get("symbol") or "").strip().lower()
    if date_val == "NO RECORDS":
        return True
    if symbol_val in ("", "nan"):
        return True
    return False


def build_deals_json(history: list[dict], watchlist: list[str]) -> list[dict]:
    perf_index = load_price_performance()

    clean_rows = [row for row in history if not is_junk_row(row)]

    # Round-trip detection: same investor, same stock, same exchange, same
    # calendar date, appearing as BOTH a BUY and a SELL. This is the only
    # honest proxy detectable from bulk/block deal filings for intraday /
    # prop-desk / arbitrage round-trips (filings carry no delivery flag).
    # Per user decision: keep these rows visible in the raw deal table for
    # auditability, but exclude them from every scoring feature.
    bs_seen = {}
    for row in clean_rows:
        bs = normalize_buy_sell(row.get("buy_sell", ""))
        if not bs:
            continue
        key = (row.get("date", ""), row.get("exchange", ""), row.get("symbol", ""), row.get("client_name", ""))
        bs_seen.setdefault(key, set()).add(bs)
    round_trip_keys = {k for k, v in bs_seen.items() if len(v) > 1}

    deals = []
    for row in clean_rows:
        client_name = row.get("client_name", "")
        raw_date = row.get("date", "")
        exchange = row.get("exchange", "")
        symbol = row.get("symbol", "")
        buy_sell_raw = row.get("buy_sell", "")
        buy_sell = normalize_buy_sell(buy_sell_raw)
        price = row.get("price", "")

        perf = perf_index.get((raw_date, exchange, symbol, client_name, buy_sell_raw, price), {})

        key = (raw_date, exchange, symbol, client_name)
        value_cr = None
        qty_f = _to_float_or_none(row.get("quantity", ""))
        price_f = _to_float_or_none(price)
        if qty_f is not None and price_f is not None:
            value_cr = round((qty_f * price_f) / 10000000, 4)

        deals.append({
            "date": parse_date_iso(raw_date),
            "date_raw": raw_date,
            "exchange": exchange,
            "deal_type": row.get("deal_type", ""),
            "symbol": symbol,
            "security_name": row.get("security_name", ""),
            "client_name": client_name,
            "buy_sell": buy_sell,
            "buy_sell_raw": buy_sell_raw,
            "quantity": row.get("quantity", ""),
            "price": price,
            "value_cr": value_cr,
            "is_round_trip": key in round_trip_keys,
            "matched_investor": match_client_to_watchlist(client_name, watchlist),
            "return_1d_pct": _to_float_or_none(perf.get("return_1d_pct")),
            "return_1w_pct": _to_float_or_none(perf.get("return_1w_pct")),
            "return_1m_pct": _to_float_or_none(perf.get("return_1m_pct")),
        })
    deals.sort(key=lambda d: d["date"], reverse=True)
    return deals


def render_html(deals: list[dict], watchlist: list[str]) -> str:
    deals_json = json.dumps(deals)
    watchlist_json = json.dumps(watchlist)
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bulk/Block Deal Tracker Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<style>
  :root {
    --bg: #0f1117; --card: #171a23; --border: #262b3a; --text: #e6e8ee;
    --muted: #8b93a7; --accent: #5b8def; --green: #3ec97a; --amber: #f0b429; --red: #ef5a6f;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); padding: 24px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .subtitle { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; background: var(--card);
    border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; }
  .toolbar label { font-size: 12px; color: var(--muted); margin-right: 4px; }
  select, input[type="text"] { background: #0f1117; color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; font-size: 13px; }
  input[type="text"] { min-width: 200px; }
  .range-btns { display: flex; gap: 6px; }
  .range-btn { background: #0f1117; color: var(--muted); border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 12px; font-size: 12px; cursor: pointer; }
  .range-btn.active { background: var(--accent); color: white; border-color: var(--accent); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; }
  .stat-value { font-size: 26px; font-weight: 600; }
  .stat-label { color: var(--muted); font-size: 13px; margin-top: 4px; }
  .section { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 20px; }
  .section h2 { font-size: 16px; margin: 0 0 16px; display: flex; justify-content: space-between; align-items: center; }
  .count-pill { font-size: 12px; color: var(--muted); font-weight: 400; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px 10px; border-bottom: 1px solid var(--border);
    cursor: pointer; user-select: none; white-space: nowrap; }
  th:hover { color: var(--text); }
  th .arrow { font-size: 10px; margin-left: 4px; }
  td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .badge { padding: 2px 8px; border-radius: 999px; font-size: 11px; }
  .badge.buy { background: rgba(62,201,122,0.15); color: var(--green); }
  .badge.sell { background: rgba(239,90,111,0.15); color: var(--red); }
  .badge.hit { background: rgba(240,180,41,0.15); color: var(--amber); }
  .badge.roundtrip { background: rgba(139,147,167,0.15); color: var(--muted); }
  .badge.na { background: rgba(139,147,167,0.12); color: var(--muted); }
  .empty { color: var(--muted); text-align: center; padding: 20px; }
  .note { color: var(--muted); font-size: 12px; margin: -8px 0 14px; }
  .toggle-btns { display: flex; gap: 6px; margin-bottom: 14px; }
  .toggle-btn { background: #0f1117; color: var(--muted); border: 1px solid var(--border); border-radius: 6px;
    padding: 5px 12px; font-size: 12px; cursor: pointer; }
  .toggle-btn.active { background: var(--accent); color: white; border-color: var(--accent); }
  .investor-search-wrap { position: relative; max-width: 420px; margin-bottom: 16px; }
  .investor-suggestions { position: absolute; top: 100%; left: 0; right: 0; background: var(--card);
    border: 1px solid var(--border); border-radius: 8px; max-height: 220px; overflow-y: auto; z-index: 10;
    display: none; }
  .investor-suggestions.open { display: block; }
  .investor-suggestions div { padding: 8px 12px; cursor: pointer; font-size: 13px; }
  .investor-suggestions div:hover { background: #1f2432; }
  .investor-detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .mini-stat { background: #0f1117; border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }
  .mini-stat .v { font-size: 18px; font-weight: 600; }
  .mini-stat .l { color: var(--muted); font-size: 11px; margin-top: 2px; }
  .behaviour-tag { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-left: 6px; }
  .behaviour-tag.new-entry { background: rgba(91,141,239,0.18); color: var(--accent); }
  .behaviour-tag.accumulating { background: rgba(62,201,122,0.15); color: var(--green); }
  .behaviour-tag.reducing { background: rgba(240,180,41,0.15); color: var(--amber); }
  .behaviour-tag.exited { background: rgba(239,90,111,0.15); color: var(--red); }
  .behaviour-tag.re-entered { background: rgba(91,141,239,0.18); color: var(--accent); }
  .score-card { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; background: #0f1117; }
  .score-card summary { cursor: pointer; font-size: 13px; display: flex; justify-content: space-between; align-items: center; list-style: none; }
  .score-card summary::-webkit-details-marker { display: none; }
  .score-card .score-total { font-weight: 600; }
  .score-bar-row { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; color: var(--muted); }
  .score-bar-row .val { color: var(--text); }
  .score-explain { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
  .insufficient { color: var(--muted); font-style: italic; }
  .export-btn { background: #0f1117; color: var(--accent); border: 1px solid var(--accent); border-radius: 6px;
    padding: 4px 10px; font-size: 11px; cursor: pointer; font-weight: 500; }
  .export-btn:hover { background: rgba(91,141,239,0.12); }
  .export-btn-all { background: var(--accent); color: white; border: none; border-radius: 6px;
    padding: 8px 16px; font-size: 13px; cursor: pointer; font-weight: 600; }
  .export-btn-all:hover { opacity: 0.9; }
  .section h2 .section-actions { display: flex; align-items: center; gap: 10px; }
  select#watchlistTradesSelect, select#scripTradesSelect { min-width: 220px; }
  canvas { max-height: 260px; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .table-scroll { max-height: 500px; overflow-y: auto; }
  .pagination { display: flex; gap: 8px; justify-content: center; margin-top: 12px; align-items: center; font-size: 13px; }
  .pagination button { background: #0f1117; color: var(--text); border: 1px solid var(--border); border-radius: 6px;
    padding: 4px 10px; cursor: pointer; font-size: 12px; }
  .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
  @media (max-width: 800px) { .two-col { grid-template-columns: 1fr; } }
</style>
</head>
<body>
  <h1>Bulk/Block Deal Tracker</h1>
  <div class="subtitle">Generated GENERATED_AT_PLACEHOLDER</div>
  <div style="margin-bottom:16px;"><button class="export-btn-all" id="exportAllBtn">Download all reports (Excel)</button>
    <span class="note" style="margin:0 0 0 10px;display:inline;">One workbook, one sheet per report, respecting your current filters &amp; date range.</span></div>

  <div class="toolbar">
    <div class="range-btns">
      <button class="range-btn" data-range="30">1M</button>
      <button class="range-btn" data-range="90">3M</button>
      <button class="range-btn active" data-range="365">1Y</button>
      <button class="range-btn" data-range="all">All time</button>
    </div>
    <div><label>From</label><input type="date" id="dateFrom"></div>
    <div><label>To</label><input type="date" id="dateTo"></div>
    <div><label>Search</label><input type="text" id="searchBox" placeholder="Symbol, security, or investor name"></div>
    <div><label>Exchange</label><select id="exchangeFilter"><option value="">All</option><option value="NSE">NSE</option><option value="BSE">BSE</option></select></div>
    <div><label>Type</label><select id="dealTypeFilter"><option value="">All</option></select></div>
    <div><label>Buy/Sell</label><select id="buySellFilter"><option value="">All</option></select></div>
    <div><label>Watchlist only</label><select id="watchlistFilter"><option value="">No</option><option value="yes">Yes</option></select></div>
  </div>

  <div class="grid">
    <div class="stat-card"><div class="stat-value" id="statTotal">-</div><div class="stat-label">Deals in selected range</div></div>
    <div class="stat-card"><div class="stat-value" id="statValue">-</div><div class="stat-label">Total value traded (&#8377; Cr)</div></div>
    <div class="stat-card"><div class="stat-value" id="statHits">-</div><div class="stat-label">Watchlist hits</div></div>
    <div class="stat-card"><div class="stat-value" id="statRising">-</div><div class="stat-label">Rising names (3+ appearances)</div></div>
  </div>

  <div class="two-col">
    <div class="section"><h2>Value of deals per day (&#8377; Cr)</h2><canvas id="dealsChart"></canvas></div>
    <div class="section"><h2>Top stocks by value (&#8377; Cr)</h2><canvas id="stocksChart"></canvas></div>
  </div>

  <div class="section">
    <h2>Watchlist tracker <span class="section-actions"><span class="count-pill" id="watchlistCount"></span><button class="export-btn" data-export="watchlist">Export Excel</button></span></h2>
    <table><thead><tr><th>Investor</th><th>Hits in range</th><th>Status</th></tr></thead><tbody id="watchlistBody"></tbody></table>
    <div style="margin-top:16px;">
      <label style="font-size:12px;color:var(--muted);margin-right:8px;">View trades for</label>
      <select id="watchlistTradesSelect"><option value="">Select a watchlist investor...</option></select>
    </div>
    <div id="watchlistTradesWrap" style="margin-top:12px;"></div>
  </div>

  <div class="section">
    <h2>Investor track record (avg. return after deal) <span class="section-actions"><span class="count-pill" id="trackRecordNote"></span><button class="export-btn" data-export="track">Export Excel</button></span></h2>
    <table>
      <thead><tr>
        <th data-trackcol="name">Investor <span class="arrow" id="arrow-track-name"></span></th>
        <th data-trackcol="deals_with_data">Deals w/ price data <span class="arrow" id="arrow-track-deals_with_data"></span></th>
        <th data-trackcol="avg_1d">Avg 1D % <span class="arrow" id="arrow-track-avg_1d"></span></th>
        <th data-trackcol="avg_1w">Avg 1W % <span class="arrow" id="arrow-track-avg_1w"></span></th>
        <th data-trackcol="avg_1m">Avg 1M % <span class="arrow" id="arrow-track-avg_1m"></span></th>
        <th data-trackcol="win_rate_1w">Win rate (1W) <span class="arrow" id="arrow-track-win_rate_1w"></span></th>
      </tr></thead>
      <tbody id="trackRecordBody"></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Rising names (non-watchlisted, 3+ appearances in range) <span class="section-actions"><span class="count-pill" id="risingCount"></span><button class="export-btn" data-export="rising">Export Excel</button></span></h2>
    <table><thead><tr><th>Name</th><th>Deal count</th><th>Stocks</th></tr></thead><tbody id="risingBody"></tbody></table>
  </div>

  <div class="section">
    <h2>Scrip-wise summary <span class="section-actions"><span class="count-pill" id="scripCount"></span><button class="export-btn" data-export="scrip">Export Excel</button></span></h2>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th data-scripcol="symbol">Symbol <span class="arrow" id="arrow-scrip-symbol"></span></th>
          <th data-scripcol="security_name">Security <span class="arrow" id="arrow-scrip-security_name"></span></th>
          <th data-scripcol="deals">Deals <span class="arrow" id="arrow-scrip-deals"></span></th>
          <th data-scripcol="buy_value">Buy value (&#8377; Cr) <span class="arrow" id="arrow-scrip-buy_value"></span></th>
          <th data-scripcol="sell_value">Sell value (&#8377; Cr) <span class="arrow" id="arrow-scrip-sell_value"></span></th>
          <th data-scripcol="net_value">Net value (&#8377; Cr) <span class="arrow" id="arrow-scrip-net_value"></span></th>
          <th data-scripcol="total_value">Total value (&#8377; Cr) <span class="arrow" id="arrow-scrip-total_value"></span></th>
        </tr></thead>
        <tbody id="scripBody"></tbody>
      </table>
    </div>
    <div style="margin-top:16px;">
      <label style="font-size:12px;color:var(--muted);margin-right:8px;">View trades for</label>
      <select id="scripTradesSelect"><option value="">Select a stock...</option></select>
      <button class="export-btn" data-export="scripTrades" style="margin-left:8px;">Export Excel</button>
    </div>
    <div id="scripTradesWrap" style="margin-top:12px;"></div>
  </div>

  <div class="section">
    <h2>Deal significance &#8211; largest deals in range <span class="section-actions"><span class="count-pill" id="significanceCount"></span><button class="export-btn" data-export="significance">Export Excel</button></span></h2>
    <div class="note">Ranked by deal value. "Size vs this stock's own history" compares this deal's value against all bulk/block deals ever recorded for the same stock in this dataset (no live average-daily-traded-value feed is available, so this is a same-stock historical percentile, not a liquidity-based measure). Round-trip (same investor, same stock, same day, both buy &amp; sell) deals are excluded &#8211; see note below.</div>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>Date</th><th>Symbol</th><th>Investor</th><th>B/S</th><th>Value (&#8377; Cr)</th><th>Size vs stock's own history</th>
        </tr></thead>
        <tbody id="significanceBody"></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <h2>Repeated accumulation engine <span class="section-actions"><span class="count-pill" id="accumCount"></span><button class="export-btn" data-export="accum">Export Excel</button></span></h2>
    <div class="note">Stocks appearing repeatedly in bulk/block deals within the selected date range. Excludes round-trip rows. "Current price" and "avg. daily traded value" are not available in this dataset (no live price feed), shown as N/A rather than estimated.</div>
    <div class="toggle-btns">
      <button class="toggle-btn" data-min="2">2+ appearances</button>
      <button class="toggle-btn active" data-min="3">3+ appearances</button>
      <button class="toggle-btn" data-min="5">5+ appearances</button>
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>Symbol</th><th>Security</th><th>Transactions</th><th>Investors</th>
          <th>Buy value (&#8377; Cr)</th><th>Sell value (&#8377; Cr)</th><th>Net value (&#8377; Cr)</th>
          <th>First txn</th><th>Latest txn</th><th>Avg. price</th><th>Current price</th>
        </tr></thead>
        <tbody id="accumBody"></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <h2>Smart Money Score &#8211; partial (deal-data only) <span class="section-actions"><button class="export-btn" data-export="sms">Export Excel</button></span></h2>
    <div class="note">
      <strong>This score is intentionally partial.</strong> It only scores the two components this dataset can support &#8211;
      Deal Activity and Accumulation Pattern &#8211; from actual bulk/block deal rows in the selected range, excluding round-trips.
      Investor Quality, Fundamental, Technical, Valuation and Risk components require data sources (investor classification,
      financials, price/technical feeds) not present in this dataset, and are shown as <em>Insufficient data</em> rather than
      estimated. Max possible score shown is <strong>35/35</strong> (Deal Activity 20 + Accumulation 15), not 100 &#8211;
      treat this as a partial signal, not a full Smart Money Score. Click any row to see the exact inputs used.
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th>Symbol</th><th>Security</th><th>Partial score (of 35)</th><th>Deal activity (of 20)</th><th>Accumulation (of 15)</th><th>Details</th>
        </tr></thead>
        <tbody id="smsBody"></tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <h2>Investor intelligence <span class="section-actions"><button class="export-btn" data-export="investor">Export Excel</button></span></h2>
    <div class="note">Search any investor name that has appeared in a bulk/block deal &#8211; not limited to the watchlist. Behaviour labels and new-entry/exit detection use each investor's <em>full</em> transaction history (not just the selected date range) to determine prior position, so they are accurate even near the edge of your date filter. Round-trip rows are excluded from all figures below.</div>
    <div class="investor-search-wrap">
      <input type="text" id="investorSearchBox" placeholder="Type an investor name...">
      <div class="investor-suggestions" id="investorSuggestions"></div>
    </div>
    <div id="investorDetailWrap"></div>
  </div>

  <div class="section">
    <h2>All deals <span class="section-actions"><span class="count-pill" id="dealsCount"></span><button class="export-btn" data-export="alldeals">Export Excel</button></span></h2>
    <div class="table-scroll">
      <table>
        <thead><tr>
          <th data-col="date">Date <span class="arrow" id="arrow-date"></span></th>
          <th data-col="exchange">Exch <span class="arrow" id="arrow-exchange"></span></th>
          <th data-col="deal_type">Type <span class="arrow" id="arrow-deal_type"></span></th>
          <th data-col="symbol">Symbol <span class="arrow" id="arrow-symbol"></span></th>
          <th data-col="security_name">Security <span class="arrow" id="arrow-security_name"></span></th>
          <th data-col="client_name">Client <span class="arrow" id="arrow-client_name"></span></th>
          <th data-col="buy_sell">B/S <span class="arrow" id="arrow-buy_sell"></span></th>
          <th data-col="quantity">Qty <span class="arrow" id="arrow-quantity"></span></th>
          <th data-col="price">Price <span class="arrow" id="arrow-price"></span></th>
          <th data-col="return_1d_pct">1D % <span class="arrow" id="arrow-return_1d_pct"></span></th>
          <th data-col="return_1w_pct">1W % <span class="arrow" id="arrow-return_1w_pct"></span></th>
          <th data-col="return_1m_pct">1M % <span class="arrow" id="arrow-return_1m_pct"></span></th>
        </tr></thead>
        <tbody id="dealsBody"></tbody>
      </table>
    </div>
    <div class="pagination">
      <button id="prevPage">Prev</button>
      <span id="pageInfo"></span>
      <button id="nextPage">Next</button>
    </div>
  </div>

<script>
const ALL_DEALS = DEALS_JSON_PLACEHOLDER;
const WATCHLIST = WATCHLIST_JSON_PLACEHOLDER;

let currentRangeDays = 365;
let filterFromISO = null;  // yyyy-mm-dd or null
let filterToISO = null;    // yyyy-mm-dd or null
let sortCol = 'date';
let sortDir = 'desc';
let scripSortCol = 'total_value';
let scripSortDir = 'desc';
let trackSortCol = 'avg_1w';
let trackSortDir = 'desc';
let currentPage = 1;
const PAGE_SIZE = 50;
let dealsChartInstance = null;
let stocksChartInstance = null;
let accumMinThreshold = 3;
let selectedInvestor = null;

// Latest computed rows per section, refreshed on every render(), used by
// the Excel export buttons so exports always reflect the numbers
// currently on screen (same filters, same date range).
let latestExport = {
  alldeals: [], scrip: [], watchlist: [], track: [], rising: [],
  significance: [], accum: [], sms: [], investor: [], watchlistTrades: [], scripTrades: [],
};

function toISODate(d) {
  return d.toISOString().slice(0, 10);
}

function setDateRangeFromPreset(rangeDays) {
  currentRangeDays = rangeDays;
  if (rangeDays === 'all') {
    filterFromISO = null;
    filterToISO = null;
  } else {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - rangeDays);
    filterFromISO = toISODate(from);
    filterToISO = toISODate(to);
  }
  document.getElementById('dateFrom').value = filterFromISO || '';
  document.getElementById('dateTo').value = filterToISO || '';
}

// Applies to every section on the page (deal table, charts, watchlist,
// repeated accumulation, investor intelligence, smart money score) --
// there is exactly one date filter state, not a per-section one.
function getFilteredDeals() {
  const search = document.getElementById('searchBox').value.trim().toLowerCase();
  const exchange = document.getElementById('exchangeFilter').value;
  const dealType = document.getElementById('dealTypeFilter').value;
  const buySell = document.getElementById('buySellFilter').value;
  const watchlistOnly = document.getElementById('watchlistFilter').value === 'yes';

  return ALL_DEALS.filter(d => {
    if (filterFromISO && d.date && d.date < filterFromISO) return false;
    if (filterToISO && d.date && d.date > filterToISO) return false;
    if (exchange && d.exchange !== exchange) return false;
    if (dealType && d.deal_type !== dealType) return false;
    if (buySell && d.buy_sell !== buySell) return false;
    if (watchlistOnly && !d.matched_investor) return false;
    if (search) {
      const hay = (d.symbol + ' ' + d.security_name + ' ' + d.client_name).toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });
}

// Excludes round-trip rows (same investor+stock+date with both a BUY and
// a SELL -- almost certainly prop/arbitrage, not directional conviction).
// Used by every *scoring* feature; the raw deal table below still shows
// these rows (flagged with a badge) for full auditability.
function scorableDeals(deals) {
  return deals.filter(d => !d.is_round_trip && d.buy_sell);
}

function sortDeals(deals) {
  const dir = sortDir === 'asc' ? 1 : -1;
  return [...deals].sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (sortCol === 'quantity' || sortCol === 'price' || sortCol.startsWith('return_')) {
      av = (av === null || av === undefined) ? -Infinity : parseFloat(av);
      bv = (bv === null || bv === undefined) ? -Infinity : parseFloat(bv);
    }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
}

function pctBadge(val) {
  if (val === null || val === undefined || isNaN(val)) return '<span style="color:#8b93a7">-</span>';
  const cls = val >= 0 ? 'buy' : 'sell';
  const sign = val >= 0 ? '+' : '';
  return '<span class="badge ' + cls + '">' + sign + val.toFixed(2) + '%</span>';
}

function groupByScripDate(deals) {
  // Merges multiple investors buying/selling the same scrip on the same
  // date+buy_sell into a single row, since price/return figures are
  // identical for all of them (the move belongs to the stock, not the
  // individual investor) -- avoids showing the same scrip/date repeated
  // once per investor.
  const map = {};
  deals.forEach(d => {
    const key = [d.date_raw, d.exchange, d.deal_type, d.symbol, d.buy_sell].join('|');
    if (!map[key]) {
      map[key] = {
        date_raw: d.date_raw, date: d.date, exchange: d.exchange, deal_type: d.deal_type,
        symbol: d.symbol, security_name: d.security_name, buy_sell: d.buy_sell,
        clients: [], quantity: 0, price_sum: 0, price_count: 0,
        matched_investor: '', return_1d_pct: d.return_1d_pct,
        return_1w_pct: d.return_1w_pct, return_1m_pct: d.return_1m_pct,
        is_round_trip: false,
      };
    }
    const g = map[key];
    if (d.client_name) g.clients.push(d.client_name);
    g.quantity += parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price);
    if (!isNaN(p)) { g.price_sum += p; g.price_count += 1; }
    if (d.matched_investor && !g.matched_investor) g.matched_investor = d.matched_investor;
    if (d.is_round_trip) g.is_round_trip = true;
  });
  return Object.values(map).map(g => {
    const uniqueClients = [...new Set(g.clients)];
    return {
      ...g,
      client_name: uniqueClients.length > 1
        ? (uniqueClients[0] + ' +' + (uniqueClients.length - 1) + ' more')
        : (uniqueClients[0] || ''),
      client_title: uniqueClients.join(', '),
      investor_count: uniqueClients.length,
      price: g.price_count ? (g.price_sum / g.price_count) : 0,
    };
  });
}

function populateDropdowns() {
  const types = [...new Set(ALL_DEALS.map(d => d.deal_type))].filter(Boolean).sort();
  const dealTypeSel = document.getElementById('dealTypeFilter');
  types.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    dealTypeSel.appendChild(opt);
  });

  const bs = [...new Set(ALL_DEALS.map(d => d.buy_sell))].filter(Boolean).sort();
  const bsSel = document.getElementById('buySellFilter');
  bs.forEach(b => {
    const opt = document.createElement('option');
    opt.value = b; opt.textContent = b;
    bsSel.appendChild(opt);
  });
}

function render() {
  const filtered = getFilteredDeals();
  const sorted = sortDeals(filtered);

  const totalValueCr = filtered.reduce((sum, d) => {
    const q = parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price) || 0;
    return sum + (q * p);
  }, 0) / 10000000;
  const hits = filtered.filter(d => d.matched_investor);

  const clientCounts = {};
  filtered.forEach(d => {
    if (!d.matched_investor && d.client_name) {
      clientCounts[d.client_name] = clientCounts[d.client_name] || [];
      clientCounts[d.client_name].push(d);
    }
  });
  const rising = Object.entries(clientCounts)
    .filter(([_, deals]) => deals.length >= 3)
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 20);
  latestExport.rising = rising.map(([name, deals]) => ({
    Name: name, 'Deal count': deals.length, Stocks: [...new Set(deals.map(d => d.symbol))].join(', '),
  }));

  document.getElementById('statTotal').textContent = filtered.length;
  document.getElementById('statValue').textContent = totalValueCr.toLocaleString(undefined, {maximumFractionDigits: 1});
  document.getElementById('statHits').textContent = hits.length;
  document.getElementById('statRising').textContent = rising.length;
  document.getElementById('dealsCount').textContent = groupByScripDate(sorted).length + ' rows (' + filtered.length + ' individual deals)';
  document.getElementById('risingCount').textContent = rising.length + ' names';
  document.getElementById('watchlistCount').textContent = WATCHLIST.length + ' tracked';

  const watchlistBody = document.getElementById('watchlistBody');
  const watchlistRows = WATCHLIST.map(name => {
    const count = filtered.filter(d => d.matched_investor === name).length;
    return { name, count };
  }).sort((a, b) => b.count - a.count);
  latestExport.watchlist = watchlistRows.map(w => ({
    Investor: w.name, 'Hits in range': w.count, Status: w.count > 0 ? 'Active' : 'No hits',
  }));
  latestExport.alldeals = filtered.map(d => ({
    Date: d.date_raw, Exchange: d.exchange, Type: d.deal_type, Symbol: d.symbol,
    Security: d.security_name, Client: d.client_name, 'B/S': d.buy_sell || d.buy_sell_raw,
    Quantity: d.quantity, Price: d.price, 'Value (Cr)': d.value_cr,
    'Round-trip (excluded from scoring)': d.is_round_trip ? 'Yes' : 'No',
    'Watchlist match': d.matched_investor || '', '1D %': d.return_1d_pct,
    '1W %': d.return_1w_pct, '1M %': d.return_1m_pct,
  }));
  watchlistBody.innerHTML = watchlistRows.map(w =>
    '<tr><td>' + w.name + '</td><td>' + w.count + '</td><td>' +
    (w.count > 0 ? '<span class="badge hit">Active</span>' : '<span class="badge" style="color:#8b93a7">No hits</span>') +
    '</td></tr>'
  ).join('') || '<tr><td colspan="3" class="empty">No watchlist entries.</td></tr>';

  // Investor track record: average return after deal, per watchlisted investor
  const trackRows = WATCHLIST.map(name => {
    const investorDeals = filtered.filter(d => d.matched_investor === name);
    const avg = (key) => {
      const vals = investorDeals.map(d => d[key]).filter(v => v !== null && v !== undefined && !isNaN(v));
      if (vals.length === 0) return null;
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    };
    const winRate1w = (() => {
      const vals = investorDeals.map(d => d.return_1w_pct).filter(v => v !== null && v !== undefined && !isNaN(v));
      if (vals.length === 0) return null;
      const wins = vals.filter(v => v > 0).length;
      return (wins / vals.length) * 100;
    })();
    const dealsWithData = investorDeals.filter(d =>
      d.return_1d_pct !== null || d.return_1w_pct !== null || d.return_1m_pct !== null
    ).length;
    return {
      name,
      deals_with_data: dealsWithData,
      avg_1d: avg('return_1d_pct'),
      avg_1w: avg('return_1w_pct'),
      avg_1m: avg('return_1m_pct'),
      win_rate_1w: winRate1w,
    };
  });
  const trackDir = trackSortDir === 'asc' ? 1 : -1;
  trackRows.sort((a, b) => {
    let av = a[trackSortCol], bv = b[trackSortCol];
    if (trackSortCol === 'name') return av.localeCompare(bv) * trackDir;
    av = (av === null || av === undefined) ? -Infinity : av;
    bv = (bv === null || bv === undefined) ? -Infinity : bv;
    return (av - bv) * trackDir;
  });

  const anyPriceData = ALL_DEALS.some(d => d.return_1d_pct !== null || d.return_1w_pct !== null || d.return_1m_pct !== null);
  latestExport.track = trackRows.map(t => ({
    Investor: t.name, 'Deals w/ price data': t.deals_with_data,
    'Avg 1D %': t.avg_1d, 'Avg 1W %': t.avg_1w, 'Avg 1M %': t.avg_1m, 'Win rate (1W) %': t.win_rate_1w,
  }));
  document.getElementById('trackRecordNote').textContent = anyPriceData ? '' : '(run price_tracker.py to populate)';
  const trackBody = document.getElementById('trackRecordBody');
  trackBody.innerHTML = trackRows.map(t =>
    '<tr><td>' + t.name + '</td><td>' + t.deals_with_data + '</td><td>' +
    pctBadge(t.avg_1d) + '</td><td>' + pctBadge(t.avg_1w) + '</td><td>' + pctBadge(t.avg_1m) +
    '</td><td>' + (t.win_rate_1w === null ? '<span style="color:#8b93a7">-</span>' : t.win_rate_1w.toFixed(0) + '%') +
    '</td></tr>'
  ).join('') || '<tr><td colspan="6" class="empty">No watchlist entries.</td></tr>';

  ['name','deals_with_data','avg_1d','avg_1w','avg_1m','win_rate_1w'].forEach(col => {
    const el = document.getElementById('arrow-track-' + col);
    if (el) el.textContent = (col === trackSortCol) ? (trackSortDir === 'asc' ? '\u25b2' : '\u25bc') : '';
  });

  const risingBody = document.getElementById('risingBody');
  risingBody.innerHTML = rising.map(([name, deals]) => {
    const stocks = [...new Set(deals.map(d => d.symbol))].join(', ');
    return '<tr><td>' + name + '</td><td>' + deals.length + '</td><td>' + stocks + '</td></tr>';
  }).join('') || '<tr><td colspan="3" class="empty">No recurring non-watchlisted names in this range yet.</td></tr>';

  // Scrip-wise summary
  const scripMap = {};
  filtered.forEach(d => {
    if (!d.symbol) return;
    if (!scripMap[d.symbol]) {
      scripMap[d.symbol] = { symbol: d.symbol, security_name: d.security_name, deals: 0, buy_value: 0, sell_value: 0 };
    }
    const entry = scripMap[d.symbol];
    entry.deals += 1;
    const q = parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price) || 0;
    const valueCr = (q * p) / 10000000;
    if (d.buy_sell === 'BUY') entry.buy_value += valueCr;
    else if (d.buy_sell === 'SELL') entry.sell_value += valueCr;
    // unclassified buy_sell values are counted in `deals` but excluded from
    // buy/sell value split, rather than silently defaulting to sell.
  });
  let scripRows = Object.values(scripMap).map(s => ({
    ...s,
    net_value: s.buy_value - s.sell_value,
    total_value: s.buy_value + s.sell_value,
  }));
  const scripDir = scripSortDir === 'asc' ? 1 : -1;
  scripRows.sort((a, b) => {
    let av = a[scripSortCol], bv = b[scripSortCol];
    if (typeof av === 'string') {
      return av.localeCompare(bv) * scripDir;
    }
    return (av - bv) * scripDir;
  });

  document.getElementById('scripCount').textContent = scripRows.length + ' scrips';
  latestExport.scrip = scripRows.map(s => ({
    Symbol: s.symbol, Security: s.security_name || '', Deals: s.deals,
    'Buy value (Cr)': s.buy_value, 'Sell value (Cr)': s.sell_value,
    'Net value (Cr)': s.net_value, 'Total value (Cr)': s.total_value,
  }));
  const scripBody = document.getElementById('scripBody');
  scripBody.innerHTML = scripRows.map(s =>
    '<tr><td>' + s.symbol + '</td><td>' + (s.security_name || '') + '</td><td>' + s.deals +
    '</td><td>' + s.buy_value.toLocaleString(undefined, {maximumFractionDigits: 2}) +
    '</td><td>' + s.sell_value.toLocaleString(undefined, {maximumFractionDigits: 2}) +
    '</td><td>' + (s.net_value >= 0 ? '<span class="badge buy">+' : '<span class="badge sell">') + s.net_value.toLocaleString(undefined, {maximumFractionDigits: 2}) + '</span>' +
    '</td><td>' + s.total_value.toLocaleString(undefined, {maximumFractionDigits: 2}) + '</td></tr>'
  ).join('') || '<tr><td colspan="7" class="empty">No deals match the current filters.</td></tr>';

  ['symbol','security_name','deals','buy_value','sell_value','net_value','total_value'].forEach(col => {
    const el = document.getElementById('arrow-scrip-' + col);
    if (el) el.textContent = (col === scripSortCol) ? (scripSortDir === 'asc' ? '\u25b2' : '\u25bc') : '';
  });

  const groupedDeals = groupByScripDate(sorted);

  const totalPages = Math.max(1, Math.ceil(groupedDeals.length / PAGE_SIZE));
  if (currentPage > totalPages) currentPage = totalPages;
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageDeals = groupedDeals.slice(start, start + PAGE_SIZE);

  const dealsBody = document.getElementById('dealsBody');
  dealsBody.innerHTML = pageDeals.map(d =>
    '<tr><td>' + d.date_raw + '</td><td>' + d.exchange + '</td><td>' + d.deal_type + '</td><td>' + d.symbol +
    '</td><td>' + d.security_name + '</td><td title="' + d.client_title + '">' + d.client_name +
    (d.investor_count > 1 ? ' <span class="badge" style="color:#8b93a7">' + d.investor_count + ' investors</span>' : '') +
    (d.matched_investor ? ' <span class="badge hit">watchlist</span>' : '') +
    (d.is_round_trip ? ' <span class="badge roundtrip" title="Same investor bought and sold this stock on this date -- excluded from scoring">round-trip</span>' : '') + '</td><td>' +
    ((d.buy_sell === 'BUY' || d.buy_sell === 'B') ? '<span class="badge buy">' + d.buy_sell + '</span>' : '<span class="badge sell">' + d.buy_sell + '</span>') +
    '</td><td>' + Number(d.quantity).toLocaleString() + '</td><td>' + d.price.toFixed(2) +
    '</td><td>' + pctBadge(d.return_1d_pct) + '</td><td>' + pctBadge(d.return_1w_pct) + '</td><td>' + pctBadge(d.return_1m_pct) + '</td></tr>'
  ).join('') || '<tr><td colspan="12" class="empty">No deals match the current filters.</td></tr>';

  document.getElementById('pageInfo').textContent = 'Page ' + currentPage + ' of ' + totalPages;
  document.getElementById('prevPage').disabled = currentPage <= 1;
  document.getElementById('nextPage').disabled = currentPage >= totalPages;

  ['date','exchange','deal_type','symbol','security_name','client_name','buy_sell','quantity','price','return_1d_pct','return_1w_pct','return_1m_pct'].forEach(col => {
    const el = document.getElementById('arrow-' + col);
    if (el) el.textContent = (col === sortCol) ? (sortDir === 'asc' ? '\u25b2' : '\u25bc') : '';
  });

  const dayValues = {};
  filtered.forEach(d => {
    if (!d.date) return;
    const q = parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price) || 0;
    const valueCr = (q * p) / 10000000;
    dayValues[d.date] = (dayValues[d.date] || 0) + valueCr;
  });
  const sortedDays = Object.keys(dayValues).sort();

  const stockValues = {};
  filtered.forEach(d => {
    const label = d.security_name ? (d.symbol + ' (' + d.security_name + ')') : d.symbol;
    if (!label) return;
    const q = parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price) || 0;
    stockValues[label] = (stockValues[label] || 0) + (q * p) / 10000000;
  });
  const topStocks = Object.entries(stockValues)
    .map(([label, val]) => [label, Math.round(val * 100) / 100])
    .sort((a,b) => b[1]-a[1]).slice(0, 10);

  if (dealsChartInstance) dealsChartInstance.destroy();
  dealsChartInstance = new Chart(document.getElementById('dealsChart'), {
    type: 'line',
    data: { labels: sortedDays, datasets: [{ label: 'Value (\u20b9 Cr)', data: sortedDays.map(d => Math.round(dayValues[d] * 100) / 100),
      borderColor: '#5b8def', backgroundColor: 'rgba(91,141,239,0.1)', fill: true, tension: 0.3 }] },
    options: { plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => '\u20b9' + ctx.parsed.y.toLocaleString(undefined, {maximumFractionDigits: 2}) + ' Cr' } } },
      scales: { x: { ticks: { color: '#8b93a7' }, grid: { color: '#262b3a' } },
                y: { ticks: { color: '#8b93a7', callback: (v) => '\u20b9' + v + 'Cr' }, grid: { color: '#262b3a' } } } }
  });

  if (stocksChartInstance) stocksChartInstance.destroy();
  stocksChartInstance = new Chart(document.getElementById('stocksChart'), {
    type: 'bar',
    data: { labels: topStocks.map(s => s[0]), datasets: [{ label: 'Value (\u20b9 Cr)', data: topStocks.map(s => s[1]),
      backgroundColor: '#3ec97a' }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => '\u20b9' + ctx.parsed.x.toLocaleString(undefined, {maximumFractionDigits: 2}) + ' Cr' } } },
      scales: { x: { ticks: { color: '#8b93a7', callback: (v) => '\u20b9' + v + 'Cr' }, grid: { color: '#262b3a' } },
                y: { ticks: { color: '#8b93a7' }, grid: { display: false } } } }
  });

  renderSignificance(filtered);
  renderAccumulation(filtered);
  renderSmartMoneyScore(filtered);
  renderInvestorDetail();
  renderWatchlistTrades();
  renderScripTrades();
}

// ---- Deal Significance ----
function renderSignificance(filtered) {
  const scorable = scorableDeals(filtered);

  // Historical value distribution per symbol, from the FULL dataset
  // (not just the filtered range) so the percentile is stable and not
  // an artifact of whatever window is currently selected.
  const historyBySymbol = {};
  scorableDeals(ALL_DEALS).forEach(d => {
    if (d.value_cr === null || d.value_cr === undefined || !d.symbol) return;
    (historyBySymbol[d.symbol] = historyBySymbol[d.symbol] || []).push(d.value_cr);
  });

  const withValue = scorable.filter(d => d.value_cr !== null && d.value_cr !== undefined);
  const top = [...withValue].sort((a, b) => b.value_cr - a.value_cr).slice(0, 25);

  const body = document.getElementById('significanceBody');
  document.getElementById('significanceCount').textContent = top.length + ' shown (of ' + withValue.length + ' scorable deals in range)';
  const exportRows = [];
  body.innerHTML = top.map(d => {
    const hist = historyBySymbol[d.symbol] || [];
    let sizeLabel = '<span class="insufficient">Only deal on record for this stock</span>';
    let sizeLabelPlain = 'Only deal on record for this stock';
    if (hist.length > 1) {
      const below = hist.filter(v => v <= d.value_cr).length;
      const pct = Math.round((below / hist.length) * 100);
      sizeLabel = pct + 'th percentile of ' + hist.length + ' recorded deals in this stock';
      sizeLabelPlain = sizeLabel;
    }
    exportRows.push({
      Date: d.date_raw, Symbol: d.symbol, Investor: d.client_name, 'B/S': d.buy_sell,
      'Value (Cr)': d.value_cr, "Size vs stock's own history": sizeLabelPlain,
    });
    return '<tr><td>' + d.date_raw + '</td><td>' + d.symbol + '</td><td>' + d.client_name +
      '</td><td>' + ((d.buy_sell === 'BUY') ? '<span class="badge buy">BUY</span>' : '<span class="badge sell">SELL</span>') +
      '</td><td>' + d.value_cr.toLocaleString(undefined, {maximumFractionDigits: 2}) +
      '</td><td>' + sizeLabel + '</td></tr>';
  }).join('') || '<tr><td colspan="6" class="empty">No scorable deals with a computable value in this range.</td></tr>';
  latestExport.significance = exportRows;
}

// ---- Repeated Accumulation Engine ----
function renderAccumulation(filtered) {
  const scorable = scorableDeals(filtered);
  const bySymbol = {};
  scorable.forEach(d => {
    if (!d.symbol) return;
    if (!bySymbol[d.symbol]) {
      bySymbol[d.symbol] = {
        symbol: d.symbol, security_name: d.security_name, transactions: 0,
        investors: new Set(), buy_value: 0, sell_value: 0,
        first: d.date_raw, last: d.date_raw, price_sum: 0, price_count: 0,
      };
    }
    const g = bySymbol[d.symbol];
    g.transactions += 1;
    if (d.client_name) g.investors.add(d.client_name);
    if (d.value_cr !== null && d.value_cr !== undefined) {
      if (d.buy_sell === 'BUY') g.buy_value += d.value_cr; else if (d.buy_sell === 'SELL') g.sell_value += d.value_cr;
    }
    const p = parseFloat(d.price);
    if (!isNaN(p)) { g.price_sum += p; g.price_count += 1; }
    if (d.date < g.first || !g.first) g.first = d.date_raw;
    // date strings here are raw (DD-MON-YYYY); compare via ISO date field instead
  });
  // Recompute first/last correctly using ISO date field.
  const isoBySymbol = {};
  scorable.forEach(d => {
    if (!d.symbol) return;
    if (!isoBySymbol[d.symbol]) isoBySymbol[d.symbol] = [];
    isoBySymbol[d.symbol].push(d);
  });
  Object.keys(bySymbol).forEach(sym => {
    const rows = [...isoBySymbol[sym]].sort((a, b) => a.date.localeCompare(b.date));
    bySymbol[sym].first = rows[0].date_raw;
    bySymbol[sym].last = rows[rows.length - 1].date_raw;
  });

  let rows = Object.values(bySymbol).filter(g => g.transactions >= accumMinThreshold);
  rows.forEach(g => {
    g.net_value = g.buy_value - g.sell_value;
    g.avg_price = g.price_count ? (g.price_sum / g.price_count) : null;
    g.investor_count = g.investors.size;
  });
  rows.sort((a, b) => (b.transactions - a.transactions) || (b.net_value - a.net_value));

  document.getElementById('accumCount').textContent = rows.length + ' stocks meet the ' + accumMinThreshold + '+ threshold';
  const body = document.getElementById('accumBody');
  body.innerHTML = rows.map(g =>
    '<tr><td>' + g.symbol + '</td><td>' + (g.security_name || '') + '</td><td>' + g.transactions +
    '</td><td>' + g.investor_count +
    '</td><td>' + g.buy_value.toLocaleString(undefined, {maximumFractionDigits: 2}) +
    '</td><td>' + g.sell_value.toLocaleString(undefined, {maximumFractionDigits: 2}) +
    '</td><td>' + (g.net_value >= 0 ? '<span class="badge buy">+' : '<span class="badge sell">') + g.net_value.toLocaleString(undefined, {maximumFractionDigits: 2}) + '</span>' +
    '</td><td>' + g.first + '</td><td>' + g.last +
    '</td><td>' + (g.avg_price !== null ? g.avg_price.toFixed(2) : '-') +
    '</td><td><span class="badge na">N/A</span></td></tr>'
  ).join('') || '<tr><td colspan="11" class="empty">No stocks meet this threshold in the selected range.</td></tr>';
  latestExport.accum = rows.map(g => ({
    Symbol: g.symbol, Security: g.security_name || '', Transactions: g.transactions,
    Investors: g.investor_count, 'Buy value (Cr)': g.buy_value, 'Sell value (Cr)': g.sell_value,
    'Net value (Cr)': g.net_value, 'First txn': g.first, 'Latest txn': g.last,
    'Avg. price': g.avg_price, 'Current price': 'N/A (no live feed)',
  }));
}

// ---- Smart Money Score (partial, deal-data only) ----
// Formula (fully documented so it is auditable, per requirement):
//   Deal Activity (max 20):
//     - Frequency component (max 10): min(total scorable transactions / 10, 1) * 10
//     - Net buy-skew component (max 10): ((buyValue - sellValue) / (buyValue + sellValue)) mapped
//       from [-1, 1] to [0, 10]. If buyValue+sellValue is 0 (no valued deals), skew = 0.
//   Accumulation Pattern (max 15):
//     - Distinct buying dates component (max 8): min(distinct BUY dates / 5, 1) * 8
//     - Distinct buying investors component (max 7): min(distinct investors who bought / 5, 1) * 7
//   Investor Quality, Fundamental, Technical, Valuation, Risk: not computed (no data source) --
//   shown as "Insufficient data", not scored as zero, and not included in the 35-point max.
function computeSmartMoneyPartial(scorable) {
  const bySymbol = {};
  scorable.forEach(d => {
    if (!d.symbol) return;
    if (!bySymbol[d.symbol]) {
      bySymbol[d.symbol] = {
        symbol: d.symbol, security_name: d.security_name, total_txns: 0,
        buy_value: 0, sell_value: 0, buy_dates: new Set(), buy_investors: new Set(),
      };
    }
    const g = bySymbol[d.symbol];
    g.total_txns += 1;
    if (d.value_cr !== null && d.value_cr !== undefined) {
      if (d.buy_sell === 'BUY') g.buy_value += d.value_cr; else if (d.buy_sell === 'SELL') g.sell_value += d.value_cr;
    }
    if (d.buy_sell === 'BUY') {
      if (d.date) g.buy_dates.add(d.date);
      if (d.client_name) g.buy_investors.add(d.client_name);
    }
  });
  return Object.values(bySymbol).map(g => {
    const freqComponent = Math.min(g.total_txns / 10, 1) * 10;
    const totalVal = g.buy_value + g.sell_value;
    const skew = totalVal > 0 ? (g.buy_value - g.sell_value) / totalVal : 0;
    const skewComponent = ((skew + 1) / 2) * 10;
    const dealActivity = Math.round((freqComponent + skewComponent) * 10) / 10;

    const dateComponent = Math.min(g.buy_dates.size / 5, 1) * 8;
    const investorComponent = Math.min(g.buy_investors.size / 5, 1) * 7;
    const accumulation = Math.round((dateComponent + investorComponent) * 10) / 10;

    return {
      symbol: g.symbol, security_name: g.security_name,
      total_txns: g.total_txns, buy_dates: g.buy_dates.size, buy_investors: g.buy_investors.size,
      buy_value: g.buy_value, sell_value: g.sell_value, skew,
      dealActivity, accumulation, total: Math.round((dealActivity + accumulation) * 10) / 10,
    };
  }).sort((a, b) => b.total - a.total);
}

function renderSmartMoneyScore(filtered) {
  const scorable = scorableDeals(filtered);
  const rows = computeSmartMoneyPartial(scorable).slice(0, 25);
  const body = document.getElementById('smsBody');
  body.innerHTML = rows.map(r => {
    const details = '<details><summary>Show inputs</summary><div class="score-explain">' +
      '<div class="score-bar-row"><span>Scorable transactions in range</span><span class="val">' + r.total_txns + '</span></div>' +
      '<div class="score-bar-row"><span>Buy value (\u20b9 Cr)</span><span class="val">' + r.buy_value.toFixed(2) + '</span></div>' +
      '<div class="score-bar-row"><span>Sell value (\u20b9 Cr)</span><span class="val">' + r.sell_value.toFixed(2) + '</span></div>' +
      '<div class="score-bar-row"><span>Net buy skew (-1 to +1)</span><span class="val">' + r.skew.toFixed(2) + '</span></div>' +
      '<div class="score-bar-row"><span>Distinct buying dates</span><span class="val">' + r.buy_dates + '</span></div>' +
      '<div class="score-bar-row"><span>Distinct investors buying</span><span class="val">' + r.buy_investors + '</span></div>' +
      '<div class="score-bar-row"><span>Investor Quality</span><span class="val insufficient">Insufficient data</span></div>' +
      '<div class="score-bar-row"><span>Fundamental Quality</span><span class="val insufficient">Insufficient data</span></div>' +
      '<div class="score-bar-row"><span>Technical Trend</span><span class="val insufficient">Insufficient data</span></div>' +
      '<div class="score-bar-row"><span>Valuation</span><span class="val insufficient">Insufficient data</span></div>' +
      '<div class="score-bar-row"><span>Risk adjustment</span><span class="val insufficient">Insufficient data</span></div>' +
      '</div></details>';
    return '<tr><td>' + r.symbol + '</td><td>' + (r.security_name || '') + '</td><td><strong>' + r.total + '</strong>/35</td>' +
      '<td>' + r.dealActivity + '/20</td><td>' + r.accumulation + '/15</td><td>' + details + '</td></tr>';
  }).join('') || '<tr><td colspan="6" class="empty">No scorable deals in the selected range.</td></tr>';
  latestExport.sms = rows.map(r => ({
    Symbol: r.symbol, Security: r.security_name || '', 'Partial score (of 35)': r.total,
    'Deal activity (of 20)': r.dealActivity, 'Accumulation (of 15)': r.accumulation,
    'Scorable transactions': r.total_txns, 'Buy value (Cr)': r.buy_value, 'Sell value (Cr)': r.sell_value,
    'Net buy skew (-1 to 1)': r.skew, 'Distinct buying dates': r.buy_dates, 'Distinct investors buying': r.buy_investors,
    'Investor Quality': 'Insufficient data', 'Fundamental Quality': 'Insufficient data',
    'Technical Trend': 'Insufficient data', 'Valuation': 'Insufficient data', 'Risk adjustment': 'Insufficient data',
  }));
}

// ---- Investor Intelligence ----
function computeInvestorEvents(investorName) {
  const allInvDeals = scorableDeals(ALL_DEALS).filter(d => d.client_name === investorName);
  const bySymbol = {};
  allInvDeals.forEach(d => { (bySymbol[d.symbol] = bySymbol[d.symbol] || []).push(d); });
  const events = [];
  Object.values(bySymbol).forEach(deals => {
    const sorted = [...deals].sort((a, b) => a.date.localeCompare(b.date));
    let pos = 0;
    let everExited = false;
    sorted.forEach(d => {
      const qty = parseFloat(d.quantity) || 0;
      const before = pos;
      if (d.buy_sell === 'BUY') pos += qty; else if (d.buy_sell === 'SELL') pos -= qty;
      let behaviour = d.buy_sell;
      if (before <= 0 && pos > 0) {
        behaviour = everExited ? 'RE-ENTERED' : 'NEW ENTRY';
      } else if (before > 0 && pos <= 0 && d.buy_sell === 'SELL') {
        behaviour = 'EXITED';
        everExited = true;
      } else if (d.buy_sell === 'BUY' && pos > before) {
        behaviour = 'ACCUMULATING';
      } else if (d.buy_sell === 'SELL' && pos < before && pos > 0) {
        behaviour = 'REDUCING';
      }
      events.push(Object.assign({}, d, { position_before: before, position_after: pos, behaviour }));
    });
  });
  return events;
}

function behaviourTagHTML(b) {
  const cls = b.toLowerCase().replace(/\\s+/g, '-');
  return '<span class="behaviour-tag ' + cls + '">' + b + '</span>';
}

function renderInvestorDetail() {
  const wrap = document.getElementById('investorDetailWrap');
  if (!selectedInvestor) {
    wrap.innerHTML = '<div class="note">No investor selected yet.</div>';
    latestExport.investor = [];
    return;
  }
  const allEvents = computeInvestorEvents(selectedInvestor);
  const events = allEvents.filter(d => {
    if (filterFromISO && d.date && d.date < filterFromISO) return false;
    if (filterToISO && d.date && d.date > filterToISO) return false;
    return true;
  });

  const buyEvents = events.filter(e => e.buy_sell === 'BUY');
  const sellEvents = events.filter(e => e.buy_sell === 'SELL');
  const buyValue = buyEvents.reduce((s, e) => s + (e.value_cr || 0), 0);
  const sellValue = sellEvents.reduce((s, e) => s + (e.value_cr || 0), 0);
  const stocksBought = new Set(buyEvents.map(e => e.symbol));
  const stocksSold = new Set(sellEvents.map(e => e.symbol));
  const newEntries = events.filter(e => e.behaviour === 'NEW ENTRY' || e.behaviour === 'RE-ENTERED').length;
  const exits = events.filter(e => e.behaviour === 'EXITED').length;

  const symbolBuyCounts = {};
  buyEvents.forEach(e => { symbolBuyCounts[e.symbol] = (symbolBuyCounts[e.symbol] || 0) + 1; });
  const repeatedAccumulation = Object.values(symbolBuyCounts).filter(c => c >= 2).length;
  const symbolSellCounts = {};
  sellEvents.forEach(e => { symbolSellCounts[e.symbol] = (symbolSellCounts[e.symbol] || 0) + 1; });
  const repeatedSelling = Object.values(symbolSellCounts).filter(c => c >= 2).length;

  const avg = (key) => {
    const vals = events.map(e => e[key]).filter(v => v !== null && v !== undefined && !isNaN(v));
    if (vals.length === 0) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const winRate1w = (() => {
    const vals = events.map(e => e.return_1w_pct).filter(v => v !== null && v !== undefined && !isNaN(v));
    if (vals.length === 0) return null;
    return (vals.filter(v => v > 0).length / vals.length) * 100;
  })();
  const anyPerfData = events.some(e => e.return_1d_pct !== null || e.return_1w_pct !== null || e.return_1m_pct !== null);

  const sortedEvents = [...events].sort((a, b) => b.date.localeCompare(a.date));

  if (sortedEvents.length === 0) {
    wrap.innerHTML = '<h3 style="margin:0 0 10px;font-size:15px;">' + selectedInvestor + '</h3>' +
      '<div class="empty">No transactions for this investor in the selected date range.</div>';
    latestExport.investor = [];
    return;
  }

  wrap.innerHTML =
    '<h3 style="margin:0 0 10px;font-size:15px;">' + selectedInvestor + '</h3>' +
    '<div class="investor-detail-grid">' +
      '<div class="mini-stat"><div class="v">' + events.length + '</div><div class="l">Total transactions (in range)</div></div>' +
      '<div class="mini-stat"><div class="v">' + buyEvents.length + '</div><div class="l">Buy transactions</div></div>' +
      '<div class="mini-stat"><div class="v">' + sellEvents.length + '</div><div class="l">Sell transactions</div></div>' +
      '<div class="mini-stat"><div class="v">\u20b9' + buyValue.toLocaleString(undefined, {maximumFractionDigits: 2}) + ' Cr</div><div class="l">Total buy value</div></div>' +
      '<div class="mini-stat"><div class="v">\u20b9' + sellValue.toLocaleString(undefined, {maximumFractionDigits: 2}) + ' Cr</div><div class="l">Total sell value</div></div>' +
      '<div class="mini-stat"><div class="v">\u20b9' + (buyValue - sellValue).toLocaleString(undefined, {maximumFractionDigits: 2}) + ' Cr</div><div class="l">Net value</div></div>' +
      '<div class="mini-stat"><div class="v">' + stocksBought.size + '</div><div class="l">Stocks bought</div></div>' +
      '<div class="mini-stat"><div class="v">' + stocksSold.size + '</div><div class="l">Stocks sold</div></div>' +
      '<div class="mini-stat"><div class="v">' + newEntries + '</div><div class="l">New entries / re-entries</div></div>' +
      '<div class="mini-stat"><div class="v">' + exits + '</div><div class="l">Exits</div></div>' +
      '<div class="mini-stat"><div class="v">' + repeatedAccumulation + '</div><div class="l">Stocks with repeated accumulation</div></div>' +
      '<div class="mini-stat"><div class="v">' + repeatedSelling + '</div><div class="l">Stocks with repeated selling</div></div>' +
    '</div>' +
    '<div class="note">Historical performance after deal (avg. return, in range): 1D ' + (avg('return_1d_pct') === null ? 'N/A' : avg('return_1d_pct').toFixed(2) + '%') +
      ' &#183; 1W ' + (avg('return_1w_pct') === null ? 'N/A' : avg('return_1w_pct').toFixed(2) + '%') +
      ' &#183; 1M ' + (avg('return_1m_pct') === null ? 'N/A' : avg('return_1m_pct').toFixed(2) + '%') +
      ' &#183; 1W win rate ' + (winRate1w === null ? 'N/A' : winRate1w.toFixed(0) + '%') +
      (anyPerfData ? '' : ' &#8212; price performance data has not been populated in this dataset yet (data/price_performance.csv is not present), so these are showing N/A rather than a fabricated figure.') +
      ' 3M/6M/1Y average return: not available &#8212; this dataset only tracks 1D/1W/1M price performance.</div>' +
    '<div class="table-scroll"><table><thead><tr>' +
      '<th>Stock</th><th>Action</th><th>Date</th><th>Quantity</th><th>Price</th><th>Value (\u20b9 Cr)</th><th>Behaviour</th><th>1D %</th><th>1W %</th><th>1M %</th>' +
    '</tr></thead><tbody>' +
    sortedEvents.map(e =>
      '<tr><td>' + e.symbol + ' <span style="color:#8b93a7;font-size:11px;">' + (e.security_name || '') + '</span></td>' +
      '<td>' + ((e.buy_sell === 'BUY') ? '<span class="badge buy">BUY</span>' : '<span class="badge sell">SELL</span>') + '</td>' +
      '<td>' + e.date_raw + '</td><td>' + Number(e.quantity).toLocaleString() + '</td><td>' + parseFloat(e.price).toFixed(2) +
      '</td><td>' + (e.value_cr !== null ? e.value_cr.toFixed(2) : '-') +
      '</td><td>' + behaviourTagHTML(e.behaviour) +
      '</td><td>' + pctBadge(e.return_1d_pct) + '</td><td>' + pctBadge(e.return_1w_pct) + '</td><td>' + pctBadge(e.return_1m_pct) + '</td></tr>'
    ).join('') +
    '</tbody></table></div>';

  latestExport.investor = sortedEvents.map(e => ({
    Investor: selectedInvestor, Stock: e.symbol, Security: e.security_name || '',
    Action: e.buy_sell, Date: e.date_raw, Quantity: e.quantity, Price: e.price,
    'Value (Cr)': e.value_cr, Behaviour: e.behaviour,
    '1D %': e.return_1d_pct, '1W %': e.return_1w_pct, '1M %': e.return_1m_pct,
  }));
}

function investorNameList() {
  const names = new Set();
  scorableDeals(ALL_DEALS).forEach(d => { if (d.client_name) names.add(d.client_name); });
  return [...names].sort();
}
const ALL_INVESTOR_NAMES = investorNameList();

document.getElementById('investorSearchBox').addEventListener('input', (e) => {
  const q = e.target.value.trim().toLowerCase();
  const box = document.getElementById('investorSuggestions');
  if (!q) { box.classList.remove('open'); box.innerHTML = ''; return; }
  const matches = ALL_INVESTOR_NAMES.filter(n => n.toLowerCase().includes(q)).slice(0, 8);
  if (matches.length === 0) { box.classList.remove('open'); box.innerHTML = ''; return; }
  box.innerHTML = matches.map(n => '<div data-name="' + n.replace(/"/g, '&quot;') + '">' + n + '</div>').join('');
  box.classList.add('open');
  box.querySelectorAll('div[data-name]').forEach(el => {
    el.addEventListener('click', () => {
      selectedInvestor = el.dataset.name;
      document.getElementById('investorSearchBox').value = selectedInvestor;
      box.classList.remove('open');
      box.innerHTML = '';
      renderInvestorDetail();
    });
  });
});
document.addEventListener('click', (e) => {
  const wrap = document.querySelector('.investor-search-wrap');
  if (wrap && !wrap.contains(e.target)) {
    document.getElementById('investorSuggestions').classList.remove('open');
  }
});

// ---- Watchlist tracker: view trades for any watchlisted investor ----
function populateWatchlistTradesSelect() {
  const sel = document.getElementById('watchlistTradesSelect');
  [...WATCHLIST].sort().forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    sel.appendChild(opt);
  });
}

function renderWatchlistTrades() {
  const sel = document.getElementById('watchlistTradesSelect');
  const wrap = document.getElementById('watchlistTradesWrap');
  const name = sel.value;
  if (!name) { wrap.innerHTML = ''; latestExport.watchlistTrades = []; return; }

  // Respects the global date filter, like every other section. Shows ALL
  // rows for this investor including round-trips (flagged, not excluded)
  // since this is a raw trade view, not a scoring feature.
  const trades = getFilteredDeals().filter(d => d.client_name === name)
    .sort((a, b) => b.date.localeCompare(a.date));

  if (trades.length === 0) {
    wrap.innerHTML = '<div class="empty">No trades for ' + name + ' in the selected date range.</div>';
    latestExport.watchlistTrades = [];
    return;
  }

  wrap.innerHTML = '<div class="table-scroll"><table><thead><tr>' +
    '<th>Date</th><th>Exchange</th><th>Type</th><th>Symbol</th><th>Security</th><th>B/S</th>' +
    '<th>Quantity</th><th>Price</th><th>Value (\u20b9 Cr)</th><th>1D %</th><th>1W %</th><th>1M %</th>' +
    '</tr></thead><tbody>' +
    trades.map(d =>
      '<tr><td>' + d.date_raw + '</td><td>' + d.exchange + '</td><td>' + d.deal_type + '</td><td>' + d.symbol +
      '</td><td>' + d.security_name + '</td><td>' +
      ((d.buy_sell === 'BUY') ? '<span class="badge buy">BUY</span>' : '<span class="badge sell">SELL</span>') +
      (d.is_round_trip ? ' <span class="badge roundtrip">round-trip</span>' : '') +
      '</td><td>' + Number(d.quantity).toLocaleString() + '</td><td>' + parseFloat(d.price).toFixed(2) +
      '</td><td>' + (d.value_cr !== null ? d.value_cr.toFixed(2) : '-') +
      '</td><td>' + pctBadge(d.return_1d_pct) + '</td><td>' + pctBadge(d.return_1w_pct) + '</td><td>' + pctBadge(d.return_1m_pct) + '</td></tr>'
    ).join('') +
    '</tbody></table></div>';

  latestExport.watchlistTrades = trades.map(d => ({
    Investor: name, Date: d.date_raw, Exchange: d.exchange, Type: d.deal_type, Symbol: d.symbol,
    Security: d.security_name, 'B/S': d.buy_sell, Quantity: d.quantity, Price: d.price,
    'Value (Cr)': d.value_cr, 'Round-trip': d.is_round_trip ? 'Yes' : 'No',
    '1D %': d.return_1d_pct, '1W %': d.return_1w_pct, '1M %': d.return_1m_pct,
  }));
}

document.getElementById('watchlistTradesSelect').addEventListener('change', renderWatchlistTrades);

// ---- Scrip-wise summary: view trades for any stock ----
function populateScripTradesSelect() {
  const sel = document.getElementById('scripTradesSelect');
  const symbols = new Set();
  ALL_DEALS.forEach(d => { if (d.symbol) symbols.add(d.symbol); });
  [...symbols].sort().forEach(sym => {
    const opt = document.createElement('option');
    opt.value = sym; opt.textContent = sym;
    sel.appendChild(opt);
  });
}

function renderScripTrades() {
  const sel = document.getElementById('scripTradesSelect');
  const wrap = document.getElementById('scripTradesWrap');
  const symbol = sel.value;
  if (!symbol) { wrap.innerHTML = ''; latestExport.scripTrades = []; return; }

  // Respects the global date filter, like every other section. Shows ALL
  // rows for this stock including round-trips (flagged, not excluded)
  // since this is a raw trade view, not a scoring feature.
  const trades = getFilteredDeals().filter(d => d.symbol === symbol)
    .sort((a, b) => b.date.localeCompare(a.date));

  if (trades.length === 0) {
    wrap.innerHTML = '<div class="empty">No trades for ' + symbol + ' in the selected date range.</div>';
    latestExport.scripTrades = [];
    return;
  }

  wrap.innerHTML = '<div class="table-scroll"><table><thead><tr>' +
    '<th>Date</th><th>Exchange</th><th>Type</th><th>Investor</th><th>B/S</th>' +
    '<th>Quantity</th><th>Price</th><th>Value (\u20b9 Cr)</th><th>1D %</th><th>1W %</th><th>1M %</th>' +
    '</tr></thead><tbody>' +
    trades.map(d =>
      '<tr><td>' + d.date_raw + '</td><td>' + d.exchange + '</td><td>' + d.deal_type + '</td><td>' + d.client_name +
      (d.matched_investor ? ' <span class="badge hit">watchlist</span>' : '') + '</td><td>' +
      ((d.buy_sell === 'BUY') ? '<span class="badge buy">BUY</span>' : '<span class="badge sell">SELL</span>') +
      (d.is_round_trip ? ' <span class="badge roundtrip">round-trip</span>' : '') +
      '</td><td>' + Number(d.quantity).toLocaleString() + '</td><td>' + parseFloat(d.price).toFixed(2) +
      '</td><td>' + (d.value_cr !== null ? d.value_cr.toFixed(2) : '-') +
      '</td><td>' + pctBadge(d.return_1d_pct) + '</td><td>' + pctBadge(d.return_1w_pct) + '</td><td>' + pctBadge(d.return_1m_pct) + '</td></tr>'
    ).join('') +
    '</tbody></table></div>';

  latestExport.scripTrades = trades.map(d => ({
    Symbol: symbol, Security: d.security_name, Date: d.date_raw, Exchange: d.exchange, Type: d.deal_type,
    Investor: d.client_name, 'Watchlist match': d.matched_investor || '', 'B/S': d.buy_sell,
    Quantity: d.quantity, Price: d.price, 'Value (Cr)': d.value_cr, 'Round-trip': d.is_round_trip ? 'Yes' : 'No',
    '1D %': d.return_1d_pct, '1W %': d.return_1w_pct, '1M %': d.return_1m_pct,
  }));
}

document.getElementById('scripTradesSelect').addEventListener('change', renderScripTrades);

// ---- Excel export (SheetJS) ----
const EXPORT_LABELS = {
  alldeals: 'All Deals', scrip: 'Scrip-wise Summary', watchlist: 'Watchlist Tracker',
  track: 'Investor Track Record', rising: 'Rising Names', significance: 'Deal Significance',
  accum: 'Repeated Accumulation', sms: 'Smart Money Score', investor: 'Investor Intelligence',
  watchlistTrades: 'Watchlist Investor Trades', scripTrades: 'Stock Trades',
};

function exportSingleSheet(key) {
  const rows = latestExport[key];
  if (!rows || rows.length === 0) {
    alert('Nothing to export for this report with the current filters -- the table is empty.');
    return;
  }
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, EXPORT_LABELS[key].slice(0, 31));
  const stamp = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, 'BulkDealTracker_' + EXPORT_LABELS[key].replace(/\\s+/g, '_') + '_' + stamp + '.xlsx');
}

function exportAllReports() {
  const wb = XLSX.utils.book_new();
  let any = false;
  Object.keys(EXPORT_LABELS).forEach(key => {
    const rows = latestExport[key];
    if (rows && rows.length > 0) {
      const ws = XLSX.utils.json_to_sheet(rows);
      XLSX.utils.book_append_sheet(wb, ws, EXPORT_LABELS[key].slice(0, 31));
      any = true;
    }
  });
  if (!any) {
    alert('Nothing to export -- all reports are empty with the current filters.');
    return;
  }
  const stamp = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, 'BulkDealTracker_AllReports_' + stamp + '.xlsx');
}

document.querySelectorAll('button[data-export]').forEach(btn => {
  btn.addEventListener('click', () => exportSingleSheet(btn.dataset.export));
});
document.getElementById('exportAllBtn').addEventListener('click', exportAllReports);

document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    setDateRangeFromPreset(btn.dataset.range === 'all' ? 'all' : parseInt(btn.dataset.range));
    currentPage = 1;
    render();
  });
});

['dateFrom', 'dateTo'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    // Manual edit: deselect preset buttons since the range no longer
    // matches a preset exactly.
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    filterFromISO = document.getElementById('dateFrom').value || null;
    filterToISO = document.getElementById('dateTo').value || null;
    currentPage = 1;
    render();
  });
});

['searchBox','exchangeFilter','dealTypeFilter','buySellFilter','watchlistFilter'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => { currentPage = 1; render(); });
});

document.querySelectorAll('.toggle-btn[data-min]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.toggle-btn[data-min]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    accumMinThreshold = parseInt(btn.dataset.min);
    render();
  });
});

document.querySelectorAll('th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (sortCol === col) { sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
    else { sortCol = col; sortDir = 'desc'; }
    render();
  });
});

document.querySelectorAll('th[data-scripcol]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.scripcol;
    if (scripSortCol === col) { scripSortDir = scripSortDir === 'asc' ? 'desc' : 'asc'; }
    else { scripSortCol = col; scripSortDir = 'desc'; }
    render();
  });
});

document.querySelectorAll('th[data-trackcol]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.trackcol;
    if (trackSortCol === col) { trackSortDir = trackSortDir === 'asc' ? 'desc' : 'asc'; }
    else { trackSortCol = col; trackSortDir = 'desc'; }
    render();
  });
});

document.getElementById('prevPage').addEventListener('click', () => { currentPage--; render(); });
document.getElementById('nextPage').addEventListener('click', () => { currentPage++; render(); });

populateDropdowns();
populateWatchlistTradesSelect();
populateScripTradesSelect();
setDateRangeFromPreset(365);
render();
</script>
</body>
</html>"""

    html = html.replace("GENERATED_AT_PLACEHOLDER", generated_at)
    html = html.replace("DEALS_JSON_PLACEHOLDER", deals_json)
    html = html.replace("WATCHLIST_JSON_PLACEHOLDER", watchlist_json)
    return html


def main():
    history = load_history()
    watchlist = load_watchlist()
    deals = build_deals_json(history, watchlist)
    html = render_html(deals, watchlist)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard written to {OUTPUT_PATH}")
    print(f"{len(deals)} deals embedded.")


if __name__ == "__main__":
    main()
