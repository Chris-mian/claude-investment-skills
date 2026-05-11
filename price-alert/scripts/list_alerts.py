#!/usr/bin/env python3
"""
list_alerts.py — Pretty-print all alerts (active + fired).

Usage:
  python list_alerts.py                # all
  python list_alerts.py --active       # only active+unfired
  python list_alerts.py --fired        # only fired
  python list_alerts.py --json         # raw JSON
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ALERTS_JSON = SCRIPT_DIR.parent / "alerts.json"


def fmt_condition(c: dict) -> str:
    op = c["op"]
    if op == "below":   return f"≤ ${c['threshold']:.2f}"
    if op == "above":   return f"≥ ${c['threshold']:.2f}"
    if op == "drop_pct":
        target = c["anchor_price"] * (1 - c["pct"]/100)
        return f"-{c['pct']}% from ${c['anchor_price']:.2f} (≤ ${target:.2f})"
    if op == "rise_pct":
        target = c["anchor_price"] * (1 + c["pct"]/100)
        return f"+{c['pct']}% from ${c['anchor_price']:.2f} (≥ ${target:.2f})"
    if op == "drop_intraday":
        return f"single-day -{c['pct']}% vs prev close (incl. AH)"
    if op == "rise_intraday":
        return f"single-day +{c['pct']}% vs prev close (incl. AH)"
    return str(c)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--active", action="store_true")
    p.add_argument("--fired",  action="store_true")
    p.add_argument("--json",   action="store_true")
    args = p.parse_args()

    with open(ALERTS_JSON) as f:
        data = json.load(f)
    alerts = data.get("alerts", [])

    if args.active:
        alerts = [a for a in alerts if a.get("active") and not a.get("fired")]
    elif args.fired:
        alerts = [a for a in alerts if a.get("fired")]

    if args.json:
        print(json.dumps(alerts, indent=2))
        return 0

    if not alerts:
        print("No alerts.")
        return 0

    print(f"{'ID':<20} {'Ticker':<8} {'Status':<10} {'Condition':<40} {'Created':<12} {'Note'}")
    print("─" * 110)
    for a in alerts:
        status = "🔥 FIRED" if a.get("fired") else ("✓ active" if a.get("active") else "⏸ paused")
        print(
            f"{a['id']:<20} {a['ticker']:<8} {status:<10} "
            f"{fmt_condition(a['condition']):<40} "
            f"{a.get('created','?'):<12} {a.get('note','')[:30]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
