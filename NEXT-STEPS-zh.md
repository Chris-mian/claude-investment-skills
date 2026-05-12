# Next Steps —— 路线图 & 已知限制

本文件记录计划中的功能、已知边界、刻意的设计取舍。问"这个工具能做 X 吗"时来这里看。

[English version](./NEXT-STEPS.md)

---

## 当前已支持（v1.6）

### Alert 条件类型

| Op | 触发 | 例句 | 状态 |
|---|---|---|---|
| `below` | price ≤ 阈值 | "GLW 跌到 140 通知我" | ✅ |
| `above` | price ≥ 阈值 | "AAPL 涨到 250 提醒" | ✅ |
| `drop` | -% 从 anchor 价格（创建时锁定） | "NVDA 跌 10% 通知我" | ✅ |
| `rise` | +% 从 anchor | "SPY 涨 5%" | ✅ |
| `drop_intraday` | 单日 -% vs 前收，含盘前盘后 | "AMD 单日跌 5%" | ✅ |
| `rise_intraday` | 单日 +% vs 前收 | "TSLA 单日涨 7%" | ✅ |
| `below_ma_50` | price ≤ 50 日 **SMA** | "VST 跌破 50DMA" | ✅ |
| `above_ma_50` | price ≥ 50 日 SMA | "NVDA 突破 50DMA" | ✅ |
| `below_ma_200` | price ≤ 200 日 SMA | "SPY 跌破 200DMA" | ✅ |
| `above_ma_200` | price ≥ 200 日 SMA | "META 突破 200DMA" | ✅ |
| `below_ema_*` / `above_ema_*` | EMA | "X 跌破 50EMA" | ❌ v1.7 |
| `rsi_below_30` / `rsi_above_70` | RSI 阈值 | "X RSI < 30 提醒" | ❌ v1.7 |
| `volume_above_Nx` | 成交量 > N× 20 日均量 | "X 成交放量提醒" | ❌ v1.8 |
| Compound AND | "X < 140 AND VIX > 25" | 目前需要拆成 2 个 alert | ❌ v1.9 |
| Compound OR | "X < 140 OR Y > 200" | 通过 NL 拆解工作（Claude 创建 2 个 alert） | ✅ 通过 NL |

### Chat 路径

- ✅ **GitHub Actions polling**（选项 A，延迟 2-15 分钟）
- ✅ **Cloudflare Workers webhook**（选项 B，延迟 1-3 秒）
- ✅ 中英 NL 解析（EN + CN）通过 Claude Sonnet 4.6 + tool use
- ✅ Alert note 的 UTF-8 round-trip（中文、em-dash、emoji 都行）

### 分析 skills（14 个）

`analyze-stock`、`earnings-prep`、`find-alpha`、`find-untapped-thesis`、`leaps-screen`、`macro-risk-check`、`macro-warning`、`narrative-reversal-screen`、`option-wall-analysis`、`portfolio-audit`、`price-alert`、`review-investment-screenshot`、`sector-rotation-analysis`、`tax-optimize`。全部执行 **macro → stock → entry → sizing → tax** pre-flight 检查清单。

---

## 延迟 / 频率 —— 已知限制

价格扫描跑在 **GitHub Actions cron 每 2 分钟一次**，24/7。意味着：

- Alert 在价格真正穿越阈值后 **0-2 分钟**触发。
- 盘前/盘后行情**会**被捕获 —— yfinance 返回最新报价，包含延长交易时段。
- **不适合 sub-minute 反应**。要 5 秒内对 sweep 单做反应，请用真正的 broker（IBKR mobile、ThinkOrSwim、TradingView）。

### 为什么不能简单地变更快

