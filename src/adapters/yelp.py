"""Yelp adapter - scrape HVAC businesses from Yelp."""
import os
import httpx
from typing import List, Dict, Any
import time


class YelpAdapter:
    """Scrape HVAC businesses from Yelp Fusion API or web scraping."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = os.getenv(config.get('sources', {}).get('yelp', {}).get('api_key_env', 'YELP_API_KEY'))
        self.enabled = config.get('sources', {}).get('yelp', {}).get('enabled', False)
        self.results_per_market = config.get('sources', {}).get('yelp', {}).get('results_per_market', 300)
    
    def discover(self, markets: List[str]) -> List[Dict[str, Any]]:
        """
        Discover HVAC businesses in target markets.
        
        Args:
            markets: List of "City, State" strings
        
        Returns:
            List of company dicts with standardized schema
        """
        if not self.enabled:
            print("⏭️  Yelp adapter disabled")
            return []
        
        if not self.api_key:
            print("⚠️  YELP_API_KEY not found - using stub data")
            return self._stub_data(markets)
        
        all_companies = []
        
        for market in markets:
            print(f"🔍 Searching Yelp in {market}...")
            companies = self._search_market(market)
            all_companies.extend(companies)
            time.sleep(1)  # Rate limiting
        
        print(f"✅ Yelp: Found {len(all_companies)} businesses")
        return all_companies
    
    def _search_market(self, location: str) -> List[Dict[str, Any]]:
        """Search Yelp API for HVAC businesses in a specific market."""
        url = "https://api.yelp.com/v3/businesses/search"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        params = {
            "term": "HVAC",
            "location": location,
            "categories": "hvac",
            "limit": min(50, self.results_per_market),  # Yelp max is 50 per request
            "sort_by": "rating"
        }
        
        try:
            response = httpx.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            businesses = data.get('businesses', [])
            return [self._normalize(biz, location) for biz in businesses]
        
        except Exception as e:
            print(f"❌ Yelp API error for {location}: {e}")
            return []
    
    def _normalize(self, biz: Dict[str, Any], location: str) -> Dict[str, Any]:
        """Normalize Yelp business data to standard schema."""
        return {
            'company_name': biz.get('name'),
            'phone': biz.get('phone'),
            'email': None,  # Yelp doesn't provide emails
            'website': biz.get('url'),
            'address': ', '.join(biz.get('location', {}).get('display_address', [])),
            'city': biz.get('location', {}).get('city'),
            'state': biz.get('location', {}).get('state'),
            'zip_code': biz.get('location', {}).get('zip_code'),
            'review_count': biz.get('review_count', 0),
            'rating': biz.get('rating'),
            'business_hours': None,  # Would need separate API call
            'service_area': location,
            'data_source': 'yelp',
            'source_id': biz.get('id'),
            'source_url': biz.get('url')
        }
    
    def _stub_data(self, markets: List[str]) -> List[Dict[str, Any]]:
        """Return stub data when API key is not available."""
        print("📌 Using Yelp stub data (3 sample businesses)")
        
        stubs = []
        for i, market in enumerate(markets[:1]):  # Just first market for stub
            stubs.extend([
                {
                    'company_name': f'Desert Air Solutions {i+1}',
                    'phone': f'(702) 555-0{i+1}01',
                    'email': None,
                    'website': f'https://desertair{i+1}.example.com',
                    'address': f'{100+i*10} Main St',
                    'city': market.split(',')[0].strip(),
                    'state': market.split(',')[1].strip() if ',' in market else 'NV',
                    'zip_code': '89101',
                    'review_count': 50 + i*10,
                    'rating': 4.5,
                    'business_hours': 'Mon-Fri 7am-7pm',
                    'service_area': market,
                    'data_source': 'yelp',
                    'source_id': f'stub-yelp-{i+1}',
                    'source_url': f'https://yelp.com/biz/stub-{i+1}'
                }
            ])
        
        return stubs
