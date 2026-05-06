#!/usr/bin/env python3
"""
Cluster Buy Scanner

Scrapes openinsider.com/latest-cluster-buys for current "MRVL/CEVA setup":
multiple insiders making open-market BUYS within a tight time window.

Why this script exists:
  Real cluster buys are rare and high-signal (~4-6% annual alpha vs single-insider
  buys per academic studies). News articles routinely conflate RSU vesting and
  board-comp DSU grants with "cluster buys" — those are NOT real buys (only Form 4
  code "P" counts). This script hits the source-of-truth directly.

How it works:
  1. Fetch /latest-cluster-buys → ticker-level cluster summary (cluster size, total $)
  2. For each cluster, optionally drill into /screener?s={TICKER}&fd={days} to get
     per-insider detail (--detail flag)
  3. Optionally enrich with yfinance current price + Forward P/E + 52w high

Usage:
  uv run --with yfinance python cluster_buy_scan.py
  Options:
    --days N          Lookback window (default: 30)
    --min-value N     Minimum aggregate cluster $ (default: 250000)
    --min-insiders N  Minimum unique insiders (default: 2)
    --detail          Drill into per-ticker /screener for senior-buyer breakdown
    --enrich          Pull yfinance price + valuation
    --senior-only     Filter to clusters that include CEO/CFO/Chair/Founder
                      (requires --detail)
"""
import sys, json, re, urllib.request, urllib.parse
from datetime import datetime, timedelta

OI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (cluster_buy_scan.py)",
    "Accept": "text/html,application/xhtml+xml",
}

SENIOR_PATTERNS = [
    r"\bceo\b", r"chief executive", r"\bcfo\b", r"chief financial",
    r"chairman", r"\bchair\b", r"founder", r"\bpres\b", r"president",
]


def is_senior(title):
    return any(re.search(p, (title or "").lower()) for p in SENIOR_PATTERNS)


