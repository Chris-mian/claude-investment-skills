# Price Alert —— 自然语言使用范例

> 复制粘贴这些示例给你的 Telegram bot 看。Bot 听得懂大白话英文 + 中文，自动设 alert + 把你的意图写进 note，触发时用你的语言回。

[English / 英文版](./EXAMPLES.md)

---

## 🎯 价格目标 alert（最常用）

### 建仓 / 加仓

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `GLW 跌到 $140 通知我` | GLW ≤ $140 |
| `我想在 NVDA $1000 加仓` | NVDA ≤ $1000, note: "加仓" |
| `SPY 跌到 700 加仓` | SPY ≤ $700, note: "加仓" |
| `VST 第一档入场 $135` | VST ≤ $135, note: "入场 tier 1" |
| `等 AMD 跌到 $280 我抄底` | AMD ≤ $280, note: "抄底" |

### 减仓 / 止盈

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `ORCL 涨到 $250 我减仓` | ORCL ≥ $250, note: "减仓" |
| `NVDA $1300 减仓信号` | NVDA ≥ $1300, note: "减仓" |
| `SMH $620 止盈` | SMH ≥ $620, note: "止盈" |
| `TSLA $500 通知我卖` | TSLA ≥ $500, note: "卖出信号" |

### 止损

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `AMD 跌穿 $260 止损` | AMD ≤ $260, note: "止损" |
| `NOK 跌到 $11 止损` | NOK ≤ $11, note: "止损" |

---

## 📉 单日波动（含盘前盘后）

新闻驱动的跳空有用，不是慢慢磨。

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `NVDA 单日跌 5% 通知我` | NVDA 单日 -5%（vs 前一日收盘）|
| `AMD 一天跌 8%` | AMD 单日 -8% |
| `任意一天 SPY 跌 3%` | SPY 单日 -3% |
| `TSLA 一天涨 10% 通知我` | TSLA 单日 +10% |
| `META 一天涨超 15%` | META 单日 +15% |
| `ORCL 盘前跳空 -5%` | ORCL 单日 -5%（包含盘前）|

**注意**：这种 alert 每天重新锚定。今天触发后，明天继续监控明天的盘。

---

## 📈 移动平均线（MA）—— 🆕 NEW

趋势破位信号。

### 50 日均线

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `VST 跌破 50 日均线` | VST ≤ 50DMA |
| `NVDA 跌破 50DMA 通知我` | NVDA ≤ 50DMA |
| `AMD 突破 50DMA` | AMD ≥ 50DMA |
| `SMH 站稳 50 日线` | SMH ≥ 50DMA |

### 200 日均线（牛熊分界线）

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `SPY 跌破 200 日均线通知我` | SPY ≤ 200DMA |
| `ORCL 跌破 200DMA` | ORCL ≤ 200DMA |
| `QQQ 突破 200 日线` | QQQ ≥ 200DMA |
| `NVDA 站上 200DMA` | NVDA ≥ 200DMA |

**为什么 MA 重要**: 50DMA = 短期趋势, 200DMA = 长期趋势。跌破 200DMA 技术上算 bear mode；收复 200DMA = bullish setup。

---

## 🔀 复合条件（OR 任一触发）

跟 bot 说多个条件，它会**分别建独立 alert**，任一触发都通知你。

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `GLW 跌到 $140 或者单日跌 10%` | 2 个 alert: GLW ≤ $140 + GLW 单日 -10% |
| `ORCL 跌到 $190 或者单日跌 3%` | 2 个 alert |
| `NVDA 跌破 200DMA 或者跌到 $900` | 2 个 alert: ≤ 200DMA + ≤ $900 |
| `SMH 跌到 $480 或者任意一天 -5%` | 2 个 alert |
| `VST $135 加仓信号，或者跌穿 50DMA` | 2 个 alert（都带 note）|

---

## 🎯 头寸管理风格示例

这些示例展示了**把意图写进 note**，触发时记得自己当初为啥设的。

