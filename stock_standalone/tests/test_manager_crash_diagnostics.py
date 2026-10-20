# -*- coding: utf-8 -*-
"""
单元测试：桌面窗口管理器全生命周期崩溃诊断、异常捕获与安全流验证
"""

import os
import sys
import time
import json
import logging
import threading
import faulthandler
import tempfile
import pytest

# 确保 stock_standalone 在 sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from webTools.window_manager.manager_crash_diagnostics import (
    SafeStream,
    ManagerDiagnostics,
    setup_manager_logger
)


def test_safe_stream_basic(tmp_path):
    """测试 SafeStream 在无控制台下的安全性与落盘能力"""
    target_file = tmp_path / "test_stream.log"
    stream = SafeStream(target_file_path=str(target_file))

    # 测试正常写入
    n = stream.write("Hello SafeStream!\n")
    assert n > 0
    stream.flush()
    assert stream.isatty() is False

    with open(target_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Hello SafeStream!" in content


def test_manager_diagnostics_lifecycle_audit(tmp_path):
    """测试进程生命周期审计记录 (START, LIFECYCLE, EXIT)"""
    diag = ManagerDiagnostics(str(tmp_path))
    diag.install()

    crash_log = tmp_path / "crash.log"
    assert crash_log.exists()

    # 验证 START 审计记录
    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[LIFECYCLE]" in content
    assert '"event": "START"' in content
    assert f'"pid": {os.getpid()}' in content

    # 记录自定义事件
    diag.record_lifecycle("CUSTOM_EVENT", {"detail": "test_ok"})
    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()
    assert '"event": "CUSTOM_EVENT"' in content
    assert "test_ok" in content

    # 测试受控退出
    diag.shutdown(exit_source="TEST_SHUTDOWN", exit_code=0)
    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()
    assert '"event": "EXIT"' in content
    assert '"exit_source": "TEST_SHUTDOWN"' in content
    assert not faulthandler.is_enabled()


def test_sys_excepthook_logging(tmp_path):
    """测试主线程未捕获异常落盘至 crash.log"""
    diag = ManagerDiagnostics(str(tmp_path))
    diag.install()

    crash_log = tmp_path / "crash.log"

    # 模拟未捕获异常调用 sys.excepthook
    try:
        raise ValueError("Simulated main thread crash!")
    except ValueError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_val, exc_tb)

    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()

    assert "主线程未捕获致命异常" in content
    assert "ValueError: Simulated main thread crash!" in content
    assert "CRASH_EXIT_MAIN_THREAD" in content


def test_threading_excepthook_logging(tmp_path, monkeypatch):
    """测试子线程未捕获异常落盘至 crash.log"""
    if not hasattr(threading, "excepthook"):
        pytest.skip("threading.excepthook requires Python 3.8+")

    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    diag = ManagerDiagnostics(str(tmp_path))
    diag.install()

    crash_log = tmp_path / "crash.log"

    class DummyArgs:
        def __init__(self, exc_type, exc_value, exc_traceback, thread):
            self.exc_type = exc_type
            self.exc_value = exc_value
            self.exc_traceback = exc_traceback
            self.thread = thread

    try:
        raise RuntimeError("Simulated worker thread exception!")
    except RuntimeError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        dummy_thread = threading.Thread(name="TestWorkerThread")
        args = DummyArgs(exc_type, exc_val, exc_tb, dummy_thread)
        threading.excepthook(args)

    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()

    assert "子线程未捕获异常" in content
    assert "TestWorkerThread" in content
    assert "RuntimeError: Simulated worker thread exception!" in content


def test_qt_message_handler_safe_when_stderr_none(tmp_path, monkeypatch):
    """测试在 GUI 模式下 sys.stderr 为 None 时 Qt 消息处理器的零崩溃与落盘"""
    try:
        from PyQt6 import QtCore
        from PyQt6.QtCore import QtMsgType
    except ImportError:
        pytest.skip("PyQt6 not available")

    captured = {}
    monkeypatch.setattr(QtCore, "qInstallMessageHandler", lambda handler: captured.update(handler=handler))

    diag = ManagerDiagnostics(str(tmp_path))
    diag.install()

    crash_log = tmp_path / "crash.log"
    monkeypatch.setattr(sys, "stderr", None)
    captured["handler"](QtMsgType.QtCriticalMsg, None, "Test critical message without stderr")

    with open(crash_log, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Test critical message without stderr" in content


def test_setup_manager_logger_rotation(tmp_path):
    """测试日志记录器自动配置 RotatingFileHandler"""
    test_logger_name = f"TestWindowManager_{int(time.time())}"
    logger = setup_manager_logger(str(tmp_path), logger_name=test_logger_name)

    assert logger is not None
    assert logger.level == logging.INFO
    assert len(logger.handlers) >= 1

    # 验证写入
    logger.info("Test rotation logger entry 1")
    logger.warning("Test rotation warning entry 2")

    log_file = tmp_path / "window_layout.log"
    assert log_file.exists()

    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Test rotation logger entry 1" in content
    assert "Test rotation warning entry 2" in content


def test_ui_log_thread_safety():
    """测试 ui.log 遇到跨线程调用时自动通过 log_signal 转发，保护主线程 GUI 控件"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QObject, pyqtSignal, QThread
    except ImportError:
        pytest.skip("PyQt6 not available")

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from webTools.window_manager.ui import WindowPosManagerUI

    received = []

    class MockUI(QObject):
        log_signal = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.log_signal.connect(self._on_log_signal)
            self.log_output_called = False

        def _on_log_signal(self, txt):
            received.append(txt)

    mock_ui = MockUI()

    # 在子线程中调用生产类的 log 实现
    def worker():
        WindowPosManagerUI.log(mock_ui, "Background log message")

    th = threading.Thread(target=worker)
    th.start()
    th.join()

    # 处理 Qt 事件队列
    app.processEvents()

    assert mock_ui.log_output_called is False, "log_output 不应在后台线程被直接调用！"
    assert "Background log message" in received, "跨线程日志应成功被 log_signal 捕获！"
