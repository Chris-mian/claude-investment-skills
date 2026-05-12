# Insider Firehose — Setup (v2.1)

If you've already completed `price-alert/SETUP.md` (Telegram bot + GitHub Secrets), this skill needs **zero additional setup** — it reuses the same bot and secrets.

**v2.1 (May 2026):** alerts are now auto-enriched (P/E + market cap + 52W context + Smart Money Score). Enabled by default — see [Enrichment toggle](#enrichment-toggle-v21) below to disable.

[中文版 / Chinese version](./SETUP-zh.md)

---

## Prerequisites

- `TELEGRAM_BOT_TOKEN` set in your fork's GitHub Secrets ✓ (from price-alert setup)
- `TELEGRAM_CHAT_ID` set in your fork's GitHub Secrets ✓ (from price-alert setup)
- The `.github/workflows/insider-firehose.yml` workflow enabled on your fork

That's it. The workflow auto-runs every 30 min weekdays 9 AM - 7:30 PM ET.

---

## Enable the workflow

On your forked repo:

1. Open `https://github.com/<your-username>/claude-investment-skills/actions`
2. Find **"Insider Firehose (Form 4 Real-Time)"** in the left sidebar
3. Click it, then click **"Enable workflow"** if it's not already on

The first run will fire on the next 30-min boundary (e.g. if you enable at 14:23 UTC, first run is 14:30 UTC).

---

## Test before going live

To verify everything works before getting real alerts:

1. Go to Actions → Insider Firehose → "Run workflow"
2. Set `test_mode` to `true`
3. Click "Run workflow"
4. Wait ~30 seconds, then click the run to see logs
5. Look for `[ALERT-BUY] TICKER  $XXX,XXX  Owner Name (Role)` lines in the log

If you see ALERT-BUY lines in the log but no Telegram messages: ✅ the parser works, secrets work, you're just in test mode. Switch `test_mode` to `false` and run again.

---

## Tune the threshold

The default is **$200,000 USD** of insider buy value to trigger an alert. At this threshold you'll typically see **20-50 alerts per day** across the whole market.

Too noisy?

```
Run workflow → min_value → 500000   (≈ 5-15 alerts/day)
Run workflow → min_value → 1000000  (≈ 2-5 alerts/day, only big convictions)
```

Want sells too?

```
Run workflow → include_sells → true   (also alerts on sells ≥ 5x threshold)
```

---

## How alerts look (v2.1 enriched)

Each alert is one Telegram message. With enrichment **on** (default), you get the basic block + 4 auto-generated sections:

```
🚨🟢 INSIDER BUY — $974,582

Ticker: MKTW  (MARKETWISE, INC.)
🪑 Stansberry Frank Porter
Dir, 10%

51,375 shares @ $18.97
(4 transactions same filing)

[SEC EDGAR ›]

🏢 MarketWise, Inc. operates a content and technology multi-brand
   platform for self-directed investors. · Financial Services

📈 Valuation
  Cap: $48M
  P/E: 10.8 (fwd 90.3)
  Net cash: $47M (99% of cap)
  Div yield: 4.81%
  Rev growth: -7.8% YoY

📊 Price
  Now: $18.06
  1Y: +18.3%
  52W: +34% from low / -17% from high
  vs MA: 50d +8.5% · 200d +9.9%

⭐ Smart Money Score: 4/10
  ✅ Cheap P/E (10.8)
  ✅ Net cash 99% of mcap
  ✅ Dividend 4.8%
```

With enrichment **off**, you get the v2.0 basic block only:

```
🚨🟢 INSIDER BUY — $12,999,988

Ticker: PLSE  (Pulse Biosciences, Inc.)
🪑 DUGGAN ROBERT W
Dir, 10%

13,000,000 shares @ $1.00

[SEC EDGAR ›]
```

Role emoji legend:
- 👑 CEO / Chairman / Founder
- 💼 CFO
- 🏛 President / COO
- 🧑‍💼 Other Officer
- 🪑 Director
- 🐳 10% Holder (usually large investor / activist fund)
- ❓ Role couldn't be parsed (rare)

Smart Money Score range:
- 🔥🔥🔥 **9-10** — Founder/CEO whale + cheap + near 52W low (rare, ~1-2/month)
- ⭐⭐⭐ **7-8** — Senior officer big check + valuation/price tailwind
- ⭐⭐ **5-6** — Decent signal with caveats
- ⭐ **3-4** — Noteworthy but mixed
- ▫️ **0-2** — Low-conviction filing

---

## Enrichment toggle (v2.1)

Enrichment is **on by default**. Three equivalent ways to flip it:

### From Telegram (easiest — works on phone)

Send any of these to your alert bot:

```
/enrich          → show current state
/enrich on       → enable
/enrich off      → disable
/enrich status   → show current state
```

The bot edits `enrichment_config.json` in your fork via the GitHub API, same path as `alerts.json`. Next cron run picks up the new state. Chinese aliases (`/enrich 开`, `/enrich 关`, `/enrich 状态`) also work.

### From CLI

```bash
python insider-firehose/scripts/firehose_cli.py --status
python insider-firehose/scripts/firehose_cli.py --enrich-on
python insider-firehose/scripts/firehose_cli.py --enrich-off
# remember to commit + push enrichment_config.json so CI sees the change
git add insider-firehose/enrichment_config.json
git commit -m "firehose: enrichment off (or on)"
git push
```

### One-off via GitHub Actions

Actions → Insider Firehose → **Run workflow** → set `enrich` input to `on` or `off`. This overrides the config file for this single run without changing the saved default.

---

## Troubleshooting

### No alerts after enabling workflow

Check the Actions tab for any failed runs. Common causes:
- `TELEGRAM_BOT_TOKEN` secret missing → workflow will say `[WARN] No Telegram creds`
- Markdown 解析 errors → SEC sometimes serves malformed XML; we skip these and log

If runs are succeeding but no Telegram messages, double-check that the bot can message you:

```bash
curl "https://api.telegram.org/bot$TOKEN/getMe"
```

### Too many alerts at $200k

Raise threshold via workflow_dispatch `min_value` input (see "Tune the threshold" above). $500k cuts noise by ~50%, $1M by ~80%.

### Missing the alert I expected

Possible reasons:
1. The Form 4 was a code A/M/F (RSU/exercise/tax) — not a true purchase. The script intentionally filters these out.
2. The buyer was a pure 10% holder (no officer/director role) — also filtered by default.
3. Value below $200k threshold.
4. SEC EDGAR feed update delay (≈ 2-5 min).

To verify, run `review-investment-screenshot/scripts/insider_ratio.py TICKER --window 30` for full 30-day insider history.

### Workflow stops committing state

GitHub Actions auto-commits the `form4_state.json` checkpoint every run. If you see "no state changes to commit" repeatedly with no new alerts, the EDGAR feed might be cached. Force a fresh run via workflow_dispatch.

### Enrichment missing from alerts (v2.1)

If alerts arrive as basic format (no 🏢 / 📈 / 📊 / ⭐ blocks):
1. Check `enrichment_config.json` — is `"enabled": true`?
2. Check workflow run log for `[INFO] Pulling EDGAR Form 4 feed... (enrich=ON)`
   - `enrich=DISABLED` → config file or env var is off
   - `enrich=UNAVAILABLE` → yfinance failed to import (workflow logs will show)
3. Look for `[ENRICH-WARN]` or `[ENRICH-FAIL]` lines per ticker — yfinance occasionally rate-limits on micro-caps. Other tickers in the same batch should still enrich.

The enrichment pipeline is **deliberately non-fatal**: any failure falls back to v2.0 basic format. You'll never lose an alert because enrichment broke.

### Too noisy with enrichment scores

The Smart Money Score is interpretive — alerts still fire regardless of score. If you want to filter by score:
- Currently no built-in filter. Easiest: skim and ignore ⭐ / ▫️ entries.
- v2.2 will add `FORM4_MIN_SCORE` env var (e.g. only push score ≥ 5).

---

## Costs

- SEC EDGAR API: **$0** (public, free, no key)
- yfinance (v2.1 enrichment): **$0** (Yahoo Finance unofficial — no key, occasional rate limits)
- GitHub Actions: **$0** on public repos (≈ 30 min/day of compute, +1-2 min/day for yfinance calls)
- Telegram Bot API: **$0** (always free)
- Storage: **$0** (state file < 100 KB at cap, enrichment_config.json < 200 bytes)

Total: **$0 / month**.

---

## Architecture diagram

See main `README.md` Component map. This skill adds one new branch (v2.1):

```
SEC EDGAR ─[every 30 min cron]→ form4_firehose.py
                                   │
                                   ├─ enrichment/ (v2.1, on by default)
                                   │    ├─ valuation.py    ─ yfinance
                                   │    ├─ price_action.py ─ yfinance
                                   │    ├─ company_info.py ─ yfinance
                                   │    ├─ score.py        ─ rubric → 0-10
                                   │    └─ format.py       ─ Markdown render
                                   │
                                   ├─ commit form4_state.json (dedup)
                                   │
                                   └─→ Telegram bot
                                         ↑
                            Telegram /enrich on|off|status
                                         │
                       Cloudflare Worker → GitHub API
                                         │
                                  enrichment_config.json
```
