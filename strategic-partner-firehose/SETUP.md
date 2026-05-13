# Strategic Partner Firehose — Setup

If you've already completed `price-alert/SETUP.md` and `insider-firehose/SETUP.md` (Telegram bot + GitHub Secrets), this skill needs **zero additional setup** — it reuses the same bot and secrets.

---

## Prerequisites

- ✅ `TELEGRAM_BOT_TOKEN` set in your fork's GitHub Secrets (from price-alert setup)
- ✅ `TELEGRAM_CHAT_ID` set in your fork's GitHub Secrets (from price-alert setup)
- ✅ The `.github/workflows/strategic-partner-firehose.yml` workflow enabled on your fork

That's it. The workflow auto-runs every 60 min weekdays 9 AM - 7 PM ET.

---

## Enable the workflow

On your forked repo:

1. Open `https://github.com/<your-username>/claude-investment-skills/actions`
2. Find **"Strategic Partner Firehose (8-K + 13D Real-Time)"** in the left sidebar
3. Click it, then click **"Enable workflow"** if it's not already on

The first run will fire on the next hour boundary (e.g. if you enable at 14:23 UTC, first run is 15:00 UTC).

---

## Test before going live

```
Actions → Strategic Partner Firehose → Run workflow → set test_mode = true
```

Look for `[ALERT]` lines in the log. If you see them in test mode but no Telegram messages, switch `test_mode` to `false` and re-run.

---

## Tune the thresholds

Defaults: **mcap ≥ $50M** and **deal ≥ $50M**. These cut noise but may filter early-stage names you'd want.

Make smaller-cap names eligible:

```
Run workflow → min_mcap → 25000000      ($25M mcap floor)
Run workflow → min_amount_m → 25        ($25M deal floor)
```

Make alerts rarer (only mega-deals):

```
Run workflow → min_mcap → 500000000     ($500M mcap floor)
Run workflow → min_amount_m → 200       ($200M deal floor)
```

---

## How alerts look

```
🤝🟢 STRATEGIC PARTNER INVESTMENT — $200M

Ticker: SGH
🐉 SK Telecom (tier_1)
Filing: 8-K, Item 1.01,3.02,7.01,9.01

Type: PIPE (Preferred)
Conversion @: $32.81

[SEC EDGAR ›]

🏢 SMART Global Holdings designs, builds and deploys enterprise 
   solutions worldwide · Technology

📈 Valuation
  Cap: $1.1B
  P/E: 18.5

📊 Price
  Now: $20.00
  vs 200DMA: -9.1%

🔥🔥🔥 Partner Score: 9/10
  EXCEPTIONAL — Founder-CEO level signal
  ✅ Tier-1 strategic investor
  ✅ Large deal ($200M)
  ✅ Deal = 18% of mcap (high commitment)
  ✅ Conversion premium +64% (long-term believer)
  ✅ Below 200DMA (-9%) — contrarian
```

Tier emoji legend:
- 🐉 Tier-1 (NVIDIA, MSFT, SKT, Samsung, TSMC, Oracle)
- 👑 Sovereign (MGX, PIF, Mubadala, ADIA, Temasek, GIC)
- 🦅 Tier-2 (Intel Capital, Qualcomm Ventures, Salesforce Ventures)
- 🦊 Smart-money VC (a16z, Sequoia, Founders Fund, Lux Capital)

Score legend:
- 🔥🔥🔥 9-10: Founder-CEO level signal (rare, ~1-2/month)
- ⭐⭐⭐ 7-8: Strong buy — Tier-1 + meaningful size
- ⭐⭐ 5-6: Watch — real signal but caveats
- ⭐ 3-4: Modest signal
- ▫️ 0-2: Weak / noise

---

## Run the test suite locally

```bash
cd ~/.claude/skills/strategic-partner-firehose/scripts
python3 tests/test_all.py
```

Expected: **32 tests pass in < 0.1 seconds**. PENG/SGH end-to-end should print `score=9/10`.

---

## CLI scoring tool (analysis.py)

You can ad-hoc score any deal without running the full firehose:

```bash
cd ~/.claude/skills/strategic-partner-firehose/scripts

# PENG/SGH replay (SK Telecom $200M)
python3 analysis.py SGH --amount 200 --tier tier_1 \
    --investor SK_Telecom --type "PIPE (Preferred)" \
    --conversion-price 32.81
```

The CLI pulls live valuation + price action via yfinance (set `--no-enrich` to skip).

---

## Costs

- SEC EDGAR: **$0** (public, free, no key)
- yfinance: **$0** (Yahoo Finance unofficial)
- GitHub Actions: **$0** on public repos (~10 min/day compute)
- Telegram: **$0**

Total: **$0 / month**.

---

## Architecture diagram

```
SEC EDGAR (8-K + 13D atom feeds, every 60 min cron)
         │
         ▼
strategic-partner-firehose/scripts/
   ├── partner_firehose.py    (main entry)
   ├── investor_registry.py   (TIER_1 / TIER_2 / SOVEREIGN / SMART_VC)
   ├── parsers.py             (regex extractors)
   ├── filters.py             (mcap + US-listed + amount)
   ├── analysis.py            (Partner Score 0-10)
   └── strategic_state.json   (dedup, auto-committed back)
         │
         ▼ (cross-skill import)
insider-firehose/scripts/enrichment/
   ├── valuation.py           (yfinance: P/E, mcap, net cash)
   ├── price_action.py        (50DMA, 200DMA, 52W context)
   ├── company_info.py        (one-liner business description)
   └── format.py              (Telegram Markdown rendering)
         │
         ▼
Telegram bot ($TELEGRAM_BOT_TOKEN)
```
