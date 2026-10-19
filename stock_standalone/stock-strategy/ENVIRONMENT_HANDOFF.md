## 2026-10-19 01:48 研究记录模型与强度分栏

- 用户授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布，发布号 `20261019014846`；部署脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261019014846`。
- TypeScript 检查与 Vite 生产构建通过；部署后 `/api/health` 返回 `ok=true`，个股分析 JS/CSS 分包均 HTTP 200，资源确认包含独立模型/强度标签和通用 ID 后缀规范化。
- 历史卡片显示基础模型 ID 与单独的推理强度标签；若模型 ID 以记录中的同一强度后缀结尾，动态移除该后缀，筛选及去重按基础模型 ID + 强度匹配。Antigravity 执行时仍按 CLI 目录中的具体变体 ID 调用；未触发新的研究或交易。

## 2026-10-19 00:57 研究差异速览适配研究目的

- 用户授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布，发布号 `20261019005716`；部署脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261019005716`。
- TypeScript 与 Vite 生产构建通过；部署后 `/api/health` 返回 `ok=true`，个股分析分包 `StockAIAnalysisWorkspace-qMhCDXVC.js` 和样式 `StockAIAnalysisWorkspace-C-VnVF5n.css` 均 HTTP 200，资源包含差异速览、限量标色与“观察重点”分支。
- 速览卡片按研究目的展示观察重点、新仓建议或持仓建议；未发起真实模型研究或交易。

## 2026-10-19 00:52 研究记录差异标注优化

- 用户授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布 Web/API，发布号 `20261019005229`；部署脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261019005229`。
- TypeScript 检查与 Vite 生产构建通过；部署后 `/api/health` 返回 `ok=true`，首页、`StockAIAnalysisWorkspace-T0jakefx.js` 与 `StockAIAnalysisWorkspace-C-VnVF5n.css` 均 HTTP 200。线上资源确认包含“主要结论速览”、有限差异标注和模型配色样式。
- 差异页新增按模型色条排列的结论/建议速览；仅结论、判断、建议与价格条件行使用模型色短语标注，每格最多 48 字符、最多 3 段；长篇证据和来源不着色，输入/截止时间移至表格末尾。未发起真实模型研究或交易。

## 2026-10-19 00:26 研究记录同股模型差异对比部署

- 用户明确授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布 Web/API，发布号 `20261019002636`；脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261019002636`。
- TypeScript 检查、Vite 生产构建通过；部署后 `/api/health` 为 `ok=true`，首页、主 JS `index-CUZ-jwTB.js` 和个股分析分包 `StockAIAnalysisWorkspace-Bckmalmr.js` 均 HTTP 200。分包含同股勾选、差异表、总耗时最快标记及证据覆盖信息。
- 研究记录支持勾选同一股票 2–4 条已完成报告，只呈现不同的研判项目，并提示研究输入/快照差异。未发起真实模型研究或交易。

## 2026-10-19 00:09 个股研究记录模型/推理强度筛选部署

- 用户授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布 Web/API，发布号 `20261019000901`；脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261019000901`。
- 本地 TypeScript 检查与 Vite 生产构建通过；部署后 `/api/health` 返回 `ok=true`，首页、主 JS `index-DCopkiPn.js` 和个股分析分包 `StockAIAnalysisWorkspace-C85EL9CA.js` 均 HTTP 200。分包含模型/推理强度筛选与去重提示文本。
- 研究记录可按模型/推理强度组合查看；同一股票同一配置仅显示最新记录，原始历史数据未删除。未触发真实模型研究或交易。

## 2026-10-18 23:36 AGV 回调修复与账号菜单发布（实机模型待验）

- 用户授权后按 `build-and-deploy.ps1 -AllowLayeredImageBuild` 发布 Web/API，发布号 `20261018232904`，部署脚本返回 `Deployment healthy`。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261018232904`。
- 绕过本机无效代理直连核验：`/api/health`、Web 首页、`index-DdmL7TDO.js`、`StockAIAnalysisWorkspace-Kapl9FNP.js` 均 HTTP 200；前端 bundle 含 `stock-open-account-manager`、`账号管理` 和 Codex/Antigravity 独立桥标签。账号入口随系统设置展示。
- 用户手动启动管理器后，当前 `agv-59333f82b2a74c0363cd3ede / ws-b33bb748186a4bbc8e69ab72` 在线/ready；本机 AGV bridge PID `34348` 存活，监听端口 `26778`。线上名录返回 `chat_queued=0`、`chat_running=0`；旧节点 `agv-7a8969d8 / ws-c1f09cc3` 仍心跳过期。未重复重启 worker。
- 本次没有发起真实 AGY 模型调用。UUID conversation_id、进度回执和错误包装修复已有离线回归，但 `CLI_OUTPUT_CALLBACK_FAILED` 是否在真实 Gemini 对话中消失，及真实流式输出/耗时，仍需由一次受控对话验证；不代表模型速度已验证。
## 2026-10-18 23:17 AGV 对话回调错误闭环修复（待实机）

