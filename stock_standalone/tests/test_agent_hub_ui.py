# -*- coding: utf-8 -*-
"""
tests/test_agent_hub_ui.py
---------------------------
测试 webTools/window_manager/agent_hub_ui.py 的数据解析引擎与 UI 逻辑：
1. 测试 AgentHubDataEngine 对任务书、事件流、心跳、决策报告的准确解析；
2. 测试基于 mtime/size 的脏检查 (Dirty Check) 缓存与增量更新机制；
3. 测试 AgentHubMonitorDialog 初始化、筛选过滤与时间线/文档渲染。
"""

import os
import sys
import json
import shutil
import tempfile
from pathlib import Path
import pytest

from PyQt6.QtWidgets import QApplication
from webTools.window_manager.agent_hub_ui import (
    AgentHubDataEngine, AgentHubSnapshot, TaskMeta, AgentHubMonitorDialog
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_agent_workspace(tmp_path):
    """构建一个模拟的 .agent_hub 沙箱工作区"""
    hub_dir = tmp_path / ".agent_hub"
    for d in ("inbox", "running", "done", "archive", "events", "decisions", "artifacts", "dashboard"):
        (hub_dir / d).mkdir(parents=True, exist_ok=True)

    # 1. 编排配置
    cfg = {
        "schema_version": 1,
        "worker_model": "gemini-3.8-flash-high",
        "batch_max_workers": 3,
        "worker_monitor_interval_seconds": 5.0,
        "max_rework_cycles": 1,
        "auto_review": True,
        "review_profiles": {
            "task_review": {"model": "gpt-5.6-luna", "effort": "low"}
        }
    }
    (hub_dir / "orchestrator.json").write_text(json.dumps(cfg), encoding="utf-8")

    # 2. 任务文件
    # inbox 任务
    t_inbox = hub_dir / "inbox" / "101_test_inbox_task.md"
    t_inbox.write_text("""# 测试待认领任务
- Task-ID: 101
- Owner: unassigned
- Priority: P0
- Risk: LOW
- Permission-Profile: P2_CODE_LOW
- Created-At: 2026-09-22
## Requirements
- 必须支持高性能解析
""", encoding="utf-8")

    # running 任务
    t_run = hub_dir / "running" / "102_test_running_task.md"
    t_run.write_text("""# 测试运行中任务
- Task-ID: 102
- Owner: antigravity
- Priority: P1
- Risk: MEDIUM
- Permission-Profile: P3_CODE_MEDIUM
- Created-At: 2026-09-22
""", encoding="utf-8")

    # running 任务心跳
    art_102 = hub_dir / "artifacts" / "102"
    art_102.mkdir(parents=True, exist_ok=True)
    hb_data = {
        "status": "RUNNING",
        "elapsed_seconds": 45.2,
        "readonly_tool_calls": 5,
        "write_tool_calls": 2,
        "readonly_calls_since_write": 0,
        "detail": "testing heartbeat"
    }
    (art_102 / "worker_heartbeat.json").write_text(json.dumps(hb_data), encoding="utf-8")

    # done 任务
    t_done = hub_dir / "done" / "103_test_done_task.md"
    t_done.write_text("""# 测试已完成任务
- Task-ID: 103
- Owner: antigravity
- Priority: P0
- Risk: HIGH
- Permission-Profile: P3_CODE_MEDIUM
- Created-At: 2026-09-21
""", encoding="utf-8")

    # done 决策与报告
    art_103 = hub_dir / "artifacts" / "103"
    art_103.mkdir(parents=True, exist_ok=True)
    (art_103 / "agent_report.json").write_text(json.dumps({
        "task_id": "103",
        "status": "SUCCESS",
        "summary": "103 任务实施圆满成功"
    }), encoding="utf-8")
    (art_103 / "walkthrough.md").write_text("# Walkthrough 103\nEverything is great.", encoding="utf-8")

    (hub_dir / "decisions" / "103_merge_report.md").write_text("""# Merge Report 103
- Codex-Decision: APPROVED
""", encoding="utf-8")

    # events.jsonl
    events_lines = [
        {"action": "claimed", "actor": "orchestrator/antigravity", "task_id": "103", "timestamp": "2026-09-21T10:00:00+00:00", "from_state": "inbox", "to_state": "running"},
        {"action": "submitted", "actor": "orchestrator/antigravity", "task_id": "103", "timestamp": "2026-09-21T10:05:00+00:00", "from_state": "running", "to_state": "done"},
        {"action": "reviewed_rework", "actor": "codex/orchestrator", "task_id": "103", "timestamp": "2026-09-21T10:06:00+00:00"},
        {"action": "reviewed_approved", "actor": "codex/orchestrator", "task_id": "103", "timestamp": "2026-09-21T10:10:00+00:00"},
    ]
    with (hub_dir / "events" / "events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events_lines:
            f.write(json.dumps(ev) + "\n")

    return tmp_path


def test_agent_hub_data_engine_parse(mock_agent_workspace):
    """测试数据引擎解析完整性"""
    engine = AgentHubDataEngine(project_root=mock_agent_workspace)
    snap = engine.load_snapshot(force=True)

    assert len(snap.inbox_tasks) == 1
    assert snap.inbox_tasks[0].task_id == "101"
    assert snap.inbox_tasks[0].title == "测试待认领任务"
    assert snap.inbox_tasks[0].risk == "LOW"

    assert len(snap.running_tasks) == 1
    assert snap.running_tasks[0].task_id == "102"
    assert snap.running_tasks[0].heartbeat.get("status") == "RUNNING"
    assert snap.running_tasks[0].heartbeat.get("readonly_tool_calls") == 5

    assert len(snap.done_tasks) == 1
    assert snap.done_tasks[0].task_id == "103"
    assert snap.done_tasks[0].decision == "APPROVED"
    assert snap.done_tasks[0].rework_count == 1
    assert snap.done_tasks[0].summary == "103 任务实施圆满成功"

    # 测试 active_worker_stats
    assert snap.active_worker_stats["status"] == "RUNNING"
    assert snap.active_worker_stats["task_id"] == "102"
    assert snap.active_worker_stats["readonly_calls"] == 5

    # 测试缓存命中：未修改时 load_snapshot 返回同一快照对象
    cached = engine.load_snapshot(force=False)
    assert cached is snap


def test_agent_hub_monitor_dialog_ui(qapp, mock_agent_workspace):
    """测试 UI 弹窗初始化、卡片渲染与表格搜索过滤交互"""
    dialog = AgentHubMonitorDialog(project_root=mock_agent_workspace)
    assert dialog is not None

    # 验证顶部卡片标签
    assert "Task 102" in dialog.lbl_worker_desc.text()
    assert "gpt-5.6-luna" in dialog.lbl_reviewer_desc.text()
    assert "并发上限: 3" in dialog.lbl_orch_desc.text()

    # 验证任务列表加载
    assert dialog.task_table.rowCount() == 3

    # 验证过滤搜索：按关键字搜索 "103"
    dialog.txt_search.setText("103")
    assert dialog.task_table.rowCount() == 1
    assert dialog.task_table.item(0, 0).text() == "103"
    assert "APPROVED" in dialog.task_table.item(0, 5).text()

    # 验证选定触发详情更新
    dialog.task_table.selectRow(0)
    assert dialog.selected_task is not None
    assert dialog.selected_task.task_id == "103"
    assert "103_test_done_task.md" in dialog.txt_task_doc.toPlainText()
    assert "103 任务实施圆满成功" in dialog.txt_impl_doc.toPlainText()
    assert "Codex-Decision: APPROVED" in dialog.txt_merge_doc.toPlainText()

    # 恢复全部过滤
    dialog.txt_search.setText("")
    dialog.combo_state.setCurrentIndex(1)  # 仅看 Inbox
    assert dialog.task_table.rowCount() == 1
    assert dialog.task_table.item(0, 0).text() == "101"

    # 验证自动刷新与配置持久化
    settings_file = Path(mock_agent_workspace) / ".agent_hub" / "monitor_ui_settings.json"

    # 模拟用户改变自动刷新设置
    dialog.chk_auto_refresh.setChecked(False)
    dialog.cb_interval.setCurrentIndex(3)  # 10秒 (10.0s)
    assert not dialog.timer.isActive()
    assert dialog.refresh_interval_sec == 10.0

    dialog.chk_auto_refresh.setChecked(True)
    assert dialog.timer.isActive()
    assert dialog.timer.interval() == 10000

    # 验证设置文件已落盘
    assert settings_file.exists()
    saved_cfg = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved_cfg.get("auto_refresh_enabled") is True
    assert saved_cfg.get("refresh_interval_sec") == 10.0

    # 关闭当前弹窗后新建弹窗，验证配置成功恢复
    dialog.close()

    dialog2 = AgentHubMonitorDialog(project_root=mock_agent_workspace)
    assert dialog2.chk_auto_refresh.isChecked() is True
    assert dialog2.cb_interval.currentIndex() == 3
    assert dialog2.refresh_interval_sec == 10.0
    assert dialog2.timer.isActive()
    assert dialog2.timer.interval() == 10000
    dialog2.close()


