#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
composite.py — Cross-firehose composite signal detector.

跨 firehose 复合信号检测器.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS DOES / 这个模块干啥
═══════════════════════════════════════════════════════════════════════

When the SAME TICKER triggers BOTH firehoses within 30 days, that's a
mega signal — both insider conviction AND external strategic validation.

当**同一个 ticker** 在 30 天内**同时**触发两个 firehose, 那就是 mega 信号:
  - Form 4: 公司高管 / 创始人 在公开市场买自己公司股票
  - 8-K / 13D: 外部 Tier-1 战略投资人 (NVIDIA/SK Telecom/MGX) 投钱

如果两个信号都在, 说明:
  ✅ 内部人在用真金白银表态
  ✅ 外部战略 capital 在 validate the story
  ✅ 双向 conviction — 极其罕见 + 极强 alpha

═══════════════════════════════════════════════════════════════════════
  ALERT LOG SCHEMA / 推送日志结构
═══════════════════════════════════════════════════════════════════════

Each firehose writes to its own JSON log on every alert it fires.
每个 firehose 触发 alert 时写自己的 JSON 日志.

  insider-firehose/scripts/recent_alerts.json:
    [
      {"ticker": "PENG", "ts": "2026-05-12T18:00:00Z",
       "type": "insider", "amount": 974582, "extra": {"role": "Director"}},
      ...
    ]

  strategic-partner-firehose/scripts/recent_alerts.json:
    [
      {"ticker": "PENG", "ts": "2026-05-12T19:00:00Z",
       "type": "partner", "amount": 200000000,
       "extra": {"investor": "SK_Telecom", "tier": "tier_1"}},
      ...
    ]

Pruned to last 90 days on each write.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Paths / 文件路径 ────────────────────────────────────────────────────

# Resolve to the user's claude skills root (works from either firehose)
# 解析到 skills 根目录 (两个 firehose 都能用)
SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent

INSIDER_LOG = SKILLS_ROOT / "insider-firehose" / "scripts" / "recent_alerts.json"
PARTNER_LOG = SKILLS_ROOT / "strategic-partner-firehose" / "scripts" / "recent_alerts.json"
COMPOSITE_LOG = SKILLS_ROOT / "strategic-partner-firehose" / "scripts" / "composite_state.json"

# ─── Config / 配置 ───────────────────────────────────────────────────────

