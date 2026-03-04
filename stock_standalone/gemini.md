# 全能交易终端开发跟踪

> 创建时间：2026-01-20 18:24  
> 最后更新：2026-02-27 20:30  
> **核心目标**：数据统筹 → 信号跟踪 → 入场监控 → 盈利闭环


---

## 📜 开发守则 (用户强制)

1.  **任务历史不丢失**: 所有实施计划、任务清单、Walkthrough必须**包含日期时间命名** (e.g., `20260124_0341_task.md`) 并归档，**禁止覆盖**旧计划。
    - 每日任务完成后，同步更新到 `gemini.md` 的【变更日志】和【最近完成任务】中。
2.  **每日闭环**: 每日结束时更新【变更日志】和【当前任务状态】，确保次日可无缝接续。
3.  **文档即代码**: `gemini.md` 是项目的 Source of Truth，必须保持最新。
4.  **自动迭代**: 每次任务完成后，自动依据此规则更新文档并保存历史文件。
5.  **记忆持续性协议**: 
    - 每次启动新对话，AI 必须首先读取 `gemini.md` 顶部的【🔴 当前任务】和【🧠 核心上下文记忆】。
    - 禁止在未同步 `gemini.md` 的情况下进行大规模重构。

---

## ✅ 最近完成任务: K 线图标题双击第一板块词修复 (03-05 00:08)

**状态**: ✅ 已完成
**目标**: 彻底修复在有特殊富文本元素（例如HTML的 Span）时，点击第一个板块词仍会复制整行的 Bug。

### 核心变更
- **终极空间定位**: 废除基于换行符或特殊字符向左/右探索边界的做法，因为文本渲染在 `QTextDocument.toPlainText()` 期间会掺加不可见的控制字符或缩进转换。
- **直接映射匹配**: 采用直接在 `plain_text` 中用 `find(category_name)` 获取各板块词的具体起始索引与结束索引，只要 `hit_idx` 落在以该板块词区间为核心的极小外延范围内 (容差设为 3 涵盖空格及分隔符)，即视为精确击中。这一手段 100% 免疫任何换行或制表干预。

### 历史记录 (Brain Artifacts)
- 任务清单: [20260305_0008_task.md]

---

## ⏳ 历史完成任务: K 线图标题双击第一板块词修复 + 板块过滤筛室新增 (03-04 23:55)

**状态**: ✅ 已完成
**目标**: 为系统的浮动输入框（特别是 `history_manager.py` 的 `edit_query`）添加全功能编辑支持，使其具备 Ctrl+Z 撤销、Ctrl+Y 重做以及鼠标右键复制粘贴全选等常见编辑机制。

### 核心变更
- **撤销栈支持**: 改造 `gui_utils.py` 中的 `askstring_at_parent_single` 对话框，启用 `tk.Text` 的 `undo=True` 并自动记录栈。
- **快捷键绑定**: 在输入框级别捕获 `Ctrl+Z`, `Ctrl+Y`, `Ctrl+A`，实现安全的事件分发（拦截 `tk.TclError`）。
- **右键上下文菜单**: 添加特定操作系统的右键激活（Windows/Linux Button-3, macOS Button-2）展示标准的【撤销】、【重做】、【剪切/复制/黏贴/全选】选项菜单。

### 历史记录 (Brain Artifacts)
- 任务清单: [20260303_1145_task.md]
- 验收报告: [20260303_1145_walkthrough.md]

---

## ✅ 历史完成任务: 修复盘后时段与时间戳被错误解析导致缓存覆写遗失的问题 (03-02 18:45)

**目标**: 解决 `minute_kline_cache.pkl` 盘后被覆写、没有保留交易时间数据，以及由于 Pandas 时间戳解析错误导致缓存恢复时全盘被过滤清空的问题。

