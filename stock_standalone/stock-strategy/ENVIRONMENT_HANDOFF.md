## 2026-10-15 21:18 Codex 默认已配置，布局修复待上线

- 已按用户要求，通过原生产配置 API 将 AI 对话默认持久化为桌面 Codex / gpt-6-luna / low，节点 codex-bf952db5fd9f615f2a8fff37。Hermes 保留可选；该设置已经生效。
- 源码 74dbefb 将联动信息移至图表底部、主操作置前，并修复首次切换 Codex 缺失节点与配置保存相互覆盖的问题。类型检查和构建通过，未做用户已取消的功能测试。
- 补丁包已上传但自动审批拒绝生产替换，理由为缺少对本次新 Web 补丁上线的明确授权；当前 Web 代码仍为 20261015210055，不将候选描述为已部署。详见 [候选与阻塞记录](docs/tasks/2026-10-15_2118_图表底部联动与Codex默认修复.md)。

## 2026-10-15 21:10 AI 对话与默认联动合并部署

- 用户批准本次 API 功能层镜像例外，已按发布脚本完成 20261015210055；源码 ae31e01，包含统一 AI 对话、SBC 联动面板黑白主题和共享默认设置。API 基于已核验 flat base，仅追加一层；镜像 ID sha256:db098a9fab20f2db1832355332f140764111abc94c21c8e6976d2e400425c94b。
- API/Web healthy、挂载结构 8/5，API 1 GiB/2 核。Web 沿用原镜像，外置资源版本更新；独立 Codex 桥已重启，心跳在线、可用模型目录 3 项。TK/ATS 未重启。
- 默认重点关注已通过管理员接口原子持久化为 JohnsonTriton（tk-eac80a9aa66a462795557e68），GET 读取确认。默认现由后端提供，跨浏览器生效；AI 对话仍保留 Hermes 原默认，可在设置选择 Codex。
- 用户在部署期间明确取消功能测试，改为自行手动验收；未执行本次线上 Web 视觉/刷新保存、真实 Codex 对话或关注回执测试，不声称这些已验收。仅必要的发布健康与状态核验完成，无测试订单。
- 回滚 COMPLETE：/mnt/4TB/dockerf/stockstrategy/rollback/20261015210055/COMPLETE；详细版本、默认契约与验证边界见 [合并部署记录](docs/tasks/2026-10-15_2110_AI对话与默认联动合并部署.md)。

## 2026-10-15 19:45 API CPU 配额优化

- 调整前 API CPU 上限 1 核；20 秒采样曾连续约 18 秒达到 97–103%，随后空闲。PVE 4 核、主机负载约 1.21；LXC 4 核，其他主要容器 CPU 低于 0.1%。
- 已在线将 `stockstrategy-api` 提升到 2 核；cgroup `cpu.max=200000 100000`、Docker `NanoCpus=2000000000`。内存保持 1 GiB；API healthy、镜像未变、8 个挂载不变、无重启/OOM。
- `docker/install.sh`、`docker/deploy-prebuilt.sh`、`docker/rollback-prebuilt.sh` 的 API 创建和恢复 CPU 配额统一为 2 核。实际慢查询/AI 响应尚未重放；只记录资源配置生效，不声称延迟改善。详见 [内存与查询卡顿排查](docs/tasks/2026-10-15_1942_后端API内存与查询卡顿.md)。
## 2026-10-15 19:42 API 内存回收与查询卡顿

