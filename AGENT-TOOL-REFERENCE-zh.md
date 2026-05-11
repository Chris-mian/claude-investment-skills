# Agent Tool Reference — 自然语言 → CLI 调用规范

[English Version](./AGENT-TOOL-REFERENCE.md)

**适用对象**：任何需要把用户语言转化为精确工具调用的 AI agent（Claude Code、自定义 agent、CLI 包装器、定时任务调度器等）。

**目标**：每个工具都给出 (1) 中英双语触发短语、(2) 准确的命令模板、(3) 参数说明、(4) 示例映射。新增语言时，先映射到标准英文意图，然后复用同一套模板。

**被以下文件加载**：`INVESTMENT-WORKFLOW.md`、`README.md`、`README-zh.md`。在生成任何工具调用之前，请先读本文件。

---

## 路径解析模式（先读这一段，本文档所有命令都套用此模式）

本文件里所有命令都用这个模板找工具集的 install root：

```bash
$(ls ~/.claude/{skills,plugins/claude-investment-skills}/PATH/TO/SCRIPT.py 2>/dev/null | head -1)
```

这个 `$(ls ...)` 表达式在**两种安装方式**下都能正确解析：

- **Git-clone 装的**：`~/.claude/skills/...` 存在 → 走这条
- **Plugin 装的**：`~/.claude/plugins/claude-investment-skills/...` 存在 → 走这条

`{skills,plugins/claude-investment-skills}` 的花括号展开成两个候选路径；`ls` 列出存在的那个（不存在的报错被 `2>/dev/null` 屏蔽）；`head -1` 取一个匹配。**罕见情况**两种 install 都存在时，`ls` 按字母排序 → `plugins/...` 胜出 —— 不要紧，两边文件内容一样。**正常用法都是单 install，谁先谁后无所谓。**

把整个模板原样粘到 bash 调用里，Claude Code 会正确 expand。**不要去掉 `$(ls ...)` 那层包装** —— 它就是让同一条命令在两种安装路径下都跑得通的关键。

---

## 解析算法（每条用户输入都按此处理）

```
1. 解析用户输入 → 识别意图（单股查询 / cluster 扫描 / max pain / ……）
2. 提取实体（ticker、天数、美元阈值等）
3. 在下方分工具章节查找标准命令模板
4. 把实体代入模板
5. 如果有歧义，优先采用 "Defaults" 中记录的默认值，而不是反问用户
6. 执行命令，解析 JSON 输出，用用户的语言组织回复
```

如果用户输入既不是英文也不是中文，先在心里翻译成标准英文意图，再查表。

---

## 快速查表

| 标准英文意图 | 双语触发词 | 工具 |
|---|---|---|
| **Daily macro warning / pullback radar** | EN: "macro warning / regime check / is the market at peak / should I take profits" · CN: "宏观警报 / 市场是不是顶了 / 该不该减仓 / regime 怎么样" | **`macro-warning` skill (batch-friendly)** |
| Check insider activity for stock(s) | EN: "insider check / insider trading on X / who's buying X" · CN: "X 内部交易 / X 高管买卖 / X insider 怎么样" | `insider_ratio.py` |
| Hunt market-wide cluster buys | EN: "find cluster buys / who are insiders buying / where's smart money" · CN: "找 cluster buy / 内部人在买什么 / 最近高管买入" | `cluster_buy_scan.py` |
| Live quotes + moving averages | EN: "quote X / price of X / where is X trading" · CN: "X 现在多少 / X 报价 / X 价格" | `quote_pull.py` |
| Option walls / OI clusters | EN: "option walls X / where will X pin / gamma map X" · CN: "X 期权墙 / X 期权磁吸位" | `option_walls.py` |
| Max pain calculation | EN: "max pain X / pin level X" · CN: "X 的 max pain / X OPEX 目标" | `max_pain.py` |

---

## 工具 1：`insider_ratio.py` — 单只 / 多只股票的内部交易检查

### 触发短语（自然语言）

**English**: "insider trading on X", "is X being bought by insiders", "who's buying X", "check insider activity for X", "insider ratio X", "X insider check", "are insiders selling X", "form 4 on X"

