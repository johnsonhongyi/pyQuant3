# Task 003 Implementation Plan

1. Inject `ProactiveExitEngine` into `IPOTradingCenter` and register every completed buy.
2. Translate defensive actions into `REDUCE_30`, `REDUCE_HALF`, and `EXIT_ALL` directives.
3. Enforce T+1 both when generating and when executing sell directives, including rotation sells.
4. Preserve TradePlan and exit-rule metadata in closed-position snapshots and persisted ledgers.
5. Restore active TradePlans and exit watches after a cold start.

Real broker gateways, credentials, auto-merge, and live-trading switches remain untouched.
