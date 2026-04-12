---
id: cdx_snapshot_fallback
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "CDX snapshots may need fallback strategies:"
---

# CDX snapshots may need fallback strategies:

5. **CDX snapshots may need fallback strategies:**
   - Exact URL → wildcard URL (catches UTM variants that bypassed paywalls)
   - Latest snapshot via `/web/2/{url}` as last resort
   - Classify errors: `no_snapshot` (don't retry), `fetch_failed` (retry 2x), `rate_limited` (exponential backoff)

## Network & Rate Limiting
