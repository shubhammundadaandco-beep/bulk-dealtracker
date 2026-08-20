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


def build_deals_json(history: list[dict], watchlist: list[str]) -> list[dict]:
    perf_index = load_price_performance()
    deals = []
    for row in history:
        client_name = row.get("client_name", "")
        raw_date = row.get("date", "")
        exchange = row.get("exchange", "")
        symbol = row.get("symbol", "")
        buy_sell = row.get("buy_sell", "")
        price = row.get("price", "")

        perf = perf_index.get((raw_date, exchange, symbol, client_name, buy_sell, price), {})

        deals.append({
            "date": parse_date_iso(raw_date),
            "date_raw": raw_date,
            "exchange": exchange,
            "deal_type": row.get("deal_type", ""),
            "symbol": symbol,
            "security_name": row.get("security_name", ""),
            "client_name": client_name,
            "buy_sell": buy_sell,
            "quantity": row.get("quantity", ""),
            "price": price,
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
  .empty { color: var(--muted); text-align: center; padding: 20px; }
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

  <div class="toolbar">
    <div class="range-btns">
      <button class="range-btn" data-range="30">1M</button>
      <button class="range-btn" data-range="90">3M</button>
      <button class="range-btn active" data-range="365">1Y</button>
      <button class="range-btn" data-range="all">All time</button>
    </div>
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
    <h2>Watchlist tracker <span class="count-pill" id="watchlistCount"></span></h2>
    <table><thead><tr><th>Investor</th><th>Hits in range</th><th>Status</th></tr></thead><tbody id="watchlistBody"></tbody></table>
  </div>

  <div class="section">
    <h2>Investor track record (avg. return after deal) <span class="count-pill" id="trackRecordNote"></span></h2>
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
    <h2>Rising names (non-watchlisted, 3+ appearances in range) <span class="count-pill" id="risingCount"></span></h2>
    <table><thead><tr><th>Name</th><th>Deal count</th><th>Stocks</th></tr></thead><tbody id="risingBody"></tbody></table>
  </div>

  <div class="section">
    <h2>Scrip-wise summary <span class="count-pill" id="scripCount"></span></h2>
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
  </div>

  <div class="section">
    <h2>All deals <span class="count-pill" id="dealsCount"></span></h2>
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

function getFilteredDeals() {
  const search = document.getElementById('searchBox').value.trim().toLowerCase();
  const exchange = document.getElementById('exchangeFilter').value;
  const dealType = document.getElementById('dealTypeFilter').value;
  const buySell = document.getElementById('buySellFilter').value;
  const watchlistOnly = document.getElementById('watchlistFilter').value === 'yes';

  let cutoff = null;
  if (currentRangeDays !== 'all') {
    cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - currentRangeDays);
  }

  return ALL_DEALS.filter(d => {
    if (cutoff && d.date) {
      const dDate = new Date(d.date);
      if (dDate < cutoff) return false;
    }
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
      };
    }
    const g = map[key];
    if (d.client_name) g.clients.push(d.client_name);
    g.quantity += parseFloat(d.quantity) || 0;
    const p = parseFloat(d.price);
    if (!isNaN(p)) { g.price_sum += p; g.price_count += 1; }
    if (d.matched_investor && !g.matched_investor) g.matched_investor = d.matched_investor;
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
    const isBuy = (d.buy_sell === 'BUY' || d.buy_sell === 'B');
    if (isBuy) entry.buy_value += valueCr; else entry.sell_value += valueCr;
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
    (d.matched_investor ? ' <span class="badge hit">watchlist</span>' : '') + '</td><td>' +
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
}

document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentRangeDays = btn.dataset.range === 'all' ? 'all' : parseInt(btn.dataset.range);
    currentPage = 1;
    render();
  });
});

['searchBox','exchangeFilter','dealTypeFilter','buySellFilter','watchlistFilter'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => { currentPage = 1; render(); });
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
