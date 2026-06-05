# 📈 东山精密震荡结构下分支路由策略强化与自适应升级方案

> [!NOTE]
> 针对东山精密 (002384) 近期的高位震荡走势、5月下旬至6月初的多轮急跌诱空（如 06-01 放量跌停杀穿 Boll 下轨后，06-02 承接买单高开高走极速反弹）等典型场景，我们对 `StrategyRouter` 决策路由机制进行了强化设计，旨在解决“震荡市频繁追涨扫损、破位瞬间割肉且反弹时踏空”的痛点。

---

## 🔍 东山精密典型案例实战技术诊断 (Case Diagnostics)

### 1. 急跌诱空与瞬间修复（极速 V 反修复）
* **现状痛点**：在 6 月 1 日跌停砸穿 Boll 下轨和主力支撑线时，系统因 `low_price < sws * 0.985` 满足了 `is_breakdown_held` 条件，将其归为 `OscillatingBreakdownBranch` 并执行止损平仓。当 6 月 2 日个股开盘出现大量多头承接（大单急拉、高开高走）形成反弹买点时，由于趋势线 SWS 此时呈现下斜态势（`sws < sws_prev5 * 0.99`），该个股在空仓状态下仍被强行归为 `OscillatingBreakdownBranch`，从而直接被 `action = "HOLD"` 短路，使操盘手错过了这笔高确定性的冰点反弹利润。
* **强化方案**：引入 **`V_REVERSAL_EXEMPT`（大跌/破位次日强修复豁免）** 机制。只要次日表现出多头强力逆袭特征（高开高走、DFF 动量急拉、重回支撑线上方），就从防守地牢中“无条件释放”，并恢复其低吸或爆发做多路由。

### 2. 震荡结构中的时间保护过敏 (`TIME_FAILSAFE`)
* **现状痛点**：在震荡结构中，个股在主升前往往存在 3~5 天的缩量洗盘磨底期。现有策略对 `TIME_FAILSAFE` 时间保护执行过严（`days_held >= 3` 且 `pnl_pct < 3%` 且趋势微跌即强制平仓）。这导致个股在洗盘的第 3 天因收益不佳被系统“善意平仓”，随即便迎来强力大阳线。
* **强化方案**：对于归属于 `SwsPullbackBranch`（慢趋势低吸）或 `SuperTrendMA10Branch` 且被判定为高位震荡市（`is_consolidation_stage`）的个股，将时间保护从 **3天延长至 5天**，且只有在出现真实账面浮亏（`pnl_pct < -1.5%`）时才执行强制保护，如果微利或微亏则坚定守仓。

---

## 🛠️ 方案 B 策略代码优化 Diff 设计 (Code Design)

> [!IMPORTANT]
> 以下为针对 `trading_kernel/engine/decision_engine.py` 的手术级代码优化方案。设计了 V 反修复豁免及高位震荡防守调整逻辑。

### 1. 优化 `OscillatingBreakdownBranch.match`（引入 V 反强势修复豁免）
```diff
     @classmethod
     def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
         sws = ctx["sws"]
         sws_prev5 = ctx["sws_prev5"]
+        price = ctx["price"]
+        dff = ctx["dff"]
+        vol_ratio = ctx["vol_ratio"]
+        pct_diff = ctx["pct_diff"]
+
+        # 👑 引入 V 反强力修复豁免机制：防止在急跌诱空次日强承接时被防守误杀
+        # 条件：1) 价格收复主力工作线上方；2) 或者是日内阳线拉升且大单资金强力流入(dff/vol_ratio共振)；3) 或者昨大跌今强反弹
+        close_prev1 = ctx.get("close_prev1", 0.0)
+        is_yesterday_panic = (close_prev1 > 0.0 and pct_diff < -6.0) or (close_prev1 > 0.0 and close_prev1 <= ctx.get("low_prev1", 0.0) * 1.01) # 昨大跌或昨收盘在最低点附近
+        is_today_strong_rebound = (price > ctx.get("open", 0.0) and pct_diff > 2.0 and dff > 1.0)
+        
+        is_v_reversal_exempt = False
+        if sws > 0.0:
+            is_rebound_above_sws = (price >= sws * 0.998)
+            is_dff_recovery = (dff > 1.8 and vol_ratio > 1.3 and price > ctx.get("open", 0.0))
+            if is_rebound_above_sws or is_dff_recovery or (is_yesterday_panic and is_today_strong_rebound):
+                is_v_reversal_exempt = True
+
+        if is_v_reversal_exempt:
+            return False # 豁免，不进入震荡破位防御分支
         
         # 10日支撑线明显呈向下倾斜趋势，代表已经进入震荡杀跌破位期
-        is_sws_downward = (sws > 0 and sws_prev5 > 0 and sws < sws_prev5 * 0.99)
+        # 优化：收紧向下倾斜门槛从 0.99 至 0.975，避免良性震荡洗盘被误杀
+        is_sws_downward = (sws > 0 and sws_prev5 > 0 and sws < sws_prev5 * 0.975)
         
         # 或者持仓状态下价格已经踩穿工作线 1.5% 以上，说明破位已被确认
         is_breakdown_held = (state == "IN_TRADE" and sws > 0 and ctx["low_price"] > 0.0 and ctx["low_price"] < sws * 0.985)
         
         return is_sws_downward or is_breakdown_held
```

