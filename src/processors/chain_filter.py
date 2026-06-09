"""Chain Filter - Exclude national HVAC brands."""
import re
from typing import Dict, Any, List


def is_chain(company_name: str, chain_brands: List[str]) -> bool:
    """
    Detect if company is a national chain based on name matching.
    
    Uses case-insensitive substring matching with word boundaries.
    """
    if not company_name:
        return False
    
    company_lower = company_name.lower()
    
    for brand in chain_brands:
        brand_lower = brand.lower()
        
        # Exact match
        if company_lower == brand_lower:
            return True
        
        # Substring match with word boundaries
        pattern = r'\b' + re.escape(brand_lower) + r'\b'
        if re.search(pattern, company_lower):
            return True
    
    return False


def filter_chains(companies: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter out chain brands from company list and mark them.
    
    Returns: List of companies with is_chain flag set.
    """
    chain_brands = config.get('chain_brands', [])
    
    filtered = []
    chains_excluded = 0
    
    for company in companies:
        company_name = company.get('company_name', '')
        
        if is_chain(company_name, chain_brands):
            company['is_chain'] = True
            chains_excluded += 1
        else:
            company['is_chain'] = False
        
        filtered.append(company)
    
    print(f"⛓️  Chain filter: {chains_excluded} national brands flagged")
    return filtered
