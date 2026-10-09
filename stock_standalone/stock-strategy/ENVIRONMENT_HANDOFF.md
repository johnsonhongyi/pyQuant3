# Easy Stock 环境交接

生产部署背景与上次线上核验见 [source/docs/项目交接说明.md](source/docs/项目交接说明.md)。其中生产快照有日期，部署前必须重新核验容器、镜像、挂载与部署脚本预期基础镜像。

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