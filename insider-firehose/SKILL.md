---
name: insider-firehose
description: Real-time SEC Form 4 insider-trading aggregator with Telegram push alerts when officers/directors buy more than $200k of their own stock on the open market. Triggers in English ("show today's insider buys", "form 4 today", "who's buying right now", "insider firehose") or Chinese ("今天 insider 怎么样", "今天谁在加仓", "form 4 实时", "内部交易实时").
---

# Insider Firehose — Real-Time Form 4 Aggregator

Pulls the SEC EDGAR Form 4 "current filings" atom feed and pushes a Telegram alert for every open-market purchase ≥ $200k by officers or directors.

## Why this exists

Tools like openinsider.com aggregate Form 4 filings but scrape on a 12-24 hour delay. **This skill pulls directly from SEC EDGAR with a 2-5 minute delay** — same authoritative source, 100-300x faster.

It also enforces the methodology rules from `review-investment-screenshot/SKILL.md`:
- **Form 4 code "P" only** (open-market purchase) — never A/M/F/G/D/C (RSU vest, option exercise, tax withholding, gift, distribution, conversion). Aggregators that conflate these produce false-positive cluster-buy headlines like the 2026-04-01 UNH "10 directors buying" story (all DSU grants).
- **10% holder-only buys skipped** by default. These are often activist funds (Saba Capital) or institutional positions, not officer/director conviction signals.
- **$200k threshold** filters out small qualifying purchases (board minimums, ESPP-style buys).

## Architecture

```
SEC EDGAR atom feed (every 30 min cron, weekdays 9 AM - 7:30 PM ET)
   │
   ▼
form4_firehose.py
   │  pulls feed, dedupes via form4_state.json
   │  for each NEW filing: fetch raw XML, parse <nonDerivativeTransaction>
   │  filter: code == "P", value ≥ $200k, role != pure 10% holder
   ▼
Telegram bot ($TELEGRAM_BOT_TOKEN)
   │
   ▼
🚨🟢 INSIDER BUY — $X.XM
$TICKER (Company) — Owner (Officer/Director/Title)
N,NNN shares @ $X.XX  · [SEC EDGAR ›]
```

State (which filings we've already alerted on) lives in `scripts/form4_state.json` and is auto-committed by the workflow back to the repo. Cap of 5000 entries (≈ 1 week of Form 4 volume).

## Files

- `scripts/form4_firehose.py` — core script: fetch + parse + filter + send
- `scripts/form4_state.json` — accession-number ledger (auto-managed)
- `.github/workflows/insider-firehose.yml` — cron + state commit

## Tuning knobs (workflow_dispatch inputs)

| Input | Default | Use |
|---|---|---|
| `min_value` | `200000` | Bump to `500000` or `1000000` if too noisy |
| `include_sells` | `false` | `true` to also alert on sells ≥ 5x threshold |
| `test_mode` | `false` | `true` prints to log instead of Telegram |

Or run manually:

```bash
TEST_MODE=1 FORM4_MIN_VALUE=500000 python scripts/form4_firehose.py
```

## Tradeoffs vs. openinsider.com

| | Firehose (this) | openinsider.com |
|---|---|---|
| Latency | 2-5 min from filing | 12-24 hours |
| Form 4 code filter | P only (true buy) | All codes shown |
| 10% holder vs officer | Officers prioritized | Mixed together |
| Threshold filter | Configurable USD | Manual UI sort |
| Notification | Telegram push | None (pull-only website) |
| Bilingual output | EN + CN role labels | EN only |
| Cost | $0 (free EDGAR + GH Actions) | Free (website) |

## What this skill does NOT do (yet)

- **Cluster detection** — currently alerts on each filing independently. If 9 insiders of one company all file on the same day (as AVA did on 2026-05-11), you get 9 separate alerts. v2.1 will roll these up into a single "🚨 CLUSTER" alert.
- **Watchlist filter** — alerts fire for ALL tickers ≥ $200k. v2.1 will let you highlight tickers you already own.
- **Daily digest** — currently push-only. v2.1 adds an end-of-day Telegram summary aggregating the day's buys.
- **Sells by default** — sells are 10x more common and mostly noise (10b5-1 plans). Set `include_sells=true` for unusual-sell alerts (≥ $1M).

## When this triggers (examples from real Form 4 filings)

Real signals this script catches:
- **PLSE Duggan Robert W (Director + 10%)**: bought $12,999,988 — Pulse Biosciences founder doubling down
- **PLSE Laviolette Paul A (CEO)**: bought $295,350 on same day → cluster signal
- **LW Gray James D**: bought $409,225 — Lamb Weston (foods)
- **ATEC Valentine Keith**: bought $996,192 — Alphatec spine

Real signals from the user's 2026-05-11 SEC EDGAR pull this skill would have alerted on:
- **ET Kelcy Warren (Founder)**: $22M — Energy Transfer (highest-conviction founder buy of the day)
- **AVA 9-insider cluster**: $1.3M total ($145k each, just below $200k individually → cluster would catch it)
- **KGS 6-insider cluster**: $900k total
- **EFX 3-director cluster**: $660k total
- **SOFI CEO Anthony Noto**: $248k (4th buy in 90 days)

## Setup

Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in GitHub Secrets (same ones used by `price-alert/`). See `SETUP.md` for first-run checklist.

## Companion skills

- `review-investment-screenshot/scripts/insider_ratio.py` — per-ticker deep dive (when an alert fires, run this for full 90d context)
- `analyze-stock` — when alert + you don't recognize the ticker, this skill pulls fundamentals + macro context
- `macro-warning` — gate any conviction buy by current regime
