#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
partner_firehose.py — Real-time SEC 8-K + SC 13D strategic-partner monitor.

实时 SEC 8-K + SC 13D 战略合作伙伴监控.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS DOES / 这个脚本干啥
═══════════════════════════════════════════════════════════════════════

Every cron tick:
  1. Pull EDGAR atom feeds for 8-K and SC 13D (separate URLs)
  2. Dedup against state file (form4_state.json pattern)
  3. For each NEW filing:
     a. Fetch raw filing text (4-Day disclosure rule means body is here)
     b. Parse Items (1.01 / 3.02 / 7.01 / 8.01 keep, else skip)
     c. Scan for strategic-investor names (TIER_1 / TIER_2 / SOVEREIGN)
     d. Extract dollar amount + conversion price + deal type
     e. Filter: ticker must be US-listed, mcap ≥ $50M, amount ≥ $50M
     f. Enrich via insider-firehose/scripts/enrichment/
     g. Compute Strategic Partner Score 0-10
     h. Push Telegram alert with rich markdown

State management:
  Reuses the same Telegram bot + GitHub Secrets as price-alert + insider-firehose.
  状态管理 / Telegram bot 复用 price-alert + insider-firehose.

═══════════════════════════════════════════════════════════════════════
  RATE LIMITING / 速率控制
═══════════════════════════════════════════════════════════════════════

SEC EDGAR: 10 req/sec limit. We sleep 0.15s between requests = 6.7 req/s.
yfinance: cached in filters.py; one call per ticker per cron run.
Telegram: no published rate limit but we send ≤ 30 alerts per run (rare).

═══════════════════════════════════════════════════════════════════════
  ENV VARS / 环境变量
═══════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN    Bot token (shared with insider-firehose)
TELEGRAM_CHAT_ID      Target chat
STRATEGIC_MIN_MCAP    Minimum market cap (default 50_000_000)
STRATEGIC_MIN_AMOUNT_M  Minimum deal amount millions USD (default 50)
EDGAR_USER_AGENT      Required by SEC: "<email> <product>/<version>"
TEST_MODE             "1" prints alerts to stdout instead of Telegram
ENRICH                "0"/"off" disables enrichment (default ON)
DRY_RUN_LIMIT         Optional: cap number of filings processed (for testing)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

# ─── Path setup so sibling skill enrichment works in dev + CI ────────────
# 路径设置 — 让姊妹 skill enrichment 在开发和 CI 都能 import
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Add insider-firehose enrichment to path for cross-skill reuse
_INSIDER_SCRIPTS = (
    SCRIPT_DIR.parent.parent / "insider-firehose" / "scripts"
)
if _INSIDER_SCRIPTS.exists():
    sys.path.insert(0, str(_INSIDER_SCRIPTS))

# ─── Local imports / 本 skill imports ─────────────────────────────────────
from investor_registry import find_strategic_investors, TIER_EMOJI  # noqa: E402
from parsers import (  # noqa: E402
    parse_atom_feed, FilingMeta, PartnerSignal,
    extract_items, extract_max_amount_usd_m, extract_conversion_price,
    extract_ticker, detect_deal_type, is_noise_filing, parse_13d_filer_and_issuer,
    KEY_8K_ITEMS,
)
from filters import apply_all_filters, MIN_MARKET_CAP_USD, MIN_DEAL_AMOUNT_USD_M  # noqa: E402
from analysis import compute_partner_score  # noqa: E402

# ─── Cross-skill enrichment (optional, non-fatal) ───────────────────────
# 跨 skill enrichment (可选, 非致命)
_ENRICH_AVAILABLE = False
try:
    from enrichment.valuation import pull_valuation  # type: ignore  # noqa: E402
    from enrichment.price_action import pull_price_action  # type: ignore  # noqa: E402
    from enrichment.company_info import pull_company_info  # type: ignore  # noqa: E402
    from enrichment import is_enabled as enrichment_enabled  # type: ignore  # noqa: E402
    _ENRICH_AVAILABLE = True
except ImportError as _imp_err:
    print(f"[INFO] enrichment unavailable: {_imp_err}", file=sys.stderr)

    def enrichment_enabled() -> bool:  # type: ignore
        return False


# ─── Constants / 常量 ────────────────────────────────────────────────────

