"""Main CLI for B2B HVAC Scraper."""
import sys
import yaml
from pathlib import Path
from dotenv import load_dotenv

from database import Database
from adapters.yelp import YelpAdapter
from processors.chain_filter import filter_chains
from processors.icp_scorer import score_and_classify
from exporters.csv_exporter import CSVExporter

# Load environment variables
load_dotenv()

def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent.parent / 'config.yaml'
    with open(config_path) as f:
        return yaml.safe_load(f)

def cmd_discover():
    """Run full discovery across all enabled sources."""
    print("🚀 Starting B2B HVAC Discovery...")
    
    config = load_config()
    db = Database(config['database']['path'])
    
    markets = config['target_geos']
    print(f"📍 Target markets: {', '.join(markets)}")
    
    # Run adapters
    all_companies = []
    
    # Yelp
    yelp = YelpAdapter(config)
    all_companies.extend(yelp.discover(markets))
    
    # BBB and Angi adapters would go here
    # For now, we have working Yelp adapter
    
    print(f"\n📊 Total companies discovered: {len(all_companies)}")
    
    # Filter chains
    filtered = filter_chains(all_companies, config)
    
    # Score and classify
    print("🎯 Scoring companies...")
    scored = []
    for company in filtered:
        scored_company = score_and_classify(company, config)
        scored.append(scored_company)
        
        # Insert into database
        db.insert_company(scored_company)
    
    # Show stats
    stats = db.get_stats()
    print(f"\n✅ Discovery complete!")
    print(f"   Total: {stats['total']}")
    print(f"   Tier A: {stats['by_tier'].get('A', 0)}")
    print(f"   Tier B: {stats['by_tier'].get('B', 0)}")
    print(f"   Tier C: {stats['by_tier'].get('C', 0)}")
    print(f"   Rejected: {stats['by_tier'].get('Reject', 0)}")
    
    db.log_activity('discover', f"Found {stats['total']} companies")
    db.close()

def cmd_stats():
    """Show database statistics."""
    config = load_config()
    db = Database(config['database']['path'])
    
    stats = db.get_stats()
    
    print("\n📊 B2B HVAC Scraper Statistics")
    print("=" * 50)
    print(f"Total Companies: {stats['total']}")
    print(f"\nBy Tier:")
    for tier, count in sorted(stats['by_tier'].items()):
        print(f"  {tier}: {count}")
    print(f"\nBy Source:")
    for source, count in sorted(stats['by_source'].items()):
        print(f"  {source}: {count}")
    print("=" * 50)
    
    db.close()

def cmd_export():
    """Export leads to CSV."""
    config = load_config()
    db = Database(config['database']['path'])
    
    companies = db.get_all_companies()
    exporter = CSVExporter(config)
    output_path = exporter.export(companies)
    
    print(f"✅ Exported {len(companies)} companies to {output_path}")
    db.close()

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python src/main.py [command]")
        print("\nCommands:")
        print("  discover  - Run full discovery across all sources")
        print("  stats     - Show database statistics")
        print("  export    - Export leads to CSV")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'discover':
        cmd_discover()
    elif command == 'stats':
        cmd_stats()
    elif command == 'export':
        cmd_export()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == '__main__':
    main()
