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
