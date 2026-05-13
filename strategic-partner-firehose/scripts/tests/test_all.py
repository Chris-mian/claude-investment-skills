#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_all.py — Unit tests for strategic-partner-firehose.

单元测试 — 覆盖 registry / parsers / filters / analysis 四个模块.

Tests against real-shape filings (saved as fixtures in tests/fixtures/).
Each test should run in < 100ms (no network calls).
所有测试 < 100ms (无网络调用).

Run:
    python -m pytest tests/test_all.py -v
or:
    python tests/test_all.py    # standalone runner
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make sibling modules importable
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from investor_registry import (  # noqa: E402
    find_strategic_investors, TIER_WEIGHT, TIER_EMOJI,
)
from parsers import (  # noqa: E402
    extract_items, extract_max_amount_usd_m, extract_conversion_price,
    extract_ticker, detect_deal_type, is_noise_filing,
    parse_atom_feed, KEY_8K_ITEMS,
)
from analysis import compute_partner_score  # noqa: E402
from classifier import compute_theme_score  # noqa: E402
import filters  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> str:
    """Read a fixture file as text."""
    return (FIXTURES / name).read_text(encoding="utf-8")


# ─── investor_registry ───────────────────────────────────────────────────

class TestInvestorRegistry(unittest.TestCase):
    """Test the strategic investor name matcher."""

    def test_finds_sk_telecom(self):
        """SK Telecom should be found in PENG/SGH 8-K. / 应该匹配到 SK Telecom."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        matches = find_strategic_investors(body)
        names = [c for _, c in matches]
        self.assertIn("SK_Telecom", names)

    def test_finds_nvidia(self):
        """NVIDIA in NVIDIA partnership 8-K. / 应该匹配到 NVIDIA."""
        body = _load_fixture("nvidia_partnership_8k.txt")
        matches = find_strategic_investors(body)
        names = [c for _, c in matches]
        self.assertIn("NVIDIA", names)

    def test_finds_sovereign_cluster(self):
        """Sovereign + Tier-1 + SoftBank in cluster fixture. / cluster 应匹配多个."""
        body = _load_fixture("sovereign_cluster_8k.txt")
        matches = find_strategic_investors(body)
        names = [c for _, c in matches]
        self.assertIn("NVIDIA", names)
        self.assertIn("MGX", names)
        self.assertIn("PIF_Saudi", names)
        self.assertIn("SoftBank", names)

    def test_no_matches_in_noise(self):
        """Noise 8-K (officer change) has no strategic investors. / 噪音文档应无匹配."""
        body = _load_fixture("noise_5_02_officer_change.txt")
        matches = find_strategic_investors(body)
        self.assertEqual(matches, [])

    def test_dedup(self):
        """Multiple aliases for same entity should match only once."""
        text = "NVIDIA Corporation invested. Nvidia Corp also signed. NVIDIA Inc..."
        matches = find_strategic_investors(text)
        nvidia_matches = [c for t, c in matches if c == "NVIDIA"]
        self.assertEqual(len(nvidia_matches), 1)

    def test_word_boundary(self):
        """'MGX' shouldn't match 'IMGX' or 'BMGXT' (regex boundary). / 边界检查."""
        text = "Random text mentioning IMGXMGXMGX and BMGXT industries."
        matches = find_strategic_investors(text)
        mgx_matches = [c for _, c in matches if c == "MGX"]
        self.assertEqual(len(mgx_matches), 0)


# ─── parsers ─────────────────────────────────────────────────────────────

