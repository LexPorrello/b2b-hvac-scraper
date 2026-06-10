"""Tests for DedupEngine (src/processors/deduplicator.py).

Run with:
    pytest src/processors/test_deduplicator.py -v
    python -m unittest src/processors/test_deduplicator.py -v
"""
import sys
import os
import tempfile
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from processors.deduplicator import DedupEngine  # noqa: E402


def _make_engine():
    """Create a DedupEngine with a fresh isolated temp database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_dedup.db")
    return DedupEngine(db_path=db_path)


def _biz(**kwargs):
    """Minimal business dict for dedup tests."""
    base = {
        "company_name": "Test HVAC Co",
        "phone": "(702) 555-0100",
        "email": "owner@testhvac.example.com",
        "website": "https://testhvac.example.com",
        "review_count": 20,
        "rating": 4.5,
    }
    base.update(kwargs)
    return base


# ── normalize_name ─────────────────────────────────────────────────────────────

class TestNormalizeName(unittest.TestCase):
    """Tests for DedupEngine.normalize_name()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_lowercases_input(self):
        result = self.engine.normalize_name("DESERT AIR SOLUTIONS")
        self.assertEqual(result, result.lower())

    def test_removes_llc_suffix(self):
        result = self.engine.normalize_name("Southwest HVAC LLC")
        self.assertNotIn("llc", result)

    def test_removes_inc_suffix(self):
        result = self.engine.normalize_name("Nevada Air Inc")
        self.assertNotIn("inc", result)

    def test_removes_corp_suffix(self):
        result = self.engine.normalize_name("Desert Cooling Corp")
        self.assertNotIn("corp", result)

    def test_removes_hvac_word(self):
        result = self.engine.normalize_name("Desert Air HVAC")
        self.assertNotIn("hvac", result)

    def test_removes_air_conditioning(self):
        result = self.engine.normalize_name("Las Vegas Air Conditioning")
        self.assertNotIn("air conditioning", result)

    def test_removes_heating_suffix(self):
        result = self.engine.normalize_name("Southwest Heating")
        self.assertNotIn("heating", result)

    def test_removes_punctuation(self):
        result = self.engine.normalize_name("Smith & Sons, HVAC!")
        self.assertNotIn("!", result)
        self.assertNotIn(",", result)

    def test_collapses_extra_whitespace(self):
        result = self.engine.normalize_name("  Desert   Air  ")
        self.assertNotIn("  ", result)

    def test_strips_leading_trailing_whitespace(self):
        result = self.engine.normalize_name("  Desert Air  ")
        self.assertEqual(result, result.strip())

    def test_empty_string_returns_empty(self):
        result = self.engine.normalize_name("")
        self.assertEqual(result, "")

    def test_same_name_different_suffixes_match(self):
        n1 = self.engine.normalize_name("Desert Air LLC")
        n2 = self.engine.normalize_name("Desert Air Inc")
        self.assertEqual(n1, n2)

    def test_result_is_string(self):
        result = self.engine.normalize_name("Test HVAC")
        self.assertIsInstance(result, str)


# ── is_chain ───────────────────────────────────────────────────────────────────

