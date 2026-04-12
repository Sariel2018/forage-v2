---
id: html_meta_dates_unreliable
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "HTML meta dates may be unreliable"
---

# HTML meta dates may be unreliable

12. **HTML meta dates may be unreliable.** CMS migrations often overwrite `article:published_time`
    with the migration date. Priority: URL path date > HTML meta > CDX timestamp > fallback.

## Data Quality