### 核心变更
- **时区强制本地化 (Timezone Localization)**: 在 `realtime_data_service.py` 的 `MinuteKlineCache.update_batch` 及 `update` 中，修改 `pd.to_datetime(val).timestamp()` 逻辑。使用 `tz_localize('Asia/Shanghai')` 处理 Naive Datetime，使其产生 CST (UTC+8) 的正确真实 Unix 时间戳（原先错将本地 Naive Datetime 作为 UTC 解析，造成 8 小时偏移落入缓存，被过滤器误伤）。
- **非交易时段硬性防御 (After-hours Defense)**: 添加 `hhmm` 拦截器。仅当 `(915 <= hhmm <= 1130) or (1300 <= hhmm <= 1505)` 时才允许数据点放入缓存 `deque`，彻底防止盘后持续轮询把高质量的白盘阶段的分时 K 线顶出队列。

### 历史记录 (Brain Artifacts)
- 任务清单: [20260302_1845_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/dad72e89-88c4-4730-8367-05225c778d1a/20260302_1845_task.md)
- 验收报告: [20260302_1845_walkthrough.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/dad72e89-88c4-4730-8367-05225c778d1a/20260302_1845_walkthrough.md)

---

## ✅ 历史完成任务: 数据库路径统一与 T1 交易时间防护 (03-02 08:50)

**状态**: ✅ 已完成
**目标**: 解决打包 EXE 后数据库表丢失的问题，并彻底拦截非交易时间的 T1 策略信号。

### 核心变更
- **路径统一 (Unified Path)**: 在 `TradingLogger`、`TradingGUI` 和 `clean_db_script.py` 中统一使用 `cct.get_base_path()`，确保 EXE 环境下数据库访问一致。
- **时间硬性防护 (Time Guards)**: 在 `stock_live_strategy.py` 引入 `is_work_day` 校验，并在 `T1StrategyEngine.evaluate_t0_signal` 增加 `get_work_time()` 双重拦截。
- **代码清理**: 优化 `T1StrategyEngine` 的类型注解与导入，移除冗余库。

### 历史记录 (Brain Artifacts)
- 实施计划: [20260302_0845_implementation_plan.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/918ee711-e9c3-4e05-bcc8-782abb648009/20260302_0845_implementation_plan.md)
- 任务清单: [20260302_0845_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/918ee711-e9c3-4e05-bcc8-782abb648009/20260302_0845_task.md)
- 验收报告: [20260302_0845_walkthrough.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/918ee711-e9c3-4e05-bcc8-782abb648009/20260302_0845_walkthrough.md)

---

## ✅ 历史完成任务: 早盘极速抢筹与去弱留强机制 (02-28 00:37)

**状态**: ✅ 已完成
**目标**: 针对“精选3,5只个股不能广撒网, 需要去弱留强”的需求，开发超快先机发掘与防御处理。实现早段极端动能捕获和VWAP硬性保护。

### 核心变更
- **激进抢筹 (Early Momentum)**: 在 `intraday_pattern_detector.py` 补充 `early_momentum_buy` 高优级验证。在 `StockLiveStrategy` `_on_pattern_detected` 级联，满足前5家自动建仓。
- **仓位风控 (Phase Engine VWAP)**: 在 `evaluate_phase` 完善当实时价格低于结算均线 (VWAP, `nclose * 0.99`) 一定时间后立即强制 `EXIT` 减仓。
- **数据管线修复**: 将 `MinuteKlineCache` 的保存过滤去除，确保分时均线逻辑全天有效运转。
- **容量上限管治**: 新增 `_process_follow_queue` 常续监控容量。满5只锁单拒绝广撒网。

### 历史记录 (Brain Artifacts)
- 实施计划: [20260227_2307_implementation_plan.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b61a772f-8ef7-4e79-a54c-ef0472a81381/20260227_2307_implementation_plan.md)
- 任务清单: [20260227_2307_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b61a772f-8ef7-4e79-a54c-ef0472a81381/20260227_2307_task.md)
- 验收报告: [20260228_0037_walkthrough.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b61a772f-8ef7-4e79-a54c-ef0472a81381/20260228_0037_walkthrough.md)

---

## ⏳ 历史完成任务: 报警日志代码缺失修复 (02-27 20:30)

**状态**: ✅ 已完成
**目标**: 解决语音报警调试日志中股票代码 (`Key`) 缺失的问题，确保所有报警信号在全链路（日志、IPC、UI）具备完整元数据。

