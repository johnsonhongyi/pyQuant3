# Easy Stock 环境交接

生产部署背景与上次线上核验见 [source/docs/项目交接说明.md](source/docs/项目交接说明.md)。其中生产快照有日期，部署前必须重新核验容器、镜像、挂载与部署脚本预期基础镜像。

## 2026-10-11 总控统一发布规则（当前有效）

- 全系统职责与共用规范见[总控文档](../docs/engineering/全系统职责与Docker发布持久化回滚规范.md)：`pyQuant3/stock_standalone` 协调 TK/ATS 桌面和跨项目验收；stock-strategy 负责 Go API、SBC/Web 和共享题材/热度/连板事实；InStock 负责 Python 选股及基本面/历史候选证据；TK/ATS 分别负责本机关注实时消费和分析证据消费。数据事实、消费回执和交易执行不可互相替代。
- 默认发布以审核 Git SHA 对齐，不构建新镜像、不追加普通功能层。stock-strategy 的宿主机 Python 任务可在既有源码 Git 路径更新；Go/Web 目前封装在只读根文件系统镜像中，尚无已验证的无镜像更新入口，因此当前 `build-and-deploy.ps1` 仅为显式分层例外，不能视作默认发布方式。
- 已有 `full-system-linkage-trial-20261011114424` 是一次明确记录的候选版本；它不授权后续每个修复都构建新镜像。分层例外须记录原因、base digest、源码 SHA、唯一候选 tag、验收及回滚点。
- Docker 镜像说明标签表示镜像构建时的运行环境/源码；容器代码更新后的 Git SHA须另行记录，不能用静态 image label 冒充当前应用 SHA。更新或回滚都保持现有 bind mount 路径和结构，代码回滚不回滚或覆盖外置数据库/日志/行情数据。
- 体积报告分列 image size、容器 `SizeRw` 与虚拟总大小；删除镜像必须逐项确认运行与回滚引用，禁止全局 prune 和带 `-v` 删除容器。
- 本文件后续按日期记录的部署与镜像操作是当时的历史事实，不是当前发布指令；如与现行规则冲突，以本节及 `source/docs/02-部署文档.md` 第 9 节为准。

## 2026-10-08 本地修复状态

- 本次仅修复 stockstrategy 的 Easy Stock 行情管理、网络代理、回补与相关回归问题；没有部署、重启生产容器或修改生产数据库。
- Go / Python 继续共用外置 SQLite。行情代理配置位于共享数据库同目录的 `market-network.json`，内容大小受 API 限制，不是增长型数据。
- 容器路径为 `/data/easy-stock/market-network.json`；宿主机对应 `/mnt/4TB/dockerf/stockstrategy/data/easy-stock/market-network.json`。
- 在“后台状态看板 → 盘后自动回补”保存 HTTP / HTTPS 代理，留空直连；须使用宿主机与容器均可访问的地址。代理不支持内嵌凭据；本地回环 API 请求直连。
- 手动重试通过 Go 刷新相应市场的跟踪标的，校验已完成日线与新鲜度后落库；定时任务日志仍展示最近一次定时任务记录。
- `docker/market-append.sh` 在运行时读取 `stockstrategy-net` 上 API 容器的地址，用于宿主机 A 股历史回补，不依赖宿主机回环端口。
- 发布应继续使用现有脚本的锁、健康检查与回滚流程。上线后核验三市场手动刷新与定时回补、代理连通性、数据库日期和完整覆盖，再更新本文件与原交接文档的生产观察结果。

审核和测试范围见 [source/docs/04-行情实现审核.md](source/docs/04-行情实现审核.md)。

## 2026-10-09 SBC Go 原生版本部署

