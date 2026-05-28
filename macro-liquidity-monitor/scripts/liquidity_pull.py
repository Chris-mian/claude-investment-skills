#!/usr/bin/env python3
"""
liquidity_pull.py — Direct-API USD liquidity / repo-plumbing puller for the
macro-liquidity-monitor skill.

NO WebSearch, NO LLM scraping. Only requests (stdlib csv/json otherwise).
All data is public and needs no API key:

  - NY Fed Markets API   SOFR (rate + p1/p99 + volume), EFFR, ON RRP, SRF/repo
                         https://markets.newyorkfed.org/api/...   (real-time, ~8am ET prior day)
  - FRED CSV             IORB, RRPONTSYD, WRESBAL, WTREGEN, WALCL
                         https://fred.stlouisfed.org/graph/fredgraph.csv?id=...

It computes the headline plumbing metrics (SOFR-IORB spread, SOFR tail,
RRP buffer, reserves vs LCLoR band, TGA weekly drain/add, net liquidity,
SRF takeup) and a deterministic tightness score → regime:

  🟢 ABUNDANT (loose) · 🟡 AMPLE (normal) · 🟠 TIGHTENING · 🔴 STRESS

Higher score = TIGHTER. The two lenses this serves:
  - "too loose" (Herman Jin's bubble worry): watch for 🟢 + RRP buffer gone.
  - "funding stress" (repo crisis): watch for 🟠/🔴 + SRF takeup spiking.

Usage:
  python liquidity_pull.py                 # human-readable card + JSON tail
  python liquidity_pull.py --json-only      # raw JSON only
  python liquidity_pull.py --telegram       # send Telegram IF regime changed
                                            #   (or SRF stress) vs state.json
  python liquidity_pull.py --telegram --force   # always send (test)
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone, date
from io import StringIO
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requires requests. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

STATE_FILE = Path(__file__).with_name("state.json")
NYFED = "https://markets.newyorkfed.org/api"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TEST_MODE = os.environ.get("TEST_MODE", "") == "1"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}


def http_get(url, browser=True, timeout=25):
    """browser=True adds a Chrome UA; FRED rejects that, so call it browser=False."""
    headers = dict(BROWSER_HEADERS) if browser else {}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def safe(fn, default=None, label=None):
    try:
        return fn()
    except Exception as e:
        if label:
            print(f"WARN: {label} failed: {e}", file=sys.stderr)
        return default


# ─────────────────────────────────────────────────────────────────────────────
# FRED CSV (no API key, default UA only — Chrome UA gets blocked)
# ─────────────────────────────────────────────────────────────────────────────
FRED_SERIES = {
    "IORB":   "IORB",        # Interest on Reserve Balances — the admin ceiling, %
    "RRP":    "RRPONTSYD",   # ON Reverse Repo outstanding, $B (the cash buffer)
    "RESERVES": "WRESBAL",   # Reserve balances at the Fed, $millions, weekly (Wed)
    "TGA":    "WTREGEN",     # Treasury General Account, $millions, weekly
    "WALCL":  "WALCL",       # Fed total assets, $millions, weekly (balance sheet)
}


def pull_fred(series_id):
    raw = http_get(f"{FRED}?id={series_id}&cosd=2025-06-01", browser=False)
    rows = [r for r in csv.reader(StringIO(raw))]
    data = [r for r in rows[1:] if len(r) >= 2 and r[1] not in (".", "")]
    if not data:
        return None
    def num(r):
        return float(r[1])
    last = data[-1]
    prev = data[-2] if len(data) > 1 else None
    week_ago = data[-6] if len(data) > 6 else None   # daily series: ~1wk back
    return {
        "series": series_id,
        "date": last[0],
        "value": num(last),
        "prev": num(prev) if prev else None,
        "prev_date": prev[0] if prev else None,
        "week_ago": num(week_ago) if week_ago else None,
    }


def pull_all_fred():
    return {k: safe(lambda s=v: pull_fred(s), label=f"FRED {v}") for k, v in FRED_SERIES.items()}


# ─────────────────────────────────────────────────────────────────────────────
# NY Fed Markets API — reference rates + repo operations (real-time, no key)
# ─────────────────────────────────────────────────────────────────────────────
def pull_rate(path):
    """secured/sofr or unsecured/effr → latest reading + percentiles + volume."""
    raw = http_get(f"{NYFED}/rates/{path}/last/10.json")
    rates = json.loads(raw).get("refRates", [])
    rates.sort(key=lambda x: x["effectiveDate"], reverse=True)   # most recent first
    if not rates:
        return None
    top = rates[0]
    return {
        "date": top["effectiveDate"],
        "rate": top.get("percentRate"),
        "p1": top.get("percentPercentile1"),
        "p99": top.get("percentPercentile99"),
        "volume_bn": top.get("volumeInBillions"),
        "prev_rate": rates[1].get("percentRate") if len(rates) > 1 else None,
    }


def pull_rrp_ops():
    """ON RRP latest operation: total parked + counterparty count."""
    raw = http_get(f"{NYFED}/rp/reverserepo/all/results/last/5.json")
    ops = json.loads(raw).get("repo", {}).get("operations", [])
    if not ops:
        return None
    ops.sort(key=lambda o: o.get("operationDate", ""), reverse=True)
    top = ops[0]
    return {
        "date": top.get("operationDate"),
        "accepted_bn": (top.get("totalAmtAccepted") or 0) / 1e9,
        "counterparties": top.get("acceptedCpty"),
    }


def pull_srf():
    """Standing Repo Facility takeup — the funding-stress alarm.
    Sum same-day 'Repo' operations (the Fed runs AM + PM SRF ops)."""
    raw = http_get(f"{NYFED}/rp/repo/all/results/last/12.json")
    ops = json.loads(raw).get("repo", {}).get("operations", [])
    ops = [o for o in ops if "repo" in (o.get("operationType", "") or "").lower()]
    if not ops:
        return {"date": None, "accepted_bn": 0.0, "n_ops": 0}
    ops.sort(key=lambda o: o.get("operationDate", ""), reverse=True)
    latest_date = ops[0].get("operationDate")
    same_day = [o for o in ops if o.get("operationDate") == latest_date]
    total = sum((o.get("totalAmtAccepted") or 0) for o in same_day)
    return {"date": latest_date, "accepted_bn": total / 1e9, "n_ops": len(same_day)}


# ─────────────────────────────────────────────────────────────────────────────
# Calendar pressure — month-end / quarter-end repo spikes
# ─────────────────────────────────────────────────────────────────────────────
def calendar_pressure(today=None):
    today = today or date.today()
    y, m = today.year, today.month
    nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
    month_end = date(nm_y, nm_m, 1).toordinal() - 1
    days_to_me = month_end - today.toordinal()
    is_qtr_end = m in (3, 6, 9, 12)
    return {
        "month_end": date.fromordinal(month_end).isoformat(),
        "days_to_month_end": days_to_me,
        "is_quarter_end_month": is_qtr_end,
        "pressure_soon": days_to_me <= 5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scoring — deterministic tightness ladder (higher = tighter)
# ─────────────────────────────────────────────────────────────────────────────
def _band(v, cuts, scores):
    """cuts ascending; return scores[i] for first cut v<=cut, else scores[-1]."""
    if v is None:
        return None
    for c, s in zip(cuts, scores):
        if v <= c:
            return s
    return scores[-1]


def score(d):
    fred, sofr, effr = d["fred"], d["sofr"], d["effr"]
    rrp_ops, srf = d["rrp_ops"], d["srf"]
    L, notes, triggers = {}, [], []

    iorb = (fred.get("IORB") or {}).get("value")
    sofr_rate = (sofr or {}).get("rate")
    sofr_p99 = (sofr or {}).get("p99")
    # RRP level: prefer FRED RRPONTSYD ($B); fall back to NY Fed ops.
    rrp_bn = (fred.get("RRP") or {}).get("value")
    if rrp_bn is None and rrp_ops:
        rrp_bn = rrp_ops.get("accepted_bn")
    reserves_bn = ((fred.get("RESERVES") or {}).get("value") or 0) / 1000.0  # $M→$B
    reserves_prev_bn = ((fred.get("RESERVES") or {}).get("prev") or 0) / 1000.0
    tga_bn = ((fred.get("TGA") or {}).get("value") or 0) / 1000.0
    tga_prev_bn = ((fred.get("TGA") or {}).get("prev") or 0) / 1000.0
    walcl_bn = ((fred.get("WALCL") or {}).get("value") or 0) / 1000.0
    srf_bn = (srf or {}).get("accepted_bn") or 0.0

    # Layer 1 — SOFR-IORB spread (bp), the headline gauge -------------------
    spread = round((sofr_rate - iorb) * 100, 1) if (sofr_rate and iorb) else None
    L["sofr_iorb_spread_bp"] = {
        "value": spread,
        "score": _band(spread, [-10, -3, 2], [0, 1, 2, 3]),
        "read": "below IORB = excess cash; at/above IORB = repo bid (tight)",
    }
    if spread is not None and spread <= -10:
        triggers.append(f"SOFR {spread}bp UNDER IORB — banks awash in cash (too-loose signal)")
    if spread is not None and spread > 5:
        triggers.append(f"SOFR {spread}bp OVER IORB — reserves getting scarce (tightening)")

    # Layer 2 — SOFR 99th-pctl vs IORB (tail stress) ------------------------
    tail = round((sofr_p99 - iorb) * 100, 1) if (sofr_p99 and iorb) else None
    L["sofr_tail_bp"] = {
        "value": tail,
        "score": _band(tail, [5, 15, 25], [0, 1, 2, 3]),
        "read": "p99 well above IORB = some desks paying up even if median calm",
    }

    # Layer 3 — ON RRP buffer remaining ($B) --------------------------------
    L["rrp_buffer_bn"] = {
        "value": round(rrp_bn, 1) if rrp_bn is not None else None,
        # higher RRP = looser, so invert: small RRP → high (tight-fragile) score
        "score": (None if rrp_bn is None else
                  (0 if rrp_bn > 200 else 1 if rrp_bn > 50 else 2 if rrp_bn > 10 else 3)),
        "read": "the shock absorber; near $0 means drains hit reserves directly",
    }
    if rrp_bn is not None and rrp_bn < 10:
        triggers.append(f"ON RRP drained to ${rrp_bn:.0f}B — buffer gone, future drains bite reserves")

    # Layer 4 — Bank reserves vs LCLoR band ($T) ----------------------------
    res_t = reserves_bn / 1000.0
    L["reserves_t"] = {
        "value": round(res_t, 2) if res_t else None,
        "score": (None if not res_t else
                  (0 if res_t > 3.4 else 1 if res_t > 3.1 else 2 if res_t > 2.9 else 3)),
        "read": "Fed est. 'ample but not abundant' (LCLoR) ~$3.0-3.2T",
        "wow_bn": round(reserves_bn - reserves_prev_bn, 1) if reserves_prev_bn else None,
    }
    if res_t and res_t < 2.9:
        triggers.append(f"Reserves ${res_t:.2f}T below LCLoR band — scarcity risk")

    # Layer 5 — TGA weekly change (drain vs add) ----------------------------
    tga_wow = round(tga_bn - tga_prev_bn, 1) if tga_prev_bn else None
    L["tga_wow_bn"] = {
        "value": tga_wow, "level_bn": round(tga_bn, 0) if tga_bn else None,
        # building TGA drains liquidity (tight); falling adds (loose)
        "score": (None if tga_wow is None else
                  (0 if tga_wow < -25 else 1 if tga_wow <= 25 else 2 if tga_wow <= 150 else 3)),
        "read": "Treasury issuance rebuilding TGA drains bank reserves",
    }
    if tga_wow is not None and tga_wow > 150:
        triggers.append(f"TGA built +${tga_wow:.0f}B this week — large reserve drain")

    # Layer 6 — SRF takeup (funding-stress alarm) ---------------------------
    L["srf_takeup_bn"] = {
        "value": round(srf_bn, 2),
        "score": (0 if srf_bn < 1 else 2 if srf_bn < 10 else 3),
        "read": "Standing Repo Facility; <$1B routine, >$10B = real funding stress",
    }
    if srf_bn >= 10:
        triggers.append(f"SRF takeup ${srf_bn:.1f}B — dealers tapping the Fed backstop (STRESS)")
    elif srf_bn >= 1:
        notes.append(f"SRF takeup ${srf_bn:.1f}B (above routine, watch)")

    # ── Liquidity Score 0-100 (higher = more abundant / looser) ─────────────
    # Transparent, additive from a neutral 50. SOFR-IORB is the spine.
    # NOTE: an empty RRP is NOT scored as "tight" here — that cash already moved
    # into the system (loose). RRP-empty is a forward FRAGILITY flag (a trigger),
    # not current tightness, so we deliberately keep it OUT of the score number.
    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    pts = 50.0
    detail = {}
    if spread is not None:                       # spine: SOFR below IORB = loose
        p = clamp(-spread * 2.5, -30, 35); pts += p; detail["spread"] = round(p, 1)
    p = (0 if srf_bn < 1 else -15 if srf_bn < 10 else -35); pts += p; detail["srf"] = p
    if res_t:                                    # reserves vs LCLoR band
        p = (8 if res_t > 3.4 else 4 if res_t > 3.1 else 0 if res_t > 2.9 else -10)
        pts += p; detail["reserves"] = p
    if tga_wow is not None:                       # TGA flow: draining adds liquidity
        p = (5 if tga_wow < -25 else 0 if tga_wow <= 25 else -5 if tga_wow <= 150 else -10)
        pts += p; detail["tga_flow"] = p
    if tail is not None:                          # SOFR tail paying up = stress
        p = (0 if tail < 10 else -3 if tail < 25 else -8); pts += p; detail["sofr_tail"] = p
    liquidity_score = int(round(clamp(pts, 0, 100)))

    # Regime band from the 0-100 score; SRF stress overrides downward.
    if liquidity_score >= 80:   regime = "🟢 ABUNDANT"   # flush — "too loose" watch
    elif liquidity_score >= 60: regime = "🟡 AMPLE"      # comfortably loose
    elif liquidity_score >= 45: regime = "⚪ BALANCED"
    elif liquidity_score >= 25: regime = "🟠 TIGHTENING"
    else:                       regime = "🔴 STRESS"
    if srf_bn >= 10 or (spread is not None and spread > 5 and (rrp_bn or 0) < 10):
        regime = "🔴 STRESS"

    net_liq = round(walcl_bn - tga_bn - (rrp_bn or 0), 0) if walcl_bn else None
    return {
        "regime": regime, "liquidity_score": liquidity_score, "score_detail": detail,
        "layers": L, "triggers": triggers, "notes": notes,
        "headline_metrics": {
            "liquidity_score": liquidity_score,
            "sofr": sofr_rate, "iorb": iorb, "spread_bp": spread,
            "effr": (effr or {}).get("rate"),
            "rrp_bn": round(rrp_bn, 1) if rrp_bn is not None else None,
            "reserves_t": round(res_t, 2) if res_t else None,
            "tga_bn": round(tga_bn, 0) if tga_bn else None,
            "srf_bn": round(srf_bn, 2),
            "net_liquidity_bn": net_liq,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Formatting + state + Telegram
# ─────────────────────────────────────────────────────────────────────────────
def fmt_human(out):
    s = out["scoring"]; h = s["headline_metrics"]; cal = out["calendar"]
    lines = [
        f"# USD Liquidity — {out['timestamp_utc'][:10]}",
        f"## Liquidity Score: {s['liquidity_score']}/100  →  {s['regime']}",
        f"   (100 = flush/too-loose · 50 = balanced · 0 = funding stress)",
        "",
        f"SOFR {h['sofr']}  |  IORB {h['iorb']}  |  spread {h['spread_bp']}bp  |  EFFR {h['effr']}",
        f"ON RRP ${h['rrp_bn']}B (buffer)  |  Reserves ${h['reserves_t']}T  |  TGA ${h['tga_bn']}B",
        f"SRF takeup ${h['srf_bn']}B  |  Net liquidity ${h['net_liquidity_bn']}B",
        "",
        "Layers (higher = tighter):",
    ]
    for k, v in s["layers"].items():
        lines.append(f"  {k:>20}: {v['value']}  → score {v['score']}")
    if s["triggers"]:
        lines += ["", "Triggers:"] + [f"  • {t}" for t in s["triggers"]]
    if s["notes"]:
        lines += ["", "Notes:"] + [f"  • {n}" for n in s["notes"]]
    me = cal["month_end"]
    tag = " (QUARTER-END — biggest repo spike)" if cal["is_quarter_end_month"] else ""
    lines += ["", f"Next calendar pressure: month-end {me} in {cal['days_to_month_end']}d{tag}"]
    return "\n".join(lines)


def fmt_telegram(out, changed_from=None):
    s = out["scoring"]; h = s["headline_metrics"]; cal = out["calendar"]
    parts = []
    if changed_from:
        parts.append(f"🔔 *REGIME CHANGED:* {changed_from} → {s['regime']}\n")
    parts += [
        f"*USD Liquidity: {s['liquidity_score']}/100* {s['regime']}  ({out['timestamp_utc'][:10]})",
        "",
        f"SOFR `{h['sofr']}` vs IORB `{h['iorb']}` = *{h['spread_bp']}bp*",
        f"ON RRP `${h['rrp_bn']}B`  Reserves `${h['reserves_t']}T`  TGA `${h['tga_bn']}B`",
        f"SRF `${h['srf_bn']}B`  NetLiq `${h['net_liquidity_bn']}B`",
    ]
    if s["triggers"]:
        parts += [""] + [f"⚠️ {t}" for t in s["triggers"][:4]]
    me = cal["month_end"]
    tag = " (QTR-END)" if cal["is_quarter_end_month"] else ""
    parts += ["", f"Next pressure: month-end {me} in {cal['days_to_month_end']}d{tag}"]
    return "\n".join(parts)


def send_telegram(msg):
    if TEST_MODE:
        print("─── TEST_MODE: would send ───\n" + msg + "\n─── end ───", file=sys.stderr)
        return True
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(f"[WARN] No Telegram creds; message NOT sent:\n{msg}", file=sys.stderr)
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[ERROR] Telegram {r.status_code}: {r.text[:200]}", file=sys.stderr)
        # retry as plain text (lone _/* break Markdown)
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": msg, "disable_web_page_preview": True}, timeout=30)
    return r.ok


def load_state():
    if STATE_FILE.exists():
        return safe(lambda: json.loads(STATE_FILE.read_text()), default={})
    return {}


def save_state(regime, score):
    STATE_FILE.write_text(json.dumps({
        "last_regime": regime, "last_score": score,
        "last_run_iso": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--telegram", action="store_true", help="send Telegram if regime changed / SRF stress")
    ap.add_argument("--force", action="store_true", help="with --telegram, always send")
    args = ap.parse_args()

    out = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fred":    pull_all_fred(),
        "sofr":    safe(lambda: pull_rate("secured/sofr"), label="SOFR"),
        "effr":    safe(lambda: pull_rate("unsecured/effr"), label="EFFR"),
        "rrp_ops": safe(pull_rrp_ops, label="RRP ops"),
        "srf":     safe(pull_srf, label="SRF"),
        "calendar": calendar_pressure(),
    }
    out["scoring"] = score(out)

    if args.telegram:
        prev = load_state()
        regime = out["scoring"]["regime"]
        score_v = out["scoring"]["liquidity_score"]
        srf_stress = (out["scoring"]["headline_metrics"]["srf_bn"] or 0) >= 1
        changed = prev.get("last_regime") not in (None, regime)
        if args.force or changed or srf_stress:
            ok = send_telegram(fmt_telegram(out, changed_from=prev.get("last_regime") if changed else None))
            print(f"[telegram] sent={ok} score={score_v} regime={regime} changed={changed} srf_stress={srf_stress}",
                  file=sys.stderr)
        else:
            print(f"[telegram] no change (still {regime} {score_v}/100); skipped", file=sys.stderr)
        save_state(regime, score_v)

    if args.json_only:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(fmt_human(out))
        print("\n--- JSON ---")
        print(json.dumps(out["scoring"]["headline_metrics"], indent=2, default=str))


if __name__ == "__main__":
    main()
