"""Tests for BBBAdapter.

Run with:
    python -m unittest src/adapters/test_bbb.py -v
    # or from the src/ directory:
    python -m unittest adapters.test_bbb -v
"""
import sys
import os
import unittest

# Support running from repo root or from the src/ directory
_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapters.bbb import BBBAdapter  # noqa: E402

# ── Shared fixtures ────────────────────────────────────────────────────────────

_BASE_CONFIG = {
    "enabled": True,
    "results_per_market": 50,
    "category": "heating-air-conditioning",
    "radius_miles": 25,
}

# Minimal realistic BBB search-results HTML (one card, all fields present)
_HTML_SINGLE_CARD = """
<html><body>
<div data-testid="serp-result-card">
  <a href="/biz/nevada-desert-air-heating-las-vegas-88-1000012345"
     data-testid="bizName">Nevada Desert Air &amp; Heating</a>
  <div data-testid="BBBRating">A+</div>
  <div data-testid="address">4210 W Flamingo Rd, Las Vegas, NV 89103</div>
  <a href="tel:7025550201">(702) 555-0201</a>
  <a href="mailto:contact@nevadadesertair.example.com">Email Us</a>
  <a href="https://nevadadesertair.example.com" data-testid="bizWebsite">
    Visit Website
  </a>
  <span>Accredited since 2012</span>
  <div data-testid="complaintCount">0 Complaints</div>
  <div data-testid="reviewCount">42 Customer Reviews</div>
</div>
</body></html>
"""

# Two cards, second has no email and uses alternate selectors
_HTML_TWO_CARDS = """
<html><body>
<div data-testid="serp-result-card">
  <a href="/biz/southwest-comfort-systems-las-vegas-88-2000023456"
     data-testid="bizName">Southwest Comfort Systems</a>
  <div data-testid="BBBRating">A</div>
  <div data-testid="address">2890 S Rainbow Blvd, Las Vegas, NV 89146</div>
  <a href="tel:17025550202">(702) 555-0202</a>
  <a href="https://swcomfort.example.com" data-testid="bizWebsite">Website</a>
  <span>Accredited since 2017</span>
  <div data-testid="complaintCount">2 Complaints</div>
  <div data-testid="reviewCount">18 Customer Reviews</div>
</div>
<div data-testid="serp-result-card">
  <a href="/biz/vegas-valley-mechanical-las-vegas-88-3000034567"
     data-testid="bizName">Vegas Valley Mechanical</a>
  <div data-testid="BBBRating">A+</div>
  <div data-testid="address">5600 McLeod Dr, Las Vegas, NV 89120</div>
  <a href="tel:7025550203">(702) 555-0203</a>
  <a href="mailto:info@vegasvalleymech.example.com">Contact</a>
  <span>Accredited since 2009</span>
  <div data-testid="complaintCount">1 Complaints</div>
  <div data-testid="reviewCount">89 Reviews</div>
</div>
</body></html>
"""

# Card where chain detection should fire
_HTML_CHAIN_CARD = """
<html><body>
<div data-testid="serp-result-card">
  <a href="/biz/one-hour-heating-air-conditioning-las-vegas-88-9000099999"
     data-testid="bizName">One Hour Heating &amp; Air Conditioning</a>
  <div data-testid="BBBRating">B+</div>
  <div data-testid="address">3700 S Valley View Blvd, Las Vegas, NV 89103</div>
  <a href="tel:7025550999">(702) 555-0999</a>
  <span>Accredited since 2019</span>
  <div data-testid="complaintCount">25 Complaints</div>
  <div data-testid="reviewCount">3000 Reviews</div>
</div>
</body></html>
"""

# Empty results page
_HTML_EMPTY = "<html><body><div class='no-results'>No businesses found.</div></body></html>"

# Page with next-page link
_HTML_HAS_NEXT = """
<html><body>
<div data-testid="serp-result-card">
  <a href="/biz/placeholder" data-testid="bizName">Placeholder HVAC</a>
  <div data-testid="BBBRating">A</div>
</div>
<a rel="next" href="?page=2">Next</a>
</body></html>
"""

# Page without next-page link
_HTML_NO_NEXT = """
<html><body>
<div data-testid="serp-result-card">
  <a href="/biz/last-page-hvac" data-testid="bizName">Last Page HVAC</a>
  <div data-testid="BBBRating">A-</div>
</div>
</body></html>
"""


# ── Trust score tests ──────────────────────────────────────────────────────────

