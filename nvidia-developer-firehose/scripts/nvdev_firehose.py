#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nvdev_firehose.py — AI ECOSYSTEM firehose (v3 MULTI-SOURCE).

v3 expansion (May 2026): expanded from NVIDIA Developer Blog only to a multi-
source AI-ecosystem monitor covering:
  • NVIDIA       — developer blog, main blog, newsroom (official press)
  • Hyperscalers — Azure, AWS, AWS-ML, GCP, GCP-AI, GCP-Systems, Meta-Eng
  • AI Labs      — OpenAI, DeepMind, HuggingFace
  • Neoclouds    — CoreWeave, Groq, Together

For each new post (Atom OR RSS 2.0), auto-extracts every mentioned company →
US ticker using the same smart resolver as v2 (heuristic candidates +
yfinance.Search + persistent cache).  Source tag is included in the Telegram
alert so you know which channel fired.

(AMD has no public RSS — those announcements are covered by our separate
SEC 8-K strategic-partner-firehose + pr-wire-firehose.)
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "nvdev_state.json"
CACHE_FILE = SCRIPT_DIR / "nvdev_ticker_cache.json"

UA = os.environ.get(
    "NVDEV_USER_AGENT",
    "ai-ecosystem-firehose/3.0 (claude-investment-skills)",
)
TEST_MODE = os.environ.get("TEST_MODE", "") == "1"
MAX_BODY = 60_000
MAX_ALERTS_PER_RUN = int(os.environ.get("MAX_ALERTS", "12"))
MAX_ALERTS_PER_SOURCE = int(os.environ.get("MAX_PER_SOURCE", "3"))
MAX_LOOKUPS_PER_ARTICLE = int(os.environ.get("MAX_LOOKUPS", "40"))


# ════════════════════════════════════════════════════════════════════════
#  FEEDS — multi-source map.  Keep aligned with SKILL.md description.
# ════════════════════════════════════════════════════════════════════════
FEED_URLS: dict[str, dict] = {
    # NVIDIA — 3 official channels
    "nv-dev":     {"url": "https://developer.nvidia.com/blog/feed/",             "label": "NVIDIA Developer"},
    "nv-blog":    {"url": "https://blogs.nvidia.com/feed/",                      "label": "NVIDIA Blog"},
    "nv-news":    {"url": "https://nvidianews.nvidia.com/rss.xml",               "label": "NVIDIA Newsroom"},
    # Hyperscalers (GCP feeds + Groq are HTML pages not RSS — skipped)
    "azure":      {"url": "https://azure.microsoft.com/en-us/blog/feed/",        "label": "Azure"},
    "aws":        {"url": "https://aws.amazon.com/blogs/aws/feed/",              "label": "AWS"},
    "aws-ml":     {"url": "https://aws.amazon.com/blogs/machine-learning/feed/", "label": "AWS ML"},
    "meta-eng":   {"url": "https://engineering.fb.com/feed/",                    "label": "Meta Engineering"},
    # AI Labs
    "openai":     {"url": "https://openai.com/blog/rss.xml",                     "label": "OpenAI"},
    "deepmind":   {"url": "https://deepmind.google/blog/rss.xml",                "label": "DeepMind"},
    "hf":         {"url": "https://huggingface.co/blog/feed.xml",                "label": "Hugging Face"},
    # Neoclouds / Strategic Compute
    "coreweave":  {"url": "https://www.coreweave.com/blog/rss.xml",              "label": "CoreWeave"},
    "together":   {"url": "https://www.together.ai/blog/rss.xml",                "label": "Together AI"},
}


