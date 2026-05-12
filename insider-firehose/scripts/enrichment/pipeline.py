"""pipeline.py — enrich() entry point + enable/disable state management.

Enable/disable resolution (highest precedence wins):
  1. ENRICH env var: "0" / "false" / "off" disables; "1" / "true" / "on" enables
  2. enrichment_config.json file at insider-firehose/enrichment_config.json
  3. Default: enabled

Why a file *and* env var: the env var lets GitHub Actions toggle for a single
run (workflow_dispatch input). The file persists user preference across runs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Config file lives at insider-firehose/enrichment_config.json
# (parent of scripts/enrichment/ is scripts/, so up two levels)
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "enrichment_config.json"


def _read_config_file() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _env_override() -> bool | None:
    raw = os.environ.get("ENRICH", "").strip().lower()
    if raw in ("0", "false", "off", "no", "disable"):
        return False
    if raw in ("1", "true", "on", "yes", "enable"):
        return True
    return None


def is_enabled() -> bool:
    """Resolve current enrichment state."""
    env = _env_override()
    if env is not None:
        return env
    cfg = _read_config_file()
    return cfg.get("enabled", True)


def set_enabled(enabled: bool, note: str = "") -> None:
    """Persist enabled flag to enrichment_config.json."""
    payload = {"enabled": bool(enabled)}
    if note:
        payload["note"] = note
    _CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def enrich(ticker: str, filing: dict, total_value: float) -> dict:
    """Return enriched data for a Form 4 alert.

    Returns {} if disabled, ticker missing, or any unexpected failure.
    Partial enrichment OK — individual modules return {} on their own failures.
    """
    if not is_enabled():
        return {}

    if not ticker or len(ticker) > 6:
        # Skip exotic tickers (rare ADRs, units) — yfinance rarely has data
        return {}

    try:
        # Import lazily so the firehose can still run without yfinance installed
        from .valuation import pull_valuation
        from .price_action import pull_price_action
        from .company_info import pull_company_info
        from .score import compute_score
    except ImportError as e:
        print(f"[ENRICH-WARN] enrichment imports failed: {e}", file=sys.stderr)
        return {}

    try:
        valuation = pull_valuation(ticker)
        price = pull_price_action(ticker)
        company = pull_company_info(ticker, valuation)
        score = compute_score(filing, total_value, valuation, price)
        return {
            "valuation": valuation,
            "price": price,
            "company": company,
            "score": score,
        }
    except Exception as e:
        print(f"[ENRICH-WARN] enrich({ticker}) failed: {e}", file=sys.stderr)
        return {}