**Chinese**: "X 内部交易", "X 高管在卖吗", "X insider 怎么样", "X 高管买卖", "查一下 X 的 insider", "X 这只股的高管动作", "最近 X 高管有买入吗"

**多 ticker 触发**："insider check on X, Y, Z" / "扫一下 X Y Z 的高管"

### 标准命令

```bash
uv run --with yfinance python $(ls ~/.claude/{skills,plugins/claude-investment-skills}/review-investment-screenshot/scripts/insider_ratio.py 2>/dev/null | head -1) "TICKER1,TICKER2,..." [flags]
```

### 参数说明

| Flag | 类型 | 默认 | 何时覆盖 |
|---|---|---|---|
| (positional) | comma-separated tickers | required | 始终大写，逗号分隔，不要带空格 |
| `--window N` | days | `90` | 用户说 "last month" → 30；"last week" → 7；"last quarter" → 90；"last year" → 365 |
| `--since YYYY-MM-DD` | date | derived from --window | 当用户给出明确起始日期时（例如 "since the crash on April 8"） |
| `--source openinsider` | source | `openinsider` (default) | 除非用户明确要求，否则保持默认 |
| `--source yfinance` | source | — | 仅在 openinsider 不可用时使用 |
| `--source both` | source | — | 高风险决策 / 用户说 "cross-verify" / "double check" 时 |
| `--min-buy-size N` | dollars | `25000` | 用户说 "include all buys" → 0；"only big buys" → 100000；"conviction only" → 250000 |

### 输出 schema（JSON，每个 ticker 一条）

```
{
  TICKER: {
    name, last, fwd_pe, target, fiftyTwoWeekHigh,
    om_buy_count, om_sell_count,
    om_buy_total_$, om_sell_total_$,
    buy_buckets_$:  {0-30d, 30-90d, 90-180d, >180d},
    sell_buckets_$: {0-30d, 30-90d, 90-180d, >180d},
    recent_90d_buy_$, recent_90d_sell_$,
    all_recent_buyers, meaningful_recent_buyers,
    meaningful_buy_total_$, micro_buy_total_$,
    buy_to_sell_ratio,
    verdict,                       # ALWAYS read this first
    top_buys,                      # sorted by VALUE desc
    top_meaningful_buys,           # ≥min-buy-size only
    top_sells
  }
}
```

### Verdict 等级（如何向用户传达）

| Verdict 字符串 | 含义 | 给用户的总结 |
|---|---|---|
| `RECENT CLUSTER BUY ✅✅✅` | 3+ insiders ≥$25K each, $500K+ aggregate | "强 cluster buy 信号 — 多位高管联手买入" |
| `RECENT STRONG BUY ✅✅` | meaningful buy ≥ 2× recent sell | "强买入信号" |
| `RECENT BUY-LEAN ✅` | meaningful buy ≥ recent sell | "略偏买入" |
| `MICRO-BUYS ONLY` | all buys <$25K | "只有 ESPP / 自动微买 — 信号弱" |
| `RECENT HEAVY DISTRIBUTION 🔴` | buy < 10% of sell | "明显减持" |
| `RECENT INSIDERS-ONLY-SELLING 🔴` | 0 buys, sells exist | "高管纯卖出 — 去 secform4.com 核实是否 10b5-1" |
| `OLD SELLS ONLY` | no recent activity, old sells | "中性 — 大概率是早先的 10b5-1" |
| `NO ACTIVITY (in window)` | nothing in window | "时间窗内没有内部交易" |
| `MIXED` | other | "信号混合" |

### 常见匹配模式

| 用户说 | → 命令 |
|---|---|
| "Insider check on NVDA" | `insider_ratio.py "NVDA" --window 90` |
| "扫一下 NVDA, AMD, AVGO 的内部交易" | `insider_ratio.py "NVDA,AMD,AVGO" --window 90` |
| "TSM 最近高管在买吗，深度看一下" | `insider_ratio.py "TSM" --window 90 --source both` |
| "Are insiders buying CRM, only conviction-level" | `insider_ratio.py "CRM" --window 90 --min-buy-size 100000` |
| "Show me ALL insider activity at TSM, even small" | `insider_ratio.py "TSM" --window 90 --min-buy-size 0` |
| "Insider check on PLTR since Feb 1" | `insider_ratio.py "PLTR" --since 2026-02-01` |
| "1 year of insider history for AMKR" | `insider_ratio.py "AMKR" --window 365` |