- 按 `docs/02-部署文档.md` 第 9 节执行 `build-and-deploy.ps1`，发布号 `20261009233755`，入口 `http://192.168.50.60:20073`。
- 部署前核验 SSH 固定指纹、实际旧版本 `20261008200333`、容器健康和挂载；可用内存 1,345,816 KiB，数据盘 584,013,692 KiB，Docker 存储 4,878,640 KiB。
- 发布脚本补充非阻塞 `flock` 部署锁；复用线上运行时镜像，本机编译 Go/Web，没有增加 Python 或其他后端运行环境。
- 新 API/Web 镜像均为 `20261009233755`，容器 `healthy`、重启策略 `always`；隔离预检查、Web 到 API 健康检查通过。
- 经 Web 代理调用 SBC v1，20 根独立合成 K 线返回 `implementation=go-native`、`schema_version=1`、20 个点；前端新资源 `index-BQ1rkf7d.js` 已验证。
- 持久化数据 `/mnt/4TB/dockerf/stockstrategy/data` 与日志挂载保留；本次未执行手动回补或实盘交易，未核验市场数据完整性及浏览器交互效果。
## 2026-10-10 SBC 图表交互与异常恢复部署

- 按部署手册第 9 节发布 `20261010002726`，入口 `http://192.168.50.60:20073`；API/Web 镜像版本一致，均为 `healthy`、重启策略 `always`。
- 发布前可用内存 1,364,896 KiB、数据盘剩余 584,004,992 KiB、Docker 存储剩余 4,863,968 KiB；SSH 固定指纹、部署锁、隔离检查及 Web 到 API 检查通过。
- 保留 `/mnt/4TB/dockerf/stockstrategy/data:/data` 和原后端/服务/Web 日志挂载；复用后端运行时，没有增加 Python 环境。
- 第一次本机构建因开发服务占用 esbuild.exe 而中止，线上未变更；关闭开发服务后完整重跑成功。
- 前端构建、157 项测试及 Go SBC/HTTP 回归通过；线上资源为 `index-BsMSVtQp.js`。
- 只读查询 000951.SZ：日线 60 根，2D 30 根，3D 20 根，周线 13 根，月线 3 根；20 根独立合成数据的 2D SBC 返回 go-native、20 个分析点。
- 浏览器线上核验详情默认图下、拖动及关闭重开恢复位置、移回图下、2D 图层。此前已核验列表独立滚动、上下切股、滚轮锚定最新和弹窗尺寸恢复。
- 数据边界：上述日线请求到 2026-10-09，部分派生周期仍使用截至 2026-09-30 的陈旧缓存，界面明确显示“陈旧行情”和截止日期；未删除缓存或进行批量补库，不能据此确认市场数据完整性。自动修复仅针对初始空数据或输入异常尝试一次，失败仍需检查上游及盘后任务。
- 详细变更、审核与后续边界见 `docs/tasks/2026-10-10_0027_SBC图表交互与异常恢复.md`。

## 2026-10-10 SBC 配色与分时 VWAP 部署

- 按部署手册第 9 节发布 `20261010004332`，API/Web 镜像均为该版本，健康状态 `healthy`、重启策略 `always`，发布保留持久化数据与日志挂载。
- 发布前可用内存 1,388,124 KiB、数据盘 584,001,508 KiB、Docker 盘 4,847,316 KiB；固定 SSH 身份、部署锁、隔离健康检查和 Web 到 API 检查通过。
- 对照 ATS 源码修复日线与分时配色、虚实线、九转胶囊、启动/逃顶聚类标记；分时由 Go 计算累计 VWAP，移除原 20 点简单均线。后端运行环境与依赖保持一致。
- Go SBC/HTTP 回归、VWAP 边界测试通过；前端相关 10 项测试、生产构建及类型检查通过。
- 线上只读检查 600733.SH 分时：238 根、末点 2026-10-09 15:00，source=sina，VWAP=4.65532111404224，vwap_estimated=true。新浪未提供成交额，此值是明确标注的收盘价/成交量加权估算。
- 浏览器验证图表底色 rgb(11,12,20)，MA5 金黄、MA20 品红、上下轨白色、中轨虚线；分时价格 rgb(0,180,216)，VWAP rgb(255,215,0)、虚线 6px/3px，图例显示“VWAP（量加权估算）”。
- 前端资源 `index-C8CHnO9f.js`。分时叠加价位明确标为日线参考，陈旧日线截止日期继续展示；未执行补库或交易，未宣称多日 VWAP 阶梯全部对齐。

