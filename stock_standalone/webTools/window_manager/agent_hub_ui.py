# -*- coding: utf-8 -*-
"""
webTools/window_manager/agent_hub_ui.py
---------------------------------------
高性能多 Agent 运行状态与任务实施进度全景监控与指挥大屏 (PyQt6)：
1. 架构定位：
   - 面向多 Agent 协同体系（Antigravity Worker、Codex Reviewer、Human Supervisor、Orchestrator）；
   - 提供毫秒级状态感知、任务实施流水线看板 (Pipeline / Kanban)、事件时序流水与产物详情下钻。
2. 核心性能特性：
   - 纯后台脏检查缓存机制 (AgentHubDataEngine)：基于 mtime/size 指纹检测，无变化时零磁盘读取；
   - 界面节流调度：基于 QTimer 智能轮询，杜绝界面卡顿；
   - 统一深色极简风格，原生支持 PyQt6 布局与 DPI 自适应。
3. 交互与功能：
   - 顶部集群卡片：Worker 心跳、调用预算 (Read/Write Budget)、耗时、Reviewer 状态与编排器配置；
   - 中部任务表格：支持 Inbox / Running / Done / Archive 分页筛选与全局模糊搜索；
   - 底部双栏下钻：左侧任务流转生命周期时间线 (Timeline)，右侧任务书/代码审查/执行报告 (Markdown 富文本)；
   - 快捷动作：一键打开任务产物目录、一键调用自动化备份。
"""

from __future__ import annotations

import os
import sys
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QTabWidget, QTextEdit, QSplitter, QFrame, QProgressBar, QMessageBox,
    QFileDialog, QCheckBox
)

try:
    from JohnsonUtil import commonTips as cct
except Exception:
    cct = None

AGENT_HUB_SINGLE_INSTANCE_SERVER = "ATS_AgentHubMonitor_SingleInstance_IPC"


def activate_existing_agent_hub_instance(timeout_ms: int = 350) -> bool:
    """
    通过 QLocalSocket IPC 管道探测是否已有 Agent Hub 监控器实例正在运行。
    若已在运行，发送 WAKEUP 唤醒指令使其置顶激活并返回 True；否则返回 False。
    """
    try:
        sock = QLocalSocket()
        sock.connectToServer(AGENT_HUB_SINGLE_INSTANCE_SERVER)
        if sock.waitForConnected(timeout_ms):
            sock.write(b"WAKEUP\n")
            sock.flush()
            sock.waitForBytesWritten(timeout_ms)
            sock.disconnectFromServer()
            return True
    except Exception:
        pass
    return False

TASK_NAME_RE = re.compile(r"^(?P<id>\d{3,})_(?!result\.md$).+\.md$")


@dataclass
class TaskMeta:
    task_id: str
    title: str
    state: str  # inbox, running, done, archive
    file_path: Path
    owner: str = "unassigned"
    priority: str = "P1"
    risk: str = "LOW"
    permission: str = "P2_CODE_LOW"
    created_at: str = ""
    updated_at: str = ""
    rework_count: int = 0
    decision: str = "PENDING"
    summary: str = ""
    heartbeat: Dict[str, Any] = field(default_factory=dict)
    report: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentHubSnapshot:
    inbox_tasks: List[TaskMeta] = field(default_factory=list)
    running_tasks: List[TaskMeta] = field(default_factory=list)
    done_tasks: List[TaskMeta] = field(default_factory=list)
    archive_tasks: List[TaskMeta] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    orchestrator_config: Dict[str, Any] = field(default_factory=dict)
    active_worker_stats: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = 0.0


