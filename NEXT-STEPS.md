# Next Steps — Roadmap & Known Limitations

This document captures planned features, known limits, and intentional design boundaries. It's the canonical place to look when asking "can this tool do X?"

[中文版 / Chinese version](./NEXT-STEPS-zh.md)

---

## What works today (v1.6)

### Alert condition types

| Op | Trigger | Example utterance | Status |
|---|---|---|---|
| `below` | price ≤ threshold | "alert me when GLW hits $140" | ✅ |
| `above` | price ≥ threshold | "alert if AAPL goes above $250" | ✅ |
| `drop` | -% from anchor price (static at creation) | "notify if NVDA drops 10%" | ✅ |
| `rise` | +% from anchor | "alert if SPY rises 5%" | ✅ |
| `drop_intraday` | single-day -% vs prev close, incl. pre/after-hrs | "AMD 单日跌 5%" | ✅ |
| `rise_intraday` | single-day +% vs prev close | "TSLA 单日涨 7%" | ✅ |
| `below_ma_50` | price ≤ 50-day **SMA** | "VST 跌破 50DMA" | ✅ |
| `above_ma_50` | price ≥ 50-day SMA | "NVDA 突破 50DMA" | ✅ |
| `below_ma_200` | price ≤ 200-day SMA | "SPY 跌破 200DMA" | ✅ |
| `above_ma_200` | price ≥ 200-day SMA | "META 突破 200DMA" | ✅ |
| `below_ema_*` / `above_ema_*` | EMA | "X 跌破 50EMA" | ❌ v1.7 |
| `rsi_below_30` / `rsi_above_70` | RSI threshold | "X RSI < 30 提醒" | ❌ v1.7 |
| `volume_above_Nx` | volume > N× 20d avg | "X 成交放量提醒" | ❌ v1.8 |
| Compound AND | "X < 140 AND VIX > 25" | currently must split into 2 alerts | ❌ v1.9 |
| Compound OR | "X < 140 OR Y > 200" | works via decomposition (Claude creates 2 alerts) | ✅ via NL |

### Chat paths

- ✅ **GitHub Actions polling** (Option A, latency 2-15 min)
- ✅ **Cloudflare Workers webhook** (Option B, latency 1-3 sec)
- ✅ Bilingual NL parsing (EN + CN) via Claude Sonnet 4.6 with tool use
- ✅ UTF-8 round-trip for non-Latin1 alert notes (Chinese, em-dashes, emoji)

### Analysis skills (14)

`analyze-stock`, `earnings-prep`, `find-alpha`, `find-untapped-thesis`, `leaps-screen`, `macro-risk-check`, `macro-warning`, `narrative-reversal-screen`, `option-wall-analysis`, `portfolio-audit`, `price-alert`, `review-investment-screenshot`, `sector-rotation-analysis`, `tax-optimize`. All enforce the **macro → stock → entry → sizing → tax** pre-flight checklist.

---

## Latency / cadence — known limits

The price scanner runs on **GitHub Actions cron every 2 minutes**, 24/7. That means:

- Alerts fire **0-2 minutes** after the price actually crosses the threshold.
- Pre/after-hours moves ARE captured — yfinance returns the latest quote including extended hours.
- **Not suitable for sub-minute reactions**. If you need a 5-second alert on a sweep order, use a real broker (IBKR mobile, ThinkOrSwim, TradingView).

### Why we can't simply make it faster

| Approach | Cost | Why we haven't done it |
|---|---|---|
| Cron every 1 min on GH Actions | $0 | Cron min granularity is technically 1 min but coalesces to 5-15 min during GH peak hours. Not reliable. |
| Cloudflare Cron Triggers (1-min min) | $0 | Possible upgrade; would require porting `check_alerts.py` to TypeScript. On roadmap as v1.7. |
| WebSocket from Polygon.io / Alpaca | $30-50/mo | Real-time. Requires rewrite as persistent worker. On roadmap (v2.0) but requires a paid data tier. |
| Broker order webhook (IBKR, Tradier) | $0-10/mo | Hooks the broker's own price stream. Most accurate but ties tool to one broker. |

### When you actually need real-time

If you're sweeping orders or scalping, use a **broker-side alert**. Use this tool's alerts for **research-grade triggers** — "remind me when GLW comes back to my tier-1 entry" — where 2-minute granularity is more than enough.

---

## Roadmap by version

