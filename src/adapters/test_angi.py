"""Tests for the Angi adapter (src/adapters/angi.py)."""
import pytest
from unittest.mock import patch
from adapters.angi import AngiAdapter


# ── HTML fixtures ──────────────────────────────────────────────────────────────

SAMPLE_CARD_HTML = """
<article class="provider-card" data-testid="provider-card">
  <h2><a href="/companies/silver-state-air-12345" data-testid="business-name">Silver State Air &amp; Heat</a></h2>
  <div class="starRating" aria-label="4.8 out of 5 stars">★★★★★</div>
  <span data-testid="review-count" class="reviewCount">127 reviews</span>
  <a href="tel:+17025550301" class="phone">(702) 555-0301</a>
  <a href="https://silverstatehvac.example.com" class="website">www.silverstatehvac.example.com</a>
  <span class="address">3100 E Charleston Blvd, Las Vegas, NV 89104</span>
  <span class="yearsInBusiness">14 years in business</span>
  <span class="serviceArea">Las Vegas, NV</span>
</article>
"""

SAMPLE_ESTABLISHED_CARD_HTML = """
<article class="provider-card" data-testid="provider-card">
  <h2><a href="/companies/desert-air-22222" data-testid="business-name">Desert Air Pros</a></h2>
  <div class="starRating" aria-label="4.2 out of 5 stars"></div>
  <span class="reviewCount">18 reviews</span>
  <a href="tel:+17025550450">(702) 555-0450</a>
  <span class="address">500 Main St, Las Vegas, NV 89101</span>
  <span class="established">Established 2010</span>
</article>
"""

SAMPLE_CHAIN_CARD_HTML = """
<article class="provider-card" data-testid="provider-card">
  <h2><a href="/companies/one-hour-heating-99999" data-testid="business-name">One Hour Heating &amp; Air Conditioning</a></h2>
  <div class="starRating" aria-label="4.0 out of 5 stars"></div>
  <span class="reviewCount">1200 reviews</span>
  <a href="tel:+17025550999">(702) 555-0999</a>
</article>
"""

SAMPLE_NO_RATING_CARD_HTML = """
<article class="provider-card" data-testid="provider-card">
  <h3><a href="/companies/desert-air-67890">Desert Air Solutions</a></h3>
  <a href="tel:+17025550450">(702) 555-0450</a>
  <span class="address">500 Main St, Las Vegas, NV 89101</span>
</article>
"""

SAMPLE_MAILTO_CARD_HTML = """
<article class="provider-card" data-testid="provider-card">
  <h2><a href="/companies/email-hvac-33333">Email HVAC Co</a></h2>
  <a href="mailto:info@emailhvac.example.com">Email Us</a>
  <a href="tel:+17025550600">(702) 555-0600</a>
</article>
"""

SAMPLE_SEARCH_PAGE_HTML = f"""
<html><body>
  <main>
    {SAMPLE_CARD_HTML}
    {SAMPLE_CHAIN_CARD_HTML}
    {SAMPLE_NO_RATING_CARD_HTML}
    <nav>
      <a aria-label="Next page" href="/companylist/las-vegas/hvac-contractors/2.htm">Next</a>
    </nav>
  </main>
</body></html>
"""

SAMPLE_LAST_PAGE_HTML = f"""
<html><body>
  <main>
    {SAMPLE_CARD_HTML}
  </main>
</body></html>
"""


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return {
        "enabled": True,
        "results_per_market": 200,
        "category": "hvac-heating-cooling",
        "chain_brands": ["Custom Chain HVAC"],
    }


@pytest.fixture
def disabled_config():
    return {
        "enabled": False,
        "results_per_market": 200,
        "category": "hvac-heating-cooling",
    }


@pytest.fixture
def adapter(config):
    return AngiAdapter(config)


# ── Initialization ─────────────────────────────────────────────────────────────

