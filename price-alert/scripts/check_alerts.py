#!/usr/bin/env python3
"""
check_alerts.py — Core alert checker. Run by GitHub Actions cron.

Reads alerts.json, evaluates each active+unfired alert against live yfinance
price, fires a Telegram notification if triggered, and writes back the
updated alerts.json (fired=true) plus an append-only fired.log.

Idempotent: re-running won't re-fire the same alert. To re-arm a fired
alert, run cancel_alert.py + add_alert.py again, or set fired=false manually.

ENV:
  TELEGRAM_BOT_TOKEN   required for notifications
  TELEGRAM_CHAT_ID     required for notifications
  ALERTS_JSON_PATH     optional override (default: ../alerts.json relative to script)

Exit codes:
  0  ran successfully (any number of alerts may have fired)
  1  config error
  2  network/data error (some alerts skipped)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yfinance as yf
    import requests
except ImportError:
    print("ERROR: pip install yfinance requests", file=sys.stderr)
    sys.exit(1)


# ─── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR  = SCRIPT_DIR.parent
ALERTS_JSON = Path(os.environ.get("ALERTS_JSON_PATH", SKILL_DIR / "alerts.json"))
FIRED_LOG   = SKILL_DIR / "alerts_fired.log"


# ─── .env loader (zero-dependency, only for local runs) ──────────────────
# GitHub Actions injects secrets via repo Settings, not via .env.
# For local testing, we read price-alert/.env if it exists.
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value and value != f"PASTE_YOUR_{key.split('_', 1)[-1]}_HERE":
                # Don't overwrite real env vars (CI), but do fill missing ones (local)
                os.environ.setdefault(key, value)


_load_dotenv(SKILL_DIR / ".env")


# ─── Telegram ───────────────────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(f"WARN: no Telegram creds, would have sent:\n{message}", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=10)
    if r.status_code != 200:
        print(f"ERROR: Telegram returned {r.status_code}: {r.text}", file=sys.stderr)
        return False
    return True


# ─── Price fetch ────────────────────────────────────────────────────────
def get_price(ticker: str) -> float | None:
    try:
        info = yf.Ticker(ticker).fast_info
        price = info.get("last_price") or info.get("lastPrice")
        if price is None:
            # fallback to full info
            full = yf.Ticker(ticker).info
            price = full.get("regularMarketPrice") or full.get("currentPrice")
        return float(price) if price is not None else None
    except Exception as e:
        print(f"WARN: price fetch failed for {ticker}: {e}", file=sys.stderr)
        return None


# ─── Condition evaluator ────────────────────────────────────────────────
def evaluate(alert: dict, current_price: float) -> tuple[bool, str]:
    """Return (triggered, human_reason)."""
    cond = alert["condition"]
    op = cond["op"]               # "below" | "above" | "drop_pct" | "rise_pct"
    threshold = cond.get("threshold")
    pct = cond.get("pct")
    anchor = cond.get("anchor_price")

    if op == "below":
        if current_price <= threshold:
            return True, f"${current_price:.2f} ≤ ${threshold:.2f}"
    elif op == "above":
        if current_price >= threshold:
            return True, f"${current_price:.2f} ≥ ${threshold:.2f}"
    elif op == "drop_pct":
        if anchor is None or pct is None:
            return False, "missing anchor/pct"
        target = anchor * (1 - pct / 100)
        if current_price <= target:
            actual_drop = (1 - current_price / anchor) * 100
            return True, f"dropped {actual_drop:.1f}% from ${anchor:.2f} (threshold: -{pct}%)"
    elif op == "rise_pct":
        if anchor is None or pct is None:
            return False, "missing anchor/pct"
        target = anchor * (1 + pct / 100)
        if current_price >= target:
            actual_rise = (current_price / anchor - 1) * 100
            return True, f"rose {actual_rise:.1f}% from ${anchor:.2f} (threshold: +{pct}%)"
    elif op == "drop_intraday":
        # Triggers if current price (incl. pre-market / after-hours) is X%
        # below the most recent regular-session close. Re-evaluates each
        # poll so the reference price advances daily.
        prev_close = cond.get("prev_close_at_check")
        if prev_close is None or prev_close <= 0:
            return False, "no prev close available"
        actual_drop = (1 - current_price / prev_close) * 100
        if actual_drop >= pct:
            return True, f"intraday drop {actual_drop:.1f}% from prev close ${prev_close:.2f} (threshold: -{pct}%)"
    elif op == "rise_intraday":
        prev_close = cond.get("prev_close_at_check")
        if prev_close is None or prev_close <= 0:
            return False, "no prev close available"
        actual_rise = (current_price / prev_close - 1) * 100
        if actual_rise >= pct:
            return True, f"intraday rise {actual_rise:.1f}% from prev close ${prev_close:.2f} (threshold: +{pct}%)"
    else:
        return False, f"unknown op: {op}"

    return False, ""


# ─── Format Telegram message ────────────────────────────────────────────
def format_message(alert: dict, current_price: float, reason: str, info: dict) -> str:
    ticker = alert["ticker"]
    direction = "🔻" if alert["condition"]["op"] in ("below", "drop_pct") else "🔺"
    note = alert.get("note", "")
    fifty_two_low = info.get("fifty_two_week_low")
    fifty_two_high = info.get("fifty_two_week_high")
    pct_off_high = ((current_price / fifty_two_high) - 1) * 100 if fifty_two_high else None

    lines = [
        f"{direction} *PRICE ALERT: {ticker}*",
        "",
        f"*Current*: ${current_price:.2f}",
        f"*Trigger*: {reason}",
    ]
    if pct_off_high is not None:
        lines.append(f"*52W high*: ${fifty_two_high:.2f}  ({pct_off_high:+.1f}% off)")
    if fifty_two_low:
        lines.append(f"*52W low*: ${fifty_two_low:.2f}")
    if note:
        lines.append("")
        lines.append(f"_Note: {note}_")
    lines.append("")
    lines.append(f"_Alert id: `{alert['id']}`_")
    lines.append(f"_Set: {alert.get('created', '?')}_")

    return "\n".join(lines)


# ─── Append-only fired log ──────────────────────────────────────────────
def log_fired(alert: dict, current_price: float, reason: str):
    record = {
        "fired_at_utc": datetime.now(timezone.utc).isoformat(),
        "alert_id": alert["id"],
        "ticker": alert["ticker"],
        "current_price": current_price,
        "reason": reason,
    }
    with open(FIRED_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


# ─── Main ───────────────────────────────────────────────────────────────
def main() -> int:
    if not ALERTS_JSON.exists():
        print(f"ERROR: {ALERTS_JSON} not found", file=sys.stderr)
        return 1

    with open(ALERTS_JSON) as f:
        data = json.load(f)

    alerts = data.get("alerts", [])
    n_active = sum(1 for a in alerts if a.get("active") and not a.get("fired"))
    print(f"Checking {n_active} active alerts at {datetime.now(timezone.utc).isoformat()}")

    n_fired = 0
    n_skipped = 0
    changed = False

    for alert in alerts:
        if not alert.get("active") or alert.get("fired"):
            continue

        ticker = alert["ticker"]
        price = get_price(ticker)
        if price is None:
            print(f"  SKIP {ticker}: price fetch failed")
            n_skipped += 1
            continue

        # For intraday conditions, also fetch yesterday's close so evaluate()
        # has the reference. Cheap — done once per alert.
        if alert["condition"]["op"] in ("drop_intraday", "rise_intraday"):
            try:
                info = yf.Ticker(ticker).info
                alert["condition"]["prev_close_at_check"] = info.get("regularMarketPreviousClose") or info.get("previousClose")
            except Exception:
                alert["condition"]["prev_close_at_check"] = None

        triggered, reason = evaluate(alert, price)
        if not triggered:
            print(f"  ✓ {ticker} ${price:.2f} — not triggered")
            continue

        # Triggered — fetch enrichment info for the message
        try:
            info = yf.Ticker(ticker).info
        except Exception:
            info = {}

        msg = format_message(alert, price, reason, info)
        sent = send_telegram(msg)
        log_fired(alert, price, reason)

        alert["fired"] = True
        alert["fired_at_utc"] = datetime.now(timezone.utc).isoformat()
        alert["fired_at_price"] = price
        alert["fired_reason"] = reason
        changed = True
        n_fired += 1
        print(f"  🚨 FIRED {ticker} ${price:.2f} — {reason} {'(sent)' if sent else '(NOT sent)'}")
        time.sleep(1)  # gentle to telegram API

    if changed:
        with open(ALERTS_JSON, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Updated {ALERTS_JSON}")

    print(f"Summary: {n_fired} fired, {n_skipped} skipped, {n_active - n_fired - n_skipped} not triggered")
    return 2 if n_skipped > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