| 方案 | 费用 | 为什么还没做 |
|---|---|---|
| GH Actions cron 每 1 分钟 | $0 | 技术上 cron 最小 1 分钟，但 GH 高峰时会被合并到 5-15 分钟。不稳定。 |
| Cloudflare Cron Triggers（最小 1 分钟）| $0 | 可行升级；需要把 `check_alerts.py` 移植到 TypeScript。在 v1.7 路线图。 |
| Polygon.io / Alpaca 的 WebSocket | $30-50/月 | 实时。需要重写成持续运行的 worker。在 v2.0 路线图但需要付费数据 tier。 |
| Broker 订单 webhook（IBKR、Tradier）| $0-10/月 | 接 broker 自己的价格流。最准但绑死一家 broker。 |

### 什么时候你真的需要实时

如果你在 sweep 单或 scalp，用 **broker 自带的 alert**。这个工具的 alert 用来做**研究级触发** —— "GLW 回到我 tier-1 入场价时提醒我" —— 2 分钟粒度绰绰有余。

---

## 路线图（按版本）

### v1.7（下一个 minor）

| 功能 | 涉及文件 |
|---|---|
| **EMA 支持** —— `below_ema_9` / `above_ema_9` / `below_ema_20` 等 | `check_alerts.py`（用 `history(period="60d").Close.ewm(span=N).mean()` 计算）、`worker.ts` enum、`chat_handler.py` enum、两处 SYSTEM_PROMPT 更新 |
| **可配置 SMA 周期** —— `below_ma_X` 任意 X（不止 50 / 200）| 同上；50DMA / 200DMA 当特例处理 |
| **RSI 阈值** —— `rsi_below_30`、`rsi_above_70`、`rsi_above_X` | 新 op type；14 日 RSI 计算用 `pandas-ta` 或手写 |
| **Cloudflare Cron Triggers** 价格扫描选项 | 可选 `worker-scan.ts` 跑在 1 分钟 CF cron 上；用户选 GH Actions 或 CF |
| Alert 消息格式优化（markdown 图表链接）| `check_alerts.py` Telegram message builder |

### v1.8

| 功能 | 说明 |
|---|---|
| **成交量 spike alert** —— `volume_above_Nx_20d` | 新闻驱动行情探测 |
| **Bollinger 带触发** —— `below_bb_lower`、`above_bb_upper` | 波动率感知的均值回归 |
| **Slack webhook channel** | 很多人有个人 Slack；简单的 `--notify slack` flag |
| **Discord webhook channel** | 同 Slack |
| **`tax-loss-harvest-screen` skill** | 扫描组合找 Q4 wash-sale aware 的卖损候选 |

### v1.9

| 功能 | 说明 |
|---|---|
| **Multi-condition AND alert** —— 例如"X below 140 AND VIX > 25"| Schema 改：condition 从 leaf 变 tree |
| **邮件 digest 模式** —— 每日 / 每周触发的 alert 摘要 | `--notify email` channel + SES 集成 |
| **Alert 生命周期状态** —— `paused`、`expired`、`archived`（除了 `active`/`fired`）| Schema + chat handler UI |
| **`dividend-capture` skill** | Ex-div 机会扫描器 |
| **`options-flow-monitor` skill** | 异动期权活动 alert |

### v2.0（major）

| 功能 | 说明 |
|---|---|
| **外汇** —— `USD/JPY`、`EUR/USD`、`GBP/USD` 等 | yfinance 用 `JPY=X` 这种 symbol 支持；对 carry trade 信号有用 |
| **加密货币** —— BTC、ETH、关键位 | yfinance 有 `BTC-USD` 等 |
| **国际股票** —— 日股（TYO）、港股（HKG）| yfinance 有 Tokyo + HK feeds |
| **可选 Polygon.io / Alpaca WebSocket** 实时价格流 | 付费 tier；持续 worker；opt-in |
| **`relative-strength-rank` skill** | 每周扫 watchlist 的 RS ranking |

---

## 这个工具**不计划**变成什么

- ❌ 下单的交易 bot
- ❌ 信号生成的回测引擎
- ❌ 组合记账工具（追踪 P&L、生成报税表）
- ❌ 研究协作 / 社交平台
- ❌ 实时 tick-by-tick 流式基础设施
- ❌ Market-making / 套利系统
- ❌ B2B SaaS —— 没有 managed-tier 路线图；每个用户都在自己的 GitHub fork + CF 账号上自托管

