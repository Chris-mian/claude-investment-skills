# 架构设计 — 我们为什么选择当前的技术栈

[English Version](./ARCHITECTURE.md)

简短回答：**直接调用 API + Python 脚本 + 1 个 MCP（yfinance）**，而不是完整的 MCP 技术栈。

本文档记录的是*为什么这么做* —— 让未来的贡献者不要试图去"现代化"那些其实已经针对当前场景调优好的部分。

---

## TL;DR

| 需求 | 本仓库的方案 | 备选方案（全 MCP） | 胜者 |
|---|---|---|---|
| 股价、期权、VIX | **yfmcp**（Yahoo Finance MCP） | Yahoo Finance MCP | **平局** —— 同一个东西 |
| 宏观数据（FRED） | `macro_pull.py` 中 **`requests` → `fredgraph.csv`** | FRED MCP | 在我们的场景下 **直接 API 胜出** |
| 内部人 Form 4 | **`insider_ratio.py` → openinsider.com** | SEC EDGAR MCP（原始数据） | **openinsider 完胜** |
| 10-K / 8-K / S-1 深度阅读 | **暂不支持** | SEC EDGAR MCP | EDGAR MCP 胜出（未来加入） |

---

## 完整 MCP 技术栈（我们刻意没采用的方案）

针对 AI 投资工具，常见的推荐方案大致长这样：

```
- Yahoo Finance MCP   → 股价、期权、VIX
- FRED MCP            → 宏观指标
- SEC EDGAR MCP       → 财报文件 + 内部人 Form 4
```

这是个干净的心智模型，对**通用型研究**很合适。我们只采用了其中第一个。

---

## 为什么保留 yfinance MCP

它就是同一个东西。`yfmcp` 正好就是本仓库流程所依赖的 Yahoo Finance MCP，无需替换。

---

## 为什么用 `requests` + FRED CSV 而不是 FRED MCP

FRED 数据有两种获取方式：

| 维度 | FRED MCP | `requests` → `fredgraph.csv?id=...` |
|---|---|---|
| 数据准确性 | 一致（同源） | 一致 |
| 安装成本 | 多一个 MCP server | 无 |
| Cron / 批处理友好度 | 需要 MCP server 持续在线 | ✅ 纯 HTTP |
| 可发现性（"X 主题下有哪些 series？"） | ✅ MCP 提供搜索 | ❌ 需要事先知道 series ID |
| 单次查询延迟 | MCP 来回往返 | ⚡ 直连 |
| 故障模式 | MCP 启动失败、MCP 版本漂移 | 仅 HTTP 故障 |

**我们的使用场景是固定的：** 每日宏观警报需要的 6 个 series（`HY_OAS`、`IG_OAS`、`DGS10`、`DGS30`、`DGS2`、`T10Y2Y`）。我们不需要临时探索新指标。把 series ID 硬编码在 `macro_pull.py` 里反而是更简单、更可靠、更适合 cron 的选择。

**有一个值得记录的小坑**（代码里已经处理好了）：FRED 会拒绝带 Chrome User-Agent 的请求。要使用 Python/requests 默认的 UA —— 参见 `pull_fred()` 和 `http_get()` 的 `browser=False` 标记。

**什么时候应该重新评估：** 如果我们将来加一个"宏观自由探索"类的 skill，用户可能会问"对比一下过去 30 年失业率和房价走势"—— 那时 FRED MCP 才有用武之地。在那之前，不必。

---

## 为什么 `insider_ratio.py`（openinsider）胜过 SEC EDGAR MCP

这是本仓库最重要的一个架构决策。

### SEC EDGAR MCP 给你的是什么

原始的 Form 4 XML 文件。要把它转成"CEO 是不是在真买股票？"的结论，你（或者运行时的 LLM）必须做：

1. 在所有文件中识别出 Form 4
2. 解析每一笔交易的 transaction code：`P`（Purchase 买入）/ `S`（Sale 卖出）/ `A`（Award/Grant 授予）/ `M`（Exercise 行权）/ `F`（Tax withhold 缴税扣除）/ `G`（Gift 赠予）
3. 排除非买入类代码（`A`/`M`/`F`/`G`）—— 我们见过的所有"假阳性"新闻头条都是漏掉了这一步
4. 按 ticker 聚合多份文件的总美元金额
5. 按时效性分桶（0-30 天 / 30-90 天 / 90-180 天 / >180 天）
6. 区分 C-suite 高管、董事、10% 股东
7. 阅读脚注以识别 10b5-1 计划披露
8. 综合上述所有规则计算买卖比

### `insider_ratio.py` 做了什么

以上全部。openinsider.com 已经把 EDGAR 解析成了干净的 schema。`insider_ratio.py` 在此之上叠加了我们的 8 条方法论：

1. **默认 `--window 90`** —— 时效性是核心；陈旧数据会污染信号
2. **只有 Form 4 code "P" 才算买入** —— `A`/`M`/`F`/`G` 全部排除
3. **`--min-buy-size 25000`** 过滤掉 ESPP / 微量买入噪音（TSM 16 笔买入假阳性案例）
4. **Top buys 按美元金额排序，而非按日期** —— 让真正的高信念资金浮出水面（Ursula Burns / TSM 案例）
5. **基于时效加权的判定阶梯** —— RECENT CLUSTER BUY / STRONG BUY / OLD SELLS ONLY 等
6. 在把卖出当作看空信号之前，**先到 secform4.com 交叉验证 10b5-1 脚注**
7. **新闻头条会把 RSU/DSU 误标为买入** —— 必须验证 code = P（UNH "10 名董事" / PLTR "Karp 1.47M" 案例）
8. **`--senior-only` 标记** —— 过滤到 C-suite / 10% 股东，得到高信号子集

