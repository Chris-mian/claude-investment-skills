# Price Alert — Natural Language Recipe Book

> Copy-paste examples of what to text your Telegram bot. The bot understands plain English and Chinese, sets alerts with proper notes, and replies in your language.

[中文版 / Chinese version](./EXAMPLES-zh.md)

---

## 🎯 Price target alerts (most common)

### Buying tier / accumulation

| Text the bot | What gets created |
|---|---|
| `alert me when GLW hits $140` | GLW ≤ $140 |
| `I want to add to NVDA at $1000` | NVDA ≤ $1000, note: "add position" |
| `etf SPY 跌到 700 通知我加仓` | SPY ≤ $700, note: "加仓" |
| `entry tier 1 for VST at $135` | VST ≤ $135, note: "entry tier 1" |
| `等 AMD 跌到 $280 我抄底` | AMD ≤ $280, note: "抄底" |

### Trim / profit-taking

| Text the bot | What gets created |
|---|---|
| `trim signal for ORCL at $250` | ORCL ≥ $250, note: "trim signal" |
| `NVDA 涨到 $1300 我减仓` | NVDA ≥ $1300, note: "减仓" |
| `take profit on SMH at $620` | SMH ≥ $620, note: "take profit" |
| `tell me when TSLA hits $500 to sell` | TSLA ≥ $500, note: "sell signal" |

### Stop loss

| Text the bot | What gets created |
|---|---|
| `stop loss on AMD at $260` | AMD ≤ $260, note: "stop loss" |
| `NOK 跌穿 $11 止损` | NOK ≤ $11, note: "止损" |

---

## 📉 Single-day moves (incl. pre-market & after-hours)

For when you care about news-driven gaps, not slow grinds.

| Text the bot | What gets created |
|---|---|
| `NVDA drops 5% in a day` | NVDA single-day -5% (vs prev close) |
| `AMD 单日跌 8% 通知我` | AMD single-day -8% |
| `any day SPY drops 3%` | SPY single-day -3% |
| `alert if TSLA jumps 10% in one day` | TSLA single-day +10% |
| `META 一天涨超过 15%` | META single-day +15% |
| `notify me if ORCL gaps down 5% pre-market` | ORCL single-day -5% (includes pre-market) |

**Note**: these reset every day. After today fires, the same alert keeps watching tomorrow's session.

---

## 📈 Moving average crosses (NEW)

For "trend break" signals.

### 50-day MA

| Text the bot | What gets created |
|---|---|
| `VST drops below 50DMA` | VST ≤ 50-day MA |
| `NVDA 跌破 50 日均线` | NVDA ≤ 50DMA |
| `alert when AMD breaks above 50DMA` | AMD ≥ 50DMA |
| `SMH 站稳 50DMA 通知我` | SMH ≥ 50DMA |

### 200-day MA (the "bull/bear" line)

| Text the bot | What gets created |
|---|---|
| `notify if SPY drops below 200DMA` | SPY ≤ 200-day MA |
| `ORCL 跌破 200 日均线` | ORCL ≤ 200DMA |
| `alert when QQQ breaks 200DMA from below` | QQQ ≥ 200DMA |
| `NVDA 突破 200DMA` | NVDA ≥ 200DMA |

**Why MA matters**: 50DMA = short-term trend, 200DMA = long-term trend. Stocks dropping below 200DMA are technically in bear-mode; reclaiming it = bullish setup.

---

## 🔀 Compound conditions (OR — any trigger fires)

Tell the bot multiple conditions; it creates separate alerts that fire independently.

| Text the bot | What gets created |
|---|---|
| `alert me if GLW hits $140 OR drops 10% in a day` | 2 alerts: GLW ≤ $140 + GLW single-day -10% |
| `ORCL 跌到 $190 或者单日跌 3%` | 2 alerts: ORCL ≤ $190 + ORCL single-day -3% |
| `NVDA breaks 200DMA OR drops to $900` | 2 alerts: NVDA ≤ 200DMA + NVDA ≤ $900 |
| `tell me when SMH drops to $480 or any day -5%` | 2 alerts: SMH ≤ $480 + SMH single-day -5% |
| `VST $135 加仓信号，或者跌穿 50DMA` | 2 alerts: VST ≤ $135 (note: 加仓) + VST ≤ 50DMA |

---

## 🎯 Position-management style examples

