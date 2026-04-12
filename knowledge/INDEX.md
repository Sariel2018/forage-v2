# Knowledge Base Index

This is the catalog of accumulated experience.
To read details, use the Read tool on the file path.

## Universal (15 entries)

- [broad_filters](universal/broad_filters.md) -- Filter lists should be broad, not narrow
- [concurrent_workers](universal/concurrent_workers.md) -- Each concurrent worker needs its own HTTP client
- [connection_pool_avalanche](universal/connection_pool_avalanche.md) -- httpx connection pool avalanche
- [connectivity_test](universal/connectivity_test.md) -- Always test connectivity before bulk downloading
- [deduplication](universal/deduplication.md) -- Deduplication must be multi-level:
- [incremental_runs](universal/incremental_runs.md) -- Incremental runs are essential
- [jsonl_storage](universal/jsonl_storage.md) -- JSONL is the best storage format
- [log_decisions](universal/log_decisions.md) -- Log every decision
- [prevent_system_sleep](universal/prevent_system_sleep.md) -- Prevent system sleep during long runs
- [proxy_check](universal/proxy_check.md) -- Check for proxy environment variables
- [retry_strategy](universal/retry_strategy.md) -- Distinguish error types for retry strategy:
- [ssl_diagnose](universal/ssl_diagnose.md) -- Diagnose SSL/connection errors before adding workarounds
- [stagger_worker_startup](universal/stagger_worker_startup.md) -- Stagger worker startup
- [thread_safe_io](universal/thread_safe_io.md) -- Thread-safe I/O
- [unified_script](universal/unified_script.md) -- Never assume two complementary scripts cover each other's blind spots

## Web Scraping (12 entries)

- [archive_org_goldmine](web_scraping/archive_org_goldmine.md) -- Archive.org is a goldmine for paywalled content
- [archive_rate_limit](web_scraping/archive_rate_limit.md) -- Archive.org rate limits at ~15 req/min/IP
- [boilerplate_removal](web_scraping/boilerplate_removal.md) -- Boilerplate removal is site-specific
- [cdx_api_enumeration](web_scraping/cdx_api_enumeration.md) -- Use CDX API for URL enumeration
- [cdx_snapshot_fallback](web_scraping/cdx_snapshot_fallback.md) -- CDX snapshots may need fallback strategies:
- [cdx_timestamp_filter](web_scraping/cdx_timestamp_filter.md) -- CDX `from_ts/to_ts` filters archive timestamp, NOT article publish date
- [cdx_truncation](web_scraping/cdx_truncation.md) -- NEVER use a single large CDX query
- [date_recovery_multi_source](web_scraping/date_recovery_multi_source.md) -- Date recovery is hard and requires multiple sources
- [html_extraction_fallback](web_scraping/html_extraction_fallback.md) -- HTML extraction needs fallback
- [html_meta_dates_unreliable](web_scraping/html_meta_dates_unreliable.md) -- HTML meta dates may be unreliable
- [url_deduplication_by_slug](web_scraping/url_deduplication_by_slug.md) -- Same article may have multiple URLs
- [url_format_evolution](web_scraping/url_format_evolution.md) -- Old sites have multiple URL formats across eras
