# 策略核心包 20261004

- strategy.yaml 版本: v1.9(打包时)
- 策略总览.md:账户体系/决策链路/版本铁律(本地 Agent 先读)
- P规则实施手册.md:逐条可实施规格(输入/条件/阈值/输出/代码位置)
- ref/:核心参考实现(校验口径用)
- 实施顺序:读 yaml 全文→按手册逐条实现→用 ref 校验→严守 point-in-time

## 统一行情与持久化数据

- 服务器所有 SQLite 表统一保存在 `/mnt/4TB/dockerf/stockstrategy/data/easy-stock/stock-data.db`；旧数据库按表合并，旧路径兼容指向该文件，迁移源保留为 `.pre-unified-*` 备份。
- Go 后端与 Python 策略共用 `daily_bars` 日线表和同一张上游 HTTP 缓存表。A 股、美股、币圈先查本地日线；缺失或显式刷新时请求上游，成功后写回共享库；网络失败可回退到本地旧数据。
- HTTP 缓存按数据类型设置有效期和陈旧回退期；浏览器的 `X-Stock-Cache-Refresh: 1` 会绕过新鲜缓存并尝试刷新。Nginx 不再单独保存行情响应缓存。
- 策略盘后增量更新仍由现有 `--append` 命令负责，没有添加交易日调度。日志统一放在 `/mnt/4TB/dockerf/stockstrategy/logs/`。
- Python 可用 `market_cache.urlopen(..., force_refresh=True)` 强制刷新；运行 `python market_cache.py` 查看共享 HTTP 缓存统计。