- 截图 `stockstrategy-api` 使用 491/512 MiB；在线核验当前镜像 `stockstrategy/backend:20261015144417`，healthy、8 个挂载、RestartCount=0、OOMKilled=false。API CPU 配额为 1 核。
- 调整前 cgroup 为 534,167,552/536,870,912 字节；匿名页约 61 MiB、文件页缓存约 448 MiB；`memory.events max=69,395`，memory PSI 10 秒窗口 `some=4.93% / full=4.51%`。`stock-data.db` 567 MiB、`linkage-operations.db` 343 MiB、`tdx-cache.db` 247 MiB，说明主要是 SQLite 文件页缓存受容器限额挤压，不是 Go 堆泄漏。
- PVE 可用内存约 2,107 MiB；LXC 102 上限 2,560 MiB、可用约 1,782 MiB。已在线 `docker update` 将 API 限额与 MemorySwap 上限调至 1 GiB；容器未重启，镜像、挂载、数据库均未变。
- 调整后容器仍 healthy，Docker stats 566 MiB/1 GiB；cgroup 当前约 703 MiB，其中 file 614 MiB、anon 86 MiB；memory PSI 10 秒窗口约 0.05%，后续 `memory.events max=71,200` 未增加，OOM 为 0。
- `docker/install.sh`、`docker/deploy-prebuilt.sh` 及 `docker/rollback-prebuilt.sh` 的 API 新建/恢复默认同步为 1 GiB。bash -n 与 git diff --check 通过，未构建/发布镜像。
- 20 秒采样曾出现约 18 秒 CPU 97–103%，随后低于 1%；CPU 配额保持 1 核，需在真实慢请求期间继续观察。未触发真实 AI 请求；详见 [内存与查询卡顿排查](docs/tasks/2026-10-15_1942_后端API内存与查询卡顿.md)。
# Easy Stock 环境交接

## 2026-10-15 20:30 统一 AI 对话 Codex 接入候选（尚未生产部署）

- 源码 4154d41：AI 对话与系统设置增加可选桌面 Codex，Web/桌面公共前端同步；独立普通对话队列、HMAC、模型/强度、续聊和取消，不进入策略执行链。默认 Hermes、凭据仍保留原运行时。
- 真实隔离 Web 两轮 Luna/low 对话均 completed，复用原生会话 01a13f7f-c289-7462-8000-42d9eb58cf90 并自动归组。Go 相关回归、Web 25 项、Python 27 项及 Web 生产构建通过。
- 生产 API/Web 仍为原版本，现场 healthy、8/5 挂载，API 1 GiB/2 核；flat base ID 与脚本一致。新 API 需明确批准本次功能层镜像例外，未擅自构建镜像或发布。桌面前端全量检查有既有 LimitUpWorkspace.tsx:283 语法错误，新组件定向检查通过。
- 候选产物、接口、权限、验收边界与发布回退见 [实施记录](docs/tasks/2026-10-15_2030_统一AI对话接入桌面Codex.md)。

## 2026-10-15 19:30 额度恢复后 Web 成功回执补验

- 6d634d36 已补齐实际 Web 研究成功验收：任务 41823961ee42447684b9bc3d36e67376，Codex 会话 01a13f4b-5f5a-7fb0-990c-a22bdbe42f68，实际 Luna/max，精确 symbol=002343.SZ，任务 completed、指令 applied，Web 显示“提案已回传”。
- 新会话由桥自动 grouped，error 为空、attempts=0，官方侧栏读取确认位于“Muse 模拟策略”，无人工移动；中文报告和索引已生成。现金 500000、零持仓，未制造成交。
- 本轮仅验收及文档更新，无代码或部署变更；上轮额度限制下未完成的成功回执补验已完成。测试浏览器的可见性/脚本问题及扩展异常如实记录，未宣称零浏览器异常。详见 [本轮验收记录](docs/tasks/2026-10-15_1930_额度恢复后Web研究成功验收.md)。

## 2026-10-15 17:40 Muse 新会话自动归组

- 独立桥已自动调用已安装 Codex App Tools MCP；新会话持久化登记、自动归组并读取确认，断线/升级连接失效时退避重试，重启继续。动态发现插件/运行时/能力，不固定分组 ID；不修改桌面内部数据库。此前“后续自动归组未实现”已由本轮补齐。
- 24 项测试通过；实际 Web 点击发送产生 f9ab541619dd4ddf9ed0fdb758dbe9b4 / 01a13ed4-a5d5-72f0-b428-10e90b7e26a2，桥自动 grouped 且官方侧栏确认，无人工移动。随后自动任务也自动归组。
- 研究输出 symbol 拼入名称导致校验拒绝，已增加逐任务精确代码/证据枚举约束并空闲更新桥；后续遇 CLI_USAGE_LIMIT，未宣称完整研究成功验收。没有实际升级 Codex；动态发现和连接恢复已测试，未来破坏性接口变化会明确 pending/错误。
- 详细验证、边界与回退见 [自动归组实施记录](docs/tasks/2026-10-15_1740_Muse自动归组与升级兼容.md)。

## 2026-10-15 17:00 Muse 会话识别与研究索引

