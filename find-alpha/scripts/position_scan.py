#!/usr/bin/env python3
"""
POSITION ALPHA SCAN (1-3 months)

Primary signals (any 2 must hit):
1. Insider cluster buy within 60 days (ratio buy:sell ≥ 2:1, $ ≥ $500k)
2. Analyst PT mean > current price by ≥ 15%
3. NTM EPS revision > +5% in last 30 days (proxied via fwd PE drop)
4. Mean reversion: near MA200 + RSI 30-50 + recent insider activity
5. Theme fit: CPU inference / photonics / OSAT / nuclear

Output: top 5 candidates.
"""
import sys, json, math, yfinance as yf
from datetime import datetime, timedelta
sys.path.insert(0, "/Users/zzizhao/.claude/skills/find-alpha/scripts")
from _universe import ALL_TICKERS, BLACKLIST, UNIVERSE

NOW = datetime.now()
CUTOFF = (NOW - timedelta(days=60)).strftime("%Y-%m-%d")

# Theme fit names (high-conviction baskets)
THEME_FIT = set(UNIVERSE["cpu_inference_edge"] + UNIVERSE["ai_dc_optical"] + UNIVERSE["osat_packaging"] + UNIVERSE["ai_power_nuclear"])

def score(ticker):
    if ticker in BLACKLIST:
        return None
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period="1y")
        if len(hist) < 100: return None
        last = float(hist["Close"].iloc[-1])
        ma200 = float(hist["Close"].tail(200).mean()) if len(hist) >= 200 else None
        rets = hist["Close"].pct_change().dropna().tail(14)
        gains = rets[rets > 0].sum()
        losses = -rets[rets < 0].sum()
        rsi = 100 - 100/(1 + (gains/losses)) if losses > 0 else 50

        target = info.get("targetMeanPrice")
        upside_to_target = ((target/last - 1) * 100) if (target and last) else 0

        # Insider 60d
        buy_$ = sell_$ = 0
        cluster_count = 0
        unique_buyers = set()
        try:
            it = tk.get_insider_transactions()
            if it is not None:
                for r in it.to_dict(orient="records"):
                    text = str(r.get("Text","")).lower()
                    date = str(r.get("Start Date",""))[:10]
                    if date < CUTOFF: continue
                    val = r.get("Value", 0)
                    if not val or isinstance(val, str): continue
                    if "purchase at price" in text:
                        buy_$ += float(val)
                        unique_buyers.add(r.get("Insider",""))
                    elif "sale at price" in text:
                        sell_$ += float(val)
        except: pass

        s_insider = 0
        if buy_$ >= 500000 and buy_$ >= sell_$ * 2:
            s_insider = min(10, buy_$ / 200000)
            if len(unique_buyers) >= 2:
                s_insider = min(10, s_insider + 2)  # cluster bonus

        s_target = 0
        if upside_to_target >= 15:
            s_target = min(8, upside_to_target / 5)

        s_meanrev = 0
        if ma200 and 0.85 < (last/ma200) < 1.05 and 30 < rsi < 55:
            s_meanrev = 6

        s_theme = 8 if ticker in THEME_FIT else 0

        # Forward PE attractive
        fwd_pe = info.get("forwardPE", 999) or 999
        rev_growth = info.get("revenueGrowth", 0) or 0
        s_garp = 0
        if 0 < fwd_pe < 30 and rev_growth > 0.15:
            s_garp = 7

        hits = sum(1 for x in [s_insider, s_target, s_meanrev, s_theme, s_garp] if x >= 6)
        if hits < 2: return None
        composite = (s_insider + s_target + s_meanrev + s_theme + s_garp) / 5

        return {
            "ticker": ticker,
            "name": info.get("shortName", ""),
            "last": round(last, 2),
            "target": target,
            "upside_to_pt_pct": round(upside_to_target, 1),
            "fwd_pe": round(fwd_pe, 1) if fwd_pe < 999 else None,
            "rev_growth_pct": round(rev_growth * 100, 1),
            "ma200_dist_pct": round((last/ma200 - 1) * 100, 1) if ma200 else None,
            "rsi": round(rsi, 0),
            "insider_buy_60d_$": int(buy_$),
            "insider_sell_60d_$": int(sell_$),
            "cluster_buyers": len(unique_buyers),
            "score": round(composite, 1),
            "hits": hits,
            "components": {
                "insider": s_insider,
                "target_upside": s_target,
                "mean_rev": s_meanrev,
                "theme_fit": s_theme,
                "garp": s_garp,
            }
        }
    except Exception as e:
        return None

if __name__ == "__main__":
    results = []
    for t in ALL_TICKERS:
        r = score(t)
        if r: results.append(r)
    results.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({
        "horizon": "position (1-3 months)",
        "scan_date": NOW.strftime("%Y-%m-%d"),
        "candidates_count": len(results),
        "top_5": results[:5],
    }, indent=2, default=str))
