# Setup — macro-liquidity-monitor

## Dependencies

Only `requests`. The other firehose skills already create `/tmp/.insider_venv`;
this skill reuses it, and falls back to system `python3`.

```bash
python3 -m pip install --quiet requests
```

## Run it now

```bash
python3 ~/.claude/skills/macro-liquidity-monitor/scripts/liquidity_pull.py
```

## Scheduled Telegram push (GitHub Actions)

The workflow `.github/workflows/macro-liquidity.yml` runs daily at 8:30am ET
(`30 12 * * 1-5`, weekdays) and pushes a Telegram message **only when the regime
changes** or **SRF takeup ≥ $1B** (idempotent via `scripts/state.json`, committed back).

It reuses the **same GitHub secrets** the insider/price-alert firehoses already use:

| Secret | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID`   | target chat / channel id |

No FRED or NY Fed key is needed — both are public.

### Manual trigger / test

`workflow_dispatch` exposes:
- `force` = `true` → send the Telegram even if the regime hasn't changed.
- `test_mode` = `true` → print the message to the Actions log, do NOT send.

### Local Telegram test (no send)

```bash
TEST_MODE=1 python3 .../scripts/liquidity_pull.py --telegram --force
```

## State

`scripts/state.json` holds `{last_regime, last_composite, last_run_iso}`. Delete it
to force the next run to alert. It is committed by the Action so reruns don't double-fire.
