"""
format_alert.py — Render political trade alerts into Telegram-ready Markdown.

Two alert types:
  Congress PTR  — STOCK Act periodic transaction reports (Senate + House)
  OGE 278-T     — Executive branch PDF disclosures (White House / Cabinet)

Telegram uses MarkdownV2; this module targets the legacy Markdown mode
(single asterisks for bold, single underscores for italic).
"""

from __future__ import annotations
import re
from typing import List

from politician_registry import Politician

# ── Amount formatting ─────────────────────────────────────────────────────────

def _abbrev_amount(amount_str: str) -> str:
    """
    Abbreviate a dollar range string for compact display.

    "$1,000,001 - $5,000,000" → "$1M–$5M"
    "$500,001 - $1,000,000"   → "$500K–$1M"
    "$1,001 - $15,000"        → "$1K–$15K"
    "$25,000,001+"            → "$25M+"
    "Unknown"                 → "?"
    """
    if not amount_str or amount_str in ("Unknown", "?"):
        return "?"

    def _fmt_num(n: int) -> str:
        if n >= 1_000_000:
            v = n / 1_000_000
            return f"${v:g}M"
        if n >= 1_000:
            v = n / 1_000
            return f"${v:g}K"
        return f"${n:,}"

    # Extract all dollar numbers from the string
    nums = [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", amount_str) if x.replace(",", "").isdigit()]
    nums = [n for n in nums if n >= 1_000]

    if not nums:
        return amount_str

    lo, hi = min(nums), max(nums)

    if "+" in amount_str and len(nums) == 1:
        return f"{_fmt_num(hi)}+"
    if lo == hi:
        return _fmt_num(hi)
    return f"{_fmt_num(lo)}–{_fmt_num(hi)}"


def _sort_trades_by_amount(trades: list) -> list:
    """Sort trades descending by amount_max, then amount_min."""
    return sorted(
        trades,
        key=lambda t: (t.get("amount_max", 0), t.get("amount_min", 0)),
        reverse=True,
    )


# ── Emoji helpers ─────────────────────────────────────────────────────────────

PARTY_EMOJI = {"D": "🔵", "R": "🔴", "I": "⚪"}
CHAMBER_LABEL = {"SENATE": "Sen.", "HOUSE": "Rep.", "EXECUTIVE": ""}


def _type_emoji(t_type: str) -> str:
    t = t_type.lower()
    if any(x in t for x in ("purchase", "buy", "p")):
        return "🟢"
    if any(x in t for x in ("sale", "sell", "s")):
        return "🔴"
    return "⚪"


def _trade_row(ticker: str, asset: str, amount_str: str, date: str,
               t_type: str, max_asset_len: int = 28) -> str:
    """Format a single trade line."""
    emoji = _type_emoji(t_type)
    ticker_part = f"`{ticker}`" if ticker else "—"
    asset_short = (asset or "")[:max_asset_len].strip()
    amt = _abbrev_amount(amount_str)
    date_part = f"_{date}_" if date and date != "?" else ""
    return f"  {emoji} {ticker_part}  {asset_short}  *{amt}*  {date_part}"


# ── Congress PTR alert ────────────────────────────────────────────────────────

def render_congress_alert(
    politician: Politician,
    trades: List[dict],
    filing_url: str,
) -> str:
    """
    Render a Telegram alert for new Congress STOCK Act PTR trades.

    Example output (see SKILL.md for full rendered preview):
        🏛 STOCK Act PTR  ⚡ NEW FILING

        👤 *Rep. Nancy Pelosi*  🔵 `D-CA`
        🎯 U.S. House of Representatives · Minority Leader
        🗓 Filed: 2026-05-13  |  3 transactions

        🟢 AAPL    Apple Inc - Common Stock   *$1K–$15K*  _2026-05-13_
        🟢 NVDA    NVIDIA Corporation          *$1K–$15K*  _2026-05-13_
        🔴 MSFT    Microsoft Corporation       *$15K–$50K* _2026-05-12_

        📎 PTR Filing →  https://...
        _Legendary track record; options activity especially notable_
    """
    party_emoji = PARTY_EMOJI.get(politician.party or "", "⚪")
    chamber_abbr = CHAMBER_LABEL.get(politician.chamber, "")
    name_str = f"{chamber_abbr} {politician.name}".strip()

    # Detect latest filing date
    dates = [t.get("transaction_date") or t.get("filing_date") or "" for t in trades]
    dates = [d for d in dates if d]
    filed_date = max(dates) if dates else "?"

    n_total = len(trades)
    purchases = [t for t in trades if "purchase" in (t.get("transaction_type") or "").lower()
                 or (t.get("transaction_type") or "").upper() == "P"]
    sales = [t for t in trades if "sale" in (t.get("transaction_type") or "").lower()
             or "sell" in (t.get("transaction_type") or "").lower()
             or (t.get("transaction_type") or "").upper() == "S"]

    lines = [
        "🏛 *STOCK Act PTR*  ⚡ NEW FILING",
        "",
        f"👤 *{name_str}*  {party_emoji} `{politician.party}-{politician.state}`",
        f"🎯 {politician.role}",
        f"🗓 Filed: `{filed_date}`  |  *{n_total}* transaction{'s' if n_total != 1 else ''}",
        "",
    ]

    # Purchases (sorted by amount desc)
    if purchases:
        buy_sorted = _sort_trades_by_amount(purchases)
        show = buy_sorted[:6]
        for t in show:
            lines.append(_trade_row(
                t.get("ticker") or "",
                t.get("asset_description") or t.get("asset") or "",
                t.get("amount_range") or "",
                t.get("transaction_date") or t.get("filing_date") or "",
                "purchase",
            ))
        if len(purchases) > 6:
            lines.append(f"  _...+{len(purchases)-6} more buys_")
        lines.append("")

    # Sales (sorted by amount desc)
    if sales:
        sell_sorted = _sort_trades_by_amount(sales)
        show = sell_sorted[:6]
        for t in show:
            lines.append(_trade_row(
                t.get("ticker") or "",
                t.get("asset_description") or t.get("asset") or "",
                t.get("amount_range") or "",
                t.get("transaction_date") or t.get("filing_date") or "",
                "sale",
            ))
        if len(sales) > 6:
            lines.append(f"  _...+{len(sales)-6} more sells_")
        lines.append("")

    lines.append(f"📎 [PTR Filing]({filing_url})")
    if politician.blurb:
        lines.append(f"_{politician.blurb}_")

    return "\n".join(lines)


# ── OGE 278-T alert ───────────────────────────────────────────────────────────

def render_oge_alert(
    politician: Politician,
    trades: List[dict],
    pdf_url: str,
    report_period: str = "",
) -> str:
    """
    Render a Telegram alert for a new OGE Form 278-T filing.

    Example output (see SKILL.md for full rendered preview):
        🏛 *OGE 278-T*  ⚡ NEW FILING

        👤 *Donald J. Trump*  🔴 `R`
        🎯 President of the United States
        🗓 Filed: 2026-05-08  |  Period: Q1 2026  |  2,707 transactions

        🟢 TOP BUYS (2,415 total):
          🟢 `MSFT`   Microsoft Corp           *$5M–$25M*  _3/17/2026_
          🟢 `NOW`    ServiceNow Inc           *$1M–$5M*   _2/10/2026_
          🟢 `NVDA`   Nvidia Corp              *$1M–$5M*   _2/10/2026_
          🟢 `ORCL`   Oracle Corp              *$1M–$5M*   _3/17/2026_
          🟢 `QCOM`   Qualcomm Inc             *$1M–$5M*   _1/12/2026_
          _...+2,410 more buys_

        🔴 TOP SELLS (292 total):
          🔴 `VIG`    Vanguard Div Appreciation *$5M–$25M*  _?_
          🔴 `META`   Meta Platforms            *$5M–$25M*  _?_
          _...+290 more sells_

        📎 OGE 278-T PDF →  https://...
        _3,642 trades in Q1 2026. NVDA/ORCL/HOOD buys; AMZN/META/MSFT sells_
    """
    party_emoji = PARTY_EMOJI.get(politician.party or "", "⚪")

    purchases = [t for t in trades if _type_emoji(t.get("type", "")) == "🟢"]
    sales = [t for t in trades if _type_emoji(t.get("type", "")) == "🔴"]
    n_total = len(trades)

    period_part = f"  |  Period: *{report_period}*" if report_period else ""

    lines = [
        "🏛 *OGE 278-T*  ⚡ NEW FILING",
        "",
        f"👤 *{politician.name}*  {party_emoji} `{politician.party}`",
        f"🎯 {politician.role}",
        f"🗓 Filed: `{report_period or '?'}`  |  *{n_total:,}* total transactions  "
        f"(*{len(purchases):,}* buys / *{len(sales):,}* sells)",
        "",
    ]

    # Top buys by amount_max desc
    if purchases:
        buy_sorted = _sort_trades_by_amount(purchases)
        show = buy_sorted[:6]
        lines.append(f"🟢 *TOP BUYS* ({len(purchases):,} total):")
        for t in show:
            lines.append(_trade_row(
                t.get("ticker") or "",
                t.get("asset") or "",
                t.get("amount_range") or "",
                t.get("date") or "",
                "purchase",
            ))
        if len(purchases) > 6:
            lines.append(f"  _...+{len(purchases)-6:,} more buys_")
        lines.append("")

    # Top sells by amount_max desc
    if sales:
        sell_sorted = _sort_trades_by_amount(sales)
        show = sell_sorted[:5]
        lines.append(f"🔴 *TOP SELLS* ({len(sales):,} total):")
        for t in show:
            lines.append(_trade_row(
                t.get("ticker") or "",
                t.get("asset") or "",
                t.get("amount_range") or "",
                t.get("date") or "",
                "sale",
            ))
        if len(sales) > 5:
            lines.append(f"  _...+{len(sales)-5:,} more sells_")
        lines.append("")

    lines.append(f"📎 [OGE 278-T PDF]({pdf_url})")
    if politician.blurb:
        lines.append(f"_{politician.blurb}_")

    return "\n".join(lines)
