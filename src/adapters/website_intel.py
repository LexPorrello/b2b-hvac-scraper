"""
Website Intelligence Extractor
==============================

Visits HVAC business websites to extract:
- Owner/leadership names from "About Us" / "Team"
- Contact emails (public on Contact page)
- Chat widget presence (live chat software)
- Booking system presence (Calendly, etc.)
- Tech stack hints (old vs modern site)

Usage:
    from website_intel import WebsiteExtractor
    
    intel = WebsiteExtractor()
    data = intel.extract("https://desertairhvac.com")
    # Returns: owner_name, emails, has_chat, has_booking, tech_score
"""

import re
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("website_intel")


class WebsiteExtractor:
    """Extract intelligence from business websites."""
    
    CHAT_WIDGETS = [
        "livechat", "intercom", "drift", "crisp", "tawk",
        "zendesk", "hubspot", "boldchat", "olark", "tidio",
        "freshdesk", "zendesk", "liveperson",
    ]
    
    BOOKING_SYSTEMS = [
        "calendly", "acuity", "squareup", "bookings", "booking",
        "appointments", "scheduleonce", "vagaro", "genbook",
    ]
    
    OWNER_TITLES = [
        "owner", "founder", "president", "ceo", "principal",
        "chief executive", "managing partner", "partner",
    ]
    
    def __init__(self, timeout: int = 15):
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HermesBot/1.0)",
            },
            follow_redirects=True,
        )
        self._cache: dict[str, dict] = {}
    
    def extract(self, url: str) -> dict:
        """Extract intelligence from a website."""
        if url in self._cache:
            return self._cache[url]
        
        result = {
            "url": url,
            "reachable": False,
            "owner_name": None,
            "emails": [],
            "phones": [],
            "has_chat_widget": False,
            "has_booking_system": False,
            "tech_score": 50,  # default
            "age_estimate": None,  # years old
            "error": None,
        }
        
        try:
            # Fetch homepage
            resp = self.client.get(url)
            if resp.status_code >= 400:
                result["error"] = f"HTTP {resp.status_code}"
                return result
            
            result["reachable"] = True
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract emails from homepage
            result["emails"] = self._extract_emails(resp.text)
            result["phones"] = self._extract_phones(resp.text)
            
            # Check for chat widget
            result["has_chat_widget"] = self._detect_chat_widget(resp.text.lower())
            
            # Check for booking system
            result["has_booking_system"] = self._detect_booking_system(resp.text.lower())
            
            # Estimate tech modernity
            result["tech_score"] = self._estimate_tech_score(soup, resp.text)
            
            # Try to find owner name
            result["owner_name"] = self._find_owner_name(soup, url)
            
            logger.info(f"Extracted intel from {url}: {len(result['emails'])} emails, chat={result['has_chat_widget']}, booking={result['has_booking_system']}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"Failed to extract from {url}: {e}")
        
        self._cache[url] = result
        return result
    
    def _extract_emails(self, text: str) -> list[str]:
        """Find email addresses in text."""
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found = re.findall(pattern, text)
        # Filter out common non-owner emails
        filtered = [e for e in set(found) if not any(skip in e.lower() for skip in [
            "noreply", "no-reply", "donotreply", "@sentry.io", ".png@", ".jpg@"
        ])]
        return filtered[:3]  # Max 3
    
    def _extract_phones(self, text: str) -> list[str]:
        """Find phone numbers in text."""
        pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        found = re.findall(pattern, text)
        return list(set(found))[:2]
    
    def _detect_chat_widget(self, text: str) -> bool:
        """Check if page contains chat widget scripts."""
        return any(widget in text for widget in self.CHAT_WIDGETS)
    
    def _detect_booking_system(self, text: str) -> bool:
        """Check if page contains booking system."""
        return any(system in text for system in self.BOOKING_SYSTEMS)
    
    def _estimate_tech_score(self, soup, text: str) -> int:
        """Estimate website tech modernity (0-100)."""
        score = 50  # baseline
        
        # +10 for responsive meta tag
        viewport = soup.find("meta", {"name": "viewport"})
        if viewport:
            score += 10
        
        # +10 for mobile-friendly indicators
        if "@media" in text:
            score += 5
        if "flexbox" in text or "flex" in text:
            score += 5
        
        # +10 for SSL
        if "https" in text or "ssl" in text:
            score += 10
        
        # +10 for modern frameworks
        modern_js = ["react", "vue", "angular", "next.js", "nuxt"]
        if any(fw in text.lower() for fw in modern_js):
            score += 10
        
        # +10 for analytics (shows they track leads)
        analytics = ["googletagmanager", "gtag", "analytics", "plausible", "mixpanel"]
        if any(a in text for a in analytics):
            score += 10
        
        # Penalties
        # -20 for very old patterns (frames, flash, tables for layout)
        if "<frameset" in text or "<frame " in text:
            score -= 20
        if "swfobject" in text or ".swf" in text:
            score -= 15
        
        return max(0, min(100, score))
    
    def _find_owner_name(self, soup, base_url: str) -> Optional[str]:
        """Try to find business owner name from About/Team pages."""
        # Strategy 1: Look for About link
        about_keywords = ["about", "team", "our-team", "staff", "meet-the-team"]
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if any(kw in href for kw in about_keywords):
                about_url = urljoin(base_url, href)
                try:
                    resp = self.client.get(about_url)
                    if resp.status_code == 200:
                        about_soup = BeautifulSoup(resp.text, "html.parser")
                        # Look for names near owner/founder titles
                        for title in self.OWNER_TITLES:
                            content = about_soup.get_text()
                            pattern = f'([A-Z]\\w+\\s[A-Z]\\w+).*(?i){title}'
                            match = re.search(pattern, content)
                            if match:
                                return match.group(1)
                except:
                    continue
        
        # Strategy 2: Look in meta description or title
        meta = soup.find("meta", {"name": "description"})
        if meta and "owner" in meta.get("content", "").lower():
            content = meta["content"]
            # Try to extract "name - owner" pattern
            match = re.search(r'by\s+([A-Z]\w+\s[A-Z]\w+)', content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None


# Convenience function
def extract_website_intel(url: str) -> dict:
    """Extract website intelligence."""
    extractor = WebsiteExtractor()
    return extractor.extract(url)
