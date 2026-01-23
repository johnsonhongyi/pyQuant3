# 全能交易终端开发跟踪

> 创建时间：2026-01-20 18:24  
> 最后更新：2026-01-23 12:14  
> **核心目标**：数据统筹 → 信号跟踪 → 入场监控 → 盈利闭环


---

## 📜 开发守则 (用户强制)

1.  **任务历史不丢失**: 所有实施计划和已完成任务必须**按日期命名** (e.g., `Phase 1: ... (01-23)`) 归档在文档中，**禁止覆盖**旧计划。
2.  **每日闭环**: 每日结束时更新【变更日志】和【当前任务状态】，确保次日可无缝接续。
3.  **文档即代码**: `gemini.md` 是项目的 Source of Truth，必须保持最新。
4.  **自动迭代**: 每次任务完成后，自动回顾并按此规则更新文档。

---

## ⚡ 快速恢复指南

**每次新对话只需发送**: `@gemini.md 继续`

我会自动：
1. 读取此文档，恢复完整上下文
2. 找到 `🔴 当前任务` 区块，继续实施
3. 完成后更新进度和变更日志

**常用指令**:
| 指令 | 说明 |
|------|------|
| `@gemini.md 继续` | 继续当前任务 |
| `@gemini.md 继续 P0.5` | 跳转到 P0.5 任务 |
| `@gemini.md 状态` | 查看进度 |
| `@gemini.md 回顾` | 总结已完成工作 |

---

## ✅ 最近完成任务: 热点面板信号监测集成 (01-21 01:20)

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
- [ ] 跟单队列可视化面板

**Phase 3: 绩效闭环** ⏳ 待办
- [ ] 每日盈亏统计
- [ ] 策略胜率计算

### P0.6: 仓位状态机执行 (PositionPhaseEngine) [Pending]

**阶段性仓位状态机 (PositionPhaseEngine)**:
- **SCOUT (试探 10%)**: 出现选股信号，但无量能或形态确认。
- **ACCUMULATE (蓄势 30%)**: 形态确认（如突破平台），量能堆积。
- **LAUNCH (启动 50%)**: 分时放量突破，形态加速。
- **SURGE (主升 70-90%)**: 脱离成本区，进入主升浪。
- **TOP_WATCH (顶部预警 50%)**: 出现高位放量滞涨或冲高回落信号。
- **EXIT (离场 0%)**: 跌破支撑或顶部确立。

**待办事项**:
- [ ] `position_phase_engine.py` - 实现状态转移逻辑与评分机制
- [ ] 顶部识别评分 - 结合 `IntradayPatternDetector` 的 `high_drop` 信号
- [ ] 震荡过滤规则 - 增加波动率与均线粘合度判断
- [ ] 集成到 `stock_live_strategy.py` - 替换简单的 `is_buy` 逻辑
- [ ] `hotlist_panel.py` - 在列表中直观显示当前股票所处的“阶段” (进度条或标签)

### P1: 策略整合

- [ ] `daily_pattern_detector.py` - 日K形态统一入口
- [ ] 重构 `_check_strategies` 形态逻辑
- [ ] 竞价阶段特殊处理
- [ ] 连续大阳检测

### P0.8: 信号优化与分析 🔴 当前任务 (01-22)

**目标**: 降低信号频率噪音，提升有效信号权重，并实现信号历史的可视化分析

**问题现状**:
- 同一股票同一形态在短时间内多次触发，导致语音播报过于频繁("刷屏")
- 低开走高等关键信号未能区分量能和位置（如是否在20日均线以下）
- 信号触发后缺乏后续跟踪（维持次数、收盘结果）无法闭环分析

**待办事项**:
- [x] **信号计数机制**: 在 `_should_notify` 中记录触发次数，同股同形态连续触发时只更新计数，不重复播报
- [x] **延迟批量播报**: 对于连续高频信号，采用"聚合播报"模式 (如 "紫光国微 低开走高 x3")
- [x] **优先级权重提升**: 低于MA20的低开走高 + 带量(换手>3%) → 设为高优先级信号
- [x] **闪屏通知**: 新增 `flash_for_high_priority()` 方法，高优先级信号触发时短暂闪烁信号日志面板边框
- [ ] **信号分组**: 多个信号同时触发时按类型分组，显示 "低开走高(3只): 紫光, 科森, 汇成"
- [ ] **信号历史同步**: `trading_analyzerQt6.py` 的"实时策略信号库"视图增加对今日信号的汇总和计数展示
- [ ] **次日决策参考**: 记录信号启动时间、维持次数、收盘涨幅，用于生成次日竞价策略建议


**变更文件**:
| 文件 | 变更 |
|------|------|
| `intraday_pattern_detector.py` | 增加 `_signal_counts` 字典跟踪信号计数 |
| `stock_live_strategy.py` | `_on_pattern_detected` 增加计数判断、高优先级信号闪屏调用 |
| `trading_analyzerQt6.py` | 增加"今日信号汇总"视图，显示计数和收盘结果 |
| `signal_strategy.db` | `signal_counts` 表已有，需在写入时更新 `count` 字段 |
| `trade_visualizer_qt6.py` 或 `instock_MonitorTK.py` | 新增 `flash_screen()` UI 闪烁效果 |

---

### P2: 数据流优化


- [ ] 热点列表批量tick请求
- [ ] 形态触发UI闪烁
- [ ] 形态历史查看

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
| **信号总线** | `signal_bus.py` | ✅ |
| **信号日志面板** | `signal_log_panel.py` | ✅ |
| **统一数据中心** | `trading_hub.py` | ✅ |

---

## 📅 变更日志

| 日期 | 内容 | 影响 |
|------|------|------|
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
