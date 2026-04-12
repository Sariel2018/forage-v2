---
id: deduplication
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Deduplication must be multi-level:"
---

# Deduplication must be multi-level:

15. **Deduplication must be multi-level:**
    - Level 1: URL/slug exact match
    - Level 2: Title + date match (catches different slugs for same article)
    - Level 3: Content similarity for truncated snapshots
    - Always keep the longest full_text version.
