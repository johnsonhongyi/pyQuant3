# Task 004 Implementation Plan

1. Add a sequential shared-cache 60-minute batch fetcher.
2. Carry distinct day and 60-minute frames through the scan worker and engine.
3. Refuse to substitute day bars when genuine 60-minute bars are unavailable.
4. Expose 60-minute prefetch latency in scan performance metrics.
5. Cover deduplication, period selection, frame isolation, and missing-day behavior.
