"""Tests for chain_filter (src/processors/chain_filter.py).

Run with:
    pytest src/processors/test_chain_filter.py -v
    python -m unittest src/processors/test_chain_filter.py -v
"""
import sys
import os
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from processors.chain_filter import is_chain, filter_chains  # noqa: E402


_KNOWN_CHAINS = [
    "One Hour Heating",
    "ARS",
    "Goettl",
    "Service Experts",
    "Aire Serv",
    "Lennox",
]


def _company(name, **kwargs):
    base = {"company_name": name, "phone": "(702) 555-0100"}
    base.update(kwargs)
    return base


# ── is_chain ───────────────────────────────────────────────────────────────────

class TestIsChain(unittest.TestCase):
    """Unit tests for is_chain()."""

    def test_exact_match(self):
        self.assertTrue(is_chain("ARS", _KNOWN_CHAINS))

    def test_chain_as_prefix_in_longer_name(self):
        self.assertTrue(is_chain("ARS Rescue Rooter", _KNOWN_CHAINS))

    def test_chain_as_suffix_in_name(self):
        self.assertTrue(is_chain("Henderson Aire Serv", _KNOWN_CHAINS))

    def test_chain_in_middle_of_name(self):
        self.assertTrue(is_chain("Goettl Air Conditioning & Plumbing", _KNOWN_CHAINS))

    def test_full_franchise_name(self):
        self.assertTrue(is_chain("One Hour Heating & Air Conditioning", _KNOWN_CHAINS))

    def test_local_business_not_a_chain(self):
        self.assertFalse(is_chain("Desert Air Solutions", _KNOWN_CHAINS))

    def test_local_business_with_common_words(self):
        self.assertFalse(is_chain("Nevada Comfort Climate Control", _KNOWN_CHAINS))

    def test_empty_name_returns_false(self):
        self.assertFalse(is_chain("", _KNOWN_CHAINS))

    def test_none_name_returns_false(self):
        self.assertFalse(is_chain(None, _KNOWN_CHAINS))

    def test_empty_chain_list_returns_false(self):
        self.assertFalse(is_chain("One Hour Heating", []))

    def test_case_insensitive_lowercase(self):
        self.assertTrue(is_chain("one hour heating & air", _KNOWN_CHAINS))

    def test_case_insensitive_uppercase(self):
        self.assertTrue(is_chain("ONE HOUR HEATING", _KNOWN_CHAINS))

    def test_case_insensitive_mixed(self):
        self.assertTrue(is_chain("Ars Rescue Rooter", _KNOWN_CHAINS))

    def test_word_boundary_prevents_false_positive_ars(self):
        # "Parsons HVAC" contains "ars" but not as a standalone word
        self.assertFalse(is_chain("Parsons HVAC", _KNOWN_CHAINS))

    def test_word_boundary_prevents_false_positive_goettl(self):
        # "Goettling" should not match "Goettl" (no word boundary after 'l')
        self.assertFalse(is_chain("Goettling Mechanical", _KNOWN_CHAINS))

    def test_service_word_alone_not_chain(self):
        self.assertFalse(is_chain("Nevada Service Co", _KNOWN_CHAINS))

    def test_lennox_dealer_detected(self):
        self.assertTrue(is_chain("Lennox Dealer Plus", _KNOWN_CHAINS))

    def test_multiple_chains_any_match_returns_true(self):
        brands = ["ARS", "Goettl", "Lennox"]
        self.assertTrue(is_chain("Lennox Dealer Plus", brands))

    def test_only_whitespace_name_returns_false(self):
        self.assertFalse(is_chain("   ", _KNOWN_CHAINS))

    def test_single_char_name_no_crash(self):
        self.assertFalse(is_chain("A", _KNOWN_CHAINS))

    def test_chain_with_punctuation_in_brand_list(self):
        brands = ["Smith & Sons"]
        self.assertTrue(is_chain("Smith & Sons HVAC", brands))

    def test_returns_bool(self):
        result = is_chain("Desert Air", _KNOWN_CHAINS)
        self.assertIsInstance(result, bool)


# ── filter_chains ──────────────────────────────────────────────────────────────

class TestFilterChains(unittest.TestCase):
    """Unit tests for filter_chains()."""

    def _config(self, brands=None):
        return {"chain_brands": brands if brands is not None else _KNOWN_CHAINS}

    def test_returns_all_companies_including_chains(self):
        companies = [
            _company("ARS Rescue Rooter"),
            _company("Desert Air Solutions"),
        ]
        result = filter_chains(companies, self._config())
        self.assertEqual(len(result), 2)

    def test_chain_flagged_true(self):
        companies = [_company("One Hour Heating & Air")]
        result = filter_chains(companies, self._config())
        self.assertTrue(result[0]["is_chain"])

    def test_local_business_flagged_false(self):
        companies = [_company("Desert Air Solutions")]
        result = filter_chains(companies, self._config())
        self.assertFalse(result[0]["is_chain"])

    def test_mixed_list_correctly_flagged(self):
        companies = [
            _company("ARS Rescue Rooter"),
            _company("Nevada Comfort Climate Control"),
            _company("Goettl Air Conditioning"),
        ]
        result = filter_chains(companies, self._config())
        flags = {r["company_name"]: r["is_chain"] for r in result}
        self.assertTrue(flags["ARS Rescue Rooter"])
        self.assertFalse(flags["Nevada Comfort Climate Control"])
        self.assertTrue(flags["Goettl Air Conditioning"])

    def test_empty_list_returns_empty(self):
        result = filter_chains([], self._config())
        self.assertEqual(result, [])

    def test_empty_chain_brands_no_flagging(self):
        companies = [_company("ARS Rescue Rooter")]
        result = filter_chains(companies, {"chain_brands": []})
        self.assertFalse(result[0]["is_chain"])

    def test_is_chain_key_set_on_all_companies(self):
        companies = [
            _company("Desert Air Solutions"),
            _company("Southwest Comfort Systems"),
        ]
        result = filter_chains(companies, self._config())
        for company in result:
            self.assertIn("is_chain", company)

    def test_missing_company_name_handled_gracefully(self):
        companies = [{"phone": "(702) 555-0100"}]
        result = filter_chains(companies, self._config())
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["is_chain"])

    def test_existing_fields_preserved(self):
        companies = [
            _company("Desert Air Solutions", email="owner@desert.example.com")
        ]
        result = filter_chains(companies, self._config())
        self.assertEqual(result[0]["email"], "owner@desert.example.com")

    def test_is_chain_flag_overwrites_existing(self):
        companies = [_company("ARS Rescue Rooter", is_chain=False)]
        result = filter_chains(companies, self._config())
        self.assertTrue(result[0]["is_chain"])

    def test_large_list_all_local_none_flagged(self):
        locals_ = [_company(f"Desert Air {i}") for i in range(20)]
        result = filter_chains(locals_, self._config())
        self.assertTrue(all(not r["is_chain"] for r in result))

    def test_chain_brands_from_config_key(self):
        companies = [_company("Custom Brand HVAC")]
        config = {"chain_brands": ["Custom Brand"]}
        result = filter_chains(companies, config)
        self.assertTrue(result[0]["is_chain"])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
