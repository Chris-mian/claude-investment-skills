# 投资 Skills — 精简工作流

[English Version](./INVESTMENT-WORKFLOW.md)

**Version 1.2** | 创建于 2026-05-04，最后调优 2026-05-06

这是投资分析 skill 系统的主索引。所有 skill 协同工作 —— 根据问题选择合适的那个。

## 🤖 如果你是 AI agent

**先阅读 [`AGENT-TOOL-REFERENCE.md`](./AGENT-TOOL-REFERENCE.md)** —— 它包含每个脚本的自然语言 → CLI 映射（中英双语），含参数说明和示例话术翻译。任何时候需要从用户表述调起工具，都查这份文档。

本文件（`INVESTMENT-WORKFLOW.md`）告诉你 *哪个 skill* 适合某个问题。`AGENT-TOOL-REFERENCE.md` 告诉你 *具体如何调用其工具*。

## 🎯 决策树

```
用户问题 → 用哪个 skill？

"分析 X" / "X 能买吗？" / "深度看一下 X"
   → analyze-stock（10 步主框架）

"找下一个 NOK" / "[主题] 里有什么未爆发的"
   → find-untapped-thesis

"X 财报前要不要拿着？"
"X 明天出财报，怎么办？"
   → earnings-prep

"X 买什么 LEAPS？" / "现货还是 LEAPS？"
   → leaps-screen

"max pain 在哪？" / "期权墙？"
"X 这周走哪里？"
   → option-wall-analysis

"宏观看着不稳 / regime 检查"
   → macro-risk-check（新闻驱动）
   → macro-warning（量化、批处理友好、8 层）

"X 现在卖还是等税务？"
   → tax-optimize

"看一下我的截图 / 组合"
   → review-investment-screenshot

"找 swing/position/LEAPS 机会"
   → find-alpha（已有）
```

## 📚 Skills 全栈

### Tier 1 — 单股分析
| Skill | 用例 | 输入 |
|---|---|---|
| `analyze-stock` | 主 10 步深度分析 | Ticker |
| `earnings-prep` | 财报前决策 | Ticker + 持仓 |
| `leaps-screen` | LEAPS 选择 | Ticker + thesis |
| `option-wall-analysis` | 短期价位 | Ticker |

### Tier 2 — 多股发掘
| Skill | 用例 | 输入 |
|---|---|---|
| `find-untapped-thesis` | NOK 风格筛选 | 主题 |
| `find-alpha` | 基于时间维度的 alpha | （自动） |

### Tier 3 — 组合操作
| Skill | 用例 | 输入 |
|---|---|---|
| `review-investment-screenshot` | 完整组合审计 | 截图 |
| `tax-optimize` | 考虑税务的减仓 | 持仓 + 买入日期 |
| `macro-risk-check` | Regime 解读 | （无） |

### Tier 4 — 自动化
| Skill | 用例 | 输入 |
|---|---|---|
| `schedule` | 周期性 agents | 时间 + 内容 |
| `loop` | 迭代任务 | Prompt |

## 🔥 主工作流（标准单股分析）

当用户给你一个 ticker 并问 "X 怎么样" 时：

```
Step 1: 先跑 macro-risk-check
   → 如果 RED：入场要非常保守
   → 如果 GREEN：继续

Step 2: 跑 analyze-stock（10 步）
   → 拿到完整画像

Step 3: 如果用户感兴趣 AND 有期权 thesis：
   → 跑 leaps-screen 做长期布局
   → 跑 option-wall-analysis 看短期价位
   → 如果 30 天内有财报，跑 earnings-prep

Step 4: 如果用户想动手：
   → 计算仓位大小
   → 如果减已有仓位，查 tax-optimize
```

## 🎨 心智模型

```
         宏观背景  ←─ 跑 macro-risk-check
              │
              ▼
        年度主题（2026：K-shape、AI factory、1973 风险）
              │
              ▼
         板块轮动
              │
              ▼
       个股分析  ←─ 跑 analyze-stock
              │
        ┌─────┼─────┐
        ▼     ▼     ▼
     Insider  催化剂  估值
        │     │     │
        ▼     ▼     ▼
       入场计划（3 档）
              │
        ┌─────┼─────┐
        ▼     ▼     ▼
      现货  LEAPS  对冲
              │
              ▼
       税务感知执行  ←─ 跑 tax-optimize
              │
              ▼
        持仓监控
              │
              ▼
       财报前准备  ←─ 跑 earnings-prep（周期性）
```

## 🔧 产业链 / 供需机制（新增）

不同子板块的增长动力差异巨大。在套用通用 AI thesis 之前，永远先识别 **增长模型**：

