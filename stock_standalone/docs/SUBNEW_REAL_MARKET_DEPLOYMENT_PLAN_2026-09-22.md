# 【明日开盘实战部署计划书】新股次新股检测中心与集中交易中心 (2026-09-22 实战严控版)

## 一、 部署目标与核心宗旨

> **实战目标**：确保明天（2026-09-22）开盘 9:30~15:00 期间，操盘手在集中交易指挥室与新股检测中心中：
> 1. **消灭早盘假阳性脉冲噪声**：早盘 9:30~10:00 绝不被虚假放量和脉冲冲高误导开仓；
> 2. **极致收敛可执行买卖点**：S0~S3 永不进入执行区；进入直接买卖点的必须通过严格可执行门：
>    $$\text{Executable Directives} = \mathbf{S4} \cap \mathbf{quality\_grade \in \{A, S, SS\}} \cap \mathbf{structure\_confirmed} \cap \mathbf{executable\_price} \cap \mathbf{RR_{\text{now}} \ge 2.5} \cap \mathbf{not\_expired} \cap \mathbf{risk\_gate\_passed}$$
>    全天直接买入候选强力收敛至 **1~3 只**；
> 3. **底线风控绝对坚挺**：同代码退出决议绝对压制买入（EXIT > BUY 阻断门），T+1 物理锁合规，零重复下单，零幽灵持仓；
> 4. **Fail-Safe 单向降级保障**：异常情况立即单向降级为 `MONITOR_ONLY` 纯观察，禁止盘中自动逆向升级，不影响人工操作。

---

## 二、 关键改进点与降级策略设计 (核心事实锁定)

### 1. P1-01 早盘成交量归一化：数学定义与时点测试矩阵
- **核心变量与业务定义锁定（杜绝除零放大）**：
  - `raw_volume_signal`：策略在当前分时算出的原始放量倍数；
  - `elapsed_minutes`：开盘已交易分钟数（9:30 为 0，9:35 为 5）；
  - `attenuation_factor`：仅针对早盘 09:30~10:00 的衰减折减系数：
    $$\text{attenuation\_factor} = \text{Clamp}\left(\frac{\text{elapsed\_minutes}}{30.0}, \text{Min}=0.20, \text{Max}=1.0\right)$$
  - `normalized_volume`：
    $$\text{normalized\_volume} = \text{raw\_volume\_signal} \times \text{attenuation\_factor}$$
- **时点边界阻断测试矩阵（必须 100% 覆盖）**：
  1. `09:30:00`：$\text{elapsed}=0 \implies \text{factor}=0.20$（保底折减，不除零，不出现 NaN/Inf）；
  2. `09:31:00`：$\text{elapsed}=1 \implies \text{factor}=0.20$（单分钟脉冲放量 10 倍折算后仅 2.0 倍）；
  3. `09:35:00`：$\text{elapsed}=5 \implies \text{factor} \approx 0.20$；
  4. `09:45:00`：$\text{elapsed}=15 \implies \text{factor}=0.50$；
  5. `09:59:59`：$\text{elapsed} \approx 30 \implies \text{factor} \approx 1.0$；
  6. `10:00:00`：$\text{elapsed}=30 \implies \text{factor}=1.0$（早盘折减结束，恢复常态量比）；
  7. `11:30:00`：$\text{factor}=1.0$；
  8. `13:00:00`：$\text{factor}=1.0$（午休不误算 elapsed，**下午严禁重新从 0 启动衰减**）。
- **降级开关与生效说明**：
  - 配置文件中设置 `enable_intraday_volume_normalization: bool = True`；
  - 盘中遇异常该开关修改后**需要 5 秒重启进程生效**（实事求是，绝不承诺虚假热重载）。

### 2. S4 可执行门：全维度拦截与 S4/S5 语义统一
- **保留完整质量评级体系**：
  - 必须严格满足：
    $$\text{S4} \cap \text{quality\_grade} \in \{\text{"A"}, \text{"S"}, \text{"SS"}\} \cap \text{structure\_confirmed} \cap \text{executable\_price} \cap \text{RR}_{\text{now}} \ge 2.5 \cap \text{not\_expired} \cap \text{risk\_gate\_passed}$$
  - 质量为 B 或 C 级的即使突破也只留在监控大表，坚决不进入直接买卖点。
