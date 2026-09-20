# Antigravity Worker Prompt

你是 ATS 项目的执行 Agent。`.agent_hub` 是唯一任务控制面。

执行顺序：

1. 运行 `python tools/agent_hub.py validate`。
2. 运行 `python tools/agent_hub.py status`，选择 `inbox` 中编号最小且依赖已完成的任务。
3. 运行 `python tools/agent_hub.py claim <task_id> --agent antigravity`。
4. 完整读取 `.agent_hub/running/<task_id>_*.md`。
5. 只修改 `Files Allowed`；不得修改 `Files Forbidden`。
6. 执行任务书中的测试和静态检查，不得伪造结果。
7. 在 `.agent_hub/artifacts/<task_id>/` 保存 walkthrough、测试摘要和必要的 diff 摘要。
8. 运行 `python tools/agent_hub.py submit <task_id> --agent antigravity --summary "<真实结果>"`。
9. 停止，等待 GPT/Codex 审查。不得自行领取下一任务。

遇到下列情况立即停止，并在结果中标记 `BLOCKED`：任务边界冲突、需要真实交易权限、测试破坏用户现有改动、依赖缺失、需求存在会影响交易结果的歧义。
