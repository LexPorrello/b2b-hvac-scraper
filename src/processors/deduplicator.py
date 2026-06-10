"""
Cross-Source Deduplication Engine
==================================

Prevents duplicate leads when the same business appears in:
- Yelp, BBB, Angi (multiple sources)
- Reddit, Nextdoor, Facebook (same homeowner on multiple platforms)

Uses fuzzy matching on name + location, then phone/email confirmation.
"""

import re
import sqlite3
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

logger = logging.getLogger("deduplicator")


class DedupEngine:
    """Deduplicate leads across multiple data sources."""
    
    # National HVAC chains to always exclude
    CHAINS = [
        "carrier", "lennox", "trane", "goodman", "rheem", "ruud",
        "amana", "bryant", "coleman", "ducane", "frigidaire",
        "gibson", "intertherm", "payne", "tempstar", "whirlpool",
        "york", "american standard", "daikin", "mitsubishi",
        "westinghouse", "maytag", "kenmore", "comfortmaker", "heil",
        "day & night", "arcoaire", "keeprite", "luxaire",
        "national chain", "franchise", "dealer network",
    ]
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "data/dedup_cache.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize deduplication database."""
        Path(self.db_path).parent.mkdir(exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                website TEXT,
                first_seen TEXT,
                last_seen TEXT,
                sources TEXT,
                merged_data TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_name ON seen_businesses(normalized_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_phone ON seen_businesses(phone)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_email ON seen_businesses(email)
        """)
        
        conn.commit()
        conn.close()
    
    def normalize_name(self, name: str) -> str:
        """Normalize business name for comparison."""
        # Lowercase
        normalized = name.lower()
        
        # Remove common suffixes
        suffixes = [
            " llc", " inc", " corp", " corporation", " company", " co",
            " & son", " & sons", " heating and air", " heating & air",
            " hvac", " air conditioning", " ac", " heating",
        ]
        for suffix in suffixes:
            normalized = normalized.replace(suffix, "")
        
        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    def is_chain(self, name: str) -> bool:
        """Check if business is a national chain/franchise."""
        normalized = name.lower()
        return any(chain in normalized for chain in self.CHAINS)
    
    def name_similarity(self, name1: str, name2: str) -> float:
        """Calculate name similarity (0.0 to 1.0)."""
        n1 = self.normalize_name(name1)
        n2 = self.normalize_name(name2)
        return SequenceMatcher(None, n1, n2).ratio()
    
    def find_duplicate(self, business: dict) -> Optional[dict]:
        """
        Check if this business already exists in our database.
        Returns existing record if found, None otherwise.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        normalized = self.normalize_name(business.get("company_name", ""))
        phone = business.get("phone", "")
        email = business.get("email", "")
        website = business.get("website", "")
        
        # Strategy 1: Exact phone match
        if phone:
            cursor.execute(
                "SELECT * FROM seen_businesses WHERE phone = ?",
                (phone,)
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return self._row_to_dict(row)
        
        # Strategy 2: Exact email match
        if email:
            cursor.execute(
                "SELECT * FROM seen_businesses WHERE email = ?",
                (email,)
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return self._row_to_dict(row)
        
        # Strategy 3: Fuzzy name match on recent entries
        cursor.execute(
            "SELECT * FROM seen_businesses WHERE normalized_name LIKE ?",
            (f"%{normalized[:8]}%",)
        )
        rows = cursor.fetchall()
        
        for row in rows:
            existing = self._row_to_dict(row)
            similarity = self.name_similarity(
                business.get("company_name", ""),
                existing.get("normalized_name", "")
            )
            if similarity >= 0.80:
                conn.close()
                return existing
        
        conn.close()
        return None
    
    def add_or_merge(self, business: dict, source: str) -> dict:
        """
        Add new business or merge with existing duplicate.
        Returns the final business record (merged or new).
        """
        # Check for chains
        if self.is_chain(business.get("company_name", "")):
            logger.info(f"Filtered chain: {business.get('company_name')}")
            return {"rejected": True, "reason": "chain/franchise"}
        
        # Check for duplicates
        existing = self.find_duplicate(business)
        
        if existing:
            # Merge data
            merged = self._merge_businesses(existing, business, source)
            self._update_record(existing["id"], merged)
            logger.info(f"Merged duplicate: {business.get('company_name')}")
            return {**merged, "merged": True, "original_id": existing["id"]}
        
        # New record
        self._insert_record(business, source)
        logger.info(f"New business added: {business.get('company_name')}")
        return {**business, "new": True}
    
    def _merge_businesses(self, existing: dict, new: dict, source: str) -> dict:
        """Merge data from multiple sources, preferring the richer record."""
        merged = dict(existing)
        
        # Merge sources list
        sources = set(existing.get("sources", "").split(", "))
        sources.add(source)
        merged["sources"] = ", ".join(sorted(filter(None, sources)))
        
        # Prefer non-empty values from new record
        for field in ["phone", "email", "website", "reviews", "rating"]:
            if not merged.get(field) and new.get(field):
                merged[field] = new[field]
        
        # Keep higher review count
        if new.get("reviews", 0) > merged.get("reviews", 0):
            merged["reviews"] = new["reviews"]
        
        # Update last seen
        from datetime import datetime
        merged["last_seen"] = datetime.now().isoformat()
        
        return merged
    
    def _insert_record(self, business: dict, source: str):
        """Insert new business record."""
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO seen_businesses 
            (normalized_name, phone, email, website, first_seen, last_seen, sources, merged_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.normalize_name(business.get("company_name", "")),
            business.get("phone", ""),
            business.get("email", ""),
            business.get("website", ""),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            source,
            str(business)
        ))
        
        conn.commit()
        conn.close()
    
    def _update_record(self, record_id: int, merged: dict):
        """Update existing record with merged data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE seen_businesses
            SET sources = ?, merged_data = ?, last_seen = ?
            WHERE id = ?
        """, (
            merged.get("sources", ""),
            str(merged),
            merged.get("last_seen", ""),
            record_id
        ))
        
        conn.commit()
        conn.close()
    
    def _row_to_dict(self, row) -> dict:
        """Convert sqlite row to dict."""
        columns = ["id", "normalized_name", "phone", "email", "website", 
                   "first_seen", "last_seen", "sources", "merged_data"]
        return {col: row[i] for i, col in enumerate(columns)}
    
    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM seen_businesses")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT sources) FROM seen_businesses")
        source_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_unique_businesses": total,
            "data_sources_used": source_count,
            "chains_filtered": "automatic",
        }
