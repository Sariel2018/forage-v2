---
id: archive_rate_limit
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Archive.org rate limits at ~15 req/min/IP"
---

# Archive.org rate limits at ~15 req/min/IP

6. **Archive.org rate limits at ~15 req/min/IP.** 3 concurrent workers with 1-2s sleep each is
   safe. More workers trigger more 429s, reducing net throughput.