| 增长模型 | 例子 | 可预测性 | 何时买 |
|---|---|---|---|
| **长周期基础设施** | 电力公用（CEG/EQT/AEP）、管道（ET/WMB）、材料（APD/LIN） | 🟢🟢 最高 | 板块滞涨时 |
| **独立产能** | 内存（MU）、HDD（WDC）、部分半导体 | 🟢 高 | 周期中段 |
| **需求弹性 + 定价权** | GPU（NVDA）、ASIC（AVGO/MRVL） | 🟢 高 | 周期前段 |
| **经常性 SaaS/ARR** | Oracle DB、EDA（CDNS/SNPS） | 🟢🟢 最高 | 估值合理时随时买 |
| **周期性大宗** | 铜、油、DRAM/NAND 周期 | 🟡 中 | 仅在周期底部 |
| **下游产能瓶颈** | 光模块（LITE/FN）、OSAT（AMKR/ASE） | 🔴 低 | 缺料尘埃落定后 |
| **单一客户集中** | Neocloud（CRWV/APLD） | 🔴 低 | 除非极端便宜，否则避开 |

**关键洞察**：同样的 "AI thesis"，盈利轨迹可以差很多。
- 内存搭 AI 顺风车 AND 自有产能扩张 → 业绩可预期超预期
- 光模块搭 AI 顺风车 BUT 受 GPU 排产产能瓶颈 → "缺料" 类失望

**性价比最高的可预测性来自**：
1. AI 电力（CEG/EQT/AEP）—— 锁定 PPA，无业绩意外风险
2. 内存（MU/WDC）—— 已售罄数年，capex 可见
3. 材料（APD/LIN）—— 数十年长约

**使用此矩阵**：跑 `sector-rotation-analysis` 拿到每个子板块机制的完整拆解。

## 🏆 制胜模式（认出这些）

### 模式 1：未爆发 thesis（BUY）
- Forward P/E < 25
- 1Y 涨幅 < 50%
- 真实催化剂（具体合同，不是叙事）
- 机构持股 < 30%
- **Skill**：find-untapped-thesis → analyze-stock

### 模式 2：叙事反转（BUY）
- 股价从 52W 高点回撤 -30% 到 -50%
- 最坏情况已 priced in
- 催化剂依然存在
- 反转信号（50DMA 上穿、首个更高低点、内部人买入）
- **Skill**：narrative-reversal-screen → analyze-stock → leaps-screen

### 模式 3：顶部派发（SELL/AVOID）
- 股价处于 52W 高点
- Insider 100% 卖出（CEO + CFO + Director）
- 1Y > 200%
- 即便业绩超预期 → -10% 到 -20%（priced in）
- **Skill**：review-investment-screenshot → tax-optimize

### 模式 4：超预期但已 priced-in 财报（HEDGE）
- 业绩超预期
- 指引符合预期，无上调
- 财报前 30 天股价已涨 60%+
- Implied move >7%
- **Skill**：earnings-prep（建议用 put 对冲）

### 模式 5：宏观尾部风险（CASH UP）
- USD/JPY < 153（yen carry 开始拆解）
- VIX > 22
- 30Y > 5.10%
- BOJ 加息在即
- **Skill**：macro-risk-check（现金提到 30-40%）

## 🚨 硬规则（永不违反）

1. **永远跑 `insider_ratio.py --window 90`**（openinsider 为主）—— 永远不要相信 yfinance 的汇总
2. **Form 4 代码 "P" 才算买入** —— `A`/`M`/`F` 是 RSU/行权/缴税，不是买入信号（已验证误报：UNH "10 directors" 4/1/2026 实际是 DSU 授予）
3. **任何 "cluster buy" 头条** 在相信前都要去 openinsider.com/[TICKER] 验证 —— 新闻常把薪酬当作信念
4. **对于计划性卖出**，在视为看空信号前先在 secform4.com 查 10b5-1 脚注
5. **加仓前永远先查宏观** —— 即便是好股票，在 red regime 也会失败
6. **仓位上限**：单股最多 10%，高 beta 最多 5%
7. **3 档入场**：永不 "市价买入"，必须有 50DMA / 200DMA 作为后备
8. **具体证据 > 叙事**："AI 好" ≠ thesis
9. **所有来源都要引用**：每个宏观主张都附 WebSearch 链接
10. **税务感知退出**：尤其对高收入者
11. **对冲 > 卖出**：对短期应税持仓而言

## 📅 推荐周期性排程（用 `schedule` skill）

| 频率 | Skill | 时机 |
|---|---|---|
| **每日 8am ET（盘前）** | **`macro-warning`** | **回调 / 顶部风险扫描（NDX PE / VIX / F&G / 8 layer）** |
| 每周一 8am ET | `macro-risk-check` | 盘前 regime 解读 |
| 每周五 4pm ET | `find-untapped-thesis` | 找下一批想法 |
| 每月 1 日 | `review-investment-screenshot` | 完整组合审计 |
| 事件前 | `earnings-prep` | 任何持仓财报前 7 天 |
| Fed/BOJ 前 | `macro-risk-check` | 24 小时前 |
| 季度 | `tax-optimize` | 年底 + 每季度 |