## 2026-10-10 分时图层隔离与完整时段最终核验

- 最终发布版本 `20261010005208`，API/Web 均为 `healthy`、重启策略 `always`；资源为 `index-VXiLz4mG.js`。此前 `20261010004855` 已修复日线图层混入分时，最终版本补齐完整当日默认展示。
- 最终预检：可用内存 1,394,708 KiB、数据盘 583,996,904 KiB、Docker 盘 4,813,536 KiB。保留部署锁、健康检查、回滚与原持久化挂载。
- 浏览器确认 238/238 根分钟走势，日线图层 0、分时参考图层 1；青色价格实线、金黄 VWAP 6/3 虚线生效，分时未混入日线均线、九转或启动标记。
- 相关前端回归累计 13 项通过，Go SBC/HTTP 及 VWAP 回归通过；最终生产构建通过。600733.SH 分时 VWAP 仍为 4.65532111404224、估算状态 true，未掩盖成交额缺失。
- 项目提交 `f4053b9`、`a75838b`；详细说明见 `docs/tasks/2026-10-10_0043_SBC配色与分时VWAP对齐.md`。

## 2026-10-10 TDX 原生 Go 与分钟关系最终部署

- 按部署手册第 9 节发布 `20261010013310`，入口 `http://192.168.50.60:20073`；API/Web 镜像版本一致，均为 healthy、重启策略 always。实现提交 `f4ea4b0`，五日图格式化器与页脚补充提交 `711843f`。
- 发布前可用内存 1,387,340 KiB，数据盘 583,977,808 KiB，Docker 盘 4,766,932 KiB；保留固定 SSH 身份、部署锁、隔离健康检查及回滚。后端原有运行环境保持一致，未增加 Python。
- 最终线上只读核验 600733.SH 的分钟、5 分钟、日线、2D 均使用 TDX，最新 2026-10-09 15:00，stale=false；四只证券批量分钟请求各 240 根。
- 原生五日接口返回 1200 根，9 月 28/29/30 日及 10 月 8/9 日各 240 根；连续窗口 VWAP=4.904210478014583，与累计成交额/成交股数一致，未标为估算。
- 新增 SQLite 缓存 `/data/easy-stock/tdx-cache.db` 及 WAL/SHM 均映射外置盘 `/mnt/4TB/dockerf/stockstrategy/data/easy-stock/`，最终观察主库约 5.0M、WAL 4.0M、SHM 32K。保留原数据和日志挂载。
- Go TDX/HTTP/SBC 回归、前端完整 165 项测试通过；五日格式化器补充后相关 4 项回归及最终生产构建通过，未重跑完整前端套件。
- 浏览器最终版本显示同题材 4 只、至少 236 组、覆盖 100% 的分钟关系证据，估算换手率提示保留。首版曾确认五日 1200 根弹窗；最终版本交互自动化仍偶发 CDP 超时，五日缩放/滚轮不记为全部验收通过，需人工复核及盘中观察。
- 分钟评分仅代表当前页抽样滞后相关性，不代表因果或完整板块带动力；换手率基于当前流通股本估算，精确历史换手率仍需历史股本/公司行为数据。北交所、指数、盘口、逐笔及交易接口不在本次范围。
- 接口、缓存、配置、测试及后续说明见 `docs/engineering/tdx-market-api.md`、`source/docs/tasks/2026-10-10_0100_TDX原生Go与分钟关系.md`。
## 2026-10-10 SBC 白色主题部署

