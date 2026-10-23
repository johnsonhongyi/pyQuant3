# 2026-10-23 13:00 【修复singleAnalyseUtil新浪行情超时与日志刷屏优化】

## 问题背景与根因定位
在运行 `python singleAnalyseUtil.py` 时出现高频网络连接超时异常并刷屏报错：
```
[10-23 11:27:56] ERROR:singleAnalyseUtil.py(<module>:1050): Error Exception:Connection timeout to host http://hq.sinajs.cn/?format=text&list=sz002312,sh600962,...
aiohttp.client_exceptions.ServerTimeoutError: Connection timeout to host http://hq.sinajs.cn/?format=text&list=...
except_count >3
```

经深入排查，发现以下 6 大缺陷：
1. **分片并发极端脆弱**：`JSONData/sina_data.py` 中 `_fetch_all_stocks` 使用 `asyncio.gather(*tasks)` 且未设 `return_exceptions=True`。全市场 5000+ 股票分为 6~7 个分片，只要其中 1 个分片在 3 秒连接超时内轻微抖动，整个 gather 立即将其他所有正在传输的分片全数强制取消（`CancelledError`），导致全市场行情获取彻底失败；
2. **重试机制完全失效**：`sina_data.py` 的 `get_stock_data` 中 `for _ in range(retry_count):` 内部根本没有 `try...except` 捕获异常，第 1 次网络抖动直接抛出未捕获异常中断函数，重试逻辑形同虚设；
3. **参数配置不合理**：
   - 单批次 `max_num = 850`，单 URL 挂 850 只股票长达 8KB，容易触发新浪端慢查询甚至拒绝；
   - 连接超时 `connect=min(3, remaining)` 过于苛刻，在网络高峰期极易误杀；
4. **脏数据未清理**：`get_stock_data` 每次循环重试未清空 `self.stock_data = []`，造成残余数据污染；
5. **缺少本地 HDF5 优雅降级**：`sina.all` 网络请求超时后直接崩溃，未能利用本地已有的最新有效 HDF5 快照降级兜底；
6. **日志严重污染刷屏与计数器漏洞**：
   - 报错直接将包含几百个股票代码的 8KB 字符串全量输出，并在终端用 `traceback.print_exc()` 打满整屏；
   - `singleAnalyseUtil.py` 的 `except_count` 仅在跨交易日时重置，偶发一次失败后即使成功 100 次，计数器依然累加，最终被永久判定为 `except_count > 3` 导致每次大幅长休眠。

---

## 实施任务清单
- [x] **1. `JohnsonUtil/commonTips.py` 增加超长 URL 错误脱敏与清洗工具**：
  - 新增 `format_clean_error(msg, max_codes=5)`，自动识别 `list=...` 并压缩为 `list=sz002312,sh600962,...(total=N stocks)`，控制错误消息在合理长度，避免日志污染。
- [x] **2. `JSONData/sina_data.py` 网络韧性与超时容错加固**：
  - 调整批次大小 `max_num = 500`；放宽连接超时至 `min(8.0, remaining)`；
  - `get_stocks_by_range` 增加分片局部快速重试机制；
  - `_fetch_all_stocks` 接入 `return_exceptions=True`，容纳部分分片成功；
  - `get_stock_data` 循环内部实施 `try...except`，清空 `self.stock_data`，重试用尽后返回符合规则的 `df.attrs['__error__']` 而不中断主流程；
  - `sina.all` 增加对本地有效 HDF5 缓存快照的优雅降级。
- [x] **3. `singleAnalyseUtil.py` 容错与日志清爽化**：
  - `get_hot_countNew` 内部包裹 `sina.all` 异常保护；
  - 成功完成一轮热点计算后立即重置 `except_count = 0`；
  - 最外层异常日志接入 `format_clean_error`，网络超时类异常跳过详细 traceback 刷屏。
- [x] **4. 自动化测试与工程验证**：
  - 编写 `tests/test_sina_network_resilience.py`，全覆盖网络超时、重试、错误脱敏、HDF5 降级和计数重置（6 项专项通过）；
  - 回归 `tests/test_single_analyse_memory.py` 与全系统测试（22 项全绿）；
  - 语法编译检查 0 错误。