# ════════════════════════════════════════════════════════════════════════
#  TRACKED — portfolio universe → 🎯 high-signal badge in alerts.
# ════════════════════════════════════════════════════════════════════════
TRACKED_TICKERS: set[str] = {
    # Optical / DSP / interconnect
    "MRVL", "LITE", "COHR", "AAOI", "CRDO", "AVGO", "ALAB", "MTSI", "APH",
    # Power semis / 800V HVDC partners
    "NVDA", "NVTS", "MPWR", "VICR", "POWI", "ON", "TXN", "STM", "IFNNY",
    "AOSL", "ADI", "ABBNY", "SIEGY", "SBGSY", "HTHIY", "RNECY", "ROHCY",
    "LITKY", "MIELY",
    # AI semis / foundries
    "AMD", "INTC", "ARM", "TSM", "GFS", "TSEM", "MU",
    # Networking / system / server
    "ANET", "CSCO", "JNPR", "DELL", "SMCI", "HPE", "FLEX",
    # Hyperscalers + neoclouds
    "MSFT", "AMZN", "GOOGL", "META", "ORCL", "AAPL", "CRWV", "NBIS",
    # Power / EPC / cooling
    "VRT", "ETN", "MOD", "NVT", "HUBB", "POWL", "STRL", "MTZ", "PWR",
    "PRIM", "GNRC",
    # Power generation
    "CEG", "VST", "TLN", "GEV", "BE", "CMI", "AEP", "D",
    # Auto / SDV / robotics
    "TSLA", "MBLY",
    # AI infra
    "AXTI", "TMUS",
}


# Short forms / aliases for ambiguous tokens.
ALIAS: dict[str, str] = {
    "MPS":                  "Monolithic Power Systems",
    "TI":                   "Texas Instruments",
    "TSMC":                 "Taiwan Semiconductor Manufacturing",
    "AMD":                  "Advanced Micro Devices",
    "HPE":                  "Hewlett Packard Enterprise",
    "STMicro":              "STMicroelectronics",
    "STMicroelectronics":   "STMicroelectronics",
    "Onsemi":               "ON Semiconductor",
    "onsemi":               "ON Semiconductor",
    "Arm":                  "Arm Holdings",
    "AWS":                  "Amazon",
    "GCP":                  "Alphabet",
    "Azure":                "Microsoft",
    "ABB":                  "ABB Ltd",
    "AOS":                  "Alpha and Omega Semiconductor",
    "Schneider":            "Schneider Electric",
    "Siemens":              "Siemens AG",
    "Hitachi":              "Hitachi Ltd",
    "Renesas":              "Renesas Electronics",
    "ROHM":                 "ROHM Semiconductor",
    "Mitsubishi Electric":  "Mitsubishi Electric",
    "LITE-ON":              "Lite-On Technology",
    "LiteOn":               "Lite-On Technology",
}


STOPWORDS: set[str] = {
    # NVIDIA brands / products
    "nvidia", "nvidia developer", "nvidia technical blog", "nvidia newsroom",
    "cuda", "tensorrt", "nim", "triton", "rapids", "nemo", "omniverse",
    "dgx", "hgx", "mgx", "grace", "hopper", "blackwell", "rubin",
    "geforce", "rtx", "gtx", "tegra", "jetson", "drive", "spectrum",
    "nvlink", "infiniband", "mellanox", "bluefield", "connectx",
    "magnum", "isaac", "metropolis", "clara", "merlin", "morpheus",
    # AWS / Azure / GCP brands
    "amazon web services", "ec2", "s3", "sagemaker", "bedrock",
    "azure openai", "azure ml", "cosmos db", "cosmosdb",
    "google cloud", "bigquery", "vertex ai", "tpu", "trillium",
    # AI lab brands
    "gpt", "claude", "gemini", "llama", "mistral", "grok",
    # Tech generic
    "ai", "ml", "llm", "gpu", "cpu", "tpu", "npu", "asic", "fpga", "rag",
    "api", "sdk", "http", "json", "yaml", "xml", "csv", "rest", "grpc",
    "linux", "windows", "macos", "ubuntu", "debian", "kubernetes", "docker",
    "pytorch", "tensorflow", "jax", "hugging face", "open source",
    "machine learning", "deep learning", "neural network", "natural language",
    "supervised learning", "reinforcement learning", "computer vision",
    "github", "gitlab", "bitbucket",
    # Conferences
    "gtc", "re invent", "build", "io", "siggraph", "supercomputing", "isc",
    "neurips", "icml", "cvpr",
    # Corporate generics
    "inc", "ltd", "corp", "corporation", "company", "limited", "group",
    "technology", "technologies", "systems", "solutions", "platform",
    "the company", "the model", "the data", "the system", "the team",
    # Calendar / structural
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "figure", "table", "step", "example", "tutorial", "blog", "post",
    "notebook", "model", "data", "code", "image", "video", "audio",
    "user", "users", "developer", "developers", "researcher", "researchers",
    "scientist", "engineer", "scientists", "engineers",
    "first", "second", "third", "fourth", "fifth",
    "united states", "europe", "asia", "china", "japan", "korea",
    "north america", "south korea", "taiwan", "india", "germany",
    "the", "new", "next", "previous", "however", "therefore", "additionally",
    "with", "using", "via", "from", "and", "or", "but", "for",
    # Single-word technical categories that wrongly resolve to small-cap
    # companies (e.g. "Robotics" → Kraken Robotics, "Research" → BA via
    # "The Boeing Company" name-overlap noise).
    "research", "robotics", "automation", "computing", "networking",
    "storage", "memory", "performance", "architecture", "intelligence",
    "learning", "vision", "language", "audio", "video", "graphics",
    "infrastructure", "platform", "framework", "service", "solution",
    "innovation", "applications", "products", "services", "industries",
    "enterprise", "enterprises", "consumer", "consumers", "customers",
    "education", "training", "research papers", "white paper",
    "team", "teams", "labs", "studio", "studios",
    "the name", "the future", "the world",
}