### 2. 优化 `SwsPullbackBranch.decide`（补齐开仓兜底与时间保护放宽）
```diff
     @classmethod
     def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
         action = "HOLD"
         size_pct = 0.0
         regime = ctx["regime"]
         setup = "SWS_COLLECT_PULLBACK"
         confidence = ctx["confidence"]
         suggest_price = ctx["price"]
         
         if state in {"FLAT", "ARMED"}:
             if ctx["vol_shrink_3d"] and ctx["is_pullback_support"] and ctx["is_doji"]:
                 if ctx["is_collecting_stage"] or ctx["is_consolidation_stage"]:
                     action = "BUY"
                     size_pct = 0.30
                     ...
                     
             if action == "HOLD":
                 # 主升浪沿 MA10 爬升企稳低吸买入规则 (TREND_FOLLOW_BUY)
                 ...
                     
             # 💡 3. 新增尾盘低风险建仓规则 (TAIL_LOW_RISK_ENTRY)
             ...
 
+            # 👑 补齐 SwsPullbackBranch 核心兜底 Fallback 开仓逻辑
+            if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
+                action = "BUY"
+                size_pct = 0.40 if ctx["is_reentry"] else 0.30
+
         elif state == "IN_TRADE":
             is_breakout_tp = (ctx["pbreak"] == 1 or (ctx["ptop"] > 0 and ctx["price"] >= ctx["ptop"] * 1.01)) and ctx["pnl_pct"] >= 5.0 and ctx["vol_ratio"] >= 1.4
             is_upper_vol_tp = (ctx["upper"] > 0.0 and ctx["price"] >= ctx["upper"] * 0.97 and ctx["vol_ratio"] >= 1.2 and ctx["pbreak"] == 0 and ctx["pnl_pct"] >= 2.0)
             # 💡 慢趋势下的自适应不加速判定与时间保护：
             # 在慢趋势中，允许横盘震荡！只有在买入满 3 天，收益率不佳且主力防线 (SWS) 走平下斜或者价格跌破 10日线时，才执行保护！
             sws_val = ctx.get("sws", 0.0)
             sws_prev5 = ctx.get("sws_prev5", 0.0)
             is_trend_decaying = (sws_val > 0.0 and sws_prev5 > 0.0 and sws_val < sws_prev5 * 1.001) or (ctx["price"] < sws_val * 0.985)
             
-            is_time_failsafe = False
-            if ctx["days_held"] >= 3 and ctx["pnl_pct"] < 3.0 and is_trend_decaying:
-                is_time_failsafe = True
+            # 优化：震荡洗盘磨底期时间保护由 3天放宽至 5天，且只保护浮亏状态
+            is_time_failsafe = False
+            max_hold_days = 5 if ctx.get("is_consolidation_stage", False) else 3
+            if ctx["days_held"] >= max_hold_days and ctx["pnl_pct"] < -1.5 and is_trend_decaying:
+                is_time_failsafe = True
```

### 3. 限制 `SuperTrendMA5Branch` 在震荡阶段的追高仓位
```diff
         if state in {"FLAT", "ARMED"}:
             # 超级主升浪沿 MA5 强趋势爬升企稳低吸与防踏空策略 (MA5_SUPER_TREND)
             ...
             
             if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
-                action = "BUY"
-                size_pct = 0.40 if ctx["is_reentry"] else 0.30
+                # 优化：高位箱体震荡阶段禁止重仓追高，下调建仓比例至 0.20 防御，避免冲高回落吃扫损
+                action = "BUY"
+                is_consolidation = bool(ctx.get("is_consolidation_stage", False))
+                if is_consolidation:
+                    size_pct = 0.20
+                else:
+                    size_pct = 0.40 if ctx["is_reentry"] else 0.30
```

---

> [!TIP]
> **本强化方案的应用价值**：通过限制 `SWS` 下斜敏感度、增加“大跌阳线修复”豁免、以及放宽震荡期时间保护天数，能够让系统在东山精密等高位宽幅震荡股中避免“急跌割肉、反弹踏空、追涨吃回落”的反复扫损恶性循环。
