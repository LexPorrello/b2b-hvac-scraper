"""Tests for WebsiteExtractor (src/adapters/website_intel.py).

Run with:
    pytest src/adapters/test_website_intel.py -v
    python -m unittest src/adapters/test_website_intel.py -v
"""
import sys
import os
import unittest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(_here, "..")
for _p in (_src, _here):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapters.website_intel import WebsiteExtractor, extract_website_intel  # noqa: E402


# ── HTML fixtures ──────────────────────────────────────────────────────────────

_MODERN_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://googletagmanager.com/gtag/js"></script>
</head>
<body>
  <style>
    .container { display: flex; }
    @media (max-width: 768px) { .menu { display: none; } }
  </style>
  <p>Contact: owner@hvacpros.example.com or (702) 555-0199</p>
  <p>info@hvacpros.example.com</p>
  <script>var React = require('react');</script>
  <a href="/about">About Us</a>
  <a href="/contact">Contact</a>
</body>
</html>"""

_OLD_HTML = """<html>
<frameset>
  <frame src="header.html">
  <frame src="main.html">
</frameset>
<body>
  <script src="swfobject.js"></script>
  <object data="intro.swf"></object>
  <p>Call us: (702) 555-0100</p>
</body>
</html>"""

_CHAT_HTML = """<html><body>
  <script src="https://livechat.example.com/chat.js">var livechat = {};</script>
  <p>We are here to help via intercom</p>
  <a href="https://calendly.com/hvacpros/appointment">Book Now</a>
</body></html>"""

_NO_EMAILS_HTML = """<html><body>
  <p>Call us at (702) 555-0100</p>
  <p>No email address shown here</p>
</body></html>"""

_META_OWNER_HTML = """<html>
<head>
  <meta name="description" content="Desert Air Solutions. Service by John Smith, owner since 2005.">
</head>
<body><p>Family owned HVAC</p></body>
</html>"""

_MULTI_EMAIL_HTML = """<html><body>
  <p>owner@hvac.example.com</p>
  <p>info@hvac.example.com</p>
  <p>service@hvac.example.com</p>
  <p>admin@hvac.example.com</p>
