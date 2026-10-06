# 策略核心包 20261004

- strategy.yaml 版本: v1.9(打包时)
- 策略总览.md:账户体系/决策链路/版本铁律(本地 Agent 先读)
- P规则实施手册.md:逐条可实施规格(输入/条件/阈值/输出/代码位置)
- ref/:核心参考实现(校验口径用)
- 实施顺序:读 yaml 全文→按手册逐条实现→用 ref 校验→严守 point-in-time

## 统一行情与持久化数据

- 服务器所有 SQLite 表统一保存在 `/mnt/4TB/dockerf/stockstrategy/data/easy-stock/stock-data.db`；旧数据库按表合并，旧路径兼容指向该文件，迁移源保留为 `.pre-unified-*` 备份。
- Go 后端与 Python 策略共用 `daily_bars` 日线表和同一张上游 HTTP 缓存表。A 股、美股、币圈的日 K、周 K、月 K 都优先使用本地日线；周/月 K 由本地日线聚合。本地数据落后于最近一个已收盘交易日时自动尝试更新，15 分钟内同一股票/交易日最多自动请求一次；显式刷新可立即重试，网络失败回退并标记本地旧数据。
- HTTP 缓存按数据类型设置有效期和陈旧回退期；浏览器的 `X-Stock-Cache-Refresh: 1` 会绕过新鲜缓存并尝试刷新。Nginx 不再单独保存行情响应缓存。
- 统一交易日日历位于 `/mnt/4TB/dockerf/stockstrategy/config/trading-calendar.json`，Python 服务目录通过符号链接读取，Go API 按文件修改时间热加载。A 股节假日由本地维护；美股常规整日休市按 NYSE 规则自动计算，临时休市/特殊开市可手动覆盖。美股常规交易日按纽约时间 16:00 收盘后才视为完整日 K，A 股按北京时间 15:00。
- 本地维护日历后运行 `.\sync-trading-calendar.ps1` 即可原子同步到服务器，无须重建或重启容器；完整部署也会同步本地日历。可在 `source/easy-stock-service` 目录运行 `python trading_calendar.py show US 2027` 查看休市日，运行 `python trading_calendar.py override US 2027-11-26 closed` 添加临时休市，`default` 可清除该日覆盖。A 股节假日区间直接维护 `trading-calendar.json`。
- 服务器 cron 自动运行盘后增量：A 股工作日北京时间 15:40 调用 `bars.py --append`；美股每日香港时间 06:15 调用 `bars_us.py --append`，由共享交易日日历跳过休市日。脚本写入统一 `stock-data.db`；美股增量优先腾讯日 K，东方财富 `105.<ticker>` 与 Yahoo 作为回退源。未拿到目标交易日数据会记录失败，不会误报补齐。
- 任务定义在 `docker/stockstrategy-market-append.cron`，锁与日志持久化在 `/mnt/4TB/dockerf/stockstrategy/data/service/locks/` 和 `/mnt/4TB/dockerf/stockstrategy/logs/service/market-append-{cn,us}.log`。安装脚本会启用系统 cron；不增加常驻容器。
- Python 可用 `market_cache.urlopen(..., force_refresh=True)` 强制刷新；运行 `python market_cache.py` 查看共享 HTTP 缓存统计。
