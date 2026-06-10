"""Tests for YelpAdapter (src/adapters/yelp.py).

Run with:
    python -m unittest src/adapters/test_yelp.py -v
    pytest src/adapters/test_yelp.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapters.yelp import YelpAdapter  # noqa: E402


_BASE_CONFIG = {
    "sources": {
        "yelp": {
            "enabled": True,
            "api_key_env": "YELP_API_KEY",
            "results_per_market": 50,
        }
    }
}

_DISABLED_CONFIG = {
    "sources": {
        "yelp": {
            "enabled": False,
            "api_key_env": "YELP_API_KEY",
            "results_per_market": 50,
        }
    }
}

_SAMPLE_YELP_BIZ = {
    "id": "yelp-abc-123",
    "name": "Desert Air Solutions",
    "phone": "+17025550101",
    "url": "https://yelp.com/biz/desert-air-solutions",
    "location": {
        "display_address": ["1234 Flamingo Rd", "Las Vegas, NV 89103"],
        "city": "Las Vegas",
        "state": "NV",
        "zip_code": "89103",
    },
    "review_count": 87,
    "rating": 4.7,
}

_SAMPLE_API_RESPONSE = {
    "businesses": [_SAMPLE_YELP_BIZ],
    "total": 1,
}


# ── Initialization ─────────────────────────────────────────────────────────────

class TestYelpAdapterInit(unittest.TestCase):
    def test_enabled_from_config(self):
        adapter = YelpAdapter(_BASE_CONFIG)
        self.assertTrue(adapter.enabled)

    def test_disabled_from_config(self):
        adapter = YelpAdapter(_DISABLED_CONFIG)
        self.assertFalse(adapter.enabled)

    def test_results_per_market_from_config(self):
        adapter = YelpAdapter(_BASE_CONFIG)
        self.assertEqual(adapter.results_per_market, 50)

    def test_results_per_market_default(self):
        adapter = YelpAdapter({"sources": {"yelp": {"enabled": True}}})
        self.assertEqual(adapter.results_per_market, 300)

    def test_empty_config_defaults_disabled(self):
        adapter = YelpAdapter({})
        self.assertFalse(adapter.enabled)

    def test_config_stored_on_instance(self):
        adapter = YelpAdapter(_BASE_CONFIG)
        self.assertIs(adapter.config, _BASE_CONFIG)


# ── Disabled adapter ───────────────────────────────────────────────────────────

class TestYelpAdapterDisabled(unittest.TestCase):
    def test_disabled_discover_returns_empty(self):
        adapter = YelpAdapter(_DISABLED_CONFIG)
        result = adapter.discover(["Las Vegas, NV"])
        self.assertEqual(result, [])

    def test_disabled_multi_market_returns_empty(self):
        adapter = YelpAdapter(_DISABLED_CONFIG)
        result = adapter.discover(["Las Vegas, NV", "Phoenix, AZ", "Reno, NV"])
        self.assertEqual(result, [])

    def test_disabled_empty_markets_returns_empty(self):
        adapter = YelpAdapter(_DISABLED_CONFIG)
        result = adapter.discover([])
        self.assertEqual(result, [])


# ── Normalize ─────────────────────────────────────────────────────────────────

class TestYelpNormalize(unittest.TestCase):
    def setUp(self):
        self.adapter = YelpAdapter(_BASE_CONFIG)

    def test_company_name_mapped(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["company_name"], "Desert Air Solutions")

    def test_data_source_is_yelp(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["data_source"], "yelp")

    def test_email_always_none(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertIsNone(result["email"])

    def test_business_hours_always_none(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertIsNone(result["business_hours"])

    def test_phone_mapped(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["phone"], "+17025550101")

    def test_website_is_yelp_url(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertIn("yelp.com", result["website"])

    def test_review_count_mapped(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["review_count"], 87)

    def test_rating_mapped(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertAlmostEqual(result["rating"], 4.7)

    def test_city_extracted(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["city"], "Las Vegas")

    def test_state_extracted(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["state"], "NV")

    def test_zip_code_extracted(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["zip_code"], "89103")

    def test_service_area_set_to_market(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["service_area"], "Las Vegas, NV")

    def test_source_id_is_yelp_id(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["source_id"], "yelp-abc-123")

    def test_source_url_same_as_website(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertEqual(result["source_url"], result["website"])

    def test_address_joined_from_display(self):
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertIn("1234 Flamingo Rd", result["address"])

    def test_standard_schema_fields_all_present(self):
        required = {
            "company_name", "phone", "email", "website", "address",
            "city", "state", "zip_code", "review_count", "rating",
            "business_hours", "service_area", "data_source",
            "source_id", "source_url",
        }
        result = self.adapter._normalize(_SAMPLE_YELP_BIZ, "Las Vegas, NV")
        self.assertTrue(required.issubset(result.keys()))

    def test_normalize_missing_location_graceful(self):
        biz = {"id": "x", "name": "Test HVAC", "review_count": 5, "rating": 4.0}
        result = self.adapter._normalize(biz, "Las Vegas, NV")
        self.assertEqual(result["company_name"], "Test HVAC")
        self.assertIsNone(result["city"])

    def test_normalize_zero_review_count_default(self):
        biz = {"id": "x", "name": "Test HVAC"}
        result = self.adapter._normalize(biz, "Las Vegas, NV")
        self.assertEqual(result["review_count"], 0)


# ── Stub data ──────────────────────────────────────────────────────────────────

class TestYelpStubData(unittest.TestCase):
    def setUp(self):
        self.adapter = YelpAdapter(_BASE_CONFIG)

    def test_returns_list(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_data_source_is_yelp(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertEqual(lead["data_source"], "yelp")

    def test_stub_has_review_count(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertGreater(lead["review_count"], 0)

    def test_city_from_market(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        self.assertEqual(result[0]["city"], "Las Vegas")

    def test_stub_has_phone(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        self.assertIsNotNone(result[0]["phone"])

    def test_standard_fields_in_stub(self):
        required = {"company_name", "phone", "data_source", "source_id"}
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertTrue(required.issubset(lead.keys()))

    def test_stub_email_is_none(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertIsNone(lead["email"])

    def test_stub_has_website(self):
        result = self.adapter._stub_data(["Las Vegas, NV"])
        for lead in result:
            self.assertIsNotNone(lead["website"])


# ── Discover (mocked HTTP) ─────────────────────────────────────────────────────

class TestYelpDiscover(unittest.TestCase):
    def setUp(self):
        self.adapter = YelpAdapter(_BASE_CONFIG)
        self.adapter.api_key = "fake-test-key"

    @patch("adapters.yelp.httpx.get")
    def test_api_returns_businesses(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = _SAMPLE_API_RESPONSE
        mock_get.return_value = mock_response

        with patch("adapters.yelp.time.sleep"):
            result = self.adapter.discover(["Las Vegas, NV"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["company_name"], "Desert Air Solutions")

    @patch("adapters.yelp.httpx.get")
    def test_api_error_returns_empty_for_market(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")

        with patch("adapters.yelp.time.sleep"):
            result = self.adapter.discover(["Las Vegas, NV"])

        self.assertEqual(result, [])

    @patch("adapters.yelp.httpx.get")
    def test_multi_market_aggregates_results(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = _SAMPLE_API_RESPONSE
        mock_get.return_value = mock_response

        with patch("adapters.yelp.time.sleep"):
            result = self.adapter.discover(["Las Vegas, NV", "Henderson, NV"])

        self.assertEqual(len(result), 2)

    @patch("adapters.yelp.httpx.get")
    def test_all_results_normalized(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = _SAMPLE_API_RESPONSE
        mock_get.return_value = mock_response

        with patch("adapters.yelp.time.sleep"):
            result = self.adapter.discover(["Las Vegas, NV"])

        for lead in result:
            self.assertEqual(lead["data_source"], "yelp")
            self.assertIn("company_name", lead)

    def test_no_api_key_falls_back_to_stub(self):
        self.adapter.api_key = None
        result = self.adapter.discover(["Las Vegas, NV"])
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        for lead in result:
            self.assertEqual(lead["data_source"], "yelp")

    @patch("adapters.yelp.httpx.get")
    def test_http_error_caught_returns_empty(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        mock_get.return_value = mock_response

        with patch("adapters.yelp.time.sleep"):
            result = self.adapter.discover(["Las Vegas, NV"])

        self.assertEqual(result, [])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
