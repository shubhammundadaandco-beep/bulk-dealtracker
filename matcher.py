"""
Matches deal 'client_name' fields against watchlist.json using fuzzy string
matching (exchange data has inconsistent name formatting/ordering, e.g.
"Kacholia Ashish D" vs "Ashish Kacholia").
"""

import json

from rapidfuzz import fuzz

# Similarity score (0-100) above which a deal is flagged as a watchlist hit.
# Tune this over time: too low -> false positives, too high -> missed variants.
MATCH_THRESHOLD = 85


def load_watchlist(path: str = "watchlist.json") -> list[str]:
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("investors", [])


def match_deal(deal: dict, watchlist: list[str]) -> dict | None:
    """
    Returns a dict with match info if deal['client_name'] fuzzy-matches any
    watchlist name above MATCH_THRESHOLD, else None.
    """
        raw_name = deal.get("client_name")
    if raw_name is None or (isinstance(raw_name, float) and raw_name != raw_name):
        client_name = ""
    else:
        client_name = str(raw_name).strip()
    if not client_name:
        return None

    best_name = None
    best_score = 0
    for watch_name in watchlist:
        score = fuzz.token_sort_ratio(client_name, watch_name)
        if score > best_score:
            best_score = score
            best_name = watch_name

    if best_score >= MATCH_THRESHOLD:
        return {
            "matched_investor": best_name,
            "match_score": best_score,
            "deal": deal,
        }
    return None


def find_watchlist_hits(deals: list[dict], watchlist: list[str]) -> list[dict]:
    hits = []
    for deal in deals:
        result = match_deal(deal, watchlist)
        if result:
            hits.append(result)
    return hits


if __name__ == "__main__":
    # Quick manual sanity check of the fuzzy matching logic itself
    # (does not touch network — just tests the matching function).
    sample_watchlist = ["Ashish Kacholia", "Radhakishan Damani"]
    sample_deals = [
        {"client_name": "Kacholia Ashish D", "symbol": "TESTSTOCK"},
        {"client_name": "Some Random Fund LLP", "symbol": "OTHERSTOCK"},
    ]
    hits = find_watchlist_hits(sample_deals, sample_watchlist)
    for h in hits:
        print(h)
