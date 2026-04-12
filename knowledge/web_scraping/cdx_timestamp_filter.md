---
id: cdx_timestamp_filter
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "CDX `from_ts/to_ts` filters archive timestamp, NOT article publish date"
---

# CDX `from_ts/to_ts` filters archive timestamp, NOT article publish date

4. **CDX `from_ts/to_ts` filters archive timestamp, NOT article publish date.** Archive.org
   periodically re-crawls old URLs, so a 2014 snapshot might contain a 1930s article.