- `CLI_OUTPUT_CALLBACK_FAILED` 的直接根因已定位：AGV 在模型完成会话初始化前发送了非 UUID 的 `thread_id=chat-<job>`；后台 `chat_result` 校验拒绝该进度回执（`CHAT_INVALID_THREAD`），`ProgressPublisher` 记录 400 后，下一次 stdout 回调因 `publish()` 检查失败被有界运行器包装成 `CLI_OUTPUT_CALLBACK_FAILED`。
- AGV 现从 AGY `init` / `step_update` / `result` 读取并校验真实 `conversation_id`，初始化前不发送 thread_id；最终结果也使用该 UUID，并回传 `reasoning_effort`，满足后台会话字段校验。回调错误日志/失败码保留底层 peer 错误，个股研究失败前缀按 Codex / Antigravity provider 区分。
- 离线验证：AGV/桥运行时 Python 19 项通过，CLI bounded runner 12 项通过；Go `internal/httpapi` 与 `internal/stockanalysis` 测试通过。尚未部署该 Go 提示修正，也未重启桌面 AGV worker；未发起真实 AGY 请求或交易，需发布并在受控任务上完成实机闭环。

## 2026-10-18 22:50 双桥模型偏好修复部署

- 按既有授权执行 `build-and-deploy.ps1 -AllowLayeredImageBuild`，发布号 `20261018225043`；脚本返回 `Deployment healthy`。部署后只读核验 Web 首页 HTTP 200，`StockAIAnalysisWorkspace-CMwd1dIU.js` HTTP 200，bundle 同时包含 Codex 与 Antigravity 独立偏好键。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261018225043`。
- Web 模型、推理强度与桥节点按 provider 分开写入本地存储；保留旧 `easy-stock.stock-ai-model.v1` 的匹配 provider 迁移，并阻止另一桥的默认模型/强度覆盖当前选择。
- AGV worker 的源码修复不在 Web/API 发布包内：进度载荷改为 Codex 同契约并使用 `chat_result`/租约令牌；AGY stream-json 使用限时有界进程、标准 `step_update`/`result` 解析、独立 stderr 排空、`--effort` 参数，策略格式错误不再伪装成已完成 WATCH。尚未重启本机 AGV worker，也未进行真实模型调用；需管理器重新启动该 worker 后再做实机验收。
- 回归：Web 46 个测试文件、235 项通过，生产构建通过；AGV/桥运行时 Python 17 项与 CLI 安全测试 12 项通过。测试均使用模拟流或离线进程，不触发模型请求或交易。

## 2026-10-18 22:16 Web 双桥适配部署

- 按用户要求执行 `build-and-deploy.ps1 -AllowLayeredImageBuild`，发布号 `20261018221610`。SSH 指纹、API/Web 健康、重启策略与磁盘预检通过；Go 后端与 `easy-stock-web` 前端构建通过；远端隔离 API smoke、Web/API 健康门禁通过，脚本返回 `Deployment healthy`。
- 上线后只读核验：API health HTTP 200，Web 首页和 `StockAIAnalysisWorkspace-Bo5-ML1I.js` HTTP 200；当前前端资源包含 Antigravity 选项和 provider 字段。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261018221610`。
- HMAC 后台名录将 `agv-*` 标为 `antigravity_desktop`、`codex-*` 标为 `codex_desktop`。截至 2026-10-18 22:28 HKT，`agv-59333f82b2a74c0363cd3ede / ws-b33bb748186a4bbc8e69ab72` 与 `codex-411ad92cc5ef25a8efbc8e82 / ws-b33bb748186a4bbc8e69ab72` 均在线/ready、队列 0/0；精确运行时查询分别返回 Gemini 与 GPT 模型目录。`agv-7a8969d81fd3f3f924cb1294 / ws-c1f09cc351724da6946658c4` 和 `codex-bf952db5fd9f615f2a8fff37 / ws-c1f09cc351724da6946658c4` 为心跳过期节点，工作区不同。
- 用户截图中的 502/超时发生在发布切换时段，当前 API health 与两个活动节点的只读查询均已恢复。截图中的 `No module named 'ats'` 属 17:29 历史日志；当前本机 `agv-7a89…` 仍未运行。本次发布没有重建桌面管理器 EXE，也没有对该节点发起启动。

## 2026-10-18 02:10 Web 20073 按 inStock 方式发布

