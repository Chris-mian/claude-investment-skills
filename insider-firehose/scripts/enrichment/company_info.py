"""company_info.py — one-line business description.

yfinance ships a long-form longBusinessSummary. We extract the first sentence
or first ~140 chars to keep Telegram messages compact.
"""
from __future__ import annotations

import re
import sys


def _first_sentence(text: str, max_len: int = 180) -> str:
    """Return first sentence, truncated to max_len if needed."""
    if not text:
        return ""
    # Strip whitespace and corporate boilerplate prefixes
    text = text.strip()
    # First sentence break — period followed by space + capital letter
    m = re.search(r"\.(?=\s+[A-Z])", text)
    first = text[: m.start() + 1] if m else text
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first


def pull_company_info(ticker: str, valuation: dict | None = None) -> dict:
    """Pull company one-liner + sector/industry. Empty dict on failure.

    If valuation dict already has sector/industry, reuses them to save an API
    call. Always tries to fetch business summary.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        print(f"[ENRICH-WARN] company yfinance.Ticker({ticker}) failed: {e}",
              file=sys.stderr)
        return {}

    if not info:
        return {}

    summary = info.get("longBusinessSummary") or ""
    one_liner = _first_sentence(summary)

    return {
        "name": info.get("shortName") or info.get("longName") or ticker,
        "sector": info.get("sector") or (valuation or {}).get("sector"),
        "industry": info.get("industry") or (valuation or {}).get("industry"),
        "one_liner": one_liner,
        "country": info.get("country"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
    }