- 独立桥已空闲更新重启，agent PID 47536，后台 online=true/ready；14 项测试和真实 Luna/low 隔离研究通过。17 个历史/验收会话已重命名并整理到可见“Muse 模拟策略”侧栏分组，17 份中文摘要已生成。
- 新会话绑定固定原生项目，首屏显示代码与模型，标题包含阶段/股票/结果/短 ID。桌面项目注册表尚未显示原生项目，后续自动加入自定义分组仍需适配，不宣称已完成。现场 ATS 已退出、TK 在线，历史 ATS 证据保持明确标记。
- 本轮未更新 Docker/API/Web/worker 或桌面打包，详见 [实施与边界](docs/tasks/2026-10-15_1700_Muse会话归组与研究索引.md)。

## 2026-10-15 15:20 模型每日目录与引擎平滑切换

- 独立桌面桥已更新：香港日期每日首次空闲刷新一次，持久化缓存支持同日重启复用；本地引擎每分钟轻量检查，升级后在任务结束/下次领取前验证并切换。
- 升级验证失败保留有效旧引擎，五分钟退避；引擎/目录不可用时降级并不领取任务。升级事件额外刷新一次模型目录，用户所选模型/推理强度保持原设置。
- 6 项新专项、既有 5 项相关回归、两套已安装引擎的真实协议切换验证通过。部署等待旧任务结束后执行，未修改 API/Web/worker、实际 TK/ATS 或账户。详见 [本轮记录](docs/tasks/2026-10-15_1520_模型每日刷新与引擎平滑切换.md)。

## 2026-10-15 14:58 真实桌面与最新模型选择验收

- 最终 API/Web 发布 `20261015144417`，Web 外置补丁 `20261015145453`，worker `20261015144450`；API/Web healthy、readonly=true、挂载 8/5 个，worker active/running、NRestarts=0。代码/包/镜像哈希与回滚见 [本轮完整记录](docs/tasks/2026-10-15_1458_真实桌面IPC模型与回执修复.md)。
- Web 已提供实际可用模型与推理强度选择、已保存/最近生效值，以及随指令和任务更新的完成/失败回执；修复内部 interval_seconds 混入设置请求导致 API 拒绝。当前最新列表为 GPT-6-Astra、GPT-6-Luna、GPT-6.1-Sol。
- 桥已优先当前桌面现有引擎 0.162.0-alpha.17.2，替代旧 CLI shim 0.157.1 的优先路径；没有安装新运行时。模型/强度按任务冻结并校验 app-server 返回配置。
- 真实 TK/ATS 安装目录 `D:\JohnsonProgram\instockMonitorTK`，活跃 IPC 库按契约定位到 RAMDisk；原节点 WATCHLIST_ADD 既有股验证已由 TK/ATS 双方 synced，故本轮不需重打包。归档库、历史上下文及 quote_status=pending_fetch 不冒充实时就绪。
- 最终生产浏览器任务 `f278da89d26b482db949d225cb11d459` completed，实际 Luna/low、configuration_confirmed=true，真实 ATS/TK connected，信号包含 2026-10-15；设置回执、分析完成提示、820px 和零异常通过。模拟 Enforce 保持开启，现金 500000、零持仓。

## 2026-10-15 14:14 Codex / ATS AI 模拟闭环已部署