- 用户明确授权把 20073 调整为与 inStock 相同的全 IPv4 地址发布；已由 `192.168.50.60:20073 → 80/tcp` 改为 `0.0.0.0:20073 → 80/tcp`。Windows 访问 `http://192.168.1.60:20073/`、`http://192.168.50.60:20073/` 均为 200；LXC 内两个地址的根页内容 SHA256 一致，`/api/health` 均 200。
- 通过 PVE `pct exec 102`，持有既有 `/run/lock/stockstrategy-deploy.lock`，仅重建 stockstrategy-web 的端口发布。新容器 a486650a6107；原 image ID `sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9`、应用版本 20261017034210、全部 Config、5 个挂载、只读根文件系统、SizeRw=0、always 重启策略及资源/网络配置保持；stockstrategy-api 身份和健康保持。
- 本地 `docker/install.sh`、`docker/deploy-prebuilt.sh` 与 LXC 安装模板已改为 `-p 20073:80`；未构建或更新镜像、未修改数据或交易行为。
- 旧容器 `stockstrategy-web-before-dual20073-20261018-020949` 保留为停止状态、restart=no。LXC 回滚：`sh /mnt/4TB/dockerf/stockstrategy/backups/dual-web-bindings-20261018-020949/rollback.sh`，恢复旧容器与安装模板，因此也会恢复旧的单地址绑定。报告只记录端口/镜像/挂载等元数据，不保存完整环境变量。

## 2026-10-16 打包入口核对

- 用户实际使用 `D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\instock-pyinstall-batch.cmd 7`。菜单 7 映射到管理器，调用 `C:\Users\Johnson\instock-pyinstall-manage-exe.cmd`；本机该闭环脚本在 `stock_standalone` 目录执行 `pyinstaller manage_window_layout.spec`，目标文件为 `dist\manage_window_layout.exe`，并在打包前后调用归档脚本。
- 默认 `manage_window_layout.spec` 已包含桥管理器、worker、对话和 `muse_research_threads` 的 hidden imports；与版本化 v5 spec 功能配置相同。版本化 spec 的 `name` 会生成不同 EXE 名，闭环脚本没有引用它。因此手动打包继续用默认 spec；v5 仅是此前并排版本配置副本，v4 是中间文件。
- 管理脚本设置的 `TEMP/TMP=C:\Temp` 仅作用于构建时。spec 使用 `runtime_tmpdir=None`，EXE 运行时的 `_MEI...` 解包路径由启动环境决定；本次源码修复是让 Codex 项目目录基于 EXE 路径，而不是把运行时解包目录改到 C 盘。源码修复还需用户通过默认闭环脚本重新打包后验收。

## 2026-10-16 21:30 后续打包源代码修复（尚未打包/部署）

- 用户在手动重打包后报告 Web 对话阶段 `OSError: 函数不正确`，路径指向 `G:\Temp\_MEI263162`。已修正 `muse_research_threads.py`：PyInstaller/Nuitka 打包运行时从 `sys.executable` 定位管理器安装目录，再使用稳定的 `stock-strategy\muse-research` 项目目录；源码开发运行仍从源码位置取根目录。此修复针对临时解包目录路径，不代表已验证所有 RAMDisk/权限场景。
- 管理器状态误把复用中的 `bridge.pid`（曾指向无关 `node.exe`）报告为桥运行。现在必须同时匹配活动状态并核验进程身份；桥退出时清理自己写入的 PID 文件。
- 桌面聊天/桥接端补充 Web 对话进度阶段、Codex 过期 thread 新建会话回退、终态结果本机缓存与回执重试/重放、检测会话归档与本地测试记录清理、心跳先落本机、停止请求可中断重试等待，以及包含阶段/操作/HTTP/WinError/errno/路径的诊断日志。管理器显示后台桥名录、友好错误和日志，并采集独立 worker 输出。
- 当前改动只在工作区源代码和 v5 手动打包 spec；没有重建或部署 EXE，也没有重新启动管理器/桌面桥。用户负责手动打包并测试。Python 语法检查和 `git diff --check` 已通过，未运行测试套件。
- Web/API 的历史部署记录仍按各自时间保留。Web 桥下拉仍可能显示旧 Codex 登记项：本 checkout 没有对应 Web/API 源码，未删除后端登记，也未在本次代码中声称解决该列表清理。

## 2026-10-16 17:29 桌面桥回执幂等、日志诊断与打包桥闭环已部署