---

## 工具 2：`cluster_buy_scan.py` — 全市场 cluster 买入扫描

### 触发短语（自然语言）

**English**: "find cluster buys", "where are insiders buying", "smart money is loading up where", "cluster buy scan", "find next MRVL setup", "weekly insider buy scan", "any cluster buys recently", "show me clusters this month"

**Chinese**: "找 cluster buy", "内部人在买什么", "最近哪些股票被高管买入", "扫一下市场 cluster buy", "找下一个 MRVL", "高管集中买入扫描", "这个月有哪些 cluster"

### 标准命令

```bash
uv run --with yfinance python $(ls ~/.claude/{skills,plugins/claude-investment-skills}/review-investment-screenshot/scripts/cluster_buy_scan.py 2>/dev/null | head -1) [flags]
```

### 参数说明

| Flag | 类型 | 默认 | 何时覆盖 |
|---|---|---|---|
| `--days N` | days | `30` | "this week" → 7；"this quarter" → 90；"this year" → 365 |
| `--min-value N` | dollars | `250000` | 用户要更严格（"only big clusters"）→ 1000000；要更宽松（"include small caps"）→ 100000 |
| `--min-insiders N` | count | `2` | "true cluster only" → 3；"any 2+ buying" → 2（默认） |
| `--detail` | flag | off | 用户希望看到逐个 insider 的明细（"show me who specifically is buying"）时加上。会增加额外的 HTTP 请求。 |
| `--enrich` | flag | off | 用户需要价格 / PE / 52 周高点上下文时加上。分析类问题默认 ON，列表类问题默认 OFF。 |
| `--senior-only` | flag | off | 用户说 "only CEO/CFO/Chair clusters" / "high-conviction only" / "顶级管理层 cluster" 时加上。会强制启用 --detail。 |

### 输出 schema

```
{
  params: {...},
  n_clusters: int,
  clusters: [
    {
      ticker, company, industry,
      n_insiders, total_buy_$,
      trade_date, filing_date,
      price, qty,
      // if --detail:
      buyers: [{date, insider, title, value, is_senior}],
      senior_buyer_count: int,
      // if --enrich:
      price_now, fwd_pe, fiftyTwoWeekHigh, mcap, target, pct_off_52wHigh
    }
  ]
}
```

### 常见匹配模式

| 用户说 | → 命令 |
|---|---|
| "Find cluster buys this month" | `cluster_buy_scan.py --days 30 --min-value 250000 --min-insiders 2 --enrich` |
| "Show me only the high-conviction clusters" | `cluster_buy_scan.py --days 30 --min-value 1000000 --min-insiders 3 --senior-only --enrich` |
| "Quick cluster scan, no detail" | `cluster_buy_scan.py --days 30 --min-value 500000 --min-insiders 3` |
| "Who are the senior insiders buying right now" | `cluster_buy_scan.py --days 30 --min-value 250000 --min-insiders 2 --senior-only --enrich` |
| "本周有什么 cluster buy" | `cluster_buy_scan.py --days 7 --min-value 250000 --min-insiders 2 --enrich` |
| "AI 板块有 cluster buy 吗" | 先跑全市场扫描，再按 industry 包含 "Semiconductor" / "Computer" / "Software" 过滤。工具本身不按行业过滤 —— 由 agent 在结果端二次过滤。 |

### 性能提示

`--detail` 和 `--senior-only` 会触发 N+1 次 HTTP 请求（每个 ticker 一次）。30 个 cluster 可能耗时 30–60 秒。除非用户明确要看 insider 明细，否则默认关闭。

---

## 工具 3：`quote_pull.py` — 批量行情 + 均线

### 触发短语

