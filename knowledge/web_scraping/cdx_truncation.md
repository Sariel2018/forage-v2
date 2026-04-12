---
id: cdx_truncation
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "NEVER use a single large CDX query"
---

# NEVER use a single large CDX query

3. **NEVER use a single large CDX query.** CDX silently truncates results when they exceed internal
   limits (~5K-10K). Results are sorted alphabetically, so truncation drops the tail end.
   - Solution: split into many small queries by prefix (e.g., per region, per content type)
   - Cache the index locally after building it — CDX queries are slow and flaky
