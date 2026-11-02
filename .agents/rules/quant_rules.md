---
trigger: always_on
alwaysApply: true
---

# pyQuant3 / stock_standalone 工程规则

## 核心定位与原则
- 针对量化股票实时监控、多周期策略计算、信号账本与 Qt 可视化平台开发。
- 绝不在主线程执行高频或阻塞式磁盘 I/O（如 HDF5/SQLite 读取），必须使用 TTL 内存缓存或后台 Worker 线程。
- 所有错误返回固定结构 `df.attrs['__error__']`，严禁抛出异常中断主轮询流程。
- 图元绘制与 K 线指标计算必须严格执行脏检查（Dirty Check）与对象池复用，杜绝频繁 `removeItem`/`addItem`。
- 文件保存必须严格为 UTF-8（无 BOM）格式。

---

## 模型分工与协同调度规则（Manager-Worker）
- **触发前提**：仅当主会话为高阶大脑模型（如 **Gemini 4 Argon**）时启用；若主会话已切换为 **Gemini Flash**，则不接管此规则，由当前模型一站式自理。
- **角色分工**：
  - **主大脑（Gemini 4 Argon）**：充当管理者，负责任务定位、决策架构、方案设计与最终验收。
  - **执行主力（Gemini Flash）**：通过 `invoke_subagent(..., Model="flash")` 派发，承接具体写代码、做测试、跑单测等高消耗 Token 的具体任务。
- **动态裁量（质量第一，效率第二）**：
  - 方案明确的高消耗任务派发 Flash 提速降本；
  - 1~2 处顺手微调、极高复杂度难点或 Flash 熔断任务由主大脑亲自操刀，严守工程质量。
