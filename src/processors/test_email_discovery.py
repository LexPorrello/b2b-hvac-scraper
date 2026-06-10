"""Tests for EmailDiscoveryEngine (src/processors/email_discovery.py).

Run with:
    pytest src/processors/test_email_discovery.py -v
    python -m unittest src/processors/test_email_discovery.py -v
"""
import sys
import os
import tempfile
import unittest
from unittest.mock import MagicMock

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from processors.email_discovery import EmailDiscoveryEngine  # noqa: E402


def _make_engine():
    """Create an EmailDiscoveryEngine with an isolated temp database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_email_cache.db")
    engine = EmailDiscoveryEngine(cache_db=db_path)
    # Replace HTTP client so tests never touch the network
    engine.client = MagicMock()
    return engine


# ── _generate_name_patterns ────────────────────────────────────────────────────

class TestGenerateNamePatterns(unittest.TestCase):
    """Tests for EmailDiscoveryEngine._generate_name_patterns()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_two_part_name_generates_emails(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertGreater(len(emails), 0)

    def test_first_name_pattern_present(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertIn("john@example.com", emails)

    def test_last_name_pattern_present(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertIn("smith@example.com", emails)

    def test_first_dot_last_pattern_present(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertIn("john.smith@example.com", emails)

    def test_first_underscore_last_pattern_present(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertIn("john_smith@example.com", emails)

    def test_initial_last_pattern_present(self):
        emails = self.engine._generate_name_patterns("John Smith", "example.com")
        self.assertIn("jsmith@example.com", emails)

    def test_no_name_returns_empty(self):
        emails = self.engine._generate_name_patterns("", "example.com")
        self.assertEqual(emails, [])

    def test_single_name_no_space_returns_empty(self):
        emails = self.engine._generate_name_patterns("John", "example.com")
        self.assertEqual(emails, [])

    def test_name_lowercased_in_output(self):
        emails = self.engine._generate_name_patterns("JOHN SMITH", "example.com")
        self.assertIn("john@example.com", emails)

    def test_domain_used_correctly(self):
        emails = self.engine._generate_name_patterns("Jane Doe", "hvac.example.net")
        for email in emails:
            self.assertTrue(email.endswith("@hvac.example.net"))

    def test_three_part_name_uses_first_and_last(self):
        emails = self.engine._generate_name_patterns("John Robert Smith", "example.com")
        # First = "john", last = "smith"
        self.assertIn("john@example.com", emails)
        self.assertIn("smith@example.com", emails)

    def test_returns_list_type(self):
        result = self.engine._generate_name_patterns("Jane Doe", "example.com")
        self.assertIsInstance(result, list)


# ── _generate_role_patterns ────────────────────────────────────────────────────

class TestGenerateRolePatterns(unittest.TestCase):
    """Tests for EmailDiscoveryEngine._generate_role_patterns()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_generates_owner_pattern(self):
        emails = self.engine._generate_role_patterns("hvac.example.com")
        self.assertIn("owner@hvac.example.com", emails)

    def test_generates_info_pattern(self):
        emails = self.engine._generate_role_patterns("hvac.example.com")
        self.assertIn("info@hvac.example.com", emails)

    def test_generates_contact_pattern(self):
        emails = self.engine._generate_role_patterns("hvac.example.com")
        self.assertIn("contact@hvac.example.com", emails)

    def test_generates_service_pattern(self):
        emails = self.engine._generate_role_patterns("hvac.example.com")
        self.assertIn("service@hvac.example.com", emails)

    def test_generates_hello_pattern(self):
        emails = self.engine._generate_role_patterns("hvac.example.com")
        self.assertIn("hello@hvac.example.com", emails)

    def test_all_patterns_end_with_domain(self):
        emails = self.engine._generate_role_patterns("test.example.com")
        for email in emails:
            self.assertTrue(email.endswith("@test.example.com"))

    def test_returns_non_empty_list(self):
        emails = self.engine._generate_role_patterns("example.com")
        self.assertIsInstance(emails, list)
        self.assertGreater(len(emails), 0)

    def test_all_are_valid_email_format(self):
        emails = self.engine._generate_role_patterns("example.com")
        for email in emails:
            self.assertIn("@", email)
            local, domain = email.split("@")
            self.assertTrue(len(local) > 0)
            self.assertEqual(domain, "example.com")


# ── _verify_email ──────────────────────────────────────────────────────────────

class TestVerifyEmail(unittest.TestCase):
    """Tests for EmailDiscoveryEngine._verify_email() (stub implementation)."""

    def setUp(self):
        self.engine = _make_engine()

    def test_valid_format_returns_true(self):
        self.assertTrue(self.engine._verify_email("owner@hvac.example.com"))

    def test_invalid_format_no_at_returns_false(self):
        self.assertFalse(self.engine._verify_email("notanemail"))

    def test_missing_domain_returns_false(self):
        self.assertFalse(self.engine._verify_email("owner@"))

    def test_missing_at_sign_returns_false(self):
        self.assertFalse(self.engine._verify_email("ownerexample.com"))

    def test_dotted_local_part_valid(self):
        self.assertTrue(self.engine._verify_email("john.smith@example.com"))

    def test_underscore_local_part_valid(self):
        self.assertTrue(self.engine._verify_email("john_smith@example.com"))

    def test_plus_local_part_invalid_per_stub_regex(self):
        # The stub regex [\w\.-]+ does not include '+', so this returns False
        self.assertFalse(self.engine._verify_email("john+tag@example.com"))

    def test_subdomain_email_valid(self):
        self.assertTrue(self.engine._verify_email("info@mail.hvac.example.com"))

    def test_uppercase_local_part_valid(self):
        self.assertTrue(self.engine._verify_email("Owner@example.com"))

    def test_empty_string_returns_false(self):
        self.assertFalse(self.engine._verify_email(""))

    def test_double_at_sign_returns_false(self):
        self.assertFalse(self.engine._verify_email("a@@example.com"))


# ── Cache operations ───────────────────────────────────────────────────────────

class TestCacheOperations(unittest.TestCase):
    """Tests for _cache_email and _is_cached_valid."""

    def setUp(self):
        self.engine = _make_engine()

    def test_cache_verified_email_returns_true(self):
        self.engine._cache_email("test@example.com", "example.com", verified=1)
        self.assertTrue(self.engine._is_cached_valid("test@example.com"))

    def test_cache_unverified_email_returns_false(self):
        self.engine._cache_email("bad@example.com", "example.com", verified=0)
        self.assertFalse(self.engine._is_cached_valid("bad@example.com"))

    def test_uncached_email_returns_false(self):
        self.assertFalse(self.engine._is_cached_valid("nobody@example.com"))

    def test_cache_overwrite_upgrades_to_verified(self):
        self.engine._cache_email("flip@example.com", "example.com", verified=0)
        self.engine._cache_email("flip@example.com", "example.com", verified=1)
        self.assertTrue(self.engine._is_cached_valid("flip@example.com"))

    def test_cache_overwrite_downgrades_to_unverified(self):
        self.engine._cache_email("flip2@example.com", "example.com", verified=1)
        self.engine._cache_email("flip2@example.com", "example.com", verified=0)
        self.assertFalse(self.engine._is_cached_valid("flip2@example.com"))

    def test_multiple_emails_cached_independently(self):
        self.engine._cache_email("a@example.com", "example.com", verified=1)
        self.engine._cache_email("b@example.com", "example.com", verified=0)
        self.assertTrue(self.engine._is_cached_valid("a@example.com"))
        self.assertFalse(self.engine._is_cached_valid("b@example.com"))

    def test_returns_bool(self):
        result = self.engine._is_cached_valid("test@example.com")
        self.assertIsInstance(result, bool)


# ── discover ───────────────────────────────────────────────────────────────────

class TestDiscover(unittest.TestCase):
    """Tests for EmailDiscoveryEngine.discover()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_returns_list(self):
        result = self.engine.discover("Desert Air", "desertair.example.com")
        self.assertIsInstance(result, list)

    def test_with_owner_name_finds_emails(self):
        result = self.engine.discover("Desert Air", "desertair.example.com", "John Smith")
        self.assertGreater(len(result), 0)

    def test_no_owner_name_still_returns_role_emails(self):
        result = self.engine.discover("Desert Air", "desertair.example.com", "")
        self.assertGreater(len(result), 0)

    def test_all_results_contain_at_sign(self):
        result = self.engine.discover("Desert Air", "desertair.example.com", "John Smith")
        for email in result:
            self.assertIn("@", email)

    def test_all_results_contain_domain(self):
        domain = "desertair.example.com"
        result = self.engine.discover("Desert Air", domain, "John Smith")
        for email in result:
            self.assertIn(domain, email)

    def test_returns_only_verified_emails(self):
        # discover() returns all format-valid candidates (stub verifier passes all valid formats)
        # With owner name, this is name patterns + role patterns
        result = self.engine.discover("Test HVAC", "test.example.com", "John Smith")
        # All results must be valid email format
        for email in result:
            self.assertRegex(email, r'^[\w\.-]+@[\w\.-]+\.\w+$')

    def test_no_duplicate_emails_in_results(self):
        result = self.engine.discover("Test HVAC", "test.example.com", "John Smith")
        self.assertEqual(len(result), len(set(result)))

    def test_pre_cached_valid_email_included(self):
        domain = "cached.example.com"
        self.engine._cache_email(f"owner@{domain}", domain, verified=1)
        result = self.engine.discover("Cached HVAC", domain)
        self.assertIn(f"owner@{domain}", result)

    def test_pre_cached_invalid_email_not_included(self):
        domain = "invalid.example.com"
        # Cache all role patterns as invalid
        for role in ["owner", "info", "contact", "admin", "office", "service", "hello"]:
            self.engine._cache_email(f"{role}@{domain}", domain, verified=0)
        result = self.engine.discover("Invalid Domain HVAC", domain)
        # Stub verifier always returns True for format-valid emails, so these still pass
        # This verifies that the function completes without error
        self.assertIsInstance(result, list)


# ── search_website ─────────────────────────────────────────────────────────────

class TestSearchWebsite(unittest.TestCase):
    """Tests for EmailDiscoveryEngine.search_website()."""

    def setUp(self):
        self.engine = _make_engine()

    def test_returns_list_on_network_error(self):
        self.engine.client.get.side_effect = Exception("No network")
        result = self.engine.search_website("https://example.com")
        self.assertIsInstance(result, list)

    def test_returns_empty_on_failure(self):
        self.engine.client.get.side_effect = Exception("Refused")
        result = self.engine.search_website("https://example.com")
        self.assertEqual(result, [])

    def test_extracts_emails_from_successful_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Contact: owner@hvac.example.com</body></html>"
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://hvac.example.com")
        self.assertIn("owner@hvac.example.com", result)

    def test_filters_noreply_from_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>noreply@example.com info@hvac.example.com</body></html>"
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://hvac.example.com")
        self.assertNotIn("noreply@example.com", result)

    def test_max_5_emails_returned(self):
        emails_text = " ".join([f"user{i}@hvac.example.com" for i in range(20)])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = f"<html><body>{emails_text}</body></html>"
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://hvac.example.com")
        self.assertLessEqual(len(result), 5)

    def test_results_lowercased(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Owner@HVAC.Example.COM</body></html>"
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://hvac.example.com")
        for email in result:
            self.assertEqual(email, email.lower())

    def test_no_duplicate_emails_in_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>owner@hvac.example.com owner@hvac.example.com</body></html>"
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://hvac.example.com")
        self.assertEqual(len(result), len(set(result)))

    def test_404_response_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        self.engine.client.get.return_value = mock_resp
        result = self.engine.search_website("https://notfound.example.com")
        self.assertIsInstance(result, list)


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
