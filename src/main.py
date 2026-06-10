"""Main CLI for B2B HVAC Scraper with Hermes scoring webhook integration."""
import sys
import yaml
import httpx
from pathlib import Path
from dotenv import load_dotenv

from database import Database
from adapters.yelp import YelpAdapter
from processors.chain_filter import filter_chains
from processors.icp_scorer import score_and_classify
from exporters.csv_exporter import CSVExporter

# Webhook URL for Hermes scoring engine
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
            "source": "yelp",
            "market": lead.get('address', {}).get('city', 'Unknown'),
        }
        resp = httpx.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️  Webhook failed (scoring engine offline?): {e}")
        return False

def discover_market():
    """Run full B2B HVAC discovery with webhook passthrough."""
    print("🔍 B2B HVAC Scraper - Discover Mode")
    
    config = load_config()
    db = Database(config)
    scrapers = []
    
    # Yelp scraper
    yelp_config = config.get('sources', {}).get('yelp', {})
    if yelp_config.get('enabled', False):
        try:
            scrapers.append(YelpAdapter(yelp_config))
        except Exception as e:
            print(f"⚠️  Yelp unavailable: {e}")
    
    hermes_count = 0
    
    for scraper in scrapers:
        print(f"\n📦 Running: {scraper.__class__.__name__}")
        for lead in scraper.scrape():
            if not filter_chains(lead, config):
                continue
            
            scored = score_and_classify(lead, config)
            if scored['tier'] in ['A', 'B']:
                db.save_and_classify(scored)
                sent = send_to_hermes(scored)
                if sent:
                    hermes_count += 1
                action = "→ Hermes" if sent else ""
                print(f"  🎯 {scored['tier']} | {scored['company_name']} {scored['icp_score']}/100 {action}")
    
    print(f"\n✅ Pipeline complete. Hermes signals: {hermes_count}")

def export_csv():
    """Export leads to CSV."""
    print("📤 Exporting leads to CSV...")
    config = load_config()
    db = Database(config)
    
    leads = db.get_all()
    csv_path = config.get('output', {}).get('csv_path', 'leads.csv')
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
