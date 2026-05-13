#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classifier.py — Theme-based "verification layer" for 8-K filings.

主题验证层 —— 不依赖 registry, 通过题材关键词识别 AI/数据中心相关 filing.

═══════════════════════════════════════════════════════════════════════
  WHY THIS EXISTS / 为什么需要这个模块
═══════════════════════════════════════════════════════════════════════

The registry approach (investor_registry.py) only fires when a filing
mentions a specific known investor by name (NVIDIA, SK Telecom, etc.).

But many of the highest-alpha 8-Ks have **anonymous customers**:
  - POWL got "$400M order from a major U.S. technology company" — no name
  - BE gets fuel-cell orders from hyperscalers — also anonymous
  - GEV gas turbines, CMI gensets — often anonymous Fortune 100 customers

These are MASSIVE signals (AI data center buildout) but the registry
misses them entirely because the customer name is redacted.

This classifier catches them via **theme keyword density**:
  - "Largest order in company history" + "data center" + "$400M+"
  - "Behind-the-meter" + "gigawatt" + "AI"
  - "Leading hyperscaler" + multi-year contract

不依赖具体公司名, 靠语义题材识别. 配合 registry, 两条并行 path 都触发
alert, 覆盖率显著提升.

═══════════════════════════════════════════════════════════════════════
  THEME CATEGORIES / 题材分类
═══════════════════════════════════════════════════════════════════════

CORE_AI:      Direct AI/ML terms                  (alpha: AI is the theme)
COMPUTE:      GPU / accelerator / chip terms       (alpha: hardware buildout)
DATACENTER:   Capacity / power / build terms      (alpha: AIDC infra)
HYPERSCALER:  Anonymous customer proxies          (alpha: big unnamed buyer)
ENERGY:       Power / fuel cell / gas turbine     (alpha: AIDC power)
MAGNITUDE:    "Largest", "record-breaking", etc.  (alpha: company-defining)
EVENT_TYPE:   Master Supply / Long-term agreement (alpha: real revenue)

Score formula:
  +2 per CORE_AI category match
  +2 per COMPUTE category match
  +2 per DATACENTER category match
  +2 per HYPERSCALER category match
  +1 per ENERGY category match
  +2 if MAGNITUDE keyword present (caps once)
  +1 if EVENT_TYPE keyword present (caps once)

