"""BBB (Better Business Bureau) adapter - scrape HVAC businesses from bbb.org.

Uses httpx for HTTP and BeautifulSoup for HTML parsing.
Rate-limited to 1 request/second to stay within polite-scraping norms.

Output schema matches YelpAdapter so the pipeline consumes both sources
interchangeably.
"""
import re
import time
from datetime import date
from typing import Any, Dict, Generator, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup


# ── Constants ──────────────────────────────────────────────────────────────────

BBB_SEARCH_URL = "https://www.bbb.org/search"
BBB_BASE_URL = "https://www.bbb.org"
REQUEST_DELAY_SECONDS = 1.0
MAX_PAGES_PER_MARKET = 10
DEFAULT_RESULTS_PER_MARKET = 100

# BBB letter grades mapped to 0-50 trust-score points
_RATING_TRUST_PTS: Dict[str, int] = {
    "A+": 50, "A": 45, "A-": 40,
    "B+": 32, "B": 28, "B-": 24,
    "C+": 18, "C": 14, "C-": 10,
    "D+": 6,  "D": 4,  "D-": 2,
    "F":  0,  "NR": 0,
}

# BBB letter grades mapped to 5.0-scale float (ICP scorer compatibility)
_RATING_NUMERIC: Dict[str, float] = {
    "A+": 5.0, "A": 4.7, "A-": 4.3,
    "B+": 3.7, "B": 3.3, "B-": 3.0,
    "C+": 2.7, "C": 2.3, "C-": 2.0,
    "D+": 1.7, "D": 1.3, "D-": 1.0,
    "F":  0.0,
}

_VALID_RATINGS = frozenset(_RATING_TRUST_PTS.keys())

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
    "HomeTeam Pest Defense",
)

# CSS selectors tried in order when looking for search-result cards
_CARD_SELECTORS: Tuple[str, ...] = (
    "[data-testid='serp-result-card']",
    "[data-testid='result-card']",
    ".result-card",
    ".SearchResult",
    "[class*='BusinessCard']",
    "[class*='result-item']",
    "li[class*='search-result']",
    "article[class*='result']",
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
}


# ── Adapter ────────────────────────────────────────────────────────────────────