- **S4 与 S5 协议统一定义**：
  - `S4`：策略形态与次级买点突破完全确立的**“终审买点 TradePlan”**（不可变结构事实）；
  - `S5`：通过了实时买区、现价、风控配额校验并下发到指挥室待执行列表的**“可撮合指令 Directive”**；
  - 股票若因盘中冲高溢出买区，仅退回非可执行状态，`S4` 结构记录绝不被篡改或否定。

### 3. 动态 RR 重算：杜绝“移动球门”，锚定固定结构
- **结构层锚点（不可变）**：
  - `structural_stop`：次级回踩低点（Higher-Low）硬防守价；
  - `structural_target`：通道中轨/上轨目标价；
  - 这两个数值属于形态结构事实，在当前 TradePlan 版本内**绝对禁止随 Tick 任意漂移**！
- **执行层变量（即时现价）**：
  - 仅利用最新实时行情 $P_{\text{now}}$ 重算即时盈亏比：
    $$\text{RR}_{\text{now}} = \frac{\text{structural\_target} - P_{\text{now}}}{P_{\text{now}} - \text{structural\_stop}}$$
  - 当股价追高超出买入区间时，$P_{\text{now}} - \text{structural\_stop}$ 放大，$\text{RR}_{\text{now}}$ 迅速跌破 2.5:1，指令立即失去可执行资格，打回大表观察。

### 4. 交易时钟 15 分钟 TTL 与历史原因留存
- **时间度量基准**：严格使用**交易分钟数（Trading Minutes）**，自动跳过 11:30~13:00 午休 90 分钟，杜绝跨午盘误杀；
- **状态流转与可追溯审计**：
  - 计划超过 15 交易分钟未成交时，状态转为 `ACTIVE \to EXPIRED`；
  - 写入 `expired_reason = "TTL_TRADING_15M"`；
  - 绝不静默物理删除，保留在当天的统计流水中，用于明晚复盘“有多少 S4 因为未进入买区而自然超时”。

### 5. 退出绝对压制买入（EXIT > BUY 阻断门）
- 同一标的在同一决策周期内只要产生退出类决议（`EXIT_ALL` / `SELL` / `REDUCE`），必须彻底覆写并物理剥离任何 `BUY` 动作；
- 本项作为今晚部署的上线阻断性测试（Blocking Contract）。

### 6. T+1 持仓事实源优先级与单向 NO-GO 安全闩
- **券商/柜台事实源与 Kernel 优先级定义**：
  - **资金与持仓事实源**：券商/柜台实际返回的 `positions` 与 `sellable_qty` 为绝对权威；
  - **本地交易状态事实源**：Kernel 负责本地风控与状态机流转；
  - **冲突处理准则**：两端持仓出现冲突时，**立即禁止该标的的 BUY/SELL 执行并触发 reconciliation 对账报警**，绝不允许本地状态自行推算或强行覆盖券商持仓！
  - `sellable_shares` 绝不能根据本地 TradePlan 推导，严格排除 `today_bought`。
- **Gate 2 单向 NO-GO 物理闩**：
  - 明早 09:25 若 8 项准入指标任一失败，系统由 `CONFIRM` 降级为 `MONITOR_ONLY`；
  - **盘中绝对禁止自动逆向升级回 CONFIRM**，即使 09:35 数据恢复正常也必须保持只读监控，彻底堵死系统突然起跳自动下单的隐患。

---

### 7. 构建指纹定位与单向无环冻结流水线
- **构建指纹归属明确**：
  - `BUILD_FINGERPRINT.json` 明确界定为**部署产物 / 运行态产物（Runtime Artifact）**，**不纳入 Git 版本跟踪**（置于 `.gitignore` 或仅在运行时写出）；
