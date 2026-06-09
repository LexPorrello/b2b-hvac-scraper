"""ICP Scoring Engine - 0-100 scale with tier classification."""
from typing import Dict, Any


def calculate_icp_score(company: Dict[str, Any], config: Dict[str, Any]) -> int:
    """
    Calculate ICP score based on contact data and business signals.
    
    Scoring breakdown:
    - Phone: +20 points
    - Email: +30 points
    - Website: +10 points
    - Reviews (50+): +15 points
    - Reviews (10-49): +5 points
    - Business Hours: +10 points
    - Service Area: +10 points
    - Chain Penalty: -15 points
    
    Returns: 0-100 integer score
    """
    weights = config.get('scoring', {}).get('weights', {})
    score = 0
    
    # Contact Data (60 points max)
    if company.get('phone'):
        score += weights.get('phone', 20)
    
    if company.get('email'):
        score += weights.get('email', 30)
    
    if company.get('website'):
        score += weights.get('website', 10)
    
    # Business Signals (30 points max)
    review_count = company.get('review_count', 0)
    if review_count >= 50:
        score += weights.get('reviews_high', 15)
    elif review_count >= 10:
        score += weights.get('reviews_med', 5)
    
    if company.get('business_hours'):
        score += weights.get('hours', 10)
    
    if company.get('service_area'):
        score += weights.get('service_area', 10)
    
    # Chain Penalty
    if company.get('is_chain'):
        score += weights.get('chain_penalty', -15)  # Negative weight
    
    # Cap at 0-100
    return max(0, min(score, 100))


def classify_tier(score: int, config: Dict[str, Any]) -> str:
    """
    Classify lead tier based on ICP score.
    
    - Tier A (≥60): Immediate outreach - complete contact info
    - Tier B (≥40): Manual research needed, then outreach
    - Tier C (≥20): Nurture queue
    - Reject (<20): Not qualified
    """
    tiers = config.get('scoring', {}).get('tiers', {})
    
    if score >= tiers.get('A', 60):
        return 'A'
    elif score >= tiers.get('B', 40):
        return 'B'
    elif score >= tiers.get('C', 20):
        return 'C'
    else:
        return 'Reject'


def score_and_classify(company: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Score company and classify tier. Returns enriched company dict."""
    score = calculate_icp_score(company, config)
    tier = classify_tier(score, config)
    
    company['icp_score'] = score
    company['tier'] = tier
    
    return company