### 核心变更
- **AlertManager 增强**: `_voice_worker` 现在能从语音文本中正则识别并补全缺失的 6 位股票代码。
- **信号调用标准化**: 将 `stock_live_strategy.py` 中遗留的直接语音调用重构为 `_trigger_alert` 统一入口。
- **覆盖场景**: 修复了“持仓股跌破MA5”、“冲高回落”、“自动买入执行”等关键报警的代码缺失问题。

### 历史记录 (Brain Artifacts)
- 实施计划: [implementation_plan.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b61a772f-8ef7-4e79-a54c-ef0472a81381/20260227_2030_implementation_plan.md)
- 任务清单: [task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b61a772f-8ef7-4e79-a54c-ef0472a81381/20260227_2030_task.md)

### 核心变更
- **统一流水线 (Unified Pipeline)**: 所有来源标的统一进入 `WATCHING` 状态。
- **状态机模型**: 实现 `WATCHING -> VALIDATED -> READY -> ENTERED -> HOLDING -> EXITED` 完整流转。
- **验证评分重构**: `validate_watchlist` 网关门槛提升至 0.7，加权“上轨攀升”与“新高”特征。
- **UI 对齐**: `HotlistPanel` 新增形态评分、描述、来源展示，支持 ToolTip。
- **数据库修复**: 彻底修复 `trading_signals.db` 结构损坏问题，补全形态支撑字段。

### 历史记录 (Brain Artifacts)
- 实施计划: [implementation_plan.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b52a30b0-3f13-4b12-bb09-dfe50b2a1a3b/implementation_plan.md)
- 任务清单: [task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b52a30b0-3f13-4b12-bb09-dfe50b2a1a3b/task.md)
- 验收报告: [walkthrough_p4.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/b52a30b0-3f13-4b12-bb09-dfe50b2a1a3b/walkthrough_p4.md)

---

### 变更文件

| 文件 | 变更 |
|------|------|
| `intraday_pattern_detector.py` | `PatternEvent` 增加 `signal` 字段，绑定 `StandardSignal` |
| `daily_pattern_detector.py` | `DailyPatternEvent` 增加 `signal` 字段，实现标准化输出 |
| `stock_live_strategy.py` | 重构 `_on_pattern_detected` 以适配标准化信号 |
| `trade_visualizer_qt6.py` | 修复 `_update_signal_log_from_ipc` 兼容性，支持 `subtype` 映射 |
| `test_signal_suite.py` | 修正语法错误，支持标准化信号测试逻辑 |

### 核心产出
- **信号标准化**: 所有形态检测器现在统一输出 `StandardSignal` 对象。
- **IPC 链路打通**: 修复了可执行程序(Visualizer)无法正确解析推送信号的问题。
- **UI 增强**: 系统现在能更准确地识别高优先级信号并触发对应的视觉反馈。

---

## ⏳ 历史完成任务: P0.9 - 主升浪持仓与见顶信号优化 (02-02 20:30)

**状态**: ✅ 已完成
**目标**: 基于 002667 案例，从发现主升浪→持有→顶部信号清仓的全流程优化。解决主升浪“拿不住”和高位“走不掉”的问题。

### 变更文件

| 文件 | 变更 |
|------|------|
| `td_sequence.py` | **新建** - TD 序列 Setup/Countdown 算法 |
| `daily_top_detector.py` | **新建** - 日线顶部风险评分引擎 |
| `intraday_decision_engine.py` | **修改** - 注入主升浪持仓保护与 `debug` 指标输出 |
| `stock_live_strategy.py` | **修改** - 集成实时 TD/Risk 报警与语音播报优化 |
| `strategy_manager.py` | **修改** - 代码质量清理与验证页集成 |

### 核心产出
- **TD 序列实战化**: 实时计算 9 连 Setup，提前预警趋势衰竭。
- **顶部风险量化**: 综合 TD、量价、背离给出 0-1 评分，>0.6 触发减仓。
- **持仓“焊死”**: 主升浪期间（连阳/红三兵）无视盘中分时波动，除非跌破关键均线。