</body></html>"""


def _make_extractor():
    """Create a WebsiteExtractor with a mock HTTP client."""
    extractor = WebsiteExtractor()
    extractor.client = MagicMock()
    return extractor


def _make_response(html, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    return resp


# ── Initialization ─────────────────────────────────────────────────────────────

class TestWebsiteExtractorInit(unittest.TestCase):
    def test_client_created(self):
        extractor = WebsiteExtractor()
        self.assertIsNotNone(extractor.client)

    def test_cache_starts_empty(self):
        extractor = WebsiteExtractor()
        self.assertEqual(len(extractor._cache), 0)

    def test_custom_timeout_accepted(self):
        extractor = WebsiteExtractor(timeout=5)
        self.assertIsNotNone(extractor.client)

    def test_chat_widgets_list_non_empty(self):
        extractor = WebsiteExtractor()
        self.assertGreater(len(extractor.CHAT_WIDGETS), 0)

    def test_booking_systems_list_non_empty(self):
        extractor = WebsiteExtractor()
        self.assertGreater(len(extractor.BOOKING_SYSTEMS), 0)


# ── _extract_emails ────────────────────────────────────────────────────────────

class TestExtractEmails(unittest.TestCase):
    def setUp(self):
        self.extractor = _make_extractor()

    def test_finds_valid_email(self):
        result = self.extractor._extract_emails("Contact: owner@hvacpros.example.com")
        self.assertIn("owner@hvacpros.example.com", result)

    def test_returns_multiple_emails(self):
        text = "info@hvac.example.com and service@hvac.example.com"
        result = self.extractor._extract_emails(text)
        self.assertEqual(len(result), 2)

    def test_max_3_emails_returned(self):
        text = " ".join([f"user{i}@hvac.example.com" for i in range(10)])
        result = self.extractor._extract_emails(text)
        self.assertLessEqual(len(result), 3)

    def test_filters_noreply(self):
        result = self.extractor._extract_emails("noreply@example.com")
        self.assertEqual(result, [])

    def test_filters_no_reply_hyphen(self):
        result = self.extractor._extract_emails("no-reply@example.com")
        self.assertEqual(result, [])

    def test_filters_donotreply(self):
        result = self.extractor._extract_emails("donotreply@example.com")
        self.assertEqual(result, [])

    def test_filters_sentry(self):
        result = self.extractor._extract_emails("errors@sentry.io")
        self.assertEqual(result, [])

    def test_empty_text_returns_empty(self):
        result = self.extractor._extract_emails("")
        self.assertEqual(result, [])

    def test_no_emails_returns_empty(self):
        result = self.extractor._extract_emails("No email here, just text.")
        self.assertEqual(result, [])

    def test_deduplicates_emails(self):
        text = "owner@hvac.example.com owner@hvac.example.com"
        result = self.extractor._extract_emails(text)
        self.assertEqual(len(result), 1)

    def test_valid_email_with_dots_in_local(self):
        result = self.extractor._extract_emails("first.last@hvac.example.com")
        self.assertIn("first.last@hvac.example.com", result)


# ── _extract_phones ────────────────────────────────────────────────────────────

class TestExtractPhones(unittest.TestCase):
    def setUp(self):
        self.extractor = _make_extractor()

    def test_finds_parenthesized_phone(self):
        result = self.extractor._extract_phones("Call (702) 555-0199")
        self.assertEqual(len(result), 1)

    def test_finds_dashed_phone(self):
        result = self.extractor._extract_phones("702-555-0199")
        self.assertEqual(len(result), 1)

    def test_finds_dotted_phone(self):
        result = self.extractor._extract_phones("702.555.0199")
        self.assertEqual(len(result), 1)

    def test_max_2_phones_returned(self):
        text = " ".join([f"702-555-0{i:03}" for i in range(10)])
        result = self.extractor._extract_phones(text)
        self.assertLessEqual(len(result), 2)

    def test_empty_text_returns_empty(self):
        result = self.extractor._extract_phones("")
        self.assertEqual(result, [])

    def test_no_phone_returns_empty(self):
        result = self.extractor._extract_phones("No phone here.")
        self.assertEqual(result, [])


# ── _detect_chat_widget ────────────────────────────────────────────────────────

class TestDetectChatWidget(unittest.TestCase):
    def setUp(self):
        self.extractor = _make_extractor()

    def test_detects_livechat(self):
        self.assertTrue(self.extractor._detect_chat_widget("livechat script loaded"))

    def test_detects_intercom(self):
        self.assertTrue(self.extractor._detect_chat_widget("intercom.io/widget"))

    def test_detects_drift(self):
        self.assertTrue(self.extractor._detect_chat_widget("drift chat enabled"))

    def test_detects_tawk(self):
        self.assertTrue(self.extractor._detect_chat_widget("tawk.to embed"))

    def test_detects_crisp(self):
        self.assertTrue(self.extractor._detect_chat_widget("crisp.chat widget"))

    def test_detects_tidio(self):
        self.assertTrue(self.extractor._detect_chat_widget("tidio chat"))

    def test_no_chat_widget_returns_false(self):
        self.assertFalse(self.extractor._detect_chat_widget("normal website content"))

    def test_empty_text_returns_false(self):
        self.assertFalse(self.extractor._detect_chat_widget(""))


# ── _detect_booking_system ─────────────────────────────────────────────────────

class TestDetectBookingSystem(unittest.TestCase):
    def setUp(self):
        self.extractor = _make_extractor()

    def test_detects_calendly(self):
        self.assertTrue(self.extractor._detect_booking_system("calendly link"))

    def test_detects_acuity(self):
        self.assertTrue(self.extractor._detect_booking_system("acuity scheduling"))

    def test_detects_squareup(self):
        self.assertTrue(self.extractor._detect_booking_system("squareup.com booking"))

    def test_detects_appointments(self):
        self.assertTrue(self.extractor._detect_booking_system("online appointments"))

    def test_detects_scheduleonce(self):
        self.assertTrue(self.extractor._detect_booking_system("scheduleonce"))

    def test_no_booking_system_returns_false(self):
        self.assertFalse(self.extractor._detect_booking_system("plain static site"))

    def test_empty_text_returns_false(self):
        self.assertFalse(self.extractor._detect_booking_system(""))


# ── _estimate_tech_score ───────────────────────────────────────────────────────

class TestEstimateTechScore(unittest.TestCase):
    def setUp(self):
        self.extractor = _make_extractor()

    def _score(self, html):
        soup = BeautifulSoup(html, "html.parser")
        return self.extractor._estimate_tech_score(soup, html)

    def test_modern_site_scores_higher_than_old(self):
        self.assertGreater(self._score(_MODERN_HTML), self._score(_OLD_HTML))

    def test_viewport_meta_raises_score(self):
        with_vp = self._score('<meta name="viewport" content="width=device-width">')
        without_vp = self._score("<p>no viewport</p>")
        self.assertGreater(with_vp, without_vp)

    def test_framesets_lower_score(self):
        framed = self._score("<frameset><frame src='a.html'></frameset>")
        plain = self._score("<p>modern</p>")
        self.assertLess(framed, plain)

    def test_flash_lowers_score(self):
        flash = self._score("<script src='swfobject.js'></script>")
        normal = self._score("<p>static</p>")
        self.assertLess(flash, normal)

    def test_score_clamped_0_to_100(self):
        for html in (_MODERN_HTML, _OLD_HTML, _CHAT_HTML):
            score = self._score(html)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_analytics_raises_score(self):
        with_analytics = self._score("<script src='googletagmanager.com/gtag.js'></script>")
        without = self._score("<p>nothing</p>")
        self.assertGreater(with_analytics, without)

    def test_react_raises_score(self):
        react_html = '<script>var react = require("react")</script>'
        plain_html = "<p>static only</p>"
        self.assertGreater(self._score(react_html), self._score(plain_html))

    def test_flexbox_raises_score(self):
        flex_html = "<style>.box { display: flex; }</style>"
        plain_html = "<p>no css</p>"
        self.assertGreater(self._score(flex_html), self._score(plain_html))

    def test_media_query_raises_score(self):
        responsive = "<style>@media (max-width: 768px) {}</style>"
        plain = "<p>no css</p>"
        self.assertGreater(self._score(responsive), self._score(plain))

    def test_https_in_content_raises_score(self):
        https_html = '<a href="https://example.com">Link</a>'
        plain_html = "<p>no links</p>"
        self.assertGreater(self._score(https_html), self._score(plain_html))

    def test_swf_object_lowers_score(self):
        swf = "<script src='swfobject.js'></script>"
        modern = "<p>normal</p>"
        self.assertLess(self._score(swf), self._score(modern))


# ── extract() with mocked HTTP ─────────────────────────────────────────────────

class TestExtract(unittest.TestCase):
    def test_unreachable_site_sets_error(self):
        extractor = _make_extractor()
        extractor.client.get.side_effect = Exception("Connection refused")
        result = extractor.extract("https://unreachable.example.com")
        self.assertFalse(result["reachable"])
        self.assertIsNotNone(result["error"])

    def test_http_404_sets_reachable_false(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response("", status=404)
        result = extractor.extract("https://notfound.example.com")
        self.assertFalse(result["reachable"])

    def test_http_200_sets_reachable_true(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_NO_EMAILS_HTML)
        result = extractor.extract("https://hvacpros.example.com")
        self.assertTrue(result["reachable"])

    def test_result_schema_always_present_on_error(self):
        extractor = _make_extractor()
        extractor.client.get.side_effect = Exception("Timeout")
        result = extractor.extract("https://example.com")
        required = {
            "url", "reachable", "owner_name", "emails", "phones",
            "has_chat_widget", "has_booking_system", "tech_score", "error"
        }
        self.assertTrue(required.issubset(result.keys()))

    def test_result_url_matches_input(self):
        extractor = _make_extractor()
        extractor.client.get.side_effect = Exception("No network")
        url = "https://myspecificsite.example.com"
        result = extractor.extract(url)
        self.assertEqual(result["url"], url)

    def test_result_cached_on_second_call(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_NO_EMAILS_HTML)
        url = "https://hvacpros.example.com"
        result1 = extractor.extract(url)
        result2 = extractor.extract(url)
        self.assertIs(result1, result2)
        self.assertEqual(extractor.client.get.call_count, 1)

    def test_emails_extracted_from_page(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_MODERN_HTML)
        result = extractor.extract("https://hvacpros.example.com")
        self.assertGreater(len(result["emails"]), 0)

    def test_chat_widget_detected(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_CHAT_HTML)
        result = extractor.extract("https://chat-enabled.example.com")
        self.assertTrue(result["has_chat_widget"])

    def test_booking_system_detected(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_CHAT_HTML)
        result = extractor.extract("https://calendly-site.example.com")
        self.assertTrue(result["has_booking_system"])

    def test_no_chat_on_simple_page(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_NO_EMAILS_HTML)
        result = extractor.extract("https://plain.example.com")
        self.assertFalse(result["has_chat_widget"])

    def test_tech_score_is_int(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_MODERN_HTML)
        result = extractor.extract("https://hvacpros.example.com")
        self.assertIsInstance(result["tech_score"], int)

    def test_phones_extracted_from_page(self):
        extractor = _make_extractor()
        extractor.client.get.return_value = _make_response(_NO_EMAILS_HTML)
        result = extractor.extract("https://phone-site.example.com")
        self.assertGreater(len(result["phones"]), 0)


# ── Convenience function ───────────────────────────────────────────────────────

class TestConvenienceFunction(unittest.TestCase):
    def test_extract_website_intel_returns_dict(self):
        # Offline: just verify schema is returned even on network failure
        result = extract_website_intel("https://localhost-nonexistent.example.com")
        self.assertIsInstance(result, dict)
        self.assertIn("url", result)
        self.assertIn("reachable", result)


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