- 按手册第 9 节发布 `20261010113041`，API/Web 健康检查通过，原持久化数据与日志保留。实现提交 `bafeac6`。
- 顶部“白色”复选框默认关闭；独立于应用主题，localStorage 自动持久化，小图与放大窗口共享，支持同源页签同步。白底适配坐标、网格、详情、K线、成交量及全部 SBC 标记线；黑色原配色保留。
- 相关 6 项测试、生产构建通过。线上浏览器确认默认未选中、勾选后白底 rgb(255,255,255)、刷新保持选择、弹窗白色；取消后恢复黑底 rgb(11,12,20)。截图检查通道、均线、九转及信号标记可见。
- 发布前可用内存 1,411,624 KiB，数据盘 583,905,520 KiB，Docker 盘 4,748,212 KiB；未新增依赖、后端运行环境或行情数据库。详情见 source/docs/tasks/2026-10-10_1130_SBC白色主题.md。
## 2026-10-10 SBC 双击放大部署

- 最终发布 `20261010115951`，API/Web 健康检查通过，保留原持久化数据与日志；提交 `67adad9`、`1565a48`。
- 双击小图绘图区（含成交量区域）打开现有放大窗口，复用保存尺寸、股票、周期和主题；按钮及选项区域不触发。聚焦采用 preventScroll，避免首次点击滚动页面打断双击。
- 4 项相关图表回归通过，最终生产构建通过。首版线上发现首次聚焦滚动导致双击中断后修正；最终版本刷新页面后首次实际双击成功打开放大窗口，显示原股票、日K与白色配色。
- 发布前可用内存 1,470,640 KiB、数据盘 583,889,896 KiB、Docker 盘 4,713,244 KiB；未改后端环境或行情逻辑。

## 2026-10-10 行情外发限流与 InStock TDX 日线闭环

- 策略服务发布 `20261010171545`，API/Web 健康检查通过。热榜、行业/主题及成分数据使用 Python/Go 共享 SQLite 限流状态；成功后按资源至少冷却 30 分钟，429/403 默认 30/60 分钟，读取 `Retry-After` 并对重复限制指数延长，最高 24 小时。
- A 股策略日线通过只读挂载读取 InStock `forwardp`，带 `source/trade_date/stale` 元数据；缺少本地目标日时不回退外部行情源。线上 `600733.SH` 最新为 2026-10-09、`stale=false`；`920305.BJ` 只返回至 2026-07-29 且 `stale=true`。Go TDX API 对其空日线返回 HTTP 200 空序列，不再误报连接故障。
- InStock 2026-10-09 回补 marker 已完整：库存 5,572 个唯一股票代码，5,538 个有效行、34 个空日线/no-trade；数据库为 5,538 行且 OHLCV 无效行 0。TDX 本地日历合并覆盖 501 个交易日，`target_in_calendar=true`。容器日线 cron 已设为工作日 16:05 首跑、16:35 重试，共享锁有效。
- InStock 容器仍基于 `instock:johnson250103-sina-runtime-flatbase-20261007`；当前 crontab 已做单行更新并备份，但该文件未由宿主机 bind mount。后续如重建/替换 InStock 容器，应以更新后的 InStock `cron/root` 为准；现存 hotfix 构建脚本基线与 live image 不匹配，不能原样重放。
- 详细复核、测试与备份位置见 `docs/tasks/2026-10-10_1326_数据底座限流与TDX闭环.md` 及上级 `../ENVIRONMENT_HANDOFF.md` 本节。

## 2026-10-11 Docker 数据外置与重建保护

