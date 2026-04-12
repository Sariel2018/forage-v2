---
id: ssl_diagnose
scope: universal
type: advisory
verified: true
source_tasks: [fa_2018_2020, whitehouse_trump2]
summary: "Diagnose SSL/connection errors before adding workarounds"
---

# Diagnose SSL/connection errors before adding workarounds

25. **Diagnose SSL/connection errors before adding workarounds.** If you see
    `SSL: UNEXPECTED_EOF_WHILE_READING` or similar errors, first check your network
    environment: is there a proxy? Is the site blocking your IP? Is the URL correct?
    Try a simple direct request before adding complex SSL workarounds.
