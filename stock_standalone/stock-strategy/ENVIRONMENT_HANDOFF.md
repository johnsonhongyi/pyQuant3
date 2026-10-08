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
