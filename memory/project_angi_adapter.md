---
name: project-angi-adapter
description: Angi adapter implementation — what was built, patterns used, test runner
metadata:
  type: project
---

Angi adapter (`src/adapters/angi.py`) built and integrated into pipeline.

**Why:** TASK-B-ANGI-ADAPTER spec required a third data source (angi.com) matching the Yelp/BBB schema.

**How to apply:** Use `AngiAdapter(config['sources']['angi']).discover(markets)` — same interface as `YelpAdapter` and `BBBAdapter`.

Key design points:
- URL pattern: `https://www.angi.com/companylist/{city-slug}/{category-slug}.htm` (page 1), `/.../{category-slug}/{N}.htm` for pages 2+
- Category config key `hvac-heating-cooling` maps to URL slug `hvac-contractors` via `_CATEGORY_SLUG_MAP`
- `calculate_reliability_score(rating, reviews, years)` → 0-100: rating contributes 0-50, reviews 0-30 (step scale), years 0-20 (1.5/yr capped)
- Output includes Angi-specific fields: `angi_rating`, `angi_reliability_score`, `years_in_business`
- Tests: `python3 -m pytest src/adapters/test_angi.py -v` (98 tests, all pass)
- main.py already had BBBAdapter; Angi added as third adapter, dedup logic extended to use `angi_reliability_score`
