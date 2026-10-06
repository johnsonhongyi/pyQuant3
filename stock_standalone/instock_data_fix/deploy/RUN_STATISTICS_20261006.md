# 策略运行统计

## 手动选择策略（hotfix9）

- 原手动刷新页面新增“选择策略单独运行”，排除放量上涨、均线多头，提供其余 8 项注册策略。
- 支持单项或多项勾选；每次变更自动保存，刷新页面和容器重启后恢复，取消全部也能保存。
- 仅运行所选策略并更新对应数据表，不补充回测。任务仍使用原共享锁，避免与原手动刷新或定时任务同时运行。
- 新接口：`/instock/api/selected-strategies`；GET 返回选项、保存的选择、状态和历史；POST 使用 `action=save/run` 与 `strategies` 名称数组。
- 所选任务使用独立 `selected` 统计分组，保留最近 10 次完整运行；比较配置包含策略列表，不同策略组合不计算耗时增减。
- 选择存储在原统计 SQLite 的 preferences 表；策略结果依然存入原策略数据表。
- 镜像：`instock:johnson250103-sina-runtime-perf-hotfix9-20261006`，基于 hotfix8；CPU、内存和缓存限额不变。

- 镜像：`instock:johnson250103-sina-runtime-perf-hotfix8-20261006`，基于 hotfix7-v3；资源限额不变。
- 页面：`/instock/manual-strategy-refresh`；完整统计：`/instock/api/manual-strategy-refresh`。
- 两项小策略与全策略各保留最近 10 次运行，包含成功、失败、锁冲突和可检测的中断；重启容器后保留记录。
- 全策略包含盘中策略入口及盘后 `strategy_data_daily_job.main`。两者通过 config.entrypoint 区分。
- 持久化文件：`/data/InStock/instock/cache/run_statistics.sqlite`，挂载到宿主机 `instockcache`；不放在易失 tmpfs 中。

## 自动记录

- 开始/结束时间、真实耗时、状态、退出码、错误摘要。
- 快照耗时、股票数量、日期；每项策略计算/结果写入耗时、扫描数、命中数、错误数、工作线程数；独立回测阶段耗时。
- 缓存内存命中、跨进程命中、源文件读取、绕过、逐出和缓存异常次数，以及结束时缓存占用。
- CPU 时间、进程峰值 RSS、进程磁盘 I/O 增量；启动/结束时的 cgroup 内存、CPU 限额/节流统计、内存事件、系统负载及 I/O/内存 pressure。
- 缓存配置、预筛选开关、线程配置、统计版本与任务入口。

指标仅在开始/结束及阶段边界采集，没有新增常驻监控进程。峰值 RSS 为当前 Python 进程生命周期峰值；盘后入口复用进程时可能包含此前阶段的峰值。
进程 I/O 不包含 MariaDB 进程自己的写入；pressure 总量增量可以辅助判断全系统的争用。

## 比较规则

- 耗时变化只比较同日期、同快照股票数量、同配置的精确成功记录。
- 列表显示缓存命中率、磁盘读取量、峰值内存和阶段耗时；完整 JSON 提供逐策略和系统计数器。
- 均值为列表内精确成功记录的描述统计，不同任务范围之间不能据此推断加速比。
- 后台线程直接等待手动进程结束并落盘，关掉网页不影响完成时间记录。
- 任务异常会自动记录；进程消失但未写入结束记录时标记中断，无法补出真实结束时间。
- 统计存储故障只记录错误日志，策略运行继续。

## 本次旧记录

用户观察区间：2026-10-06 12:34:28 至 12:44:46，共 618 秒。
日志确认：2026-09-30 历史快照 5544 只，加载 358 秒；放量上涨 62.6 秒，命中 10；均线多头 42 秒，命中 3；扫描错误均为 0。
旧网页结束时间取自查询时刻，未提供真实进程退出时间。因此该记录标为 estimated，不参与精确耗时增减比较，不伪造旧 CPU、内存和 I/O 指标。

下一次运行重点查看：快照加载时长、cache.evictions/cache_errors/source_reads、io_delta.read_bytes、major_faults、cpu_stat 节流及 pressure 增量。
当前全市场历史范围大于 24MB 热缓存容量，微基准收益不能直接外推到全量快照；是否存在缓存频繁逐出需由新指标证实。

## PVE 现场采样与升级建议（2026-10-06）

