"""Database layer for B2B HVAC Scraper - SQLite storage with deduplication."""
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self.initialize()
    
    def initialize(self):
        """Create tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Main companies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                website TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                zip_code TEXT,
                review_count INTEGER DEFAULT 0,
                rating REAL,
                business_hours TEXT,
                service_area TEXT,
                is_chain BOOLEAN DEFAULT 0,
                icp_score INTEGER DEFAULT 0,
                tier TEXT,
                data_source TEXT NOT NULL,
                source_id TEXT,
                source_url TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified TIMESTAMP,
                notes TEXT,
                UNIQUE(data_source, source_id)
            )
        """)
        
        # Cross-source matches for deduplication
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cross_source_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id_1 INTEGER NOT NULL,
                company_id_2 INTEGER NOT NULL,
                match_type TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id_1) REFERENCES companies(id),
                FOREIGN KEY (company_id_2) REFERENCES companies(id),
                UNIQUE(company_id_1, company_id_2)
            )
        """)
        
        # Activity log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def insert_company(self, company: Dict[str, Any]) -> Optional[int]:
        """Insert or update company record."""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO companies (
                    company_name, phone, email, website, address, city, state, zip_code,
                    review_count, rating, business_hours, service_area, is_chain,
                    icp_score, tier, data_source, source_id, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(data_source, source_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    phone = excluded.phone,
                    email = excluded.email,
                    website = excluded.website,
                    review_count = excluded.review_count,
                    rating = excluded.rating,
                    icp_score = excluded.icp_score,
                    tier = excluded.tier,
                    last_verified = CURRENT_TIMESTAMP
            """, (
                company.get('company_name'),
                company.get('phone'),
                company.get('email'),
                company.get('website'),
                company.get('address'),
                company.get('city'),
                company.get('state'),
                company.get('zip_code'),
                company.get('review_count', 0),
                company.get('rating'),
                company.get('business_hours'),
                company.get('service_area'),
                company.get('is_chain', False),
                company.get('icp_score', 0),
                company.get('tier'),
                company.get('data_source'),
                company.get('source_id'),
                company.get('source_url')
            ))
            
            self.conn.commit()
            return cursor.lastrowid
        
        except sqlite3.IntegrityError as e:
            print(f"⚠️  Duplicate company: {company.get('company_name')} from {company.get('data_source')}")
            return None
    
    def get_companies_by_tier(self, tier: str) -> List[Dict]:
        """Get all companies for a specific tier."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM companies 
            WHERE tier = ? 
            ORDER BY icp_score DESC, detected_at DESC
        """, (tier,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_companies(self) -> List[Dict]:
        """Get all companies."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM companies ORDER BY icp_score DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        # Count by tier
        cursor.execute("""
            SELECT tier, COUNT(*) as count 
            FROM companies 
            GROUP BY tier
        """)
        tier_counts = {row['tier']: row['count'] for row in cursor.fetchall()}
        
        # Count by source
        cursor.execute("""
            SELECT data_source, COUNT(*) as count 
            FROM companies 
            GROUP BY data_source
        """)
        source_counts = {row['data_source']: row['count'] for row in cursor.fetchall()}
        
        # Total count
        cursor.execute("SELECT COUNT(*) as total FROM companies")
        total = cursor.fetchone()['total']
        
        return {
            'total': total,
            'by_tier': tier_counts,
            'by_source': source_counts
        }
    
    def log_activity(self, action: str, details: str = ""):
        """Log an activity."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO activity_log (action, details) VALUES (?, ?)
        """, (action, details))
        self.conn.commit()
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
