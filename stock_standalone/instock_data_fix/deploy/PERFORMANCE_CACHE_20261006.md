# inStock 全策略与缓存调优

- PVE：192.168.1.50，J4125 四核，3765MB 内存；Docker 位于 LXC 102，1792MB 内存、512MB swap；数据盘为机械盘。
- iKuai VM100：1024MB；OpenWRT VM101：1248MB。未修改路由虚拟机与 PVE 配置。
- 最终镜像：`instock:johnson250103-sina-runtime-perf-hotfix7-20261006-v3`。
- Docker：保留 2 CPU、1280MB 内存、禁用容器额外 swap；CPU shares=256；BLAS/OMP/MKL 单线程。
- 当前内核不支持 Docker `--blkio-weight`，不得添加此参数。

## 运行路径

1. 同轮只获取一份 Sina 实时报价，先过滤价格/成交量无效的股票，再按绝对涨幅与振幅排序。
2. 排名前 800 只股票具有历史缓存准入资格；其余有效股票仍计算，避免漏掉策略信号。
3. TDX 解析缓存：进程内 LRU + tmpfs 中的 SQLite/NumPy 二进制缓存，文件大小、mtime_ns、inode 变化后自动失效。
4. 默认部署两层分别限额 24MB；tmpfs 挂载上限 96MB，包含 SQLite 页和事务日志开销；缓存故障回退原始文件读取。
5. 配置共享缓存时关闭旧逐股 pickle 缓存，避免双重缓存和无限增长；保留旧磁盘文件，不主动删除。
6. 十项注册策略串行共享同轮快照；逐股最多两线程，每策略复制输入防止污染其他策略。
7. cron 保留交易日检查与 flock；移除只跑两策略的限制。旧调用可显式使用 `INSTOCK_SMALL_STRATEGIES_ONLY=1`。

## 可调参数

| 参数 | 部署值 / 默认值 | 用途 |
|---|---|---|
| INSTOCK_HISTORY_CACHE_DIR | /run/instock-history | 跨 cron 缓存目录，必须使用 tmpfs |
| INSTOCK_HISTORY_CACHE_MB | 24 / 32 | 两层各自的容量上限，0 禁用新缓存 |
| INSTOCK_CACHE_HOT_STOCKS | 800 | 实时优先缓存股票数，0 不缓存实时股票 |
| INSTOCK_PREFILTER_ACTIVE_ONLY | 0 | 设为 1 启用活动阈值过滤，会改变选股覆盖范围 |
| INSTOCK_MIN_CHANGE | 1 | 活动阈值：绝对涨幅百分比 |
| INSTOCK_MIN_AMPLITUDE | 2 | 活动阈值：振幅百分比，与涨幅条件取或 |
| INSTOCK_MIN_AMOUNT | 1000000 | 活动阈值：最低成交额（元） |

实时价格与当日成交量每轮重新合并，不缓存最终信号。休市和历史日期沿用历史扫描路径。
当前未验证 Sina 部分行情缺失时的全市场覆盖，也没有交易时段全市场延迟实测。

## 验证

- 本地与目标 Docker：5 项测试通过，覆盖排序、过滤开关、跨进程命中、文件失效、修改隔离、禁用/故障回退与容量限制。
- 真实 TDX 64 只 / 30590 行只读基准：无缓存 0.859 秒、冷共享缓存 1.154 秒、共享热缓存 0.651 秒、进程内热缓存 0.219 秒；结果一致。
- 25 只历史样本完成全部 10 策略扫描，约 1.014 秒；排行榜外部依赖在离线测试中跳过，不写策略结果表。
- 微基准不代表全市场策略总耗时；冷缓存有额外写入成本，容器重建后需重新预热。
- 部署后 Web 健康检查与路由连通性验证；不能据此保证高峰期永不断流。

## 部署与回滚

`build-performance-hotfix7-20261006.sh` 从 v2 镜像构建 v3，部署脚本检查当前镜像为 v2，并在策略锁内切换容器。
Web 健康检查失败自动回滚；旧容器保留为 `inStock-rollback-perf-时间戳`。
手动回滚：停止当前 inStock，将其重命名后，将指定旧容器重命名为 inStock，恢复 restart=always 并启动。