# SEC EDGAR feeds (URL-encoded form type because some types have spaces)
# SEC EDGAR feed (form type 含空格的要 URL 编码)
EDGAR_FEEDS: dict[str, str] = {
    "8-K": (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcurrent&type=8-K&output=atom&count=100"
    ),
    "SC 13D": (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcurrent&type=SC+13D&output=atom&count=40"
    ),
}

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "ssurmiczizhao@gmail.com strategic-partner-firehose/1.0",
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

# Polite throttle: SEC asks ≤ 10 req/sec
# SEC 限速 10 req/sec
HTTP_DELAY = 0.15  # seconds

TEST_MODE = os.environ.get("TEST_MODE", "") == "1"
DRY_RUN_LIMIT = int(os.environ.get("DRY_RUN_LIMIT", "0"))  # 0 = no limit

STATE_FILE = SCRIPT_DIR / "strategic_state.json"


# ─── State helpers / 状态管理 ───────────────────────────────────────────

def load_state() -> dict:
    """Load dedup state. Returns empty default if missing/corrupt."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"seen_accessions": [], "last_run_iso": None}


def save_state(state: dict) -> None:
    """Persist state. Cap seen list at 10000 (~1 month at typical 8-K volume)."""
    accs = state.get("seen_accessions", [])
    if len(accs) > 10000:
        state["seen_accessions"] = accs[-10000:]
    state["last_run_iso"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


# ─── EDGAR fetch helpers / EDGAR 拉取 ────────────────────────────────────

def fetch_atom(url: str) -> str:
    """Pull an EDGAR atom feed, raise on non-200."""
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_filing_text(index_url: str) -> str:
    """
    Fetch the combined text body of a filing.
    拉 filing 的合并文本.

    A filing index page lists documents. We pull:
      1. The primary .htm (cover page + items)
      2. The largest .htm exhibit (usually press release / agreement)
    然后合并以最大化关键词命中.

    Returns empty string on error.
    """
    try:
        r = requests.get(index_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] index fetch failed: {e}", file=sys.stderr)
        return ""

    # Find document hrefs on index page
    # 找文档链接
    candidates = re.findall(r'href="([^"]+\.(?:htm|html))"', r.text)
    if not candidates:
        return ""

    # Exclude index-related links
    docs = [c for c in candidates
            if "index" not in c.lower() and "/xsl" not in c.lower()]
    if not docs:
        return ""

    # Fetch up to 3 docs (primary + 2 largest exhibits) and concat
    # 抓最多 3 个文档 (主 + 最大 2 个附件)
    combined = []
    for doc in docs[:3]:
        url = doc if doc.startswith("http") else "https://www.sec.gov" + doc
        try:
            time.sleep(HTTP_DELAY)
            dr = requests.get(url, headers=HEADERS, timeout=30)
            if dr.ok:
                # Strip HTML tags crudely (we only need text content for regex)
                # 粗暴去 HTML 标签, 我们只需文本做 regex
                stripped = re.sub(r"<[^>]+>", " ", dr.text)
                stripped = re.sub(r"\s+", " ", stripped)
                combined.append(stripped)
        except Exception as e:
            print(f"[WARN] doc fetch failed {doc}: {e}", file=sys.stderr)
            continue

    return "\n".join(combined)


# ─── Core analysis / 核心分析 ──────────────────────────────────────────

def analyze_filing(meta: FilingMeta, body: str) -> PartnerSignal | None:
    """
    Run a filing through the full analysis pipeline.
    跑完整分析流程.

    Returns PartnerSignal if all filters pass; None otherwise.
    通过所有 filter 返回 PartnerSignal, 否则 None.
    """
    if not body:
        return None

    # ─ Step 1: Noise filter (cheapest) ─
    if meta.form_type == "8-K" and is_noise_filing(body):
        return None

    # ─ Step 2: Strategic investor scan ─
    investors = find_strategic_investors(body)
    if not investors:
        return None

    # ─ Step 3: Extract structured data ─
    items = extract_items(body)
    amount_m = extract_max_amount_usd_m(body)
    conv_price = extract_conversion_price(body)
    ticker = extract_ticker(body)
    deal_type = detect_deal_type(body)
    company_name = ""

    # For 13D, also extract issuer name (ticker may be missing)
    # 对 13D, 还要解析 issuer 名字 (ticker 可能没有)
    if meta.form_type.startswith("SC 13"):
        filer, issuer = parse_13d_filer_and_issuer(body)
        if issuer and not company_name:
            company_name = issuer

    # ─ Step 4: 8-K items must be in our key set ─
    if meta.form_type == "8-K":
        if not set(items) & KEY_8K_ITEMS:
            return None

    # ─ Step 5: Hard filters (mcap + US-listed + amount) ─
    if not ticker:
        return None

    passes, reason = apply_all_filters(ticker, amount_m)
    if not passes:
        print(f"[SKIP] {ticker}: {reason}", file=sys.stderr)
        return None

    return PartnerSignal(
        ticker=ticker,
        company_name=company_name,
        form_type=meta.form_type,
        items=items,
        investors=investors,
        amount_usd_m=amount_m,
        conversion_price=conv_price,
        deal_type=deal_type,
        filing_link=meta.link,
        accession=meta.accession,
    )


# ─── Alert formatting / 推送格式化 ──────────────────────────────────────

def format_alert(signal: PartnerSignal, enriched: dict | None = None) -> str:
    """
    Build a Telegram Markdown message.
    构建 Telegram Markdown 消息.

    Enriched data is optional — if missing, we still send a basic alert.
    """
    enriched = enriched or {}
    valuation = enriched.get("valuation") or {}
    price = enriched.get("price") or {}
    company = enriched.get("company") or {}
    score_data = enriched.get("score") or {}

    # Header
    top_tier, top_canonical = signal.investors[0]
    tier_emoji = TIER_EMOJI.get(top_tier, "🤝")

    # Format primary investor name nicely
    top_name = top_canonical.replace("_", " ")

    lines = [
        f"🤝🟢 *STRATEGIC PARTNER INVESTMENT* — ${signal.amount_usd_m:,.0f}M",
        "",
        f"*Ticker*: `{signal.ticker}`",
        f"{tier_emoji} *{top_name}* ({top_tier})",
    ]

    # Show additional investors if any
    if len(signal.investors) > 1:
        others = [f"{TIER_EMOJI.get(t, '🤝')} {c.replace('_', ' ')}"
                  for t, c in signal.investors[1:]]
        lines.append(f"  + {', '.join(others)}")

    lines.extend([
        f"_Filing: {signal.form_type}"
        + (f", Item {','.join(signal.items)}" if signal.items else "") + "_",
        "",
        f"*Type*: {signal.deal_type}",
    ])

    if signal.conversion_price is not None:
        lines.append(f"*Conversion @*: ${signal.conversion_price:.2f}")

    lines.append(f"\n[SEC EDGAR ›]({signal.filing_link})")

    # Enrichment sections
    if company.get("one_liner"):
        sector = company.get("sector") or ""
        lines.append(f"\n🏢 _{company['one_liner']}_")
        if sector:
            lines[-1] += f" · {sector}"

    if valuation:
        v_lines = ["\n📈 *Valuation*"]
        mcap = valuation.get("market_cap")
        if mcap is not None:
            mcap_str = f"${mcap/1e9:.1f}B" if mcap >= 1e9 else f"${mcap/1e6:.0f}M"
            v_lines.append(f"  Cap: {mcap_str}")
        pe = valuation.get("trailing_pe")
        if pe is not None:
            v_lines.append(f"  P/E: {pe:.1f}")
        if len(v_lines) > 1:
            lines.append("\n".join(v_lines))

    if price:
        p_lines = ["\n📊 *Price*"]
        cur = price.get("current")
        if cur is not None:
            p_lines.append(f"  Now: ${cur:.2f}")
        m200 = price.get("pct_vs_200dma")
        if m200 is not None:
            p_lines.append(f"  vs 200DMA: {m200:+.1f}%")
        if len(p_lines) > 1:
            lines.append("\n".join(p_lines))

    if score_data:
        score = score_data.get("score", 0)
        verdict = score_data.get("verdict", "")
        emoji = "🔥🔥🔥" if score >= 9 else "⭐⭐⭐" if score >= 7 else (
            "⭐⭐" if score >= 5 else "⭐" if score >= 3 else "▫️")
        lines.append(f"\n{emoji} *Partner Score: {score}/10*")
        if verdict:
            lines.append(f"  _{verdict}_")
        for f in (score_data.get("factors") or [])[:5]:
            lines.append(f"  {f}")

    return "\n".join(lines)


# ─── Telegram delivery / Telegram 推送 ──────────────────────────────────

def send_telegram(msg: str) -> bool:
    """Send to Telegram; respect TEST_MODE."""
    if TEST_MODE:
        print("─── TEST_MODE: would send ───", file=sys.stderr)
        print(msg, file=sys.stderr)
        print("─── end ───", file=sys.stderr)
        return True

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(f"[WARN] No Telegram creds; message NOT sent:\n{msg}", file=sys.stderr)
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if r.ok:
            return True
        print(f"[ERROR] Telegram {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Telegram exception: {e}", file=sys.stderr)
        return False


# ─── Main / 主入口 ───────────────────────────────────────────────────────

def main() -> int:
    state = load_state()
    seen = set(state.get("seen_accessions", []))

    enrich_status = (
        "ON" if (_ENRICH_AVAILABLE and enrichment_enabled())
        else "DISABLED" if _ENRICH_AVAILABLE else "UNAVAILABLE"
    )
    print(
        f"[INFO] Partner firehose starting (mcap≥${MIN_MARKET_CAP_USD/1e6:.0f}M, "
        f"amount≥${MIN_DEAL_AMOUNT_USD_M:.0f}M, enrich={enrich_status})",
        file=sys.stderr,
    )

    total_filings = 0
    total_processed = 0
    total_alerts = 0
    total_skip_seen = 0
    total_skip_filtered = 0

    for form_type, url in EDGAR_FEEDS.items():
        try:
            xml = fetch_atom(url)
            filings = parse_atom_feed(xml)
        except Exception as e:
            print(f"[ERROR] {form_type} feed: {e}", file=sys.stderr)
            continue

        print(f"[INFO] {form_type}: {len(filings)} filings in feed", file=sys.stderr)
        total_filings += len(filings)

        for meta in filings:
            if meta.accession in seen:
                total_skip_seen += 1
                continue
            seen.add(meta.accession)

            if DRY_RUN_LIMIT and total_processed >= DRY_RUN_LIMIT:
                print(f"[INFO] DRY_RUN_LIMIT={DRY_RUN_LIMIT} reached",
                      file=sys.stderr)
                break

            try:
                time.sleep(HTTP_DELAY)
                body = fetch_filing_text(meta.link)
                total_processed += 1
            except Exception as e:
                print(f"[WARN] body fetch failed {meta.accession}: {e}",
                      file=sys.stderr)
                continue

            try:
                signal = analyze_filing(meta, body)
            except Exception as e:
                print(f"[WARN] analysis failed {meta.accession}: {e}",
                      file=sys.stderr)
                continue

            if signal is None:
                total_skip_filtered += 1
                continue

            # Enrich + score
            enriched: dict = {}
            if _ENRICH_AVAILABLE and enrichment_enabled():
                try:
                    valuation = pull_valuation(signal.ticker)  # type: ignore
                    price = pull_price_action(signal.ticker)  # type: ignore
                    company = pull_company_info(signal.ticker, valuation)  # type: ignore
                    score = compute_partner_score(
                        signal={
                            "investors": signal.investors,
                            "amount_usd_m": signal.amount_usd_m,
                            "deal_type": signal.deal_type,
                            "conversion_price": signal.conversion_price,
                            "form_type": signal.form_type,
                        },
                        valuation=valuation,
                        price=price,
                    )
                    enriched = {
                        "valuation": valuation,
                        "price": price,
                        "company": company,
                        "score": score,
                    }
                except Exception as e:
                    print(f"[WARN] enrichment failed {signal.ticker}: {e}",
                          file=sys.stderr)

            msg = format_alert(signal, enriched)
            if send_telegram(msg):
                total_alerts += 1
                print(
                    f"[ALERT] {signal.ticker:6s}  ${signal.amount_usd_m:>7,.0f}M  "
                    f"{signal.investors[0][1]:25s}  {signal.form_type}",
                    file=sys.stderr,
                )

    # Persist state
    state["seen_accessions"] = list(seen)
    save_state(state)

    print(
        f"[DONE] feeds={total_filings} processed={total_processed} "
        f"alerts={total_alerts} skip_seen={total_skip_seen} "
        f"skip_filtered={total_skip_filtered}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
