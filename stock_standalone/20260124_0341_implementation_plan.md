# Vectorized Gap Detection & Follow Integration

Optimize gap scanning performance using pandas vectorization and automate addition to the 'Follow Queue' for high-priority gap signals.

## Proposed Changes

### [Component] Trade Visualizer (`trade_visualizer_qt6.py`)

#### [MODIFY] [trade_visualizer_qt6.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/trade_visualizer_qt6.py)

- **Vectorize Scanning**: Optimize `_check_hotlist_patterns` to use pandas vectorized operations on `self.df_all` for market-wide gap detection.
- **Follow Integration**:
    - Automatically call `hub.add_to_follow_queue()` for detected gap stocks.
    - Set entry strategy to "竞价买入" (Auction) for gap-ups.
- **Live Strategy Alarm**:
    - Trigger `SignalMessage` with high priority (85+) for "Gap Up" (momentum start) and "Gap Down" (momentum failure).
    - Ensure these signals reach the `Alert System` (audio/log) as critical action signals.

### [Component] Strategy Controller (`strategy_controller.py`)
- **Signal Handling**: Ensure gap signals from the visualizer or monitor are correctly routed to the logging and alert systems.