class BBBAdapter:
    """Scrape HVAC businesses from BBB.org search results.

    Pagination, rate limiting, chain filtering, and trust scoring are all
    handled internally. The public ``discover()`` method returns normalized
    dicts that match the schema produced by YelpAdapter.

    Usage::

        config = yaml.safe_load(open('config.yaml'))
        bbb_cfg = config['sources']['bbb']
        adapter = BBBAdapter(bbb_cfg)
        leads = adapter.discover(['Las Vegas, NV', 'Phoenix, AZ'])
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the adapter.

        Args:
            config: The ``sources.bbb`` section of config.yaml.
        """
        self.config = config
        self.enabled: bool = config.get("enabled", False)
        self.results_per_market: int = config.get(
            "results_per_market", DEFAULT_RESULTS_PER_MARKET
        )
        self.category: str = config.get("category", "heating-air-conditioning")
        self.radius_miles: int = config.get("radius_miles", 50)

    # ── Public interface ───────────────────────────────────────────────────────

    def discover(self, markets: List[str]) -> List[Dict[str, Any]]:
        """Discover HVAC businesses in target markets via BBB.org.

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
            print("⏭️  BBB adapter disabled")
            return []

        all_companies: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for market in markets:
            parts = market.split(",")
            city = parts[0].strip()
            state = parts[1].strip() if len(parts) > 1 else "NV"

            print(f"🔍 Searching BBB in {market}...")
            market_count = 0

            for page_businesses in self.search_hvac_businesses(
                city, state, self.radius_miles
            ):
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

            print(f"  📋 BBB {market}: {market_count} businesses")
            time.sleep(REQUEST_DELAY_SECONDS)

        print(f"✅ BBB: Found {len(all_companies)} businesses total")
        return all_companies

    def search_hvac_businesses(
        self, city: str, state: str, radius_miles: int = 50
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """Search BBB for HVAC businesses, yielding one page at a time.

        Yields pages until results are exhausted or ``MAX_PAGES_PER_MARKET``
        is reached.  Each page is fetched with a 1-second delay inserted by
        the caller (``discover``).

        Args:
            city: City name (e.g. ``"Las Vegas"``).
            state: State abbreviation (e.g. ``"NV"``).
            radius_miles: Search radius (informational; BBB may ignore it).

        Yields:
            List of raw business dicts extracted from one search-results page.
        """
        location = f"{city}, {state}"

        for page_num in range(1, MAX_PAGES_PER_MARKET + 1):
            html = self._fetch_search_page(location, page_num)
            if not html:
                break

            businesses = self.extract_business_data(html)
            if not businesses:
                break  # Empty page → no more results

            yield businesses

            if not self._has_next_page(html, page_num):
                break

    def extract_business_data(self, html: str) -> List[Dict[str, Any]]:
        """Parse BBB search-results HTML and return raw business dicts.

        Tries multiple CSS selectors to locate result cards because BBB
        renders with React (server-side rendered) and class names may vary
        across deployments.

        Args:
            html: Raw HTML string from a BBB search page.

        Returns:
            List of raw business dicts.  Each dict has keys:
            ``name``, ``phone``, ``email``, ``website``, ``bbb_rating``,
            ``accreditation_years``, ``complaint_count``, ``review_count``,
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

    def calculate_trust_score(
        self,
        rating: Optional[str],
        years: int,
        complaints: int,
    ) -> int:
        """Calculate a 0-100 trust score from BBB quality signals.

        Score components:

        ==============================  =======
        Signal                          Points
        ==============================  =======
        Rating (A+ → F)                 0 – 50
        Accreditation tenure (1.5/yr)   0 – 30
        Complaint record bonus          -20 – +20
        ==============================  =======

        Complaint bonuses/penalties:

        * 0 complaints: +20
        * 1-2 complaints: +10
        * 3-5 complaints: +5
        * 6-10 complaints: ±0
        * 11-20 complaints: -5
        * 21+ complaints: -20

        Args:
            rating: BBB letter grade (``"A+"``, ``"A"``, …, ``"F"``,
                    or ``"NR"`` / ``None`` for no rating).
            years: Years of BBB accreditation; 0 means not accredited.
            complaints: Total complaints on file.

        Returns:
            Integer in ``[0, 100]``.
        """
        clean = self._clean_rating(rating)
        score: float = float(_RATING_TRUST_PTS.get(clean, 0))

        # Accreditation tenure: 1.5 pts per year, max 30 at 20 yrs
        if years > 0:
            score += min(30.0, years * 1.5)

        # Complaint record
        if complaints == 0:
            score += 20.0
        elif complaints <= 2:
            score += 10.0
        elif complaints <= 5:
            score += 5.0
        elif complaints <= 10:
            pass  # neutral
        elif complaints <= 20:
            score -= 5.0
        else:
            score -= 20.0

        return max(0, min(100, int(score)))

    def is_chain_or_franchise(self, name: Optional[str]) -> bool:
        """Return True if the business name matches a known national chain.

        Combines the built-in ``_CHAIN_BRANDS`` tuple with any extra brands
        listed under ``chain_brands`` in the adapter's config dict.

        Word-boundary regex matching is used so that ``"ARS"`` matches
        ``"ARS Rescue Rooter"`` but not ``"Parsons HVAC"``).

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
        """Convert a raw BBB business dict to the standard pipeline schema.

        Produces the same field set as YelpAdapter so downstream processors
        (chain filter, ICP scorer, database) work without modification.
        BBB-specific fields (``bbb_rating``, ``bbb_trust_score``,
        ``accreditation_years``, ``complaint_count``) are appended alongside
        the standard fields.

        Args:
            biz: Raw business dict from ``extract_business_data``.
            location: Market string used as ``service_area``.

        Returns:
            Normalized company dict.
        """
        trust_score = self.calculate_trust_score(
            biz.get("bbb_rating"),
            biz.get("accreditation_years", 0),
            biz.get("complaint_count", 0),
        )

        return {
            # ── Standard fields (match YelpAdapter schema) ─────────────────
            "company_name": biz.get("name"),
            "phone": biz.get("phone"),
            "email": biz.get("email"),
            "website": biz.get("website"),
            "address": biz.get("address"),
            "city": biz.get("city"),
            "state": biz.get("state"),
            "zip_code": biz.get("zip_code"),
            "review_count": biz.get("review_count", 0),
            "rating": self._rating_to_numeric(biz.get("bbb_rating")),
            "business_hours": None,  # not on BBB search-results pages
            "service_area": location,
            "data_source": "bbb",
            "source_id": biz.get("source_id"),
            "source_url": biz.get("source_url"),
            # ── BBB-specific enrichment ────────────────────────────────────
            "bbb_rating": biz.get("bbb_rating"),
            "bbb_trust_score": trust_score,
            "accreditation_years": biz.get("accreditation_years", 0),
            "complaint_count": biz.get("complaint_count", 0),
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
        print("📌 Using BBB stub data (5 sample businesses)")

        raw_stubs: List[Dict[str, Any]] = [
            {
                "name": "Nevada Desert Air & Heating",
                "phone": "(702) 555-0201",
                "email": "contact@nevadadesertair.example.com",
                "website": "https://nevadadesertair.example.com",
                "bbb_rating": "A+",
                "accreditation_years": 12,
                "complaint_count": 0,
                "review_count": 42,
                "address": "4210 W Flamingo Rd, Las Vegas, NV 89103",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89103",
                "source_id": "stub-bbb-001",
                "source_url": "https://www.bbb.org/biz/nevada-desert-air-stub-001",
            },
            {
                "name": "Southwest Comfort Systems",
                "phone": "(702) 555-0202",
                "email": None,
                "website": "https://swcomfort.example.com",
                "bbb_rating": "A",
                "accreditation_years": 7,
                "complaint_count": 2,
                "review_count": 18,
                "address": "2890 S Rainbow Blvd Ste 110, Las Vegas, NV 89146",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89146",
                "source_id": "stub-bbb-002",
                "source_url": "https://www.bbb.org/biz/southwest-comfort-stub-002",
            },
            {
                "name": "Vegas Valley Mechanical",
                "phone": "(702) 555-0203",
                "email": "info@vegasvalleymech.example.com",
                "website": "https://vegasvalleymech.example.com",
                "bbb_rating": "A+",
                "accreditation_years": 15,
                "complaint_count": 1,
                "review_count": 89,
                "address": "5600 McLeod Dr Unit B, Las Vegas, NV 89120",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89120",
                "source_id": "stub-bbb-003",
                "source_url": "https://www.bbb.org/biz/vegas-valley-mechanical-stub-003",
            },
            {
                # National chain — will be flagged by is_chain_or_franchise
                "name": "One Hour Heating & Air Conditioning",
                "phone": "(702) 555-0999",
                "email": "corporate@onehour.example.com",
                "website": "https://onehour.example.com",
                "bbb_rating": "B+",
                "accreditation_years": 5,
                "complaint_count": 25,
                "review_count": 3000,
                "address": "3700 S Valley View Blvd, Las Vegas, NV 89103",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89103",
                "source_id": "stub-bbb-004",
                "source_url": "https://www.bbb.org/biz/one-hour-stub-004",
            },
            {
                "name": "SunState Climate Control",
                "phone": "(702) 555-0205",
                "email": "service@sunstatecc.example.com",
                "website": None,
                "bbb_rating": "A-",
                "accreditation_years": 3,
                "complaint_count": 4,
                "review_count": 11,
                "address": "8100 W Sahara Ave, Las Vegas, NV 89117",
                "city": "Las Vegas",
                "state": "NV",
                "zip_code": "89117",
                "source_id": "stub-bbb-005",
                "source_url": "https://www.bbb.org/biz/sunstate-climate-stub-005",
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
        self, location: str, page: int = 1
    ) -> Optional[str]:
        """Fetch a BBB search-results page via httpx.

        Args:
            location: "City, State" string (e.g. ``"Las Vegas, NV"``).
            page: 1-based page number.

        Returns:
            HTML string, or ``None`` if the request fails.
        """
        params: Dict[str, Any] = {
            "find_country": "USA",
            "find_loc": location,
            "find_text": "HVAC",
            "page": page,
        }

        try:
            with httpx.Client(
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=30,
            ) as client:
                resp = client.get(BBB_SEARCH_URL, params=params)
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPStatusError as exc:
            print(
                f"❌ BBB HTTP {exc.response.status_code} "
                f"fetching page {page} for {location}"
            )
            return None
        except Exception as exc:
            print(f"❌ BBB fetch error (page {page}, {location}): {exc}")
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
            or soup.select("[data-testid='nextPage']")
            or soup.select("a[rel='next']")
            or soup.select(".pagination-next:not(.disabled)")
            or soup.select(
                "[class*='pagination'] [aria-disabled='false'][aria-label*='Next']"
            )
        )
        return bool(indicators)

    # ── HTML parsing ───────────────────────────────────────────────────────────

    def _find_result_cards(self, soup: BeautifulSoup) -> list:
        """Locate business-result card elements in a parsed page.

        Tries each selector in ``_CARD_SELECTORS`` and returns the first
        non-empty match.  This resilience is needed because BBB's React
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
        """Extract all structured fields from a single BBB result-card element.

        Args:
            card: A BeautifulSoup element representing one business result.

        Returns:
            Dict of raw business fields, or ``None`` on parse error.
        """
        try:
            name = self._extract_text(card, [
                "[data-testid='bizName']",
                ".business-title",
                "h2 a",
                "h3 a",
                ".biz-name",
                "[class*='BusinessName']",
                "[class*='business-name']",
                "a[href*='/biz/']",
            ])

            phone = self._extract_phone(card)
            email = self._extract_email(card)
            website, source_url, source_id = self._extract_urls(card)

            raw_rating = self._extract_text(card, [
                "[data-testid='BBBRating']",
                "[data-testid='rating']",
                ".rating-letter-grade",
                "[class*='Rating']",
                "[aria-label*='rating']",
                "[class*='grade']",
                "[class*='letterGrade']",
            ])
            bbb_rating = self._clean_rating(raw_rating)

            accreditation_years = self._extract_accreditation_years(card)
            complaint_count = self._extract_count(
                card,
                [
                    "[data-testid='complaintCount']",
                    "[class*='complaint']",
                    "[class*='Complaint']",
                ],
                label="complaint",
            )
            review_count = self._extract_count(
                card,
                [
                    "[data-testid='reviewCount']",
                    "[class*='review']",
                    "[class*='Review']",
                    ".review-count",
                ],
                label="review",
            )

            address_text = self._extract_text(card, [
                "[data-testid='address']",
                ".address",
                "[class*='Address']",
                "[itemprop='address']",
                "[class*='location']",
                "[class*='Location']",
            ])
            city, state, zip_code = self._parse_address(address_text)

            return {
                "name": name,
                "phone": phone,
                "email": email,
                "website": website,
                "bbb_rating": bbb_rating,
                "accreditation_years": accreditation_years,
                "complaint_count": complaint_count,
                "review_count": review_count,
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
            "[data-testid='bizPhone']",
            ".phone",
            "[class*='Phone']",
            "[class*='phone']",
        ])
        return self._clean_phone(raw)

    def _extract_email(self, card) -> Optional[str]:
        """Extract email address from a card element.

        Checks ``mailto:`` links first, then regex-scans the card's text.
        Skips BBB's own domain addresses.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Email string or ``None``.
        """
        mailto = card.select_one("[href^='mailto:']")
        if mailto:
            addr = mailto.get("href", "").replace("mailto:", "").strip()
            if addr and "bbb.org" not in addr:
                return addr

        text = card.get_text(" ")
        m = re.search(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
        )
        if m:
            email = m.group(0)
            if "example" not in email and "bbb.org" not in email:
                return email

        return None

    def _extract_urls(
        self, card
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract website URL, BBB profile URL, and slug-based source_id.

        Args:
            card: BeautifulSoup card element.

        Returns:
            Tuple of ``(website, source_url, source_id)``.
        """
        source_url: Optional[str] = None
        source_id: Optional[str] = None
        website: Optional[str] = None

        profile_link = card.select_one("a[href*='/biz/']")
        if profile_link:
            href = profile_link.get("href", "")
            if href:
                source_url = (
                    href if href.startswith("http") else BBB_BASE_URL + href
                )
                m = re.search(r"/biz/([^/?#]+)", href)
                if m:
                    source_id = m.group(1)

        # External business website (not bbb.org)
        website_el = card.select_one("[data-testid='bizWebsite']")
        if not website_el:
            website_el = card.select_one(
                "a[href^='http']:not([href*='bbb.org'])"
            )
        if website_el:
            href = website_el.get("href", "")
            if href and "bbb.org" not in href:
                website = href

        return website, source_url, source_id

    def _extract_count(
        self,
        card,
        selectors: List[str],
        label: str,
    ) -> int:
        """Extract a numeric count (reviews or complaints) from a card.

        First tries the provided selectors; falls back to a regex scan of
        the card's full text for patterns like "3 complaints" or "42 reviews".

        Args:
            card: BeautifulSoup card element.
            selectors: CSS selectors targeting the count element.
            label: Singular noun to match in fallback regex (``"complaint"``
                   or ``"review"``).

        Returns:
            Integer count; ``0`` if not found.
        """
        text = self._extract_text(card, selectors)
        if text:
            m = re.search(r"(\d[\d,]*)", text)
            if m:
                return int(m.group(1).replace(",", ""))

        full = card.get_text(" ", strip=True)
        m = re.search(
            rf"(\d[\d,]*)\s+{re.escape(label)}", full, re.IGNORECASE
        )
        if m:
            return int(m.group(1).replace(",", ""))

        return 0

    def _extract_accreditation_years(self, card) -> int:
        """Infer how many years a business has been BBB-accredited.

        Parsing priority:
        1. "Accredited since YYYY" / "Member since YYYY"
        2. "N years accredited"
        3. Accreditation badge present (return 1)
        4. No evidence (return 0)

        Args:
            card: BeautifulSoup card element.

        Returns:
            Integer year count; ``0`` means not accredited.
        """
        full = card.get_text(" ", strip=True)

        m = re.search(
            r"(?:accredited|member)\s+since\s+(\d{4})",
            full,
            re.IGNORECASE,
        )
        if m:
            year = int(m.group(1))
            return max(0, date.today().year - year)

        m = re.search(
            r"(\d+)\s+years?\s+(?:accredited|member)",
            full,
            re.IGNORECASE,
        )
        if m:
            return int(m.group(1))

        badge = card.select_one(
            "[data-testid='accredited'], "
            "[class*='Accredited'], "
            "[aria-label*='Accredited']"
        )
        if badge:
            return 1

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

    def _clean_rating(self, rating: Optional[str]) -> str:
        """Normalize a BBB letter-grade string to a canonical form.

        Args:
            rating: Raw rating string (e.g. ``"A+"``, ``"Rating: A-"``,
                    ``"no rating"``).

        Returns:
            Canonical rating string from ``_VALID_RATINGS``, or ``"NR"``.
        """
        if not rating:
            return "NR"
        cleaned = rating.strip().upper()
        if cleaned in _VALID_RATINGS:
            return cleaned
        # Use negative lookbehind so "A" in "RATING" doesn't shadow a trailing "A+"
        m = re.search(r"(?<!\w)([A-F][+-]?)(?!\w)", cleaned)
        if m and m.group(1) in _VALID_RATINGS:
            return m.group(1)
        return "NR"

    def _rating_to_numeric(self, rating: Optional[str]) -> Optional[float]:
        """Map a BBB letter grade to a 5.0-scale float.

        Used to populate the standard ``rating`` field so the ICP scorer
        and database receive a consistent numeric value regardless of source.

        Args:
            rating: BBB letter grade string.

        Returns:
            Float in ``[0.0, 5.0]``, or ``None`` for unrated (``"NR"``).
        """
        return _RATING_NUMERIC.get(self._clean_rating(rating))

    def _parse_address(
        self, address: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Split a full address string into ``(city, state, zip)`` components.

        Handles the common US format: ``"<Street>, <City>, <ST> <ZIP>"``.
        Extracts the last city/state/zip group so street lines don't
        interfere.

        Args:
            address: Full address string (e.g.
                     ``"4210 W Flamingo Rd, Las Vegas, NV 89103"``).

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