| 你的策略 | 给 bot 发 |
|---|---|
| 建 NVDA 3 档入场 | `NVDA 3 档入场: $1100 tier1, $980 tier2, $850 tier3`（创 3 个 alert）|
| 看 capitulation 抄底 | `AMD 从现在跌 25% 通知我，capitulation 抄底` |
| Covered call 预警 | `ORCL 接近 $210，我有 calls 到期那个价` |
| 除权前买入 | `GLW 除权前回调到 $150` |
| 财报反应 | `AMD 单日跌 12% 通知我，财报 disaster 抄底` |
| 宏观转折 | `SPY 跌破 200DMA 通知我，regime shift 信号` |

Note 跟着 alert 走，触发通知里能看到，你记得当初的策略。

---

## 🗂️ 管理命令

| 给 bot 发 | 结果 |
|---|---|
| `列出我的 alerts` | Bot 显示当前 active alerts 表 |
| `所有 alerts 包括已触发` | 包含 fired/触发历史 |
| `取消 GLW` | 取消所有 GLW alerts |
| `取消 $190 那个 ORCL` | Bot 按描述识别特定 alert |
| `清空全部` | Bot 问确认，然后全清 |
| `重新激活那个触发过的 NVDA alert` | 重新启用已触发的 alert |

---

## 🌐 中英文混说

Bot 能自然处理一句话里中英混。

| 给 bot 发 | Bot 创建啥 |
|---|---|
| `set GLW alert at $140 加仓信号` | GLW ≤ $140, note: "加仓信号" |
| `AMD 跌 10% 通知我, this is a buying chance` | AMD drop 10%, note: "buying chance" |
| `NVDA 突破 200DMA, regime shift alert` | NVDA ≥ 200DMA, note: "regime shift" |

---

## 🎁 方便的小技巧

### 看哪个 alert 快要触发了

```
哪些 alerts 离触发最近？
```

Bot 拉当前价格，按距离触发的远近排序。

### 一次批量从 watchlist 设

```
帮我设 AI 半导体的 alerts: NVDA $1000, AMD $280, SMCI $30, MU $450
```

Bot 一次创 4 个 alerts。

### 带 note 批量

```
GLW $140 tier1, $120 tier2, $100 tier3, 都标 'AI glass'
```

3 个 alerts，都带 "AI glass" note。

---

## ❌ Bot **不会**做的事

Bot 范围**只管 alerts**。这些事用 **Claude Code** 直接问：

| ❌ Bot 不答 | ✅ 用 Claude Code 问 |
|---|---|
| "NVDA 现在多少钱?" | `分析 NVDA` |
| "ORCL 能买吗?" | `ORCL 怎么样?` |
| "宏观环境如何?" | `宏观警报` / `regime check` |
| "组合该怎么对冲?" | `审一下我的组合` |
| "找便宜的 AI 标的" | `找未爆发的 AI 股` |

Bot 的活: **加 / 列 / 取消 alerts**。Claude Code 的活: **研究 + 分析**。

如果你问 bot 超出范围的事，它会礼貌地告诉你 + 建议用 Claude Code。

---

## 🚀 进阶: 用 Claude Code 组合复杂 macro 逻辑

复杂的多条件 setup 用 **Claude Code（不是 bot）** 搭。例如：

```
你 (在 Claude Code 里说): 
当前宏观 ORANGE，给我组合设几个防御 alerts:
  - AI/Semi 持仓全部: 如果 SMH 单日跌 8% 通知我
  - GLW / ONTO / LRCX: 各自 -25% 回调通知
  - VIX > 25 通知我（需要把 VIX 加成监控标的）
  - AI Power 持仓 (VST, CEG): 跌破 200DMA 通知我
```

Claude Code 读你组合、查当前价、算 strike levels、跑 add_alert.py 批量创建。然后 commit + push。

之后 Telegram bot 就是你的**只读推送通道** + 偶尔管理。

---

## 💡 未来能力（暂不支持）

如果你想要这些，open issue 给 dev：

- RSI 超买超卖（RSI > 70 / RSI < 30）
- MACD 信号交叉
- Bollinger 带突破
- 成交量爆量（>2× 20 日均量）
- 死叉 / 金叉（50DMA 穿 200DMA）
- 财报/事件相对日期 alert
- 板块/指数关联（SPY 涨了但 ORCL 没动 → 通知）
- 多条件复合（A AND B，不仅 OR）

这些需要历史价数据 + 更复杂状态，但都能做。在 GitHub repo 开 issue。