- 备份扩展至 InStock 容器源码、环境、项目配置、`/etc/environment`、运行 root crontab、`/tmp` 修复文件和 MariaDB 在线全库快照；主目录为 `/mnt/4TB/dockerf/maintenance-backups/stockstrategy-instock-predeploy-20261010-235029`。MariaDB 31 张 InnoDB 应用表的压缩快照约 1.24 GiB，校验通过。
- InStock 下一版通过只读外置源码、外置配置和现有四类数据挂载运行；容器根文件系统只读，回撤保留旧容器且不覆盖数据库。旧日期部署/同步脚本已拒绝执行。
- stock-strategy 部署与回撤入口现在核对完整挂载契约及回撤 SHA256。新任务文档：`docs/tasks/2026-10-11_0055_Docker持久化挂载与无损重建.md`；InStock 挂载约定：`../instock_data_fix/deploy/DOCKER_DATA_CONTRACT.md`。
- 未停止生产容器、未部署新版本。备份在同一 4TB 盘，仍需异地副本覆盖磁盘故障风险。
## 2026-10-11 stock-strategy API 单层镜像与外置持久化核验

- API 已切换到 `stockstrategy/backend:20261010171545`，镜像 ID `sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d`，1 层、101,772,610 字节；后端程序 SHA256 为 `d8d152e0497c9dae335266bf6a935e85b6eaee36efca272d7aa2f60bcf719832`。旧 25 层镜像以 `preflat-20261010171545-20261010-180805` 和 `preflat-20261010171545-20261010-184456` 保留，旧容器 `stockstrategy-api-rollback-20261010-184456` 停止保留用于回撤。API/Web 均健康。
- API 的 `/data`、后端日志、服务日志、InStock `forwardp`、cron 配置均为原有外置 bind mount；数据/日志在 `/mnt/4TB/dockerf/stockstrategy/`，`forwardp` 与 cron 挂载只读。Web 静态发布目录和日志也在外置盘，容器镜像未更换。
- 完整备份位于 `/mnt/4TB/dockerf/maintenance-backups/stockstrategy-api-flat-success-20261010-184456`，`COMPLETE` 已创建；数据与配置复制校验文件为空，表示无差异。配置前后 SHA256 相同，标准化数据树前后清单相同；`stock-data`、`tdx-cache` SQLite 完整性均为 `ok`，schema 与业务行无变化。
- `docker diff` 未发现 API 应用目录或数据库/配置写入；仅有 Docker init 与外置挂载点登记。Web 写层仅见 nginx PID 和临时 cache 目录，日志仍走外置挂载。当前 API/Web 的 `ReadonlyRootfs=false` 与切换前一致；后续如需强化只读策略，应先单独验证运行期写路径。
- 发布入口 `docker/deploy-prebuilt.sh` 已增加日历、market-append、cron 与外置配置不一致时的前置拒绝，并停止随程序发布覆盖这些运行配置；日志目录仅调整顶层属主，不递归改写历史日志。每版后端仍从固定单层 flat base 构建，预期镜像为 2 层，不再继承上一版累积层。新入口由本地 `build-and-deploy.ps1` 打包执行。
- 验证：生产 API/Web 健康；最终备份的配置、标准化数据树及两份数据库前后摘要逐项 `cmp` 一致；`bash -n docker/deploy-prebuilt.sh` 与 `git diff --check` 通过。

## 2026-10-11 stock-strategy 全只读发布与 nginx 缓存外置

