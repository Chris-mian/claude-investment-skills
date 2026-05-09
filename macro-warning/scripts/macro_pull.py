#!/usr/bin/env python3
"""
macro_pull.py — Direct-API macro indicator puller for the macro-warning skill.

NO WebSearch, NO LLM scraping. All data via:
  - yfinance       (price, VIX, MOVE, yields, FX, ETFs)
  - FRED CSV       (HY/IG OAS, treasury yields cross-verify) — public, no API key
  - CNN unofficial (Fear & Greed score + history)            — JSON endpoint
  - multpl.com     (Shiller CAPE, SPX trailing PE)           — meta tag scrape

Outputs a single JSON blob with all raw values plus a deterministic
8-layer score (0-2 per layer, max 16) and regime tag.

Usage:
  python macro_pull.py
  python macro_pull.py --json-only      # raw JSON, no human header
  python macro_pull.py --history        # also pull 30-day history for delta
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from io import StringIO

# ─── Imports that may need pip install ───────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    import requests
except ImportError:
    print("ERROR: requires yfinance + pandas + requests. Run: pip install yfinance pandas requests",
          file=sys.stderr)
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def http_get(url, extra_headers=None, timeout=20, browser=True):
    """browser=True adds Chrome UA + Accept headers; some sites (FRED) reject those."""
    headers = dict(BROWSER_HEADERS) if browser else {}
    if extra_headers:
        headers.update(extra_headers)
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def safe(fn, default=None, label=None):
    """Run fn(), swallow exceptions, optionally log to stderr."""
    try:
        return fn()
    except Exception as e:
        if label:
            print(f"WARN: {label} failed: {e}", file=sys.stderr)
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Source 1: yfinance — quotes for VIX/MOVE/VVIX/yields/DXY/JPY/ETFs
# ─────────────────────────────────────────────────────────────────────────────
YF_TICKERS = {
    "SPX":    "^GSPC",
    "NDX":    "^NDX",
    "QQQ":    "QQQ",
    "SPY":    "SPY",
    "VIX":    "^VIX",
    "MOVE":   "^MOVE",
    "VVIX":   "^VVIX",
    "TNX":    "^TNX",     # 10Y
    "TYX":    "^TYX",     # 30Y
    "DXY":    "DX-Y.NYB",
    "USDJPY": "JPY=X",
    "GLD":    "GLD",
    "XLK":    "XLK",
    "XLU":    "XLU",
    "XLP":    "XLP",
    "XLY":    "XLY",
    "XLE":    "XLE",
    "XLF":    "XLF",
    "SMH":    "SMH",
    "RSP":    "RSP",
    "IWM":    "IWM",
}


def pull_yfinance():
    out = {}
    for label, sym in YF_TICKERS.items():
        info = safe(lambda s=sym: yf.Ticker(s).fast_info, default={}, label=f"yf {sym} fast_info")
        try:
            price = info.get("last_price") if info else None
        except Exception:
            price = None

        # Fall back to ticker.info for fields fast_info doesn't carry (PE, 200DMA)
        full = safe(lambda s=sym: yf.Ticker(s).info, default={}, label=f"yf {sym} info")
        out[label] = {
            "symbol": sym,
            "price": price or full.get("regularMarketPrice"),
            "prev_close": full.get("regularMarketPreviousClose"),
            "change_pct": full.get("regularMarketChangePercent"),
            "fifty_two_week_high": full.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": full.get("fiftyTwoWeekLow"),
            "fifty_day_avg": full.get("fiftyDayAverage"),
            "two_hundred_day_avg": full.get("twoHundredDayAverage"),
            "trailing_pe": full.get("trailingPE"),
            "forward_pe": full.get("forwardPE"),
            "ytd_return_pct": full.get("ytdReturn"),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Source 2: FRED CSV (no API key) — credit spreads + treasury yields
# ─────────────────────────────────────────────────────────────────────────────
FRED_SERIES = {
    "HY_OAS":  "BAMLH0A0HYM2",      # ICE BofA US High Yield OAS, %
    "IG_OAS":  "BAMLC0A0CM",        # ICE BofA US Corporate IG OAS, %
    "DGS10":   "DGS10",             # 10Y treasury yield, %
    "DGS30":   "DGS30",             # 30Y treasury yield, %
    "T10Y2Y":  "T10Y2Y",            # 10Y - 2Y term spread (recession indicator)
    "DGS2":    "DGS2",              # 2Y treasury yield
}


def pull_fred(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    # FRED rejects Chrome User-Agent — must use default Python/requests UA
    raw = http_get(url, browser=False)
    df = pd.read_csv(StringIO(raw))
    # FRED column names: ['observation_date', '<SERIES_ID>']; missing values are '.'
    date_col, val_col = df.columns[0], df.columns[1]
    df = df[df[val_col] != "."].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna()
    if len(df) == 0:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    week_ago = df.iloc[-6] if len(df) > 6 else None
    return {
        "series": series_id,
        "latest_date": str(last[date_col]),
        "latest_value": float(last[val_col]),
        "prev_value": float(prev[val_col]) if prev is not None else None,
        "week_ago_value": float(week_ago[val_col]) if week_ago is not None else None,
    }


def pull_all_fred():
    return {k: safe(lambda s=v: pull_fred(s), label=f"FRED {v}") for k, v in FRED_SERIES.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Source 3: CNN Fear & Greed (unofficial JSON)
# ─────────────────────────────────────────────────────────────────────────────
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def pull_cnn_fng():
    raw = http_get(CNN_URL, extra_headers={
        "Origin": "https://www.cnn.com",
        "Referer": "https://www.cnn.com/",
    })
    data = json.loads(raw)
    fng = data.get("fear_and_greed", {})
    return {
        "score": fng.get("score"),
        "rating": fng.get("rating"),
        "timestamp": fng.get("timestamp"),
        "previous_close": fng.get("previous_close"),
        "previous_1_week": fng.get("previous_1_week"),
        "previous_1_month": fng.get("previous_1_month"),
        "previous_1_year": fng.get("previous_1_year"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Source 4: multpl.com — Shiller CAPE + SPX trailing PE
# ─────────────────────────────────────────────────────────────────────────────
def pull_multpl(slug, label):
    url = f"https://www.multpl.com/{slug}"
    raw = http_get(url)
    # The current value is in the meta description tag, e.g.:
    # 'Current Shiller PE Ratio is 42.05, a change of +0.35 ...'
    m = re.search(
        rf"Current {re.escape(label)} is ([0-9]+\.?[0-9]*)"
        rf"(?:.*?change of ([+\-][0-9]+\.?[0-9]*))?",
        raw, re.DOTALL,
    )
    if not m:
        return None
    return {
        "value": float(m.group(1)),
        "change_from_prev_close": float(m.group(2)) if m.group(2) else None,
        "source_url": url,
    }


def pull_multpl_all():
    return {
        "shiller_pe":      safe(lambda: pull_multpl("shiller-pe",       "Shiller PE Ratio"),       label="multpl shiller"),
        "spx_trailing_pe": safe(lambda: pull_multpl("s-p-500-pe-ratio", "S&P 500 PE Ratio"),       label="multpl spx_pe"),
        "spx_dividend_yield": safe(lambda: pull_multpl("s-p-500-dividend-yield", "S&P 500 Dividend Yield"), label="multpl spx_dy"),
        "buffett_indicator": safe(lambda: pull_multpl("buffett-indicator", "Buffett Indicator"), label="multpl buffett"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Source 5: Compute % above 200DMA from SPX top constituents (yfinance)
# ─────────────────────────────────────────────────────────────────────────────
# Top 50 SPX names by weight as proxy for full S&P 500 breadth.
# Using just top 50 is biased toward mega-cap, so we mark it as `proxy_only`.
SPX_TOP_50 = [
    "NVDA","MSFT","AAPL","AMZN","GOOGL","META","BRK-B","AVGO","TSLA","JPM",
    "WMT","LLY","V","XOM","UNH","MA","ORCL","JNJ","PG","COST",
    "HD","NFLX","ABBV","BAC","CRM","KO","CVX","WFC","MRK","CSCO",
    "TMUS","PEP","AMD","ADBE","LIN","ACN","ABT","MCD","NOW","TMO",
    "GE","ISRG","TXN","DIS","INTU","IBM","PM","DHR","CAT","RTX",
]


def pull_breadth_proxy():
    """% of SPX top 50 trading above their 200-day moving average."""
    above = 0
    total = 0
    misses = []
    for sym in SPX_TOP_50:
        info = safe(lambda s=sym: yf.Ticker(s).info, default=None)
        if not info:
            misses.append(sym)
            continue
        price = info.get("regularMarketPrice")
        ma200 = info.get("twoHundredDayAverage")
        if price is None or ma200 is None or ma200 == 0:
            misses.append(sym)
            continue
        total += 1
        if price > ma200:
            above += 1
    if total == 0:
        return None
    return {
        "above": above,
        "total": total,
        "pct_above_200dma_top50": round(100.0 * above / total, 2),
        "missing_tickers": misses,
        "note": "PROXY: SPX top 50 by weight, not the full $S5TH index",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scoring — deterministic 8-layer, 0-2 per layer, max 16
# ─────────────────────────────────────────────────────────────────────────────
def _bucket(value, green_lt, yellow_lt, *, reverse=False):
    """Return 0/1/2 score. reverse=True means lower=worse (e.g. VIX <14 = euphoric)."""
    if value is None:
        return None
    if reverse:
        if value > green_lt:  return 0
        if value > yellow_lt: return 1
        return 2
    else:
        if value < green_lt:  return 0
        if value < yellow_lt: return 1
        return 2


def score_all(d):
    """d = {yf:..., fred:..., cnn:..., multpl:..., breadth:...}"""
    scores = {}
    triggers = []

    # Layer 1: Valuation
    cape = (d["multpl"].get("shiller_pe") or {}).get("value")
    spx_pe = (d["multpl"].get("spx_trailing_pe") or {}).get("value")
    cape_score  = _bucket(cape,   green_lt=28, yellow_lt=35)
    spx_score   = _bucket(spx_pe, green_lt=22, yellow_lt=27)
    layer1 = max(x for x in [cape_score, spx_score, 0] if x is not None)
    scores["valuation"] = {"score": layer1, "cape": cape, "spx_trailing_pe": spx_pe}
    if cape and cape > 38: triggers.append(f"Shiller CAPE {cape} > 38 (extreme)")

    # Layer 2: Volatility — VIX <18=complacency, <14=euphoria; MOVE <80=bond complacency
    vix  = d["yf"]["VIX"]["price"]
    move = d["yf"]["MOVE"]["price"]
    if vix is None: vix_score = None
    elif vix < 14: vix_score = 2
    elif vix < 18: vix_score = 2
    elif vix < 25: vix_score = 1
    else:           vix_score = 0
    move_score = _bucket(move, green_lt=120, yellow_lt=80)  # reverse logic
    if move is not None:
        if move < 70:    move_score = 2
        elif move < 100: move_score = 1
        else:             move_score = 0
    layer2 = max(x for x in [vix_score, move_score, 0] if x is not None)
    scores["volatility"] = {"score": layer2, "vix": vix, "move": move}
    if vix and vix < 18: triggers.append(f"VIX {vix} < 18 (exit-signal threshold)")
    if vix and vix < 14: triggers.append(f"VIX {vix} < 14 (euphoria)")

    # Layer 3: Sentiment — CNN F&G
    fng = (d["cnn"] or {}).get("score")
    if fng is None: fng_score = None
    elif fng > 85:   fng_score = 2
    elif fng > 75:   fng_score = 2
    elif fng > 60:   fng_score = 1
    elif fng < 25:   fng_score = 0   # extreme fear = buy, not warning
    else:             fng_score = 0
    scores["sentiment"] = {"score": fng_score or 0, "cnn_fng": fng}
    if fng and fng > 85: triggers.append(f"CNN F&G {fng} > 85 (extreme greed)")

    # Layer 4: Credit
    hy = (d["fred"]["HY_OAS"] or {}).get("latest_value")  # in %
    ig = (d["fred"]["IG_OAS"] or {}).get("latest_value")
    hy_bps = hy * 100 if hy else None
    if hy_bps is None: hy_score = None
    elif hy_bps < 280:  hy_score = 2  # complacency
    elif hy_bps < 400:  hy_score = 1
    elif hy_bps > 600:  hy_score = 2  # stress
    else:                hy_score = 0
    layer4 = hy_score or 0
    scores["credit"] = {"score": layer4, "hy_oas_bps": hy_bps, "ig_oas_bps": (ig*100 if ig else None)}

    # Layer 5: Currency / carry
    jpy = d["yf"]["USDJPY"]["price"]
    dxy = d["yf"]["DXY"]["price"]
    if jpy is None: jpy_score = None
    elif jpy > 160: jpy_score = 2
    elif jpy > 155: jpy_score = 1
    else:            jpy_score = 0
    scores["currency"] = {"score": jpy_score or 0, "usdjpy": jpy, "dxy": dxy}
    if jpy and jpy > 160: triggers.append(f"USD/JPY {jpy} > 160 (BOJ intervention zone)")

    # Layer 6: Breadth
    br = d["breadth"]
    if br and br.get("pct_above_200dma_top50") is not None:
        pct = br["pct_above_200dma_top50"]
        if pct < 40: br_score = 2
        elif pct < 60: br_score = 1
        elif pct < 75: br_score = 1
        else:           br_score = 0
    else:
        br_score = None
    scores["breadth"] = {"score": br_score or 0, "pct_above_200dma_top50": br.get("pct_above_200dma_top50") if br else None}

    # Layer 7: CTA flow — no public API; manual
    scores["cta_flow"] = {"score": 0, "note": "No public API; check Goldman PB report manually"}

    # Layer 8: Sector euphoria — SMH +YoY > 80% OR XLK YoY > 35% = euphoric
    smh_yoy = d["yf"]["SMH"].get("change_pct")
    xlk_p   = d["yf"]["XLK"]["price"]
    xlk_200 = d["yf"]["XLK"]["two_hundred_day_avg"]
    smh_p   = d["yf"]["SMH"]["price"]
    smh_52w_low = d["yf"]["SMH"]["fifty_two_week_low"]
    smh_52w_yoy = ((smh_p - smh_52w_low) / smh_52w_low * 100) if (smh_p and smh_52w_low) else None
    sector_score = 0
    if smh_52w_yoy and smh_52w_yoy > 100: sector_score = 2
    elif smh_52w_yoy and smh_52w_yoy > 50: sector_score = 1
    scores["sector_rotation"] = {
        "score": sector_score,
        "smh_52w_low_to_now_pct": round(smh_52w_yoy, 1) if smh_52w_yoy else None,
        "xlk_vs_200dma_pct": round((xlk_p / xlk_200 - 1) * 100, 1) if xlk_p and xlk_200 else None,
    }

    total = sum(s["score"] for s in scores.values())
    if total <= 3:    regime = "🟢 GREEN"
    elif total <= 7:  regime = "🟡 YELLOW"
    elif total <= 11: regime = "🟠 ORANGE"
    else:              regime = "🔴 RED"

    return {"layers": scores, "composite": total, "max": 16, "regime": regime, "triggers": triggers}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true",
                    help="Emit raw JSON only, no human header")
    ap.add_argument("--skip-breadth", action="store_true",
                    help="Skip breadth computation (50 yfinance calls — slow)")
    args = ap.parse_args()

    out = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "yf":      pull_yfinance(),
        "fred":    pull_all_fred(),
        "cnn":     safe(pull_cnn_fng, label="CNN F&G"),
        "multpl":  pull_multpl_all(),
        "breadth": (None if args.skip_breadth else safe(pull_breadth_proxy, label="breadth")),
    }
    out["scoring"] = score_all(out)

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