**这些规则全部来自真实的 bug。** PSTG/TSM/UNH/PLTR/CRDO 几个案例都把一次错误判断转化成了方法论改进。如果改用原始 EDGAR MCP，就意味着要从零开始重建这套规则目录，并在运行时一个一个重新踩坑。

### 可复现性论据

我们的规则活在**确定性的 Python 代码**里（`insider_ratio.py`、`cluster_buy_scan.py`）。同样的输入 → 永远同样的输出。可审计、可测试、git diff 可看。

如果同样的逻辑活在**基于 EDGAR MCP 的 LLM prompt**里，agent 每次运行都要重新推导规则，伴随 prompt 漂移、幻觉风险，且没有测试面。

---

## 完整 MCP 仍然能带给我们的（未来工作）

`insider_ratio.py` 并不能覆盖 EDGAR 的全部内容。下面这些只有 EDGAR（或 EDGAR MCP）能回答：

- 10-K / 10-Q MD&A 文本阅读（"NVDA 在供应受限方面是怎么说的？"）
- 8-K 重大事件追踪（"我们 watchlist 这周有什么 8-K？"）
- S-1 IPO 招股书解析
- 13D/13G 维权投资者持仓追踪
- Proxy statement（委托书）薪酬数据

当某个 skill 真正需要这些时，再装 EDGAR MCP —— 但是作为**新增**，而不是替换 `insider_ratio.py`。

```bash
# 未来:
claude mcp add edgar -- npx -y @some/edgar-mcp
```

---

## 增加新数据源时的决策原则

在"MCP"和"直接 API + 脚本"之间抉择时，问自己：

1. **我们需要从这个数据源拿的数据集是不是固定且小？** → 直接 API
2. **是否需要探索式 / 临时性的查询？** → MCP
3. **是否会跑在 cron / 批处理调度上？** → 直接 API（少一个活动部件）
4. **是否已经有预聚合的中间层（比如 openinsider 之于 EDGAR）？** → 如果能解决问题就用中间层
5. **是否要在数据之上叠加自定义规则？** → 把规则放进确定性代码（Python），不要放进 LLM prompt

默认倾向：**优先直接 API，仅当用例确实需要发现或 schema introspection 时再上 MCP。**

---

## 当前数据源映射（截至 v1.4）

| 层 | 指标 | 数据源 | 机制 |
|---|---|---|---|
| 估值 | Shiller CAPE、SPX trailing PE、股息率 | `multpl.com` | HTML meta tag scrape |
| 波动率 | VIX、MOVE、VVIX | `^VIX`、`^MOVE`、`^VVIX` | yfmcp / yfinance |
| 情绪 | CNN F&G + 1w/1m/1y 历史 | `production.dataviz.cnn.io/index/fearandgreed/graphdata` | 非官方 JSON（browser headers） |
| 信用 | HY/IG OAS、DGS10/30/2、T10Y2Y | `fred.stlouisfed.org/graph/fredgraph.csv?id=...` | 公开 CSV（默认 UA） |
| 汇率 | DXY、USD/JPY | `DX-Y.NYB`、`JPY=X` | yfmcp / yfinance |
| 广度 | SPX top 50 中站上 200DMA 占比（代理指标） | 通过 yfinance 计算 | 批量 API 调用 |
| 板块 | XLK、XLU、XLP、XLY、XLE、XLF、SMH、RSP、IWM | yfmcp / yfinance | 逐 ticker |
| 内部人美元比 | 单 ticker 含 code 过滤的买卖比 | openinsider.com | scrape（`insider_ratio.py`） |
| Cluster buys | 全市场最近的集群买入活动 | openinsider.com/latest-cluster-buys | scrape（`cluster_buy_scan.py`） |
| 股价、期权、新闻 | 单 ticker | Yahoo Finance | yfmcp |
| **CTA 资金流** | — | （无公开 API） | 手动：Goldman PB report |
| **AAII 情绪** | 周度 | （无公开 API） | 手动：aaii.com 周四 |
| **10-K / 8-K / 13D** | — | （暂不支持） | 未来：EDGAR MCP |

---

## 总结

我们选择的是：
- **yfinance MCP** 用于 ticker 数据（一个活动部件，社区维护良好）
- **直接 HTTP API** 用于固定的宏观数据（基础设施更少、cron 友好）
- **openinsider 抓取** 用于内部人交易（因为他们已经做完了我们本来要重建的 EDGAR 解析）
- **确定性 Python** 用于我们的规则（可审计、可测试、git diff 可看）

不要把 `insider_ratio.py` 替换成 EDGAR MCP。不要把 `macro_pull.py` 里的 FRED 逻辑替换成 FRED MCP。只有当未来某个 skill 真正需要 10-K / 8-K / 13D 解析时，才加入 EDGAR MCP。
