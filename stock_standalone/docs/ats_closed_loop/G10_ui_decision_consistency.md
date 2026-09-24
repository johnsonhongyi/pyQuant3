# G10 UI 决策透出

状态：UI 代码缺口已补；桌面人工验收未完成。实施前确认三处已有中文弱化/失效徽章，但展示分别按快照字段自行判断；指挥室右键菜单仍允许点击失效或过期 BUY，执行中心才会二次拦截。

现由 UniverseManager 和指挥室排名表调用共享生命周期分类函数，将 SignalLifecycle 状态与回撤/失效标记统一合并显示；首见涨幅为正而最新涨幅转负时，两处均归为走弱。生命周期原因保留最近事件的 `snapshot_id`、`event_id` 和 `candidate_id`；持仓交易池即使对应候选已为 `INACTIVE`，也保留真实持仓行并显示失效/走弱徽章。排名和指令表 tooltip 展示可用审计 ID，指令表显式显示 `reject_reason`/`gate_reason`。指挥室右键“立即执行”会禁用失效 BUY；动作入口再次校验失效、过期、陈旧指令与实时快照，并提示阻断原因。账户 tooltip 同时呈现 TK 内核对账状态、订单流水状态、PAPER 恢复就绪及阻断原因，避免将代码集合相等误示为账户已对齐。执行中心仍保留最终校验。

专项复验 `python -m pytest tests/test_g10_ui_execution_gate.py tests/test_ui_decision_badges_and_shadow_runner.py::test_universe_manager_extracts_weakened_and_invalidated_badges -q`：5 passed，覆盖失效/过期 BUY 拦截、右键菜单禁用与原因、正转负弱化分类，以及 WATCH/TRADE 投影的徽章和快照事件身份。三处真实视图一致性、桌面按钮状态及运行时 DirectiveAuditEnvelope 追溯仍待人工 GUI 验收；当前桌面没有可见 ATS 窗口，未启动线上运行实例。