- API/Web 发布 `20261016171738`，隔离发布源码提交 `da9bad51f097b92f2b3eef2a8c891165bd1eb1dc`；部署脚本 health、隔离 smoke 与上线门禁通过。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261016171738`。
- 后端终态回执支持同一租约/相同结果幂等重试；`result_writeback` 暂留 15 秒租约，未写回时桥可快速重领本机缓存成功结果。测试任务的终态 GET 不再立即删除，Web 客户端收到终态后通过 DELETE 确认清理，避免丢包后重查 404。
- Web 桥测试展示本机引擎启动、会话建立、Codex 回复和结果写回阶段及等待时长；成功/失败终态后清理临时 Web job/session。
- 桥日志记录阶段、操作、HTTP 状态、errno/WinError、原因、后端地址或本机路径；管理器把常见网络/文件错误映射为中文说明并捕获打包桥启动输出。心跳支持 Go RFC3339Nano 与 epoch 秒/毫秒/微秒/纳秒，兼容 Python 3.9，显示本地时间和相对时长。
- 管理器 v5 并排安装：`D:\JohnsonProgram\instockMonitorTK\manage_window_layout.bridge-closed-loop-20261016-v5.exe`，46,318,047 字节，SHA256 `9107CC9974DCD3754D5A1EA4ADD571574FA727925956552E46F7317217341F9E`。当前运行 worker PID `26572`，可执行文件为 v5；身份 `411ad92c / b33bb748`，在线/ready，后台运行/排队 `0/0`。旧管理器 UI 未强制关闭；需打开 v5 管理器查看新的日志格式，已安装的 v4 是时间解析修正前的中间包，不要用于查看时间。
- 生产 Web→API→打包 v5 桥→Codex→回执闭环通过：固定标记 `CODEX_BRIDGE_OK`，`gpt-6-luna / max`，10.7 秒；随后 DELETE 清理了 Web 测试 job/session，后台队列归零。Codex 测试 thread 保留在桌面 Codex 历史。API health、Web 根页和 SettingsDrawer/AIChatWorkspace 资源均 HTTP 200。未调用市场工具或交易。
- 未运行测试套件；Python 语法检查和部署构建通过。历史 OSError 日志没有 errno/路径，无法事后还原具体根因；之后的新异常会带操作阶段和系统错误详情。

## 2026-10-16 14:12 桌面桥自动切换、全链路检测与后台计数已部署

- 发布号 `20261016141223`，隔离发布源码 SHA `d36092d3cb0d2c7d375a211b29fa861442824f66`；部署脚本返回 `Deployment healthy`。回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261016141223`。
- API 设置与 AI 对话页现按新鲜心跳和可用模型筛选所有登记桥；仍在线时保持原桥，离线时优先默认 ATS 工作区的活跃桥，否则选其他活跃桥。对话页每 30 秒轻量复核，自动保存切换并提示桥短标识；不重置输入状态。
- API 设置新增“测试桌面桥全链路”：只对当前选择的桥提交固定 `CODEX_BRIDGE_OK` 检测，显示后端排队、桥领取、Codex 回复和回执阶段；Web 侧测试任务/会话记录在终态读取后清理；新建的 Codex 测试 thread 和桌面管理器本地结果历史会保留。测试不改已保存配置，也不调用市场工具；页面提示会占用一次 Codex 调用。本次没有点击真实测试按钮。
- 管理器名录显示所有登记桥及有效运行/排队数，过期租约不计入；修正名录表格为 5 列。新版管理器 `D:\JohnsonProgram\instockMonitorTK\manage_window_layout.bridge-inventory-20261016-v2.exe`，SHA256 `0f5efb11b9d375363c37b765a44ccdd82d9c5bfe4488aefdc5aae364ec8a823a`，46,310,520 字节。旧 EXE 未覆盖；本轮未主动停止这 4 个运行进程。
- 只读验收：API health、Web、SettingsDrawer、AIChatWorkspace 资源均 HTTP 200；HMAC 名录返回 3 个桥。Web 对话 `411ad92c/b33bb748` 为在线/ready，后台运行/排队均 0；策略桥 `bf952db5/c1f09cc3` 心跳已过期，默认联动桥 `eac80a9a/b33bb748` 无心跳。
- TypeScript 检查和 Vite 生产构建通过，PyInstaller 管理器构建与 SHA256 校验通过。未运行真实 Codex 对话/桥全链路测试，未更改策略桥选择，未重启 TK/ATS，未操作模拟账户或交易账本。

## 2026-10-16 13:28 桥名录与管理器对齐 UI 已部署

- Go/Web 发布号 20261016132815，隔离发布源码 SHA 7568387bcfe50206dd4efbc4f4af15ea4c03d3d2。部署脚本返回 Deployment healthy；API 地址 http://192.168.50.60:20073，回滚命令：bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261016132815。
- 后端只读桥名录允许已登记桥使用无查询参数、无请求体的 HMAC GET；列出全部后台桥、90 秒心跳状态、Web 对话目标、策略研究目标和默认联动节点。其他读写权限未变。Web 桥选择项统一为 Codex · 节点短 ID / 工作区短 ID。
- 部署后只读 HMAC 核验返回 3 个后台桥。当前 Web 对话为 codex-411ad92c / ws-b33bb748（在线、ready）；策略研究为 codex-bf952db5 / ws-c1f09cc3（在线、ready）；默认联动为 JohnsonTriton / tk-eac80a9a / ws-b33bb748（名录中无心跳）。本机打包桥身份与 Web 对话目标一致。
- API health、Web 根路径及 SettingsDrawer、AutoFollowWorkspace 静态资源均 HTTP 200。TypeScript 检查、Vite 生产构建和部署脚本隔离 API smoke 通过；未运行真实 Codex 对话或策略任务。
- 管理器包已构建并校验 SHA256：b3082b2c1d72815f5e1e650418b589575c5047ce00d46a53ac37b87be1c9d16f，46,308,749 字节。新版并排放在 D:\JohnsonProgram\instockMonitorTK\manage_window_layout.bridge-inventory-20261016.exe；旧版仍被 4 个进程占用，没有覆盖或停止这些进程。需启动新版主程序后，在 Codex 桌面桥管理器中打开“后台桥名录”标签。
- 此前计划任务 StockStrategy-CodexATSBridge 使用开发桥 codex-bf952db5fd9f615f2a8fff37 / ws-c1f09cc351724da6946658c4；Web 选中的安装版管理器桥为 codex-411ad92cc5ef25a8efbc8e82 / ws-b33bb748186a4bbc8e69ab72。之前重启命中开发桥，不是安装版桥。此后以 node_id 和 workspace_id 成对核对。
- 本轮未重启 TK/ATS、未停止桥进程、未更改 Web/策略/default 桥设置，也未发送 AI 任务或触碰模拟账户与交易账本。

