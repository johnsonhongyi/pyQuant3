# Implementation Plan - Emotion Scoring & Performance Feedback (2026-03-10 22:40)

Integrated advanced structural anchors and a performance feedback loop into the sentiment scoring system to capture "Strong Start" breakouts and reward continued momentum.

## Proposed Changes

### [Component] Data Service
#### [MODIFY] [realtime_data_service.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/realtime_data_service.py)
- **Metadata Integration**: Extracted `hmax60`, `hmax`, `max5`, `high4`, `top15`, and `ral` from historical data.
- **"Strong Start" (强势启动) Logic**:
  - Implemented tiered breakout bonuses (+20 to +30 points) for price crossing historical peaks.
  - Added status labels for "强势启动", "活异动", and "加速".
- **Performance Feedback Loop**:
  - Recorded signal start prices in `IntradayEmotionTracker`.
  - Added dynamic "绩效分" (Performance Bonus, up to +25) based on post-signal price appreciation.

### [Component] Replay Tool
#### [MODIFY] [test_bidding_replay.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/test_bidding_replay.py)
- Updated display to show both **Emotion** and **Detector** scores.
- Added selective stock filtering via `--codes`.

## Verification Results

### Automated Replay
- Ran: `python stock_standalone/test_bidding_replay.py --codes 688787 --resample d --start 09:30:00 --end 10:00:00`
- **Observation**: `688787` (SeaSky) triggered "Strong Start" at 09:30:27. Emotion score hit the **100.0** cap as the price continued to rise, and "绩效+" labels appeared as requested.
