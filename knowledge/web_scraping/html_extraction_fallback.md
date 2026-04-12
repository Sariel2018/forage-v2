---
id: html_extraction_fallback
scope: web_scraping
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "HTML extraction needs fallback"
---

# HTML extraction needs fallback

13. **HTML extraction needs fallback.** `<p>` tag extraction works for modern pages but fails on
    old/non-standard HTML. Use a wide extractor (all visible text blocks >30 chars) as fallback
    when primary extraction yields ≤200 characters but HTML is >5KB.