## 2026-10-16 12:45 AI 桌面桥自适应与对话恢复部署

- 用户明确要求按部署手册部署。Go/Web 发布源码 SHA `75981727b03e7d9404b77f39cae00a26d9da80c6`（隔离干净发布分支 `codex/ai-chat-bridge-auto-release-20261016`），固定 API base `stockstrategy/backend:flatbase-20261010171545`，base ID `sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d`。
- 发布号 `20261016124537`。API 镜像 `stockstrategy/backend:20261016124537`，ID `sha256:ad0ce585e30d3d3a8a05e266e6c826086d365e77e1321fe70173fc5f8b9abab1`，119,504,356 字节、2 层；Web 沿用 `stockstrategy/web:20261011114424`，ID `sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9`，62,396,647 字节、11 层。
- 部署前 SSH 指纹、API/Web health、always 重启策略及资源预检通过；可用内存 1,911,348 KiB，数据盘剩余 574,521,304 KiB，Docker 盘剩余 4,619,424 KiB。Go 编译、集成 Web `npm ci` / `tsc -b` / Vite 构建通过，远端隔离 API smoke 通过。
- 上线后 API/Web 均 `healthy`、重启策略 `always`、`ReadOnlyRootfs=true`、`SizeRw=0`；挂载仍为 8/5。API/Web→API health 返回 `ok=true`，Web 根路径 HTTP 200，`AIChatWorkspace-BibFBvpp.js` HTTP 200。回滚快照 `/mnt/4TB/dockerf/stockstrategy/rollback/20261016124537/COMPLETE` 存在且 `SHA256SUMS` 全部通过；回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261016124537`。
- 身份区分：计划任务 StockStrategy-CodexATSBridge 使用开发桥 codex-bf952db5fd9f615f2a8fff37 / ws-c1f09cc351724da6946658c4；安装版管理器桥为 codex-411ad92cc5ef25a8efbc8e82 / ws-b33bb748186a4bbc8e69ab72。此前重启命中开发桥，不是 Web 当前选中的打包桥。确认队列空闲后，仅重启该任务；停止检查时有新任务并发领取，等待它完成后通过 `stop.request` 正常退出，未中断任务。任务现为 `Running`，单桥/单 agent，状态 `ready`；节点 `codex-bf952db5fd9f615f2a8fff37`、工作区 `ws-c1f09cc351724da6946658c4` 保持不变，模型目录 3 项、`catalog_day=2026-10-16`，引擎路径 `C:\Users\Johnson\AppData\Local\OpenAI\Codex\bin\9614f1d9b40d9c4f\codex.exe`。桥按现有注册流程重新注册，标签代码包含节点与工作区 ID。
- 没有重启 TK/ATS，没有执行真实 Codex 对话、个股研究或交易；仅执行部署 smoke、健康和静态资源只读验收。外置行情库、模拟账户与交易账本未改。
## 2026-10-15 23:24 个股 AI 模型偏好恢复修复已部署

- 修复研究记录恢复时把历史任务的 `ai_provider/model/reasoning_effort` 覆盖当前选择的问题；模型选择仍在点击时写入浏览器 `localStorage`，历史任务只恢复股票、用途、周期和分析深度。
- 前端 TypeScript 检查及 Vite 生产构建通过。Web 外置静态补丁 `20261015232159` 已原子替换入口；发布前旧 index SHA256 `78f4b74875a161f28dc19513bb22b1cc45afdc6525f3eb0fff5ba792333439ad`，上线后本地和 HTTP index SHA256 均为 `1200793047462ac23f9088984a844910bfb7110255f4a3f532874905101c050f`。新个股分析资源 `StockAIAnalysisWorkspace-BIso3zX7.js` 可正常读取。
- 回滚入口备份和 `COMPLETE` 位于 `/mnt/4TB/dockerf/stockstrategy/auto-follow/web-hotfix/20261015232159`；静态资源目录仍为 `/mnt/4TB/dockerf/stockstrategy/app/web-dist/20261015224710`。API/Web 镜像未变，均 healthy、只读根文件系统、`SizeRw=0`，挂载保持 8/5；未重启容器、未改数据库或模拟账户。未执行浏览器交互验收，待用户刷新后确认选择恢复。

## 2026-10-15 22:54 个股 AI Codex 模型与字体设置已部署

- 用户授权审核通过后部署。源码提交 `6e81720f88c313528215df70c3677c0300402851`；发布号 `20261015224710`。
- Go 编译、集成 Web 的 TypeScript/Vite 生产构建、隔离 API health smoke、线上 API/Web 健康检查及 Web→API health 检查通过。
- API 镜像 `stockstrategy/backend:20261015224710`，ID `sha256:a520cd6d97e1d7b1c6f0a6b2b5a31d87dcee4bc42ece7cfe639c7968b15f36e7`，119,516,644 字节、2 层；固定 base ID `sha256:ed8cbe9544efbcd5f4a50039b79884d43d1d2b662dc9ee6715325c1525d52d6d`、1 层。
- Web 沿用 `stockstrategy/web:20261011114424`（ID `sha256:ce15ecc17364a415c3a4e609a2858b046af4f3bc9f1058c33bdfaf13b1bb07e9`，62,396,647 字节、11 层），静态资源更新到本次发布。API/Web healthy、只读根文件系统、容器写层 0；挂载数量保持 8/5。
- 桌面桥已重启并报告 `running`，agent PID `33364`；桌面节点 `codex-bf952db5fd9f615f2a8fff37` 和工作区 `ws-c1f09cc351724da6946658c4` 沿用原值。桥文件 `desktop_chat.py` SHA256 `905a22331168b11a506cdf507b6bfb94728ef69187e67a90bf8a4d77be25428f`。未运行真实 Codex 个股研究或功能测试，未重启 TK/ATS、未生成订单。
- 回滚快照 `/mnt/4TB/dockerf/stockstrategy/rollback/20261015224710/COMPLETE` 已核验。回滚命令：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261015224710`。

