# Architecture — Why we use what we use

Short answer: **direct APIs + Python scripts + 1 MCP (yfinance)**, not a full MCP-based stack.

This document records *why* — so future contributors don't try to "modernize" things that are already optimal for the use case.

---

## TL;DR

| Need | This repo's approach | Alternative (full-MCP) | Winner |
|---|---|---|---|
| Stock prices, options, VIX | **yfmcp** (Yahoo Finance MCP) | Yahoo Finance MCP | **Tied** — same thing |
| Macro data (FRED) | **`requests` → `fredgraph.csv`** in `macro_pull.py` | FRED MCP | **Direct API wins** for our use case |
| Insider Form 4 | **`insider_ratio.py` → openinsider.com** | SEC EDGAR MCP (raw) | **openinsider wins** decisively |
| 10-K / 8-K / S-1 deep reads | **Not yet supported** | SEC EDGAR MCP | EDGAR MCP wins (future addition) |

---

## The full-MCP stack (what we deliberately didn't do)

A common recommendation for AI investment tooling looks like this:

```
- Yahoo Finance MCP   → prices, options, VIX
- FRED MCP            → macro indicators
- SEC EDGAR MCP       → filings + insider Form 4
```

This is a clean mental model and great for **general research**. We adopted only the first.

---

## Why we kept yfinance MCP

It's the same thing. `yfmcp` is exactly the Yahoo Finance MCP this repo's flows assume. No change.

---

## Why we use `requests` + FRED CSV instead of FRED MCP

FRED data is reachable two ways:

| Aspect | FRED MCP | `requests` → `fredgraph.csv?id=...` |
|---|---|---|
| Data accuracy | Identical (same source) | Identical |
| Install overhead | One more MCP server | None |
| Cron / batch friendliness | Needs MCP server alive | ✅ Bare HTTP |
| Discoverability ("which series exists for X?") | ✅ MCP exposes search | ❌ Need to know series ID |
| Latency per query | MCP round-trip | ⚡ Direct |
| Failure modes | MCP startup, MCP version drift | HTTP only |

**Our use case is fixed:** 6 series for daily macro warning (`HY_OAS`, `IG_OAS`, `DGS10`, `DGS30`, `DGS2`, `T10Y2Y`). We don't need ad-hoc exploration. Hard-coding the series IDs in `macro_pull.py` is the simpler, more reliable, more cron-friendly choice.

**One quirk worth documenting** (already handled in code): FRED rejects requests with a Chrome User-Agent. Use the default Python/requests UA — see `pull_fred()` and the `browser=False` flag on `http_get()`.

**When to revisit:** if we add an "ad-hoc macro research" skill where the user might ask "compare unemployment vs housing prices over 30 years" — then FRED MCP earns its keep. Until then, no.

---

## Why `insider_ratio.py` (openinsider) beats SEC EDGAR MCP

This is the most important architectural decision in the repo.

### What SEC EDGAR MCP gives you

Raw Form 4 XML filings. To turn that into "is the CEO actually buying?" you (or the LLM at runtime) must:

1. Identify Form 4 documents among all filings
2. Parse each one's transaction code: `P` (Purchase) / `S` (Sale) / `A` (Award/Grant) / `M` (Exercise) / `F` (Tax withhold) / `G` (Gift)
3. Exclude the non-buy codes (`A`/`M`/`F`/`G`) — every false-positive headline we've seen comes from missing this step
4. Aggregate $ value across multiple filings per ticker
5. Bucket by recency (0-30d / 30-90d / 90-180d / >180d)
6. Distinguish C-suite from directors from 10% holders
7. Read footnotes for 10b5-1 plan disclosures
8. Compute a buy/sell ratio that respects all of the above

### What `insider_ratio.py` does

All of it. openinsider.com already parses EDGAR into a clean schema. `insider_ratio.py` then layers our 8-rule methodology on top:

1. **Default `--window 90`** — recency dominates; old data pollutes signal
2. **Form 4 code "P" only counts as buy** — `A`/`M`/`F`/`G` excluded
3. **`--min-buy-size 25000`** filters ESPP / micro-buy noise (TSM 16-buy false positive case)
4. **Top buys sorted by $ value, not date** — surfaces real conviction (the Ursula Burns / TSM case)
5. **Recency-weighted verdict ladder** — RECENT CLUSTER BUY / STRONG BUY / OLD SELLS ONLY / etc.
6. **Cross-verify 10b5-1 footnotes** at secform4.com before treating sells as bearish
7. **News headlines mislabel RSU/DSU as buys** — verify code = P (UNH "10 directors" / PLTR "Karp 1.47M" cases)
8. **`--senior-only` flag** — filter to C-suite / 10% holders for high-signal subset