- 用户明确批准本次固定 flat base 的 API 功能层例外。最终 API/Web 发布 `20261015140855`，API 源码 `97de300`（闭环功能 `22510f1`）；独立模拟 worker `20261015140000`，桌面/worker 实现提交 `472d583c`。以下旧日期的“尚未部署”是历史状态。
- API 镜像 `stockstrategy/backend:20261015140855`，ID `sha256:76b5571ea6bfcb72953640830c1bcbc229355a466c76f6911756bae73d5e9380`；固定 base ID `sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d`。线上二进制 SHA256 `e254d0cf6ae50b2255dd7cf9b1f77d9a414ad9eb7457eda0d121078157e25e41`。
- Web 复用 `stockstrategy/web:20261011114424`，外置资源发布 `20261015140855`。API/Web 均 healthy、readonly=true，原持久化挂载结构与 8/5 个挂载保留；worker active/running、NRestarts=0，包 SHA256 `2d0176ab19d7601028796b181240a6d36ef4a92d802c896c52f4a75132c90580`。
- 当前用户计划任务 `StockStrategy-CodexATSBridge` Running，独立端口 26776；节点 `codex-bf952db5fd9f615f2a8fff37`、工作区 `ws-c1f09cc351724da6946658c4`。原 JohnsonTriton 节点保留，密钥仅在被忽略的运行目录。已启用 paper AI Enforce，无券商连接。
- 真实生产分析任务 `38b31a865192445cbce2c20071e30e18` completed，Codex 会话 `01a13e30-3cc7-7150-bd08-3db089f5543a`；实际调用市场、逐股和 ATS 工具，10 只提案为 3 observe/7 avoid。桌面 HMAC ready，账户现金 500000、持仓零；市场门禁与过期资金证据阻止新开仓，未制造生产成交或复盘。
- 已修复 Web 登录中间件重复消耗同一 HMAC nonce 导致的 401；认证/linkage 回归、Python 36 项、Linux worker 34 项、实际生产浏览器 AI 展示/820px/零异常通过。合成行情下的真实模型买入→T+1→次日退出→自动复盘验收另见任务文档。
- 最终回滚点 `/mnt/4TB/dockerf/stockstrategy/rollback/20261015140855/COMPLETE` 已观察；该点回到中间候选 `20261015135845`（存在 HMAC 401），完整回退应使用已验证的原稳定点 `20261015013333` 并先停 worker，或将 AI 关闭后按层回退。worker 前版本 `20261015021700`。回退代码不回滚/覆盖账本。
- 仍需真实盘中连续/跨日对账；当前池匹配的 ATS 信号为历史证据，资金源存在日期/时效缺口。详细实现、发布轨迹、操作和后续见 [闭环验收与发布记录](docs/tasks/2026-10-15_1348_CodexATS策略闭环端到端验收与发布.md)。

## 2026-10-15 12:43 本会话代码提交分界

- 已部署版本仍为 API `20261015013333`、Web 外置补丁 `20261015021500`、worker `20261015021700`。本次版本提交不表示重新部署。
- 工作区新增 Codex/ATS AI 协同草案（任务队列、HMAC IPC、app-server 代理、结构化提案与前台互动），尚未部署或完成真实 AI 联调，不应将本次提交 HEAD 视为线上已验收源码。默认 AI 关闭，shadow/enforce 未在线启用。
- 功能清单、版本与包哈希、验证边界、AI 草案状态及后续优先级见 [完整中文交接](docs/tasks/2026-10-15_1243_本会话版本提交与完整交接.md)。

## 2026-10-15 02:15 资金观察与逐股条件计划

- LXC 102 独立模拟 worker 更新为 `20261015021700`（包 SHA256 `2979edc7cb74b0656817a14624efa336fce41b389cdc79d8ad8517fa1aeb4f80`）；外置 Web 补丁 `20261015021500`。沿用部署锁、校验、健康检查与回滚，没有新建镜像、重建 API/Web 容器或改挂载。
- 自动跟单新增“资金轮动 / 计划”：资金覆盖/来源/日期、账户资金分布、逐股 VWAP/MA20/量价及条件应对。只读研究与开仓门禁分离，非交易时段也展示明确标记的参考池。
- 观察到行业 48、题材 181、参考个股 10，10 份日线指标已计算；现金 500000、持仓零。新浪资金缺 trade_date，只作参考，未接入自动资金轮换。Python 24 项在 Windows/Linux 通过，前端相关 10 项通过；浏览器入口/展开/820px 布局及零运行异常通过，尚未盘中连续验证。
- 修复 Go 纳秒时间戳在 Python 3.9 的兼容，并核实/适配本地日线成交量为股的契约，增加成交额/股数价格合理性检查。没有放松行情过期、交易时段、T+1 或风险阈值。
- 部署、哈希、回滚与未完成边界详见 `docs/tasks/2026-10-15_0215_资金观察与逐股条件计划.md`。

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
- 2026-10-11 补充纠正：取消兼容目录复制方案，未执行安装目录写入。根因为 TK 网关绕过 get_conf_path；源码已共用资源释放/更新路径，隔离网关测试 22 项通过（含开发和两种打包路径、自动释放、更新缓存）。现场 EXE 尚未重建，关注保存现场验收仍待完成。

## 2026-10-11 17:49 TK PyInstaller 生产闭环（取代上述待验收状态）

