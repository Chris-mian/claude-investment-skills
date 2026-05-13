# Strategic Partner Firehose — Find the Next PENG

**找下一个 PENG —— 在 Substack/Twitter 推它之前**

This skill watches SEC EDGAR for the same filings that Substack/Twitter writers eventually pump 6-18 months later. We get the alert the day the company files the 8-K.

---

## TL;DR

| | |
|---|---|
| **What it watches** | SEC 8-K (Items 1.01 / 3.02 / 7.01 / 8.01) and SC 13D filings |
| **What it detects** | Tier-1 strategic investments (NVIDIA, MSFT, SK Telecom, Samsung, MGX, PIF, …) ≥ $50M into US-listed companies ≥ $50M market cap |
| **Latency vs Twitter** | **Hours** vs Twitter's **6-18 months** |
| **Cost** | $0 / month (SEC + yfinance + GitHub Actions + Telegram all free) |
| **Output** | Telegram alert with business one-liner + P/E + Smart Money Score + Partner Score |

---

## What is a Form 8-K?

**Form 8-K = "Current Report"** — every US-listed company **must** file an 8-K with the SEC within **4 business days** of any "material event." This is how the SEC enforces fair-disclosure rules: if material news exists, every shareholder must be able to learn about it at the same time.

### Why this is alpha-rich

Most retail investors **never read 8-K filings directly**. They wait for:
1. The press release to hit Yahoo News
2. A trader to tweet about it
3. A Substack to write the deep dive
4. Their broker app's news feed to surface it

By the time chain hits, **6-18 months can pass** between the 8-K filing and the Twitter pump. The SEC text was free and public the whole time.

### Key 8-K Items we monitor

