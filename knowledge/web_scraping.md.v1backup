# Web Scraping Experience Knowledge Base

Distilled from real-world data collection projects. These are lessons learned, not code —
agents should use these to inform their own implementations.

## Archive.org & CDX API

1. **Archive.org is a goldmine for paywalled content.** Most major media sites have been fully
   archived by the Wayback Machine, often including content behind paywalls (archived before
   paywall was added, or via special bot access).

2. **Use CDX API for URL enumeration.** Don't rely on a site's own navigation/search to discover
   article URLs. CDX wildcard queries can find all archived URLs for a domain.
   - Endpoint: `https://web.archive.org/cdx/search/cdx`
   - Key params: `url`, `output=json`, `fl=original`, `filter=statuscode:200`, `collapse=urlkey`

3. **NEVER use a single large CDX query.** CDX silently truncates results when they exceed internal
   limits (~5K-10K). Results are sorted alphabetically, so truncation drops the tail end.
   - Solution: split into many small queries by prefix (e.g., per region, per content type)
   - Cache the index locally after building it — CDX queries are slow and flaky

4. **CDX `from_ts/to_ts` filters archive timestamp, NOT article publish date.** Archive.org
   periodically re-crawls old URLs, so a 2014 snapshot might contain a 1930s article.

5. **CDX snapshots may need fallback strategies:**
   - Exact URL → wildcard URL (catches UTM variants that bypassed paywalls)
   - Latest snapshot via `/web/2/{url}` as last resort
   - Classify errors: `no_snapshot` (don't retry), `fetch_failed` (retry 2x), `rate_limited` (exponential backoff)

## Network & Rate Limiting

6. **Archive.org rate limits at ~15 req/min/IP.** 3 concurrent workers with 1-2s sleep each is
   safe. More workers trigger more 429s, reducing net throughput.

7. **httpx connection pool avalanche.** After 5+ hours of continuous requests, the server may
   silently drop TCP connections. Stale connections in the pool cause cascading failures.
   - Fix: track consecutive failures; after 10, close the client and create a new one

8. **Distinguish error types for retry strategy:**
   - Connection error / timeout → retry 2x max
   - 429 rate limit → exponential backoff (30/60/90/120/150s)
   - No snapshot exists → don't retry, log and move on

9. **Prevent system sleep during long runs.** macOS: `caffeinate -i -s &`

## URL Formats & Site Structure

10. **Old sites have multiple URL formats across eras.** A site redesigned in 2022 may have URLs
    from 3 different CMS systems. Always check Archive.org snapshots from different years to
    understand URL evolution before writing any scraping code.

11. **Same article may have multiple URLs** (old format, new format, with/without port :80,
    UTM variants). The slug (last URL segment) is usually stable across formats — use it for
    cross-format deduplication.

12. **HTML meta dates may be unreliable.** CMS migrations often overwrite `article:published_time`
    with the migration date. Priority: URL path date > HTML meta > CDX timestamp > fallback.

## Data Quality

13. **HTML extraction needs fallback.** `<p>` tag extraction works for modern pages but fails on
    old/non-standard HTML. Use a wide extractor (all visible text blocks >30 chars) as fallback
    when primary extraction yields ≤200 characters but HTML is >5KB.

14. **Boilerplate removal is site-specific.** Paywall prompts, copyright notices, navigation text,
    subscription CTAs — build a keyword list and filter lines containing them.

15. **Deduplication must be multi-level:**
    - Level 1: URL/slug exact match
    - Level 2: Title + date match (catches different slugs for same article)
    - Level 3: Content similarity for truncated snapshots
    - Always keep the longest full_text version.

16. **Date recovery is hard and requires multiple sources.** No single method works for all
    articles. Try: URL path extraction, sitemap matching, TOC page matching, CDX index
    cross-referencing. Each method recovers a fraction; combine for best coverage.

## Concurrency

17. **Each concurrent worker needs its own HTTP client** (independent connection pool). One
    worker's pool crash should not affect others.

18. **Thread-safe I/O.** Use locks for: file writes, print statements, shared counters. Distribute
    URLs to workers via round-robin for even load.

19. **Stagger worker startup** (1s between each) to avoid simultaneous first requests triggering
    rate limits.

## General Principles

20. **Incremental runs are essential.** Always load existing data and skip already-downloaded URLs.
    Long scraping jobs WILL be interrupted.

21. **JSONL is the best storage format** for scraping output. Append-friendly, streaming-compatible,
    good tooling ecosystem. Split by month for manageability.

22. **Filter lists should be broad, not narrow.** Missing a filter (letting junk in) is harder to
    fix than over-filtering (which shows up in coverage metrics). Include: author pages, tag pages,
    index pages, sponsored content, newsletters.

23. **Never assume two complementary scripts cover each other's blind spots.** One unified script
    handling all formats is always safer than two scripts that "should" add up to full coverage.

24. **Log every decision.** Error logs, skip reasons, retry counts — you'll need them for
    debugging and for the gap report.

## Network Environment

25. **Diagnose SSL/connection errors before adding workarounds.** If you see
    `SSL: UNEXPECTED_EOF_WHILE_READING` or similar errors, first check your network
    environment: is there a proxy? Is the site blocking your IP? Is the URL correct?
    Try a simple direct request before adding complex SSL workarounds.

26. **Check for proxy environment variables.** If `HTTPS_PROXY`, `ALL_PROXY`, or
    `http_proxy` are set in the environment, they may interfere with requests to
    sites that don't need a proxy. Check `env | grep -i proxy` and unset if needed.

27. **Always test connectivity before bulk downloading.** Fetch one page first, verify the
    response is valid HTML/JSON (not an error page or CAPTCHA), then proceed with
    the full crawl.
