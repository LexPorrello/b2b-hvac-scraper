"""Angi (formerly Angie's List) adapter - scrape HVAC businesses from angi.com.

Uses httpx for HTTP and BeautifulSoup for HTML parsing.
Rate-limited to 1 request/second to stay within polite-scraping norms.

Output schema matches YelpAdapter / BBBAdapter so the pipeline consumes all
sources interchangeably.
"""
import re
import time
from datetime import date
from typing import Any, Dict, Generator, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup


# ── Constants ──────────────────────────────────────────────────────────────────

ANGI_BASE_URL = "https://www.angi.com"
ANGI_COMPANYLIST_URL = "https://www.angi.com/companylist/{city_slug}/{category_slug}.htm"
ANGI_COMPANYLIST_PAGE_URL = "https://www.angi.com/companylist/{city_slug}/{category_slug}/{page}.htm"

REQUEST_DELAY_SECONDS = 1.0
MAX_PAGES_PER_MARKET = 10
DEFAULT_RESULTS_PER_MARKET = 200
DEFAULT_CATEGORY_SLUG = "hvac-contractors"

# Map config category keys to Angi URL slugs
_CATEGORY_SLUG_MAP: Dict[str, str] = {
    "hvac-heating-cooling": "hvac-contractors",
    "hvac": "hvac-contractors",
    "heating-air-conditioning": "hvac-contractors",
    "hvac-contractors": "hvac-contractors",
}

# National HVAC chain brands — supplements whatever is in config.yaml
_CHAIN_BRANDS: Tuple[str, ...] = (
    "One Hour Heating",
    "One Hour Air",
    "ARS Rescue Rooter",
    "ARS",
    "Goettl",
    "American Home Shield",
    "Precision Air",
    "Aire Serv",
    "Mr. Appliance",
    "Benjamin Franklin Plumbing",
    "Mister Sparky",
    "Service Experts",
    "BELFOR",
    "Restoration 1",
    "Servpro",
    "1-800-PLUMBER",
    "Rooter Hero",
    "ABC Home & Commercial Services",
    "HomeAdvisor Direct",
    "Angi Leads",
    "Sears Home Services",
    "Home Depot",
    "Comfort Systems USA",
    "EMCOR",
    "Johnson Controls",
    "Trane",
    "Lennox",
    "Carrier",
    "Bryant",
    "Day & Night",
    "Four Seasons Heating",
    "Service Champions",
)

# CSS selectors tried in order when looking for business listing cards
_CARD_SELECTORS: Tuple[str, ...] = (
    "[data-testid='provider-card']",
    "[data-testid='business-card']",
    "[class*='ProviderCard']",
    "[class*='BusinessCard']",
    "[class*='provider-card']",
    "[class*='business-card']",
    "article[class*='provider']",
    "article[class*='listing']",
    "li[class*='provider']",
    "li[class*='result']",
    "[class*='CompanyCard']",
    "[class*='company-card']",
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.angi.com/",
}


# ── Adapter ────────────────────────────────────────────────────────────────────

