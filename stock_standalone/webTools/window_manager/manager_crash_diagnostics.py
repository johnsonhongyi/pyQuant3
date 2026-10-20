# -*- coding: utf-8 -*-
"""
桌面窗口管理器 - 全生命周期崩溃诊断与审计加固模块 (Manager Crash Diagnostics)

核心能力：
1. 底层原生崩溃捕获：通过 faulthandler 捕获 C/C++ 访问冲突 (0xC0000005) 及段错误，将各线程堆栈落盘至 crash.log。
2. Python 主线程及子线程未捕获异常监控：挂载 sys.excepthook 与 threading.excepthook，杜绝静默闪退。
3. Qt 致命消息安全接线：解决 GUI 无控制台打包模式下 sys.stderr 为 None 导致的 AttributeError 闪退，防递归落盘。
4. 进程生命周期审计记录：启动（PID、PPID、启动模式、参数）、退出（退出来源、退出码、运行耗时）100% 可回溯。
5. 控制台与日志编码保护：提供安全回退流 SafeStream，杜绝 Emoji/GBK 编码崩溃。
"""

from __future__ import annotations

import os
import sys
import time
import json
import atexit
import logging
from logging.handlers import RotatingFileHandler
import threading
import traceback
import faulthandler
from typing import Optional, Any, TextIO


class SafeStream:
    """
    针对 Windows GUI 打包模式 (console=False) 下 sys.stdout / sys.stderr 为 None 的安全替代流。
    提供标准流接口，确保任何第三方库或内部代码调用 stream.write / flush 时不会抛出 AttributeError。
    """
    def __init__(self, target_file_path: Optional[str] = None, fallback_stream: Optional[TextIO] = None):
        self._target_file_path = target_file_path
        self._fallback_stream = fallback_stream
        self.encoding = "utf-8"
        self._lock = threading.Lock()

    def write(self, s: str) -> int:
        if not s:
            return 0
        written = 0
        # 1. 尝试写入 fallback_stream (若存在且未关闭)
        if self._fallback_stream and hasattr(self._fallback_stream, "write"):
            try:
                written = self._fallback_stream.write(s)
            except Exception:
                pass
        # 2. 尝试写入持久化诊断文件 (若指定)
        if self._target_file_path:
            with self._lock:
                try:
                    with open(self._target_file_path, "a", encoding="utf-8", errors="replace") as f:
                        f.write(s)
                except Exception:
                    pass
        return written if written > 0 else len(s)

    def flush(self):
        if self._fallback_stream and hasattr(self._fallback_stream, "flush"):
            try:
                self._fallback_stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False

    def reconfigure(self, **kwargs):
        pass