- 按用户授权使用 instock-pyinstall-to-exe.cmd、py_stock_build 环境打包（201 秒），生产构建环境网关 22 项测试通过；实际 EXE 归档核验包含 get_conf_path 修复和证券资源，外置密钥匹配，无密钥记录。
- 生产 TK release 20261011-174350：仅更新 D:\JohnsonProgram\instockMonitorTK\instock_MonitorTK.exe，先关闭旧进程再启动新进程。新 SHA256 22F3801EFAA1407ECFF07A9FAE96D935CD7F33C705D2B5BA50702C6908F20A20；旧 EXE 及 release.json 保存在同安装目录 release-backups/tk-linkage-20261011-174350。配置、数据和交易开关保持既有值。
- 真实原始配置导入 connected；网页查询200；错误HMAC、nonce重放、越权、跨源请求401。操作 acceptance-684dd758ae4d40a3a9af38136f4ebf53（已有自选000002.SZ）applied、persisted=true、revision=1、TK/ATS=synced；幂等重放通过。
- 生产浏览器前端600733北汽蓝谷关注操作39414d13822e4a315306dfe30c12eac5：persisted=true、revision=2、TK/ATS=synced，页面显示已在关注及双端synced；非交易时段最终回执行情market_closed。不以缺行情伪装实时正常，未触发交易。
- TK读取根目录stock_codes.conf，未创建JSONData副本。API/Web镜像与本节上方Go发布相同且healthy。真实证券联网自动更新未强制执行；隔离测试已覆盖自动释放和更新缓存失效。

## 2026-10-12 00:32 TK/Go 自助接入同源鉴权修复部署

