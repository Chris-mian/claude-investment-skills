#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semi_insider_screener.py — Semiconductor insider-BUY screener with a
"too-late" filter.

半导体内部人抄底筛选器 + "已翻倍则跳过"过滤.

═══════════════════════════════════════════════════════════════════════
  THE IDEA (from the VSH example) / 思路
═══════════════════════════════════════════════════════════════════════

VSH had a 100%-buy insider cluster at $18.72 (Feb 2026) → now ~$50 (+170%).
Great signal, but ALREADY DOUBLED = too late to chase. We want the NEXT VSH:
a semiconductor name where insiders are BUYING (open-market, Form-4 code P)
that has NOT already doubled.

  1. Pull recent open-market insider PURCHASES from openinsider (code P only).
  2. Keep only tickers in our SEMICONDUCTOR universe (universe.json).
  3. Pull 3-month price + current; compute run-since-buy and 3-mo return.
  4. FLAG candidates that have NOT doubled (skip the already-doubled ones).
  5. Annotate each with segment / CPU-relation / chokepoint (卡脖子) from the
     universe, and push a Telegram alert.

Universe: universe.json (default = public semi list; private repo holds the
authoritative copy). Dedup via screener_state.json (ticker|tradedate).

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TEST_MODE, UNIVERSE (path),
     MIN_BUY_USD (default 50000), DOUBLED_PCT (default 100 = skip if +100%),
     MAX_RUN_PCT (default 80 = only alert if run-since-buy <= this)
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import urllib.request
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.environ.get("UNIVERSE", os.path.join(SCRIPT_DIR, "universe.json"))
STATE_FILE = os.path.join(SCRIPT_DIR, "screener_state.json")

# openinsider recent open-market purchases >= $25k (code P), market-wide.
OI_URL = "http://openinsider.com/latest-insider-purchases-25k"
HEADERS = {"User-Agent": "ssurmiczizhao@gmail.com semi-insider-screener/1.0",
           "Accept": "text/html"}

MIN_BUY_USD = float(os.environ.get("MIN_BUY_USD", "50000"))
DOUBLED_PCT = float(os.environ.get("DOUBLED_PCT", "100"))   # skip if already +100%
MAX_RUN_PCT = float(os.environ.get("MAX_RUN_PCT", "80"))    # only alert if run<=80%
TEST_MODE = os.environ.get("TEST_MODE", "") == "1"



# ── Centralized Telegram fan-out (DM + Channel) ───────────────────────
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))))
import _tg
# ──────────────────────────────────────────────────────────────────────

def load_universe() -> dict:
    d = json.load(open(UNIVERSE_FILE))
    rows = d.get("tickers", d) if isinstance(d, dict) else d
    return {r["ticker"].upper(): r for r in rows}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def fetch_purchases(retries=3) -> list[dict]:
    """Parse openinsider purchases tinytable → list of buy dicts."""
    html = ""
    for i in range(retries):
        try:
            req = urllib.request.Request(OI_URL, headers=HEADERS)
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
            break
        except Exception as e:
            print(f"[WARN] openinsider fetch {i}: {e}", file=sys.stderr)
            time.sleep(3)
    m = re.search(r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>', html, re.DOTALL | re.I)
    if not m:
        return []
    body = re.search(r"<tbody>(.*?)</tbody>", m.group(1), re.DOTALL | re.I)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", (body.group(1) if body else m.group(1)),
                      re.DOTALL | re.I)
    out = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.I)
        if len(cells) < 12:
            continue
        tkm = re.search(r'href="/([A-Za-z.]+)"', cells[3])
        ticker = tkm.group(1).upper() if tkm else ""
        c = [_clean(x) for x in cells]
        if not ticker:
            continue
        # purchases page cols: 1 FilingDate 2 TradeDate 3 Ticker 4 Company
        #   5 Insider 6 Title 7 TradeType 8 Price 9 Qty 10 Owned 11 dOwn 12 Value
        try:
            tdate = c[2][:10]
            price = float(re.sub(r"[^0-9.]", "", c[8]) or 0)
            value = abs(float(re.sub(r"[^0-9.]", "", c[12]) or 0))
            title = c[6]
        except Exception:
            continue
        if "P" not in c[7]:  # code P = open-market purchase
            continue
        out.append({"ticker": ticker, "tdate": tdate, "price": price,
                    "value": value, "title": title, "insider": c[5]})
    return out