class AgentHubDataEngine:
    """
    负责 .agent_hub 数据提取与缓存的后台轻量引擎
    具备 mtime 脏检查机制，避免高频 I/O 阻塞 UI 主线程
    """

    def __init__(self, project_root: Path | str | None = None):
        if project_root is None:
            # 源码运行时从模块位置推导工程根目录；打包运行时 __file__ 位于
            # PyInstaller 的临时 _MEI 目录，不能作为用户工程目录，也可能在
            # 启动清理阶段已失效。manage_window_layout.py 已将真实根目录设为 CWD。
            if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
                project_root = os.environ.get("INSTOCK_APP_ROOT") or os.getcwd()
            else:
                # webTools/window_manager -> stock_standalone
                project_root = Path(__file__).parent.parent.parent

        self.project_root = self._select_project_root(project_root)
        self.hub_dir = self.project_root / ".agent_hub"
        self._fingerprints: Dict[str, Tuple[int, int]] = {}
        self._cached_snapshot: Optional[AgentHubSnapshot] = None

    @staticmethod
    def _select_project_root(project_root: Path | str | None) -> Path:
        """选择真正含有 Agent Hub 数据的根目录。

        打包版 EXE 可能放在 dist、webTools 或单独的 tools 目录，EXE 目录
        本身通常没有 .agent_hub。旧逻辑会因此正常打开空窗口。候选目录按
        显式配置、当前目录、EXE 目录及其父级逐级检查。
        """
        explicit = Path(project_root).absolute() if project_root else None
        candidates: List[Path] = []
        if cct is not None:
            configured = str(getattr(cct, "agent_hub_path", "") or "").strip()
            if configured:
                candidates.append(Path(configured).expanduser().absolute())
        if os.environ.get("INSTOCK_APP_ROOT"):
            candidates.append(Path(os.environ["INSTOCK_APP_ROOT"]).absolute())
        if explicit:
            candidates.append(explicit)
        # 源码开发环境：即使从快捷方式/其他 CWD 启动，也能稳定回到
        # stock_standalone 根目录。agent_hub_path 为空时使用此 fallback。
        if not getattr(sys, "frozen", False) and not hasattr(sys, "_MEIPASS"):
            # 默认开发路径（动态等价于）：
            # D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock_standalone
            # 这里不写死盘符，换机器/换工作区后仍可正确识别。
            candidates.append(Path(__file__).parent.parent.parent.absolute())
        for raw in (os.getcwd(), os.path.dirname(os.path.abspath(sys.executable))):
            p = Path(raw).absolute()
            candidates.extend([p, *list(p.parents)[:4]])

        seen: Set[str] = set()
        for candidate in candidates:
            key = os.path.normcase(os.path.normpath(str(candidate)))
            if key in seen:
                continue
            seen.add(key)
            hub = candidate / ".agent_hub"
            if hub.is_dir() and (
                (hub / "orchestrator.json").exists()
                or any(hub.iterdir())
            ):
                return candidate
        return explicit or Path(os.getcwd()).absolute()

    def _get_file_fp(self, path: Path) -> Tuple[int, int]:
        try:
            st = path.stat()
            return st.st_size, st.st_mtime_ns
        except OSError:
            return 0, 0

    def _update_fingerprints(self) -> None:
        key_paths = [
            self.hub_dir / "orchestrator.json",
            self.hub_dir / "dashboard" / "STATUS.md",
            self.hub_dir / "events" / "events.jsonl",
            self.hub_dir / "inbox",
            self.hub_dir / "running",
            self.hub_dir / "done",
            self.hub_dir / "archive",
        ]
        for p in key_paths:
            self._fingerprints[str(p)] = self._get_file_fp(p)

    def _has_changed(self) -> bool:
        """检查关键目录和文件的修改时间指纹是否变化"""
        key_paths = [
            self.hub_dir / "orchestrator.json",
            self.hub_dir / "dashboard" / "STATUS.md",
            self.hub_dir / "events" / "events.jsonl",
            self.hub_dir / "inbox",
            self.hub_dir / "running",
            self.hub_dir / "done",
            self.hub_dir / "archive",
        ]
        for p in key_paths:
            fp = self._get_file_fp(p)
            str_p = str(p)
            if self._fingerprints.get(str_p) != fp:
                return True
        return False

    def parse_task_file(self, file_path: Path, state: str) -> TaskMeta:
        """从 markdown 任务书中快速解析元数据"""
        task_id = "000"
        m = TASK_NAME_RE.match(file_path.name)
        if m:
            task_id = m.group("id")

        title = file_path.stem
        owner = "unassigned"
        priority = "P1"
        risk = "LOW"
        permission = "P2_CODE_LOW"
        created_at = ""

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            # 优先提取第一级标题或紧跟在 # Task 后的具体实施目标
            for i, line in enumerate(lines[:15]):
                line_s = line.strip()
                if line_s.startswith("# "):
                    heading = line_s[2:].strip()
                    if heading.lower() not in ("task", "任务"):
                        title = heading
                        break
                    # 若是一级标题仅为 '# Task'，则寻找紧随其后的首行有效业务说明
                    for follow in lines[i + 1:i + 8]:
                        follow_s = follow.strip()
                        if follow_s and not follow_s.startswith("#") and not follow_s.startswith("-"):
                            title = follow_s
                            break
                    if title != file_path.stem:
                        break

            for line in lines[:35]:
                line_str = line.strip()
                if line_str.startswith("- Task-ID:"):
                    task_id = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("- Owner:"):
                    owner = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("- Priority:"):
                    priority = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("- Risk:"):
                    risk = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("- Permission-Profile:"):
                    permission = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("- Created-At:"):
                    created_at = line_str.split(":", 1)[1].strip()
        except Exception:
            pass

        # 检查决策报告
        decision = "PENDING"
        dec_file = self.hub_dir / "decisions" / f"{task_id}_merge_report.md"
        if dec_file.is_file():
            try:
                dec_text = dec_file.read_text(encoding="utf-8", errors="replace")
                m_dec = re.search(r"Codex-Decision:\s*([A-Z_]+)", dec_text)
                if m_dec:
                    decision = m_dec.group(1)
            except Exception:
                pass
        elif state == "archive":
            decision = "APPROVED"

        # 检查心跳
        heartbeat = {}
        hb_file = self.hub_dir / "artifacts" / task_id / "worker_heartbeat.json"
        if hb_file.is_file():
            try:
                heartbeat = json.loads(hb_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 检查 agent_report.json
        report = {}
        rep_file = self.hub_dir / "artifacts" / task_id / "agent_report.json"
        if rep_file.is_file():
            try:
                report = json.loads(rep_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        mtime_str = ""
        try:
            mtime = file_path.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        return TaskMeta(
            task_id=task_id.zfill(3),
            title=title,
            state=state,
            file_path=file_path,
            owner=owner,
            priority=priority,
            risk=risk,
            permission=permission,
            created_at=created_at,
            updated_at=mtime_str,
            decision=decision,
            heartbeat=heartbeat,
            report=report,
            summary=report.get("summary", "")
        )

    def load_snapshot(self, force: bool = False) -> AgentHubSnapshot:
        """加载最新的多 Agent 体系状态快照"""
        if not force and self._cached_snapshot and not self._has_changed():
            return self._cached_snapshot

        snap = AgentHubSnapshot()
        snap.last_updated = datetime.now().timestamp()

        # 1. 编排配置
        cfg_path = self.hub_dir / "orchestrator.json"
        if cfg_path.is_file():
            try:
                snap.orchestrator_config = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # 2. 状态分类任务
        state_dirs = ("inbox", "running", "done", "archive")
        tasks_map = {
            "inbox": snap.inbox_tasks,
            "running": snap.running_tasks,
            "done": snap.done_tasks,
            "archive": snap.archive_tasks,
        }

        for state in state_dirs:
            s_dir = self.hub_dir / state
            if not s_dir.is_dir():
                continue
            for f in sorted(s_dir.glob("*.md")):
                if TASK_NAME_RE.match(f.name) and not f.name.endswith("_result.md"):
                    meta = self.parse_task_file(f, state)
                    tasks_map[state].append(meta)

        # 3. 解析事件流 events.jsonl
        events_path = self.hub_dir / "events" / "events.jsonl"
        events_list: List[Dict[str, Any]] = []
        if events_path.is_file():
            try:
                with events_path.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events_list.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                pass
        snap.events = events_list

        # 4. 计算打回次数
        rework_map: Dict[str, int] = {}
        for ev in events_list:
            if ev.get("action") == "reviewed_rework":
                tid = str(ev.get("task_id", "")).zfill(3)
                rework_map[tid] = rework_map.get(tid, 0) + 1

        all_tasks = snap.inbox_tasks + snap.running_tasks + snap.done_tasks + snap.archive_tasks
        for t in all_tasks:
            t.rework_count = rework_map.get(t.task_id, 0)

        # 5. 计算当前活跃 worker 状态
        if snap.running_tasks:
            running_t = snap.running_tasks[0]
            hb = running_t.heartbeat
            snap.active_worker_stats = {
                "task_id": running_t.task_id,
                "title": running_t.title,
                "status": hb.get("status", "RUNNING"),
                "elapsed": hb.get("elapsed_seconds", 0.0),
                "readonly_calls": hb.get("readonly_tool_calls", 0),
                "write_calls": hb.get("write_tool_calls", 0),
                "readonly_since_write": hb.get("readonly_calls_since_write", 0),
                "detail": hb.get("detail", ""),
                "model": snap.orchestrator_config.get("worker_model", "gemini-3.8-flash-high")
            }
        else:
            snap.active_worker_stats = {
                "status": "IDLE",
                "task_id": "None",
                "model": snap.orchestrator_config.get("worker_model", "gemini-3.8-flash-high")
            }

        self._cached_snapshot = snap
        self._update_fingerprints()
        return snap


class AgentHubMonitorDialog(QDialog):
    """
    高性能多 Agent 运行状态与任务实施进度全景监控弹窗
    """

    def __init__(self, parent=None, project_root: Path | str | None = None):
        super().__init__(parent)
        self.setWindowTitle("🤖 Agent Hub 多Agent实时运行状态与任务实施指挥监控")
        self.resize(1180, 780)
        self.setMinimumSize(920, 620)

        self.engine = AgentHubDataEngine(project_root)
        self.current_snapshot: Optional[AgentHubSnapshot] = None
        self.selected_task: Optional[TaskMeta] = None
        self.settings_file = self.engine.hub_dir / "monitor_ui_settings.json"

        # 加载持久化设置
        self.auto_refresh_enabled = True
        self.refresh_interval_sec = 2.5
        self._load_ui_settings()

        self._init_ui()
        self._setup_timer()
        self._setup_single_instance_server()
        self.refresh_data(force=True)

    def _setup_single_instance_server(self):
        """开启 QLocalServer 监听单实例唤醒指令，防止多进程多窗口重叠"""
        try:
            # 清理残留死管道
            QLocalServer.removeServer(AGENT_HUB_SINGLE_INSTANCE_SERVER)
            self._local_server = QLocalServer(self)
            self._local_server.newConnection.connect(self._on_local_connection)
            self._local_server.listen(AGENT_HUB_SINGLE_INSTANCE_SERVER)
        except Exception:
            self._local_server = None

    def _on_local_connection(self):
        """处理来自新启动进程的 IPC 消息"""
        if not hasattr(self, '_local_server') or not self._local_server:
            return
        client_sock = self._local_server.nextPendingConnection()
        if client_sock:
            client_sock.readyRead.connect(lambda: self._handle_local_data(client_sock))

    def _handle_local_data(self, sock: QLocalSocket):
        """读取客户端指令并置顶激活自身窗口"""
        try:
            msg = sock.readAll().data().decode("utf-8", errors="ignore")
            if "WAKEUP" in msg:
                self.activate_and_raise()
            sock.disconnectFromServer()
        except Exception:
            pass

    def activate_and_raise(self):
        """强力置顶并激活当前窗口（解决托盘最小化或窗口被遮挡）"""
        try:
            if self.isMinimized():
                self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
            # 若处于 Windows 环境，调用底层 force_topmost_activate_hwnd
            hwnd = int(self.winId()) if hasattr(self, 'winId') else 0
            if hwnd:
                try:
                    from . import core
                    core.force_topmost_activate_hwnd(hwnd)
                except Exception:
                    pass
        except Exception:
            pass

    def closeEvent(self, event):
        """关闭时释放 IPC 监听与定时器"""
        try:
            if hasattr(self, '_local_server') and self._local_server:
                self._local_server.close()
                QLocalServer.removeServer(AGENT_HUB_SINGLE_INSTANCE_SERVER)
        except Exception:
            pass
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)

    def _load_ui_settings(self):
        """从 .agent_hub/monitor_ui_settings.json 中读取持久化设置"""
        if self.settings_file.is_file():
            try:
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                self.auto_refresh_enabled = bool(data.get("auto_refresh_enabled", True))
                self.refresh_interval_sec = float(data.get("refresh_interval_sec", 2.5))
            except Exception:
                pass

    def _save_ui_settings(self):
        """持久化保存当前设置至 .agent_hub/monitor_ui_settings.json"""
        try:
            payload = {
                "auto_refresh_enabled": self.auto_refresh_enabled,
                "refresh_interval_sec": self.refresh_interval_sec,
                "updated_at": datetime.now().isoformat()
            }
            self.settings_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _setup_timer(self):
        """定时自动刷新引擎"""
        if not hasattr(self, 'timer'):
            self.timer = QTimer(self)
            self.timer.timeout.connect(lambda: self.refresh_data(force=False))

        if self.auto_refresh_enabled:
            interval_ms = max(500, int(self.refresh_interval_sec * 1000))
            self.timer.start(interval_ms)
        else:
            self.timer.stop()

    def _on_auto_refresh_toggled(self, state: int):
        """自动刷新开关切换"""
        self.auto_refresh_enabled = bool(state == Qt.CheckState.Checked.value or state == 2 or state is True)
        self._setup_timer()
        self._save_ui_settings()
        status_txt = "开启" if self.auto_refresh_enabled else "关闭"
        self.lbl_status.setText(f"自动刷新已{status_txt} (周期: {self.refresh_interval_sec}s)")

    def _on_interval_changed(self, index: int):
        """刷新时间选择切换"""
        interval_map = {0: 1.0, 1: 2.5, 2: 5.0, 3: 10.0, 4: 30.0}
        self.refresh_interval_sec = interval_map.get(index, 2.5)
        self._setup_timer()
        self._save_ui_settings()
        self.lbl_status.setText(f"刷新周期已更新为 {self.refresh_interval_sec} 秒并已持久化保存")

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f1f5f9;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QFrame#cardFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel {
                color: #cbd5e1;
            }
            QTableWidget {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                gridline-color: #334155;
                color: #f8fafc;
                selection-background-color: #38bdf8;
                selection-color: #0f172a;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                font-weight: bold;
                border: 1px solid #334155;
                padding: 4px;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 6px;
                color: #f8fafc;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QLineEdit, QComboBox {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 5px;
                color: #f8fafc;
                padding: 4px 8px;
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                background-color: #1e293b;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #0f172a;
                color: #94a3b8;
                padding: 6px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-size: 12px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-bottom: none;
            }
            QTextEdit {
                background-color: #090d16;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # 1. 顶部 Header 与 Agent 集群状态卡片
        main_layout.addLayout(self._create_top_header())
        main_layout.addWidget(self._create_cluster_cards_widget())

        # 2. 中间主分割区：上部任务流水看板，下部详细与轨迹
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(4)

        # 任务列表区
        task_list_container = QWidget()
        task_list_layout = QVBoxLayout(task_list_container)
        task_list_layout.setContentsMargins(0, 0, 0, 0)
        task_list_layout.setSpacing(6)

        task_list_layout.addLayout(self._create_filter_toolbar())
        self.task_table = self._create_task_table()
        task_list_layout.addWidget(self.task_table)

        splitter.addWidget(task_list_container)

        # 底部下钻区 (左侧事件时序，右侧产物详情)
        bottom_container = self._create_bottom_details_widget()
        splitter.addWidget(bottom_container)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        main_layout.addWidget(splitter, stretch=1)

        # 3. 底部操作状态栏
        main_layout.addLayout(self._create_bottom_statusbar())

    def _create_top_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("🛡️ ATS 多 Agent 协同与任务实施指挥中心")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_lbl)

        layout.addStretch()

        # 自动刷新开关
        self.chk_auto_refresh = QCheckBox("自动刷新")
        self.chk_auto_refresh.setStyleSheet("""
            QCheckBox {
                color: #cbd5e1;
                font-size: 12px;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)
        self.chk_auto_refresh.setChecked(self.auto_refresh_enabled)
        self.chk_auto_refresh.stateChanged.connect(self._on_auto_refresh_toggled)
        layout.addWidget(self.chk_auto_refresh)

        # 刷新时间间隔选择
        lbl_int = QLabel("间隔:")
        lbl_int.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(lbl_int)

        self.cb_interval = QComboBox()
        self.cb_interval.addItems(["1.0秒", "2.5秒", "5.0秒", "10秒", "30秒"])
        self.cb_interval.setFixedWidth(78)
        # 根据当前值回显
        interval_idx_map = {1.0: 0, 2.5: 1, 5.0: 2, 10.0: 3, 30.0: 4}
        curr_idx = interval_idx_map.get(self.refresh_interval_sec, 1)
        self.cb_interval.setCurrentIndex(curr_idx)
        self.cb_interval.currentIndexChanged.connect(self._on_interval_changed)
        layout.addWidget(self.cb_interval)

        self.lbl_last_refresh = QLabel("更新: --")
        self.lbl_last_refresh.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_last_refresh)

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setFixedWidth(70)
        btn_refresh.clicked.connect(lambda: self.refresh_data(force=True))
        layout.addWidget(btn_refresh)

        btn_backup = QPushButton("💾 极速备份")
        btn_backup.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        btn_backup.clicked.connect(self._on_backup_clicked)
        layout.addWidget(btn_backup)

        return layout

    def _create_cluster_cards_widget(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 卡片 1: Worker 状态
        self.card_worker = QFrame()
        self.card_worker.setObjectName("cardFrame")
        l1 = QVBoxLayout(self.card_worker)
        l1.setContentsMargins(10, 8, 10, 8)
        self.lbl_worker_title = QLabel("🤖 Antigravity Worker (执行端)")
        self.lbl_worker_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #38bdf8;")
        self.lbl_worker_desc = QLabel("状态: 空闲就绪 · 模型: --")
        self.lbl_worker_desc.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self.lbl_worker_budget = QLabel("工具调用: 0 读 / 0 写 (预算: 12)")
        self.lbl_worker_budget.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        l1.addWidget(self.lbl_worker_title)
        l1.addWidget(self.lbl_worker_desc)
        l1.addWidget(self.lbl_worker_budget)
        layout.addWidget(self.card_worker, stretch=1)

        # 卡片 2: Reviewer 状态
        self.card_reviewer = QFrame()
        self.card_reviewer.setObjectName("cardFrame")
        l2 = QVBoxLayout(self.card_reviewer)
        l2.setContentsMargins(10, 8, 10, 8)
        self.lbl_reviewer_title = QLabel("🧐 Codex Reviewer (审查端)")
        self.lbl_reviewer_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #c084fc;")
        self.lbl_reviewer_desc = QLabel("模型: gpt-5.6-luna (effort: low)")
        self.lbl_reviewer_desc.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self.lbl_reviewer_stat = QLabel("自动审查: 开启 · 熔断上限: 1 轮")
        self.lbl_reviewer_stat.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        l2.addWidget(self.lbl_reviewer_title)
        l2.addWidget(self.lbl_reviewer_desc)
        l2.addWidget(self.lbl_reviewer_stat)
        layout.addWidget(self.card_reviewer, stretch=1)

        # 卡片 3: Orchestrator 编排器
        self.card_orch = QFrame()
        self.card_orch.setObjectName("cardFrame")
        l3 = QVBoxLayout(self.card_orch)
        l3.setContentsMargins(10, 8, 10, 8)
        self.lbl_orch_title = QLabel("⚙️ Agent Orchestrator (编排枢纽)")
        self.lbl_orch_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #fbbf24;")
        self.lbl_orch_desc = QLabel("并发上限: 3 · 轮询: 5.0s")
        self.lbl_orch_desc.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self.lbl_orch_stat = QLabel("管道总任务: 0 (待办 0 / 运行 0 / 完成 0)")
        self.lbl_orch_stat.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        l3.addWidget(self.lbl_orch_title)
        l3.addWidget(self.lbl_orch_desc)
        l3.addWidget(self.lbl_orch_stat)
        layout.addWidget(self.card_orch, stretch=1)

        return container

    def _create_filter_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 状态分类 Tab 切换
        self.combo_state = QComboBox()
        self.combo_state.addItems(["全部状态", "📥 Inbox (待认领)", "⚡ Running (执行中)", "✅ Done (待审/完成)", "📦 Archive (已归档)"])
        self.combo_state.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self.combo_state)

        # 风险过滤
        self.combo_risk = QComboBox()
        self.combo_risk.addItems(["全部风险", "LOW (低风险)", "MEDIUM (中风险)", "HIGH (高风险)"])
        self.combo_risk.currentIndexChanged.connect(self._apply_filter)
        layout.addWidget(self.combo_risk)

        # 关键词搜索
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 搜索 Task ID、标题、负责人或摘要...")
        self.txt_search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.txt_search, stretch=1)

        self.lbl_match_count = QLabel("匹配: 0 项")
        self.lbl_match_count.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_match_count)

        return layout

    def _create_task_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "Task ID", "状态", "优先级", "风险", "负责人", "决策/审查", "打回轮数", "任务实施目标与标题"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        table.setColumnWidth(0, 75)
        table.setColumnWidth(1, 85)
        table.setColumnWidth(2, 65)
        table.setColumnWidth(3, 70)
        table.setColumnWidth(4, 90)
        table.setColumnWidth(5, 110)
        table.setColumnWidth(6, 75)

        table.itemSelectionChanged.connect(self._on_task_selected)
        return table

    def _create_bottom_details_widget(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # 左侧：任务流转时间线与事件流
        left_box = QFrame()
        left_box.setObjectName("cardFrame")
        l_layout = QVBoxLayout(left_box)
        l_layout.setContentsMargins(8, 6, 8, 6)
        lbl_ev = QLabel("⏱️ 任务流转时序与审计追踪")
        lbl_ev.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px;")
        l_layout.addWidget(lbl_ev)

        self.txt_timeline = QTextEdit()
        self.txt_timeline.setReadOnly(True)
        l_layout.addWidget(self.txt_timeline)
        layout.addWidget(left_box, stretch=4)

        # 右侧：文档与产物下钻
        right_box = QFrame()
        right_box.setObjectName("cardFrame")
        r_layout = QVBoxLayout(right_box)
        r_layout.setContentsMargins(8, 6, 8, 6)

        self.tab_artifacts = QTabWidget()

        # Tab 1: 任务书 (Task Spec)
        self.txt_task_doc = QTextEdit()
        self.txt_task_doc.setReadOnly(True)
        self.tab_artifacts.addTab(self.txt_task_doc, "📋 任务书")

        # Tab 2: 实施方案与结果 (Implementation)
        self.txt_impl_doc = QTextEdit()
        self.txt_impl_doc.setReadOnly(True)
        self.tab_artifacts.addTab(self.txt_impl_doc, "📝 实施报告")

        # Tab 3: 代码审查结果 (Codex Review)
        self.txt_review_doc = QTextEdit()
        self.txt_review_doc.setReadOnly(True)
        self.tab_artifacts.addTab(self.txt_review_doc, "🔍 审查意见")

        # Tab 4: 合并报告 (Merge Report)
        self.txt_merge_doc = QTextEdit()
        self.txt_merge_doc.setReadOnly(True)
        self.tab_artifacts.addTab(self.txt_merge_doc, "⚖️ 合并决策")

        # Tab 5: 统一主计划 (Master & Remediation Plan)
        self.txt_plan_doc = QTextEdit()
        self.txt_plan_doc.setReadOnly(True)
        self.tab_artifacts.addTab(self.txt_plan_doc, "🗺️ 总实施计划")

        r_layout.addWidget(self.tab_artifacts)
        layout.addWidget(right_box, stretch=6)

        return container

    def _create_bottom_statusbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        btn_open_artifacts = QPushButton("📂 打开当前任务产物目录")
        btn_open_artifacts.clicked.connect(self._on_open_artifacts_dir)
        layout.addWidget(btn_open_artifacts)

        btn_open_hub = QPushButton("📁 打开 .agent_hub 目录")
        btn_open_hub.clicked.connect(self._on_open_hub_dir)
        layout.addWidget(btn_open_hub)

        return layout

    def refresh_data(self, force: bool = False):
        """拉取最新数据并刷新视图"""
        try:
            snap = self.engine.load_snapshot(force=force)
            self.current_snapshot = snap
            self.lbl_last_refresh.setText(f"更新: {datetime.now().strftime('%H:%M:%S')}")
            self._render_cluster_cards(snap)
            self._render_task_table(snap)
        except Exception as e:
            self.lbl_status.setText(f"刷新异常: {e}")

    def _render_cluster_cards(self, snap: AgentHubSnapshot):
        # 1. Worker 卡片
        w_stats = snap.active_worker_stats
        w_status = w_stats.get("status", "IDLE")
        w_model = w_stats.get("model", "--")
        if w_status == "IDLE":
            self.lbl_worker_desc.setText(f"状态: ⚪ 空闲就绪 · 模型: {w_model}")
            self.lbl_worker_budget.setText("工具调用: 0 读 / 0 写 (未在执行)")
        else:
            tid = w_stats.get("task_id", "")
            elapsed = w_stats.get("elapsed", 0.0)
            r_calls = w_stats.get("readonly_calls", 0)
            w_calls = w_stats.get("write_calls", 0)
            r_since = w_stats.get("readonly_since_write", 0)
            color = "#22c55e" if w_status in ("RUNNING", "SUCCESS") else "#f59e0b"
            self.lbl_worker_desc.setText(f"状态: <b style='color:{color}'>{w_status}</b> (Task {tid}) · 耗时: {elapsed:.1f}s")
            self.lbl_worker_budget.setText(f"工具调用: {r_calls} 读 / {w_calls} 写 (连续读: {r_since})")

        # 2. Reviewer 卡片
        rev_prof = snap.orchestrator_config.get("review_profiles", {}).get("task_review", {})
        rev_model = rev_prof.get("model", "gpt-5.6-luna")
        rev_effort = rev_prof.get("effort", "low")
        max_rework = snap.orchestrator_config.get("max_rework_cycles", 1)
        auto_rev = snap.orchestrator_config.get("auto_review", True)
        self.lbl_reviewer_desc.setText(f"模型: {rev_model} (effort: {rev_effort})")
        self.lbl_reviewer_stat.setText(f"自动审查: {'🟢 开启' if auto_rev else '⚪ 关闭'} · 熔断上限: {max_rework} 轮")

        # 3. Orchestrator 卡片
        max_workers = snap.orchestrator_config.get("batch_max_workers", 3)
        poll_sec = snap.orchestrator_config.get("worker_monitor_interval_seconds", 5.0)
        n_inbox = len(snap.inbox_tasks)
        n_run = len(snap.running_tasks)
        n_done = len(snap.done_tasks)
        n_arch = len(snap.archive_tasks)
        total = n_inbox + n_run + n_done + n_arch
        self.lbl_orch_desc.setText(f"并发上限: {max_workers} · 轮询: {poll_sec}s")
        self.lbl_orch_stat.setText(f"管道总任务: {total} (待办 {n_inbox} / 运行 {n_run} / 待审 {n_done} / 归档 {n_arch})")

    def _render_task_table(self, snap: AgentHubSnapshot):
        current_sel_id = self.selected_task.task_id if self.selected_task else None

        all_tasks = snap.inbox_tasks + snap.running_tasks + snap.done_tasks + snap.archive_tasks
        # 按 task_id 排序
        all_tasks.sort(key=lambda x: x.task_id, reverse=True)

        state_filter = self.combo_state.currentIndex()
        risk_filter = self.combo_risk.currentText()
        search_kw = self.txt_search.text().strip().lower()

        filtered: List[TaskMeta] = []
        for t in all_tasks:
            # 状态过滤
            if state_filter == 1 and t.state != "inbox":
                continue
            elif state_filter == 2 and t.state != "running":
                continue
            elif state_filter == 3 and t.state != "done":
                continue
            elif state_filter == 4 and t.state != "archive":
                continue

            # 风险过滤
            if "LOW" in risk_filter and t.risk != "LOW":
                continue
            elif "MEDIUM" in risk_filter and t.risk != "MEDIUM":
                continue
            elif "HIGH" in risk_filter and t.risk != "HIGH":
                continue

            # 关键字过滤
            if search_kw:
                matchable = f"{t.task_id} {t.title} {t.owner} {t.summary}".lower()
                if search_kw not in matchable:
                    continue

            filtered.append(t)

        self.lbl_match_count.setText(f"匹配: {len(filtered)} / {len(all_tasks)} 项")

        self.task_table.setRowCount(len(filtered))
        target_row_to_select = -1

        for row, t in enumerate(filtered):
            if current_sel_id and t.task_id == current_sel_id:
                target_row_to_select = row

            item_id = QTableWidgetItem(t.task_id)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setData(Qt.ItemDataRole.UserRole, t)

            # 状态渲染
            state_text = {
                "inbox": "📥 待认领",
                "running": "⚡ 运行中",
                "done": "✅ 待审/完成",
                "archive": "📦 已归档"
            }.get(t.state, t.state)
            item_state = QTableWidgetItem(state_text)
            item_state.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_pri = QTableWidgetItem(t.priority)
            item_pri.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_risk = QTableWidgetItem(t.risk)
            item_risk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if t.risk == "HIGH":
                item_risk.setForeground(QtGui.QBrush(QtGui.QColor("#ef4444")))
            elif t.risk == "MEDIUM":
                item_risk.setForeground(QtGui.QBrush(QtGui.QColor("#f59e0b")))
            else:
                item_risk.setForeground(QtGui.QBrush(QtGui.QColor("#10b981")))

            item_owner = QTableWidgetItem(t.owner)
            item_owner.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 决策 / 审查结论
            dec_text = t.decision
            if dec_text == "APPROVED":
                dec_text = "🟢 APPROVED"
            elif dec_text == "REWORK_BLOCKED_FOR_HUMAN":
                dec_text = "🛑 熔断等待人工"
            elif dec_text == "REWORK":
                dec_text = "🟡 REWORK"
            item_dec = QTableWidgetItem(dec_text)
            item_dec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 打回轮数
            rework_str = f"{t.rework_count} 次" if t.rework_count > 0 else "-"
            item_rework = QTableWidgetItem(rework_str)
            item_rework.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if t.rework_count >= 1:
                item_rework.setForeground(QtGui.QBrush(QtGui.QColor("#f43f5e")))

            item_title = QTableWidgetItem(t.title)

            self.task_table.setItem(row, 0, item_id)
            self.task_table.setItem(row, 1, item_state)
            self.task_table.setItem(row, 2, item_pri)
            self.task_table.setItem(row, 3, item_risk)
            self.task_table.setItem(row, 4, item_owner)
            self.task_table.setItem(row, 5, item_dec)
            self.task_table.setItem(row, 6, item_rework)
            self.task_table.setItem(row, 7, item_title)

        if target_row_to_select >= 0:
            self.task_table.selectRow(target_row_to_select)
        elif len(filtered) > 0 and self.task_table.currentRow() < 0:
            self.task_table.selectRow(0)

    def _apply_filter(self):
        if self.current_snapshot:
            self._render_task_table(self.current_snapshot)

    def _on_task_selected(self):
        row = self.task_table.currentRow()
        if row < 0:
            return
        item_id = self.task_table.item(row, 0)
        if not item_id:
            return
        task: TaskMeta = item_id.data(Qt.ItemDataRole.UserRole)
        if not task:
            return
        self.selected_task = task
        self._render_task_details(task)

    def _render_task_details(self, task: TaskMeta):
        """在下方双栏渲染选中任务的流转时间线与产物文档"""
        self.lbl_status.setText(f"当前选中: Task {task.task_id} - {task.title} [{task.state.upper()}]")

        # 1. 渲染流转时间线
        events = [e for e in self.current_snapshot.events if str(e.get("task_id", "")).zfill(3) == task.task_id]
        tl_lines = []
        if not events:
            tl_lines.append(f"⏱️ Task {task.task_id} 尚未捕获历史事件记录。")
            tl_lines.append(f"• 创建时间: {task.created_at or '--'}")
            tl_lines.append(f"• 状态: {task.state}")
            tl_lines.append(f"• 更新时间: {task.updated_at}")
        else:
            tl_lines.append(f"<b>Task {task.task_id} 关键实施与流转轨迹 ({len(events)} 项事件):</b><br>")
            for ev in events:
                ts = ev.get("timestamp", "").replace("T", " ")[:19]
                act = ev.get("action", "")
                actor = ev.get("actor", "")
                f_st = ev.get("from_state", "")
                t_st = ev.get("to_state", "")
                reason = ev.get("reason", "")

                icon = "🔹"
                if "claimed" in act:
                    icon = "🚀"
                elif "submitted" in act:
                    icon = "📤"
                elif "approved" in act:
                    icon = "🟢"
                elif "rework" in act:
                    icon = "⚠️"
                elif "blocked" in act:
                    icon = "🛑"

                line = f"{icon} <code>{ts}</code> [<b>{act}</b>] by <i>{actor}</i>"
                if f_st and t_st:
                    line += f" ({f_st} &rarr; {t_st})"
                if reason:
                    line += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;↳ <i>原因: {reason}</i>"
                tl_lines.append(line)

        # 附加心跳概览
        if task.heartbeat:
            hb = task.heartbeat
            tl_lines.append("<hr><b>最新执行心跳 (Worker Heartbeat):</b>")
            tl_lines.append(f"• 状态: <b>{hb.get('status', '--')}</b> · 耗时: {hb.get('elapsed_seconds', 0.0)}s")
            tl_lines.append(f"• 只读工具: {hb.get('readonly_tool_calls', 0)} · 写入工具: {hb.get('write_tool_calls', 0)}")
            if hb.get("detail"):
                tl_lines.append(f"• 详情: <i>{hb.get('detail')}</i>")

        self.txt_timeline.setHtml("<br>".join(tl_lines))

        # 2. 渲染右侧 Tab
        # Tab 1: 任务书
        try:
            t_content = task.file_path.read_text(encoding="utf-8", errors="replace")
            header = f"# [{task.file_path.name}]\n\n"
            self.txt_task_doc.setPlainText(header + t_content)
        except Exception as e:
            self.txt_task_doc.setPlainText(f"无法读取任务书文件: {e}")

        # Tab 2: 实施报告 / agent_report.json / walkthrough
        artifact_dir = self.engine.hub_dir / "artifacts" / task.task_id
        impl_parts = []
        if task.report:
            impl_parts.append(f"【结构化 Agent 报告】\n{json.dumps(task.report, ensure_ascii=False, indent=2)}\n")

        walkthrough_f = artifact_dir / "walkthrough.md"
        if walkthrough_f.is_file():
            impl_parts.append(f"【Walkthrough 总结】\n{walkthrough_f.read_text(encoding='utf-8', errors='replace')}\n")

        test_res_f = artifact_dir / "test_result.md"
        if test_res_f.is_file():
            impl_parts.append(f"【测试验证记录】\n{test_res_f.read_text(encoding='utf-8', errors='replace')}\n")

        if not impl_parts:
            self.txt_impl_doc.setPlainText("暂无实施报告产物 (Task 尚未执行或产物未生成)")
        else:
            self.txt_impl_doc.setPlainText("\n----------------------------------------\n".join(impl_parts))

        # Tab 3: 代码审查意见 (codex_review.md)
        review_f = self.engine.hub_dir / "review" / f"{task.task_id}_review.md"
        if not review_f.is_file():
            review_f = artifact_dir / "codex_review.md"

        if review_f.is_file():
            try:
                self.txt_review_doc.setPlainText(review_f.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                self.txt_review_doc.setPlainText(f"读取审查报告失败: {e}")
        else:
            self.txt_review_doc.setPlainText("暂无 Codex 审查意见文件")

        # Tab 4: 合并报告 (merge_report.md)
        merge_f = self.engine.hub_dir / "decisions" / f"{task.task_id}_merge_report.md"
        if merge_f.is_file():
            try:
                self.txt_merge_doc.setPlainText(merge_f.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                self.txt_merge_doc.setPlainText(f"读取合并决策失败: {e}")
        else:
            self.txt_merge_doc.setPlainText("暂无独立 Merge Report")

        # Tab 5: 统一主计划 (优先加载当前修复计划并说明当前状态)
        plan_file = self.engine.project_root / "docs" / "MULTI_AGENT_SIGNAL_T1_REMEDIATION_EXECUTION_PLAN_2026-09-22.md"
        master_file = self.engine.hub_dir / "master_plan.md"
        plan_text_parts = []
        if plan_file.is_file():
            plan_text_parts.append(f"【当前执行的最高实施计划: {plan_file.name}】\n" + plan_file.read_text(encoding="utf-8", errors="replace"))
        if master_file.is_file():
            plan_text_parts.append(f"【Agent Hub 基础主计划: {master_file.name}】\n" + master_file.read_text(encoding="utf-8", errors="replace"))
        self.txt_plan_doc.setPlainText("\n\n============================================================\n\n".join(plan_text_parts))

    def _on_open_artifacts_dir(self):
        """在文件管理器中打开当前选定任务的产物目录"""
        if not self.selected_task:
            QMessageBox.information(self, "提示", "请先在上方表格选中一个任务！")
            return
        target = self.engine.hub_dir / "artifacts" / self.selected_task.task_id
        target.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(target))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{e}")

    def _on_open_hub_dir(self):
        """在文件管理器中打开 .agent_hub 根目录"""
        try:
            os.startfile(str(self.engine.hub_dir))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{e}")

    def _on_backup_clicked(self):
        """一键调用 backup_agent_tasks 脚本触发极速备份"""
        backup_script = self.engine.project_root / "tools" / "backup_agent_tasks.py"
        if not backup_script.is_file():
            QMessageBox.warning(self, "文件缺失", f"未找到备份脚本: {backup_script}")
            return
        try:
            self.lbl_status.setText("正在执行多 Agent 配置极速双轨备份...")
            QtWidgets.QApplication.processEvents()
            res = subprocess.run(
                [sys.executable, str(backup_script)],
                capture_output=True,
                text=True,
                timeout=20
            )
            if res.returncode == 0:
                self.lbl_status.setText("✅ 备份完成！(RamDisk & E盘最新指针已更新)")
                QMessageBox.information(self, "备份成功", "已成功为多 Agent 配置与任务体系生成双轨持久化备份！")
            else:
                self.lbl_status.setText("⚠️ 备份执行异常")
                QMessageBox.warning(self, "备份异常", f"执行异常:\n{res.stderr or res.stdout}")
        except Exception as e:
            self.lbl_status.setText(f"备份失败: {e}")
            QMessageBox.critical(self, "备份失败", str(e))


def main(project_root: Path | str | None = None):
    """独立测试/子进程启动入口（支持单实例互斥与已有实例前台置顶激活）"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    
    # 单实例检查：若已有运行中的 Agent Hub 监控器，直接唤醒置顶并退出当前新进程
    if activate_existing_agent_hub_instance(timeout_ms=350):
        sys.exit(0)

    dialog = AgentHubMonitorDialog(project_root=project_root)
    dialog.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
