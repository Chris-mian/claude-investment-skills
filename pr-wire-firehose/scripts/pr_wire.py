#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pr_wire.py — Press-release wire poller (the FASTEST signal — beats the 8-K).

新闻稿 wire 轮询器 —— 最快的信号, 经常比 8-K 早几秒到几分钟.

═══════════════════════════════════════════════════════════════════════
  WHY / 为什么
═══════════════════════════════════════════════════════════════════════

A strategic deal usually hits the PR wire (BusinessWire/GlobeNewswire) and
the company's own newsroom the INSTANT it's announced — often seconds before
the matching 8-K is disseminated by EDGAR. For the absolute earliest read on
"NVIDIA invests in X" / "AMD partners with Y" / a hyperscaler order, the
newsroom RSS is the edge.

战略交易通常在 EDGAR 8-K 之前几秒~几分钟就上了 PR wire 和公司 newsroom.
要抢最早的"NVDA 投了谁 / AMD 和谁合作 / hyperscaler 下单", 盯 newsroom RSS.

═══════════════════════════════════════════════════════════════════════
  FEEDS / 数据源
═══════════════════════════════════════════════════════════════════════

  TARGETED  = a specific company's own newsroom (NVDA/AMD). Every new item is
              high-signal → alert on all.
  BROAD     = a wide wire (GlobeNewswire public companies). High volume →
              only alert when title/summary matches the strategic-investor
              registry OR an AI-infrastructure keyword.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TEST_MODE
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "pr_wire_state.json"

# Reuse the strategic-investor registry (cross-skill, like partner_firehose).
# 复用战略投资人 registry.
_PARTNER_SCRIPTS = SCRIPT_DIR.parent.parent / "strategic-partner-firehose" / "scripts"
if _PARTNER_SCRIPTS.exists():
    sys.path.insert(0, str(_PARTNER_SCRIPTS))
try:
    from investor_registry import find_strategic_investors, TIER_EMOJI  # noqa: E402
except ImportError:
    def find_strategic_investors(_):  # type: ignore
        return []
    TIER_EMOJI = {}  # type: ignore

USER_AGENT = os.environ.get(
    "PR_WIRE_USER_AGENT", "ssurmiczizhao@gmail.com pr-wire-firehose/1.0")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
TEST_MODE = os.environ.get("TEST_MODE", "") == "1"

# (source_label, url, mode). mode = "targeted" (alert all) | "broad" (filter)
# 加 feed 就在这里加一行. targeted=全推, broad=匹配才推.
FEEDS: list[tuple[str, str, str]] = [
    ("NVIDIA Newsroom", "https://nvidianews.nvidia.com/releases.xml", "targeted"),
    ("AMD Newsroom", "https://ir.amd.com/news-events/press-releases/rss", "targeted"),
    ("GlobeNewswire (public cos)",
     "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
     "GlobeNewswire%20-%20News%20about%20Public%20Companies", "broad"),
]

# ── Verification gate / 验证闸门 ─────────────────────────────────────────
# Extract a public exchange:ticker from the PR text (e.g. "(NASDAQ: IREN)").
# 从新闻稿里抽取交易所:代码, 用来验证它是个真上市可交易的票.
_RX_TICKER = re.compile(
    r"\(?\s*(?:NASDAQ|NYSE\s*American|NYSE\s*Arca|NYSE|AMEX|CBOE|"
    r"OTCQB|OTCQX|OTC)\s*:\s*([A-Za-z][A-Za-z.\-]{0,5})\s*\)?", re.I)
# Targeted newsrooms map to a known ticker (the PR may not print "(NASDAQ:…)").
_FEED_TICKER = {"NVIDIA Newsroom": "NVDA", "AMD Newsroom": "AMD"}
# Market-cap floor: drops micro-cap "AI" shells (e.g. Global Mofy's $8M raise).
# 市值下限: 滤掉 Global Mofy 那种圈钱小盘壳. 设 0 关闭.
MIN_MCAP = float(os.environ.get("PR_MIN_MCAP", "500000000"))  # $500M default

# Optional: tag names that are in our semiconductor universe (cross-skill).
_SEMI_UNIVERSE: dict = {}



# ── Centralized Telegram fan-out (DM + Channel) ───────────────────────
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))))
import _tg
# ──────────────────────────────────────────────────────────────────────

