# -*- coding: utf-8 -*-
"""
测试：SBC Launcher 持仓盯盘在股票池下拉菜单中展示并选择最近 3 组历史快照
----------------------------------------------------------------------
1. 验证 _build_sbc_subprocess_command 支持透传 --snapshot 参数；
2. 验证 SBCProcessManager.launch_holdings_watcher 支持指定 snapshot_idx；
3. 验证 UniverseTreeWidget._append_snapshots_menu 正确读取最近 3 组历史快照并生成子菜单及对应 Action；
4. 验证点击 Action 触发指定快照组加载。
"""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication(sys.argv)

import run_sbc
from ats.ui.sbc_launcher import _build_sbc_subprocess_command, SBCProcessManager
from ats.ui.universe_widget import UniverseTreeWidget


def test_build_sbc_subprocess_command_with_snapshot():
    """测试 _build_sbc_subprocess_command 正确支持 snapshot_idx"""
    cmd = _build_sbc_subprocess_command(is_holdings=True, snapshot_idx=2)
    assert cmd is not None
    assert "--snapshot" in cmd
    assert "2" in cmd
    idx = cmd.index("--snapshot")
    assert cmd[idx + 1] == "2"

    cmd_normal = _build_sbc_subprocess_command(is_holdings=True)
    assert "--snapshot" not in cmd_normal


def test_sbc_process_manager_launch_with_snapshot():
    """测试 SBCProcessManager.launch_holdings_watcher 能够透传 snapshot_idx"""
    mgr = SBCProcessManager.get_instance()
    
    with patch("subprocess.Popen") as mock_popen, \
         patch.object(mgr, "is_launcher_running", return_value=False):
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        proc = mgr.launch_holdings_watcher(snapshot_idx=3)
        assert mock_popen.called
        call_args = mock_popen.call_args[0][0]
        assert "--snapshot" in call_args
        assert "3" in call_args


def test_universe_widget_append_snapshots_menu():
    """测试 UniverseTreeWidget._append_snapshots_menu 正确构造 3 组历史快照子菜单"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_file = os.path.join(tmp_dir, "sbc_launcher_holdings_layout.json")
        fake_snapshots = [
            {
                "time": "2026-09-17 12:45:00",
                "codes": ["600733", "603407"],
                "windows": [{"code": "600733"}, {"code": "603407"}]
            },
            {
                "time": "2026-09-17 12:30:00",
                "codes": ["688635"],
                "windows": [{"code": "688635"}]
            },
            {
                "time": "2026-09-17 11:20:00",
                "codes": ["600733", "603407", "688635"],
                "windows": [{"code": "600733"}, {"code": "603407"}, {"code": "688635"}]
            }
        ]
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({
                "sbc_holdings_windows": fake_snapshots[0]["windows"],
                "recent_history_snapshots": fake_snapshots
            }, f, ensure_ascii=False)

        with patch.object(run_sbc, "_get_launcher_layout_cfg_path", return_value=cfg_file):
            widget = UniverseTreeWidget()
            menu = QMenu()
            
            widget._append_snapshots_menu(menu)
            
            # 验证是否成功生成了子菜单
            submenus = [act.menu() for act in menu.actions() if act.menu() is not None]
            assert len(submenus) == 1
            snap_menu = submenus[0]
            assert "历史快照恢复" in snap_menu.title()
            
            # 验证子菜单包含 3 个历史快照选项
            snap_actions = snap_menu.actions()
            assert len(snap_actions) == 3
            assert "快照 1" in snap_actions[0].text()
            assert "600733, 603407" in snap_actions[0].text()
            assert "快照 2" in snap_actions[1].text()
            assert "688635" in snap_actions[1].text()
            assert "快照 3" in snap_actions[2].text()

            # 验证点击快照 2 触发 launch_holdings_watcher(snapshot_idx=2)
            mgr = SBCProcessManager.get_instance()
            with patch.object(mgr, "launch_holdings_watcher") as mock_launch:
                snap_actions[1].trigger()
                mock_launch.assert_called_once_with(snapshot_idx=2)