## 🛠 底层工具

### MCP Servers
- `mcp__yfmcp__*` —— yfinance 数据（价格、期权、新闻、信息）
- `WebSearch` —— 宏观事件、新闻、合同
- `WebFetch` —— IR 页面、SEC 文件

### Insider 数据源（按可信度排序）
1. **openinsider.com** —— 主源。Form 4 含交易代码（P/S/A/M/F/G）。免费，免认证。下面两个脚本都用它。
2. **secform4.com** —— 备用。展示 10b5-1 计划脚注披露。
3. **stocktitan.net** —— 易读的 Form 4 叙述。
4. **yfinance** `get_insider_transactions()` —— 仅作 fallback。已知盲区（漏掉 NKE/UNH/PLTR 的真实 cluster buy）。

### 脚本（位于 `~/.claude/skills/review-investment-screenshot/scripts/`）
- **`insider_ratio.py`**（v3）—— 严格的开放市场美元比例。默认 `--window 90`、`--source openinsider`（默认）、`--source both` 用于交叉验证。Form 4 代码感知（仅 `P` 算买入）。
- **`cluster_buy_scan.py`** —— 抓取 openinsider.com/latest-cluster-buys 寻找全市场 MRVL/CEVA 风格的 cluster buy。用 `--days 30 --min-value 500000 --min-insiders 3 --detail --enrich --senior-only`。
- `quote_pull.py` —— 批量实时报价 + 均线
- `option_walls.py` —— 顶部 OI 集群
- `max_pain.py` —— max pain 计算

### Python 环境
- `/tmp/.insider_venv` —— Python 3.9 + yfinance
- 安装：`bash ~/.claude/skills/setup.sh`（一键；安装 yfinance + 验证脚本）

## 📖 年度主题框架

**通用宏观框架**（每年套用 —— 用当年主题填充）：

需要把每只股票对应到的年度主题：
- **K-shape 分化** —— 板块内部，赢家碾压输家；选赢家那一边
- **AI = factory mode** —— 超大规模厂商买算力像工厂买机器（capex >> opex）
- **电力作为瓶颈** —— 哪种投入受供给约束（电力、燃料、材料），就向上重定价
- **需求破坏风险窗口** —— 监控油价/通胀/衰退指标
- **Carry trade 结构** —— 跟踪 JPY 借贷流、BOJ 政策

**每年更新**：日历翻篇时替换为当年具体主题。跟踪：
- 当年 Top 3-5 宏观风险
- Top 3-5 子板块顺风
- 契合每个主题的具体个股

## 🔄 后续改进（TODO）

- [ ] 添加 `narrative-reversal-screen` skill（ORCL 风格）
- [ ] 添加 `sector-rotation-analysis` skill
- [ ] 添加 `portfolio-audit` skill（从 review-screenshot 正式化）
- [ ] 添加 `bond-yield-analysis` 脚本（用于 term premium 跟踪）
- [ ] 添加 `calendar-events.py`（自动拉取未来 30 天事件）
- [ ] 同步到 GitHub repo `claude-investment-skills`
- [ ] 添加 `examples/` 文件夹放真实案例

## 💬 Memory 引用

用户的 memory 系统位于 `/Users/zzizhao/.claude/projects/-Volumes-workplace-invest/memory/`：
- `user_investment_reviews.md` —— review 偏好
- `feedback_insider_methodology.md` —— insider 方法论
- `macro_framework_2026.md` —— 年度宏观主题框架（每年更新）
- `feedback_insider_methodology.md` —— 7 条规则：openinsider 为主、代码感知（仅 P）、10b5-1 意识、近期权重、BUY 稀缺性、新闻头条质疑、yfinance 盲区
- （待添加）`user_position_thesis.md` —— 当前持仓 thesis

## 📜 操作哲学

> "卖早不是最坏结果 —— 错过下一个底才是。"
> —— +20% 锁定的利润可恢复；错过 -25% 的买点不可恢复。

> "握住高信念核心。砍掉杠杆和噪声。"
> —— 永远不要仅因宏观恐惧就完全去风险化一个胜出的长期 thesis。

> "长周期结构性趋势以年为单位，不是季度。"
> —— 不要让一次财报 miss 否定多年 thesis。

> "范式转变不可逆 —— 但估值会在范式内轮动。"
> —— 真正的创新会持续；估值倍数仍会均值回归。

## ✅ 如何使用本文档

1. **首次使用者**：从头读到尾，然后试一个 skill
2. **重复使用者**：直接看 "决策树" 一节即可
3. **分享给朋友**：把这份文档 + skills 文件夹一起发给他们
4. **更新**：新建 skill 时在这里登记，每年更新主题

---

**Built with**: Claude Code —— 自顶向下、宏观感知的投资 skill 系统