- 按部署手册由 Windows 本地编译并发布 `20261011114424`；API/Web 均通过健康检查，入口 `http://192.168.50.60:20073`。回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261011114424`。
- API 基于固定 1 层 `flatbase-20261010171545` 构建，发布镜像校验为 2 层；API/Web 根文件系统均只读，API 8 个、Web 5 个外置 bind mount 契约校验通过。
- Web 整个 `/var/cache` 绑定到 `/mnt/4TB/dockerf/stockstrategy/runtime/20261011114424/web/cache`，nginx 缓存位于外置目录 `nginx/` 子目录；API/Web 的 `/tmp`、`/run` 也使用同版本隔离 runtime 外置目录。
- 新容器严格 `docker diff` 核验通过，`/var`、`/var/cache` 及其他应用运行时路径没有留在容器可写层；生产复核显示 API 镜像为 2 层，UID 101 对外置缓存中的 `/var/cache/nginx` 有写权限。旧 Web 仅保留在停止的回滚容器中；该容器原有的 `/var`、`/var/cache` 父目录记录按旧版兼容规则保留。runtime 目录须随该版回滚快照留存。
## 2026-10-11 stock-strategy 镜像清理状态

- 未创建新镜像。生产 API `20261011114424`（2 层）及固定 base `flatbase-20261010171545`（1 层）保持原 ID；API/Web 健康，最新 `20261011114424` 回滚快照 `SHA256SUMS` 校验通过。
- 删除了无标签、无容器引用、无父子镜像依赖的悬空单层镜像 `sha256:86cdcd64f75a`；移除了 Web 的 `20261010115951`、`20261010164527`、`full-system-linkage-trial-20261011114424` 三个旧别名，Web 实际镜像未改变。保留当前与回滚清单要求的标签。
- 旧 API 回滚容器 `stockstrategy-api-rollback-20261010-184456` 仍停止保留，引用 25 层镜像 `sha256:9528e661c84a` 及其历史父镜像链。其 5 个挂载均为外置 bind mount；`docker diff` 仅有外置挂载点登记和 Docker init，无应用或业务数据写层。
- 自动审核拒绝删除该生产停止容器，理由是镜像清理请求未明确授权删除容器。须取得明确授权后才能删除该旧回滚容器并清理其不再引用的 API 历史镜像链；当前 API、Web、最新回滚容器和外置数据不在清理范围内。
- 发布脚本现在要求本地 `-AllowLayeredImageBuild` 与远端 `--allow-layered-image` 双重显式开关；首次安装镜像操作要求 `--allow-image-build`。手册已记录门禁和禁止全局 prune。无开关启动本地发布脚本已验证在编译前退出。

## 2026-10-11 stock-strategy backend 镜像清理完成

- 按用户明确授权删除停止的旧回滚容器 stockstrategy-api-rollback-20261010-184456 及其历史 API 镜像父链；旧回滚路径已退役，代码版本回溯由 Git 管理。
- backend 现在只有两个镜像 ID：605917063f7b（20261011114424 与 full-system-linkage-trial-20261011114424，2 层，119 MB）和 ed8cbe9544ef（20261010171545 与 flatbase-20261010171545，1 层，102 MB）。无其他 backend 历史标签或镜像链。
- API/Web 生产服务仍健康且 ReadonlyRootfs=true；最新 API/Web 回滚容器保留，最新回滚快照 20261011114424 的 SHA256 校验通过。Web 镜像未改变。
- 删除旧容器时未使用 -v；其挂载均为外置 bind mount，外置数据、日志和配置未删除。未构建镜像、未重启服务。

## 2026-10-11 stock-strategy TK 桌面节点联动发布

- 按部署手册第 9 节发布 `20261011150918`，源码为 `source` 仓库提交 `5c0c917eaad171b529c7939c470473bce66eddb3`（`feat: 支持TK桌面节点自助接入联动`）。Windows 工作区 npm 生命周期进程受限导致首次构建失败；改用该提交的干净隔离工作副本并在授权环境重跑同一脚本后成功，失败尝试未写入生产。
- 后端新增 TK 桌面节点配置包导入、身份/HMAC/私网地址校验、SQLite 注册持久化、回连测试和重启恢复；peer 请求增加时间戳/nonce 防重放、路由白名单与请求体限制，并为联动目标读写增加同步保护。系统状态页新增粘贴/剪贴板导入、校验、连接状态和重试面板。Go 构建、`npm ci`（232 个包）、`tsc -b`、Vite 生产构建（1999 个模块）通过；发布隔离 API smoke 通过。本次未执行独立 Go/Web 全量测试套件。
- API 镜像 `stockstrategy/backend:20261011150918`，ID `sha256:7762f6b27e119995c5dcf73ba030d7720d02d5b7865f1ed55b692d5da759efc8`，从固定 base `flatbase-20261010171545`（ID `sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d`）产生，2 层、119,336,420 字节；API/Web app-version 均为 `20261011150918`。Web 镜像未更换，仍为 `stockstrategy/web:20261011114424`；静态文件挂载至 `/mnt/4TB/dockerf/stockstrategy/app/web-dist/20261011150918`。
- API、Web 均 healthy，API `/api/health` 和 Web 代理的 `/api/health` 返回正常。API/Web 根文件系统只读、`SizeRw=0`；API 8 个、Web 5 个挂载。SQLite 数据库和既有日志挂载保留；本次未修改数据库、行情数据或实盘交易状态。API/Web 的 `/tmp`、`/run` 及 Web `/var/cache` 使用本 release 的 runtime 外置目录。
- 回滚快照 `/mnt/4TB/dockerf/stockstrategy/rollback/20261011150918` 的 `COMPLETE` 与 `SHA256SUMS` 校验通过，记录的上一版 API/Web 标签均为 `20261011114424`。回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261011150918`。
- 本次仅证明从现有 pinned base 快速构建应用差异层的发布链有效；镜像未记录 source commit label，指定源码版本压平/晋升新 base 的命令尚未实现。设计见 `source/docs/tasks/2026-10-11_1520_分层镜像基线重建与业务代码保真设计.md`；实施和专项验收前不得从线上容器或人工同步目录生成新业务 base。