class TestDedupIsChain(unittest.TestCase):
    """Tests for DedupEngine.is_chain()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_carrier_is_chain(self):
        self.assertTrue(self.engine.is_chain("Carrier HVAC Services"))

    def test_lennox_is_chain(self):
        self.assertTrue(self.engine.is_chain("Lennox Dealer"))

    def test_trane_is_chain(self):
        self.assertTrue(self.engine.is_chain("Trane Technologies"))

    def test_goodman_is_chain(self):
        self.assertTrue(self.engine.is_chain("Goodman Manufacturing Rep"))

    def test_franchise_keyword_is_chain(self):
        self.assertTrue(self.engine.is_chain("Nevada Franchise Heating"))

    def test_dealer_network_is_chain(self):
        self.assertTrue(self.engine.is_chain("Southwest Dealer Network HVAC"))

    def test_local_business_not_chain(self):
        self.assertFalse(self.engine.is_chain("Desert Air Solutions"))

    def test_local_business_with_common_word(self):
        self.assertFalse(self.engine.is_chain("Silver State Air & Heat"))

    def test_case_insensitive_upper(self):
        self.assertTrue(self.engine.is_chain("CARRIER AIR"))

    def test_case_insensitive_lower(self):
        self.assertTrue(self.engine.is_chain("lennox service"))

    def test_empty_string_returns_false(self):
        self.assertFalse(self.engine.is_chain(""))

    def test_york_is_chain(self):
        self.assertTrue(self.engine.is_chain("York HVAC Dealer"))

    def test_daikin_is_chain(self):
        self.assertTrue(self.engine.is_chain("Daikin Mini-Split Installer"))


# ── name_similarity ────────────────────────────────────────────────────────────

class TestNameSimilarity(unittest.TestCase):
    """Tests for DedupEngine.name_similarity()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_identical_names_return_1_0(self):
        sim = self.engine.name_similarity("Desert Air Solutions", "Desert Air Solutions")
        self.assertAlmostEqual(sim, 1.0)

    def test_completely_different_names_low_similarity(self):
        sim = self.engine.name_similarity("Desert Air Solutions", "Plumbing Pro Services")
        self.assertLess(sim, 0.5)

    def test_llc_suffix_normalized_away(self):
        sim = self.engine.name_similarity(
            "Desert Air Solutions LLC", "Desert Air Solutions"
        )
        self.assertGreater(sim, 0.95)

    def test_similarity_is_symmetric(self):
        sim1 = self.engine.name_similarity("Alpha HVAC Co", "Beta Services Inc")
        sim2 = self.engine.name_similarity("Beta Services Inc", "Alpha HVAC Co")
        self.assertAlmostEqual(sim1, sim2, places=5)

    def test_slight_variation_high_similarity(self):
        sim = self.engine.name_similarity(
            "Southwest Comfort Systems", "Southwest Comfort System"
        )
        self.assertGreater(sim, 0.85)

    def test_returns_float_between_0_and_1(self):
        sim = self.engine.name_similarity("Alpha HVAC", "Beta Air")
        self.assertGreaterEqual(sim, 0.0)
        self.assertLessEqual(sim, 1.0)

    def test_abbreviated_vs_full_moderately_similar(self):
        sim = self.engine.name_similarity("SW Comfort", "Southwest Comfort Systems")
        self.assertLess(sim, 0.90)

    def test_empty_strings_not_crash(self):
        sim = self.engine.name_similarity("", "")
        self.assertGreaterEqual(sim, 0.0)


# ── find_duplicate ─────────────────────────────────────────────────────────────