### v2.2 (next — insider firehose iterations)

| Feature | Owner files |
|---|---|
| **Cluster detection** — roll up multiple same-ticker same-day filings into one "🚨 N-INSIDER CLUSTER" alert (e.g. AVA 9-insider cluster = 1 alert not 9) | `form4_firehose.py` add aggregation pass |
| **Watchlist filter** — alerts on your already-held tickers get 🟡 highlight + always pass through, even below threshold | `form4_state.json` add `watchlist` field; pull from `price-alert/alerts.json` ticker list |
| **Daily digest** — end-of-day Telegram summary aggregating all buys (not just ≥ $200k), sortable | `form4_digest.py` new script + separate cron at 17:30 ET |
| **Founder buy auto-bump** — if `officerTitle` contains "Founder", lower threshold to $50k (founder $50k = high signal vs CFO $200k) | `form4_firehose.py` role-aware threshold |
| **Historical insider context in score** — openinsider 180d cluster detection feeds into Smart Money Score (+1 if 3rd buy in 90d) | `enrichment/insider_history.py` new module |
| **Score-based filter** — `FORM4_MIN_SCORE` env var to suppress alerts below a chosen score (e.g. only push score ≥ 5) | `form4_firehose.py` post-enrichment filter |

### v1.7 (next minor)

| Feature | Owner files |
|---|---|
| **EMA support** — `below_ema_9` / `above_ema_9` / `below_ema_20` / etc. | `check_alerts.py` (compute from `history(period="60d").Close.ewm(span=N).mean()`), `worker.ts` enum, `chat_handler.py` enum, SYSTEM_PROMPT updates in both |
| **Configurable SMA periods** — `below_ma_X` for any X (not just 50, 200) | Same as above; treat 50DMA / 200DMA as special cases |
| **RSI thresholds** — `rsi_below_30`, `rsi_above_70`, `rsi_above_X` | New op type; 14-day RSI compute via `pandas-ta` or manual |
| **Cloudflare Cron Triggers option** for price scan | Optional `worker-scan.ts` running on 1-min Cloudflare cron; user picks GH Actions or CF |
| Improved alert message formatting (markdown links to charts) | `check_alerts.py` Telegram message builder |

### v1.8

| Feature | Notes |
|---|---|
| **Volume spike alerts** — `volume_above_Nx_20d` | News-driven move detector |
| **Bollinger band touches** — `below_bb_lower`, `above_bb_upper` | Volatility-aware mean reversion |
| **Slack webhook channel** | Many users have personal Slacks; simple `--notify slack` flag |
| **Discord webhook channel** | Same pattern as Slack |
| **`tax-loss-harvest-screen` skill** | Scan portfolio for wash-sale-aware harvest candidates Q4 |

### v1.9

| Feature | Notes |
|---|---|
| **Multi-condition AND alerts** — e.g. "X below 140 AND VIX > 25" | Schema change: condition becomes a tree, not a leaf |
| **Email digest mode** — daily/weekly summary of fired alerts | `--notify email` channel + SES integration |
| **Alert lifecycle states** — `paused`, `expired`, `archived` (beyond `active`/`fired`) | Schema + UI in chat handler |
| **`dividend-capture` skill** | Ex-div opportunity screener |
| **`options-flow-monitor` skill** | Unusual options activity alerts |

### v2.0 (major)

| Feature | Notes |
|---|---|
| **FX pairs** — `USD/JPY`, `EUR/USD`, `GBP/USD`, ... | yfinance supports via `JPY=X`-style symbols; useful for carry-trade signals |
| **Crypto** — BTC, ETH, key levels | yfinance has `BTC-USD` etc. |
| **International equities** — Japan (TYO), Hong Kong (HKG) | yfinance has Tokyo + HK feeds |
| **Optional Polygon.io / Alpaca WebSocket** for real-time price stream | Paid tier; persistent worker; opt-in |
| **`relative-strength-rank` skill** | Weekly RS ranking across watchlist |

---

## What this tool is NOT planning to become

- ❌ A trading bot that places orders
- ❌ A backtesting engine for signal generation
- ❌ A portfolio accounting tool (track P&L over time, generate tax forms)
- ❌ A research collaboration / social platform
- ❌ Real-time tick-by-tick streaming infrastructure
- ❌ A market-making / arbitrage system
- ❌ A B2B SaaS — there's no managed-tier roadmap; everyone self-hosts on their own GitHub fork + CF account