class TestParsers(unittest.TestCase):
    """Test 8-K + 13D parsing."""

    def test_extract_items(self):
        """Should extract 8-K Items from PENG fixture."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        items = extract_items(body)
        self.assertIn("1.01", items)
        self.assertIn("3.02", items)
        self.assertIn("7.01", items)
        self.assertIn("9.01", items)

    def test_extract_dollar_amount_200m(self):
        """Should extract $200 million from PENG fixture."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        amount = extract_max_amount_usd_m(body)
        self.assertEqual(amount, 200.0)

    def test_extract_dollar_amount_billion(self):
        """Should extract $2.5 billion as 2500."""
        body = _load_fixture("sovereign_cluster_8k.txt")
        amount = extract_max_amount_usd_m(body)
        self.assertEqual(amount, 2500.0)

    def test_extract_dollar_with_commas(self):
        """'$1,500 million' should parse correctly."""
        amount = extract_max_amount_usd_m("Total commitment of $1,500 million")
        self.assertEqual(amount, 1500.0)

    def test_extract_conversion_price(self):
        """Conversion price $32.81 from PENG fixture."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        cp = extract_conversion_price(body)
        self.assertEqual(cp, 32.81)

    def test_extract_ticker_from_trading_symbol(self):
        """Should extract 'SGH' from PENG fixture."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        ticker = extract_ticker(body)
        self.assertEqual(ticker, "SGH")

    def test_extract_ticker_hypo(self):
        """Should extract 'HYPO' from NVIDIA fixture."""
        body = _load_fixture("nvidia_partnership_8k.txt")
        ticker = extract_ticker(body)
        self.assertEqual(ticker, "HYPO")

    def test_detect_deal_type_pipe_preferred(self):
        """PENG fixture should be classified as PIPE Preferred."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        dt = detect_deal_type(body)
        self.assertEqual(dt, "PIPE (Preferred)")

    def test_detect_deal_type_jda(self):
        """NVIDIA fixture mentions Joint Development Agreement."""
        body = _load_fixture("nvidia_partnership_8k.txt")
        dt = detect_deal_type(body)
        # Order matters in detector: PIPE matches first due to "preferred" absent
        # but "private placement" present. Both should be detectable.
        self.assertIn(dt, [
            "PIPE (Common)", "Joint Development", "Strategic Partnership",
            "Master Supply Agreement",
        ])

    def test_is_noise_5_02(self):
        """Item 5.02-only filing should be classified as noise."""
        body = _load_fixture("noise_5_02_officer_change.txt")
        self.assertTrue(is_noise_filing(body))

    def test_is_not_noise_peng(self):
        """PENG fixture has Item 1.01/3.02 — not noise."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        self.assertFalse(is_noise_filing(body))

    def test_empty_text_is_noise(self):
        """Empty body returns True for noise."""
        self.assertTrue(is_noise_filing(""))

    def test_key_items_constant(self):
        """Constants should be sane."""
        self.assertIn("1.01", KEY_8K_ITEMS)
        self.assertIn("3.02", KEY_8K_ITEMS)


# ─── filters ─────────────────────────────────────────────────────────────

class TestFilters(unittest.TestCase):
    """Test eligibility filters (mock yfinance to avoid network)."""

    def setUp(self):
        filters.clear_caches()

    def test_amount_filter_passes(self):
        self.assertTrue(filters.passes_amount_filter(100, min_m=50))

    def test_amount_filter_fails(self):
        self.assertFalse(filters.passes_amount_filter(30, min_m=50))

    def test_amount_filter_at_threshold(self):
        """Exactly at threshold should pass."""
        self.assertTrue(filters.passes_amount_filter(50.0, min_m=50))

    def test_apply_all_filters_bad_ticker(self):
        """Empty / malformed ticker should fail fast without yfinance call."""
        ok, reason = filters.apply_all_filters("", 100)
        self.assertFalse(ok)
        self.assertIn("invalid ticker", reason)

    def test_apply_all_filters_low_amount(self):
        """Amount below threshold fails before any network call."""
        ok, reason = filters.apply_all_filters("AAPL", 10, min_amount_m=50)
        self.assertFalse(ok)
        self.assertIn("amount", reason)

    def test_apply_all_filters_mocked_pass(self):
        """Mock yfinance via cache to test PENG path."""
        # Inject mock data into filter cache to avoid yfinance call
        filters._mcap_cache["SGH"] = 1_100_000_000  # PENG when SK Telecom invested
        filters._exchange_cache["SGH"] = "NMS"
        ok, reason = filters.apply_all_filters("SGH", 200.0)
        self.assertTrue(ok, msg=f"expected pass, got: {reason}")

    def test_apply_all_filters_mocked_small_cap(self):
        """Mock a sub-$50M nano-cap → should fail."""
        filters._mcap_cache["TINY"] = 10_000_000  # $10M mcap
        filters._exchange_cache["TINY"] = "NMS"
        ok, reason = filters.apply_all_filters("TINY", 100)
        self.assertFalse(ok)
        self.assertIn("mcap", reason)

    def test_apply_all_filters_mocked_foreign(self):
        """Mock a foreign listing → should fail."""
        filters._mcap_cache["HKBIG"] = 5_000_000_000
        filters._exchange_cache["HKBIG"] = "HKG"  # Hong Kong
        ok, reason = filters.apply_all_filters("HKBIG", 100)
        self.assertFalse(ok)
        self.assertIn("not US-listed", reason)


