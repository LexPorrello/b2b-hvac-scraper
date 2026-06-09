"""CSV Exporter - Generate GHL-ready CSV files."""
import csv
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime


class CSVExporter:
    """Export leads to CSV for manual GHL import."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_path = config.get('export', {}).get('csv_path', './data/leads.csv')
        self.fields = config.get('export', {}).get('fields', [
            'company_name', 'phone', 'email', 'website', 'city', 'state',
            'icp_score', 'tier', 'source', 'detected_at'
        ])
    
    def export(self, companies: List[Dict[str, Any]]) -> str:
        """
        Export companies to CSV file.
        
        Returns: Path to generated CSV file
        """
        output_path = Path(self.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Sort by tier (A first) and score (highest first)
        tier_order = {'A': 0, 'B': 1, 'C': 2, 'Reject': 3}
        sorted_companies = sorted(
            companies,
            key=lambda x: (tier_order.get(x.get('tier', 'Reject'), 99), -x.get('icp_score', 0))
        )
        
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.fields, extrasaction='ignore')
            writer.writeheader()
            
            for company in sorted_companies:
                writer.writerow({k: company.get(k, '') for k in self.fields})
        
        return str(output_path)
    
    def export_tier(self, companies: List[Dict[str, Any]], tier: str) -> str:
        """Export only specific tier to CSV."""
        filtered = [c for c in companies if c.get('tier') == tier]
        
        output_path = Path(self.output_path).parent / f'leads_tier_{tier}.csv'
        
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.fields, extrasaction='ignore')
            writer.writeheader()
            
            for company in filtered:
                writer.writerow({k: company.get(k, '') for k in self.fields})
        
        return str(output_path)
