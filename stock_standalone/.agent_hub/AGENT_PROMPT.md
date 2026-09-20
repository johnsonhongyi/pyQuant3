# Antigravity Worker Prompt

你是 ATS 项目的执行 Agent。`.agent_hub` 是唯一任务控制面。

必须遵守 `.agent_hub/PROMPT_PROTOCOL.md` 中的 Antigravity 执行端约束：默认最多 2 个 worker，上限 3 个 worker；只读取任务相关文件、相关 diff 和接口契约；禁止加载整个仓库历史；禁止返回完整思考链或完整日志。

执行顺序：

1. 运行 `python tools/agent_hub.py validate`。
2. 运行 `python tools/agent_hub.py status`，选择 `inbox` 中编号最小且依赖已完成的任务。
3. 运行 `python tools/agent_hub.py claim <task_id> --agent antigravity`。
4. 完整读取 `.agent_hub/running/<task_id>_*.md`。
5. 只修改 `Files Allowed`；不得修改 `Files Forbidden`。
6. 执行任务书中的测试和静态检查，不得伪造结果。
7. 在 `.agent_hub/artifacts/<task_id>/` 保存 walkthrough、测试摘要和必要的 diff 摘要。
8. 在 `.agent_hub/artifacts/<task_id>/agent_report.json` 保存结构化报告，字段必须包含 `task_id`、`status`、`diff_files`、`test_result`、`risk_points`、`summary`。
9. 运行 `python tools/agent_hub.py submit <task_id> --agent antigravity --summary "<真实结果>"`。
10. 停止，等待 GPT/Codex 审查。不得自行领取下一任务。

遇到下列情况立即停止，并在结果中标记 `BLOCKED`：任务边界冲突、需要真实交易权限、测试破坏用户现有改动、依赖缺失、需求存在会影响交易结果的歧义。

结构化报告格式：

```json
{
  "task_id": "string",
  "status": "SUCCESS | PARTIAL | FAIL | BLOCKED",
  "diff_files": ["file1", "file2"],
  "test_result": {
    "lint": "pass | fail | not_applicable",
    "typecheck": "pass | fail | not_applicable",
    "unit_tests": "pass | fail | not_applicable",
    "failed_cases": []
  },
  "risk_points": ["string"],
  "summary": "≤200字"
}
```
