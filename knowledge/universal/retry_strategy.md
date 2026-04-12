---
id: retry_strategy
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Distinguish error types for retry strategy:"
---

# Distinguish error types for retry strategy:

8. **Distinguish error types for retry strategy:**
   - Connection error / timeout → retry 2x max
   - 429 rate limit → exponential backoff (30/60/90/120/150s)
   - No snapshot exists → don't retry, log and move on