---

## ⏳ 历史完成任务: 热点面板信号监测集成 (01-21 01:20)

**状态**: ✅ 已完成  
**目标**: 为热点列表股票提供实时形态检测和跟单日志

### 变更文件

| 文件 | 变更 |
|------|------|
| `signal_log_panel.py` | **新建** - 实时信号日志浮动面板 |
| `hotlist_panel.py` | 新增 `check_patterns`/`_on_signal_detected` 方法 |
| `trade_visualizer_qt6.py` | 新增热点面板初始化和定时检测逻辑 |

### 快捷键 (系统全局模式)

| 按键 | 功能 |
|------|------|
| **Alt+H** | 显示/隐藏热点自选面板 (Global) |
| **Alt+L** | 显示/隐藏信号日志面板 (Global) |
| **H** | 添加当前股票到热点自选 |

---

## ✅ 最近完成任务: 报警弹窗交互优化 (01-22 22:45)

**状态**: ✅ 已完成
**目标**: 解决双击放大回弹、拖拽卡顿、单击歧义等交互问题，提供丝滑的操作体验

### 变更文件

| 文件 | 变更 |
|------|------|
| `instock_MonitorTK.py` | **交互重构** - 悬停停止震动、阻止事件冒泡、防抖、竞态修复 |

---

## ✅ 最近完成任务: P1.5 - 价格缺口可视化与自动跟单 (01-24 03:40)

**状态**: ✅ 已完成
**目标**: 实现价格缺口(Gap)在K线图上的无限延伸显示，集成实时全市场缺口扫描，并自动联动到 `TradingHub` 跟单队列。

### 变更文件

| 文件 | 变更 |
|------|------|
| `trade_visualizer_qt6.py` | **核心逻辑集成** - `_draw_price_gaps` (无限带宽) + `_check_hotlist_patterns` (向量化全市场扫描) |
| `hotlist_panel.py` | `add_stock` 方法支持 `group` 参数，实现分组管理。 |
| `signal_types.py` | 新增 `GAP_UP`, `GAP_DOWN` 信号类型及视觉配置。 |

### 历史记录
- 实施计划: `20260124_0341_implementation_plan.md`
- 任务清单: `20260124_0341_task.md`
- 验收报告: `20260124_0341_walkthrough.md`

---

---

## ⚡ 快速恢复指南

## ✅ 上一个任务: P0 收尾 - 集成形态检测 (已完成 01-21 01:08)

**变更文件**: `stock_live_strategy.py`

| 序号 | 变更点 | 状态 |
|------|--------|------|
| 1 | 添加导入 `IntradayPatternDetector` | ✅ |
| 2 | 初始化检测器 (2分钟冷却) | ✅ |
| 3 | 新增回调方法 `_on_pattern_detected` | ✅ |
| 4 | 循环内调用 `detector.update()` | ✅ |

---

## 🎯 核心问题与解决方向

**1. 添加导入**
```python
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent
```

**2. 初始化检测器**
```python
# --- ⭐ 日内形态检测器 ---
self.pattern_detector = IntradayPatternDetector(cooldown=120, publish_to_bus=True)
self.pattern_detector.on_pattern = self._on_pattern_detected
```

**3. 回调方法**
```python
def _on_pattern_detected(self, event: PatternEvent) -> None:
    """形态检测回调 - 触发语音播报"""
    pattern_cn = IntradayPatternDetector.PATTERN_NAMES.get(event.pattern, event.pattern)
    msg = f"{event.name} {pattern_cn}"
    action = "风险" if event.pattern in ('high_drop', 'top_signal') else "形态"
    logger.info(f"🔔 形态信号: {event.code} {event.name} - {pattern_cn}")
    self._trigger_alert(event.code, event.name, msg, action=action, price=event.price)
```

**4. 策略循环内调用**
```python
# 日内形态检测
if hasattr(self, 'pattern_detector'):
    try:
        prev_close = float(row.get('lastp1d', 0))
        self.pattern_detector.update(code, data.get('name', ''), None, row, prev_close)
    except Exception as e:
        logger.debug(f"Pattern detect error for {code}: {e}")
```