class AngiAdapter:
    """Scrape HVAC businesses from Angi.com (formerly Angie's List).

    Pagination, rate limiting, chain filtering, and reliability scoring are
    all handled internally. The public ``discover()`` method returns normalized
    dicts that match the schema produced by YelpAdapter and BBBAdapter.

    Usage::

        config = yaml.safe_load(open('config.yaml'))
        angi_cfg = config['sources']['angi']
        adapter = AngiAdapter(angi_cfg)
        leads = adapter.discover(['Las Vegas, NV', 'Phoenix, AZ'])
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the adapter.

        Args:
            config: The ``sources.angi`` section of config.yaml.
        """
        self.config = config
        self.enabled: bool = config.get("enabled", False)
        self.results_per_market: int = config.get(
            "results_per_market", DEFAULT_RESULTS_PER_MARKET
        )
        raw_category: str = config.get("category", "hvac-heating-cooling")
        self.category_slug: str = _CATEGORY_SLUG_MAP.get(
            raw_category, DEFAULT_CATEGORY_SLUG
        )

    # ── Public interface ───────────────────────────────────────────────────────

    def discover(self, markets: List[str]) -> List[Dict[str, Any]]:
        """Discover HVAC businesses in target markets via Angi.com.

        Paginates through search results for each market until
        ``results_per_market`` is reached or no more pages exist.
        Rate-limited to at most one request per second.

        Args:
            markets: List of "City, State" strings
                     (e.g. ``["Las Vegas, NV", "Phoenix, AZ"]``).

        Returns:
            List of company dicts using the standard pipeline schema.
        """
        if not self.enabled:
            print("⏭️  Angi adapter disabled")
            return []

        all_companies: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for market in markets:
            parts = market.split(",")
            city = parts[0].strip()
            state = parts[1].strip() if len(parts) > 1 else "NV"  # noqa: F841

            print(f"🔍 Searching Angi in {market}...")
            market_count = 0

            for page_businesses in self.search_hvac_businesses(city, state):
                for biz in page_businesses:
                    normalized = self._normalize(biz, market)
                    source_id = normalized.get("source_id") or ""

                    if source_id and source_id in seen_ids:
                        continue
                    if source_id:
                        seen_ids.add(source_id)

                    all_companies.append(normalized)
                    market_count += 1

                    if market_count >= self.results_per_market:
                        break

                if market_count >= self.results_per_market:
                    break

                time.sleep(REQUEST_DELAY_SECONDS)

            print(f"  📋 Angi {market}: {market_count} businesses")
            time.sleep(REQUEST_DELAY_SECONDS)

        print(f"✅ Angi: Found {len(all_companies)} businesses total")
        return all_companies

    def search_hvac_businesses(
        self, city: str, state: str  # noqa: ARG002
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """Search Angi for HVAC businesses, yielding one page at a time.

        Yields pages until results are exhausted or ``MAX_PAGES_PER_MARKET``
        is reached. Each page is fetched with a 1-second delay inserted by
        the caller (``discover``).

        Args:
            city: City name (e.g. ``"Las Vegas"``).
            state: State abbreviation (e.g. ``"NV"``); used for context only.

        Yields:
            List of raw business dicts extracted from one search-results page.
        """
        city_slug = self._to_city_slug(city)

        for page_num in range(1, MAX_PAGES_PER_MARKET + 1):
            html = self._fetch_search_page(city_slug, page_num)
            if not html:
                break

            businesses = self.extract_business_data(html)
            if not businesses:
                break

            yield businesses

            if not self._has_next_page(html, page_num):
                break

    def extract_business_data(self, html: str) -> List[Dict[str, Any]]:
        """Parse Angi search-results HTML and return raw business dicts.

        Tries multiple CSS selectors to locate result cards because Angi
        renders with React (server-side rendered) and class names vary
        across deployments.

        Args:
            html: Raw HTML string from an Angi companylist page.

        Returns:
            List of raw business dicts. Each dict has keys:
            ``name``, ``phone``, ``email``, ``website``, ``angi_rating``,
            ``review_count``, ``years_in_business``, ``service_area``,
            ``address``, ``city``, ``state``, ``zip_code``,
            ``source_id``, ``source_url``.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = self._find_result_cards(soup)
        businesses: List[Dict[str, Any]] = []

        for card in cards:
            biz = self._parse_business_card(card)
            if biz and biz.get("name"):
                businesses.append(biz)

        return businesses

    def calculate_reliability_score(
        self,
        rating: Optional[float],
        reviews: int,
        years: int,
    ) -> int:
        """Calculate a 0-100 reliability score from Angi quality signals.

        Score components:

        ==============================  =======
        Signal                          Points
        ==============================  =======
        Star rating (0-5 → 0-50 pts)    0 – 50
        Review volume (step scale)       0 – 30
        Years in business (1.5/yr)       0 – 20
        ==============================  =======

        Review breakpoints:

        * 0 reviews: 0 pts
        * 1-4 reviews: 5 pts
        * 5-9 reviews: 10 pts
        * 10-24 reviews: 15 pts
        * 25-49 reviews: 20 pts
        * 50-99 reviews: 25 pts
        * 100-499 reviews: 28 pts
        * 500+ reviews: 30 pts

        Args:
            rating: Angi star rating (0.0–5.0), or ``None`` if unrated.
            reviews: Total review count.
            years: Years in business; 0 means unknown.

        Returns:
            Integer in ``[0, 100]``.
        """
        score: float = 0.0

        # Rating component: 0-50 pts
        if rating is not None and rating >= 0:
            score += (rating / 5.0) * 50.0

        # Review volume component: step scale, 0-30 pts
        if reviews >= 500:
            score += 30.0
        elif reviews >= 100:
            score += 28.0
        elif reviews >= 50:
            score += 25.0
        elif reviews >= 25:
            score += 20.0
        elif reviews >= 10:
            score += 15.0
        elif reviews >= 5:
            score += 10.0
        elif reviews >= 1:
            score += 5.0

        # Years in business: 1.5 pts per year, cap at 20 pts (~13+ years)
        if years > 0:
            score += min(20.0, years * 1.5)

        return max(0, min(100, int(score)))

    def is_chain_or_franchise(self, name: Optional[str]) -> bool:
        """Return True if the business name matches a known national chain.

        Combines the built-in ``_CHAIN_BRANDS`` tuple with any extra brands
        listed under ``chain_brands`` in the adapter's config dict.

        Word-boundary regex matching is used so that ``"ARS"`` matches
        ``"ARS Rescue Rooter"`` but not ``"Parsons HVAC"``.

        Args:
            name: Business name to check.

        Returns:
            ``True`` if the business is a known chain or franchise.
        """
        if not name:
            return False

        name_lower = name.lower()
        config_brands: List[str] = self.config.get("chain_brands", [])
        all_brands = list(_CHAIN_BRANDS) + config_brands

        for brand in all_brands:
            brand_lower = brand.lower()
            if name_lower == brand_lower:
                return True
            pattern = r"\b" + re.escape(brand_lower) + r"\b"
            if re.search(pattern, name_lower):
                return True

        # Pattern-based franchise indicators
        for pattern in (
            r"\bfranchis(?:e|ing)\b",
            r"\bnationwide\b",
            r"\bnational\b.*\bhvac\b",
        ):
            if re.search(pattern, name_lower):
                return True

        return False

    # ── Normalization ──────────────────────────────────────────────────────────

    def _normalize(self, biz: Dict[str, Any], location: str) -> Dict[str, Any]:
        """Convert a raw Angi business dict to the standard pipeline schema.

        Produces the same field set as YelpAdapter / BBBAdapter so downstream
        processors (chain filter, ICP scorer, database) work without
        modification. Angi-specific fields (``angi_rating``,
        ``angi_reliability_score``, ``years_in_business``) are appended
        alongside the standard fields.

        Args:
            biz: Raw business dict from ``extract_business_data``.
            location: Market string used as ``service_area`` fallback.

        Returns:
            Normalized company dict.
        """
        reliability_score = self.calculate_reliability_score(
            biz.get("angi_rating"),
            biz.get("review_count", 0),
            biz.get("years_in_business", 0),
        )

        return {
            # ── Standard fields (match Yelp/BBB adapter schema) ───────────
            "company_name": biz.get("name"),
            "phone": biz.get("phone"),
            "email": biz.get("email"),
            "website": biz.get("website"),
            "address": biz.get("address"),
            "city": biz.get("city"),
            "state": biz.get("state"),
            "zip_code": biz.get("zip_code"),
            "review_count": biz.get("review_count", 0),
            "rating": biz.get("angi_rating"),
            "business_hours": None,  # not on Angi companylist pages
            "service_area": biz.get("service_area") or location,
            "data_source": "angi",
            "source_id": biz.get("source_id"),
            "source_url": biz.get("source_url"),
            # ── Angi-specific enrichment ───────────────────────────────────
            "angi_rating": biz.get("angi_rating"),
            "angi_reliability_score": reliability_score,
            "years_in_business": biz.get("years_in_business", 0),
        }

    def _stub_data(self, markets: List[str]) -> List[Dict[str, Any]]:
        """Return realistic stub records for offline tests and dry runs.

        Returns normalized dicts (not raw) so they drop straight into the
        pipeline without further processing.

        Args:
            markets: Target markets; only the first market is populated.

        Returns:
            List of 5 normalized company dicts.
        """
        print("📌 Using Angi stub data (5 sample businesses)")

        raw_stubs: List[Dict[str, Any]] = [
            {
                "name": "Silver State Air & Heat",
                "phone": "(702) 555-0301",
                "email": "info@silverstatehvac.example.com",
                "website": "https://silverstatehvac.example.com",
                "angi_rating": 4.8,
                "review_count": 127,
                "years_in_business": 14,
                "service_area": "Las Vegas, NV",
                "address": "3100 E Charleston Blvd, Las Vegas, NV 89104",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89104",
                "source_id": "stub-angi-001",
                "source_url": "https://www.angi.com/companylist/las-vegas/hvac-contractors/stub-001",
            },
            {
                "name": "Desert Premium HVAC",
                "phone": "(702) 555-0302",
                "email": None,
                "website": "https://desertpremiumhvac.example.com",
                "angi_rating": 4.5,
                "review_count": 43,
                "years_in_business": 8,
                "service_area": "Las Vegas, NV",
                "address": "1800 S Industrial Rd, Las Vegas, NV 89102",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89102",
                "source_id": "stub-angi-002",
                "source_url": "https://www.angi.com/companylist/las-vegas/hvac-contractors/stub-002",
            },
            {
                "name": "Nevada Cool Air",
                "phone": "(702) 555-0303",
                "email": "service@nevadacoolair.example.com",
                "website": None,
                "angi_rating": 4.2,
                "review_count": 18,
                "years_in_business": 5,
                "service_area": "Henderson, NV",
                "address": "2400 Wigwam Pkwy, Henderson, NV 89014",
                "city": "Henderson",
                "state": "NV",
                "zip_code": "89014",
                "source_id": "stub-angi-003",
                "source_url": "https://www.angi.com/companylist/las-vegas/hvac-contractors/stub-003",
            },
            {
                # National chain — will be flagged by is_chain_or_franchise
                "name": "One Hour Heating & Air Conditioning",
                "phone": "(702) 555-0999",
                "email": "corporate@onehour.example.com",
                "website": "https://onehour.example.com",
                "angi_rating": 4.0,
                "review_count": 1200,
                "years_in_business": 20,
                "service_area": "Las Vegas, NV",
                "address": "3700 S Valley View Blvd, Las Vegas, NV 89103",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89103",
                "source_id": "stub-angi-004",
                "source_url": "https://www.angi.com/companylist/las-vegas/hvac-contractors/stub-004",
            },
            {
                "name": "Mojave Valley Mechanical",
                "phone": "(702) 555-0305",
                "email": "contact@mojavevalleymech.example.com",
                "website": "https://mojavevalleymech.example.com",
                "angi_rating": 3.8,
                "review_count": 7,
                "years_in_business": 3,
                "service_area": "Las Vegas, NV",
                "address": "6250 McLeod Dr, Las Vegas, NV 89120",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89120",
                "source_id": "stub-angi-005",
                "source_url": "https://www.angi.com/companylist/las-vegas/hvac-contractors/stub-005",
            },
        ]

        target_market = markets[0] if markets else "Las Vegas, NV"
        result: List[Dict[str, Any]] = []
        for biz in raw_stubs:
            normalized = self._normalize(biz, target_market)
            normalized["is_chain"] = self.is_chain_or_franchise(
                normalized["company_name"]
            )
            result.append(normalized)

        return result

    # ── HTTP layer ─────────────────────────────────────────────────────────────

    def _fetch_search_page(
        self, city_slug: str, page: int = 1
    ) -> Optional[str]:
        """Fetch an Angi companylist page via httpx.

        Page 1: ``/companylist/{city}/{category}.htm``
        Page N: ``/companylist/{city}/{category}/{n}.htm``

        Args:
            city_slug: Hyphenated city slug (e.g. ``"las-vegas"``).
            page: 1-based page number.

        Returns:
            HTML string, or ``None`` if the request fails.
        """
        if page == 1:
            url = ANGI_COMPANYLIST_URL.format(
                city_slug=city_slug, category_slug=self.category_slug
            )
        else:
            url = ANGI_COMPANYLIST_PAGE_URL.format(
                city_slug=city_slug,
                category_slug=self.category_slug,
                page=page,
            )

        try:
            with httpx.Client(
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=30,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPStatusError as exc:
            print(
                f"❌ Angi HTTP {exc.response.status_code} "
                f"fetching page {page} for {city_slug}"
            )
            return None
        except Exception as exc:
            print(f"❌ Angi fetch error (page {page}, {city_slug}): {exc}")
            return None

    def _has_next_page(self, html: str, current_page: int) -> bool:
        """Return True when the page contains an active 'next page' element.

        Args:
            html: HTML of the current page.
            current_page: Current 1-based page index.

        Returns:
            ``True`` if pagination indicates more results exist.
        """
        if current_page >= MAX_PAGES_PER_MARKET:
            return False

        soup = BeautifulSoup(html, "html.parser")
        indicators = (
            soup.select("[aria-label='Next page']")
            or soup.select("[aria-label='Go to next page']")
            or soup.select("[data-testid='nextPage']")
            or soup.select("a[rel='next']")
            or soup.select(".pagination-next:not(.disabled)")
            or soup.select("[class*='pagination'] a[aria-disabled='false']")
            or soup.select("[class*='next-page']")
        )
        return bool(indicators)

    # ── HTML parsing ───────────────────────────────────────────────────────────

    def _find_result_cards(self, soup: BeautifulSoup) -> list:
        """Locate business-result card elements in a parsed page.

        Tries each selector in ``_CARD_SELECTORS`` and returns the first
        non-empty match. This resilience is needed because Angi's React
        rendering may change class names between deployments.

        Args:
            soup: Parsed page.

        Returns:
            List of card elements (may be empty if no results found).
        """
        for selector in _CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _parse_business_card(self, card) -> Optional[Dict[str, Any]]:
        """Extract all structured fields from a single Angi result-card element.

        Args:
            card: A BeautifulSoup element representing one business result.

        Returns:
            Dict of raw business fields, or ``None`` on parse error.
        """
        try:
            name = self._extract_text(card, [
                "[data-testid='business-name']",
                "[data-testid='provider-name']",
                "[class*='businessName']",
                "[class*='BusinessName']",
                "[class*='companyName']",
                "[class*='CompanyName']",
                "[class*='provider-name']",
                "h2 a",
                "h3 a",
                "h2",
                "h3",
                "a[href*='/companies/']",
                "a[href*='/provider/']",
            ])

            phone = self._extract_phone(card)
            email = self._extract_email(card)
            website, source_url, source_id = self._extract_urls(card)
            angi_rating = self._extract_rating(card)
            review_count = self._extract_review_count(card)
            years_in_business = self._extract_years_in_business(card)
            service_area = self._extract_text(card, [
                "[data-testid='service-area']",
                "[class*='serviceArea']",
                "[class*='ServiceArea']",
                "[class*='service-area']",
            ])

            address_text = self._extract_text(card, [
                "[data-testid='address']",
                "[class*='address']",
                "[class*='Address']",
                "[itemprop='address']",
                "[class*='location-text']",
            ])
            city, state, zip_code = self._parse_address(address_text)

            return {
                "name": name,
                "phone": phone,
                "email": email,
                "website": website,
                "angi_rating": angi_rating,
                "review_count": review_count,
                "years_in_business": years_in_business,
                "service_area": service_area,
                "address": address_text,
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "source_id": source_id,
                "source_url": source_url,
            }
        except Exception:
            return None

    # ── Field extractors ───────────────────────────────────────────────────────

    def _extract_text(
        self, element, selectors: List[str]
    ) -> Optional[str]:
        """Try each CSS selector; return the first non-empty text match.

        Args:
            element: BeautifulSoup element to search within.
            selectors: Ordered list of CSS selector strings.

        Returns:
            Stripped text, or ``None`` if no selector matches.
        """
        for sel in selectors:
            found = element.select_one(sel)
            if found:
                text = found.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_phone(self, card) -> Optional[str]:
        """Extract and normalize the business phone number from a card.

        Prefers ``href="tel:…"`` links; falls back to text selectors.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Formatted phone string or ``None``.
        """
        tel_el = card.select_one("[href^='tel:']")
        if tel_el:
            raw = tel_el.get("href", "").replace("tel:", "")
            return self._clean_phone(raw)

        raw = self._extract_text(card, [
            "[data-testid='phone-number']",
            "[data-testid='phone']",
            "[class*='phoneNumber']",
            "[class*='PhoneNumber']",
            "[class*='phone']",
            ".phone",
        ])
        return self._clean_phone(raw)

    def _extract_email(self, card) -> Optional[str]:
        """Extract email address from a card element.

        Checks ``mailto:`` links first, then regex-scans the card's text.
        Skips Angi's own domain addresses.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Email string or ``None``.
        """
        mailto = card.select_one("[href^='mailto:']")
        if mailto:
            addr = mailto.get("href", "").replace("mailto:", "").strip()
            if addr and "angi.com" not in addr and "angieslist.com" not in addr:
                return addr

        text = card.get_text(" ")
        m = re.search(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
        )
        if m:
            email = m.group(0)
            if (
                "example" not in email
                and "angi.com" not in email
                and "angieslist.com" not in email
            ):
                return email

        return None

    def _extract_urls(
        self, card
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract website URL, Angi profile URL, and slug-based source_id.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Tuple of ``(website, source_url, source_id)``.
        """
        source_url: Optional[str] = None
        source_id: Optional[str] = None
        website: Optional[str] = None

        # Angi profile link patterns
        for href_fragment in ("/companies/", "/provider/", "/contractor/"):
            profile_link = card.select_one(f"a[href*='{href_fragment}']")
            if profile_link:
                href = profile_link.get("href", "")
                if href:
                    source_url = (
                        href
                        if href.startswith("http")
                        else ANGI_BASE_URL + href
                    )
                    m = re.search(
                        r"/(?:companies|provider|contractor)/([^/?#]+)",
                        href,
                    )
                    if m:
                        source_id = m.group(1)
                    break

        # External business website (not angi.com / angieslist.com)
        for el in card.select("a[href^='http']"):
            href = el.get("href", "")
            if (
                href
                and "angi.com" not in href
                and "angieslist.com" not in href
                and "homeadvisor.com" not in href
            ):
                website = href
                break

        return website, source_url, source_id

    def _extract_rating(self, card) -> Optional[float]:
        """Extract the Angi star rating as a float in ``[0.0, 5.0]``.

        Checks aria-labels first (``"4.8 out of 5 stars"``), then data
        attributes, then text selectors.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Float in ``[0.0, 5.0]``, or ``None`` if no rating found.
        """
        # aria-label patterns: "4.8 out of 5", "Rated 4.5 stars"
        for el in card.select("[aria-label]"):
            label = el.get("aria-label", "")
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:out\s*of\s*5|stars?)",
                label,
                re.IGNORECASE,
            )
            if m:
                try:
                    return max(0.0, min(5.0, float(m.group(1))))
                except ValueError:
                    pass

        # data-rating / data-score / data-star-rating attributes
        for attr in ("data-rating", "data-score", "data-star-rating"):
            el = card.select_one(f"[{attr}]")
            if el:
                try:
                    return max(0.0, min(5.0, float(el.get(attr, ""))))
                except ValueError:
                    pass

        # Text selectors
        raw = self._extract_text(card, [
            "[data-testid='star-rating']",
            "[data-testid='rating']",
            "[class*='starRating']",
            "[class*='StarRating']",
            "[class*='rating-value']",
            "[class*='ratingValue']",
        ])
        if raw:
            m = re.search(r"(\d+(?:\.\d+)?)", raw)
            if m:
                try:
                    val = float(m.group(1))
                    if val <= 5.0:
                        return val
                except ValueError:
                    pass

        return None

    def _extract_review_count(self, card) -> int:
        """Extract total review count from a card element.

        Checks aria-labels for patterns like ``"128 reviews"``, then
        dedicated CSS selectors, then falls back to a full-text scan.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Integer count; ``0`` if not found.
        """
        for el in card.select("[aria-label]"):
            label = el.get("aria-label", "")
            m = re.search(r"(\d[\d,]*)\s+review", label, re.IGNORECASE)
            if m:
                return int(m.group(1).replace(",", ""))

        raw = self._extract_text(card, [
            "[data-testid='review-count']",
            "[data-testid='reviewCount']",
            "[class*='reviewCount']",
            "[class*='ReviewCount']",
            "[class*='review-count']",
            "[class*='numReviews']",
        ])
        if raw:
            m = re.search(r"(\d[\d,]*)", raw)
            if m:
                return int(m.group(1).replace(",", ""))

        # Fallback: scan full card text
        full = card.get_text(" ", strip=True)
        m = re.search(r"(\d[\d,]*)\s+review", full, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))

        return 0

    def _extract_years_in_business(self, card) -> int:
        """Extract years in business from a card element.

        Parsing priority:

        1. ``"N years in business"`` / ``"in business N years"``
        2. ``"Established YYYY"`` / ``"Since YYYY"`` / ``"Founded YYYY"``
        3. CSS selector targeting a years-in-business element
        4. No evidence → return ``0``

        Args:
            card: BeautifulSoup card element.

        Returns:
            Integer year count; ``0`` means unknown.
        """
        full = card.get_text(" ", strip=True)

        # "N years in business" or "in business N years"
        m = re.search(
            r"(\d+)\s+years?\s+in\s+business|in\s+business\s+(\d+)\s+years?",
            full,
            re.IGNORECASE,
        )
        if m:
            return int(m.group(1) or m.group(2))

        # "Established YYYY" / "Since YYYY" / "Founded YYYY"
        m = re.search(
            r"(?:established|since|founded|est\.?)\s*(\d{4})",
            full,
            re.IGNORECASE,
        )
        if m:
            year = int(m.group(1))
            return max(0, date.today().year - year)

        # CSS selector approach
        raw = self._extract_text(card, [
            "[data-testid='years-in-business']",
            "[class*='yearsInBusiness']",
            "[class*='YearsInBusiness']",
            "[class*='years-in-business']",
            "[class*='established']",
        ])
        if raw:
            m = re.search(r"(\d+)", raw)
            if m:
                val = int(m.group(1))
                # Distinguish year counts (≤100) from founding years (>1900)
                if val > 1900:
                    return max(0, date.today().year - val)
                return val

        return 0

    # ── String utilities ───────────────────────────────────────────────────────

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        """Normalize any phone string to ``(NXX) NXX-XXXX`` format.

        Strips all non-digit characters; handles optional leading ``1``.
        Returns the original stripped string if it can't be normalized to
        10 digits (e.g. international numbers).

        Args:
            phone: Raw phone string (from HTML text or ``tel:`` href).

        Returns:
            Formatted phone string or ``None`` if input is empty.
        """
        if not phone:
            return None
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits[0] == "1":
            digits = digits[1:]
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        stripped = phone.strip()
        return stripped or None

    def _to_city_slug(self, city: str) -> str:
        """Convert a city name to an Angi URL slug.

        ``"Las Vegas"``  → ``"las-vegas"``
        ``"St. George"`` → ``"st-george"``

        Args:
            city: Human-readable city name.

        Returns:
            URL-safe hyphenated slug.
        """
        slug = city.lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug.strip())
        return slug

    def _parse_address(
        self, address: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Split a full address string into ``(city, state, zip)`` components.

        Handles the common US format: ``"<Street>, <City>, <ST> <ZIP>"``.
        Extracts the last city/state/zip group so street lines don't
        interfere.

        Args:
            address: Full address string (e.g.
                     ``"3100 E Charleston Blvd, Las Vegas, NV 89104"``).

        Returns:
            Tuple ``(city, state_abbr, zip_code)``; each element may be
            ``None`` if the address can't be parsed.
        """
        if not address:
            return None, None, None

        m = re.search(r"([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?", address)
        if m:
            city = m.group(1).strip()
            state = m.group(2).strip()
            zip_code = (m.group(3) or "").strip() or None
            return city, state, zip_code

        return None, None, None