class ManagerDiagnostics:
    """管理器全局单例诊断控制器"""
    _instance: Optional[ManagerDiagnostics] = None
    _lock = threading.Lock()

    def __init__(self, app_root: str):
        self.app_root = os.path.abspath(app_root)
        self.crash_log_path = os.path.join(self.app_root, "crash.log")
        self.main_log_path = os.path.join(self.app_root, "window_layout.log")
        self.start_time = time.time()
        self._faulthandler_file: Optional[TextIO] = None
        self._faulthandler_enabled = False
        self._installed = False
        self._has_exited = False
        self._atexit_registered = False
        self._qt_recursion_guard = threading.local()

    @classmethod
    def get_instance(cls, app_root: Optional[str] = None) -> ManagerDiagnostics:
        with cls._lock:
            if cls._instance is None:
                if not app_root:
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    app_root = os.path.dirname(current_dir)
                cls._instance = cls(app_root)
            return cls._instance

    def install(self):
        """安装所有崩溃捕获钩子与诊断通道"""
        with self._lock:
            if self._installed:
                return
            self._installed = True

            # 1. 确保标准输出流在 console=False 时安全存在
            self._ensure_safe_streams()

            # 2. 启用 faulthandler (原生崩溃和段错误捕获)
            self._enable_faulthandler()

            # 3. 挂载 sys.excepthook (主线程未捕获异常)
            self._install_sys_excepthook()

            # 4. 挂载 threading.excepthook (子线程未捕获异常)
            self._install_threading_excepthook()

            # 5. 挂载安全的 Qt 消息处理器
            self._install_qt_message_handler()

            # 6. 注册 atexit 兜底审计
            if not self._atexit_registered:
                atexit.register(self._on_process_atexit)
                self._atexit_registered = True

            # 7. 记录启动审计事件
            self.record_lifecycle("START", {
                "pid": os.getpid(),
                "ppid": os.getppid() if hasattr(os, "getppid") else None,
                "argv": sys.argv,
                "python_version": sys.version.split()[0],
                "is_frozen": getattr(sys, "frozen", False),
                "cwd": os.getcwd(),
                "app_root": self.app_root
            })

    def _ensure_safe_streams(self):
        """确保 sys.stdout 和 sys.stderr 安全可用"""
        if sys.stdout is None:
            sys.stdout = SafeStream(target_file_path=self.main_log_path)
        else:
            if hasattr(sys.stdout, "reconfigure"):
                try:
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        if sys.stderr is None:
            sys.stderr = SafeStream(target_file_path=self.crash_log_path, fallback_stream=sys.stdout)
        else:
            if hasattr(sys.stderr, "reconfigure"):
                try:
                    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    def _enable_faulthandler(self):
        """启用 Python faulthandler 实时捕获 C/C++ 内存段错误"""
        try:
            self._faulthandler_file = open(self.crash_log_path, "a", encoding="utf-8", errors="replace", buffering=1)
            faulthandler.enable(file=self._faulthandler_file, all_threads=True)
            self._faulthandler_enabled = True
        except Exception as e:
            self._write_crash_log(f"[DIAGNOSTICS_INIT_FAIL] faulthandler.enable failed: {e}\n")

    def _install_sys_excepthook(self):
        """主线程未捕获异常钩子"""
        old_excepthook = sys.excepthook

        def _manager_sys_excepthook(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                if old_excepthook:
                    old_excepthook(exc_type, exc_value, exc_traceback)
                return

            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            msg = (
                f"\n{'='*70}\n"
                f"[{now_str}] 💥 [FATAL CRASH] 主线程未捕获致命异常 (PID: {os.getpid()})\n"
                f"异常类型: {exc_type.__name__}: {exc_value}\n"
                f"调用栈追踪:\n{tb_str}"
                f"{'='*70}\n"
            )
            self._write_crash_log(msg)
            self._log_to_main_logger(logging.CRITICAL, msg)
            self.record_lifecycle("CRASH_EXIT_MAIN_THREAD", {
                "exc_type": exc_type.__name__,
                "exc_msg": str(exc_value)
            })

            if old_excepthook and old_excepthook != _manager_sys_excepthook:
                try:
                    old_excepthook(exc_type, exc_value, exc_traceback)
                except Exception:
                    pass

        sys.excepthook = _manager_sys_excepthook

    def _install_threading_excepthook(self):
        """子线程未捕获异常钩子 (Python 3.8+)"""
        if not hasattr(threading, "excepthook"):
            return

        old_thread_excepthook = threading.excepthook

        def _manager_threading_excepthook(args):
            exc_type = args.exc_type
            exc_value = args.exc_value
            exc_traceback = args.exc_traceback
            thread_name = args.thread.name if args.thread else "UnknownThread"
            thread_id = args.thread.ident if args.thread else None

            if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                return

            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            msg = (
                f"\n{'='*70}\n"
                f"[{now_str}] ⚠️ [FATAL THREAD EXCEPTION] 子线程未捕获异常\n"
                f"线程名: {thread_name} (ID: {thread_id}, PID: {os.getpid()})\n"
                f"异常类型: {exc_type.__name__}: {exc_value}\n"
                f"调用栈追踪:\n{tb_str}"
                f"{'='*70}\n"
            )
            self._write_crash_log(msg)
            self._log_to_main_logger(logging.ERROR, msg)

            if old_thread_excepthook and old_thread_excepthook != _manager_threading_excepthook:
                try:
                    old_thread_excepthook(args)
                except Exception:
                    pass

        threading.excepthook = _manager_threading_excepthook

    def _install_qt_message_handler(self):
        """挂载健壮且防递归的 Qt 消息处理器"""
        try:
            from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        except ImportError:
            return

        def _qt_message_handler(mode, context, message):
            if getattr(self._qt_recursion_guard, "active", False):
                return
            self._qt_recursion_guard.active = True

            try:
                if any(k in message for k in ("DirectWrite", "CreateFontFaceFromHDC", "QFontDef", "Fixedsys", "Terminal")):
                    return

                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                if mode == QtMsgType.QtFatalMsg:
                    level_tag = "FATAL"
                    log_func = logging.CRITICAL
                elif mode == QtMsgType.QtCriticalMsg:
                    level_tag = "CRITICAL"
                    log_func = logging.ERROR
                elif mode == QtMsgType.QtWarningMsg:
                    level_tag = "WARNING"
                    log_func = logging.WARNING
                else:
                    return

                formatted = f"[{now_str}] [Qt {level_tag}] {message}\n"

                if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                    self._write_crash_log(formatted)

                self._log_to_main_logger(log_func, f"[Qt {level_tag}] {message}")

                if sys.stderr and hasattr(sys.stderr, "write"):
                    try:
                        sys.stderr.write(formatted)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._qt_recursion_guard.active = False

        try:
            qInstallMessageHandler(_qt_message_handler)
        except Exception as e:
            self._write_crash_log(f"[DIAGNOSTICS_INIT_FAIL] qInstallMessageHandler failed: {e}\n")

    def _write_crash_log(self, text: str):
        """无锁、原子追加写入 crash.log"""
        try:
            with open(self.crash_log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(text)
                f.flush()
        except Exception:
            pass

    def _log_to_main_logger(self, level: int, text: str):
        """写入主日志记录器，带流关闭检测"""
        try:
            logger = logging.getLogger("WindowManager")
            if logger and logger.handlers:
                # 检查 handlers 是否已经关闭 (避免 atexit 期间的 ValueError)
                for h in logger.handlers:
                    stream = getattr(h, "stream", None)
                    if stream and getattr(stream, "closed", False):
                        return
                logger.log(level, text)
        except Exception:
            pass

    def record_lifecycle(self, event: str, details: Optional[dict] = None):
        """记录进程生命周期审计标记"""
        now = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        uptime = round(now - self.start_time, 2)
        payload = {
            "timestamp": now_str,
            "event": event,
            "pid": os.getpid(),
            "uptime_sec": uptime
        }
        if details:
            payload.update(details)

        line = f"[{now_str}] [LIFECYCLE] {json.dumps(payload, ensure_ascii=False)}\n"
        self._write_crash_log(line)
        self._log_to_main_logger(logging.INFO, f"[LIFECYCLE:{event}] (Uptime: {uptime}s) {details or ''}")

    def shutdown(self, exit_source: str = "NORMAL", exit_code: int = 0):
        """记录正常或受控退出审计"""
        with self._lock:
            if self._has_exited:
                return
            self._has_exited = True

        self.record_lifecycle("EXIT", {
            "exit_source": exit_source,
            "exit_code": exit_code
        })
        if self._faulthandler_file:
            try:
                if self._faulthandler_enabled:
                    faulthandler.disable()
                    self._faulthandler_enabled = False
                self._faulthandler_file.flush()
                self._faulthandler_file.close()
                self._faulthandler_file = None
            except Exception:
                pass

    def _on_process_atexit(self):
        """解释器退出兜底钩子"""
        if not self._has_exited:
            try:
                self.shutdown(exit_source="ATEXIT_FALLBACK", exit_code=0)
            except Exception:
                pass


def setup_manager_logger(app_root: str, logger_name: str = "WindowManager") -> logging.Logger:
    """
    配置带有自动轮转 (RotatingFileHandler) 的安全日志记录器。
    单文件 10MB，保留 5 个历史切片，彻底消除日志无限膨胀及无控制台写入失败。
    """
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)d): %(message)s',
            datefmt='%m-%d %H:%M:%S'
        )

        # 1. 控制台 Handler：GUI 无控制台时 SafeStream 已把 stdout 写入主日志，
        #    再挂 StreamHandler 会造成同一条日志重复落盘并绕过轮转。
        if sys.stdout is not None and not isinstance(sys.stdout, SafeStream):
            try:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
            except Exception:
                pass

        # 2. 轮转文件 Handler (10MB x 5 backups)
        try:
            log_file = os.path.join(app_root, "window_layout.log")
            rotating_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
                delay=True
            )
            rotating_handler.setFormatter(formatter)
            logger.addHandler(rotating_handler)
        except Exception as e:
            if sys.stderr and hasattr(sys.stderr, "write"):
                try:
                    sys.stderr.write(f"[WARN] Failed to setup RotatingFileHandler: {e}\n")
                except Exception:
                    pass

    return logger
