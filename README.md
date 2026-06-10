# B2B HVAC Scraper

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-305%20passing-green.svg)]()
[![GitHub](https://img.shields.io/badge/GitHub-LexPorrello%2Fb2b--hvac--scraper-lightgrey.svg)](https://github.com/LexPorrello/b2b-hvac-scraper)

Nex-Trends B2B HVAC Scraper — Automatically discovers, scores, and enriches HVAC business leads from Yelp, BBB, and Angi within your geographic corridor (Summerlin to Henderson).

## 📋 What This Does

Finds independent HVAC businesses (non-chain) who are most likely to buy marketing/AI services:
- **Scans** Yelp, Better Business Bureau, and Angi for HVAC businesses in your market
- **Filters chains/franchises** — only passes independent operators (mom-and-pop shops)
- **ICP Scoring** — rates every business 0-100 on digital maturity, demand stability, and receptiveness
- **Enriches** — discovers owner names, emails, website intelligence
- **Deduplicates** — merges data from multiple sources into single rich profiles
- **Routes** — Tier A leads (80+ ICP) auto-route to Hermes scoring engine via webhook

## 🏗️ Architecture

```
src/
├── adapters/          # Data source scanners
│   ├── yelp.py        # Yelp Fusion API scanner (reviews, rating, phone)
│   ├── bbb.py         # BBB.org scraper (accreditation, complaint history, trust score)
│   ├── angi.py        # Angi.com scraper (rating, review count, service area)
│   └── website_intel.py  # Website analysis (owner names, emails, chat/booking detection)
├── processors/        # Data processing
│   ├── icp_scorer.py      # ICP score calculation (0-100)
│   ├── chain_filter.py    # Chain/franchise detection and exclusion
│   ├── deduplicator.py    # Cross-source deduplication with fuzzy matching
│   └── email_discovery.py # Email pattern generation and verification
├── exporters/          # Output generation
│   └── csv_exporter.py   # CSV output for GHL import
└── database.py        # SQLite lead storage + dedup cache
```

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env to add your API keys

# Discover leads
python src/main.py discover

# Output: data/b2b_leads_<timestamp>.csv
```

## ⚙️ Configuration

**config.yaml** controls markets, adapter settings, and tier thresholds:

```yaml
markets:
  - "Las Vegas, NV"
  - "Henderson, NV"
  - "North Las Vegas, NV"

adapters:
  yelp:
    enabled: true
    search_radius_miles: 25
  bbb:
    enabled: true
    max_pages: 10
  angi:
    enabled: true
    timeout: 30

icp_scoring:
  tier_a_min: 80   # Auto-routes to scoring engine
  tier_b_min: 60
```

## 🔑 Required API Keys

| Service | Key | How to Get |
|---------|-----|------------|
| Yelp Fusion | `YELP_API_KEY` | [Yelp Fusion](https://www.yelp.com/developers/v3/manage_app) |
| BBB | None (scraping) | Rate-limited to 1 req/sec |
| Angi | None (scraping) | Rate-limited to 1 req/sec |

## 🧪 Testing

```bash
# Run all tests
python -m pytest src/ -v

# Test specific adapter
python -m pytest src/adapters/test_bbb.py -v
```

**305 tests passing** across all adapters and processors.

## 📊 Lead Pipeline

```
Yelp → ICP Score: 88 → Tier A → CALL TODAY → Webhook → GHL
BBB  → ICP Score: 75 → Tier B -> NURTURE → Email Campaign
Angi → Chain Detected → FILTERED → Discard
```

## 🔗 Downstream Integration

Tier A/B leads automatically POST to Hermes scoring engine:
```
POST http://127.0.0.1:5000/webhook/b2b-hvac-router
```

See [`LexPorrello/hermes-scoring-engines`](https://github.com/LexPorrello/hermes-scoring-engines) for scoring engine details.

## 📈 Stats

- **~5,791 LOC** across adapters, processors, tests
- **3 data sources** (Yelp, BBB, Angi)
- **4 processors** (scoring, filtering, dedup, email discovery)
- **305 tests** all passing
- **Stub mode** — works without API keys for testing

## 🛡️ License

Nex-Trends Partnership — Lex retains code ownership.

---

Built for [Nex-Trends](https://github.com/LexPorrello) | Air & Water Systems Company