def _load_semi_universe() -> dict:
    try:
        p = (SCRIPT_DIR.parent.parent / "semiconductor-insider-screener"
             / "scripts" / "universe.json")
        d = json.loads(p.read_text())
        return {r["ticker"].upper(): r for r in d.get("tickers", [])}
    except Exception:
        return {}


def verify_and_enrich(ticker: str) -> dict | None:
    """
    GATE: confirm `ticker` is a real public equity with mcap >= floor; return a
    rule-based quick-read (mcap / price / % below 52w high). None = fails gate.
    闸门: 确认是真上市票且市值过线; 返回规则型快速读数. None = 不通过.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi = t.fast_info

        def _g(*names):
            for n in names:
                v = getattr(fi, n, None)
                if v is None:
                    try:
                        v = fi[n]
                    except Exception:
                        v = None
                if v:
                    return v
            return None

        mcap = _g("market_cap", "marketCap")
        last = _g("last_price", "lastPrice")
        hi = _g("year_high", "yearHigh")
        if not mcap:  # fast_info miss → fall back to .info (slower, reliable)
            try:
                info = t.info or {}
                mcap = info.get("marketCap")
                last = last or info.get("currentPrice") or info.get("regularMarketPrice")
                hi = hi or info.get("fiftyTwoWeekHigh")
            except Exception:
                pass
        if not mcap or mcap < MIN_MCAP:
            return None
        below = ((hi - last) / hi * 100) if (hi and last) else None
        return {"ticker": ticker.upper(), "mcap": float(mcap),
                "price": float(last) if last else None, "below_52wh": below}
    except Exception as e:
        print(f"[WARN] verify {ticker}: {e}", file=sys.stderr)
        return None


# AI-infrastructure keywords for filtering BROAD feeds.
# 宽 feed 用的 AI 基建关键词 — 命中才推, 否则太吵.
_AI_KEYWORDS = re.compile(
    r"\b(artificial intelligence|\bA\.?I\.?\b|data ?center|GPU|accelerat|"
    r"\bHBM\b|advanced packaging|co-?packaged optic|liquid cool|800\s?V|"
    r"1\.6\s?T|hyperscal|neocloud|inference|training cluster|supercomputer|"
    r"silicon photonic|CoWoS|NVLink|InfiniBand|Ethernet fabric|"
    r"foundry|wafer|transformer shortage|switchgear|substation)\b",
    re.IGNORECASE,
)


def load_state() -> set[str]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("seen", []))
        except Exception:
            pass
    return set()


def save_state(seen: set[str]) -> None:
    seen_list = list(seen)
    if len(seen_list) > 5000:
        seen_list = seen_list[-5000:]
    STATE_FILE.write_text(json.dumps(
        {"seen": seen_list, "updated": datetime.now(timezone.utc).isoformat()},
        indent=2) + "\n")


def _txt(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 or Atom into [{id,title,link,summary}, ...]."""
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out

    # RSS 2.0: <channel><item><title/><link/><guid/><description/>
    for item in root.iter("item"):
        title = _txt(item.find("title"))
        link = _txt(item.find("link"))
        guid = _txt(item.find("guid")) or link
        desc = _txt(item.find("description"))
        if title:
            out.append({"id": guid, "title": html.unescape(title),
                        "link": link, "summary": html.unescape(desc)})
    if out:
        return out

    # Atom: <entry><title/><link href/><id/><summary/>
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = _txt(entry.find("a:title", ns))
        id_ = _txt(entry.find("a:id", ns))
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        summary = _txt(entry.find("a:summary", ns)) or _txt(entry.find("a:content", ns))
        if title:
            out.append({"id": id_ or link, "title": html.unescape(title),
                        "link": link, "summary": html.unescape(summary)})
    return out


def send_telegram(msg, *args, **kwargs) -> bool:
    """Delegates to _tg.send so every alert fans out to BOTH the
    @DuckyduckyTradeBot DM (TELEGRAM_CHAT_ID) and the duckyduckyChannel
    (TELEGRAM_CHAT_ID_CHANNEL).  Same bot, two routes."""
    tm = globals().get("TEST_MODE", False)
    if isinstance(tm, str):
        tm = tm == "1"
    return _tg.send(msg, test_mode=bool(tm))


