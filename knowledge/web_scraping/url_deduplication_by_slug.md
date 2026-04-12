---
id: url_deduplication_by_slug
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Same article may have multiple URLs"
---

# Same article may have multiple URLs

11. **Same article may have multiple URLs** (old format, new format, with/without port :80,
    UTM variants). The slug (last URL segment) is usually stable across formats — use it for
    cross-format deduplication.
