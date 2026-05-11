# Insider Firehose — Setup

If you've already completed `price-alert/SETUP.md` (Telegram bot + GitHub Secrets), this skill needs **zero additional setup** — it reuses the same bot and secrets.

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

## How alerts look

Each alert is one Telegram message in this format:

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

---

## Costs

- SEC EDGAR API: **$0** (public, free, no key)
- GitHub Actions: **$0** on public repos (≈ 30 min/day of compute)
- Telegram Bot API: **$0** (always free)
- Storage: **$0** (state file < 100 KB at cap)

Total: **$0 / month**.

---

## Architecture diagram

See main `README.md` Component map. This skill adds one new branch:

```
SEC EDGAR ─[every 30 min cron]→ form4_firehose.py ─→ Telegram bot
                                   │
                                   └─ commit form4_state.json (dedup)
```