## 2026-10-15 Web 补丁 20261015211435 已上线

- 用户明确授权“部署本次补丁”后，已执行此前待批的 Web 外置资源补丁，源码 74dbefb；包哈希校验、发布锁、原子 index 替换、HTTP 入口一致性和 API/Web 健康检查完成，脚本返回 healthy。
- 图表底部联动布局与 Codex 首次切换修复已上线；API 镜像和容器未重建，持久化挂载与账本未改。AI 对话默认仍为桌面 Codex / gpt-6-luna / low，Hermes 保留可选。
- 回滚备份及 COMPLETE 位于 /mnt/4TB/dockerf/stockstrategy/auto-follow/web-hotfix/20261015211435；原入口 previous-index.html，所改源码 source-before。未触发用户取消的真实对话、研究、关注或 UI 功能测试，由用户手动验收。

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


## 2026-10-16 Web 基准指数 TDX 回补闭环

- Web 选股分析按板块使用 000001.SH、399001.SZ、399006.SZ。InStock 日任务新增指数历史读取、缺口回补和每日自动调度；即使 INSTOCK_STOCK_SPOT_ONLY=1 也会运行指数回补。优先使用 TDX HQ，失败时逐年请求腾讯历史行情；按交易日日历校验目标日和最近 300 根，并以原子替换写入 SH000001.TXT、SZ399001.TXT、SZ399006.TXT。
- 生产 LXC 102 的 inStock 容器已在 strategy_enter.lock 下更新单个日任务文件，无容器重启或镜像重建。运行文件 SHA256：cd5d818eab7692d31127c7ad464d38f424d5556f681776ab5c944e899e400e48；回滚副本：/data/InStock/instock/job/basic_data_daily_job.py.bak-codex-permissions-20261016025343。
- 生产回补目标 2026-10-15。共享数据目录三文件末日均为目标日，权限均为 0644；行数：SZ399001.TXT 8696、SZ399006.TXT 3974、SH000001.TXT 8590。最新 300 个交易日均无缺口，完成标记 /data/InStock/instock/cache/close_finalize/tdx-index-2026-10-15.done 为 complete=true、missing_recent_dates=0。
- 生产原历史仍有少量早期缺口：深证成指 19 个（1991–1995）、上证指数 8 个（1992–1994）；它们不影响 Web 的 300 日窗口，也不会触发每日重复全量下载。数据回滚副本位于共享 forwardp 目录，后缀为 .pre-window-finalize-20261016024944。
- stockstrategy-api 只读挂载同一 TDX 目录。Web 容器快速分析接口返回 200，benchmark_symbol=399006.SZ、质量 ready、缺失错误数 0；Web Codex Desktop deep 研究完成，任务 succeeded、AI ready、基准 ready。完整研究通过生产 API 路由执行，未验证浏览器视觉点击。
- TDX HQ 对指数历史请求返回 pytdx 解包错误，腾讯兜底已实际用于回补。新增 Python 回归 7 项通过，原 TDX HQ 回归 11 项通过。新增 Go 文件读取测试覆盖三种基准；本机无 Go 工具链，未运行该 Go 测试，线上 Web API 实测已验证数据读取。
- 已知 AI 例外：Web 快速 Codex 研判返回 JSON 字段校验错误，任务降级；/stocks/ai-analysis 的 Hermes 模式当前也不可用。Web 页面默认 deep 的 Codex Desktop 路径已成功；上述快速模式/Hermes 另行处理。

