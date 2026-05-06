#!/usr/bin/env python3
"""
Live Quote + Technicals Puller (yfinance fallback when yfmcp not loaded)

Pulls: last price, day pct, day range, volume vs 20d avg, MA20/50/200,
1y high/low, % from 1y high, RV30 annualized, next earnings date.

Usage:
  uv run --with yfinance python quote_pull.py "TICKER1,TICKER2,..."
"""
import sys, json, math, yfinance as yf

def pull(tickers):
    out = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="1y", auto_adjust=False)
            if len(hist) == 0:
                out[t] = {"err": "no history"}
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
            day_pct = ((last - prev) / prev * 100) if prev else None
            day_lo = float(hist["Low"].iloc[-1])
            day_hi = float(hist["High"].iloc[-1])
            vol = int(hist["Volume"].iloc[-1])
            avg_vol = int(hist["Volume"].tail(20).mean())
            closes = hist["Close"]
            ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
            ma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
            ma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
            hi52 = float(hist["High"].max())
            lo52 = float(hist["Low"].min())
            from_hi = (last / hi52 - 1) * 100
            rets = closes.pct_change().dropna().tail(30)
            rv30 = float(rets.std() * math.sqrt(252) * 100) if len(rets) >= 10 else None
            earnings = None
            try:
                cal = tk.calendar
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed:
                        earnings = str(ed[0]) if isinstance(ed, list) else str(ed)
            except Exception:
                pass
            out[t] = {
                "last": round(last, 2),
                "as_of": str(hist.index[-1].date()),
                "day_pct": round(day_pct, 2) if day_pct is not None else None,
                "day_low": round(day_lo, 2),
                "day_high": round(day_hi, 2),
                "volume": vol,
                "avg_vol_20d": avg_vol,
                "vol_ratio": round(vol / avg_vol, 2) if avg_vol else None,
                "ma20": round(ma20, 2) if ma20 else None,
                "ma50": round(ma50, 2) if ma50 else None,
                "ma200": round(ma200, 2) if ma200 else None,
                "hi_1y": round(hi52, 2),
                "lo_1y": round(lo52, 2),
                "pct_from_1y_hi": round(from_hi, 1),
                "rv30_ann_pct": round(rv30, 1) if rv30 else None,
                "next_earnings": earnings,
            }
        except Exception as e:
            out[t] = {"err": str(e)[:120]}
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: quote_pull.py 'TICKER1,TICKER2'")
        sys.exit(1)
    tickers = sys.argv[1].split(",")
    print(json.dumps(pull(tickers), indent=2, default=str))