def price_now_and_3mo(ticker: str):
    """Return (current, price_3mo_ago, pct_52w_below) via yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        h = t.history(period="3mo")
        if h is None or len(h) < 2:
            return None
        cur = float(h["Close"].iloc[-1])
        old = float(h["Close"].iloc[0])
        fi = t.fast_info or {}
        hi = fi.get("year_high")
        below = ((hi - cur) / hi * 100) if hi else None
        return cur, old, below
    except Exception as e:
        print(f"[WARN] price {ticker}: {e}", file=sys.stderr)
        return None


def send_telegram(msg, *args, **kwargs) -> bool:
    """Delegates to _tg.send so every alert fans out to BOTH the
    @DuckyduckyTradeBot DM (TELEGRAM_CHAT_ID) and the duckyduckyChannel
    (TELEGRAM_CHAT_ID_CHANNEL).  Same bot, two routes."""
    tm = globals().get("TEST_MODE", False)
    if isinstance(tm, str):
        tm = tm == "1"
    return _tg.send(msg, test_mode=bool(tm))


def fmt(b: dict, u: dict, cur: float, run_since: float, below) -> str:
    choke = _CHOKE.get(u["chokepoint"], u["chokepoint"])
    bl = f" · {below:.0f}% below 52wH" if below is not None else ""
    return "\n".join([
        f"🟢🔬 *SEMI INSIDER BUY — {b['ticker']}* (still has room)",
        f"_{u['name']} · {u['segment']}_",
        f"💰 insider bought ~${b['value']:,.0f} @ ${b['price']:.2f} ({b['tdate']}) · {b['title']}",
        f"📊 now ${cur:.2f} ({run_since:+.0f}% since buy){bl}",
        f"🔗 chokepoint(卡脖子): {choke} · CPU-relation: {u['cpu_relation']}",
        f"_{u['note']}_",
        f"openinsider.com/{b['ticker']}",
    ])


def main() -> int:
    uni = load_universe()
    print(f"[INFO] universe: {len(uni)} semi tickers", file=sys.stderr)
    buys = fetch_purchases()
    print(f"[INFO] openinsider: {len(buys)} recent purchases", file=sys.stderr)
    # keep semi-universe + above min value
    semi = [b for b in buys if b["ticker"] in uni and b["value"] >= MIN_BUY_USD]
    print(f"[INFO] {len(semi)} purchases in semi universe (>= ${MIN_BUY_USD:,.0f})",
          file=sys.stderr)

    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {"seen": []}
    seen = set(state.get("seen", []))
    alerts, skipped_doubled = 0, 0

    for b in sorted(semi, key=lambda x: x["value"], reverse=True):
        key = f"{b['ticker']}|{b['tdate']}"
        pn = price_now_and_3mo(b["ticker"])
        if not pn:
            continue
        cur, old3, below = pn
        run_since = (cur - b["price"]) / b["price"] * 100 if b["price"] else 0
        ret3 = (cur - old3) / old3 * 100 if old3 else 0
        # "too late" filter: already doubled since the buy OR in 3 months
        if run_since >= DOUBLED_PCT or ret3 >= DOUBLED_PCT:
            skipped_doubled += 1
            print(f"[SKIP-doubled] {b['ticker']} run {run_since:+.0f}% / 3mo {ret3:+.0f}%",
                  file=sys.stderr)
            seen.add(key)
            continue
        if run_since > MAX_RUN_PCT:
            print(f"[SKIP-ran] {b['ticker']} run {run_since:+.0f}% > {MAX_RUN_PCT}%",
                  file=sys.stderr)
            seen.add(key)
            continue
        u = uni[b["ticker"]]
        line = (f"[CANDIDATE] {b['ticker']:5s} ${b['value']:>10,.0f} @ ${b['price']:.2f} "
                f"-> ${cur:.2f} ({run_since:+.0f}%) | {u['chokepoint']:7s} | {u['segment']}")
        print(line, file=sys.stderr)
        if key not in seen:
            if send_telegram(fmt(b, u, cur, run_since, below)):
                alerts += 1
                time.sleep(0.5)
            seen.add(key)

    if not TEST_MODE:
        state["seen"] = sorted(seen)[-5000:]
        state["updated"] = datetime.now(timezone.utc).isoformat()
        json.dump(state, open(STATE_FILE, "w"), indent=2)
    print(f"[DONE] semi-buys={len(semi)} alerts={alerts} skipped_doubled={skipped_doubled}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
