---
name: bbb-adapter-implementation
description: BBB adapter built for b2b-hvac-scraper; notes on project patterns and pipeline architecture
metadata:
  type: project
---

BBB adapter implemented in src/adapters/bbb.py (~971 LOC) with full test suite in src/adapters/test_bbb.py (85 tests, all passing).

**Key patterns in this codebase:**
- Adapters live in src/adapters/, implement `discover(markets: List[str]) -> List[Dict]`
- Standard schema fields: company_name, phone, email, website, address, city, state, zip_code, review_count, rating, business_hours, service_area, data_source, source_id, source_url
- Main pipeline: discover → filter_chains (list) → score_and_classify → db.insert_company → send_to_hermes
- Database uses db.insert_company() (not save_and_classify), db.get_all_companies() (not get_all)
- config.yaml sources.bbb.enabled=true — BBB is already configured

**Why:** Spec in shared-ops-memory/mission-control/active/TASK-A-BBB-ADAPTER.md

**How to apply:** When adding more adapters (Angi, Google Places), follow the same discover(markets) → _normalize() → _stub_data() pattern. Test with `python3 -m unittest src/adapters/test_bbb.py -v` from repo root.