- PVE 物理内存 4GB（可见 3.7GiB），采样可用约 175MiB、Swap 已用约 1.7GiB；I/O PSI avg10 some/full 约 99%/67%，vmstat blocked 96–98、iowait 69–72%。
- 系统盘是 BKKJ32G 32GB mSATA SATA SSD，TRIM 可用，SMART 通电 41,442 小时；重映射扇区和程序失败计数为 0，厂商私有磨损字段无法可靠解读。PVE 根盘已用 19/26GB（76%）。
- 一秒采样中 sda 读取约 98MB/s、util 约 100%、队列约 24；loop0 同时约 42MB/s、await 约 95ms、队列约 73；USB 机械盘空闲。现场瓶颈落在系统盘/LXC 根存储与全局内存压力。
- DMI 显示 1 条 4GB DDR4、另有 1 个空槽。J4125 官方内存上限为 8GB，短期可加一条匹配的 4GB；不要仅凭 DMI 板级 32GB 字段购买更大容量。
- 2026-10-06 13:06 启动的两策略任务到 13:40 统计仍为 running、finished_at 为空；历史日期快照阶段记录 5,544 只、353.337 秒。阶段最终耗时尚无结果。iKuai VM 100 为 running；此前成功采样 inStock 容器 CPU 约 91%、内存约 1.08/1.25GiB、累计读约 1.71GB，启动时未见 CPU throttling 或 OOM。
- 低成本方案：升至 8GB RAM，并把 32GB mSATA 换成兼容的 256–512GB 高耐久 SATA SSD；长期方案：N100 小主机配 16GB RAM、1TB NVMe（需本机留备份/数据则 2TB），并确认 NVMe 槽实际通道和 iKuai 所需网卡/IOMMU 兼容。
- PassMark CPU Mark 对比约为 N100/J4125 = 1.81，多线程；单线程约 1.63。当前主要是内存和 I/O 等待，单换 CPU 不会得到同等端到端加速；N100+16GB+NVMe 的 1.5–3 倍是待同配置实测的工程估计，不是已验证结果。
- 新主机优先将 PVE 根盘、LXC102 根盘、Docker 镜像层和确认后的 TDX 活跃工作集放到 NVMe。当前挂载清单未见 TDX 历史目录的独立 bind mount，迁移前先确认路径并建立持久卷；/run/instock-history 是 tmpfs，无需迁移。策略结果、日志、run_statistics.sqlite 与历史归档可暂留 /mnt/4TB，并继续备份。
- 服务器构建与卡顿时间重合。若构建容器的工作目录、Docker writable layer、npm 缓存或镜像层位于该 mSATA 根盘，构建写入会与 inStock 扫描争用磁盘和内存，能解释首页/API 超时；目前不能仅凭采样把全部压力归因于构建。

### 13:50 进程监控追加

- PVE load average 为 102.37/90.58/75.92；可用内存约 176MiB，Swap 已用约 1.7GiB；blocked 约 98–101，iowait 约 63–67%。sda 与 loop0 均 100% util，loop0 await 约 126ms、队列约 71；USB HDD 空闲。
- 远端构建尚未退出：PID 258587 的父 shell 命令为 sh -c tsc -b && vite build；PID 258588 的 node tsc -b 状态为 Dl，等待点 folio_wait_bit_common，已运行约 33 分钟。进程位于 LXC102 的 Docker 容器 ID 前缀 44eb；因此中止后首页超时与主机 I/O 拥塞吻合，tsc 仍阻塞时 Vite build 尚未开始。
- 同一采样中 inStock 主进程 RSS 约 968MiB、CPU 约 33%；iKuai QEMU RSS 约 1.07GiB、CPU 约 56%；OpenWRT QEMU RSS 约 150MiB、CPU 约 9%。这次系统高 load 主要伴随大量 I/O 阻塞，不等价于 CPU 算力满载。

### 内存调整后复测（14:52–14:53）

- 确认配置：LXC102 memory=2600MiB、swap=2048MiB；VM100=800MiB，VM101=608MiB。来宾 RAM 上限合计 4008MiB，高于 PVE 可见的 3.7GiB，属于可用量低于配置上限的超分配。
- 当前 Docker 实测总占用约 498MiB：inStock 254MiB/1.25GiB，MariaDB 156MiB，API 35MiB，Portainer 40MiB，Web 13MiB。此刻实际负载可运行，不能由此保证所有来宾同时达到上限时仍有宿主机余量。
- 复测 PVE available 约 1.3GiB、Swap 已用约 0.95GiB；vmstat blocked=0、iowait=0，I/O PSI avg10 已降至约 2%。PID 258588 的 tsc 阻塞进程已消失；构建没有在本次监控中重新启动。
- swap=2048MiB 是 LXC 可用交换空间上限，不是新增物理 RAM；其消耗仍会落到 PVE 主机的 swap/存储上。inStock 容器原 1.25GiB 上限保持不变。