class TestCalculateTrustScore(unittest.TestCase):
    """Unit tests for BBBAdapter.calculate_trust_score."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_perfect_score_a_plus_20_years_zero_complaints(self):
        # A+ = 50, 20 yrs = 30, 0 complaints = +20 → 100
        score = self.adapter.calculate_trust_score("A+", 20, 0)
        self.assertEqual(score, 100)

    def test_a_rating_zero_complaints_moderate_tenure(self):
        # A = 45, 10 yrs = 15, 0 complaints = +20 → 80
        score = self.adapter.calculate_trust_score("A", 10, 0)
        self.assertEqual(score, 80)

    def test_a_minus_rating_7_years_2_complaints(self):
        # A- = 40, 7 yrs = 10.5 → 10 (int), 2 complaints = +10 → 60
        score = self.adapter.calculate_trust_score("A-", 7, 2)
        self.assertEqual(score, 60)

    def test_b_plus_rating_5_years_5_complaints(self):
        # B+ = 32, 5 yrs = 7.5 → 7 (int), 5 complaints = +5 → 44
        score = self.adapter.calculate_trust_score("B+", 5, 5)
        self.assertEqual(score, 44)

    def test_f_rating_no_accreditation_many_complaints(self):
        # F = 0, 0 yrs = 0, 25 complaints = -20 → 0 (clamped)
        score = self.adapter.calculate_trust_score("F", 0, 25)
        self.assertEqual(score, 0)

    def test_nr_rating_not_accredited_zero_complaints(self):
        # NR = 0, 0 yrs = 0, 0 complaints = +20 → 20
        score = self.adapter.calculate_trust_score("NR", 0, 0)
        self.assertEqual(score, 20)

    def test_none_rating_treated_as_nr(self):
        score_nr = self.adapter.calculate_trust_score("NR", 0, 0)
        score_none = self.adapter.calculate_trust_score(None, 0, 0)
        self.assertEqual(score_nr, score_none)

    def test_complaint_penalty_tiers(self):
        base_rating, base_years = "A", 0
        # 0 complaints → +20
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 0), 65
        )
        # 1-2 complaints → +10
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 1), 55
        )
        # 3-5 complaints → +5
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 4), 50
        )
        # 6-10 complaints → neutral
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 8), 45
        )
        # 11-20 complaints → -5
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 15), 40
        )
        # 21+ complaints → -20
        self.assertEqual(
            self.adapter.calculate_trust_score(base_rating, base_years, 50), 25
        )

    def test_score_always_in_0_100_range(self):
        for rating in ("A+", "A", "B", "C", "D", "F", "NR"):
            for years in (0, 5, 25):
                for complaints in (0, 5, 100):
                    score = self.adapter.calculate_trust_score(
                        rating, years, complaints
                    )
                    self.assertGreaterEqual(score, 0)
                    self.assertLessEqual(score, 100)

    def test_accreditation_capped_at_30_points(self):
        # 50 years should give same accreditation points as 20 years (30 max)
        score_20 = self.adapter.calculate_trust_score("NR", 20, 10)
        score_50 = self.adapter.calculate_trust_score("NR", 50, 10)
        self.assertEqual(score_20, score_50)


# ── Chain detection tests ──────────────────────────────────────────────────────

class TestIsChainOrFranchise(unittest.TestCase):
    """Unit tests for BBBAdapter.is_chain_or_franchise."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    # Known chains
    def test_one_hour_heating_full_name(self):
        self.assertTrue(
            self.adapter.is_chain_or_franchise("One Hour Heating & Air Conditioning")
        )

    def test_ars_exact(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("ARS"))

    def test_ars_rescue_rooter(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("ARS Rescue Rooter"))

    def test_goettl(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("Goettl Air Conditioning"))

    def test_service_experts(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("Service Experts Heating & Air"))

    def test_aire_serv(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("Aire Serv of Las Vegas"))

    def test_servpro(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("SERVPRO of Henderson"))

    # Local businesses — must NOT be flagged
    def test_local_business_not_a_chain(self):
        self.assertFalse(
            self.adapter.is_chain_or_franchise("Desert Air Solutions")
        )

    def test_local_business_ars_not_in_name(self):
        # "Parsons HVAC" contains "ars" but not as a word boundary
        self.assertFalse(self.adapter.is_chain_or_franchise("Parsons HVAC"))

    def test_local_business_nevada_comfort(self):
        self.assertFalse(
            self.adapter.is_chain_or_franchise("Nevada Comfort Climate Control")
        )

    def test_empty_string_returns_false(self):
        self.assertFalse(self.adapter.is_chain_or_franchise(""))

    def test_none_returns_false(self):
        self.assertFalse(self.adapter.is_chain_or_franchise(None))

    def test_config_chain_brands_honored(self):
        config_with_extra = dict(_BASE_CONFIG, chain_brands=["Desert King HVAC"])
        adapter = BBBAdapter(config_with_extra)
        self.assertTrue(adapter.is_chain_or_franchise("Desert King HVAC Solutions"))

    def test_franchise_keyword_detected(self):
        self.assertTrue(
            self.adapter.is_chain_or_franchise("Cool Air Franchising LLC")
        )

    def test_case_insensitive(self):
        self.assertTrue(self.adapter.is_chain_or_franchise("one hour heating"))
        self.assertTrue(self.adapter.is_chain_or_franchise("ONE HOUR HEATING"))


