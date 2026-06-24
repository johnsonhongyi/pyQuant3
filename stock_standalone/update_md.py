import codecs

new_entry = """## 2026-06-24 21:00
- [x] **实现 MA20 主升浪黄金坑策略的实盘预警闭环 (Integrated MA20 Trend BUY2 Logic into Live Strategy and Dashboard)**：
    - [x] **接入实盘决策引擎 (Decision Engine Integration)**：在 `intraday_decision_engine.py` 的买入判定逻辑中，成功引入 `trade_signal == 2`（MA20回踩反包）的捕获分支。一旦识别到该历史信号，引擎将自动将决策置为 "买入"，并强行给予 `0.45` 的高基础仓位评分（超越 0.40 的买入硬门槛），同时输出附带 `[MA20黄金坑]` 和 `BUY2` 标识的高优先判定理由，彻底打通了从历史选股到盘中拦截的执行链路。
    - [x] **报警信息染色与视效增强 (Dashboard Highlighting)**：在 `signal_dashboard_panel.py` 中更新了 UI 视觉规则，在 `_get_pattern_color` 颜色过滤器中新增了对 `BUY2` 或 `黄金坑` 关键字的探测。一旦命中，立刻触发显眼的 `#FFD700` (金色) 报警高亮；同时更新 `CATEGORY_MAP`，将 `BUY2` 和 `黄金坑` 同步收录至“买入机会”与“跟单信号”分组，实现报警瀑布流的精准推流与多维展示。

"""

try:
    with codecs.open('GEMINI.md', 'r', 'utf-8') as f:
        data = f.read()
except FileNotFoundError:
    data = ""

with codecs.open('GEMINI.md', 'w', 'utf-8') as f:
    f.write(new_entry + data)