**English**: "current price of X", "quote X", "where is X trading", "X stock price now", "pull quotes for X, Y, Z", "live price"

**Chinese**: "X 现在多少", "X 报价", "X 价格", "X 现价", "拉一下 X Y Z 的价格"

### 标准命令

```bash
uv run --with yfinance python $(ls ~/.claude/{skills,plugins/claude-investment-skills}/review-investment-screenshot/scripts/quote_pull.py 2>/dev/null | head -1) "TICKER1,TICKER2,..."
```

### 参数说明

只需逗号分隔的 tickers，无 flag。始终大写。

### 常见匹配模式

| 用户说 | → 命令 |
|---|---|
| "Quote NVDA" | `quote_pull.py "NVDA"` |
| "Pull MSFT, AAPL, GOOGL" | `quote_pull.py "MSFT,AAPL,GOOGL"` |
| "AMD AVGO MRVL 现价" | `quote_pull.py "AMD,AVGO,MRVL"` |

---

## 工具 4：`option_walls.py` — 持仓量集群

### 触发短语

**English**: "option walls for X", "OI clusters X", "where will X pin this week", "gamma map X", "support and resistance options X", "key strikes X"

**Chinese**: "X 期权墙", "X 主要 strike", "X 这周走哪里", "X 期权磁吸位", "X 关键 strike"

### 标准命令

```bash
uv run --with yfinance python $(ls ~/.claude/{skills,plugins/claude-investment-skills}/review-investment-screenshot/scripts/option_walls.py 2>/dev/null | head -1) TICKER [n_expiries]
```

### 参数说明

| 位置 | 类型 | 默认 | 何时覆盖 |
|---|---|---|---|
| 1 | ticker | required | 单个 ticker，大写 |
| 2 | int | typically 4 | 用户说 "look out months" / "next 6 expirations" 时调大 |

---

## 工具 5：`max_pain.py` — max pain 计算

### 触发短语

**English**: "max pain X", "X max pain", "pin level X", "where will X close OPEX"

**Chinese**: "X 的 max pain", "X OPEX 目标", "X 收盘锚点"

### 标准命令

```bash
uv run --with yfinance python $(ls ~/.claude/{skills,plugins/claude-investment-skills}/review-investment-screenshot/scripts/max_pain.py 2>/dev/null | head -1) TICKER [n_expiries]
```

---

## Skill：`macro-warning` — 每日 8 层回调风险雷达

### 触发短语（自然语言）

**English**: "macro warning", "macro check", "regime check", "is the market at peak", "should I take profits", "is it time to buy", "pullback risk", "market top", "daily macro radar"

**Chinese**: "宏观警报", "宏观检查", "regime 怎么样", "市场是不是顶了", "该不该减仓", "现在能不能加仓", "市场风险大不大", "顶部信号"

### 标准调用方式

这是一个 **skill**，不是 CLI 脚本。调用方式：
- Slash 命令：`/macro-warning`
- 或者指示 agent："Run the macro-warning skill"
- 或者通过 `/schedule` 做定时批量执行

### 它做什么

8 层综合打分（0–16）并输出 regime 标签：
1. 估值（NDX P/E >38、SPX P/E、Shiller CAPE、Buffett Indicator）
2. 波动率（VIX、MOVE、VVIX、VIX/VVIX 比值）
3. 情绪（CNN F&G、AAII、NAAIM、P/C ratio）
4. 信用（HY OAS、IG OAS、收益率曲线、30Y）
5. 货币（DXY、USD/JPY、BOJ pricing）
6. 市场宽度（200DMA 上方占比、A/D、新高新低、McClellan）
7. CTA / vol-target 仓位
8. 板块轮动倾向（XLU/XLK、防御 vs 周期）

强制规则：NDX P/E >38 或 VIX <14 或 F&G >85 任一触发 → 自动至少 YELLOW。

### 输出

单一 regime 标签（🟢 GREEN / 🟡 YELLOW / 🟠 ORANGE / 🔴 RED）+ 8 层细分表 + 与昨日的差异 + 具体仓位调整建议 + 板块倾向 + 催化剂关注清单。