# ── HTML extraction tests ──────────────────────────────────────────────────────

class TestExtractBusinessData(unittest.TestCase):
    """Tests for extract_business_data and _parse_business_card."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_single_card_extracts_name(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(len(businesses), 1)
        self.assertEqual(businesses[0]["name"], "Nevada Desert Air & Heating")

    def test_single_card_extracts_phone(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(businesses[0]["phone"], "(702) 555-0201")

    def test_single_card_extracts_email(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(
            businesses[0]["email"], "contact@nevadadesertair.example.com"
        )

    def test_single_card_extracts_website(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(
            businesses[0]["website"], "https://nevadadesertair.example.com"
        )

    def test_single_card_extracts_bbb_rating(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(businesses[0]["bbb_rating"], "A+")

    def test_single_card_extracts_complaint_count(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(businesses[0]["complaint_count"], 0)

    def test_single_card_extracts_review_count(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(businesses[0]["review_count"], 42)

    def test_single_card_extracts_address(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertIn("Las Vegas", businesses[0]["address"])

    def test_single_card_parses_city_state_zip(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        biz = businesses[0]
        self.assertEqual(biz["city"], "Las Vegas")
        self.assertEqual(biz["state"], "NV")
        self.assertEqual(biz["zip_code"], "89103")

    def test_single_card_extracts_source_id(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        self.assertEqual(
            businesses[0]["source_id"],
            "nevada-desert-air-heating-las-vegas-88-1000012345",
        )

    def test_single_card_source_url_is_absolute(self):
        businesses = self.adapter.extract_business_data(_HTML_SINGLE_CARD)
        source_url = businesses[0]["source_url"]
        self.assertTrue(source_url.startswith("http"))

    def test_two_cards_returns_two_businesses(self):
        businesses = self.adapter.extract_business_data(_HTML_TWO_CARDS)
        self.assertEqual(len(businesses), 2)

    def test_two_cards_names_correct(self):
        businesses = self.adapter.extract_business_data(_HTML_TWO_CARDS)
        names = [b["name"] for b in businesses]
        self.assertIn("Southwest Comfort Systems", names)
        self.assertIn("Vegas Valley Mechanical", names)

    def test_two_cards_ratings(self):
        businesses = self.adapter.extract_business_data(_HTML_TWO_CARDS)
        ratings = {b["name"]: b["bbb_rating"] for b in businesses}
        self.assertEqual(ratings["Southwest Comfort Systems"], "A")
        self.assertEqual(ratings["Vegas Valley Mechanical"], "A+")

    def test_phone_with_country_code_normalized(self):
        # Second card in _HTML_TWO_CARDS has "tel:17025550202" (1-prefix)
        businesses = self.adapter.extract_business_data(_HTML_TWO_CARDS)
        southwest = next(
            b for b in businesses if b["name"] == "Southwest Comfort Systems"
        )
        self.assertEqual(southwest["phone"], "(702) 555-0202")

    def test_empty_html_returns_empty_list(self):
        businesses = self.adapter.extract_business_data(_HTML_EMPTY)
        self.assertEqual(businesses, [])

    def test_chain_card_has_high_complaint_count(self):
        businesses = self.adapter.extract_business_data(_HTML_CHAIN_CARD)
        self.assertEqual(len(businesses), 1)
        self.assertEqual(businesses[0]["complaint_count"], 25)


# ── Normalize tests ────────────────────────────────────────────────────────────

class TestNormalize(unittest.TestCase):
    """Tests for BBBAdapter._normalize output schema."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)
        self._raw = {
            "name": "Test HVAC Co",
            "phone": "(702) 555-0100",
            "email": "test@hvac.example.com",
            "website": "https://testhvac.example.com",
            "bbb_rating": "A",
            "accreditation_years": 5,
            "complaint_count": 1,
            "review_count": 30,
            "address": "100 Main St, Las Vegas, NV 89101",
            "city": "Las Vegas",
            "state": "NV",
            "zip_code": "89101",
            "source_id": "test-hvac-co-las-vegas-88-99999",
            "source_url": "https://www.bbb.org/biz/test-hvac-co",
        }

    def _normalize(self):
        return self.adapter._normalize(self._raw, "Las Vegas, NV")

    def test_company_name_mapped(self):
        self.assertEqual(self._normalize()["company_name"], "Test HVAC Co")

    def test_data_source_is_bbb(self):
        self.assertEqual(self._normalize()["data_source"], "bbb")

    def test_service_area_set_to_market(self):
        self.assertEqual(self._normalize()["service_area"], "Las Vegas, NV")

    def test_business_hours_is_none(self):
        self.assertIsNone(self._normalize()["business_hours"])

    def test_rating_is_numeric(self):
        result = self._normalize()
        self.assertIsInstance(result["rating"], float)
        self.assertEqual(result["rating"], 4.7)  # "A" → 4.7

    def test_bbb_trust_score_present(self):
        result = self._normalize()
        self.assertIn("bbb_trust_score", result)
        self.assertGreater(result["bbb_trust_score"], 0)

    def test_standard_yelp_schema_fields_present(self):
        required = {
            "company_name", "phone", "email", "website", "address",
            "city", "state", "zip_code", "review_count", "rating",
            "business_hours", "service_area", "data_source",
            "source_id", "source_url",
        }
        result = self._normalize()
        self.assertTrue(required.issubset(result.keys()))

    def test_nr_rating_maps_to_none_numeric(self):
        raw = dict(self._raw, bbb_rating="NR")
        result = self.adapter._normalize(raw, "Las Vegas, NV")
        self.assertIsNone(result["rating"])


