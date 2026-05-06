#!/usr/bin/env python3
"""
LEAPS THESIS SCAN (6-12+ months)

Primary signals (any 2 must hit):
1. Founder/family/10%+ holder open-market buy ≥ $5M (AMKR Kim family pattern)
2. Forward P/E < 25x AND revenue growth > 20% (GARP)
3. Below MA200 (early cycle) + cash > 15% mcap + low debt
4. Multi-year secular thesis fit (CPU inference, AI DC, edge AI, nuclear, US re-shoring)
5. New CEO with skin-in-the-game (>$1M open market buy in first 3 months as CEO)

Output: top 5 LEAPS candidates.
"""
import sys, json, yfinance as yf
from datetime import datetime, timedelta
sys.path.insert(0, "/Users/zzizhao/.claude/skills/find-alpha/scripts")
from _universe import ALL_TICKERS, BLACKLIST, UNIVERSE

NOW = datetime.now()
CUTOFF = (NOW - timedelta(days=365)).strftime("%Y-%m-%d")

SECULAR_THEMES = set(
    UNIVERSE["cpu_inference_edge"] +
    UNIVERSE["ai_dc_optical"] +
    UNIVERSE["osat_packaging"] +
    UNIVERSE["ai_power_nuclear"] +
    UNIVERSE["uranium_materials"] +
    UNIVERSE["memory_storage"]
)

def score(ticker):
    if ticker in BLACKLIST:
        return None
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period="2y")
        if len(hist) < 200: return None
        last = float(hist["Close"].iloc[-1])
        ma200 = float(hist["Close"].tail(200).mean())
        below_ma200 = last < ma200

        mcap = info.get("marketCap", 0) or 0
        cash = info.get("totalCash", 0) or 0
        debt = info.get("totalDebt", 0) or 0
        cash_pct = (cash/mcap * 100) if mcap > 0 else 0
        debt_to_cash = debt/cash if cash > 0 else 999

        fwd_pe = info.get("forwardPE", 999) or 999
        rev_growth = info.get("revenueGrowth", 0) or 0

        # Big insider buys (founder / 10%+ / family / new CEO)
        big_buys_$ = 0
        big_buyers = []
        try:
            it = tk.get_insider_transactions()
            if it is not None:
                for r in it.to_dict(orient="records"):
                    text = str(r.get("Text","")).lower()
                    date = str(r.get("Start Date",""))[:10]
                    pos = str(r.get("Position","")).lower()
                    if date < CUTOFF: continue
                    val = r.get("Value", 0)
                    if not val or isinstance(val, str): continue
                    if "purchase at price" in text:
                        v = float(val)
                        # Bonus weight for founder/10% holder/CEO buys
                        if "beneficial owner" in pos or "10%" in pos or "ceo" in pos or "chief executive" in pos or "chairman" in pos or "founder" in pos:
                            big_buys_$ += v
                            big_buyers.append({"date": date, "insider": r.get("Insider",""), "pos": r.get("Position",""), "$": int(v)})
        except: pass

        # Score components
        s_big_insider = 0
        if big_buys_$ >= 5_000_000:
            s_big_insider = min(10, big_buys_$ / 1_000_000)
        elif big_buys_$ >= 1_000_000:
            s_big_insider = 6

        s_garp = 0
        if 0 < fwd_pe < 25 and rev_growth > 0.2:
            s_garp = 8

        s_early_cycle = 0
        if below_ma200 and cash_pct > 15 and debt_to_cash < 0.5:
            s_early_cycle = 7

        s_theme = 8 if ticker in SECULAR_THEMES else 0

        s_balance_sheet = 0
        if cash_pct > 15 and debt_to_cash < 1:
            s_balance_sheet = 6

        hits = sum(1 for x in [s_big_insider, s_garp, s_early_cycle, s_theme, s_balance_sheet] if x >= 6)
        if hits < 2: return None
        composite = (s_big_insider + s_garp + s_early_cycle + s_theme + s_balance_sheet) / 5

        return {
            "ticker": ticker,
            "name": info.get("shortName", ""),
            "last": round(last, 2),
            "mcap_$B": round(mcap / 1e9, 2) if mcap else None,
            "fwd_pe": round(fwd_pe, 1) if fwd_pe < 999 else None,
            "rev_growth_pct": round(rev_growth * 100, 1),
            "cash_pct_of_mcap": round(cash_pct, 1),
            "below_ma200": below_ma200,
            "ma200_dist_pct": round((last/ma200 - 1) * 100, 1),
            "big_insider_buys_$": int(big_buys_$),
            "big_buyers": big_buyers[:5],
            "score": round(composite, 1),
            "hits": hits,
            "components": {
                "big_insider": s_big_insider,
                "garp": s_garp,
                "early_cycle": s_early_cycle,
                "theme_fit": s_theme,
                "balance_sheet": s_balance_sheet,
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
        "horizon": "leaps (6-12+ months)",
        "scan_date": NOW.strftime("%Y-%m-%d"),
        "candidates_count": len(results),
        "top_5": results[:5],
    }, indent=2, default=str))
