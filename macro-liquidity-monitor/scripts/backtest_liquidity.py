#!/usr/bin/env python3
"""backtest_liquidity.py — does the liquidity score lead SPX/NDX?

Reconstructs the daily 0-100 score from FRED history (the same formula as
liquidity_pull.py, with SRF/SOFR-tail ≈ 0 historically — negligible 2024-25) and
tests it against forward SPX/NDX returns. Also isolates NET LIQUIDITY (WALCL-TGA-RRP):
its 13-week CHANGE is the one forward-looking factor; its LEVEL is a spurious trap.

All data: FRED CSV (no key). Usage: python backtest_liquidity.py [--start YYYY-MM-DD]

Key 2024-05..2026-05 findings:
  - score LEVEL → fwd-1w/1m: corr ≈ +0.07 (coincident, NOT a weekly timer)
  - regime buckets → fwd-3m: 🟢/🟡 ≈ +4–6%, 🔴 ≈ NDX −1% (value = downside avoidance)
  - net-liq 13wk CHANGE → fwd-3m: +0.26 SPX / +0.33 NDX  (the forward signal)
  - net-liq LEVEL ~ SPX level: −0.71  (spurious — both trended apart on AI/earnings)
Caveats: 2yr is one bull regime; overlapping fwd windows inflate significance.
"""
import argparse, io
import numpy as np, pandas as pd, requests


def fred(sid, start):
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}", timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), na_values=["."])
    df.columns = ["date", sid]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[sid]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-05-01")
    args = ap.parse_args()

    S = {s: fred(s, args.start) for s in
         ["SOFR", "IORB", "RRPONTSYD", "WRESBAL", "WTREGEN", "WALCL", "SP500", "NASDAQCOM"]}
    idx = pd.bdate_range(args.start, S["SP500"].index.max())
    df = pd.DataFrame({k: v.reindex(idx).ffill() for k, v in S.items()})

    df["spread_bp"]  = (df["SOFR"] - df["IORB"]) * 100
    df["reserves_t"] = df["WRESBAL"] / 1e6
    df["tga_bn"]     = df["WTREGEN"] / 1e3
    df["tga_wow"]    = df["tga_bn"] - df["tga_bn"].shift(5)
    df["net_liq_bn"] = df["WALCL"] / 1e3 - df["tga_bn"] - df["RRPONTSYD"]
    df["netliq_13w_chg"] = df["net_liq_bn"] - df["net_liq_bn"].shift(65)

    sp  = lambda b: np.clip(-b * 2.5, -30, 35)
    rp  = lambda t: np.where(t > 3.4, 8, np.where(t > 3.1, 4, np.where(t > 2.9, 0, -10)))
    tp  = lambda w: np.where(w < -25, 5, np.where(w <= 25, 0, np.where(w <= 150, -5, -10)))
    mp  = lambda m: np.where(m > 300, 12, np.where(m > 100, 6, np.where(m >= -100, 0, np.where(m >= -300, -6, -12))))
    df["score"] = (50 + sp(df["spread_bp"]) + rp(df["reserves_t"]) + tp(df["tga_wow"]) + mp(df["netliq_13w_chg"])).clip(0, 100)
    df["regime"] = pd.cut(df["score"], [-1, 24, 44, 59, 79, 100],
                          labels=["🔴 STRESS", "🟠 TIGHT", "⚪ BAL", "🟡 AMPLE", "🟢 ABUND"])

    for px, tag in [("SP500", "SPX"), ("NASDAQCOM", "NDX")]:
        for h, nm in [(5, "1w"), (21, "1m"), (63, "3m")]:
            df[f"{tag}_fwd_{nm}"] = df[px].shift(-h) / df[px] - 1

    d = df.dropna(subset=["score"])
    print(f"obs {len(d)}  {d.index.min().date()}..{d.index.max().date()}  current score {d['score'].iloc[-1]:.0f}")
    print(f"net-liq 13wk momentum now: {d['netliq_13w_chg'].iloc[-1]:+.0f}B")

    print("\n=== score LEVEL → forward returns (corr) ===")
    for tag in ["SPX", "NDX"]:
        print(f"  {tag}: " + "  ".join(f"{nm}={d['score'].corr(d[f'{tag}_fwd_{nm}']):+.2f}" for nm in ["1w", "1m", "3m"]))

    print("\n=== avg forward return by regime band ===")
    g = d.groupby("regime", observed=True)
    print(pd.DataFrame({"n": g.size(),
                        "SPX_fwd3m%": (g["SPX_fwd_3m"].mean() * 100).round(2),
                        "NDX_fwd3m%": (g["NDX_fwd_3m"].mean() * 100).round(2)}).to_string())

    print("\n=== net liquidity: LEVEL trap vs 13wk-CHANGE signal ===")
    print(f"  level corr (contemporaneous):  netliq~SPX {d['net_liq_bn'].corr(d['SP500']):+.2f}  netliq~NDX {d['net_liq_bn'].corr(d['NASDAQCOM']):+.2f}")
    for tag in ["SPX", "NDX"]:
        print(f"  Δnetliq(13w)→{tag} fwd:  " + "  ".join(f"{nm}={d['netliq_13w_chg'].corr(d[f'{tag}_fwd_{nm}']):+.2f}" for nm in ["1m", "3m"]))


if __name__ == "__main__":
    main()