- **单向无环冻结流水线**：
  1. 代码修改与适配完成；
  2. 运行关键契约测试 + 全量回归套件；
  3. 执行最终 Git Commit（`git commit -m "..."`）；
  4. 校验 `git status --porcelain` 输出为空（Clean Working Tree）；
  5. 运行指纹工具基于当前 `HEAD` commit hash 写出部署指纹 `BUILD_FINGERPRINT.json`；
  6. 执行 `git tag -a v2026.09.22-subnew-live -m "..."`；
  7. 冻结生效，今晚 22:00 后严禁任何参数微调。

---

## 三、 明早 GO / NO-GO 终审门控 (09:15 / 09:25)

### 🛑 Gate 1：09:15 集合竞价启动门禁
1. **构建指纹一致性**：当前运行程序指纹与 Git tagged commit 100% 匹配；
2. **对账快照检查**：`reconciliation/latest.json` 为 `ALIGNED`；
3. **持仓 T+1 状态**：昨仓转为可卖，今仓初始为 0；
4. **待执行指令清空**：`pending_directives` 初始为空，无历史隔夜残留。

### 🛑 Gate 2：09:25 集合竞价撮合完毕终审 (GO / NO-GO)
**8 项准入指标必须全部绿灯（ALL GREEN），严禁“7/8 也差不多”：**
- [ ] 1. `build_identity == expected`
- [ ] 2. `market_data_fresh == True`（时钟无倒流，延迟 $\le 3\text{s}$）
- [ ] 3. `account_reconciliation == ALIGNED`
- [ ] 4. `sellable_qty_reconciliation == ALIGNED`
- [ ] 5. `pending_directives == EMPTY_AT_BOOT`
- [ ] 6. `duplicate_plan_check == PASS`
- [ ] 7. `EXIT_BUY_contract == PASS`
- [ ] 8. `risk/execution_path == HEALTHY`

> ⚠️ **NO-GO 单向降级锁定**：  
> 任意 1 项为 RED $\longrightarrow$ 立即置为 `MONITOR_ONLY`！  
> 当天系统只充当大表监控器，严禁自动恢复为执行态，全部由人工盯盘。

---

## 四、 实战运行节奏与三次对账机制

```
[08:45 - 09:15] 盘前自检与 Gate 1 检查
[09:15 - 09:25] 竞价抢筹感知 (IPO_BID_SURGE)，底仓今日可用卖出确认
[09:25]         Gate 2 (GO / NO-GO 终审单向门)
[09:30 - 10:00] 早盘严控期：衰减折减生效，S4 可执行门生效，S0~S3 坚决留在大表
[10:00 - 11:30] 黄金交易确认窗口：监控长期通道次级买点突破，核对卡片阶梯
[11:30]         午盘轻量对账：核对早盘 PAPER 成交记录与持仓状态机
[13:00 - 14:30] 午后防守跟踪：ProactiveExitEngine 动态防守位生效，监控破位出局
[14:30 - 15:00] 尾盘决策结算：清点未执行过期买点，交易时钟 15 分钟 TTL 撤销归档
[15:00]         日终全量对账：生成日终对账快照，归档 reconciliation_YYYYMMDD.jsonl
```

---

## 五、 今晚闭环执行步骤清单 (待授权后实施)

1. [ ] **Step 1（快照）**：保存当前阶段三已验证的基线快照；
2. [ ] **Step 2（P1-01）**：实施早盘衰减折减模型（Clamp[0.20, 1.0] 保护，带开关配置，通过 8 时点测试矩阵）；
3. [ ] **Step 3（S4 收敛门）**：落实 S4 可执行门（保留 quality_grade，动态现价 + 结构锚点，交易时钟 15 分钟 TTL）；
4. [ ] **Step 4（阻断测试）**：运行 EXIT > BUY 阻断专项、T+1 柜台优先事实源对账专项测试；
5. [ ] **Step 5（全量回归）**：关键契约测试全部 PASS + 全量 suite 无失败；
6. [ ] **Step 6（单向冻结）**：Final Commit $\to$ 验证 Clean Tree $\to$ 生成构建指纹 $\to$ 打 Tag 冻结封板。