---

## 🎯 核心问题与解决方向

| 问题 | 原因 | 解决方向 |
|------|------|----------|
| 震荡频繁交易 | 信号即买入，无趋势确认 | 阶段性仓位状态机 |
| 未捕捉主升浪 | 仓位一次性建仓/清仓 | 蓄势→启动→主升分阶段加仓 |
| 高位未及时离场 | 无顶部形态检测 | 顶部识别评分机制 |

---

## 📋 迭代任务清单

### P0: 信号总线 + 形态检测 ✅ 已完成

- [x] `signal_bus.py` - 统一信号总线 ✅ 01-21
- [x] `intraday_pattern_detector.py` - 日内形态检测器 ✅ 01-21
- [x] `hotlist_panel.py` - 语音通知信号 ✅ 01-21
- [x] `stock_live_strategy.py` - 集成形态检测 ✅ 01-21
- [x] `trade_visualizer_qt6.py` - 全局热键 + 信号日志集 ✅ 01-21

### P0.5: 统一数据中心 + 板块联动跟单 (2026-01-23)

**目标**: 数据说话、盈利说话，聚焦板块联动强势突破

**Phase 0: 数据统筹** ✅ 已完成
- [x] `trading_hub.py` - 统一数据访问层 (新增)
- [x] 扩展数据库表：`follow_queue`、`positions`、`strategy_stats`
- [x] 整合 `signal_strategy.db` + `trading_signals.db`

**Phase 1: 板块联动跟单** ✅ 已完成
- [x] 重构 `_scan_rank_for_follow` 聚焦板块效应
- [x] 热点面板右键「加入跟单队列」
- [x] 信号优先级：板块联动连阳(P10) > 连阳回踩MA5(P9) > 板块突破(P8)

**跟单信号类型**:
| 优先级 | 信号类型 | 条件 |
|--------|----------|------|
| P10 | 板块联动连阳 | 热点板块 + 连阳≥2 + 放量 |
| P9 | 连阳回踩MA5 | 连阳≥2 + 回踩MA5启动 |
| P8 | 板块突破 | 热点板块 + 突破high4/hmax + 放量 |
| P7 | 回踩MA5启动 | 价格偏离MA5 ±3% + 放量 |
| P6 | 回踩MA10启动 | 价格偏离MA10 ±3% + 放量 |

**Phase 2: 入场监控** ⏳ 进行中
- [x] 竞价买入提醒 (9:25)
- [x] 盘中回踩MA5提醒
- [ ] 突破确认提醒
- [x] 跟单队列可视化面板

**Phase 3: 绩效闭环** ⏳ 待办
- [ ] 每日盈亏统计
- [ ] 策略胜率计算

### P0.6: 仓位状态机执行 (PositionPhaseEngine) ✅ 已完成
- [x] **Core Engine**: `position_phase_engine.py` implemented (SCOUT/ACCUMULATE/LAUNCH/SURGE/EXIT).
- [x] **Integration**: Integrated into `StockLiveStrategy`.
- [x] **Visualization**: `HotlistPanel` receives Phase updates.

### P1: 策略整合 (Strategy Integration)
- [ ] `daily_pattern_detector.py` - 日K形态统一入口
- [ ] 重构 `_check_strategies` 形态逻辑
- [ ] 竞价阶段特殊处理
- [ ] 连续大阳检测

### P0.8: 信号优化与分析 (Signal Analysis) ✅ 已完成 (P5)
**目标**: 提升信号透明度，回答"为什么没买"的问题。

**完成事项**:
- [x] **信号历史同步**: `trading_analyzerQt6.py` 增加 "今日信号汇总" 视图。
- [x] **影子策略分析**: 对比主策略与影子策略(更严苛参数)的触发差异。
- [x] **策略调优**: 竞价策略参数放宽至 7% + 量比校验。

---

## 🧠 核心上下文记忆 (长期维护)