These show how to embed **your intent** in the alert note, so when it fires you remember why.

| Your strategy | Text the bot |
|---|---|
| Building a 3-tier entry on NVDA | `set 3-tier NVDA entry: $1100 tier 1, $980 tier 2, $850 tier 3` (creates 3 alerts) |
| Watching for capitulation buy | `AMD drops 25% from here, tell me — capitulation buy` |
| Covered-call early-warning | `ORCL approaches $210 — I have calls expiring there` |
| Dividend ex-date entry | `GLW pulls back to $150 before ex-div date` |
| Earnings reaction | `if AMD drops 12% in a day, tell me — earnings disaster buy` |
| Macro pivot | `tell me if SPY drops below 200DMA — regime shift signal` |

The note travels with the alert and shows up in the trigger notification so you remember the play.

---

## 🗂️ Management commands

| Text the bot | Result |
|---|---|
| `list my alerts` / `什么 alerts 我有` | Bot replies with active alerts table |
| `show all alerts including fired` | Includes fired/triggered history |
| `cancel GLW` / `取消 GLW` | Cancels all GLW alerts |
| `cancel the $190 ORCL one` | Bot identifies specific alert by description |
| `remove all alerts` / `清空全部` | Bot asks confirmation, then cancels everything |
| `re-arm the fired NVDA alert` | Re-activates a previously fired alert |

---

## 🌐 Mixed-language conversations

The bot handles mixed EN/CN in one message naturally.

| Text the bot | What gets created |
|---|---|
| `set GLW alert at $140 加仓信号` | GLW ≤ $140, note: "加仓信号" |
| `AMD 跌 10% 通知我, this is a buying chance` | AMD drop 10%, note: "buying chance" |
| `NVDA 突破 200DMA, regime shift alert` | NVDA ≥ 200DMA, note: "regime shift" |

---

## 🎁 Convenience tricks

### Show me what's close to triggering

```
which alerts are closest to firing?
```

Bot will fetch current prices and rank your alerts by distance-to-trigger.

### Bulk set from watchlist

```
set alerts for AI semi: NVDA $1000, AMD $280, SMCI $30, MU $450
```

Bot creates 4 alerts in one turn.

### Conditional notes

```
GLW at $140 for tier 1, $120 for tier 2, $100 for tier 3 — all with note 'AI glass'
```

3 alerts, all noted "AI glass".

---

## ❌ What the bot WON'T do

The bot is scoped to **alert management only**. For these, use Claude Code directly:

| ❌ Bot can't answer | ✅ Ask Claude Code instead |
|---|---|
| "What's NVDA price right now?" | `analyze NVDA` |
| "Should I buy ORCL?" | `is ORCL a buy?` |
| "What's the macro setup?" | `macro warning` / `regime check` |
| "Recommend a portfolio hedge" | `portfolio audit` |
| "Find me undervalued AI plays" | `find untapped thesis in AI` |

The bot's job: **set, list, cancel alerts**. Claude Code's job: **research and analysis**.

If you ask the bot something out of scope, it'll politely tell you and suggest Claude Code.

---

## 🚀 Advanced: composing alerts with macro logic

You can use Claude Code (not the bot) to build complex multi-conditional setups. For example:

```
You (in Claude Code): given current macro is ORANGE, set up defensive alerts:
  - All my AI/Semi positions trigger if SMH drops 8% in a day
  - GLW / ONTO / LRCX trigger at -25% pullback levels
  - VIX > 25 → tell me (need to add VIX as a ticker)
  - 200DMA breaches on all my AI Power holdings (VST, CEG)
```

Claude Code reads your portfolio, looks up current prices, computes the right strike levels, and runs `add_alert.py` for each — all in one conversation. Then commits.

After that, the Telegram bot becomes your read-only delivery channel + occasional management.

---

## 💡 Future capabilities (not yet supported)

If you want these, ping the dev:

- RSI overbought/oversold (RSI > 70 / RSI < 30)
- MACD signal crosses
- Bollinger band breakouts
- Volume spike (>2× 20-day avg)
- Death cross / golden cross (50DMA crosses 200DMA)
- Earnings/event-date-relative alerts
- Sector / index correlations (alert me when SPY moves and ORCL doesn't)
- Multi-leg compound logic (A AND B, not just OR)

These need historical price data + more complex state, but all are buildable. Open an issue on the GitHub repo.