def format_alert(source: str, item: dict, investors: list, enr: dict) -> str:
    lines = []
    if investors:
        tier, canon = investors[0]
        emoji = TIER_EMOJI.get(tier, "📰")
        lines.append(f"{emoji}⚡ *PR WIRE — {canon.replace('_', ' ')}*")
    else:
        lines.append("📰⚡ *PR WIRE — AI INFRA*")
    lines.append(f"_{source}_")
    lines.append("")
    lines.append(f"*{item['title']}*")
    summ = item.get("summary", "")
    if summ:
        summ = re.sub(r"<[^>]+>", "", summ)
        lines.append(summ[:240] + ("…" if len(summ) > 240 else ""))

    # ── Quick read (rule-based, NO LLM) ──
    mc = enr["mcap"]
    mcs = (f"${mc/1e12:.2f}T" if mc >= 1e12 else
           f"${mc/1e9:.1f}B" if mc >= 1e9 else f"${mc/1e6:.0f}M")
    px = f" · ${enr['price']:.2f}" if enr.get("price") else ""
    qr = f"\n📊 `{enr['ticker']}` · {mcs} mcap{px}"
    if enr.get("below_52wh") is not None:
        qr += f" · {enr['below_52wh']:.0f}% below 52wH"
    lines.append(qr)
    # one-line heuristic read
    b = enr.get("below_52wh")
    if b is not None and b < 5:
        lines.append("⚠️ near 52w high — extended, don't chase the spike")
    elif b is not None and b >= 25:
        lines.append("🟢 well off its high — room if the news is real")
    s = enr.get("semi")
    if s:
        lines.append(f"🔬 in semi universe · {s['segment']} · 卡脖子 {s['chokepoint']}")

    if item.get("link"):
        lines.append(f"\n[Read ›]({item['link']})")
    return "\n".join(lines)


def main() -> int:
    global _SEMI_UNIVERSE
    _SEMI_UNIVERSE = _load_semi_universe()
    seen = load_state()
    total_new = 0
    total_alerts = 0
    total_gated = 0

    for source, url, mode in FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            # Pass raw bytes so ElementTree honors the XML encoding declaration
            # (avoids latin-1 mojibake on UTF-8 smart quotes).
            items = parse_feed(r.content)
        except Exception as e:
            print(f"[WARN] feed failed {source}: {e}", file=sys.stderr)
            continue

        print(f"[INFO] {source}: {len(items)} items", file=sys.stderr)
        for item in items:
            uid = f"{source}|{item['id']}"
            if uid in seen:
                continue
            seen.add(uid)
            total_new += 1

            blob = f"{item['title']} {item.get('summary', '')}"
            investors = find_strategic_investors(blob)
            relevant = bool(_AI_KEYWORDS.search(blob))

            if mode == "broad":
                # Wide wire: fire only if a tracked name OR an AI keyword hits.
                if not investors and not relevant:
                    continue
            else:
                # Targeted newsroom (NVDA/AMD): self-name always matches, so gate
                # on AI-infra relevance to drop gaming/events/consumer noise.
                if not relevant:
                    continue

            # ── VERIFICATION GATE: must be a real public, tradeable ticker ──
            # Targeted feeds → known ticker; broad feeds → extract from PR text.
            ticker = _FEED_TICKER.get(source)
            if not ticker:
                m = _RX_TICKER.search(blob)
                ticker = m.group(1).upper() if m else None
            if not ticker:
                total_gated += 1
                print(f"[GATE-drop] no public ticker: {item['title'][:60]}",
                      file=sys.stderr)
                continue
            enr = verify_and_enrich(ticker)
            if not enr:
                total_gated += 1
                print(f"[GATE-drop] {ticker}: not verifiable / mcap < "
                      f"${MIN_MCAP/1e6:.0f}M floor — {item['title'][:50]}",
                      file=sys.stderr)
                continue
            enr["semi"] = _SEMI_UNIVERSE.get(ticker)

            if send_telegram(format_alert(source, item, investors, enr)):
                total_alerts += 1
                print(f"[ALERT] {ticker} {source}: {item['title'][:60]}",
                      file=sys.stderr)
                time.sleep(0.5)

    if not TEST_MODE:
        save_state(seen)
    print(f"[DONE] new={total_new} alerts={total_alerts} gated_out={total_gated}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