# ── Helper method tests ────────────────────────────────────────────────────────

class TestCleanPhone(unittest.TestCase):
    """Tests for BBBAdapter._clean_phone."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_10_digit_string(self):
        self.assertEqual(self.adapter._clean_phone("7025550101"), "(702) 555-0101")

    def test_formatted_input_unchanged(self):
        self.assertEqual(
            self.adapter._clean_phone("(702) 555-0101"), "(702) 555-0101"
        )

    def test_with_country_code_1(self):
        self.assertEqual(self.adapter._clean_phone("17025550101"), "(702) 555-0101")

    def test_dashes_dots_spaces(self):
        self.assertEqual(self.adapter._clean_phone("702-555-0101"), "(702) 555-0101")
        self.assertEqual(self.adapter._clean_phone("702.555.0101"), "(702) 555-0101")

    def test_none_returns_none(self):
        self.assertIsNone(self.adapter._clean_phone(None))

    def test_empty_returns_none(self):
        self.assertIsNone(self.adapter._clean_phone(""))

    def test_non_10_digit_returned_as_is(self):
        result = self.adapter._clean_phone("+44 20 7946 0958")
        self.assertIsNotNone(result)  # Not None; returned stripped


class TestCleanRating(unittest.TestCase):
    """Tests for BBBAdapter._clean_rating."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_valid_ratings_pass_through(self):
        for r in ("A+", "A", "A-", "B+", "B", "B-", "C", "D", "F", "NR"):
            self.assertEqual(self.adapter._clean_rating(r), r)

    def test_lowercase_normalized(self):
        self.assertEqual(self.adapter._clean_rating("a+"), "A+")

    def test_whitespace_stripped(self):
        self.assertEqual(self.adapter._clean_rating("  A  "), "A")

    def test_embedded_rating_extracted(self):
        self.assertEqual(self.adapter._clean_rating("Rating: A+"), "A+")

    def test_none_returns_nr(self):
        self.assertEqual(self.adapter._clean_rating(None), "NR")

    def test_empty_returns_nr(self):
        self.assertEqual(self.adapter._clean_rating(""), "NR")

    def test_unrecognized_string_returns_nr(self):
        self.assertEqual(self.adapter._clean_rating("Excellent"), "NR")


