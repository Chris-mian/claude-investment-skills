#!/usr/bin/env python3
"""
cancel_alert.py — Cancel an alert by id, ticker, or all.

Usage:
  python cancel_alert.py glw-below-a3b2c1     # exact id
  python cancel_alert.py GLW                  # by ticker (cancels all matching)
  python cancel_alert.py --all                # cancel everything
  python cancel_alert.py glw-below-a3b2c1 --rearm   # re-activate a fired alert
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ALERTS_JSON = SCRIPT_DIR.parent / "alerts.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target", nargs="?", help="alert id or ticker")
    p.add_argument("--all", action="store_true", help="cancel ALL alerts")
    p.add_argument("--rearm", action="store_true",
                   help="re-arm (set fired=false, active=true) instead of cancel")
    args = p.parse_args()

    with open(ALERTS_JSON) as f:
        data = json.load(f)

    matched = []
    for a in data.get("alerts", []):
        if args.all:
            matched.append(a)
        elif args.target and (a["id"] == args.target or a["ticker"].upper() == args.target.upper()):
            matched.append(a)

    if not matched:
        print(f"No alerts matched '{args.target or '--all'}'")
        return 1

    for a in matched:
        if args.rearm:
            a["active"] = True
            a["fired"] = False
            a.pop("fired_at_utc", None)
            a.pop("fired_at_price", None)
            a.pop("fired_reason", None)
            print(f"  ↻ re-armed {a['id']} ({a['ticker']})")
        else:
            a["active"] = False
            print(f"  ✗ cancelled {a['id']} ({a['ticker']})")

    with open(ALERTS_JSON, "w") as f:
        json.dump(data, f, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
