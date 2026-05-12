"""format.py — render the enriched Telegram message.

Builds on the v2.0 basic alert by appending sections:
  - 🏢 one-line business description + sector
  - 📈 valuation block (P/E, market cap, net cash, dividend)
  - 📊 price action (current, 52W range, MA distances)
  - ⭐ Smart Money Score + factor list

All sections gracefully skipped if their data is missing — partial enrichment
is better than no enrichment.

Output is Telegram Markdown (parse_mode=Markdown). Keep <4096 chars; usually
under 1500 even with all sections present.
"""
from __future__ import annotations


def _fmt_money(v: float | int | None, currency: str = "USD") -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e9:
        return f"{sign}${av/1e9:.1f}B"
    if av >= 1e6:
        return f"{sign}${av/1e6:.0f}M"
    if av >= 1e3:
        return f"{sign}${av/1e3:.0f}K"
    return f"{sign}${av:.0f}"


def _fmt_pct(v: float | None, plus: bool = False) -> str:
    if v is None:
        return "—"
    fmt = f"{v:+.1f}%" if plus else f"{v:.1f}%"
    return fmt


def _fmt_pe(v: float | None) -> str:
    if v is None:
        return "—"
    if v < 0:
        return "n/a (loss)"
    if v > 999:
        return ">999"
    return f"{v:.1f}"


def _score_emoji(score: int) -> str:
    if score >= 9:
        return "🔥🔥🔥"
    if score >= 7:
        return "⭐⭐⭐"
    if score >= 5:
        return "⭐⭐"
    if score >= 3:
        return "⭐"
    return "▫️"


def render_enriched(basic_msg: str, enriched: dict) -> str:
    """Take the v2.0 basic alert text and append enrichment sections.

    `enriched` keys: company, valuation, price, score (any may be missing).
    Returns the basic message unmodified if enriched is empty.
    """
    if not enriched:
        return basic_msg

    company = enriched.get("company") or {}
    valuation = enriched.get("valuation") or {}
    price = enriched.get("price") or {}
    score_block = enriched.get("score") or {}

    sections = [basic_msg]

    # 🏢 business one-liner
    if company.get("one_liner"):
        sector = company.get("sector") or ""
        industry = company.get("industry") or ""
        ctx = f" · {sector}" if sector else ""
        if industry and industry != sector:
            ctx += f" / {industry}"
        sections.append(f"\n🏢 _{company['one_liner']}_{ctx}")

    # 📈 valuation
    if valuation:
        v_lines = ["\n📈 *Valuation*"]
        mcap = valuation.get("market_cap")
        if mcap is not None:
            v_lines.append(f"  Cap: {_fmt_money(mcap)}")
        pe = valuation.get("trailing_pe")
        fwd = valuation.get("forward_pe")
        if pe is not None or fwd is not None:
            v_lines.append(f"  P/E: {_fmt_pe(pe)} (fwd {_fmt_pe(fwd)})")
        net = valuation.get("net_cash")
        net_pct = valuation.get("net_cash_pct_mcap")
        if net is not None:
            tag = f" ({net_pct:.0f}% of cap)" if net_pct is not None else ""
            v_lines.append(f"  Net cash: {_fmt_money(net)}{tag}")
        div = valuation.get("dividend_yield")
        if div is not None and div > 0:
            div_pct = div if div >= 1 else div * 100
            v_lines.append(f"  Div yield: {div_pct:.2f}%")
        rev_g = valuation.get("revenue_growth")
        if rev_g is not None:
            v_lines.append(f"  Rev growth: {rev_g*100:+.1f}% YoY")
        if len(v_lines) > 1:
            sections.append("\n".join(v_lines))

    # 📊 price
    if price:
        p_lines = ["\n📊 *Price*"]
        cur = price.get("current")
        if cur is not None:
            p_lines.append(f"  Now: ${cur:.2f}")
        ch = price.get("change_1y_pct")
        if ch is not None:
            # yfinance returns 1y as fraction (0.32 = +32%) for most tickers
            ch_pct = ch if abs(ch) > 1 else ch * 100
            p_lines.append(f"  1Y: {ch_pct:+.1f}%")
        h = price.get("pct_vs_52w_high")
        l = price.get("pct_vs_52w_low")
        if h is not None and l is not None:
            p_lines.append(f"  52W: {l:+.0f}% from low / {h:+.0f}% from high")
        m50 = price.get("pct_vs_50dma")
        m200 = price.get("pct_vs_200dma")
        if m50 is not None or m200 is not None:
            p_lines.append(
                f"  vs MA: 50d {_fmt_pct(m50, plus=True)} · "
                f"200d {_fmt_pct(m200, plus=True)}"
            )
        if len(p_lines) > 1:
            sections.append("\n".join(p_lines))

    # ⭐ Smart Money Score
    if score_block and score_block.get("score") is not None:
        score = score_block["score"]
        factors = score_block.get("factors") or []
        s_lines = [f"\n{_score_emoji(score)} *Smart Money Score: {score}/10*"]
        for f in factors[:6]:  # cap to 6 factors to keep msg compact
            s_lines.append(f"  {f}")
        sections.append("\n".join(s_lines))

    return "".join(sections)
