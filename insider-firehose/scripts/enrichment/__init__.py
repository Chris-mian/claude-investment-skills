"""enrichment — adds valuation + price action + score to each Form 4 alert.

Entry point: enrich(ticker, filing) → dict with valuation/price/company/score.

Designed to be NON-FATAL: any failure (network, parse, rate-limit) returns
an empty dict and the caller falls back to the basic v2.0 alert. The
firehose must never break because of enrichment.
"""
from .pipeline import enrich, is_enabled, set_enabled

__all__ = ["enrich", "is_enabled", "set_enabled"]