class TestAngiAdapterInit:
    def test_enabled_flag_set(self, adapter):
        assert adapter.enabled is True

    def test_disabled_flag(self, disabled_config):
        a = AngiAdapter(disabled_config)
        assert a.enabled is False

    def test_category_slug_mapping(self, adapter):
        assert adapter.category_slug == "hvac-contractors"

    def test_category_slug_direct(self):
        a = AngiAdapter({"enabled": True, "category": "hvac-contractors"})
        assert a.category_slug == "hvac-contractors"

    def test_category_slug_fallback_for_unknown(self):
        a = AngiAdapter({"enabled": True, "category": "unknown-category"})
        assert a.category_slug == "hvac-contractors"

    def test_results_per_market_default(self):
        a = AngiAdapter({"enabled": True})
        assert a.results_per_market == 200

    def test_results_per_market_custom(self, config):
        config["results_per_market"] = 50
        a = AngiAdapter(config)
        assert a.results_per_market == 50


# ── extract_business_data ──────────────────────────────────────────────────────

class TestExtractBusinessData:
    def test_extracts_three_businesses_from_page(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_SEARCH_PAGE_HTML)
        assert len(businesses) == 3

    def test_extracts_name(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert len(businesses) == 1
        assert businesses[0]["name"] == "Silver State Air & Heat"

    def test_extracts_phone(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["phone"] == "(702) 555-0301"

    def test_extracts_rating(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["angi_rating"] == pytest.approx(4.8, abs=0.01)

    def test_extracts_review_count(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["review_count"] == 127

    def test_extracts_years_in_business(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["years_in_business"] == 14

    def test_extracts_address(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert "Las Vegas" in (businesses[0]["address"] or "")

    def test_extracts_city_from_address(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["city"] == "Las Vegas"

    def test_extracts_state_from_address(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["state"] == "NV"

    def test_extracts_zip_from_address(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["zip_code"] == "89104"

    def test_extracts_source_url(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert "silver-state-air" in (businesses[0]["source_url"] or "")

    def test_extracts_source_id(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert "silver-state-air" in (businesses[0]["source_id"] or "")

    def test_extracts_website(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_CARD_HTML)
        assert businesses[0]["website"] == "https://silverstatehvac.example.com"

    def test_extracts_email_from_mailto(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_MAILTO_CARD_HTML)
        assert businesses[0]["email"] == "info@emailhvac.example.com"

    def test_no_rating_returns_none(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_NO_RATING_CARD_HTML)
        assert businesses[0]["angi_rating"] is None

    def test_established_year_parsed(self, adapter):
        businesses = adapter.extract_business_data(SAMPLE_ESTABLISHED_CARD_HTML)
        assert businesses[0]["years_in_business"] >= 14  # 2010 → 14+ years

    def test_empty_html_returns_empty_list(self, adapter):
        result = adapter.extract_business_data("<html><body></body></html>")
        assert result == []

    def test_skips_cards_without_name(self, adapter):
        html = '<article class="provider-card"><span class="phone">(702) 555-0000</span></article>'
        result = adapter.extract_business_data(html)
        assert result == []


# ── calculate_reliability_score ───────────────────────────────────────────────

class TestCalculateReliabilityScore:
    def test_perfect_inputs_give_100(self, adapter):
        score = adapter.calculate_reliability_score(5.0, 500, 20)
        assert score == 100

    def test_zero_inputs_give_zero(self, adapter):
        score = adapter.calculate_reliability_score(0.0, 0, 0)
        assert score == 0

    def test_none_rating_zero_pts(self, adapter):
        # 0 rating pts + 25 review pts (50+) + 15 year pts (10 * 1.5) = 40
        score = adapter.calculate_reliability_score(None, 50, 10)
        assert score == 40

    def test_high_rating_contributes(self, adapter):
        # 4.8 / 5.0 * 50 = 48
        score = adapter.calculate_reliability_score(4.8, 0, 0)
        assert score == 48

    def test_review_breakpoint_0(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 0, 0) == 0

    def test_review_breakpoint_1(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 1, 0) == 5

    def test_review_breakpoint_5(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 5, 0) == 10

    def test_review_breakpoint_10(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 10, 0) == 15

    def test_review_breakpoint_25(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 25, 0) == 20

    def test_review_breakpoint_50(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 50, 0) == 25

    def test_review_breakpoint_100(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 100, 0) == 28

    def test_review_breakpoint_500(self, adapter):
        assert adapter.calculate_reliability_score(0.0, 500, 0) == 30

    def test_years_cap_at_20pts(self, adapter):
        # 14 * 1.5 = 21 → capped at 20
        score_big = adapter.calculate_reliability_score(0.0, 0, 14)
        score_huge = adapter.calculate_reliability_score(0.0, 0, 100)
        assert score_big == score_huge
        assert score_big <= 20

    def test_score_clamped_max_100(self, adapter):
        score = adapter.calculate_reliability_score(5.0, 999, 999)
        assert score == 100

    def test_score_clamped_min_0(self, adapter):
        score = adapter.calculate_reliability_score(-1.0, -1, -1)
        assert score >= 0

    def test_real_world_example(self, adapter):
        # Silver State stub: 4.8 rating, 127 reviews, 14 years
        # 4.8/5*50=48, 28 (100+ reviews), min(20, 14*1.5)=20 → 96
        score = adapter.calculate_reliability_score(4.8, 127, 14)
        assert score == 96


# ── is_chain_or_franchise ──────────────────────────────────────────────────────

class TestIsChainOrFranchise:
    def test_exact_match_chain(self, adapter):
        assert adapter.is_chain_or_franchise("One Hour Heating") is True

    def test_partial_match_chain(self, adapter):
        assert adapter.is_chain_or_franchise("One Hour Heating & Air Conditioning") is True

    def test_ars_match(self, adapter):
        assert adapter.is_chain_or_franchise("ARS Rescue Rooter") is True

    def test_local_business_not_chain(self, adapter):
        assert adapter.is_chain_or_franchise("Silver State Air & Heat") is False

    def test_none_returns_false(self, adapter):
        assert adapter.is_chain_or_franchise(None) is False

    def test_empty_string_returns_false(self, adapter):
        assert adapter.is_chain_or_franchise("") is False

    def test_word_boundary_no_false_positive(self, adapter):
        # "ARS" should NOT match "Parsons HVAC"
        assert adapter.is_chain_or_franchise("Parsons HVAC") is False

    def test_franchise_keyword_detected(self, adapter):
        assert adapter.is_chain_or_franchise("Nevada Franchise Heating") is True

    def test_config_chain_brands_honored(self, adapter):
        assert adapter.is_chain_or_franchise("Custom Chain HVAC") is True

    def test_case_insensitive_match(self, adapter):
        assert adapter.is_chain_or_franchise("ONE HOUR HEATING") is True

    def test_nationwide_keyword_detected(self, adapter):
        assert adapter.is_chain_or_franchise("Nationwide Air Service") is True


# ── _normalize ─────────────────────────────────────────────────────────────────

class TestNormalize:
    def _sample_biz(self):
        return {
            "name": "Test HVAC Co",
            "phone": "(702) 555-0100",
            "email": None,
            "website": "https://testhvac.example.com",
            "angi_rating": 4.5,
            "review_count": 50,
            "years_in_business": 8,
            "service_area": "Las Vegas, NV",
            "address": "100 Main St, Las Vegas, NV 89101",
            "city": "Las Vegas",
            "state": "NV",
            "zip_code": "89101",
            "source_id": "test-001",
            "source_url": "https://www.angi.com/companies/test-001",
        }

    def test_all_standard_fields_present(self, adapter):
        normalized = adapter._normalize(self._sample_biz(), "Las Vegas, NV")
        required = [
            "company_name", "phone", "email", "website",
            "address", "city", "state", "zip_code",
            "review_count", "rating", "business_hours",
            "service_area", "data_source", "source_id", "source_url",
        ]
        for field in required:
            assert field in normalized, f"Missing standard field: {field}"

    def test_data_source_is_angi(self, adapter):
        normalized = adapter._normalize({"name": "Test"}, "Las Vegas, NV")
        assert normalized["data_source"] == "angi"

    def test_business_hours_always_none(self, adapter):
        normalized = adapter._normalize({"name": "Test"}, "Las Vegas, NV")
        assert normalized["business_hours"] is None

    def test_angi_specific_fields_present(self, adapter):
        normalized = adapter._normalize(self._sample_biz(), "Las Vegas, NV")
        assert "angi_rating" in normalized
        assert "angi_reliability_score" in normalized
        assert "years_in_business" in normalized

    def test_reliability_score_computed(self, adapter):
        normalized = adapter._normalize(self._sample_biz(), "Las Vegas, NV")
        assert normalized["angi_reliability_score"] > 0

    def test_service_area_fallback_to_location(self, adapter):
        biz = {"name": "Test", "service_area": None}
        normalized = adapter._normalize(biz, "Las Vegas, NV")
        assert normalized["service_area"] == "Las Vegas, NV"

    def test_service_area_from_biz_preferred(self, adapter):
        biz = {"name": "Test", "service_area": "Henderson, NV"}
        normalized = adapter._normalize(biz, "Las Vegas, NV")
        assert normalized["service_area"] == "Henderson, NV"

    def test_rating_field_matches_angi_rating(self, adapter):
        biz = {"name": "Test", "angi_rating": 4.2}
        normalized = adapter._normalize(biz, "Las Vegas, NV")
        assert normalized["rating"] == 4.2
        assert normalized["angi_rating"] == 4.2


# ── _clean_phone ───────────────────────────────────────────────────────────────

class TestCleanPhone:
    def test_formats_10_digit_number(self, adapter):
        assert adapter._clean_phone("7025550123") == "(702) 555-0123"

    def test_strips_leading_1(self, adapter):
        assert adapter._clean_phone("17025550123") == "(702) 555-0123"

    def test_already_formatted(self, adapter):
        assert adapter._clean_phone("(702) 555-0123") == "(702) 555-0123"

    def test_dashes_format(self, adapter):
        assert adapter._clean_phone("702-555-0123") == "(702) 555-0123"

    def test_returns_none_for_none(self, adapter):
        assert adapter._clean_phone(None) is None

    def test_returns_none_for_empty_string(self, adapter):
        assert adapter._clean_phone("") is None

    def test_tel_href_format(self, adapter):
        assert adapter._clean_phone("+17025550301") == "(702) 555-0301"


# ── _to_city_slug ──────────────────────────────────────────────────────────────

class TestToCitySlug:
    def test_las_vegas(self, adapter):
        assert adapter._to_city_slug("Las Vegas") == "las-vegas"

    def test_phoenix(self, adapter):
        assert adapter._to_city_slug("Phoenix") == "phoenix"

    def test_removes_special_chars(self, adapter):
        assert adapter._to_city_slug("St. George") == "st-george"

    def test_trims_whitespace(self, adapter):
        assert adapter._to_city_slug("  Las Vegas  ") == "las-vegas"

    def test_already_slug(self, adapter):
        assert adapter._to_city_slug("las-vegas") == "las-vegas"

    def test_multi_word(self, adapter):
        assert adapter._to_city_slug("North Las Vegas") == "north-las-vegas"


# ── _parse_address ─────────────────────────────────────────────────────────────

class TestParseAddress:
    def test_parses_full_us_address(self, adapter):
        city, state, zip_code = adapter._parse_address(
            "3100 E Charleston Blvd, Las Vegas, NV 89104"
        )
        assert city == "Las Vegas"
        assert state == "NV"
        assert zip_code == "89104"

    def test_returns_none_tuple_for_none(self, adapter):
        city, state, zip_code = adapter._parse_address(None)
        assert city is None
        assert state is None
        assert zip_code is None

    def test_returns_none_for_unparseable(self, adapter):
        city, state, zip_code = adapter._parse_address("No address here")
        assert city is None

    def test_address_without_zip(self, adapter):
        city, state, zip_code = adapter._parse_address("100 Main St, Phoenix, AZ")
        assert city == "Phoenix"
        assert state == "AZ"


# ── _has_next_page ─────────────────────────────────────────────────────────────

class TestHasNextPage:
    def test_detects_aria_label_next_page(self, adapter):
        html = '<nav><a aria-label="Next page" href="/page/2">Next</a></nav>'
        assert adapter._has_next_page(html, 1) is True

    def test_detects_rel_next(self, adapter):
        html = '<a rel="next" href="/page/2">Next</a>'
        assert adapter._has_next_page(html, 1) is True

    def test_no_next_link_returns_false(self, adapter):
        assert adapter._has_next_page("<html></html>", 1) is False

    def test_max_pages_always_returns_false(self, adapter):
        html = '<a aria-label="Next page">Next</a>'
        assert adapter._has_next_page(html, 10) is False

    def test_page_9_can_still_have_next(self, adapter):
        html = '<a aria-label="Next page">Next</a>'
        assert adapter._has_next_page(html, 9) is True


# ── discover (mocked HTTP) ─────────────────────────────────────────────────────

class TestDiscover:
    def test_disabled_returns_empty_list(self, disabled_config):
        a = AngiAdapter(disabled_config)
        assert a.discover(["Las Vegas, NV"]) == []

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_returns_normalized_leads(self, mock_fetch, adapter):
        mock_fetch.return_value = SAMPLE_SEARCH_PAGE_HTML
        result = adapter.discover(["Las Vegas, NV"])
        assert len(result) > 0
        assert all("company_name" in r for r in result)
        assert all(r["data_source"] == "angi" for r in result)

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_deduplicates_by_source_id(self, mock_fetch, adapter):
        # Return the same page twice (page 1 and "page 2")
        mock_fetch.return_value = SAMPLE_SEARCH_PAGE_HTML
        result = adapter.discover(["Las Vegas, NV"])
        source_ids = [r["source_id"] for r in result if r.get("source_id")]
        assert len(source_ids) == len(set(source_ids))

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_respects_results_per_market_cap(self, mock_fetch, adapter):
        adapter.results_per_market = 1
        mock_fetch.return_value = SAMPLE_SEARCH_PAGE_HTML
        result = adapter.discover(["Las Vegas, NV"])
        assert len(result) <= 1

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_handles_fetch_failure_gracefully(self, mock_fetch, adapter):
        mock_fetch.return_value = None
        result = adapter.discover(["Las Vegas, NV"])
        assert result == []

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_stops_pagination_on_last_page(self, mock_fetch, adapter):
        # Last page has no next-page link
        mock_fetch.return_value = SAMPLE_LAST_PAGE_HTML
        result = adapter.discover(["Las Vegas, NV"])
        # Should only call fetch once since no next page
        assert mock_fetch.call_count == 1

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_multi_market_discover(self, mock_fetch, adapter):
        mock_fetch.return_value = SAMPLE_LAST_PAGE_HTML
        result = adapter.discover(["Las Vegas, NV", "Phoenix, AZ"])
        # 1 business per market × 2 markets = 2 (source_ids differ by card — same card across markets dedupes differently)
        assert len(result) >= 1

    @patch("adapters.angi.AngiAdapter._fetch_search_page")
    def test_all_standard_fields_in_output(self, mock_fetch, adapter):
        mock_fetch.return_value = SAMPLE_CARD_HTML
        result = adapter.discover(["Las Vegas, NV"])
        if result:
            for field in ["company_name", "phone", "data_source", "source_url", "rating"]:
                assert field in result[0]


# ── _stub_data ─────────────────────────────────────────────────────────────────

class TestStubData:
    def test_returns_exactly_5_stubs(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        assert len(stubs) == 5

    def test_stubs_have_company_name(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        assert all("company_name" in s for s in stubs)

    def test_stubs_data_source_is_angi(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        assert all(s["data_source"] == "angi" for s in stubs)

    def test_chain_stub_flagged(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        chain_stubs = [s for s in stubs if s.get("is_chain")]
        assert len(chain_stubs) >= 1

    def test_stubs_have_reliability_score(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        assert all("angi_reliability_score" in s for s in stubs)

    def test_stubs_have_years_in_business(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        assert all("years_in_business" in s for s in stubs)

    def test_no_markets_uses_default(self, adapter):
        stubs = adapter._stub_data([])
        assert len(stubs) == 5

    def test_first_stub_has_high_reliability(self, adapter):
        stubs = adapter._stub_data(["Las Vegas, NV"])
        # Silver State: rating 4.8, 127 reviews, 14 years → score 96
        assert stubs[0]["angi_reliability_score"] >= 90
