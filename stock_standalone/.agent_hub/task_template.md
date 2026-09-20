# Task

一句话说明唯一交付目标。

## Metadata

- Task-ID: 000
- Owner: unassigned
- Priority: P1
- Risk: LOW
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