class TestParseAddress(unittest.TestCase):
    """Tests for BBBAdapter._parse_address."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_standard_us_address(self):
        city, state, zip_code = self.adapter._parse_address(
            "4210 W Flamingo Rd, Las Vegas, NV 89103"
        )
        self.assertEqual(city, "Las Vegas")
        self.assertEqual(state, "NV")
        self.assertEqual(zip_code, "89103")

    def test_address_without_zip(self):
        city, state, _ = self.adapter._parse_address(
            "100 Main St, Phoenix, AZ"
        )
        self.assertEqual(city, "Phoenix")
        self.assertEqual(state, "AZ")

    def test_none_address_returns_nones(self):
        city, state, zip_code = self.adapter._parse_address(None)
        self.assertIsNone(city)
        self.assertIsNone(state)
        self.assertIsNone(zip_code)

    def test_empty_address_returns_nones(self):
        city, state, zip_code = self.adapter._parse_address("")
        self.assertIsNone(city)
        self.assertIsNone(state)
        self.assertIsNone(zip_code)

    def test_suite_in_address(self):
        city, state, zip_code = self.adapter._parse_address(
            "2890 S Rainbow Blvd Ste 110, Las Vegas, NV 89146"
        )
        self.assertEqual(city, "Las Vegas")
        self.assertEqual(state, "NV")
        self.assertEqual(zip_code, "89146")


class TestRatingToNumeric(unittest.TestCase):
    """Tests for BBBAdapter._rating_to_numeric."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_a_plus_is_5_0(self):
        self.assertEqual(self.adapter._rating_to_numeric("A+"), 5.0)

    def test_f_is_0_0(self):
        self.assertEqual(self.adapter._rating_to_numeric("F"), 0.0)

    def test_nr_returns_none(self):
        self.assertIsNone(self.adapter._rating_to_numeric("NR"))

    def test_none_returns_none(self):
        self.assertIsNone(self.adapter._rating_to_numeric(None))

    def test_descending_order(self):
        grades = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
        scores = [self.adapter._rating_to_numeric(g) for g in grades]
        for i in range(len(scores) - 1):
            self.assertGreater(scores[i], scores[i + 1])


# ── Stub data tests ────────────────────────────────────────────────────────────

class TestStubData(unittest.TestCase):
    """Tests for BBBAdapter._stub_data."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_returns_list(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_uses_standard_schema(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        required = {
            "company_name", "phone", "data_source",
            "source_id", "bbb_trust_score",
        }
        for lead in result:
            self.assertTrue(required.issubset(lead.keys()))

    def test_all_from_bbb_source(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertEqual(lead["data_source"], "bbb")

    def test_chain_flagged_in_stub(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        chains = [r for r in result if r.get("is_chain")]
        self.assertGreater(len(chains), 0)

    def test_non_chains_not_flagged(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        non_chains = [r for r in result if not r.get("is_chain")]
        self.assertGreater(len(non_chains), 0)

    def test_trust_scores_are_ints_in_range(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            score = lead["bbb_trust_score"]
            self.assertIsInstance(score, int)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


# ── Pagination detection tests ─────────────────────────────────────────────────

class TestHasNextPage(unittest.TestCase):
    """Tests for BBBAdapter._has_next_page."""

    def setUp(self):
        self.adapter = BBBAdapter(_BASE_CONFIG)

    def test_page_with_next_link(self):
        self.assertTrue(self.adapter._has_next_page(_HTML_HAS_NEXT, 1))

    def test_page_without_next_link(self):
        self.assertFalse(self.adapter._has_next_page(_HTML_NO_NEXT, 1))

    def test_max_page_always_returns_false(self):
        from adapters.bbb import MAX_PAGES_PER_MARKET
        self.assertFalse(
            self.adapter._has_next_page(_HTML_HAS_NEXT, MAX_PAGES_PER_MARKET)
        )


# ── Adapter disabled tests ─────────────────────────────────────────────────────

class TestAdapterDisabled(unittest.TestCase):
    """Ensure disabled adapter returns empty list without making requests."""

    def test_disabled_discover_returns_empty(self):
        adapter = BBBAdapter({"enabled": False})
        result = adapter.discover(["Las Vegas, NV"])
        self.assertEqual(result, [])

    def test_enabled_false_skips_fetch(self):
        adapter = BBBAdapter({"enabled": False})
        # No patch needed — discover returns [] before any network call
        result = adapter.discover(["Phoenix, AZ", "Tucson, AZ"])
        self.assertEqual(result, [])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