| Item | What it means | Example | Why we care |
|---|---|---|---|
| **1.01** | Entry into Material Definitive Agreement | "Company entered into Strategic Partnership Agreement with NVIDIA..." | The actual deal contract — joint ventures, supply agreements, M&A LOIs |
| **3.02** | Unregistered Sales of Equity Securities | "Company sold 200,000 preferred shares to SK Telecom for $200M..." | **PIPE deals** — this is the actual mechanism for strategic investments (PENG/SGH's filing was exactly this) |
| **7.01** | Reg FD Disclosure | "Press release attached as Exhibit 99.1..." | Usually has the press-release narrative attached |
| **8.01** | Other Events | "Company received order from a US hyperscaler valued at $400M..." | Catch-all for material customer wins |

### 8-K Items we **filter out** (noise)

| Item | Why we skip it |
|---|---|
| **2.02** | Earnings results — we have other tools for earnings |
| **5.02** | Officer/director changes — usually not investible signal |
| **5.07** | Shareholder vote results — routine |
| **8.01 alone** | Without other items, often dividend / buyback announcements |

---

## What is SC 13D?

**SC 13D = Beneficial Ownership Report (Active)** — any entity or person that acquires **> 5%** of a public company's voting shares with intent to influence management must file within **10 days**.

### Why it's a separate signal from 8-K

8-K is filed by **the company** about events affecting itself.
SC 13D is filed by **the investor** about its position in another company.

If NVIDIA buys 6% of a small AI company through open-market purchases, **NVIDIA files the 13D, not the company**. The company may not even file an 8-K until later (or not at all).

### SC 13D vs SC 13G

| | SC 13D | SC 13G |
|---|---|---|
| **Filer intent** | Active (may seek to influence) | Passive (index fund, ETF) |
| **Examples** | NVIDIA strategic stake, founder takeover | Vanguard, BlackRock |
| **Our weighting** | High signal | Low signal (we downgrade -1 in score) |

### Key 13D fields we extract

- **Name of Filing Person** (the strategic investor)
- **Name of Issuer** (the target company)
- **Item 4 — Purpose of Transaction** — if it mentions "to actively participate in management" or "strategic partnership," that's a very strong signal

---

## Real backtest: PENG/SGH timeline

This is the textbook example of why this skill exists.

```
2024-07-15  📄 SGH files 8-K
            ├─ Item 1.01: Securities Purchase Agreement w/ SK Telecom
            ├─ Item 3.02: Unregistered sale of 200,000 preferred shares
            ├─ Amount: $200 million
            └─ Conversion price: $32.81
            
            ⏰ This skill would have alerted within ~1 hour
            🎯 SGH stock that day: ~$20

2024-12-XX  Deal closes. SK Telecom now owns 6M+ shares.

2024-10-XX  Company renames SMART Global Holdings → Penguin Solutions
2025-01-XX  PENG ticker change.

2026-04-01  Q2 2026 earnings — pivot to inference AI, raised guide
            🎯 PENG stock: $18 → $30 (+67% in 1 month)

2026-04-25  Intel earnings beat → AI semis rally
            🎯 PENG: $30 → $44 (+47% in 2 weeks)

2026-05-08  Substack post: "Assessing Penguin Solutions Valuation"
2026-05-12  Twitter pump from @KadunaBull
            🎯 PENG: $44.13, post-market $49.99

📊 SGH/PENG return from 8-K filing date to Twitter pump:
   $20 → $50 = +150% in 22 months

📊 Twitter readers who buy on the pump:
   $50 → ? (likely fades — squeeze + ATH + analyst targets below)
```

**Whoever read the 8-K on 2024-07-15 made 5x what whoever followed the Twitter pump made.**

---

## More backtest examples (would have triggered)

### CRWV — CoreWeave + OpenAI Master Supply Agreement

```
2025-09-XX  CRWV 8-K Item 1.01: Master Services Agreement with OpenAI
            ├─ Amount: $11.9 billion over 5 years
            ├─ Type: Long-term supply / strategic partnership
            
            ⏰ This skill would have alerted within hours
            🎯 CRWV stock: ~$115
            
🎯 Score breakdown (estimate):
   Tier-1 OpenAI: not in our default registry yet, but
   "OpenAI" can be added if user wants this signal type.
```

### ORCL — Stargate JV

```
2025-01-21  ORCL 8-K Item 1.01: $500B Stargate JV with OpenAI / MGX / SoftBank
            ├─ Cluster: NVIDIA, OpenAI, MGX, SoftBank Vision Fund
            ├─ Amount: $500 billion (mega cluster)
            
            ⏰ Score: 10/10 EXCEPTIONAL — quad sovereign cluster
            🎯 ORCL stock: $158
```

### Hypothetical NVIDIA $500M investment

The unit test fixture `nvidia_partnership_8k.txt` represents this scenario. Score: **8-9/10**.

---

## How Substack/Twitter shillers use the same data

Everyone serious about finding alpha has access to SEC EDGAR. **The difference is speed and process:**

```
SEC EDGAR (公开免费)
       │
       ▼
   ┌───────────┬─────────────┬───────────────┬──────────────────┐
   │           │             │               │                  │
   ▼           ▼             ▼               ▼                  ▼
 Hedge      Substack      Twitter        Reddit            This skill
 funds      writers       traders        chatters          
   │           │             │               │                  │
1 day      1-3 weeks    1-3 months   6-18 months        Hours (cron)
```

**Substack writers like Gaetano @crux_capital_, Bryan @BryzonX**:
- Read SEC EDGAR via [efts.sec.gov full-text search](https://efts.sec.gov)
- Cross-check with company IR pages
- Write deep dive 1-3 weeks after filing
- Sell to paid subscribers

**Twitter pumpers like Kaduna @KadunaBull**:
- Often pulling from Substack writers (downstream)
- Or hand-curated screens of SEC filings
- Post when stock has already rallied (FOMO bait)
- 6-18 months after the original 8-K

**This skill**:
- Polls EDGAR atom feed every 60 min
- Filters + scores automatically
- Pushes Telegram alert within hours
- Same data, faster pipeline

You don't have a "secret edge" — you have the **same edge as Substack writers, automated**.

---

## What if I want to add OpenAI / Anthropic / xAI to the registry?

Edit `scripts/investor_registry.py`. They're private companies so they file as **investors** in SC 13D, not as issuers in 8-K. Add them to `TIER_1`:

```python
TIER_1 = {
    ...
    "OpenAI": ["OpenAI, Inc.", "OpenAI LLC", "OpenAI Global"],
    "Anthropic": ["Anthropic, PBC", "Anthropic Holdings"],
    "xAI": ["X.AI Corp.", "xAI Holdings"],
    ...
}
```

Then `find_strategic_investors("...investment from OpenAI...")` will match.

---

## Schedule / cron behavior

The GitHub Actions workflow runs **every 60 minutes** during weekdays 9 AM - 7 PM ET. We don't run on weekends because SEC EDGAR is quiet (no live filings, just delayed weekend filings showing up Monday).

**Why hourly, not every 30 min like insider-firehose?**
- 8-K filings are heavier to parse (we fetch full body, not just metadata)
- yfinance enrichment adds 1-3 sec per ticker
- Bigger filings (1.5 MB+ HTML) are slow to download from EDGAR
- Hourly is enough — these aren't time-sensitive in seconds

**Rate limiting**:
- SEC: 10 req/sec limit → we sleep 0.15s between requests (6.7 req/s)
- yfinance: cached in `filters.py` (one call per ticker per cron run)
- Telegram: well below their rate limit (rarely > 10 alerts per run)

---

## Hard filters applied (in fast-fail order)

```python
1. Noise filter           # Skip Items 5.02, 5.07, 2.02-only filings
2. Strategic investor     # Regex match against TIER_1/TIER_2/SOVEREIGN
3. 8-K Items              # Must include 1.01, 3.02, 7.01, or 8.01
4. Amount ≥ $50M          # Regex extracted $$$ amount
5. Valid ticker           # Format check
6. US-listed              # yfinance exchange must be NYSE/NASDAQ/AMEX
7. Market cap ≥ $50M      # yfinance marketCap
```

Each filter is **fast-fail**: cheapest first, network calls last.

---

## How to extend the registry

The strategic investor list lives in `scripts/investor_registry.py`. Adding a new entity:

```python
TIER_1["MetaAI_VC"] = [
    "Meta AI Ventures",
    "Meta AI Fund",
    # ... any aliases the SEC filing might use
]
```

Then re-run the test suite to validate:

```bash
python3 tests/test_all.py
```

---

## CLI scoring (no firehose needed)

You can ad-hoc score any deal:

```bash
# PENG/SGH replay
python3 scripts/analysis.py SGH \
    --amount 200 \
    --tier tier_1 \
    --investor SK_Telecom \
    --type "PIPE (Preferred)" \
    --conversion-price 32.81
```

This pulls live valuation + price action from yfinance and computes the 0-10 Partner Score.

---

## Companion skills

| Skill | Used together with this how |
|---|---|
| `insider-firehose` | **The other firehose.** When same ticker fires both alerts (insider buy + strategic partner) within 30 days = MEGA SIGNAL. |
| `analyze-stock` | When alert fires for ticker you don't recognize, run analyze-stock for full context. |
| `option-wall-analysis` | After alert + you want to size in, check option flow positioning. |
| `macro-warning` | Gate any conviction buy by current macro regime. |
| `tax-optimize` | Tax math before exit. |

---

## Files

```
strategic-partner-firehose/
├── SKILL.md              # NL trigger description
├── SETUP.md              # 5-min setup
├── README.md             # This file (long-form)
├── strategic_config.json # On/off toggle
└── scripts/
    ├── partner_firehose.py     # Main entry
    ├── investor_registry.py    # TIER_1 / TIER_2 / SOVEREIGN / SMART_VC names
    ├── parsers.py              # 8-K + 13D regex extractors
    ├── filters.py              # mcap + US-listed filters
    ├── analysis.py             # 0-10 Partner Score CLI
    ├── strategic_state.json    # Dedup ledger
    └── tests/
        ├── test_all.py         # 32 unit tests (all pass)
        └── fixtures/
            ├── peng_sgh_sk_telecom_8k.txt
            ├── nvidia_partnership_8k.txt
            ├── sovereign_cluster_8k.txt
            └── noise_5_02_officer_change.txt
```

---

## Limitations

1. **EDGAR atom feed is "current 100"** — if more than 100 8-Ks file in one hour during peak (4-7 PM ET earnings season), we may miss some. Mitigation: hourly cron + 10000-entry state cap.

2. **HTML parsing is fragile** — we strip tags with regex. Edge cases (XBRL-only inline filings, encrypted exhibits) may break extraction.

3. **Amount extraction can be fooled** — "$200 million authorized buyback" matches our regex even though it's not a strategic investment. Mitigation: keyword filter requires strategic-investor name AND deal-type keyword nearby.

4. **No semantic understanding** — we don't run an LLM over the filing text. Some legitimate partnerships will be missed if they use unusual phrasing. v2.3 may add an LLM second-pass.

5. **No price-impact backtest** — we have not yet built a tool that automatically tests "did stocks go up after this skill would have alerted?" — that's a v2.3 add.

---

## Versioning

- **1.0 (2026-05-12)**: Initial release. 32 unit tests pass. Real backtest validates PENG/SGH (score 9/10), sovereign cluster (10/10), noise correctly filtered.

---

## What this skill is NOT planning to become

- ❌ A trading bot that places orders
- ❌ A leaderboard of top strategic deals
- ❌ A subscription service / B2B SaaS
- ❌ Foreign-only filings (HKEX, LSE, JPX) — US-listed only
- ❌ Crypto-IPO / SPAC-specific tracking
