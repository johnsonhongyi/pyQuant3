# Task

一句话说明唯一交付目标。

## Metadata

- Task-ID: 000
- Owner: unassigned
- Priority: P1
- Risk: LOW
- Permission-Profile: P2_CODE_LOW
- Depends-On: none
- Created-By: codex
- Created-At: YYYY-MM-DD

## Context

说明为什么做、现有事实和业务边界。

## Files Allowed

- `path/to/file.py`
- `tests/test_file.py`

## Files Forbidden

- `trade_gateway.py`
- 真实券商接口、凭据和实盘开关

## Requirements

- 可验证要求 1
- 可验证要求 2

## Definition of Done

- [ ] 实现范围完整
- [ ] 测试通过
- [ ] 无越界文件修改
- [ ] 结果和风险已记录

## Verification

```powershell
python -m pytest tests/test_file.py -q
```

## Rollback

说明如何撤销本任务自身的改动，不得覆盖用户或其他 Agent 的改动。

## Output Contract

在 `.agent_hub/artifacts/000/` 生成：

- `walkthrough.md`
- `test_result.md`
- `changed_files.txt`
- `agent_report.json`


## 并行与P节点建议元数据

任务创建时应明确：
- `Depends-On`: 上游任务编号，多个编号以空格/逗号分隔；无依赖写 `none`。
- `Files Allowed`: 既是 Worker 修改白名单，也是并行文件所有权声明。
- 相互独立且文件集合不重叠的任务才允许进入同一并行批次。
- 属于同一 P 节点的任务完成后，由 `checkpoint-review` 做一次 Medium 级综合审查，而不是逐任务重复提高推理档位。
