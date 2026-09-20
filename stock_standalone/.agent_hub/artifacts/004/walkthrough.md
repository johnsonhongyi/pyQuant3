# Task 004 Walkthrough

- `batch_fetch_60m_kline_fast` reuses `TDXRealtimeFetcher.fetch_kline_bars(category="60m")` and its 30-second cache.
- `IPOScanWorker` prefetches day and 60-minute frames in its background thread, then forwards both to `analyze_stock`.
- Secondary-buy evaluation now requires a real 60-minute frame; a day frame is optional context only.
- Scan diagnostics report `60f_ms` separately.