守住定位：**研究级别的投资思考伙伴**，纪律化方法论，给**个人理财 / 个人 buy-side 投资者**做 swing / position / LEAPS 用。

---

## 贡献

开 issue 时打版本 label（`v1.7`、`v1.8` 等）+ 类型 label（`feature`、`data-source`、`channel`、`skill`）。

每个新 condition type 走同一个 pattern：

1. 在 `price-alert/webhook/worker.ts` AND `price-alert/scripts/chat_handler.py` 加 enum 项（两处必须一致 —— 共享同一 NL schema）
2. 在 `price-alert/scripts/check_alerts.py` 加求值逻辑
3. 加 unit test 验证触发 + 消息
4. 更新 `price-alert/EXAMPLES.md` 加中英文示例
5. 更新 `AGENT-TOOL-REFERENCE.md` Tool 6 的 pattern mapping
6. 在 `README.md` Changelog 升版本号

新 skill 按现有 `SKILL.md` pattern 走，`description:` frontmatter 列中英 trigger。如果 skill 做 buy/add/trim 推荐，**必须**注入 Pre-flight checklist（v1.6 更新过的任一 skill 都是模板）。

---

## 版本历史

| 版本 | 日期 | 亮点 |
|---|---|---|
| **2.1** | 2026-05-12 | **`insider-firehose` v2.1：自动 Tier-2 enrichment**。每个 alert 自动附加公司一句话简介、P/E + 市值 + 净现金 + 股息、52W 价格位置（vs 50DMA / 200DMA / 高 / 低）、0-10 Smart Money Score。默认开启；可通过 Telegram `/enrich on` / `/enrich off`（中文别名 `/enrich 开` / `/enrich 关` 也行）、CLI `firehose_cli.py`、GitHub Actions 输入参数、或 `ENRICH` 环境变量切换。Non-fatal —— yfinance 失败时自动 fallback 到 v2.0 基础格式。worker 加 fast-path 跳过 Claude（节省 token + 延迟）。 |
| **2.0** | 2026-05-11 | **新 skill：`insider-firehose`** —— 实时 SEC EDGAR Form 4 监控 + Telegram 推送 officer/director ≥ $200k 公开市场买入。30 分钟一次 cron，仅工作日。延迟 2-5 分钟 vs openinsider 的 12-24 小时。 |
| 1.7 | 2026-05-11 | 插件市场安装路径（与 git-clone 二选一，两个都支持）。47 个 SKILL.md 重写为 dual-mode 脚本路径解析。NEXT-STEPS 路线图 + "Who this is for / not for" 定位 + state-source 可观测性。 |
| **1.6** | 2026-05-11 | Cloudflare Worker webhook（1-3 秒 chat 延迟）、AGENTS.md setup 编排指南、预渲染 Mermaid 图（SVG/PNG）、6 个 skill 注入 pre-flight 方法论、AGENT-TOOL-REFERENCE.md 扩展 Tool 6 + Skill Catalog |
| 1.5 | 2026-05-10 | 首次公开发布、MIT LICENSE、INTRODUCTION.md、双语翻译、"NL 怎么触发 skill"章节、5 个对话示例 |
| 1.4 | 2026-05-09 | macro-warning 真实数据后端（`macro_pull.py`）、ARCHITECTURE.md |
| 1.3 | 2026-05-08 | `macro-warning` skill（8 层 pullback radar）、cron-friendly、memory 集成 |
| 1.2 | 2026-05-05 | AGENT-TOOL-REFERENCE.md 初版 —— NL → CLI 契约 |
| 1.1 | 2026-05-05 | insider_ratio.py v3（openinsider 优先、Form 4 code-aware）、cluster_buy_scan.py |
| 1.0 | 2026-05-04 | 初始发布 |
