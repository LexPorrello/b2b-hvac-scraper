"""Tests for ICP Scorer (src/processors/icp_scorer.py).

Run with:
    pytest src/processors/test_icp_scorer.py -v
    python -m unittest src/processors/test_icp_scorer.py -v
"""
import sys
import os
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from processors.icp_scorer import calculate_icp_score, classify_tier, score_and_classify  # noqa: E402


_DEFAULT_CONFIG = {}

_FULL_CONFIG = {
    "scoring": {
        "weights": {
            "phone": 20,
            "email": 30,
            "website": 10,
            "reviews_high": 15,
            "reviews_med": 5,
            "hours": 10,
            "service_area": 10,
            "chain_penalty": -15,
        },
        "tiers": {
            "A": 60,
            "B": 40,
            "C": 20,
        }
    }
}


def _company(**kwargs):
    """Build a minimal company dict for scoring tests."""
    base = {
        "company_name": "Test HVAC Co",
        "phone": None,
        "email": None,
        "website": None,
        "review_count": 0,
        "business_hours": None,
        "service_area": None,
        "is_chain": False,
    }
    base.update(kwargs)
    return base


# ── calculate_icp_score ────────────────────────────────────────────────────────

class TestCalculateICPScore(unittest.TestCase):
    """Unit tests for calculate_icp_score()."""

    def test_all_signals_gives_95(self):
        # phone(20)+email(30)+website(10)+reviews_high(15)+hours(10)+service(10)=95
        c = _company(
            phone="(702) 555-0100",
            email="owner@hvac.example.com",
            website="https://hvac.example.com",
            review_count=100,
            business_hours="Mon-Fri 8am-6pm",
            service_area="Las Vegas, NV",
        )
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 95)

    def test_zero_signals_zero_score(self):
        self.assertEqual(calculate_icp_score(_company(), _DEFAULT_CONFIG), 0)

    def test_phone_only_gives_20(self):
        c = _company(phone="(702) 555-0100")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 20)

    def test_email_only_gives_30(self):
        c = _company(email="owner@example.com")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 30)

    def test_website_only_gives_10(self):
        c = _company(website="https://example.com")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 10)

    def test_phone_and_email_gives_50(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 50)

    def test_phone_email_website_gives_60(self):
        c = _company(
            phone="(702) 555-0100",
            email="o@example.com",
            website="https://example.com",
        )
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 60)

    def test_high_reviews_50_plus_gives_15(self):
        c = _company(review_count=50)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 15)

    def test_high_reviews_100_gives_15(self):
        c = _company(review_count=100)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 15)

    def test_medium_reviews_10_gives_5(self):
        c = _company(review_count=10)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 5)

    def test_medium_reviews_49_gives_5(self):
        c = _company(review_count=49)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 5)

    def test_low_reviews_9_gives_0(self):
        c = _company(review_count=9)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_zero_reviews_gives_0(self):
        c = _company(review_count=0)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_exactly_50_reviews_is_high_tier(self):
        c = _company(review_count=50)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 15)

    def test_exactly_10_reviews_is_medium_tier(self):
        c = _company(review_count=10)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 5)

    def test_service_area_adds_10(self):
        c = _company(service_area="Las Vegas, NV")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 10)

    def test_business_hours_adds_10(self):
        c = _company(business_hours="Mon-Fri 8am-5pm")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 10)

    def test_chain_penalty_subtracts_15(self):
        c = _company(phone="(702) 555-0100", is_chain=True)
        # 20 (phone) - 15 (chain) = 5
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 5)

    def test_chain_penalty_floored_at_zero(self):
        c = _company(is_chain=True)
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_chain_with_full_data_reduces_score(self):
        c = _company(
            phone="(702) 555-0100",
            email="o@example.com",
            website="https://example.com",
            is_chain=True,
        )
        score = calculate_icp_score(c, _DEFAULT_CONFIG)
        # 20+30+10 - 15 = 45
        self.assertEqual(score, 45)

    def test_score_never_exceeds_100(self):
        c = _company(
            phone="(702) 555-0100",
            email="o@example.com",
            website="https://example.com",
            review_count=999,
            business_hours="Always open",
            service_area="Las Vegas, NV",
        )
        self.assertLessEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 100)

    def test_score_never_below_zero(self):
        c = _company(is_chain=True)
        self.assertGreaterEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_custom_phone_weight_honored(self):
        config = {"scoring": {"weights": {"phone": 40}}}
        c = _company(phone="(702) 555-0100")
        self.assertEqual(calculate_icp_score(c, config), 40)

    def test_custom_email_weight_honored(self):
        config = {"scoring": {"weights": {"email": 50}}}
        c = _company(email="o@example.com")
        self.assertEqual(calculate_icp_score(c, config), 50)

    def test_custom_chain_penalty_honored(self):
        config = {"scoring": {"weights": {"chain_penalty": -5}}}
        c = _company(phone="(702) 555-0100", is_chain=True)
        # 20 + (-5) = 15
        self.assertEqual(calculate_icp_score(c, config), 15)

    def test_empty_phone_string_not_counted(self):
        c = _company(phone="")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_empty_email_string_not_counted(self):
        c = _company(email="")
        self.assertEqual(calculate_icp_score(c, _DEFAULT_CONFIG), 0)

    def test_results_consistent_across_calls(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        score1 = calculate_icp_score(c, _DEFAULT_CONFIG)
        score2 = calculate_icp_score(c, _DEFAULT_CONFIG)
        self.assertEqual(score1, score2)


# ── classify_tier ──────────────────────────────────────────────────────────────

class TestClassifyTier(unittest.TestCase):
    """Unit tests for classify_tier()."""

    def test_score_60_is_tier_a(self):
        self.assertEqual(classify_tier(60, _DEFAULT_CONFIG), "A")

    def test_score_95_is_tier_a(self):
        self.assertEqual(classify_tier(95, _DEFAULT_CONFIG), "A")

    def test_score_100_is_tier_a(self):
        self.assertEqual(classify_tier(100, _DEFAULT_CONFIG), "A")

    def test_score_59_is_tier_b(self):
        self.assertEqual(classify_tier(59, _DEFAULT_CONFIG), "B")

    def test_score_40_is_tier_b(self):
        self.assertEqual(classify_tier(40, _DEFAULT_CONFIG), "B")

    def test_score_39_is_tier_c(self):
        self.assertEqual(classify_tier(39, _DEFAULT_CONFIG), "C")

    def test_score_20_is_tier_c(self):
        self.assertEqual(classify_tier(20, _DEFAULT_CONFIG), "C")

    def test_score_19_is_reject(self):
        self.assertEqual(classify_tier(19, _DEFAULT_CONFIG), "Reject")

    def test_score_0_is_reject(self):
        self.assertEqual(classify_tier(0, _DEFAULT_CONFIG), "Reject")

    def test_custom_tier_a_threshold(self):
        config = {"scoring": {"tiers": {"A": 80, "B": 60, "C": 40}}}
        self.assertEqual(classify_tier(80, config), "A")
        self.assertEqual(classify_tier(79, config), "B")

    def test_custom_tier_b_threshold(self):
        config = {"scoring": {"tiers": {"A": 80, "B": 60, "C": 40}}}
        self.assertEqual(classify_tier(60, config), "B")
        self.assertEqual(classify_tier(59, config), "C")

    def test_custom_tier_c_threshold(self):
        config = {"scoring": {"tiers": {"A": 80, "B": 60, "C": 40}}}
        self.assertEqual(classify_tier(40, config), "C")
        self.assertEqual(classify_tier(39, config), "Reject")

    def test_tier_a_boundary_is_inclusive(self):
        self.assertEqual(classify_tier(60, _DEFAULT_CONFIG), "A")
        self.assertEqual(classify_tier(59, _DEFAULT_CONFIG), "B")

    def test_tier_b_boundary_is_inclusive(self):
        self.assertEqual(classify_tier(40, _DEFAULT_CONFIG), "B")
        self.assertEqual(classify_tier(39, _DEFAULT_CONFIG), "C")

    def test_tier_c_boundary_is_inclusive(self):
        self.assertEqual(classify_tier(20, _DEFAULT_CONFIG), "C")
        self.assertEqual(classify_tier(19, _DEFAULT_CONFIG), "Reject")

    def test_returns_string(self):
        for score in (0, 20, 40, 60, 100):
            tier = classify_tier(score, _DEFAULT_CONFIG)
            self.assertIsInstance(tier, str)


# ── score_and_classify ─────────────────────────────────────────────────────────

class TestScoreAndClassify(unittest.TestCase):
    """Unit tests for score_and_classify()."""

    def test_enriches_company_with_icp_score(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertIn("icp_score", result)
        self.assertIsInstance(result["icp_score"], int)

    def test_enriches_company_with_tier(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertIn("tier", result)
        self.assertIn(result["tier"], ["A", "B", "C", "Reject"])

    def test_returns_same_company_dict(self):
        c = _company(phone="(702) 555-0100")
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertIs(result, c)

    def test_tier_a_full_contact_company(self):
        c = _company(
            phone="(702) 555-0100",
            email="o@example.com",
            website="https://example.com",
            review_count=100,
            service_area="Las Vegas, NV",
        )
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertEqual(result["tier"], "A")

    def test_reject_company_no_contact_data(self):
        c = _company()
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertEqual(result["tier"], "Reject")
        self.assertEqual(result["icp_score"], 0)

    def test_icp_score_matches_calculate(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        expected_score = calculate_icp_score(c.copy(), _DEFAULT_CONFIG)
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertEqual(result["icp_score"], expected_score)

    def test_tier_matches_classify(self):
        c = _company(phone="(702) 555-0100", email="o@example.com")
        score = calculate_icp_score(c.copy(), _DEFAULT_CONFIG)
        expected_tier = classify_tier(score, _DEFAULT_CONFIG)
        result = score_and_classify(c, _DEFAULT_CONFIG)
        self.assertEqual(result["tier"], expected_tier)

    def test_chain_company_gets_reduced_score(self):
        c_chain = _company(phone="(702) 555-0100", email="o@example.com", is_chain=True)
        c_local = _company(phone="(702) 555-0100", email="o@example.com", is_chain=False)
        r_chain = score_and_classify(c_chain, _DEFAULT_CONFIG)
        r_local = score_and_classify(c_local, _DEFAULT_CONFIG)
        self.assertLess(r_chain["icp_score"], r_local["icp_score"])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