Stay in the lane: **research-grade investment thinking partner** with disciplined methodology for **personal finance / individual buy-side investors** doing swing / position / LEAPS horizons.

---

## Contributing

Open an issue tagged with the version label (`v1.7`, `v1.8`, etc.) and a type label (`feature`, `data-source`, `channel`, `skill`).

Each new condition type follows the same pattern:

1. Add the enum entry in `price-alert/webhook/worker.ts` AND `price-alert/scripts/chat_handler.py` (both must match — they share the same NL schema)
2. Add the evaluation logic in `price-alert/scripts/check_alerts.py`
3. Add a unit test that triggers + verifies the message
4. Update `price-alert/EXAMPLES.md` with bilingual sample utterances
5. Update `AGENT-TOOL-REFERENCE.md` Tool 6 with the new pattern mapping
6. Bump version in `README.md` Changelog

For new skills, follow the existing `SKILL.md` pattern with `description:` frontmatter listing bilingual triggers. Always inject the Pre-flight checklist if the skill makes buy/add/trim recommendations (template in any of the v1.6-updated skills).

---

## Versioning history

| Version | Date | Highlights |
|---|---|---|
| **2.2** | 2026-05-12 | **NEW SKILL: `strategic-partner-firehose`** — real-time SEC 8-K + SC 13D monitor for PIPE deals + strategic investments. Detects Tier-1 (NVIDIA, MSFT, SK Telecom, Samsung, Oracle) + Sovereign (MGX, Saudi PIF, Mubadala) + Smart-VC investments ≥ $50M into US-listed companies ≥ $50M mcap. Auto-scores 0-10 ("Partner Score") via cross-skill enrichment reuse. 32 unit tests pass; PENG/SGH backtest scores 9/10 EXCEPTIONAL. Cron hourly weekdays 9 AM - 7 PM ET. Catches the "next PENG" 6-18 months before Substack/Twitter pumps it. |
| **2.1** | 2026-05-12 | **`insider-firehose` v2.1: Tier-2 enrichment.** Every alert is auto-augmented with business one-liner, P/E + market cap + net cash + dividend, 52W price context (vs 50DMA / 200DMA / high / low), and a 0-10 Smart Money Score (role + check size + valuation + price action). Enabled by default; toggle via Telegram `/enrich on` / `/enrich off` (Chinese aliases work too), CLI `firehose_cli.py`, GitHub Actions input, or `ENRICH` env var. Non-fatal — if yfinance fails, falls back to v2.0 basic alert. yfinance added to workflow install step. Worker fast-path bypasses Claude for `/enrich` commands (cheap + low latency). |
| **2.0** | 2026-05-11 | **NEW SKILL: `insider-firehose`** — real-time SEC EDGAR Form 4 monitor with Telegram push alerts for officer/director open-market buys ≥ $200k. Cron every 30 min, weekdays. 2-5 min latency vs openinsider's 12-24 hours. State-managed dedup via committed JSON. Plugin marketplace + git-clone install both work. |
| 1.7 | 2026-05-11 | Plugin marketplace install path (`/plugin marketplace add ...`), two-way door with existing git-clone path. 47 SKILL.md script paths rewritten to dual-mode resolution. NEXT-STEPS roadmap + "Who this is for / not for" positioning, state-source observability section. |
| 1.6 | 2026-05-11 | Cloudflare Worker webhook (1-3 sec chat latency), AGENTS.md setup orchestration guide, pre-rendered Mermaid diagrams (SVG/PNG), pre-flight methodology embedded in 6 skills, AGENT-TOOL-REFERENCE.md extended with Tool 6 + Skill Catalog |
| 1.5 | 2026-05-10 | First public release, MIT LICENSE, INTRODUCTION.md, bilingual translations, "How NL triggers skills" section, 5 conversation examples |
| 1.4 | 2026-05-09 | macro-warning real data backend (`macro_pull.py`), ARCHITECTURE.md |
| 1.3 | 2026-05-08 | `macro-warning` skill (8-layer pullback radar), cron-friendly, memory integration |
| 1.2 | 2026-05-05 | AGENT-TOOL-REFERENCE.md initial — NL → CLI contract |
| 1.1 | 2026-05-05 | insider_ratio.py v3 (openinsider primary, Form 4 code-aware), cluster_buy_scan.py |
| 1.0 | 2026-05-04 | Initial release |
