#!/usr/bin/env python3
"""
Max Pain Calculator — Computes the strike price where total option holder loss is maximized
(= the price where dealers/option writers profit the most when options expire).

Theory: Stock prices "gravitate" toward max pain near expiry due to dealer hedging.
Useful for monthly/quarterly OPEX (third Friday) — anchor for short-term price prediction.

Usage:
  uv run --with yfinance python max_pain.py TICKER [num_expiries]

Output JSON:
{
  "ticker": "NVDA",
  "spot": 198.48,
  "by_expiry": {
    "2026-05-15": {
      "max_pain": 195.0,
      "spot_vs_max_pain_pct": +1.79,
      "interpretation": "Bullish bias - max pain below spot",
      "total_call_oi": 145000,
      "total_put_oi": 132000,
      "put_call_ratio": 0.91,
      "top_5_call_walls": [{"K": 200, "OI": 25000}, ...],
      "top_5_put_walls": [{"K": 190, "OI": 18000}, ...]
    }
  }
}
"""
import sys, json
import yfinance as yf

def calculate_max_pain(calls_df, puts_df):
    """
    Max pain = strike where sum of in-the-money option holder losses is maximized.
    For calls: holder loses if strike > expiry price (option expires OTM)
    For puts: holder loses if strike < expiry price (option expires OTM)

    Total pain at strike K = Σ(ITM call OI × (K - call_strike)) + Σ(ITM put OI × (put_strike - K))
    Max pain = strike where this is maximized for option WRITERS (= max loss for holders)
    """
    # All possible expiry prices = all strikes
    all_strikes = sorted(set(list(calls_df["strike"]) + list(puts_df["strike"])))

    pain_per_strike = []
    for K in all_strikes:
        # Pain for call holders: only ITM calls (strike < K) lose
        # If K is the expiry price, calls with strike < K are ITM and have value (K - strike) per contract
        # Call WRITER pain = sum(call_OI × max(K - call_strike, 0))
        call_pain = sum(
            row["openInterest"] * max(K - row["strike"], 0)
            for _, row in calls_df.iterrows()
            if row["openInterest"] > 0
        )
        # Put WRITER pain = sum(put_OI × max(put_strike - K, 0))
        put_pain = sum(
            row["openInterest"] * max(row["strike"] - K, 0)
            for _, row in puts_df.iterrows()
            if row["openInterest"] > 0
        )
        total_pain = call_pain + put_pain
        pain_per_strike.append((K, total_pain))

    if not pain_per_strike:
        return None
    # Max pain = strike with the LOWEST total pain (writers' profit point)
    # Wait, actually max pain in standard definition = strike where option holders' total loss is max
    # = where writers' profit is MAX
    # Total option holder profit at K = sum(ITM call value) + sum(ITM put value)
    # Max pain price = where this is MIN (holders lose most, writers profit most)
    pain_per_strike.sort(key=lambda x: x[1])
    max_pain_strike = pain_per_strike[0][0]
    return max_pain_strike, pain_per_strike

def analyze(ticker, num_expiries=4):
    tk = yf.Ticker(ticker)
    spot = float(tk.history(period="2d")["Close"].iloc[-1])
    out = {"ticker": ticker, "spot": round(spot, 2), "by_expiry": {}}

    for exp in tk.options[:num_expiries]:
        try:
            ch = tk.option_chain(exp)
            calls = ch.calls[["strike", "openInterest", "volume"]].copy().fillna(0)
            puts = ch.puts[["strike", "openInterest", "volume"]].copy().fillna(0)

            # Filter to relevant range (spot ±50%)
            calls = calls[(calls.strike >= spot * 0.5) & (calls.strike <= spot * 1.5)]
            puts = puts[(puts.strike >= spot * 0.5) & (puts.strike <= spot * 1.5)]

            result = calculate_max_pain(calls, puts)
            if result is None:
                out["by_expiry"][exp] = {"err": "no OI data"}
                continue
            max_pain_strike, pain_curve = result

            spot_vs_mp = (spot - max_pain_strike) / max_pain_strike * 100

            # Interpretation
            if spot_vs_mp > 3:
                interp = "Bearish gravity — spot above max pain, dealers benefit from drift down"
            elif spot_vs_mp < -3:
                interp = "Bullish gravity — spot below max pain, dealers benefit from drift up"
            else:
                interp = "Pinned — spot near max pain, expect chop into expiry"

            total_call_oi = int(calls["openInterest"].sum())
            total_put_oi = int(puts["openInterest"].sum())
            pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

            top_call_walls = (
                calls[calls.openInterest > 0]
                .sort_values("openInterest", ascending=False)
                .head(5)
            )
            top_put_walls = (
                puts[puts.openInterest > 0]
                .sort_values("openInterest", ascending=False)
                .head(5)
            )

            # Highest call OI = resistance (sellers/writers there)
            # Highest put OI = support (sellers/writers there)
            call_wall = float(top_call_walls.iloc[0]["strike"]) if len(top_call_walls) > 0 else None
            put_wall = float(top_put_walls.iloc[0]["strike"]) if len(top_put_walls) > 0 else None

            out["by_expiry"][exp] = {
                "max_pain": round(max_pain_strike, 2),
                "spot_vs_max_pain_pct": round(spot_vs_mp, 2),
                "interpretation": interp,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "put_call_ratio": pcr,
                "key_call_resistance": call_wall,
                "key_put_support": put_wall,
                "top_5_call_walls": [
                    {"K": float(r["strike"]), "OI": int(r["openInterest"])}
                    for _, r in top_call_walls.iterrows()
                ],
                "top_5_put_walls": [
                    {"K": float(r["strike"]), "OI": int(r["openInterest"])}
                    for _, r in top_put_walls.iterrows()
                ],
            }
        except Exception as e:
            out["by_expiry"][exp] = {"err": str(e)[:200]}
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: max_pain.py TICKER [num_expiries]")
        sys.exit(1)
    ticker = sys.argv[1].upper()
    n = int(sys.argv[2]) if len(sys.argv) >= 3 else 4
    print(json.dumps(analyze(ticker, n), indent=2, default=str))