## 2026-10-11 17:10 TK/Go 鉴权一致性修复与现场验收

- 发布 `20261011170509`，应用源码 SHA `3d8359ea429cf7f178ba39fb6a6f9727fcf66117`；发布脚本提交 `95db0cd3`。从干净隔离副本按手册构建，固定 base、部署锁、隔离 smoke、健康门禁、回滚快照全部执行。
- 无令牌网页导入及后续联动共用内网/同源鉴权；声明桌面身份的请求始终验 HMAC。已配置 token 时仍校验 Bearer/X-A-Stock-Token。nginx 保留 Host 端口，配置和入口脚本随现有 web-dist/.runtime 版本化，复用现有 Web 镜像及 5 个挂载；旧容器保持自身入口和资源，可直接回滚。
- API 镜像 `stockstrategy/backend:20261011170509`，ID `sha256:5f1c1d8618c7d65693c2bf0542177343f7b3b5e0f397fa2c2ab52a75a1e1c2f4`，2 层、119336420 字节；Web 镜像仍 `stockstrategy/web:20261011114424`，ID `sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9`、62396647 字节。两者 RepoDigests 为空，记录 image ID，不虚构 registry digest。
- API/Web 均 healthy、always、只读根文件系统、SizeRw=0；SizeRootFs 分别 119336420/62396647；挂载数 8/5。数据、日志、行情、日历路径不变，runtime 和 Web 静态目录使用本 release。nginx -t 和回滚 SHA256SUMS 均通过。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261011170509`。
- 本机 Go `internal/httpapi`、`internal/linkage` 包测试通过，前端定向 12 项通过，发布 Go 编译、tsc/Vite 构建通过。真实 TK 导入 connected；targets/context/events/attention 均 200；跨源导入、错误 HMAC、nonce 重放、桌面越权读取 targets 均 401。
- 实际关注验收选用已有关注股 600418.SH；操作 `acceptance-0eb4fa96b52b4995a3c118e9acc6394a` 被 TK 以 `security_directory_unavailable` 拒绝，未保存关注变更。重复提交确认幂等；不能宣称 TK/ATS 消费闭环通过。
- 实际网关进程为 `D:\JohnsonProgram\instockMonitorTK\instock_MonitorTK.exe`。安装目录存在有效的根目录 stock_codes.conf，缺少网关读取的 JSONData/stock_codes.conf。拟从同一安装目录原样复制至兼容路径、不改程序；自动审批因先前“不改 TK”约束拒绝，已请求用户明确授权，尚未执行复制。
- 详细审核与后续范围见 `docs/tasks/2026-10-11_1710_TK与Go鉴权部署验收.md`；未触发真实交易，未记录密钥。