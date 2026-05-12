#!/usr/bin/env python3
"""firehose_cli.py — small CLI for toggling enrichment + showing status.

Usage:
  python scripts/firehose_cli.py --status
  python scripts/firehose_cli.py --enrich-on
  python scripts/firehose_cli.py --enrich-off

The script edits enrichment_config.json in the firehose root. Commit the
result so the next GitHub Actions run picks it up.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make enrichment package importable when running this CLI directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from enrichment import is_enabled, set_enabled  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Insider firehose toggle CLI")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--enrich-on", action="store_true",
                   help="Enable Tier-2 enrichment (P/E + score + price action)")
    g.add_argument("--enrich-off", action="store_true",
                   help="Disable enrichment — fall back to basic v2.0 alerts")
    g.add_argument("--status", action="store_true",
                   help="Show current enrichment status (default action)")
    args = ap.parse_args()

    if args.enrich_on:
        set_enabled(True, note="Enabled via firehose_cli.py")
        print("✅ Enrichment ENABLED")
        print("Next alert will include: business one-liner + P/E + 52W context + Smart Money Score")
    elif args.enrich_off:
        set_enabled(False, note="Disabled via firehose_cli.py")
        print("🔕 Enrichment DISABLED")
        print("Falling back to v2.0 basic alerts (ticker + buyer + size only)")
    else:
        state = "ON ✅" if is_enabled() else "OFF 🔕"
        print(f"Enrichment: {state}")
        print("Toggle with --enrich-on / --enrich-off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
