#!/usr/bin/env python3
"""
Insider Trading Strict Buy-vs-Sell Ratio Analyzer (v3)

PRIMARY SOURCE: openinsider.com (Form 4 with transaction codes)
FALLBACK SOURCE: yfinance (when openinsider is unreachable)

CRITICAL LESSONS (codified from real failures):

1. yfinance "% Net Shares Purchased" counts RSU as buys + tax as sells → false positives.
   Use only "purchase at price" / "sale at price" entries.

2. RECENCY: a sale 6 months ago at ATH means nothing if the stock is now -33%.
   Default --window 90, bucket by 0-30d / 30-90d / 90-180d / >180d.

3. Form 4 transaction CODES (most important filter):
     P = Purchase (open-market buy)         ← ONLY this counts as bullish
     S = Sale (open-market sell)            ← bearish (but verify 10b5-1)
     A = Award/Grant (RSU/DSU)              ← IGNORE (compensation, not signal)
     M = Exercise (option → stock)          ← IGNORE (compensation flow)
     F = Tax Withholding                    ← IGNORE (mechanical)
     G = Gift                               ← IGNORE
     D = Disposition (other)                ← context-dependent
     C = Conversion                         ← IGNORE

4. yfinance Text field does NOT distinguish 10b5-1 scheduled vs ad-hoc selling.
   Sales from "trusts" (THE EEC TRUST etc.) are almost always 10b5-1.
   openinsider shows the raw Form 4 footnote — better source.

5. yfinance MISSES many real buys (UNH/PLTR/WEX cluster-buy hunt 2026-05-05 returned
   0 buys when SEC Form 4 confirmed real activity). openinsider has wider coverage.

6. News articles often LIE about "cluster buys" — UNH "10 directors bought 4/1/2026"
   was actually $0 DSU board-comp grants. Always verify code = "P" before trusting
   any cluster-buy headline.

Usage:
  uv run --with yfinance,pandas,lxml,requests python insider_ratio.py "TICKER1,TICKER2,..."
  Options:
    --window N             Last N days (default: 90)
    --since YYYY-MM-DD     Custom start date
    --source openinsider   Use openinsider.com (default)
    --source yfinance      Use yfinance only
    --source both          Cross-verify (recommended for high-stakes calls)
    --min-buy-size N       Minimum $ per buy to count toward cluster (default: 25000)
                           Lower = more permissive. Set to 0 to disable micro filter.
                           Why: TSM 2026-05-05 had 16 VP buys @ $3-8K each that
                           triggered false-positive cluster verdict.

The output prints structured JSON. For human reads, see the verdict + buckets.
"""
import sys, json, io, re, urllib.request, urllib.parse
from datetime import datetime, timedelta

# -- yfinance fallback (lazy import to avoid hard dep if user only wants openinsider)
def _yf():
    import yfinance as yf
    return yf

# -- openinsider scraping --------------------------------------------------------

OI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (insider_ratio.py; cluster-buy verification)",
    "Accept": "text/html,application/xhtml+xml",
}

