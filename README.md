# B2B HVAC Scraper
**Purpose:** Find independent HVAC businesses needing marketing, AI agents, and A2P messaging services.

## Features
- Multi-source scraping (Yelp, BBB, Angi)
- ICP scoring (0-100 scale)
- Chain filtering (excludes national brands)
- Cross-source deduplication
- Geographic filtering (Clark County, NV + expansion markets)
- CSV export for GHL manual import

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python src/main.py discover
```

## Commands
- `discover` - Run full discovery across all sources
- `refresh` - Re-verify Tier A/B leads
- `stats` - Show lead counts by tier
- `export` - Generate CSV for GHL import

## Landing Page
https://nex-trends.com/ai-growth-w-page