- 发布 `20261012003209`，目标源码 SHA `71a77b76230c9bdd0c8baf0e301fe8f2cc60e272`（包含 Go/Web 鉴权一致性修复 `63a5630c49835139cc2d8274aa7a51cf4198d222`）。根因为浏览器导入直接请求保存的 Go `:20081`，页面来自 Web `:20073`，无令牌策略将两者判定为跨源；TK `hmac_key` 是后续 HMAC 凭据，不是 Go 管理令牌。导入现改走同主机 Web `/api` 网关，同时保留 Go `backend_base_url`；Vite 开发代理保留 Host/Origin 一致。
- API 镜像 `stockstrategy/backend:20261012003209`，ID `sha256:83dd32c9995bf04aacec60eb5146f534a92d2dbf9621d2d8255d7cf26ce0b2f6`，2 层、119,365,092 字节。Web 仍为 `stockstrategy/web:20261011114424`，ID `sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9`，11 层、62,396,647 字节。
- API/Web 均 `healthy`、重启策略 `always`、只读根文件系统；`SizeRw=0`，根文件系统分别 119,365,092/62,396,647 字节。外置挂载数仍为 API 8、Web 5：保留 `/data`、`/logs`、交易日历、行情任务、InStock 只读行情；Web 静态文件位于 `/mnt/4TB/dockerf/stockstrategy/app/web-dist/20261012003209`，`/tmp`、`/run`、Web `/var/cache` 使用该 release 的外置 runtime。
- 生产只读验收：Web 代理及 LAN 入口 `/api/health` 正常；无令牌同源 targets/context/events/attention 均返回 200；跨源 targets/import/commands 返回 401；同源 malformed import/commands 分别返回 400，malformed attention identity 返回 403，均未写数据。targets 读回已有节点 `tk-eac80a9aa66a462795557e68`/workspace `ws-b33bb748186a4bbc8e69ab72`，API 标记 `configured` 仅证明持久注册，不代表本次在线握手。测试包括配置令牌时错误 Bearer/X-A-Stock-Token 拒绝、无令牌来源边界、Web 同主机跨端口经同源代理；Go `go test ./...`、Web 34 文件/183 测试及 `tsc -b && vite build` 通过。
- 回滚快照 `/mnt/4TB/dockerf/stockstrategy/rollback/20261012003209` 的 `COMPLETE` 存在且全部 `SHA256SUMS` 校验通过。回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261012003209`。
- 这次部署证明鉴权路径已修复。Windows 剪贴板未包含 TK 配置行，所以本次未重新导入/更新已有目标，也未修改 TK 或执行交易；本次发布不能据此宣称新的 HMAC configure/connected 现场验收。取得安全配置输入后，可按现有页面重新握手，并验证关注命令回执与幂等。

## 2026-10-13 14:52 页面用户认证部署与验收

- 按手册第9节从干净隔离副本发布20261013144813；审核源码SHA=e316aaa900ab55104b99e2368cdff381a539a945，本次12个变更文件与生产源码逐项SHA256一致，未推送远程。固定base、锁、隔离smoke、健康及回滚门禁全部执行。
- API镜像stockstrategy/backend:20261013144813，ID=sha256:48c92a4e0b858df7d767a459f8f9cf501cc78efbb01d7c6e7558ca58b41d0143，2层、119406052字节。固定base仍为flatbase-20261010171545 / sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d（1层）。
- Web复用stockstrategy/web:20261011114424，ID=sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9，11层、62396647字节。两个镜像RepoDigests均为空。API/Web app-version均为20261013144813，healthy、always、ReadonlyRootfs=true、SizeRw=0，SizeRootFs分别119406052/62396647。
- API8个/Web5个bind挂载，保留既有数据、日志、只读InStock行情、日历及cron路径；runtime及Web静态目录切换至本release，资源index-B9egOyWT.js。API健康、Web代理健康、容器Web→API健康、nginx -t通过。
- 新增认证库/data/easy-stock/web-users.db，外置路径/mnt/4TB/dockerf/stockstrategy/data/easy-stock/web-users.db，权限600、20480字节。默认管理员johnson按用户提供密码首次初始化；未添加测试用户、未修改已有密码、未触发交易。
- 当前Windows网络通过真实域名http://johnsonhongyi.asuscomm.com:29988验收：匿名lan=false、业务接口401；登录200、管理员用户列表200、业务接口200；退出后业务接口401。内网http://192.168.50.60:20073匿名lan=true、业务接口200。Cookie核验HttpOnly、SameSite=Strict。
- 外网共享Token不再绕过登录，Web启动/发布脚本不再注入VITE_A_STOCK_TOKEN；线上没有非空A_STOCK_TOKEN，无当前令牌需轮换。HMAC桌面协议独立保留。
- 回滚快照/mnt/4TB/dockerf/stockstrategy/rollback/20261013144813：COMPLETE存在，全部SHA256SUMS通过。回滚：bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261013144813。恢复原API20261012003209及旧Web运行配置，保留外置数据库；回滚到旧版会恢复旧版外网访问策略，应先限制公网入口。
- 首次20261013144422在切换容器前被发布说明标签门禁拦截；旧容器一直健康，源码自动恢复、快照校验通过。统一镜像标签写入使用RELEASE_NOTE后，从同一SHA完整重跑成功。
- 脚本SHA256：build-and-deploy.ps1=027e37dc038222ab04b12a21f91cd606293f0fe92198182aee51053f9718628d；deploy-prebuilt.sh=d106077d7ff659eb8d411be72cc9582d6f847a10058f09fbb0b34d2987dc5062；rollback-prebuilt.sh=3042d53d5a7040efb670e3e944c1c76c3ede3a19b19b6b685262844785315c37。
- 未验范围：用户指定入口为HTTP，密码传输未加密；公网独立设备未专项验证。浏览器工具内核因EISDIR启动失败，未将浏览器点击/视觉布局记为已验收。

## 2026-10-15 独立 A 股自动跟单模拟 worker

- 用户明确授权在 LXC 102 与 Muse 并行独立模拟。新增 systemd `stockstrategy-auto-follow.service`，发布 `20261015000500`，active/running、enabled，复核 NRestarts=0；非交易时段等待，无实盘接口、无模拟成交验收。
- 代码 `/mnt/4TB/dockerf/stockstrategy/auto-follow/releases/20261015000500`，current 链接指向该版；包 SHA256 `033d4235c22faae8fd23341d680ad3439c0855c653deb6bcf74a07cbb745ccbd`，9 项文件 SHA256 校验通过，COMPLETE 存在。线上 source 不含 Git 元数据，本次不宣称核验到应用 Git SHA。
- 独立账本 `/mnt/4TB/dockerf/stockstrategy/data/auto-follow/account.db`（SQLite integrity_check=ok，paper，50 万现金，持仓/平仓 0），HTTP 缓存同目录 http-cache.db，日志为外置 logs/service/auto-follow.log；不覆盖 Muse 原账本或共享行情库。
- LXC Python 3.9.2 未装 PyYAML；采用本地 v1.9 无密钥参数快照和必要标准库模块，不升级环境。盘中情绪走 Go emotion-history 原生状态/风险门，不将其伪装为 Muse 分数；行情仍需 P8/P25 确认。共享交易日日历读取原外置 config。
- 内网 API 经 `http://192.168.50.60:20073`；端口只绑定该 LAN 地址，127.0.0.1 不可达。健康、情绪与报价字段只读探针通过；已验证行情有 trade_time/source/stale 等字段，盘中新鲜度与成交须交易时段继续验收。
- 本地及线上 13 项隔离测试通过。API 仍为 backend:20261013144813、Web 为 web:20261011114424，均 healthy、根文件系统只读；没有新建镜像、重启原容器或修改 cron。发布文件权限已收紧为 0644，账户目录 0700。
- 首版停用/回撤：`systemctl disable --now stockstrategy-auto-follow.service`，保留独立账户与原生产数据。后续更新使用 deploy-auto-follow.sh 的部署锁、SHA256、隔离测试、健康检查与失败恢复，不回滚账本。
- 实施与限制见 [任务记录](docs/tasks/2026-10-14_2355_自动跟单模拟盘规划与实施.md)；最新版 Muse 来源手册保留，本地差异见 [审核记录](docs/engineering/muse-2026-10-14-local-audit.md)。

