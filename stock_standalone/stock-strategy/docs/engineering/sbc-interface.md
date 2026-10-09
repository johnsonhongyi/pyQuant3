# SBC K 线分析接口

后端为纯 Go 实现，已于 2026-10-09 部署版本 `20261009233755`。网页日/周/月 K 线共用 `KLineChart`，展示均线、通道三轨、KX 支撑、反转线、黄金分割、九转、启动/逃顶、逆势先锋及策略评分/介入/止损/目标。日线另显示近 5 日振幅活跃度。各图层独立开关；分时保持原显示。

## 协议

`POST /api/v1/quotes/sbc/v1/analyze`，沿用现有后端鉴权。

- 输入：`symbol`、`period`、`bars`。必须使用图表显示的同一批 OHLCV 数据，时间严格递增，无重复，10–1000 根。允许 day/week/month/5/15/30/60。
- 输出：`data.schema_version=1`、`source=ats-sbc`、`implementation=go-native`、`symbol`、`period`、`as_of`、`trade_date`、原始末根 `market_meta`、逐根 `points`、画布 `levels`、日线 `activity`、`strategy` 以及 `engine_revision` 对照源码 SHA-256 清单。未预热或停画指标返回 null。
- 前端校验版本、股票、周期和每根时间，取消旧请求，丢弃与当前快照不匹配的结果。
- 错误保留基础 K 线并显示原因。继承原行情陈旧标记，不补造实时数据，不执行交易。
- 后端在请求内完成计算，数据上限 1000 根，保留 10 秒请求超时与取消检查。每次使用独立数组及结果对象；不启动子进程，不访问行情网络或交易执行模块。

## 运行条件

使用 server 现有 Go 构建流程，SBC 新增代码仅使用 Go 标准库和既有 `foundation.KLine`，支持 `CGO_ENABLED=0`。后端不需要 Python、NumPy、Pandas、TA-Lib 或新增环境变量。

`docker/backend.Dockerfile`、Go 模块依赖和生产环境保持原状；按现有发布流程构建 server 即包含 SBC 计算。已按部署手册完成生产发布，API/Web 健康检查和 SBC 原生接口冒烟验证通过。

## 与 SBC 对齐

开发机运行 `python tools/sync_sbc.py`，默认 ATS 根为上一级目录；其他位置用 `--ats-root`。AST 提取结果只存于 `tools/sbc_reference/`，同时更新对照源码清单；不会生成或替换 Go 算法。参考 Python 不进入后端构建或镜像。

移植来源：`JSONData/tdx_channel_factory.py`、`tdx_data_Day.py` 的通道和九转函数、`ats/channel_bottom_reversal_strategy.py` 的纯策略函数。Go 实现保留主跌通道、反弹子通道、回退通道、DRAWLINE 配对、EMA/RSI 预热和 Python/NumPy 不同的取整规则。活跃度及黄金分割按 SBC 画布规则计算。额外多日换手缓存不在此接口范围内。

SBC 更新后，在具备原 Python 依赖的开发机运行 `python tools/generate_sbc_fixtures.py` 更新冻结对照样本，再执行 Go 测试；如有差异，修改对应 Go 算法直至通过。冻结样本使用 gzip 存储，Go 测试可独立读取，不要求测试机安装 Python。

自定义计算服务可实现前端 `SBCProvider`，通过 `KLineChart.sbcProvider` 注入，保持 v1 快照协议即可。新增字段优先兼容扩展；破坏性变更另建版本。

验证：后端 `go test ./internal/sbc`，接口 `go test ./internal/httpapi -run '^TestSBC'`；前端 `npm.cmd test -- --run src/lib/sbc.test.ts src/lib/kline.test.ts`。31 组 ATS 冻结样本覆盖预热边界、涨跌横盘、主跌/反弹、多次先锋、两种上涨形态及两种底部突破，并校验逐根指标和策略字段。另有非法输入、取消、并发一致性以及清空 PATH 后的原生 HTTP 测试。
