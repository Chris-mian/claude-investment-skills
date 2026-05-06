#!/usr/bin/env python3
"""
Option Walls Analyzer — finds gamma walls (strike concentrations) by OI.

Usage:
  uv run --with yfinance python option_walls.py TICKER [num_expiries]
"""
import sys, json, yfinance as yf

def analyze(ticker, num_expiries=4):
    tk = yf.Ticker(ticker)
    spot = float(tk.history(period="2d")["Close"].iloc[-1])
    out = {"ticker": ticker, "spot": spot, "by_expiry": {}}
    for exp in tk.options[:num_expiries]:
        try:
            ch = tk.option_chain(exp)
            c = ch.calls[["strike","openInterest","volume","impliedVolatility","lastPrice"]].copy().fillna(0)
            p = ch.puts[["strike","openInterest","volume","impliedVolatility","lastPrice"]].copy().fillna(0)
            c = c[(c.strike >= spot * 0.7) & (c.strike <= spot * 1.5)]
            p = p[(p.strike >= spot * 0.7) & (p.strike <= spot * 1.5)]
            top_calls = c.sort_values("openInterest", ascending=False).head(10)
            top_puts = p.sort_values("openInterest", ascending=False).head(10)
            out["by_expiry"][exp] = {
                "top_call_OI": [{"K":float(r.strike),"OI":int(r.openInterest),"V":int(r.volume),"IV":round(float(r.impliedVolatility)*100,1)} for _,r in top_calls.iterrows()],
                "top_put_OI": [{"K":float(r.strike),"OI":int(r.openInterest),"V":int(r.volume),"IV":round(float(r.impliedVolatility)*100,1)} for _,r in top_puts.iterrows()],
            }
        except Exception as e:
            out["by_expiry"][exp] = {"err": str(e)[:120]}
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: option_walls.py TICKER [num_expiries]")
        sys.exit(1)
    ticker = sys.argv[1].upper()
    n = int(sys.argv[2]) if len(sys.argv) >= 3 else 4
    print(json.dumps(analyze(ticker, n), indent=2, default=str))
