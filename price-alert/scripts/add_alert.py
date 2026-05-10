#!/usr/bin/env python3
"""
add_alert.py — Add a new price alert to alerts.json.

Usage:
  python add_alert.py TICKER below PRICE [--note "..."]
  python add_alert.py TICKER above PRICE [--note "..."]
  python add_alert.py TICKER drop PCT   [--note "..."]   # drops X% from current
  python add_alert.py TICKER rise PCT   [--note "..."]   # rises X% from current
  python add_alert.py TICKER drop PCT --anchor PRICE     # drops X% from explicit anchor

Examples:
  python add_alert.py GLW below 140 --note "AI glass entry tier 1"
  python add_alert.py NVDA drop 10
  python add_alert.py SMH below 480 --note "Sector pullback target"
"""
import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("ERROR: pip install yfinance", file=sys.stderr)
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
ALERTS_JSON = SCRIPT_DIR.parent / "alerts.json"


def get_current_price(ticker: str) -> float:
    info = yf.Ticker(ticker).fast_info
    price = info.get("last_price") or info.get("lastPrice")
    if price is None:
        full = yf.Ticker(ticker).info
        price = full.get("regularMarketPrice") or full.get("currentPrice")
    if price is None:
        raise ValueError(f"could not fetch price for {ticker}")
    return float(price)


def main() -> int:
    p = argparse.ArgumentParser(description="Add a price alert")
    p.add_argument("ticker", help="Ticker symbol, e.g. GLW")
    p.add_argument("op", choices=["below", "above", "drop", "rise"],
                   help="Trigger condition")
    p.add_argument("value", type=float,
                   help="Price ($) for below/above; percent (10 = 10%%) for drop/rise")
    p.add_argument("--note", default="", help="Free-form note shown in alert")
    p.add_argument("--anchor", type=float,
                   help="Anchor price for drop/rise (default: current price)")
    args = p.parse_args()

    ticker = args.ticker.upper()
    current = get_current_price(ticker)
    print(f"Current {ticker}: ${current:.2f}")

    # Build condition
    if args.op == "below":
        condition = {"op": "below", "threshold": args.value}
        target_str = f"${args.value:.2f} (current ${current:.2f}, {((args.value/current-1)*100):+.1f}%)"
    elif args.op == "above":
        condition = {"op": "above", "threshold": args.value}
        target_str = f"${args.value:.2f} (current ${current:.2f}, {((args.value/current-1)*100):+.1f}%)"
    elif args.op == "drop":
        anchor = args.anchor if args.anchor else current
        condition = {"op": "drop_pct", "pct": args.value, "anchor_price": anchor}
        target_price = anchor * (1 - args.value / 100)
        target_str = f"-{args.value}% from ${anchor:.2f} = trigger at ${target_price:.2f}"
    elif args.op == "rise":
        anchor = args.anchor if args.anchor else current
        condition = {"op": "rise_pct", "pct": args.value, "anchor_price": anchor}
        target_price = anchor * (1 + args.value / 100)
        target_str = f"+{args.value}% from ${anchor:.2f} = trigger at ${target_price:.2f}"

    alert = {
        "id": f"{ticker.lower()}-{args.op}-{uuid.uuid4().hex[:6]}",
        "ticker": ticker,
        "condition": condition,
        "note": args.note,
        "created": str(date.today()),
        "created_price": current,
        "active": True,
        "fired": False,
    }

    # Load + append + save
    with open(ALERTS_JSON) as f:
        data = json.load(f)
    data.setdefault("alerts", []).append(alert)
    with open(ALERTS_JSON, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✓ Alert added: {alert['id']}")
    print(f"  Ticker:   {ticker}")
    print(f"  Trigger:  {target_str}")
    if args.note:
        print(f"  Note:     {args.note}")
    print(f"\nTotal active alerts: {sum(1 for a in data['alerts'] if a.get('active') and not a.get('fired'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