US_EXCHANGES = {"NMS", "NYQ", "NGM", "ASE", "PCX", "BTS",
                "PNK", "OTC", "OQX", "OQB", "OQS"}


# ── feed fetching + parsing (handles BOTH Atom AND RSS 2.0) ────────────
def fetch_feed(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def parse_feed(xml: str, source_key: str) -> list[dict]:
    """Unified parser: tries Atom <entry> first, falls back to RSS <item>.
    Each returned dict gets a 'source' field with the feed key."""
    out: list[dict] = []

    # Atom
    atom_entries = re.findall(r"<entry[\s>](.*?)</entry>", xml, re.DOTALL)
    if atom_entries:
        for e in atom_entries:
            out.append(_parse_atom_entry(e, source_key))
        return out

    # RSS 2.0
    rss_items = re.findall(r"<item[\s>](.*?)</item>", xml, re.DOTALL)
    for it in rss_items:
        out.append(_parse_rss_item(it, source_key))
    return out


def _strip(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.DOTALL)
    return html.unescape(s).strip()


def _parse_atom_entry(e: str, source_key: str) -> dict:
    def t(tag: str) -> str:
        m = re.search(f"<{tag}[^>]*>(.*?)</{tag}>", e, re.DOTALL)
        return _strip(m.group(1)) if m else ""

    link_m = re.search(r'<link[^>]+rel="alternate"[^>]*href="([^"]+)"', e)
    if not link_m:
        link_m = re.search(r'<link[^>]+href="([^"]+)"', e)
    link = link_m.group(1) if link_m else ""

    a_m = re.search(r"<author>.*?<name>(.*?)</name>.*?</author>", e, re.DOTALL)
    author = a_m.group(1).strip() if a_m else ""

    return {
        "source":  source_key,
        "id":      t("id") or link,
        "title":   re.sub(r"<[^>]+>", "", t("title")),
        "link":    link,
        "author":  author,
        "updated": t("updated") or t("published"),
        "summary": re.sub(r"<[^>]+>", " ", t("summary") or t("content"))[:500],
    }


def _parse_rss_item(it: str, source_key: str) -> dict:
    def t(tag: str) -> str:
        m = re.search(f"<{tag}[^>]*>(.*?)</{tag}>", it, re.DOTALL)
        return _strip(m.group(1)) if m else ""

    link = t("link")
    return {
        "source":  source_key,
        "id":      t("guid") or link,
        "title":   re.sub(r"<[^>]+>", "", t("title")),
        "link":    link,
        "author":  t("dc:creator") or t("author"),
        "updated": t("pubDate") or t("dc:date"),
        "summary": re.sub(r"<[^>]+>", " ", t("description"))[:500],
    }


def fetch_article(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as exc:
        print(f"[WARN] fetch {url}: {exc}", file=sys.stderr)
        return ""
    m = re.search(r"<article[^>]*>(.*?)</article>", h, re.DOTALL)
    if not m:
        m = re.search(r"<main[^>]*>(.*?)</main>", h, re.DOTALL)
    body = m.group(1) if m else h
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.DOTALL | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.DOTALL | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    return re.sub(r"\s+", " ", body)[:MAX_BODY]


# ── smart extraction (same algorithm as v2) ────────────────────────────
_CAND_PAT = re.compile(
    r"\b([A-Z][a-zA-Z0-9.&\-]{1,30}(?:\s+[A-Z][a-zA-Z0-9.&\-]{1,30}){0,3})\b"
)


def extract_candidates(text: str) -> list[tuple[str, int]]:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"([.!?;:,])", r" \1 ", text)
    freq: dict[str, int] = {}
    for m in _CAND_PAT.finditer(text):
        c = m.group(1).strip().rstrip(".")
        if c.lower().startswith("the "):
            c = c[4:]
        if len(c) < 3:
            continue
        if c.lower() in STOPWORDS:
            continue
        freq[c] = freq.get(c, 0) + 1
    return sorted(freq.items(), key=lambda x: -x[1])


def _name_overlap(query: str, candidate: str) -> bool:
    """Both sides must have at least one substantive word (>3 chars) AND
    those word sets must intersect.  Short queries no longer auto-pass —
    that bug let 'The' match 'The Boeing Company' (=> BA false positive)."""
    q = {w for w in re.split(r"\W+", query.lower()) if len(w) > 3}
    c = {w for w in re.split(r"\W+", candidate.lower()) if len(w) > 3}
    if not q or not c:
        return False
    return bool(q & c)


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.load(open(CACHE_FILE))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    if not TEST_MODE:
        json.dump(cache, open(CACHE_FILE, "w"), indent=2, sort_keys=True,
                  ensure_ascii=False)


def resolve_ticker(name: str, cache: dict) -> dict | None:
    key = name.lower().strip()
    if key in cache:
        return cache[key]
    lookup_name = ALIAS.get(name, name)
    try:
        import yfinance as yf
        results = yf.Search(lookup_name, max_results=5).quotes or []
    except Exception as exc:
        print(f"[WARN] yfinance.Search('{lookup_name}'): {exc}", file=sys.stderr)
        cache[key] = None
        return None
    for q in results:
        if q.get("quoteType") != "EQUITY":
            continue
        exch = q.get("exchange", "")
        if exch not in US_EXCHANGES:
            continue
        canon_name = q.get("longname") or q.get("shortname") or ""
        if not _name_overlap(lookup_name, canon_name):
            continue
        result = {
            "ticker":   q["symbol"],
            "exchange": exch,
            "name":     canon_name,
            "source":   "yfinance",
        }
        cache[key] = result
        return result
    cache[key] = None
    return None


def extract_all_mentions(text: str, cache: dict) -> dict[str, dict]:
    hits: dict[str, dict] = {}
    candidates = extract_candidates(text)
    lookups = 0
    for cand, _freq in candidates:
        key = cand.lower().strip()
        if key in cache:
            if cache[key]:
                hits[cand] = cache[key]
            continue
        if lookups >= MAX_LOOKUPS_PER_ARTICLE:
            print(f"[INFO] lookup cap {MAX_LOOKUPS_PER_ARTICLE} hit", file=sys.stderr)
            break
        r = resolve_ticker(cand, cache)
        lookups += 1
        time.sleep(0.15)
        if r:
            hits[cand] = r
    for m in re.finditer(r"\((?:NASDAQ|NYSE|NSE):\s*([A-Z]{1,6})\)", text):
        sym = m.group(1)
        hits.setdefault(f"(exchange:{sym})",
                        {"ticker": sym, "source": "exchange-tag", "name": ""})
    return hits


# ── alert format ───────────────────────────────────────────────────────
def fmt_alert(item: dict, mentions: dict[str, dict]) -> str:
    tracked = [(n, m) for n, m in mentions.items()
               if m and m["ticker"] in TRACKED_TICKERS]
    other = [(n, m) for n, m in mentions.items()
             if m and m["ticker"] not in TRACKED_TICKERS]
    head = "🟢🟪" if tracked else "🟪"
    src_label = FEED_URLS.get(item.get("source"), {}).get("label",
                                                          item.get("source", "?"))
    lines = [
        f"{head} *{src_label}* — new post",
        f"*{item['title']}*",
    ]
    if item.get("author"):
        lines.append(f"_作者: {item['author']}_")
    if item.get("updated"):
        lines.append(f"_发布: {str(item['updated'])[:10]}_")
    lines.append("")
    if tracked:
        lines.append("🎯 *组合内标的(高信号):*")
        for n, m in tracked[:12]:
            lines.append(f"  • {n} → `{m['ticker']}`")
    if other:
        if tracked:
            lines.append("")
        lines.append("🔍 *其他识别到的可交易标的:*")
        for n, m in other[:10]:
            nm = m.get("name", "")[:35]
            lines.append(f"  • {n} → `{m['ticker']}`" + (f"  ({nm})" if nm else ""))
    if not mentions:
        lines.append("_未识别到可交易标的 — 文章可能是纯技术教程_")
    lines.append("")
    lines.append(item["link"])
    return "\n".join(lines)


def send_telegram(msg: str) -> bool:
    if TEST_MODE:
        print("─── TEST_MODE ───\n" + msg + "\n─── end ───", file=sys.stderr)
        return True
    import requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[WARN] no Telegram creds, message dropped", file=sys.stderr)
        print(msg, file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id": chat, "text": msg, "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=20)
    if r.status_code == 200:
        return True
    r2 = requests.post(url, json={
        "chat_id": chat, "text": msg,
        "disable_web_page_preview": True,
    }, timeout=20)
    return r2.status_code == 200


# ── main ───────────────────────────────────────────────────────────────
def main() -> int:
    state = json.load(open(STATE_FILE)) if STATE_FILE.exists() else {"seen": []}
    cache = _load_cache()
    seen: set[str] = set(state.get("seen", []))
    print(f"[INFO] state={len(seen)} seen, cache={len(cache)} resolved, "
          f"feeds={len(FEED_URLS)}", file=sys.stderr)

    # Collect ALL entries across ALL sources
    all_entries: list[dict] = []
    feed_stats: dict[str, int] = {}
    for source_key, meta in FEED_URLS.items():
        try:
            xml = fetch_feed(meta["url"])
            entries = parse_feed(xml, source_key)
            all_entries.extend(entries)
            feed_stats[source_key] = len(entries)
        except Exception as exc:
            print(f"[WARN] {source_key} feed failed: {exc}", file=sys.stderr)
            feed_stats[source_key] = 0

    print(f"[INFO] feed totals: {feed_stats}", file=sys.stderr)
    print(f"[INFO] total entries pulled: {len(all_entries)}", file=sys.stderr)

    # FIRST RUN (or migration from v2): seed everything silently
    if not seen:
        for e in all_entries:
            seen.add(e["id"])
        state["seen"] = sorted(seen)[-5000:]
        state["updated"] = datetime.now(timezone.utc).isoformat()
        if not TEST_MODE:
            json.dump(state, open(STATE_FILE, "w"), indent=2)
        print(f"[INFO] FIRST RUN: seeded {len(seen)} entries silently",
              file=sys.stderr)
        return 0

    new_by_source: dict[str, list[dict]] = {}
    for e in all_entries:
        if e["id"] in seen:
            continue
        new_by_source.setdefault(e["source"], []).append(e)

    total_new = sum(len(v) for v in new_by_source.values())
    print(f"[INFO] {total_new} new entries across {len(new_by_source)} sources",
          file=sys.stderr)

    sent = 0
    for source_key, items in new_by_source.items():
        for e in items[:MAX_ALERTS_PER_SOURCE]:
            if sent >= MAX_ALERTS_PER_RUN:
                break
            body = fetch_article(e["link"]) if e["link"] else ""
            haystack = " ".join([e["title"], e.get("summary", ""), body])
            mentions = extract_all_mentions(haystack, cache)
            msg = fmt_alert(e, mentions)
            if send_telegram(msg):
                sent += 1
                time.sleep(1)
            seen.add(e["id"])
        # mark remaining as seen too (don't backlog-spam later)
        for e in items[MAX_ALERTS_PER_SOURCE:]:
            seen.add(e["id"])

    if not TEST_MODE:
        state["seen"] = sorted(seen)[-5000:]
        state["updated"] = datetime.now(timezone.utc).isoformat()
        json.dump(state, open(STATE_FILE, "w"), indent=2)
        _save_cache(cache)

    print(f"[DONE] new={total_new} sent={sent} cache_size={len(cache)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