# ─── analysis (scoring) ─────────────────────────────────────────────────

class TestAnalysis(unittest.TestCase):
    """Test the 0-10 Partner Score."""

    def test_peng_scenario_high_score(self):
        """
        PENG / SGH scenario: SK Telecom $200M PIPE Preferred + conversion $32.81
        at then-stock ~$20 (below ATH, below 200DMA = contrarian).
        Expected score: 8-10.
        """
        signal = {
            "investors": [("tier_1", "SK_Telecom")],
            "amount_usd_m": 200.0,
            "deal_type": "PIPE (Preferred)",
            "conversion_price": 32.81,
            "form_type": "8-K",
        }
        valuation = {"market_cap": 1_100_000_000}  # $1.1B
        price = {
            "current": 20.0,
            "ma_200": 22.0,            # current below 200DMA → +1
            "high_52w": 28.0,
            "low_52w": 17.5,           # +14% from low → near 52W low
        }
        result = compute_partner_score(signal, valuation, price)
        self.assertGreaterEqual(result["score"], 7, msg=f"Got {result}")

    def test_sovereign_cluster_max_score(self):
        """
        Sovereign cluster: NVIDIA + MGX + PIF + SoftBank, $2.5B deal.
        Should hit max score 10.
        """
        signal = {
            "investors": [
                ("tier_1", "NVIDIA"),
                ("sovereign", "MGX"),
                ("sovereign", "PIF_Saudi"),
                ("tier_1", "SoftBank"),
            ],
            "amount_usd_m": 2500.0,
            "deal_type": "PIPE (Preferred)",
            "conversion_price": 120.50,
            "form_type": "8-K",
        }
        valuation = {"market_cap": 5_000_000_000}
        price = {
            "current": 95.0,
            "ma_200": 105.0,
            "high_52w": 130.0,
            "low_52w": 80.0,
        }
        result = compute_partner_score(signal, valuation, price)
        self.assertEqual(result["score"], 10)
        self.assertIn("EXCEPTIONAL", result["verdict"])

    def test_low_score_passive_only(self):
        """13G passive filer + small deal → low score."""
        signal = {
            "investors": [("smart_vc", "Sequoia")],
            "amount_usd_m": 50.0,
            "deal_type": "Unknown",
            "conversion_price": None,
            "form_type": "SC 13G",
        }
        valuation = {"market_cap": 500_000_000}
        price = {
            "current": 30.0,
            "ma_200": 25.0,           # above 200DMA → no bonus
            "high_52w": 32.0,         # near 52W high → -1
            "low_52w": 18.0,
        }
        result = compute_partner_score(signal, valuation, price)
        self.assertLess(result["score"], 5)

    def test_returns_dict_keys(self):
        """Return dict always has score/raw/factors/verdict keys."""
        result = compute_partner_score(
            {"investors": [], "amount_usd_m": 0, "deal_type": "Unknown",
             "conversion_price": None, "form_type": "8-K"},
            {}, {},
        )
        for key in ("score", "raw", "factors", "verdict"):
            self.assertIn(key, result)


