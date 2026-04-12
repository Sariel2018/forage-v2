---
id: concurrent_workers
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Each concurrent worker needs its own HTTP client"
---

# Each concurrent worker needs its own HTTP client

17. **Each concurrent worker needs its own HTTP client** (independent connection pool). One
    worker's pool crash should not affect others.