> [!IMPORTANT]
> **1. 观察池验证网关 (Single Gate Protocol)**
> - **文件**: `trading_hub.py` -> `validate_watchlist`
> - **硬性阈值**: `total_score >= 0.7`
> - **权重算式**: `趋势(0.3) + 上轨攀升(0.4) + 新高(0.3) + 形态分加成(max 0.3)`
> - **逻辑**: 每日 9:15 触发验证，不达标维持 `WATCHING`，达标晋升 `VALIDATED`。
>
> **2. 数据库一致性**
> - `hot_stock_watchlist` 表必须包含: `daily_patterns`, `pattern_score`, `source`。
> - `follow_queue` 在 ENTERED 状态时，必须由 `risk_engine` 实时监控 T+0 止盈止损。
>
> **3. 状态机流转**
> - 禁止任何标的跳过 `VALIDATED` 节点直接进入 `ENTERED`（除手动添加外）。

---

## 🔴 当前任务: Phase 5 分析器性能优化 (分页与时间过滤)

**状态**: 🔴 进行中
**目标**: 解决交易分析器(`trading_analyzerQt6.py`)查询超大记录时渲染引发的严重卡顿。新增时间区间过滤项与表格分页呈现功能。

### 核心子任务

| 序号 | 任务描述 | 状态 |
|------|----------|------|
| 1 | **UI 强化**: 在 `TradingGUI` 顶部栏加入 `时间范围` 条件下拉框，底部置入分页导航栏 | ⏳ 待办 |
| 2 | **数据剥离渲染**: 将 DataFrame 请求与 QTableWidget 循环渲染分开，依靠 `cached_full_df` 控制当页只绘 200 行 | ⏳ 待办 |
| 3 | **过滤应用**: 在拉取或渲染前拦截 DataFrame，裁切时间以减少无用数据混淆 | ⏳ 待办 |