**These rules came from real bugs.** The PSTG/TSM/UNH/PLTR/CRDO cases all turned a wrong call into a methodology improvement. Switching to raw EDGAR MCP means starting from scratch on this catalogue and re-discovering each bug at runtime.

### Reproducibility argument

Our rules live in **deterministic Python** (`insider_ratio.py`, `cluster_buy_scan.py`). Same input → same output, every time. Auditable, testable, git-diffable.

If the same logic lived in **LLM prompts on top of EDGAR MCP**, the agent would re-derive the rules every run, with prompt drift, hallucination risk, and no test surface.

---

## What full-MCP would still buy us (future work)

`insider_ratio.py` doesn't cover everything in EDGAR. Things only EDGAR (or EDGAR MCP) can answer:

- 10-K / 10-Q MD&A text reads ("what did NVDA say about supply constraints?")
- 8-K material event tracking ("any 8-K filings for our watchlist this week?")
- S-1 IPO prospectus parsing
- 13D/13G activist position tracking
- Proxy statement comp data

When a skill genuinely needs these, install EDGAR MCP — but as an **addition**, not a replacement for `insider_ratio.py`.

```bash
# Future:
claude mcp add edgar -- npx -y @some/edgar-mcp
```

---

## Decision principles for adding new data sources

When deciding between "MCP" vs "direct API + script", ask:

1. **Is the data set we need from this source fixed and small?** → direct API
2. **Do we need exploratory / ad-hoc queries?** → MCP
3. **Will this run on a cron / batch schedule?** → direct API (one less moving part)
4. **Is there pre-aggregated middleware (like openinsider for EDGAR)?** → use the middleware if it solves your problem
5. **Are we layering custom rules on top?** → put rules in deterministic code (Python), not in LLM prompts

Default tilt: **direct APIs first, MCP only when a use case demands discovery or schema introspection.**

---

## Current data source map (as of v1.4)

| Layer | Indicator | Source | Mechanism |
|---|---|---|---|
| Valuation | Shiller CAPE, SPX trailing PE, Div Yield | `multpl.com` | HTML meta tag scrape |
| Volatility | VIX, MOVE, VVIX | `^VIX`, `^MOVE`, `^VVIX` | yfmcp / yfinance |
| Sentiment | CNN F&G + 1w/1m/1y history | `production.dataviz.cnn.io/index/fearandgreed/graphdata` | unofficial JSON (browser headers) |
| Credit | HY/IG OAS, DGS10/30/2, T10Y2Y | `fred.stlouisfed.org/graph/fredgraph.csv?id=...` | public CSV (default UA) |
| Currency | DXY, USD/JPY | `DX-Y.NYB`, `JPY=X` | yfmcp / yfinance |
| Breadth | % SPX top 50 above 200DMA (proxy) | computed via yfinance | batched API calls |
| Sector | XLK, XLU, XLP, XLY, XLE, XLF, SMH, RSP, IWM | yfmcp / yfinance | per-ticker |
| Insider $ ratio | per-ticker buy/sell with code filtering | openinsider.com | scrape (`insider_ratio.py`) |
| Cluster buys | market-wide recent cluster activity | openinsider.com/latest-cluster-buys | scrape (`cluster_buy_scan.py`) |
| Stock prices, options, news | per-ticker | Yahoo Finance | yfmcp |
| **CTA flow** | — | (no public API) | manual: Goldman PB report |
| **AAII sentiment** | weekly | (no public API) | manual: aaii.com Thursdays |
| **10-K / 8-K / 13D** | — | (not yet supported) | future: EDGAR MCP |

---

## Summary

We chose:
- **yfinance MCP** for tickers (one moving part, well-supported)
- **Direct HTTP APIs** for fixed macro data (less infrastructure, cron-friendly)
- **openinsider scraping** for insiders (because they already did the EDGAR parsing we'd otherwise rebuild)
- **Deterministic Python** for our rules (auditable, testable, git-diffable)

Don't replace `insider_ratio.py` with EDGAR MCP. Don't replace `macro_pull.py`'s FRED logic with FRED MCP. Add EDGAR MCP only when a future skill needs 10-K / 8-K / 13D parsing.