class TestFindDuplicate(unittest.TestCase):
    """Tests for DedupEngine.find_duplicate()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_no_existing_records_returns_none(self):
        b = _biz(phone="(702) 555-7777")
        result = self.engine.find_duplicate(b)
        self.assertIsNone(result)

    def test_phone_duplicate_found(self):
        b = _biz(phone="(702) 555-0777")
        self.engine._insert_record(b, "yelp")
        result = self.engine.find_duplicate(b)
        self.assertIsNotNone(result)
        self.assertEqual(result["phone"], "(702) 555-0777")

    def test_email_duplicate_found(self):
        b = _biz(email="unique@hvactest.example.com", phone="(702) 555-0001")
        self.engine._insert_record(b, "yelp")
        b2 = dict(b)
        b2["phone"] = "(702) 555-0002"  # different phone, same email
        result = self.engine.find_duplicate(b2)
        self.assertIsNotNone(result)

    def test_different_phone_and_email_returns_none(self):
        b = _biz(phone="(702) 555-0001", email="a@example.com")
        self.engine._insert_record(b, "yelp")
        b2 = _biz(
            company_name="Unrelated HVAC",
            phone="(702) 555-9999",
            email="z@other.example.com",
        )
        result = self.engine.find_duplicate(b2)
        self.assertIsNone(result)

    def test_result_has_id_field(self):
        b = _biz(phone="(702) 555-1234")
        self.engine._insert_record(b, "yelp")
        result = self.engine.find_duplicate(b)
        self.assertIn("id", result)


# ── add_or_merge ───────────────────────────────────────────────────────────────

class TestAddOrMerge(unittest.TestCase):
    """Tests for DedupEngine.add_or_merge()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_chain_rejected(self):
        b = _biz(company_name="Carrier HVAC Services")
        result = self.engine.add_or_merge(b, "yelp")
        self.assertTrue(result.get("rejected"))
        self.assertEqual(result.get("reason"), "chain/franchise")

    def test_lennox_chain_rejected(self):
        b = _biz(company_name="Lennox Dealer Shop")
        result = self.engine.add_or_merge(b, "bbb")
        self.assertTrue(result.get("rejected"))

    def test_new_business_marked_new(self):
        b = _biz(phone="(702) 555-0100")
        result = self.engine.add_or_merge(b, "yelp")
        self.assertTrue(result.get("new"))

    def test_new_business_not_marked_merged(self):
        b = _biz(phone="(702) 555-0100")
        result = self.engine.add_or_merge(b, "yelp")
        self.assertFalse(result.get("merged", False))

    def test_duplicate_by_phone_merged(self):
        b1 = _biz(company_name="Test HVAC Co", phone="(702) 555-0200")
        b2 = _biz(company_name="Test HVAC Company LLC", phone="(702) 555-0200")
        self.engine.add_or_merge(b1, "yelp")
        result = self.engine.add_or_merge(b2, "bbb")
        self.assertTrue(result.get("merged"))

    def test_duplicate_by_email_merged(self):
        b1 = _biz(company_name="Alpha HVAC", phone="(702) 555-0111",
                  email="info@alphahvac.example.com")
        b2 = _biz(company_name="Alpha Air Solutions", phone="(702) 555-0222",
                  email="info@alphahvac.example.com")
        self.engine.add_or_merge(b1, "yelp")
        result = self.engine.add_or_merge(b2, "angi")
        self.assertTrue(result.get("merged"))

    def test_merged_result_has_original_id(self):
        b1 = _biz(company_name="Beta HVAC", phone="(702) 555-0300")
        b2 = _biz(company_name="Beta HVAC LLC", phone="(702) 555-0300")
        self.engine.add_or_merge(b1, "yelp")
        result = self.engine.add_or_merge(b2, "bbb")
        self.assertIn("original_id", result)

    def test_source_tracked_after_merge(self):
        b1 = _biz(company_name="Gamma HVAC", phone="(702) 555-0400")
        b2 = _biz(company_name="Gamma HVAC LLC", phone="(702) 555-0400")
        self.engine.add_or_merge(b1, "yelp")
        result = self.engine.add_or_merge(b2, "bbb")
        self.assertIn("bbb", result.get("sources", ""))

    def test_unique_business_stored(self):
        b = _biz(phone="(702) 555-9001", email="unique9001@hvac.example.com")
        self.engine.add_or_merge(b, "yelp")
        stats = self.engine.get_stats()
        self.assertGreater(stats["total_unique_businesses"], 0)

    def test_two_unique_businesses_stored(self):
        b1 = _biz(phone="(702) 555-9002", email="a9002@hvac.example.com",
                  company_name="First HVAC")
        b2 = _biz(phone="(702) 555-9003", email="b9003@hvac.example.com",
                  company_name="Second HVAC")
        self.engine.add_or_merge(b1, "yelp")
        self.engine.add_or_merge(b2, "bbb")
        stats = self.engine.get_stats()
        self.assertEqual(stats["total_unique_businesses"], 2)


# ── _merge_businesses ──────────────────────────────────────────────────────────

