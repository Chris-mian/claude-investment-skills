#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filters.py — Eligibility filters for strategic-partner alerts.

筛选条件 —— 决定一个 filing 值不值得推送。

═══════════════════════════════════════════════════════════════════════
  WHY FILTERING IS CRITICAL / 为什么 filter 关键
═══════════════════════════════════════════════════════════════════════

SEC EDGAR ships ~500 8-K filings per day. Most are noise (officer changes,
routine dividends, share buybacks). Without filters, the Telegram channel
becomes useless.
SEC EDGAR 每天 ~500 个 8-K, 大部分是垃圾 (高管变动、分红、回购). 没有过
滤器, Telegram 频道就废了。

Hard filters applied in this order (短路, 越早过滤越好):
顺序排列, 早 fail fast 越好:

  1. Form type / item match     (cheap, no network call)
  2. Strategic investor match   (cheap, in-memory regex)
  3. Amount ≥ $50M              (cheap, regex)
  4. US-listed equity           (1 yfinance call — cache aggressively)
  5. Market cap ≥ $50M          (same yfinance call, no extra cost)

═══════════════════════════════════════════════════════════════════════
  MARKET-CAP THRESHOLD RATIONALE / 市值门槛理由
═══════════════════════════════════════════════════════════════════════

Default $50M because:
  - Below $50M = nano-cap, illiquid, often pump-and-dump
  - PENG was $1.1B mcap when SK Telecom invested → far above
  - Real strategic investments rarely target sub-$50M public companies
默认 $50M:
  - $50M 以下 = 极微盘, 流动性差, 多为 pump-and-dump
  - PENG 接 SK Telecom 投资时市值 $1.1B → 远在阈值之上
  - 真实战略投资极少投 $50M 以下上市公司

User can override via STRATEGIC_MIN_MCAP env var.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# ─── Configurable thresholds / 可配置阈值 ─────────────────────────────────

MIN_MARKET_CAP_USD: int = int(os.environ.get("STRATEGIC_MIN_MCAP", "50000000"))
MIN_DEAL_AMOUNT_USD_M: float = float(os.environ.get("STRATEGIC_MIN_AMOUNT_M", "50"))

# US-listed exchanges (from yfinance's `info["exchange"]` field)
# 美股交易所代码 (yfinance info["exchange"])
US_EXCHANGES: set[str] = {
    "NMS",   # NASDAQ Global Select Market
    "NGM",   # NASDAQ Global Market
    "NCM",   # NASDAQ Capital Market
    "NYQ",   # NYSE
    "ASE",   # NYSE American (formerly AMEX)
    "PCX",   # NYSE Arca
    "BATS",  # BATS / Cboe
    "NAS",   # General NASDAQ (older code)
}


# ─── In-memory caches / 内存缓存 ──────────────────────────────────────────
# Avoid repeated yfinance calls for the same ticker within a single run.
# 避免一次运行内重复调用 yfinance 查同一个 ticker (rate-limit + 性能).

_mcap_cache: dict[str, Optional[float]] = {}
_exchange_cache: dict[str, Optional[str]] = {}


def _fetch_ticker_basics(ticker: str) -> tuple[Optional[float], Optional[str]]:
    """
    Pull (market_cap, exchange) for a ticker via yfinance. Returns (None, None)
    if ticker doesn't exist or yfinance fails.

    通过 yfinance 拉 (market_cap, exchange). 失败返回 (None, None).

    Cached in-memory to avoid duplicate calls within the same cron run.
    """
    # Check cache first
    if ticker in _mcap_cache:
        return (_mcap_cache[ticker], _exchange_cache.get(ticker))

    try:
        import yfinance as yf
    except ImportError:
        print("[FILTER-WARN] yfinance not installed, can't filter by mcap",
              file=sys.stderr)
        _mcap_cache[ticker] = None
        _exchange_cache[ticker] = None
        return (None, None)

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        print(f"[FILTER-WARN] yfinance.Ticker({ticker}) failed: {e}",
              file=sys.stderr)
        _mcap_cache[ticker] = None
        _exchange_cache[ticker] = None
        return (None, None)

    mcap = info.get("marketCap")
    exch = info.get("exchange") or info.get("fullExchangeName")

    # Normalize: yfinance returns mcap as int or None
    # 标准化: yfinance 返回 int 或 None
    mcap_f: Optional[float] = float(mcap) if isinstance(mcap, (int, float)) else None

    _mcap_cache[ticker] = mcap_f
    _exchange_cache[ticker] = exch

    return (mcap_f, exch)