详细记录见任务报告 docs/tasks/2026-10-16_0254_Web基准指数数据回补闭环.md。
## 2026-10-16 桌面桥 Web→API→Codex→回执闭环修复

- 发布 `20261016144526`，隔离发布源码提交 `a9cefc5d80d29f2dc9fb02cacae378a59bdb48f5`；API/Web healthy，原有数据挂载与交易配置未改。回滚：`bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261016144526`。
- Web/API 修复桌面聊天 GET 短暂失败重试、取消确认、租约过期与本地缓存回执重放竞态。设置检测的 Codex 回合上限 120 秒，Web 总上限 180 秒。
- 桥端 `chat_result` 瞬时网络错误最多重试 3 次；成功结果保留本地账本并可在租约重领时重放；本机心跳状态先落盘。新日志标明 operation 与 HTTP 状态。
- 打包管理器 v3 已并排安装，SHA256 `3E0C7339DA31EE90A1C9E37842153077AD5C813ED56F43EB42ED75F9959FFF5B`；已使用该包的冻结 worker 优雅替换空闲旧桥。当前本机 agent ready、无活动 job；API runtime 查询 online=true，模型目录正常；HMAC 名录确认 chat_running=0、chat_queued=0。
- API health、Web 根页及设置/对话资源 HTTP 200；Python 语法检查、Go 编译、TypeScript 检查和 Vite 生产构建通过。未运行测试套件；执行一次真实固定短标记闭环检测，9.1 秒返回 `CODEX_BRIDGE_OK`，测试 job/session 清理后队列为 0/0。未改行情、持仓、账户或交易风控数据。
- OSError 本身无法证明路径故障；当前 Codex 引擎路径存在、桥状态文件持续更新。若再出现异常，新日志可区分桥请求、HTTP 状态、Codex 启动/回合和本地路径阶段。详见 [任务记录](docs/tasks/2026-10-16_1452_桌面桥闭环超时与回执修复.md)。


## 2026-10-17 02:56 桌面桥常驻、派发、流式与性能验收

- Web/API 发布 20261017021507，独立 source 源码 SHA 540876a57041a3286f20569efc3e93083367a592，干净隔离副本通过原脚本发布；28 个变更文件生产摘要一致。API ID sha256:46006d7148592fa3a8367da2591c55c1598925ca1f53080d968d5708372224e4，2 层、119590372 字节；Web 复用 web:20261011114424。healthy、always、ReadonlyRootfs=true、SizeRw=0，8/5 个 bind mounts 保持。
- 生产管理器已通过原批量打包选项 7 替换，代码 SHA f7a701fda58bb9a04b3b39d6070ff519913b7ada，EXE SHA256 1A8EEC129AC2FB8800C24B6F5C40BA6F67E6C47909316FA79E9B879B64EE805A。桥 ready/online，原 node/workspace 及 luna/max 配置保持；队列 0/0，WAL 账本 quick_check=ok、待回执 0，唯一常驻引擎。
- 修复缓存/回执原子性、网络退出、同步桌面扫描、题材短写锁竞争及 queue.Empty 遮蔽，保留研究/对话独立桥选择；关闭桥不需要的继承 MCP/插件，仅保留显式只读工具。Python 46 项、相关 Go 模块、Web 9 项及生产构建通过；真实动态工具调用、停止回收及浏览器 SSE 闭环通过。
- 阶段性 103 个短标记全部成功，最终版本 10/10，总耗时 P50/P95=5.016/11.734 秒、领取 P95=46 ms。此前 31 样本含原生 Codex 回合 88.4 秒长尾；最终确认有一次回传重试函数 4.844 秒，不承诺稳定秒回。
- 北新路桥 quick/standard=22.516/99.140 秒；deep 两次=144.500/317.087 秒，均 AI ready。最终真实页面提交 635082c525e807a96ce09aca4edf999d，SSE 200、页面运行错误 0；core 一轮 239.277 秒，剩余主要时间在 Codex 调用，保留资料缺失及行情日期。
- 回滚快照 20261017021507 的 COMPLETE 和 SHA256SUMS 全部通过，命令 bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261017021507；优化前完整快照为 20261017015525，原管理器备份同编号目录下 manage_window_layout.exe。未回滚数据、未触发实盘下单，未实际执行生产回撤。
- 详见 [部署与性能验收记录](../docs/tasks/2026-10-17_0256_桌面桥生产部署与性能验收.md)。仅本地 Git 提交，未推送。


## 2026-10-17 Web 桥链路计时复核与后续优化

