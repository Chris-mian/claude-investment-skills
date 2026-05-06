#!/usr/bin/env python3
"""
SWING ALPHA SCAN (1-3 weeks)

Primary signals (any 2 must hit):
1. Earnings within 21 days + ESP > 0 + recent beat history
2. Short squeeze: short% > 15% + days-to-cover > 5
3. Insider cluster buy within last 14 days
4. Mean reversion: -10~-15% from 30d high + bounce confirmed

Output: top 5 candidates ranked by composite score.
"""
import sys, json, math, yfinance as yf
from datetime import datetime, timedelta
sys.path.insert(0, "/Users/zzizhao/.claude/skills/find-alpha/scripts")
from _universe import ALL_TICKERS, BLACKLIST

NOW = datetime.now()
CUTOFF_INSIDER = (NOW - timedelta(days=14)).strftime("%Y-%m-%d")
CUTOFF_EARNINGS = NOW + timedelta(days=21)

def score(ticker):
    if ticker in BLACKLIST:
        return None
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        hist = tk.history(period="3mo")
        if len(hist) < 30:
            return None
        last = float(hist["Close"].iloc[-1])
        hi30 = float(hist["High"].tail(30).max())
        from_30d_hi = (last/hi30 - 1) * 100
        ma20 = float(hist["Close"].tail(20).mean())
        rets = hist["Close"].pct_change().dropna().tail(14)
        gains = rets[rets > 0].sum()
        losses = -rets[rets < 0].sum()
        rsi = 100 - 100/(1 + (gains/losses)) if losses > 0 else 50
        # Short data
        short_pct = info.get("shortPercentOfFloat", 0) or 0
        # Earnings
        next_earn = None
        try:
            cal = tk.calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    next_earn = ed[0] if isinstance(ed, list) else ed
        except: pass
        days_to_earn = None
        if next_earn:
            try:
                ed_dt = next_earn if isinstance(next_earn, datetime) else datetime.strptime(str(next_earn)[:10], "%Y-%m-%d")
                days_to_earn = (ed_dt - NOW).days
            except: pass
        # Insider recent
        recent_insider_buy_$ = 0
        recent_insider_sell_$ = 0
        try:
            it = tk.get_insider_transactions()
            if it is not None:
                for r in it.to_dict(orient="records"):
                    text = str(r.get("Text","")).lower()
                    date = str(r.get("Start Date",""))[:10]
                    if date < CUTOFF_INSIDER:
                        continue
                    val = r.get("Value", 0)
                    if not val or isinstance(val, str): continue
                    if "purchase at price" in text:
                        recent_insider_buy_$ += float(val)
                    elif "sale at price" in text:
                        recent_insider_sell_$ += float(val)
        except: pass

        # Score components (0-10 each)
        s_earnings = 0
        if days_to_earn is not None and 0 < days_to_earn <= 21:
            s_earnings = 8 if days_to_earn <= 7 else 6
        s_short = 0
        if short_pct > 0.15:
            s_short = min(10, short_pct * 50)
        s_insider = 0
        if recent_insider_buy_$ > recent_insider_sell_$ * 2 and recent_insider_buy_$ > 100000:
            s_insider = min(10, recent_insider_buy_$ / 100000)
        s_meanrev = 0
        if -15 < from_30d_hi < -8 and 30 < rsi < 50 and last > ma20 * 0.97:
            s_meanrev = 7

        hits = sum(1 for x in [s_earnings, s_short, s_insider, s_meanrev] if x >= 6)
        if hits < 2:
            return None
        composite = (s_earnings + s_short + s_insider + s_meanrev) / 4
        return {
            "ticker": ticker,
            "name": info.get("shortName", ""),
            "last": round(last, 2),
            "score": round(composite, 1),
            "hits": hits,
            "days_to_earn": days_to_earn,
            "short_pct": round(short_pct * 100, 1),
            "rsi": round(rsi, 0),
            "from_30d_hi": round(from_30d_hi, 1),
            "insider_buy_14d_$": int(recent_insider_buy_$),
            "insider_sell_14d_$": int(recent_insider_sell_$),
            "components": {
                "earnings": s_earnings,
                "short_squeeze": s_short,
                "insider_cluster": s_insider,
                "mean_rev": s_meanrev,
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
        "horizon": "swing (1-3 weeks)",
        "scan_date": NOW.strftime("%Y-%m-%d"),
        "candidates_count": len(results),
        "top_5": results[:5],
    }, indent=2, default=str))