## 2026-10-15 自动跟单控制台完整发布

- 用户明确授权部署及本次镜像例外。按 build-and-deploy.ps1 -AllowLayeredImageBuild 发布 `20261015013333`，API 从已核验固定 flat base 构建，2 层、119426532 字节，ID `sha256:3004cb440dd5b0285a7741a93ead8ad9c581824f201289fd3aba18f0fafd2100`；Web 复用 web:20261011114424。API/Web healthy、ReadonlyRootfs=true，8/5 个原 bind mounts 保持。
- 新增侧栏“自动跟单”，入口 `http://192.168.50.60:20073/#auto-follow`；状态 API 与控制队列经过原鉴权，支持跟随范围、强势股原因、模拟持仓/成交、日志、暂停/恢复及回执。worker 更新为 `20261015012500` / paper-follow-console-v2，active、NRestarts=0。
- 独立账户目录 root:10001、2770，account.db/control.db 等 0660；Go 只写独立控制库，worker 单写账户。模拟现金 500000、持仓/平仓 0、enabled=true、kill=false，两库 integrity_check=ok；备份 `/mnt/4TB/dockerf/stockstrategy/auto-follow/backups/20261015013214/account.db`。没有接实盘、覆盖 Muse 原账本或改变行情/风控参数。
- 线上 17 项 worker 隔离测试通过；本地 API/原鉴权回归与前端测试通过。真实浏览器验收发现并修复 HTTP crypto.randomUUID 不可用问题，补测后前端共 8 项通过。Web 修补 `20261015014500` 使用原有外置静态挂载、部署锁与原子入口切换，无二次镜像构建或容器重启，旧资源保留。
- 最终 Edge 无头浏览器实际点击五个视图、暂停→回执→恢复通过，820px 宽度检查通过，捕获运行异常 0。API 幂等、非法指令 400、跨源拒绝和匿名公网来源 401 通过；现金/持仓未变。IAB/Chrome 工具内核仍有 EISDIR，改用独立临时 Edge 配置完成验收，不读取个人浏览器资料。
- 程序 SHA256 `2e1ef4159939f2c24cc03429803a993eaeeccde30360aa2441a3fa486fdec7b9`；Web 最终 index SHA256 `f659273f1faba3337de9a138ce774184b2b6bedbfb4e464cd794764f095043bf`，资源 `index-DbLS3fwf.js`。镜像标签表示构建时状态，Web 外置修补以文件哈希/补丁记录识别，不能用镜像标签冒充当前 Web 代码 SHA。
- 主回滚快照 rollback/20261015013333 COMPLETE 存在且 SHA256SUMS 通过；整体回撤先停止模拟 worker，再运行 `bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261015013333`，不回滚账户数据。Web 补丁备份在 auto-follow/web-hotfix/20261015014500；详细包哈希、回撤限制与验收见 [任务记录](docs/tasks/2026-10-15_0105_自动跟单控制台闭环.md)。
- 当前夜间无候选/成交，不代表盘中已验收；仍需盘中核验信号、行情新鲜度、跨日退出与长期稳定性。公网独立设备未专项验证。未提交/推送代码。