Clamped to 0-10. Score ≥ 6 = "fire alert".
"""
from __future__ import annotations

import re

# ─── Theme keyword categories / 题材关键词分类 ────────────────────────────
# All keywords case-insensitive. Use \b boundary in regex to avoid partial matches.
# 所有关键词大小写不敏感, 用 \b 边界避免子串误匹配.

CORE_AI: list[str] = [
    "artificial intelligence",
    "AI infrastructure",
    "AI data center", "AI datacenter",
    "AI cluster", "AI clusters",
    "AI workload", "AI workloads",
    "AI training", "AI inference",
    "machine learning", "deep learning",
    "neural network",
    "large language model", "LLM",
    "generative AI", "GenAI",
    "foundation model",
    "transformer model",
    "AI supercomputer",
    "AI factory", "AI factories",
]

COMPUTE: list[str] = [
    # NVIDIA chip codenames + product lines
    "Blackwell", "Hopper", "Rubin",
    "GB200", "B200", "H200", "H100",
    "DGX", "HGX",
    "NVLink", "NVL72",
    # General compute hardware
    "GPU compute", "GPU cluster", "GPU clusters",
    "GPU infrastructure",
    "accelerator", "accelerators",
    "TPU", "ASIC",
    # Memory + interconnect
    "HBM", "High Bandwidth Memory", "HBM3", "HBM4",
    "CXL",
    # AMD / Intel competitors
    "Instinct", "MI300X", "MI325X",
    "Xeon", "EPYC",
]

DATACENTER: list[str] = [
    "data center", "datacenter",
    "data center capacity", "datacenter capacity",
    "data center build", "data center expansion",
    "hyperscale", "hyperscaler", "hyperscalers",
    "colocation", "co-location", "co-located",
    "multi-gigawatt", "gigawatts", "gigawatt-scale",
    "megawatts", "MW capacity",
    "behind-the-meter", "behind the meter",
    "greenfield data center",
    "AI factory build",
    "edge data center",
    "data center campus",
]

# Anonymous-customer proxy phrases (catches POWL-style "unnamed big tech customer")
# 匿名客户代号 (抓 POWL 这种 "未具名大客户")
HYPERSCALER_PROXY: list[str] = [
    "leading hyperscaler", "major hyperscaler", "top hyperscaler",
    "tier-1 hyperscaler", "tier 1 hyperscaler",
    "leading cloud provider", "major cloud provider",
    "leading technology company", "major technology company",
    "major U.S. technology company", "major US technology company",
    "Fortune 100 technology", "Fortune 500 technology",
    "leading AI company", "major AI company",
    "tier-1 customer", "top-tier customer",
    "blue-chip customer",
    "leading global technology",
    "publicly traded technology company",
    "large investment-grade customer",
]

ENERGY: list[str] = [
    "fuel cell", "fuel cells",
    "gas turbine", "gas turbines",
    "natural gas power",
    "microturbine", "microturbines",
    "genset", "gensets",
    "modular power",
    "onsite power", "on-site power",
    "stationary power",
    "battery storage", "BESS",
    "switchgear",
    "data center power",
    "AI power",
]

MAGNITUDE: list[str] = [
    "largest order in company history",
    "largest contract in company history",
    "largest single order",
    "record-breaking",  "record breaking",
    "largest in our history",
    "transformational",
    "company-defining",
    "multi-year agreement",
    "multi-year contract",
    "multi-billion",
    "billion-dollar",
    "frame agreement",
    "framework agreement",
]

EVENT_TYPE: list[str] = [
    "master supply agreement",
    "master services agreement",
    "master purchase agreement",
    "long-term supply agreement", "long term supply agreement",
    "preferred supplier",
    "exclusive supplier",
    "joint development agreement",
    "strategic agreement",
    "strategic partnership",
    "strategic collaboration",
    "definitive agreement",
]


# ─── Compile patterns once / 模块加载时一次性编译 regex ────────────────────
def _compile(words: list[str]) -> list[re.Pattern]:
    """Compile each keyword as case-insensitive whole-word regex."""
    return [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in words]


_PATTERNS: dict[str, list[re.Pattern]] = {
    "core_ai": _compile(CORE_AI),
    "compute": _compile(COMPUTE),
    "datacenter": _compile(DATACENTER),
    "hyperscaler": _compile(HYPERSCALER_PROXY),
    "energy": _compile(ENERGY),
    "magnitude": _compile(MAGNITUDE),
    "event_type": _compile(EVENT_TYPE),
}


# ─── Scoring weights / 评分权重 ──────────────────────────────────────────
# Per-category point if ANY keyword in category matches (we don't double-count
# within a category — many keywords in one category = same signal).
# 类别内任意关键词命中 = 加该类别分; 类别内多个命中不重复加分.
_CATEGORY_WEIGHTS: dict[str, int] = {
    "core_ai": 2,       # AI 题材本身
    "compute": 2,       # 硬件 / GPU / 芯片
    "datacenter": 2,    # 数据中心容量
    "hyperscaler": 2,   # 匿名大客户代号 (POWL-style catch)
    "energy": 1,        # 能源 (AIDC power)
    "magnitude": 2,     # "Largest in history" 类
    "event_type": 1,    # Master Supply / JV 类
}


def _categories_hit(text: str) -> dict[str, list[str]]:
    """
    Returns dict mapping category → list of matched phrases.
    返回 category → 命中短语列表.

    Whitespace is normalized first (collapse newlines + multiple spaces)
    because real SEC filings have line breaks mid-phrase after HTML tag
    stripping. Without normalization, "major U.S. technology\\ncompany"
    fails to match the pattern "major U.S. technology company".
    先标准化空格 (合并换行 + 多空格), 因为 SEC filing HTML 去标签后
    短语中间常有换行, 不标准化会导致 multi-word phrase 不匹配.
    """
    hits: dict[str, list[str]] = {}
    if not text:
        return hits

    # Normalize whitespace: any run of whitespace → single space
    # 标准化: 任意空白连续 → 单空格
    normalized = re.sub(r"\s+", " ", text)

    for cat, patterns in _PATTERNS.items():
        matched = []
        for pat in patterns:
            m = pat.search(normalized)
            if m:
                matched.append(m.group(0))
        if matched:
            # Dedup while preserving order
            seen = set()
            unique = []
            for w in matched:
                wl = w.lower()
                if wl not in seen:
                    seen.add(wl)
                    unique.append(w)
            hits[cat] = unique

    return hits


def compute_theme_score(text: str) -> dict:
    """
    Score a filing's body text on AI/AIDC theme relevance.
    给 filing 正文打 AI/AIDC 题材相关性分数.

    Args:
        text: filing body text (8-K cover + exhibits combined)

    Returns:
        {
            "score": 0-10 int,
            "categories": {cat: [matched_phrases...]},
            "ai_relevant": bool (score >= 6),
            "primary_theme": str ("AI Data Center" / "Hyperscaler Contract" / ...),
            "magnitude_signal": bool,
        }
    """
    if not text:
        return {
            "score": 0,
            "categories": {},
            "ai_relevant": False,
            "primary_theme": "None",
            "magnitude_signal": False,
        }

    hits = _categories_hit(text)

    # Compute score: 1 point per category hit, weighted
    # 计算分数: 每个类别命中加一次权重分
    raw_score = 0
    for cat, phrases in hits.items():
        if phrases:
            raw_score += _CATEGORY_WEIGHTS.get(cat, 0)

    score = max(0, min(10, raw_score))

    # Derive primary theme from highest-priority hit category
    # 从最高优先级类别推断主题
    priority = ["hyperscaler", "datacenter", "core_ai", "compute", "energy"]
    primary_theme = "None"
    for cat in priority:
        if cat in hits:
            theme_names = {
                "hyperscaler": "Hyperscaler Contract (anonymous customer)",
                "datacenter": "AI Data Center Infrastructure",
                "core_ai": "AI / ML Theme",
                "compute": "GPU / Compute Hardware",
                "energy": "AI Data Center Power",
            }
            primary_theme = theme_names[cat]
            break

    return {
        "score": score,
        "categories": hits,
        "ai_relevant": score >= 6,
        "primary_theme": primary_theme,
        "magnitude_signal": "magnitude" in hits,
    }


# ─── CLI sanity check / 命令行健康检查 ──────────────────────────────────

if __name__ == "__main__":
    import sys

    sample = sys.stdin.read() if not sys.stdin.isatty() else """
    Powell Industries announced the largest order in company history,
    a multi-year contract valued at $400 million for behind-the-meter
    power systems supporting a greenfield AI data center being built
    for a major U.S. technology company.
    """

    result = compute_theme_score(sample)
    print(f"Score: {result['score']}/10")
    print(f"Primary theme: {result['primary_theme']}")
    print(f"AI-relevant: {result['ai_relevant']}")
    print(f"Magnitude signal: {result['magnitude_signal']}")
    print(f"Categories hit:")
    for cat, phrases in result["categories"].items():
        print(f"  {cat}: {', '.join(phrases)}")