- 最终发布 20261017034210，独立 source SHA 2b012b64902dc9a2a0027292ea844c8c999f3e5d，27 个变更文件生产摘要一致。API ID sha256:3e16c9533a9b699aade3f97366d19e1ccbde6c2e6b1d6eb8ff16337cfb466bb6，2层、119594468字节；Web复用20261011114424。两个容器healthy、always、只读根、SizeRw=0，8/5挂载保留；固定base及回滚快照门禁通过。
- 原脚本选项7重新打包并原子替换管理器，代码SHA 1e714ca7a14b6eb11f8a1ed390cfd0c075d13f76，EXE SHA256 A2DC5C414015F59425C91EEA5E463B71003B1C6374166D43180A086BEDEB5FC7。桥ready，唯一引擎，默认luna/max，队列0/0、账本ok、待回执0。旧包备份为原performance-20261017015525目录下manage_window_layout.pre-receipt-latency.exe。
- 减少空闲领取写锁、nonce清理频率与重复SSE，新增闲置连接轮换/回执重试诊断、研究分段计时及降级诊断保留。Python44项、Web13项、相关Go模块与构建通过；最终3次快速研究及3次短对话均成功。首阶段另有一次21.489秒证据降级，未冒充AI成功。
- 43.252秒记录中AI调用38.994、其余4.258；旧22.476秒为18.880/3.596，并非Web固定增加21秒。新quick同档实测29.640/32.543/47.672秒，浏览器额外约329ms；最慢一次Codex等待及输出43秒，仍有原生调用长尾，不能保证稳定22秒。
- 回滚：bash /root/johnson/stock-strategy/docker/rollback-prebuilt.sh 20261017034210；COMPLETE及摘要均已核验，未实际回撤、不回滚业务数据。详见[性能复核记录](../docs/tasks/2026-10-17_0350_Web桥计时与性能复核.md)。仅本地提交，未推送。

## 2026-10-18 InStock 策略收益列自适应显示

- 在当前 InStock `stock_web.html` 增加 `rate_N` 收益列自适应：日期、代码、名称等核心列始终列入显示；收益列数量至少填满当前表格可用宽度；数据期数更多时保留所有已发现的收益期数，由原有横向滚动查看。
- 期数按当前策略和日期的数据页逐页累计；窗口大小改变时重新计算列数。DataTables 请求仅发送后端实际使用的列搜索字段；复制、CSV、打印仍导出完整列。
- 原模板及 SHA-256 副本、可重放补丁工具保存在 InStock 既有外置 cache 备份目录。仅修改模板，不重建镜像、不重启容器。
- 首次检查时运行中的 `run_web` 仍返回旧模板；已只重启 supervisor 的 `run_web`（`run_cron` 未动），新进程 PID 11505。实时页面响应现已包含 `__instockAdaptiveReturnsV1`，确认新模板已加载。
- 未运行自动测试或登录浏览器 UI 验收；用户侧若仍显示旧布局需强制刷新页面（Ctrl+F5）。未做基准测试，性能收益尚无实测百分比。


## 2026-10-19 AGV 模型及等级自适应发布

- 目录以 agy models 为准，Claude 不再伪造 high/max，公布 auto 并省略 CLI --effort；Gemini 按实际变体适配，Web 合并模型家族。保持现网 API 契约，无 API 镜像/数据库迁移。
- 子仓库 main b34afe91815f51570547b397569bcb4d8f1c2852；Web 发布 20261019041026，原子入口更新，45 资源验证；容器/镜像/挂载不变。回滚：bash /mnt/4TB/dockerf/stockstrategy/rollback/web-agv-20261019041026/rollback.sh。
- 菜单7打包管理器已安装，SHA256 1a9d3bcd35f45ed10721252878972e8952d052c6513cd111a67e6a02ed0d7151；保留原程序备份、身份及偏好。AGV ready/online，22项Python测试通过。
- 真实 Claude 任务08ae40f57eec92808a359ad481d8be57完成：桥6.50秒，输入10167/缓存9478/输出31，SSE正常。研究样本因无效rule_baseline引用保持失败，不降低证据校验。
- 用户指定全局聊天 Gemini 3.8 Flash／Medium，PUT及读回通过。详情及限制见 docs/tasks/2026-10-19_0405_AGV模型推理等级修复与部署.md（主仓库）。


## 2026-10-19 09:44 AGV资格检查EOF恢复

- 资格检查头像GET EOF与推理档位无关；外层重试原先只恢复领取循环。现聊天/策略对尚无内容的eligibility EOF/reset/timeout最多原任务内重试一次，共享原超时预算，停止及已有输出不重试；持续失败返回AGY_ELIGIBILITY_NETWORK_ERROR。
- 25项Python相关回归通过，菜单7构建并安装SHA256 0d4d143d7d707033cad91b331931f622344d0e37656ecd216d06ab46f12cf500；两桥ready，身份及偏好保留。旧包备份stock-strategy/backups/agv-model-20261019041026-094336，主仓库实现提交b8b0630e，未推送。
- 无服务端/Web变更，不改历史失败记录；未模拟生产网络故障。详见主仓库docs/tasks/2026-10-19_0942_AGV资格检查EOF恢复.md。