### 历史记录
- **实施计划**: [20260301_2320_implementation_plan.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/72698ac6-1914-495f-be2e-9dbbf4bbd8df/20260301_2320_implementation_plan.md)
- **任务清单**: [20260301_2320_task.md](file:///C:/Users/Johnson/.gemini/antigravity/brain/72698ac6-1914-495f-be2e-9dbbf4bbd8df/20260301_2320_task.md)

---

## ⏳ 历史完成任务: Phase 4 留强去弱自动化 (03-01 10:35)

**状态**: ✅ 已完成

### P2: 交易闭环与报警优化 ✅ 已完成
- [x] **Alert System Hardening**: Created `alert_manager.py` ✅ 01-23
- [x] **Trading Analytics**: `compute_and_sync_strategy_stats` in `TradingAnalyzer` ✅ 01-23

### P3: 修复交易缺失 (Fix Missing Trades) ✅ 已完成
- [x] **Trade Execution Implementation**: `_execute_follow_trade` added to `StockLiveStrategy`.
- [x] **Alert & Monitor Linkage**: Process now triggers Trade + Monitor + Voice Alert.

### P4: 数据一致性与 UI 优化 (Data & UI) ✅ 已完成
- [x] **Data Consistency**: Verified `TradingHub` vs `TradingLogger` sync.
- [x] **UI Refresh**: `HotlistPanel` Reason/Phase columns added.
- [x] **Visuals**: Implemented `flash_screen` and high-priority alerts.

---

### P6: 策略整合 (Strategy Integration) ✅ 已完成
**目标**: 统一日线形态检测逻辑，标准化策略入口，增强竞价/回踩/突破逻辑。

**完成事项**:
- [x] `daily_pattern_detector.py` - 日K形态统一检测器 (Volunteer/Platform/BigBull) ✅ 01-23
- [x] `daily_strategy_loader.py` - 集成检测器并同步到跟单队列 ✅ 01-23
- [x] `stock_live_strategy.py` - 集成 `DailyPatternDetector` 并标准化 `_process_follow_queue` ✅ 01-23
- [x] 竞价策略标准化：`_check_auction_conditions` 独立逻辑 ✅ 01-23
- [x] 成功捕捉形态: V型反转、平台突破、大阳线、竞价高开 ✅ 01-23

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                     数据层                                │
│  tdx_data_Day.py → realtime_data_service.py → df_all     │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│                     检测层                                │
│  IntradayPatternDetector + DailyPatternDetector          │
│  └── SignalBus(统一事件分发)                              │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│                     执行层 (P0.5核心)                     │
│  PositionPhaseEngine: SCOUT→ACCUMULATE→LAUNCH→SURGE→EXIT │
│  └── 阶段性仓位: 0%→20%→50%→70%→50%→0%                   │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│                     输出层                                │
│  VoiceAnnouncer + HotlistPanel + TradingLogger           │
└──────────────────────────────────────────────────────────┘
```

---

## 📝 已完成模块

| 模块 | 文件 | 状态 |
|------|------|------|
| 热点面板 | `hotlist_panel.py` | ✅ |
| 热点详情 | `hotspot_popup.py` | ✅ |
| 策略框架 | `strategy_interface.py` | ✅ |
| 策略控制 | `strategy_controller.py` | ✅ |
| 信号系统 | `signal_types.py`, `signal_message_queue.py` | ✅ |
| 风险引擎 | `risk_engine.py`, `sector_risk_monitor.py` | ✅ |
| 语音播报 | `VoiceAnnouncer`, `VoiceProcess` | ✅ |
| 持久化 | `trading_logger.py` | ✅ |
| **日内形态检测** | `intraday_pattern_detector.py` | ✅ |
| **日K形态检测** | `daily_pattern_detector.py` | ✅ |
| **信号总线** | `signal_bus.py` | ✅ |
| **信号日志面板** | `signal_log_panel.py` | ✅ |
| **统一数据中心** | `trading_hub.py` | ✅ |
| **TD 序列信号** | `td_sequence.py` | ✅ |
| **日线顶部检测** | `daily_top_detector.py` | ✅ |
| **主升浪持仓保护** | `intraday_decision_engine.py` | ✅ |

---

## 📅 变更日志

| 03-05 00:08 | **UI 终极修复**: 采用直接坐标空间距离计算代替字符边界嗅探，彻底解决了第一个板块词错位的异常 | `trade_visualizer_qt6.py` |
| 03-04 23:55 | **UI 双增强**: 修复标题 hitTest 走漏换行符，新增板块过滤框支持右键粘贴过滤、清空 | `trade_visualizer_qt6.py` |
| 03-03 11:45 | **编辑体验升级**: 为 edit_query 输入框增加完整的鼠标右键菜单与 Ctrl+Z 撤销/重做支持 | `gui_utils.py` |
| 03-02 18:50 | **时间戳缓存修复**: 修正 Pandas 时间戳转化的时区偏移错误(UTC->Asia/Shanghai)，增加盘后缓存覆写防御机制 | `realtime_data_service.py` |
| 02-28 00:37 | **早盘超快抢筹与去弱留强机制**: 实现 early_momentum_buy 高优先级直入及仓位上限(5)，VWAP风控强退出机制解决死拿劣质标的 | `intraday_pattern_detector.py`, `position_phase_engine.py`, `stock_live_strategy.py`, `realtime_data_service.py` |
| 02-27 20:30 | **报警日志修复**: 增强 AlertManager 代码识别，重构 StockLiveStrategy 报警入口 | `alert_manager.py`, `stock_live_strategy.py` |
| 02-10 18:00 | **紧急 BUG 修复**: 修复 `trading_hub.py` 的 NameError (Dict) 与 `instock_MonitorTK.py` 的 NoneType 崩溃 | `trading_hub.py`, `instock_MonitorTK.py` |
| 02-10 17:50 | **P3/P4 统一流水线整合**: 实现以 Watchlist 为核心的状态机，重构验证评分 (Threshold=0.7)，UI 列对齐 | `trading_hub.py`, `hotlist_panel.py`, `stock_live_strategy.py` |
| 02-10 17:00 | **数据库结构修复**: 恢复损坏的 trading_signals.db，补全 Watchlist 形态字段 | `trading_hub.py`, `sqlite3` |
| 02-03 02:20 | **P1.6 信号标准化**: 统一 SignalStandard 结构，修复 Visualizer IPC 接收逻辑 | `intraday_pattern_detector.py`, `trade_visualizer_qt6.py` |
| 02-02 20:30 | **P0.9 完结**: TD/TopScore 实时报警集 | `stock_live_strategy.py`, `strategy_manager.py` |
| 01-24 03:41 | **P1.5 缺口监控与自动跟单完成**：集成向量化全市场缺口扫描，支持自动加入 `TradingHub` 跟单队列，优化 K 线缺口无限带显示 | `trade_visualizer_qt6.py`, `hotlist_panel.py`, `signal_types.py` |
| 01-23 16:45 | **P6 策略整合完成**：统一日K形态检测，标准化竞价/盘中跟单逻辑 | `stock_live_strategy.py`, `daily_pattern_detector.py`, `daily_strategy_loader.py` |
| 01-23 12:14 | 板块联动策略优化：聚焦连阳加速+回踩MA5/10启动模式 | `stock_live_strategy.py` |
| 01-23 11:51 | 创建 `trading_hub.py` 统一数据中心，整合两个数据库 | `trading_hub.py` (新增) |
| 01-23 11:45 | 热点面板右键添加「加入跟单队列」功能 | `hotlist_panel.py` |
| 01-22 22:45 | 修复报警弹窗交互：双击放大回弹、拖拽卡顿、Hover停止震动 | `instock_MonitorTK.py` |
| 01-22 19:46 | P0.8 Phase 1 完成：信号计数机制、聚合播报、高优先级检测(multi-MA+换手) | `intraday_pattern_detector.py`, `stock_live_strategy.py` |
| 01-22 19:15 | 新增 P0.8 信号优化任务规划：信号计数、批量播报、高优先级闪屏、分析可视化 | `gemini.md` |
| 01-22 19:05 | 新增策略信号数据库查看功能：trading_analyzerQt6 支持切换数据源、数据库诊断 | `trading_analyzerQt6.py`, `trading_logger.py`, `trading_analyzer.py` |
| 01-22 15:00 | 优化加载布局：强制禁用表格列自动宽 (ResizeToContents)，彻底解决面板内容撑大导致图表被挤压的问题 | `trade_visualizer_qt6.py` |

| 01-22 14:35 | 修复加载布局预设时 K 线视图计算错误：强制使用预设宽度而不是不可靠的瞬时物理宽度 | `trade_visualizer_qt6.py` |
| 01-22 13:46 | 修复 Filter 面板切换时 K 线图被遮挡问题：新增 `_reset_kline_view` 方法，使用 splitter 实际宽度计算可见K线数 | `trade_visualizer_qt6.py` |
| 01-21 11:27 | 合并监控循环：删除独立30s定时器 | `trade_visualizer_qt6.py` |
| 01-21 11:10 | 同股去重：弹窗复用 + 消息更新 | `instock_MonitorTK.py` |
| 01-21 01:26 | 升级全局热键模式，集成信号日志面板 | `trade_visualizer_qt6.py` |
| 01-21 01:20 | 重构热点监控，支持形态日志流 | `signal_log_panel.py` |
| 01-21 01:05 | 重构跟踪机制，增加当前任务详情区块 | `gemini.md` |
| 01-21 00:55 | 批准 P0 收尾实施计划 | `stock_live_strategy.py` |
| 01-21 00:36 | 整合规划文档，建立长期迭代跟踪 | `gemini.md` |
| 01-21 00:30 | 规划最后一公里执行问题解决方案 | 新增 `PositionPhaseEngine` 设计 |
| 01-20 18:38 | 完成 HotSpotPopup 详情弹窗 | `hotspot_popup.py` |
| 01-20 18:31 | 完成 HotlistPanel 热点面板 | `hotlist_panel.py` |
| 01-20 18:24 | 创建架构规划，确认设计决策 | - |

---

## 🔗 相关文档

- 信号总线: `signal_bus.py`
- 形态检测: `intraday_pattern_detector.py`
- 数据库: `signal_strategy.db` (follow_record表)