COMPOSITE_WINDOW_DAYS = int(os.environ.get("COMPOSITE_WINDOW_DAYS", "30"))
LOG_RETENTION_DAYS = 90  # Keep 90 days of history per firehose
# 我们保留 90 天历史, composite 窗口 30 天 (默认)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime | None:
    """Parse ISO 8601 timestamp. Returns None on failure."""
    try:
        # Handle both '2026-05-12T18:00:00Z' and '...+00:00' formats
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_log(path: Path) -> list[dict]:
    """Load recent_alerts.json. Returns empty list on missing/corrupt."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "alerts" in data:
            return data["alerts"]
    except Exception:
        pass
    return []


def _save_log(path: Path, alerts: list[dict]) -> None:
    """Write alerts to disk. Atomic via tmp file."""
    # Ensure parent dir exists
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(alerts, indent=2) + "\n")
    tmp.replace(path)


def _prune(alerts: list[dict], days: int) -> list[dict]:
    """Drop alerts older than `days`."""
    cutoff = _now_utc() - timedelta(days=days)
    pruned = []
    for a in alerts:
        ts = _parse_ts(a.get("ts", ""))
        if ts and ts >= cutoff:
            pruned.append(a)
    return pruned


def log_alert(
    firehose_type: str,
    ticker: str,
    amount_usd: float,
    extra: dict | None = None,
) -> None:
    """
    Append an alert to the appropriate firehose log.
    把 alert 记录到对应 firehose 的日志.

    Called by:
      - insider-firehose form4_firehose.py after sending an alert
      - strategic-partner-firehose partner_firehose.py after sending

    Args:
        firehose_type: "insider" or "partner"
        ticker: stock symbol
        amount_usd: USD amount of the alert event
        extra: any extra fields (role, investor name, etc.)
    """
    if firehose_type == "insider":
        path = INSIDER_LOG
    elif firehose_type == "partner":
        path = PARTNER_LOG
    else:
        return

    alerts = _load_log(path)
    alerts.append({
        "ticker": ticker.upper(),
        "ts": _now_utc().isoformat(),
        "type": firehose_type,
        "amount": amount_usd,
        "extra": extra or {},
    })

    # Prune old entries to bound file size
    alerts = _prune(alerts, LOG_RETENTION_DAYS)
    _save_log(path, alerts)


def check_composite(
    ticker: str,
    own_type: str,
    window_days: int = COMPOSITE_WINDOW_DAYS,
) -> dict | None:
    """
    Check if the OTHER firehose recently alerted on the same ticker.
    检查另一个 firehose 是否最近也对同一 ticker 发过 alert.

    Args:
        ticker: stock symbol
        own_type: "insider" or "partner" — which firehose is asking
        window_days: lookback window (default 30 days)

    Returns:
        dict with composite info if match found, else None.
        Example:
            {
                "this_type": "partner",
                "other_type": "insider",
                "other_alerts": [list of insider alerts on same ticker],
                "lag_days": 5,  # days between the two events
            }
    """
    other_type = "insider" if own_type == "partner" else "partner"
    other_path = INSIDER_LOG if other_type == "insider" else PARTNER_LOG

    other_alerts = _load_log(other_path)
    cutoff = _now_utc() - timedelta(days=window_days)

    ticker_upper = ticker.upper()
    matches = []
    for a in other_alerts:
        if a.get("ticker", "").upper() != ticker_upper:
            continue
        ts = _parse_ts(a.get("ts", ""))
        if ts and ts >= cutoff:
            matches.append(a)

    if not matches:
        return None

    # Compute lag from most recent match
    # 计算最近匹配的 lag
    most_recent = max(matches, key=lambda x: _parse_ts(x["ts"]) or _now_utc())
    other_ts = _parse_ts(most_recent["ts"])
    lag_days = None
    if other_ts:
        lag_days = (_now_utc() - other_ts).days

    return {
        "this_type": own_type,
        "other_type": other_type,
        "other_alerts": matches,
        "lag_days": lag_days,
    }


def is_composite_already_sent(ticker: str, window_hours: int = 24) -> bool:
    """
    Returns True if we already sent a composite alert for this ticker recently.
    返回 True 如果我们最近 (24h) 已经发过这个 ticker 的 composite alert.

    Dedup: composite alerts are sticky — once we say "PENG is a mega signal",
    we don't keep saying it every cron tick. Re-arms after 24h or new event.
    去重: 复合 alert 不要每个 cron tick 都重发, 24h 内只发一次.
    """
    if not COMPOSITE_LOG.exists():
        return False
    try:
        state = json.loads(COMPOSITE_LOG.read_text())
        sent = state.get("sent", {})
        ts_str = sent.get(ticker.upper())
        if not ts_str:
            return False
        ts = _parse_ts(ts_str)
        if not ts:
            return False
        return (_now_utc() - ts).total_seconds() < window_hours * 3600
    except Exception:
        return False


def mark_composite_sent(ticker: str) -> None:
    """Record that we sent a composite alert for this ticker."""
    COMPOSITE_LOG.parent.mkdir(parents=True, exist_ok=True)
    state = {"sent": {}}
    if COMPOSITE_LOG.exists():
        try:
            state = json.loads(COMPOSITE_LOG.read_text())
            if not isinstance(state.get("sent"), dict):
                state = {"sent": {}}
        except Exception:
            pass
    state["sent"][ticker.upper()] = _now_utc().isoformat()
    COMPOSITE_LOG.write_text(json.dumps(state, indent=2) + "\n")


def format_composite_alert(
    ticker: str,
    company_name: str,
    composite_info: dict,
    own_alert_summary: str = "",
) -> str:
    """
    Build a MEGA SIGNAL alert message combining both firehoses.
    构建合并两个 firehose 的 MEGA SIGNAL 消息.

    Args:
        ticker: stock symbol
        company_name: company display name
        composite_info: dict from check_composite()
        own_alert_summary: 1-line summary of the alert that just fired

    Returns:
        Markdown-formatted Telegram message string.
    """
    this_type = composite_info["this_type"]
    other_type = composite_info["other_type"]
    other_alerts = composite_info["other_alerts"]
    lag = composite_info.get("lag_days") or 0

    lines = [
        f"🚨🚨🚨 *MEGA SIGNAL — {ticker}* 🚨🚨🚨",
        "",
        f"*Both firehoses fired within {lag} days:*",
        "",
    ]

    # Describe THIS firehose's alert (what just triggered)
    # 描述这次触发的 alert
    if this_type == "partner":
        lines.append(f"  🤝 *Strategic Partner*: just now")
        if own_alert_summary:
            lines.append(f"     _{own_alert_summary}_")
    else:
        lines.append(f"  📊 *Insider Buy*: just now")
        if own_alert_summary:
            lines.append(f"     _{own_alert_summary}_")

    # Describe OTHER firehose's alerts (the prior matches)
    # 描述另一个 firehose 之前的 alert
    for a in other_alerts[:3]:  # cap at 3
        ts = _parse_ts(a.get("ts", ""))
        days_ago = (_now_utc() - ts).days if ts else 0
        amount_str = f"${a.get('amount', 0):,.0f}"
        extra = a.get("extra", {})

        if other_type == "insider":
            role = extra.get("role", "Insider")
            who = extra.get("owner", "")
            lines.append(
                f"  📊 *Insider Buy* {days_ago}d ago: {who or role} bought {amount_str}"
            )
        else:
            inv = extra.get("investor", "").replace("_", " ")
            tier = extra.get("tier", "")
            lines.append(
                f"  🤝 *Strategic Partner* {days_ago}d ago: "
                f"{inv} ({tier}) invested {amount_str}"
            )

    lines.extend([
        "",
        f"_Composite signals are rare (< 1% of firehose alerts) — both",
        f" insider conviction AND external Tier-1 validation aligned._",
    ])

    if company_name:
        lines.insert(2, f"_{company_name}_\n")

    return "\n".join(lines)