### 推荐排程

盘前预警（美东 8 点，工作日）：
```bash
# Via /schedule skill
cron: "0 12 * * 1-5"   # 8am ET = 12 UTC
prompt: "Run macro-warning skill. If regime flipped or NDX PE crossed 38, emphasize the change."
```

收盘后总结（美东 5 点，工作日）：
```bash
cron: "0 21 * * 1-5"
```

### 常见模式

| 用户说 | → 动作 |
|---|---|
| "Run macro warning" | 完整跑一次 8 层扫描，输出报告 |
| "Is the market at top?" | 同上，开头优先讲估值 + 情绪两层 |
| "Should I add now?" | 同上，但开头先给 action items（add/hold/trim） |
| "宏观警报" | 同上，用中文输出 |
| "Set up daily macro alert" | 用 /schedule 创建上面提到的 cron |

### 记忆集成

每次跑完，skill 会把日期 + regime + 关键指标写入 `~/.claude/projects/-Volumes-workplace-invest/memory/macro_history.jsonl`。这样后续运行就可以计算差值（"VIX 连涨 3 天"、"NDX PE 今日突破 38"）。

---

## 多工具组合模式

复杂请求需要串联多个工具。示例：

### "Should I buy X?"（单股完整分析）

并行运行：
```bash
insider_ratio.py "X" --window 90 &
quote_pull.py "X" &
option_walls.py X 4 &
wait
```
然后调用 `analyze-stock` skill 进行汇总。

### "Find me cluster buys + verify each one"

```bash
# Step 1: discover
cluster_buy_scan.py --days 30 --min-value 500000 --min-insiders 3 --enrich
# Step 2: for each ticker found, verify
insider_ratio.py "TICKER1,TICKER2,..." --window 90 --source both
```

### "AI sector cluster scan"

```bash
# Step 1: market-wide
cluster_buy_scan.py --days 30 --min-value 250000 --min-insiders 2 --enrich
# Step 2: agent post-filters results by industry contains:
# "Semiconductors" / "Computer" / "Software" / "Internet" / "Electronic"
# Step 3: deep-verify the AI subset
insider_ratio.py "FILTERED_TICKERS" --window 90
```

### "Pre-earnings prep on X"

调用 `earnings-prep` skill，它内部会执行：
```bash
insider_ratio.py "X" --window 60 &     # 60d to catch pre-earnings activity
option_walls.py X 4 &                  # near-term pin levels
quote_pull.py "X" &                    # current price + MAs
wait
# Then WebSearch for consensus + implied move
```

---

## 双语实体抽取规则

| 用户输入中的实体 | 抽取方式 |
|---|---|
| Ticker symbol | 1–5 个大写字母（有时带 $ 前缀）。例：NVDA、$NVDA、BRK.B |
| 天数 / 时间窗 | "last week"=7, "last month"=30, "last quarter"=90, "this year"=365, "上周"=7, "上个月"=30, "最近三个月"=90 |
| 美元阈值 | "big"="conviction"="significant" → 100000+；"small"="any" → 25000；"only large"="serious" → 1000000 |
| 高管过滤 | 提到 "CEO" / "CFO" / "founder" / "chairman" → 设置 --senior-only；提到 "高管" / "创始人" / "董事长" → --senior-only |

---

## 环境前提

所有脚本都假设 `/tmp/.insider_venv` 已存在并装好 yfinance + pandas + numpy。如果是全新环境：

```bash
bash ~/.claude/skills/setup.sh
```

如果脚本报 `ModuleNotFoundError`，重新跑一次 setup。如果 openinsider 网络不可达，`insider_ratio.py` 会自动回退到 yfinance，并在输出里加一个字段 `"fallback": "used yfinance (openinsider unreachable)"`。

---

## 新增工具的方法

新增脚本时，按同样的模板追加到本文件：
1. Triggers（EN + CN）
2. Canonical command
3. Parameters table
4. Output schema
5. Common pattern mappings

触发短语优先动词起首（"find / check / scan / hunt / show"），而不是名词起首 —— 这样从用户语言中识别意图更容易。