def fetch_openinsider_ticker(ticker, days=90):
    """Fetch ticker history from openinsider.com.

    Returns list of dicts with keys: date, code, insider, position, shares, price, value, text.
    Filters to date >= today - days. Empty list on error.
    """
    url = (
        f"http://openinsider.com/screener?s={urllib.parse.quote(ticker)}"
        f"&o=&pl=&ph=&ll=&lh=&fd={days}&fdr=&td=0&tdr="
        f"&fdlyl=&fdlyh=&daysago=&xp=1&xs=1"
        f"&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999"
        f"&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=200&page=1"
    )
    try:
        req = urllib.request.Request(url, headers=OI_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"openinsider fetch failed: {e}"}

    # The relevant table has class "tinytable". Pull rows by regex (avoid heavy deps).
    table_match = re.search(
        r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not table_match:
        return []
    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.DOTALL | re.IGNORECASE)

    # column order on openinsider /screener:
    #  0:X  1:Filing Date  2:Trade Date  3:Ticker  4:Insider Name  5:Title  6:Trade Type
    #  7:Price  8:Qty  9:Owned  10:ΔOwn  11:Value
    txns = []
    for row in rows_html:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 12:
            continue
        def clean(s):
            s = re.sub(r"<[^>]+>", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s
        cleaned = [clean(c) for c in cells]
        try:
            trade_date = cleaned[2][:10]
            ticker_cell = cleaned[3]
            insider = cleaned[4]
            title = cleaned[5]
            trade_type_full = cleaned[6]  # e.g. "P - Purchase"
            price = float(cleaned[7].replace("$","").replace(",","")) if cleaned[7] else 0.0
            qty_str = cleaned[8].replace(",","").replace("+","")
            qty = abs(int(qty_str)) if qty_str.lstrip("-").isdigit() else 0
            value_str = cleaned[11].replace("$","").replace(",","").replace("+","")
            value = abs(float(value_str)) if value_str.lstrip("-").replace(".","").isdigit() else 0.0
        except Exception:
            continue
        # Extract Form 4 code (first letter of Trade Type)
        code = trade_type_full[:1] if trade_type_full else ""
        txns.append({
            "date": trade_date,
            "code": code,
            "trade_type": trade_type_full,
            "insider": insider,
            "position": title,
            "shares": qty,
            "price": price,
            "value": value,
        })
    return txns


# -- yfinance fallback parser ---------------------------------------------------

def fetch_yfinance_ticker(ticker, since_date):
    """Fallback to yfinance get_insider_transactions(). Filter by 'purchase at price'/'sale at price'."""
    try:
        yf = _yf()
        tk = yf.Ticker(ticker)
        it = tk.get_insider_transactions()
        if it is None or len(it) == 0:
            return []
        out = []
        for r in it.to_dict(orient="records"):
            text = str(r.get("Text","")).lower()
            date = str(r.get("Start Date",""))[:10]
            if since_date and date < since_date:
                continue
            shares = r.get("Shares", 0)
            value = r.get("Value", 0)
            if "purchase at price" in text:
                code = "P"
            elif "sale at price" in text:
                code = "S"
            else:
                continue  # skip RSU/tax/exercises
            out.append({
                "date": date,
                "code": code,
                "trade_type": code + " - " + ("Purchase" if code=="P" else "Sale"),
                "insider": r.get("Insider", ""),
                "position": r.get("Position", ""),
                "shares": int(shares) if shares else 0,
                "price": 0.0,
                "value": float(value) if value and not isinstance(value, str) and str(value)!='nan' else 0.0,
            })
        return out
    except Exception as e:
        return {"error": f"yfinance fetch failed: {e}"}


# -- core analyzer --------------------------------------------------------------

def bucket(date_str, today):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return "unknown"
    days = (today - d).days
    if days <= 30: return "0-30d"
    if days <= 90: return "30-90d"
    if days <= 180: return "90-180d"
    return ">180d"


def analyze(tickers, source="openinsider", since=None, window_days=None, min_buy_size=25_000):
    """
    min_buy_size: filter for "meaningful" buys when counting cluster (default $25K).
        Why: TSM 2026-05-05 false positive — 16 VP buys @ $3-8K each totaled $827K
        and triggered "CLUSTER BUY" but were ESPP/automated noise, not conviction.
        Set to 0 to disable.
    """
    today = datetime.utcnow().date()
    if window_days and not since:
        since = (today - timedelta(days=window_days)).isoformat()
    elif not since:
        since = (today - timedelta(days=90)).isoformat()

    results = {}
    for t in tickers:
        # Fetch
        if source == "yfinance":
            txns = fetch_yfinance_ticker(t, since)
        elif source == "both":
            oi = fetch_openinsider_ticker(t, days=(today - datetime.strptime(since, "%Y-%m-%d").date()).days)
            yf_t = fetch_yfinance_ticker(t, since)
            txns = oi if isinstance(oi, list) and oi else (yf_t if isinstance(yf_t, list) else [])
            results.setdefault(t, {})["sources"] = {
                "openinsider_count": len(oi) if isinstance(oi, list) else 0,
                "yfinance_count": len(yf_t) if isinstance(yf_t, list) else 0,
            }
        else:  # default openinsider
            txns = fetch_openinsider_ticker(t, days=(today - datetime.strptime(since, "%Y-%m-%d").date()).days)
            if isinstance(txns, dict) and "error" in txns:
                # graceful degradation
                txns = fetch_yfinance_ticker(t, since)
                results.setdefault(t, {})["fallback"] = "used yfinance (openinsider unreachable)"

        if isinstance(txns, dict) and "error" in txns:
            results.setdefault(t, {})["err"] = txns["error"]
            continue

        # Filter by since
        txns = [tx for tx in txns if tx["date"] >= since]

        buys, sells = [], []
        for tx in txns:
            tx["bucket"] = bucket(tx["date"], today)
            if tx["code"] == "P":
                buys.append(tx)
            elif tx["code"] == "S":
                sells.append(tx)
            # Other codes intentionally dropped (A/M/F/G/D/C are not real signals)

        def bucket_totals(records):
            out = {"0-30d": 0, "30-90d": 0, "90-180d": 0, ">180d": 0}
            for r in records:
                if r.get("value"):
                    out[r["bucket"]] += r["value"]
            return out

        buy_buckets = bucket_totals(buys)
        sell_buckets = bucket_totals(sells)
        buy_total = sum(buy_buckets.values())
        sell_total = sum(sell_buckets.values())
        recent_buy = buy_buckets["0-30d"] + buy_buckets["30-90d"]
        recent_sell = sell_buckets["0-30d"] + sell_buckets["30-90d"]

        ratio = "N/A"
        if buy_total > 0 and sell_total > 0:
            ratio = f"1 : {sell_total/buy_total:.1f}"
        elif buy_total > 0:
            ratio = "buys-only ✅"
        elif sell_total > 0:
            ratio = "sells-only 🔴"

        # Verdict — recency-weighted, cluster-aware, micro-buy-aware
        recent_buys = [b for b in buys if b["bucket"] in ("0-30d","30-90d")]
        # Total recent buyers (including micro)
        all_recent_buyers = len({b["insider"] for b in recent_buys})
        # Meaningful buyers (filter out ESPP-style micro buys)
        meaningful_buys = [b for b in recent_buys if b.get("value", 0) >= min_buy_size]
        meaningful_buyers = len({b["insider"] for b in meaningful_buys})
        meaningful_buy_total = sum(b.get("value", 0) for b in meaningful_buys)
        micro_buy_total = recent_buy - meaningful_buy_total

        if buy_total == 0 and sell_total == 0:
            verdict = "NO ACTIVITY (in window) — neutral"
        elif meaningful_buyers >= 3 and meaningful_buy_total >= 500_000:
            verdict = f"RECENT CLUSTER BUY ✅✅✅ ({meaningful_buyers} insiders w/ ≥${min_buy_size//1000}K each, ${meaningful_buy_total/1e6:.1f}M aggregate)"
        elif meaningful_buyers >= 1 and meaningful_buy_total >= recent_sell * 2 and meaningful_buy_total > 0:
            verdict = f"RECENT STRONG BUY ✅✅ ({meaningful_buyers} buyer(s), ${meaningful_buy_total/1e6:.2f}M)"
        elif meaningful_buy_total > 0 and meaningful_buy_total >= recent_sell:
            verdict = f"RECENT BUY-LEAN ✅ ({meaningful_buyers} buyer(s), ${meaningful_buy_total/1e6:.2f}M)"
        elif recent_buy > 0 and meaningful_buyers == 0:
            verdict = f"MICRO-BUYS ONLY (${recent_buy:,.0f} across {all_recent_buyers} insiders, all <${min_buy_size//1000}K — likely ESPP/automated, low signal)"
        elif meaningful_buy_total > 0 and recent_sell > 0 and meaningful_buy_total < recent_sell * 0.1:
            verdict = "RECENT HEAVY DISTRIBUTION 🔴"
        elif recent_buy == 0 and recent_sell > 0:
            verdict = "RECENT INSIDERS-ONLY-SELLING 🔴 (verify 10b5-1 via SEC Form 4)"
        elif recent_buy == 0 and recent_sell == 0 and sell_total > 0:
            verdict = "OLD SELLS ONLY (likely 10b5-1) — neutral"
        else:
            verdict = "MIXED"

        # ticker info via yfinance (best-effort)
        info = {}
        try:
            info = _yf().Ticker(t).info or {}
        except Exception:
            pass

        results.setdefault(t, {}).update({
            "name": info.get("shortName"),
            "mcap": info.get("marketCap"),
            "last": info.get("currentPrice") or info.get("regularMarketPrice"),
            "fwd_pe": info.get("forwardPE"),
            "p_s": info.get("priceToSalesTrailing12Months"),
            "rev_growth": info.get("revenueGrowth"),
            "target": info.get("targetMeanPrice"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "window_since": since,
            "source_used": source,
            "om_buy_count": len(buys),
            "om_sell_count": len(sells),
            "om_buy_total_$": round(buy_total, 0),
            "om_sell_total_$": round(sell_total, 0),
            "buy_buckets_$": {k: round(v, 0) for k, v in buy_buckets.items()},
            "sell_buckets_$": {k: round(v, 0) for k, v in sell_buckets.items()},
            "recent_90d_buy_$": round(recent_buy, 0),
            "recent_90d_sell_$": round(recent_sell, 0),
            "all_recent_buyers": all_recent_buyers,
            "meaningful_recent_buyers": meaningful_buyers,
            "meaningful_buy_total_$": round(meaningful_buy_total, 0),
            "micro_buy_total_$": round(micro_buy_total, 0),
            "min_buy_size_threshold_$": min_buy_size,
            "buy_to_sell_ratio": ratio,
            "verdict": verdict,
            "form4_code_filter": "Only P (purchase) and S (sale) counted; A/M/F/G/D/C dropped",
            "micro_filter": f"Buys under ${min_buy_size:,} excluded from cluster verdict (likely ESPP/automated)",
            "note": "Verify high-stakes calls at openinsider.com/[TICKER] and secform4.com",
            # Sort by VALUE descending so the biggest/most-meaningful buys show up first.
            # (Earlier bug: TSM had 4 real $100K+ buys hidden behind 21 micro-buys when
            # top_buys was sorted by date.)
            "top_buys": sorted(buys, key=lambda x: x.get("value", 0) or 0, reverse=True)[:8],
            "top_sells": sorted(sells, key=lambda x: x.get("value", 0) or 0, reverse=True)[:5],
            "top_meaningful_buys": sorted(meaningful_buys, key=lambda x: x.get("value", 0) or 0, reverse=True)[:8],
        })
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tickers = [t.strip().upper() for t in sys.argv[1].split(",") if t.strip()]
    source = "openinsider"
    since = None
    window = None
    min_buy = 25_000
    for i, a in enumerate(sys.argv):
        if a == "--source" and i+1 < len(sys.argv):
            source = sys.argv[i+1]
        elif a == "--since" and i+1 < len(sys.argv):
            since = sys.argv[i+1]
        elif a == "--window" and i+1 < len(sys.argv):
            window = int(sys.argv[i+1])
        elif a == "--min-buy-size" and i+1 < len(sys.argv):
            min_buy = int(sys.argv[i+1])
    print(json.dumps(analyze(tickers, source=source, since=since, window_days=window, min_buy_size=min_buy), indent=2, default=str))
