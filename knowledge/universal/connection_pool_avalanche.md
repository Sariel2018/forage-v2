---
id: connection_pool_avalanche
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "httpx connection pool avalanche"
---

# httpx connection pool avalanche

7. **httpx connection pool avalanche.** After 5+ hours of continuous requests, the server may
   silently drop TCP connections. Stale connections in the pool cause cascading failures.
   - Fix: track consecutive failures; after 10, close the client and create a new one
