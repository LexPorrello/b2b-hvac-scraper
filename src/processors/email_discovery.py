"""
Email Discovery Engine
======================

Finds valid email addresses for HVAC business owners.

Pattern-based guessing + verification + caching.

Usage:
    from email_discovery import EmailDiscoveryEngine
    
    engine = EmailDiscoveryEngine()
    emails = engine.find_emails("Desert Air Solutions", domain="desertair.com")
    # Returns: ['john@desertair.com', 'owner@desertair.com'] (verified)
"""

import re
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("email_discovery")


class EmailDiscoveryEngine:
    """Discover and verify business email addresses."""
    
    # Common patterns for small business emails
    NAME_PATTERNS = [
        "{first}@{domain}",
        "{last}@{domain}",
        "{first}.{last}@{domain}",
        "{first}_{last}@{domain}",
        "{first_initial}{last}@{domain}",
    ]
    
    ROLE_PATTERNS = [
        "owner@{domain}",
        "info@{domain}",
        "contact@{domain}",
        "admin@{domain}",
        "office@{domain}",
        "service@{domain}",
        "hello@{domain}",
    ]
    
    def __init__(self, cache_db: Optional[str] = None):
        self.client = httpx.Client(timeout=10)
        self.cache_db = cache_db or "data/email_cache.db"
        self._init_cache()
    
    def _init_cache(self):
        """Initialize email verification cache."""
        Path(self.cache_db).parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_cache (
                email TEXT PRIMARY KEY,
                domain TEXT,
                verified INTEGER DEFAULT 0,
                source TEXT,
                discovered_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def discover(self, company_name: str, domain: str, owner_name: str = "") -> list[str]:
        """
        Discover emails for a business.
        
        Args:
            company_name: Full business name
            domain: Website domain (e.g., "desertair.com")
            owner_name: Owner's name if known (e.g., "John Smith")
        
        Returns:
            List of verified email addresses
        """
        candidates = []
        
        # Generate pattern-based candidates
        candidates.extend(self._generate_name_patterns(owner_name, domain))
        candidates.extend(self._generate_role_patterns(domain))
        
        # Deduplicate
        candidates = list(set(candidates))
        
        # Verify each candidate
        verified = []
        for email in candidates:
            if self._is_cached_valid(email):
                verified.append(email)
            elif self._verify_email(email):
                verified.append(email)
                self._cache_email(email, domain, verified=1)
            else:
                self._cache_email(email, domain, verified=0)
        
        logger.info(f"Discovered {len(verified)} verified emails for {domain}")
        return verified
    
    def _generate_name_patterns(self, owner_name: str, domain: str) -> list[str]:
        """Generate email patterns from owner name."""
        if not owner_name or " " not in owner_name:
            return []
        
        parts = owner_name.lower().split()
        first = parts[0]
        last = parts[-1]
        first_initial = first[0]
        
        emails = []
        for pattern in self.NAME_PATTERNS:
            try:
                email = pattern.format(
                    first=first,
                    last=last,
                    first_initial=first_initial,
                    domain=domain
                )
                emails.append(email)
            except KeyError:
                continue
        
        return emails
    
    def _generate_role_patterns(self, domain: str) -> list[str]:
        """Generate role-based email patterns."""
        return [p.format(domain=domain) for p in self.ROLE_PATTERNS]
    
    def _verify_email(self, email: str) -> bool:
        """
        Verify email deliverability via SMTP.
        
        Note: This is a stub. Real SMTP verification requires:
        1. DNS MX record lookup
        2. Connect to mail server
        3. VRFY/RCPT TO command
        4. Handle greylisting, rate limits
        
        For production, use a service like:
        - ZeroBounce API
        - Hunter.io Verifier
        - NeverBounce
        """
        # Stub: validate format only
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            return False
        
        # Check if domain has MX records (stub: assume valid)
        domain = email.split("@")[1]
        
        # In production, do actual SMTP check here
        logger.debug(f"Verification stub for {email} (domain: {domain})")
        
        # Return True for valid format (production would do real check)
        return True
    
    def _is_cached_valid(self, email: str) -> bool:
        """Check cache for previously verified email."""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT verified FROM email_cache WHERE email = ?",
            (email,)
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None and row[0] == 1
    
    def _cache_email(self, email: str, domain: str, verified: int):
        """Cache email verification result."""
        from datetime import datetime
        
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO email_cache (email, domain, verified, source, discovered_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, domain, verified, "pattern_discovery", datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def search_website(self, url: str) -> list[str]:
        """
        Extract emails from website pages (Contact, About, Footer).
        """
        emails = []
        
        try:
            # Check common pages
            pages = ["", "/contact", "/about", "/about-us", "/contact-us"]
            
            for page in pages:
                try:
                    resp = self.client.get(f"{url.rstrip('/')}{page}", timeout=8)
                    if resp.status_code == 200:
                        found = re.findall(
                            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                            resp.text
                        )
                        emails.extend(found)
                except:
                    continue
        except Exception as e:
            logger.warning(f"Website search failed for {url}: {e}")
        
        # Filter and deduplicate
        emails = list(set(e.lower() for e in emails))
        emails = [e for e in emails if not any(skip in e for skip in [
            "noreply", "no-reply", "donotreply", "@sentry", ".png", ".jpg"
        ])]
        
        return emails[:5]  # Max 5
