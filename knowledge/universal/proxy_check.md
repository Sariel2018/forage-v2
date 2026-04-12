---
id: proxy_check
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Check for proxy environment variables"
---

# Check for proxy environment variables

26. **Check for proxy environment variables.** If `HTTPS_PROXY`, `ALL_PROXY`, or
    `http_proxy` are set in the environment, they may interfere with requests to
    sites that don't need a proxy. Check `env | grep -i proxy` and unset if needed.
