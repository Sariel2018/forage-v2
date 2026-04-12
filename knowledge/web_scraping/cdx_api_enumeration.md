---
id: cdx_api_enumeration
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Use CDX API for URL enumeration"
---

# Use CDX API for URL enumeration

2. **Use CDX API for URL enumeration.** Don't rely on a site's own navigation/search to discover
   article URLs. CDX wildcard queries can find all archived URLs for a domain.
   - Endpoint: `https://web.archive.org/cdx/search/cdx`
   - Key params: `url`, `output=json`, `fl=original`, `filter=statuscode:200`, `collapse=urlkey`
