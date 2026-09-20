# Task 003 Walkthrough

- `IPOTradingCenter` now owns an injectable `ProactiveExitEngine`.
- `BUY`, `BUY_SCOUT`, and `BUY_CONFIRM` executions register or refresh the protected position and its higher-low stop.
- `evaluate_position_exit` converts the eight-layer engine result into an auditable order directive.
- Normal same-day reductions/exits and manual full-rotation sells are physically rejected by the execution layer. Only explicitly classified structural hard stops can use the emergency bypass.
- Partial exits update remaining shares in both engines; full exits archive the original holding snapshot with TradePlan and exit rule metadata.
- Ledger serialization and cold-start restoration now preserve nested TradePlans and rebuild the exit watch pool.