def _http_get(url):
    req = urllib.request.Request(url, headers=OI_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _clean(cell):
    """Strip HTML tags + collapse whitespace."""
    s = re.sub(r"<[^>]+>", " ", cell)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_ticker(raw_cell):
    """Ticker cell on openinsider has JS onmouseover gibberish. Pull last token."""
    # The structure ends with ">TICKER</td>" or similar; cleaned text leaves only the ticker
    cleaned = _clean(raw_cell)
    # Sometimes returns "', DELAY, 1)\" onmouseout=\"UnTip()\">OPCH" — grab last alphanumeric
    m = re.search(r"\b([A-Z][A-Z0-9\.\-]{0,9})\s*$", cleaned)
    return m.group(1) if m else cleaned[-6:]


def fetch_cluster_summary(days=30, min_value=250_000, min_insiders=2):
    """Parse openinsider.com/latest-cluster-buys → list of cluster summaries.

    Cluster-buys page columns (after td extraction):
      0: X flag,  1: Filing Date,  2: Trade Date,  3: Ticker (with JS noise),
      4: Company Name,  5: Industry,  6: Cluster size (# insiders),
      7: Trade Type "P - Purchase",  8: Price,  9: Qty (aggregate),
      10: Owned,  11: ΔOwn,  12: Value (aggregate $)
    """
    try:
        html = _http_get("http://openinsider.com/latest-cluster-buys")
    except Exception as e:
        return {"error": f"fetch failed: {e}"}

    table_match = re.search(
        r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not table_match:
        return []
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.DOTALL | re.IGNORECASE)

    cutoff = (datetime.utcnow() - timedelta(days=days)).date()
    clusters = []
    for row in rows_html:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 13:
            continue
        try:
            filing_date = _clean(cells[1])[:10]
            trade_date = _clean(cells[2])[:10]
            ticker = _extract_ticker(cells[3])
            company = _clean(cells[4])
            industry = _clean(cells[5])
            cluster_size = int(_clean(cells[6])) if _clean(cells[6]).isdigit() else 0
            price_str = _clean(cells[8]).replace("$","").replace(",","")
            price = float(price_str) if price_str.replace(".","").isdigit() else 0.0
            qty_str = _clean(cells[9]).replace(",","").replace("+","").lstrip("-")
            qty = int(qty_str) if qty_str.isdigit() else 0
            value_raw = _clean(cells[12]).replace("$","").replace(",","").replace("+","")
            value = abs(float(value_raw)) if value_raw.lstrip("-").replace(".","").isdigit() else 0.0
        except Exception:
            continue

        # Filter
        try:
            tdate = datetime.strptime(trade_date, "%Y-%m-%d").date()
        except Exception:
            continue
        if tdate < cutoff: continue
        if cluster_size < min_insiders: continue
        if value < min_value: continue
        if not ticker or not ticker.isalpha(): continue  # skip malformed

        clusters.append({
            "ticker": ticker,
            "company": company,
            "industry": industry,
            "n_insiders": cluster_size,
            "trade_date": trade_date,
            "filing_date": filing_date,
            "price": price,
            "qty": qty,
            "total_buy_$": round(value, 0),
        })
    return clusters


def fetch_ticker_detail(ticker, days=90):
    """Drill into /screener?s=TICKER for per-insider breakdown."""
    url = (
        f"http://openinsider.com/screener?s={urllib.parse.quote(ticker)}"
        f"&o=&pl=&ph=&ll=&lh=&fd={days}&fdr=&td=0&tdr="
        f"&fdlyl=&fdlyh=&daysago=&xp=1&xs=1"
        f"&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999"
        f"&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=200&page=1"
    )
    try:
        html = _http_get(url)
    except Exception as e:
        return [{"error": str(e)}]

    table_match = re.search(
        r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not table_match: return []
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.DOTALL | re.IGNORECASE)

    txns = []
    for row in rows_html:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 12: continue
        try:
            trade_date = _clean(cells[2])[:10]
            insider = _clean(cells[4])
            title = _clean(cells[5])
            trade_type = _clean(cells[6])
            code = trade_type[:1] if trade_type else ""
            value_raw = _clean(cells[11]).replace("$","").replace(",","").replace("+","")
            value = abs(float(value_raw)) if value_raw.lstrip("-").replace(".","").isdigit() else 0.0
        except Exception:
            continue
        if code != "P": continue  # ONLY real buys
        txns.append({
            "date": trade_date,
            "insider": insider,
            "title": title,
            "value": value,
            "is_senior": is_senior(title),
        })
    return txns


def enrich_with_yfinance(clusters):
    try:
        import yfinance as yf
    except Exception:
        return clusters
    for c in clusters:
        try:
            info = yf.Ticker(c["ticker"]).info or {}
            c["price_now"] = info.get("currentPrice") or info.get("regularMarketPrice")
            c["fwd_pe"] = info.get("forwardPE")
            c["fiftyTwoWeekHigh"] = info.get("fiftyTwoWeekHigh")
            c["mcap"] = info.get("marketCap")
            c["target"] = info.get("targetMeanPrice")
            if c.get("price_now") and c.get("fiftyTwoWeekHigh"):
                c["pct_off_52wHigh"] = round(
                    100 * (c["price_now"] - c["fiftyTwoWeekHigh"]) / c["fiftyTwoWeekHigh"], 1
                )
        except Exception as e:
            c["enrich_error"] = str(e)[:100]
    return clusters


if __name__ == "__main__":
    days = 30
    min_value = 250_000
    min_insiders = 2
    detail = False
    enrich = False
    senior_only = False
    for i, a in enumerate(sys.argv):
        if a == "--days" and i+1 < len(sys.argv):
            days = int(sys.argv[i+1])
        elif a == "--min-value" and i+1 < len(sys.argv):
            min_value = int(sys.argv[i+1])
        elif a == "--min-insiders" and i+1 < len(sys.argv):
            min_insiders = int(sys.argv[i+1])
        elif a == "--detail":
            detail = True
        elif a == "--enrich":
            enrich = True
        elif a == "--senior-only":
            senior_only = True
            detail = True  # senior filter requires per-insider data

    clusters = fetch_cluster_summary(days=days, min_value=min_value, min_insiders=min_insiders)
    if isinstance(clusters, dict) and "error" in clusters:
        print(json.dumps(clusters, indent=2)); sys.exit(1)

    # De-duplicate by ticker (keep highest $ aggregate)
    by_ticker = {}
    for c in clusters:
        if c["ticker"] not in by_ticker or c["total_buy_$"] > by_ticker[c["ticker"]]["total_buy_$"]:
            by_ticker[c["ticker"]] = c
    clusters = list(by_ticker.values())

    if detail:
        for c in clusters:
            buyers = fetch_ticker_detail(c["ticker"], days=days)
            c["buyers"] = sorted(buyers, key=lambda x: x.get("value",0), reverse=True)[:8]
            c["senior_buyer_count"] = sum(1 for b in buyers if b.get("is_senior"))
        if senior_only:
            clusters = [c for c in clusters if c.get("senior_buyer_count",0) >= 1]

    if enrich:
        clusters = enrich_with_yfinance(clusters)

    # Sort: senior count first, then $ amount
    clusters.sort(key=lambda x: (-(x.get("senior_buyer_count") or 0), -x["total_buy_$"]))

    print(json.dumps({
        "params": {"days": days, "min_value": min_value, "min_insiders": min_insiders,
                   "detail": detail, "senior_only": senior_only, "enrich": enrich},
        "n_clusters": len(clusters),
        "clusters": clusters,
        "source": "openinsider.com/latest-cluster-buys",
    }, indent=2, default=str))