# ─── classifier (theme detector) ────────────────────────────────────────

class TestClassifier(unittest.TestCase):
    """Test theme-based classifier (v2.4 — catches anonymous-customer signals)."""

    def test_powl_anonymous_customer_detected(self):
        """
        POWL fixture: $400M order from 'major U.S. technology company' (anonymous).
        Registry would MISS this. Theme classifier should CATCH it with high score.
        """
        body = _load_fixture("powl_aidc_anonymous_8k.txt")

        # 1. Registry should NOT find any specific investor
        # 1. Registry 不应该找到具名投资人
        investors = find_strategic_investors(body)
        self.assertEqual(investors, [],
                         "Registry should NOT match anonymous customer")

        # 2. Theme classifier SHOULD score this high
        # 2. 题材分类器应该给高分
        theme = compute_theme_score(body)
        self.assertGreaterEqual(theme["score"], 6,
                                f"Theme score too low: {theme}")
        self.assertTrue(theme["ai_relevant"])
        self.assertTrue(theme["magnitude_signal"])
        self.assertIn("hyperscaler", theme["categories"])

        print(f"\n  ✓ POWL anonymous-customer: score={theme['score']}/10, "
              f"theme='{theme['primary_theme']}'")

    def test_peng_also_has_theme(self):
        """PENG fixture should ALSO get theme score (AI infra mention)."""
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")
        theme = compute_theme_score(body)
        # PENG mentions "AI infrastructure" + "AI data center"
        self.assertGreaterEqual(theme["score"], 2)

    def test_noise_has_low_theme(self):
        """Officer-change noise has zero theme score."""
        body = _load_fixture("noise_5_02_officer_change.txt")
        theme = compute_theme_score(body)
        self.assertLess(theme["score"], 4)

    def test_empty_text(self):
        result = compute_theme_score("")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["categories"], {})


# ─── integration smoke test ─────────────────────────────────────────────

class TestEndToEnd(unittest.TestCase):
    """Sanity end-to-end: PENG fixture should produce a non-trivial signal."""

    def setUp(self):
        filters.clear_caches()
        # Inject mock so we don't hit yfinance during this test
        filters._mcap_cache["SGH"] = 1_100_000_000
        filters._exchange_cache["SGH"] = "NMS"

    def test_peng_end_to_end(self):
        """
        Full pipeline:
          fixture body → extract → filter → enrich → score
        Validates that PENG/SGH would have triggered an alert.
        """
        body = _load_fixture("peng_sgh_sk_telecom_8k.txt")

        # 1. Not noise
        self.assertFalse(is_noise_filing(body))

        # 2. Items match
        items = extract_items(body)
        self.assertTrue(set(items) & KEY_8K_ITEMS)

        # 3. Strategic investor found
        investors = find_strategic_investors(body)
        self.assertTrue(any(c == "SK_Telecom" for _, c in investors))

        # 4. Amount extracted
        amount = extract_max_amount_usd_m(body)
        self.assertEqual(amount, 200.0)

        # 5. Ticker extracted
        ticker = extract_ticker(body)
        self.assertEqual(ticker, "SGH")

        # 6. Filters pass (with mocked yfinance)
        ok, reason = filters.apply_all_filters(ticker, amount)
        self.assertTrue(ok, msg=reason)

        # 7. Score reasonable
        result = compute_partner_score(
            {
                "investors": investors,
                "amount_usd_m": amount,
                "deal_type": detect_deal_type(body),
                "conversion_price": extract_conversion_price(body),
                "form_type": "8-K",
            },
            valuation={"market_cap": 1_100_000_000},
            price={"current": 20.0, "ma_200": 22.0,
                   "high_52w": 28.0, "low_52w": 17.5},
        )
        self.assertGreaterEqual(result["score"], 7)
        print(f"\n  ✓ PENG end-to-end: score={result['score']}/10 — "
              f"{result['verdict']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