def passes_mcap_filter(ticker: str, min_usd: int = MIN_MARKET_CAP_USD) -> bool:
    """
    True if ticker's market cap ≥ min_usd. False otherwise (including unknown).
    True 当 ticker 市值 ≥ min_usd, 否则 False (包括查不到的情况).

    Default $50M cutoff. Override via STRATEGIC_MIN_MCAP env var.
    """
    mcap, _ = _fetch_ticker_basics(ticker)
    if mcap is None:
        return False
    return mcap >= min_usd


def passes_us_listing_filter(ticker: str) -> bool:
    """
    True if ticker trades on a US exchange (NYSE/NASDAQ/AMEX).
    True 当 ticker 在美国主流交易所上市.

    Why we filter: foreign-only ADRs / pink-sheet listings are harder to
    trade for US retail and often have idiosyncratic risks. We focus on
    investible names.
    过滤理由: foreign-only ADR + 粉单 难以交易 + 异质风险. 只看可投资的票。
    """
    _, exch = _fetch_ticker_basics(ticker)
    if exch is None:
        return False
    return exch in US_EXCHANGES


def passes_amount_filter(
    amount_usd_m: float,
    min_m: float = MIN_DEAL_AMOUNT_USD_M,
) -> bool:
    """
    True if deal amount ≥ min_m millions USD.
    True 当 deal 金额 ≥ min_m millions.

    Default $50M cutoff. Smaller deals exist but signal-to-noise drops fast.
    """
    return amount_usd_m >= min_m


def apply_all_filters(
    ticker: str,
    amount_usd_m: float,
    min_mcap_usd: int = MIN_MARKET_CAP_USD,
    min_amount_m: float = MIN_DEAL_AMOUNT_USD_M,
) -> tuple[bool, str]:
    """
    Apply all filters in fast-fail order. Returns (passes, reason_if_failed).
    按快速 fail 顺序应用所有 filter. 返回 (passes, 失败原因).

    Filter order chosen for cheapest checks first:
      1. amount       (already parsed, free)
      2. ticker valid (string check, free)
      3. yfinance     (network call, cached)

    Args:
        ticker: Issuer ticker (e.g., "PENG")
        amount_usd_m: Already-parsed deal amount in millions
        min_mcap_usd: Market cap floor (default $50M)
        min_amount_m: Deal size floor (default $50M)

    Returns:
        (True, "") on pass; (False, "reason") on fail.
    """
    # 1. Amount filter (cheap)
    if not passes_amount_filter(amount_usd_m, min_amount_m):
        return (False, f"amount ${amount_usd_m:.1f}M < ${min_amount_m}M floor")

    # 2. Ticker sanity (cheap)
    # Ticker format: 1-5 uppercase chars, optionally with dot/dash
    if not ticker or len(ticker) > 6 or not ticker[0].isalpha():
        return (False, f"invalid ticker '{ticker}'")

    # 3. Single yfinance call gets both mcap + exchange
    # 一次 yfinance 调用同时拿 mcap + exchange
    mcap, exch = _fetch_ticker_basics(ticker)
    if mcap is None or exch is None:
        return (False, f"yfinance has no data for '{ticker}' (likely not US-listed or delisted)")

    # 4. US-listed check
    if exch not in US_EXCHANGES:
        return (False, f"exchange '{exch}' not US-listed")

    # 5. Market cap floor
    if mcap < min_mcap_usd:
        return (False, f"mcap ${mcap/1e6:.1f}M < ${min_mcap_usd/1e6:.0f}M floor")

    return (True, "")


def clear_caches() -> None:
    """
    Clear in-memory caches. Useful for tests + long-running processes.
    清空内存缓存. 测试 + 常驻进程用.
    """
    _mcap_cache.clear()
    _exchange_cache.clear()
