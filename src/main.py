"""Main CLI for B2B HVAC Scraper with Hermes scoring webhook integration."""
import sys
import yaml
import httpx
from pathlib import Path
from dotenv import load_dotenv

from database import Database
from adapters.yelp import YelpAdapter
from adapters.bbb import BBBAdapter
from processors.chain_filter import filter_chains
from processors.icp_scorer import score_and_classify
from exporters.csv_exporter import CSVExporter

WEBHOOK_URL = "http://127.0.0.1:5000/webhook/b2b-hvac-router"

load_dotenv()


def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)


def send_to_hermes(lead: dict):
    """Push qualified lead to Hermes scoring engine webhook."""
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "company_name": lead['company_name'],
            "phone": lead.get('phone'),
            "email": lead.get('email'),
            "website": lead.get('website'),
            "address": lead.get('address'),
            "icp_score": lead['icp_score'],
            "tier": lead['tier'],
            "reviews": lead.get('review_count'),
            "source": lead.get('data_source', 'unknown'),
            "market": lead.get('city') or lead.get('service_area', 'Unknown'),
        }
        resp = httpx.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️  Webhook failed (scoring engine offline?): {e}")
        return False


def _dedup_cross_source(leads: list) -> list:
    """Remove duplicate businesses that appear across multiple sources.

    Dedup key: normalized phone digits (10-digit US number).
    When two records share a phone number the one with the higher
    bbb_trust_score (or review_count as tie-breaker) is kept.
    Records with no phone are always kept as-is.
    """
    seen_phones: dict = {}
    result: list = []

    for lead in leads:
        phone = lead.get('phone') or ''
        digits = ''.join(c for c in phone if c.isdigit())

        if not digits:
            result.append(lead)
            continue

        if digits not in seen_phones:
            seen_phones[digits] = len(result)
            result.append(lead)
        else:
            existing_idx = seen_phones[digits]
            existing = result[existing_idx]
            existing_score = existing.get('bbb_trust_score') or existing.get('review_count', 0)
            this_score = lead.get('bbb_trust_score') or lead.get('review_count', 0)
            if this_score > existing_score:
                result[existing_idx] = lead

    return result


def discover_market():
    """Run full B2B HVAC discovery pipeline with webhook passthrough."""
    print("🔍 B2B HVAC Scraper - Discover Mode")

    config = load_config()
    db_path = config.get('database', {}).get('path', './data/b2b_leads.db')
    db = Database(db_path)
    markets = config.get('target_geos', ['Las Vegas, NV'])

    adapters = []

    # Yelp (primary source)
    yelp_config = config.get('sources', {}).get('yelp', {})
    if yelp_config.get('enabled', False):
        try:
            adapters.append(YelpAdapter(yelp_config))
        except Exception as e:
            print(f"⚠️  Yelp unavailable: {e}")

    # BBB (secondary source — runs after Yelp)
    bbb_config = config.get('sources', {}).get('bbb', {})
    if bbb_config.get('enabled', False):
        try:
            adapters.append(BBBAdapter(bbb_config))
        except Exception as e:
            print(f"⚠️  BBB unavailable: {e}")

    # Collect raw leads from all active adapters
    raw_leads = []
    if adapters:
        for adapter in adapters:
            leads = adapter.discover(markets)
            raw_leads.extend(leads)
            print(f"  📥 {adapter.__class__.__name__}: {len(leads)} leads collected")
    else:
        print("📌 No adapters active, using stub data for testing")
        raw_leads = get_stub_leads()

    print(f"\n📊 Raw leads before dedup: {len(raw_leads)}")

    # Cross-source deduplication by phone number
    deduped = _dedup_cross_source(raw_leads)
    dropped = len(raw_leads) - len(deduped)
    if dropped:
        print(f"🔀 Dedup: removed {dropped} cross-source duplicates")

    # Chain flagging + ICP scoring
    flagged = filter_chains(deduped, config)

    hermes_count = 0
    tier_counts: dict = {'A': 0, 'B': 0, 'C': 0, 'Reject': 0}

    for lead in flagged:
        scored = score_and_classify(lead, config)
        tier = scored['tier']
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        db.insert_company(scored)

        if tier in ('A', 'B'):
            sent = send_to_hermes(scored)
            if sent:
                hermes_count += 1
            action = "→ Hermes" if sent else ""
            src = scored.get('data_source', '?')
            print(
                f"  🎯 {tier} | {scored['company_name']} "
                f"{scored['icp_score']}/100 [{src}] {action}"
            )

    print(
        "\n📈 Tier breakdown: "
        + " | ".join(
            f"{t}:{tier_counts.get(t, 0)}" for t in ['A', 'B', 'C', 'Reject']
        )
    )
    print(f"✅ Pipeline complete. Hermes signals: {hermes_count}")


def get_stub_leads():
    """Stub data for testing webhook integration."""
    return [
        {
            'company_name': 'Desert Air Solutions',
            'phone': '(702) 555-0123',
            'email': 'info@desertair.com',
            'website': 'https://desertair.com',
            'address': '123 Main St, Las Vegas, NV 89101',
            'city': 'Las Vegas',
            'state': 'NV',
            'zip_code': '89101',
            'review_count': 78,
            'rating': 4.5,
            'business_hours': 'Mon-Fri 7am-7pm',
            'service_area': 'Las Vegas, NV',
            'data_source': 'stub',
            'source_id': 'stub-001',
            'source_url': None,
        },
        {
            'company_name': 'Cool Breeze HVAC',
            'phone': '(702) 555-0456',
            'email': None,
            'website': None,
            'address': '456 Desert Rd, Las Vegas, NV 89102',
            'city': 'Las Vegas',
            'state': 'NV',
            'zip_code': '89102',
            'review_count': 12,
            'rating': 4.0,
            'business_hours': None,
            'service_area': 'Las Vegas, NV',
            'data_source': 'stub',
            'source_id': 'stub-002',
            'source_url': None,
        },
        {
            'company_name': 'One Hour Heating & Air Conditioning',
            'phone': '(702) 555-0999',
            'email': 'corporate@onehour.com',
            'website': 'https://onehour.com',
            'address': '789 Chain Ave, Las Vegas, NV 89103',
            'city': 'Las Vegas',
            'state': 'NV',
            'zip_code': '89103',
            'review_count': 5000,
            'rating': 4.2,
            'business_hours': '24/7',
            'service_area': 'Las Vegas, NV',
            'data_source': 'stub',
            'source_id': 'stub-003',
            'source_url': None,
        },
    ]


def export_csv():
    """Export leads to CSV."""
    print("📤 Exporting leads to CSV...")
    config = load_config()
    db_path = config.get('database', {}).get('path', './data/b2b_leads.db')
    db = Database(db_path)
    leads = db.get_all_companies()
    csv_path = config.get('export', {}).get('csv_path', './data/leads.csv')
    CSVExporter.export(leads, csv_path)
    print(f"✅ Exported {len(leads)} leads to {csv_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python src/main.py [discover|stats|export]")
        sys.exit(1)

    cmd = sys.argv[1]
    commands = {'discover': discover_market, 'export': export_csv}

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")


if __name__ == '__main__':
    main()