class TestMergeBusinesses(unittest.TestCase):
    """Tests for DedupEngine._merge_businesses()."""

    def setUp(self):
        self.engine = _make_engine()

    def _existing(self, **kwargs):
        base = {
            "id": 1,
            "normalized_name": "test hvac",
            "phone": "(702) 555-0100",
            "email": None,
            "website": None,
            "reviews": 10,
            "rating": 4.0,
            "sources": "yelp",
            "last_seen": "2024-01-01T00:00:00",
        }
        base.update(kwargs)
        return base

    def test_sources_merged_include_both(self):
        existing = self._existing(sources="yelp")
        new = {"phone": "(702) 555-0100", "email": None, "website": None,
               "reviews": 10, "rating": 4.0}
        merged = self.engine._merge_businesses(existing, new, "bbb")
        self.assertIn("bbb", merged["sources"])
        self.assertIn("yelp", merged["sources"])

    def test_email_filled_from_new_when_missing(self):
        existing = self._existing(email=None)
        new = {"email": "owner@hvac.example.com", "phone": None,
               "website": None, "reviews": 5, "rating": 4.0}
        merged = self.engine._merge_businesses(existing, new, "bbb")
        self.assertEqual(merged["email"], "owner@hvac.example.com")

    def test_existing_email_preserved_when_new_is_none(self):
        existing = self._existing(email="old@hvac.example.com")
        new = {"email": None, "phone": None, "website": None,
               "reviews": 5, "rating": 4.0}
        merged = self.engine._merge_businesses(existing, new, "bbb")
        self.assertEqual(merged["email"], "old@hvac.example.com")

    def test_higher_review_count_kept(self):
        existing = self._existing(reviews=10)
        new = {"reviews": 25, "phone": None, "email": None,
               "website": None, "rating": 4.5}
        merged = self.engine._merge_businesses(existing, new, "angi")
        self.assertEqual(merged["reviews"], 25)

    def test_lower_review_count_not_overwritten(self):
        existing = self._existing(reviews=50)
        new = {"reviews": 10, "phone": None, "email": None,
               "website": None, "rating": 4.0}
        merged = self.engine._merge_businesses(existing, new, "angi")
        self.assertEqual(merged["reviews"], 50)

    def test_last_seen_updated(self):
        existing = self._existing(last_seen="2024-01-01T00:00:00")
        new = {"reviews": 5, "phone": None, "email": None, "website": None, "rating": 4.0}
        merged = self.engine._merge_businesses(existing, new, "bbb")
        self.assertNotEqual(merged["last_seen"], "2024-01-01T00:00:00")

    def test_sources_sorted_deduped(self):
        existing = self._existing(sources="yelp")
        new = {"reviews": 5, "phone": None, "email": None, "website": None, "rating": 4.0}
        # Adding yelp again should not create duplicate
        merged = self.engine._merge_businesses(existing, new, "yelp")
        sources_list = [s for s in merged["sources"].split(", ") if s]
        self.assertEqual(len(sources_list), len(set(sources_list)))

    def test_returns_dict(self):
        existing = self._existing()
        new = {"reviews": 5, "phone": None, "email": None, "website": None, "rating": 4.0}
        result = self.engine._merge_businesses(existing, new, "bbb")
        self.assertIsInstance(result, dict)


# ── get_stats ──────────────────────────────────────────────────────────────────

class TestGetStats(unittest.TestCase):
    """Tests for DedupEngine.get_stats()."""

    def test_empty_engine_has_zero_businesses(self):
        engine = _make_engine()
        stats = engine.get_stats()
        self.assertEqual(stats["total_unique_businesses"], 0)

    def test_stats_has_required_keys(self):
        engine = _make_engine()
        stats = engine.get_stats()
        self.assertIn("total_unique_businesses", stats)
        self.assertIn("data_sources_used", stats)
        self.assertIn("chains_filtered", stats)

    def test_stats_increment_after_adding_businesses(self):
        engine = _make_engine()
        engine.add_or_merge(_biz(phone="(702) 555-1111", email="a@example.com",
                                  company_name="First HVAC"), "yelp")
        engine.add_or_merge(_biz(phone="(702) 555-2222", email="b@example.com",
                                  company_name="Second HVAC"), "bbb")
        stats = engine.get_stats()
        self.assertEqual(stats["total_unique_businesses"], 2)

    def test_chains_filtered_label_present(self):
        engine = _make_engine()
        stats = engine.get_stats()
        self.assertIsNotNone(stats["chains_filtered"])

    def test_chain_does_not_increment_unique_count(self):
        engine = _make_engine()
        engine.add_or_merge(_biz(company_name="Carrier HVAC Services"), "yelp")
        stats = engine.get_stats()
        self.assertEqual(stats["total_unique_businesses"], 0)


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
