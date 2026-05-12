"""price_action.py — compute distance from 50DMA / 200DMA / 52W high/low.

Why this matters for insider context:
  - Buying near 52W LOW = high-conviction signal (insider sees value).
  - Buying near 52W HIGH = either momentum-chasing or genuine inflection.
  - Below 200DMA = bearish trend → insider is contrarian / brave / right.
  - Above 200DMA = trend agrees with insider.
"""
from __future__ import annotations

import sys
from typing import Any


def _safe_get(info: dict, key: str, default: Any = None) -> Any:
    v = info.get(key)
    if v is None or v == "Infinity" or v == "-Infinity":
        return default
    return v


def pull_price_action(ticker: str) -> dict:
    """Pull current price + moving averages + 52W context. Empty dict on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        print(f"[ENRICH-WARN] price yfinance.Ticker({ticker}) failed: {e}",
              file=sys.stderr)
        return {}

    if not info:
        return {}

    current = _safe_get(info, "currentPrice") or _safe_get(info, "regularMarketPrice")
    ma50 = _safe_get(info, "fiftyDayAverage")
    ma200 = _safe_get(info, "twoHundredDayAverage")
    high_52w = _safe_get(info, "fiftyTwoWeekHigh")
    low_52w = _safe_get(info, "fiftyTwoWeekLow")
    change_1y_pct = _safe_get(info, "fiftyTwoWeekChangePercent")

    def pct_from(price_val, ref):
        if price_val is None or ref is None or ref == 0:
            return None
        return round(100 * (price_val - ref) / ref, 1)

    return {
        "current": current,
        "ma_50": ma50,
        "ma_200": ma200,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_vs_50dma": pct_from(current, ma50),
        "pct_vs_200dma": pct_from(current, ma200),
        "pct_vs_52w_high": pct_from(current, high_52w),
        "pct_vs_52w_low": pct_from(current, low_52w),
        "change_1y_pct": change_1y_pct,
    }
