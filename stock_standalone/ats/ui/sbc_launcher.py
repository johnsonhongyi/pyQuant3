# -*- coding: utf-8 -*-
"""
SBC Process Launcher & Lifecycle Manager
----------------------------------------
提供 SBC 实盘分时走势独立子进程启动器与统一生命周期管理：
1. 【独立持仓盯盘】以独立进程启动 run_sbc.py，专用于持仓盯盘，使用独立持久化配置 (config/sbc_launcher_holdings_layout.json)；
2. 【二次点击统一关闭】二次点击一键弹出确认统一关闭并持久化保存持仓盯盘窗口；
3. 【单实例激活唤醒】同一标的代码若已在子进程运行中，直接通过 Win32 API 唤醒并置顶其窗口；
4. 【统一关闭与孤儿守护】在 ATS 退出 (closeEvent 与 atexit) 时自动统一终止所有 SBC 子进程，绝不残留后台孤儿进程。
"""

import os
import json
import sys
import atexit
import subprocess
import tempfile
import uuid
import threading
import time
from typing import Optional, Dict, List

from sys_utils import get_app_root, is_packaged_env
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("ATS.SBCLauncher")


def _get_sbc_log_path(name: str = "sbc") -> str:
    """返回 SBC 子进程独立日志文件路径 (按日期区分，最多保留 3 天)"""
    from datetime import date
    try:
        log_dir = os.path.join(get_app_root(), "logs", "sbc")
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f"{name}_{date.today().strftime('%Y%m%d')}.log")
    except Exception:
        import tempfile
        return os.path.join(tempfile.gettempdir(), f"{name}.log")


def _open_sbc_log(log_path: str):
    """安全打开 SBC 子进程日志文件句柄；失败时降级为 DEVNULL，保证 Popen 始终可以启动"""
    try:
        return open(log_path, "a", encoding="utf-8", buffering=1)  # buffering=1 行缓冲
    except Exception:
        return subprocess.DEVNULL


def _activate_window_by_title_keyword(keyword: str) -> bool:
    """尝试通过标题关键字查找并激活 Win32 窗口 (还原最小化并置顶)"""
    try:
        import win32gui
        import win32con

        found_hwnd = None

        def _enum_cb(hwnd, _):
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if keyword in title:
                    found_hwnd = hwnd
                    return False  # 停止枚举
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            pass

        if found_hwnd:
            try:
                # 若最小化则恢复
                if win32gui.IsIconic(found_hwnd):
                    win32gui.ShowWindow(found_hwnd, win32con.SW_RESTORE)
                else:
                    win32gui.ShowWindow(found_hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(found_hwnd)
                return True
            except Exception as act_err:
                logger.debug(f"[SBCLauncher] 激活窗口句柄 {found_hwnd} 提示: {act_err}")
    except Exception:
        pass
    return False


def _is_widget_alive(w) -> bool:
    """安全判断 QWidget 实例是否存活且可见 (兼容 sip.isdeleted 与各类窗口引用)"""
    if not w:
        return False
    try:
        from PyQt6.sip import isdeleted
        if isdeleted(w):
            return False
    except (TypeError, ValueError):
        pass
    except Exception:
        return False
    try:
        return bool(getattr(w, "isVisible", lambda: False)())
    except Exception:
        return False


def _build_sbc_subprocess_command(
    code: Optional[str] = None,
    period_mode: Optional[str] = "10d",
    is_holdings: bool = False,
    snapshot_idx: Optional[int] = None
) -> Optional[List[str]]:
    """
    智能构造多进程调起 SBC 的命令行 (全面支持源码开发与 PyInstaller 打包环境)
    - 源码环境: [sys.executable, run_sbc.py, <code>, <period>] 或 [sys.executable, run_sbc.py, --snapshot, N]
    - 打包环境: [target_exe, "--sbc", <code>, <period>] 或 [target_exe, "--sbc-hold", --snapshot, N]
    """
    app_root = get_app_root()
    is_frozen = is_packaged_env()
    is_py_interpreter = ("python" in os.path.basename(sys.executable).lower())

    # 1. 源码开发环境: 若当前为 Python 解释器且源码 run_sbc.py 存在，优先使用 python 解释器执行
    run_sbc_path = os.path.join(app_root, "run_sbc.py")
    if not is_frozen and is_py_interpreter and os.path.exists(run_sbc_path):
        if is_holdings:
            cmd = [sys.executable, run_sbc_path]
            if snapshot_idx is not None:
                cmd.extend(["--snapshot", str(snapshot_idx)])
            return cmd
        else:
            cmd = [sys.executable, run_sbc_path, str(code)]
            if period_mode:
                cmd.append(str(period_mode))
            return cmd

    # 2. 打包环境 (PyInstaller / Nuitka 冻结模式): 定位用于启动独立 SBC 子进程的可执行文件
    target_exe = None
    if is_frozen and sys.executable.lower().endswith(".exe"):
        curr_base = os.path.basename(sys.executable).lower()
        if "ats" in curr_base:
            target_exe = sys.executable
        else:
            # 检查同目录下是否存在 ATS_Terminal.exe
            candidate = os.path.join(app_root, "ATS_Terminal.exe")
            if os.path.exists(candidate):
                target_exe = candidate
            else:
                target_exe = sys.executable
    else:
        candidate_ats = os.path.join(app_root, "ATS_Terminal.exe")
        if os.path.exists(candidate_ats):
            target_exe = candidate_ats

    if target_exe and os.path.exists(target_exe):
        if is_holdings:
            cmd = [target_exe, "--sbc-hold"]
            if snapshot_idx is not None:
                cmd.extend(["--snapshot", str(snapshot_idx)])
            return cmd
        else:
            cmd = [target_exe, "--sbc", str(code)]
            if period_mode:
                cmd.append(str(period_mode))
            return cmd

    # 3. 兜底尝试外部存在 python 且存在 run_sbc.py
    if os.path.exists(run_sbc_path):
        py_exe = sys.executable if is_py_interpreter else "python"
        if is_holdings:
            cmd = [py_exe, run_sbc_path]
            if snapshot_idx is not None:
                cmd.extend(["--snapshot", str(snapshot_idx)])
            return cmd
        else:
            cmd = [py_exe, run_sbc_path, str(code)]
            if period_mode:
                cmd.append(str(period_mode))
            return cmd

    return None


class SBCProcessManager:
    """SBC 独立子进程与进程内降级全局生命周期管理器 (单例)"""
    _instance: Optional["SBCProcessManager"] = None

    @classmethod
    def get_instance(cls) -> "SBCProcessManager":
        if cls._instance is None:
            cls._instance = SBCProcessManager()
        return cls._instance

    def __init__(self):
        # 记录正在运行的 SBC 子进程: key -> subprocess.Popen
        self._procs: Dict[str, subprocess.Popen] = {}
        # 记录打包或降级环境下在进程内打开的持仓盯盘窗口实例列表
        self._in_process_holdings: List = []
        # 注册退出钩子，保证即使异常崩溃也能清理子进程
        self._close_workers = []
        self._closing_processes = {}
        self._closing_holdings = None
        self._closing_holdings_proc = None
        self._pending_holdings_launch = None
        self._restart_timer_pending = False
        self._shutdown_requested = False
        atexit.register(self._close_at_exit)

    def cleanup_dead_processes(self):
        """清理已经自然退出的子进程对象"""
        dead_keys = []
        for key, proc in list(self._procs.items()):
            if proc is None or proc.poll() is not None:
                dead_keys.append(key)
        for k in dead_keys:
            proc = self._procs.pop(k, None)
            status_path = getattr(proc, "_sbc_closed_path", None)
            if status_path:
                try:
                    os.remove(status_path)
                except OSError:
                    pass

    def is_launcher_running(self) -> bool:
        """检查持仓盯盘启动器是否正在运行 (同时支持独立子进程与进程内降级模式)"""
        self.cleanup_dead_processes()
        proc = self._procs.get("__holdings_launcher__")
        if proc and proc.poll() is None:
            status_path = getattr(proc, "_sbc_closed_path", None)
            return not (status_path and os.path.isfile(status_path))
        if self._in_process_holdings:
            self._in_process_holdings = [w for w in self._in_process_holdings if _is_widget_alive(w)]
            if self._in_process_holdings:
                return True
        return False

    def launch_holdings_watcher(self, snapshot_idx: Optional[int] = None, snapshot_data: Optional[dict] = None):
        """【🚀 启动持仓盯盘】在开发环境与打包环境下均优先调起独立子进程运行 (支持指定历史快照)"""
        if self._shutdown_requested:
            return None
        if snapshot_idx is not None and snapshot_data is None:
            import run_sbc
            snapshots = run_sbc.get_launcher_history_snapshots()
            if 1 <= snapshot_idx <= len(snapshots):
                import copy
                snapshot_data = copy.deepcopy(snapshots[snapshot_idx - 1])
        if self._closing_holdings is not None and self._closing_holdings.is_alive():
            self._pending_holdings_launch = (snapshot_idx, snapshot_data)
            if not self._restart_timer_pending:
                from PyQt6.QtCore import QTimer
                self._restart_timer_pending = True
                QTimer.singleShot(100, self._retry_holdings_launch)
            return None
        if self._closing_holdings_proc is not None and self._closing_holdings_proc.poll() is None:
            logger.warning("[SBCLauncher] 上次关闭尚未完成，保留旧进程并取消重开。")
            return None
        self.cleanup_dead_processes()
        if self.is_launcher_running():
            if snapshot_idx is not None:
                logger.info(f"[SBCLauncher] 切换至历史快照 {snapshot_idx}，平稳关闭当前盯盘并重启...")
                self.close_launcher_process()
                if self._on_gui_thread():
                    return self.launch_holdings_watcher(snapshot_idx=snapshot_idx, snapshot_data=snapshot_data)
            else:
                logger.info("[SBCLauncher] 持仓盯盘已在运行中，尝试激活窗口...")
                self.activate_launcher_windows()
                return self._procs.get("__holdings_launcher__") or self._in_process_holdings

        cmd = _build_sbc_subprocess_command(is_holdings=True, snapshot_idx=snapshot_idx)
        if cmd:
            app_root = get_app_root()
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            env = os.environ.copy()
            # 💡 核心隔离：剥离 PyInstaller 父进程临时解压目录环境变量，避免子进程锁死父进程 _MEIxxxxx 导致退出报 PYI-10032 警告
            env.pop("_MEIPASS2", None)
            env["ATS_SBC_SUBPROCESS"] = "1"
            env["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
            env.pop("SBC_RESTORE_SNAPSHOT", None)
            if snapshot_data is not None:
                env["SBC_RESTORE_SNAPSHOT"] = json.dumps(snapshot_data, ensure_ascii=False)
            closed_path = os.path.join(tempfile.gettempdir(), f"ats_sbc_closed_{uuid.uuid4().hex}")
            env["ATS_SBC_CLOSED_PATH"] = closed_path
            try:
                import run_sbc
                env["SBC_LAYOUT_CONFIG_PATH"] = run_sbc._get_launcher_layout_cfg_path()
            except Exception:
                pass
            env["ATS_MAIN_PID"] = str(os.getpid())

            # ⭐ [FIX] 将 SBC 子进程的 stdout/stderr 重定向到独立日志文件，切断与父进程共享的
            # Windows 控制台句柄（CONOUT$/CONIN$）。若不重定向，SBC 被强杀后其 PyInstaller
            # bootloader 仍在 C 层执行清理并写控制台，与 ATS 并发写控制台产生内核锁竞争，
            # 导致 ATS 退出时永久卡死在控制台 WriteConsole 调用上。
            sbc_log_path = _get_sbc_log_path("sbc_holdings")
            sbc_log_fh = _open_sbc_log(sbc_log_path)

            logger.info(f"[SBCLauncher] 🚀 正在启动持仓盯盘独立多进程: {' '.join(cmd)}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=app_root,
                    env=env,
                    creationflags=flags,
                    close_fds=True,
                    stdout=sbc_log_fh,
                    stderr=sbc_log_fh,
                )
                # 父进程在子进程继承句柄后立即关闭自己持有的文件句柄，防止泄漏
                if sbc_log_fh is not subprocess.DEVNULL:
                    try: sbc_log_fh.close()
                    except Exception: pass
                previous = self._procs.get("__holdings_launcher__")
                if previous and previous.poll() is None:
                    self._procs[f"__retired_holdings_{previous.pid}__"] = previous
                self._procs["__holdings_launcher__"] = proc
                proc._sbc_closed_path = closed_path
                logger.info(f"[SBCLauncher] ✅ 成功调起持仓盯盘独立进程 (PID={proc.pid})，日志: {sbc_log_path}")
                return proc
            except Exception as e:
                if sbc_log_fh is not subprocess.DEVNULL:
                    try: sbc_log_fh.close()
                    except Exception: pass
                logger.warning(f"[SBCLauncher] 调起持仓盯盘子进程异常，转为内存模式降级: {e}")

        # 💡 【兜底降级】若无法调起独立子进程，在当前进程内打开持仓盯盘窗口
        logger.info("[SBCLauncher] 无法调起外部子进程，在当前进程内调起持仓盯盘窗口...")
        try:
            import run_sbc
            os.environ["SBC_LAYOUT_CONFIG_PATH"] = run_sbc._get_launcher_layout_cfg_path()
            os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
            restored = run_sbc.restore_launcher_holdings_windows(snapshot_index=snapshot_idx, snapshot_data=snapshot_data)
            if not restored:
                from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
                dlg = open_sbc_chart_dialog(None, code="600733", period_mode="10d")
                if dlg:
                    dlg.show()
                    restored = [dlg]
            self._in_process_holdings = restored or []
            logger.info(f"[SBCLauncher] ✅ [内存降级模式] 成功调起 {len(self._in_process_holdings)} 个持仓盯盘窗口")
            return self._in_process_holdings
        except Exception as e_fallback:
            logger.error(f"[SBCLauncher] 进程内调起持仓盯盘异常: {e_fallback}", exc_info=True)
            return None

    @staticmethod
    def _on_gui_thread():
        try:
            from PyQt6.QtCore import QCoreApplication, QThread
            app = QCoreApplication.instance()
            return app is not None and QThread.currentThread() == app.thread()
        except Exception:
            return False

    def _start_close_worker(self, target, *args, holdings=False):
        self._close_workers = [w for w in self._close_workers if w.is_alive()]
        self._closing_processes = {pid: p for pid, p in self._closing_processes.items()
                                   if p.poll() is None}
        owned = args[0].values() if isinstance(args[0], dict) else (args[0],)
        self._closing_processes.update({p.pid: p for p in owned if p is not None})
        worker = threading.Thread(target=target, args=args, daemon=False, name="ATS-SBCClose")
        self._close_workers.append(worker)
        if holdings:
            self._closing_holdings = worker
            self._closing_holdings_proc = (args[0].get('__holdings_launcher__')
                                           if isinstance(args[0], dict) else args[0])
        try:
            worker.start()
        except Exception as err:
            logger.error(f"[SBCLauncher] 无法提交后台关闭任务: {err}")
            for proc in owned:
                if proc is not None:
                    self._procs[f'__retired_{proc.pid}__'] = proc
            return False
        return True

    def _retry_holdings_launch(self):
        self._restart_timer_pending = False
        pending = self._pending_holdings_launch
        self._pending_holdings_launch = None
        if pending is not None and not self._shutdown_requested:
            self.launch_holdings_watcher(snapshot_idx=pending[0], snapshot_data=pending[1])

    def _close_in_process_holdings(self):
        # 1. 优先关闭并持久化保存在当前进程内打开的持仓盯盘窗口
        if self._in_process_holdings:
            try:
                import run_sbc
                alive_wins = [w for w in self._in_process_holdings if _is_widget_alive(w)]
                if alive_wins:
                    logger.info(f"[SBCLauncher] 正在关闭进程内 {len(alive_wins)} 个持仓盯盘窗口并持久化...")
                    run_sbc.save_launcher_holdings_windows(force=True)
                    run_sbc.persist_sbc_runtime_caches()
                    for w in alive_wins:
                        try:
                            w.close()
                        except Exception:
                            pass
                self._in_process_holdings.clear()
                logger.info("[SBCLauncher] 进程内持仓盯盘窗口已统一关闭并完成持久化。")
            except Exception as e_inproc_close:
                logger.error(f"[SBCLauncher] 关闭进程内持仓盯盘窗口异常: {e_inproc_close}")

    def close_launcher_process(self) -> bool:
        """GUI 调用立即提交关闭；旧进程落盘及等待由有生命周期的后台线程负责。"""
        self._pending_holdings_launch = None
        self._close_in_process_holdings()
        self.cleanup_dead_processes()
        proc = self._procs.pop("__holdings_launcher__", None)
        if not proc or proc.poll() is not None:
            return True
        if self._on_gui_thread():
            return self._start_close_worker(self._close_launcher_subprocess, proc, holdings=True)
        return self._close_launcher_subprocess(proc)

    def _close_launcher_subprocess(self, proc) -> bool:
        logger.info(f"[SBCLauncher] 正在优雅关闭持仓盯盘独立进程 (PID={proc.pid}) 并等待持久化...")
        children = self._sbc_bootloader_children(proc)
        try:
            # 💡 【核心持久化】在关闭前精确捕获当前仍然处于打开显示状态的窗口列表，已经手动关闭的窗口 HWND 已消亡，绝对不会被持久化！
            active_launcher_windows = []
            if sys.platform == "win32":
                import win32gui
                import win32process
                import win32con
                import re

                target_pids = {proc.pid, *(child.pid for child in children)}

                # 1. 优先扫描当前真正存活且可见的持仓盯盘窗口
                def _scan_visible_cb(hwnd, _):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                            if w_pid in target_pids:
                                t = win32gui.GetWindowText(hwnd)
                                m = re.search(r"[【\[(]?(\d{6})", t)
                                if m:
                                    c = m.group(1)
                                    if not any(item.get("code") == c for item in active_launcher_windows):
                                        l, top, r, b = win32gui.GetWindowRect(hwnd)
                                        w = max(640, r - l)
                                        h = max(420, b - top)
                                        active_launcher_windows.append({
                                            "code": c,
                                            "x": l,
                                            "y": top,
                                            "width": w,
                                            "height": h,
                                            "period_mode": "10d"
                                        })
                    except Exception:
                        pass
                    return True

                try:
                    win32gui.EnumWindows(_scan_visible_cb, None)
                except Exception:
                    pass

                # 2. 将当前仍然打开的窗口精准写盘持久化至 sbc_launcher_holdings_layout.json
                try:
                    import json
                    from datetime import datetime
                    from run_sbc import _get_launcher_layout_cfg_path
                    cfg_path = _get_launcher_layout_cfg_path()
                    old_data = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                old_data = json.load(f)
                        except Exception:
                            old_data = {}

                    # 💡 铁壁防冲洗守卫 (P0)：若 active_launcher_windows 为空，但历史已有有效记录，严禁覆盖写入 0 个！
                    if len(active_launcher_windows) == 0:
                        if old_data.get("sbc_holdings_windows") or old_data.get("recent_history_snapshots"):
                            logger.info(f"[SBCLauncher] 🛡 Win32 未扫描到可见窗口，保留现有有效配置，严禁覆盖写 0！")
                    else:
                        old_period_map = old_data.get("sbc_period_modes", {})
                        for item in active_launcher_windows:
                            c = item["code"]
                            if c in old_period_map:
                                item["period_mode"] = old_period_map[c]

                        # 💡 维护最近 3 组历史快照 recent_history_snapshots
                        recent_snapshots = old_data.get("recent_history_snapshots", [])
                        if not isinstance(recent_snapshots, list):
                            recent_snapshots = []
                        current_codes = sorted([item["code"] for item in active_launcher_windows])
                        should_add = True
                        if recent_snapshots and isinstance(recent_snapshots[0], dict):
                            last_codes = sorted(recent_snapshots[0].get("codes", []))
                            if last_codes == current_codes:
                                should_add = False
                        if should_add and current_codes:
                            recent_snapshots.insert(0, {
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "codes": [item["code"] for item in active_launcher_windows],
                                "windows": active_launcher_windows
                            })
                            recent_snapshots = recent_snapshots[:3]

                        save_data = {
                            "sbc_holdings_windows": active_launcher_windows,
                            "sbc_open_windows": active_launcher_windows,
                            "initialized": True,
                            "recent_history_snapshots": recent_snapshots
                        }
                        if "sbc_period_modes" in old_data:
                            save_data["sbc_period_modes"] = old_data["sbc_period_modes"]

                        tmp_path = cfg_path + f".tmp_{os.getpid()}"
                        with open(tmp_path, "w", encoding="utf-8") as f:
                            json.dump(save_data, f, ensure_ascii=False, indent=2)
                        try:
                            if os.path.exists(cfg_path):
                                os.replace(tmp_path, cfg_path)
                            else:
                                os.rename(tmp_path, cfg_path)
                        except Exception:
                            import shutil
                            shutil.move(tmp_path, cfg_path)
                        logger.info(f"[SBCLauncher] ✅ 统一关闭时成功精准集中持久化当前打开的 {len(active_launcher_windows)} 个盯盘窗口 (保留最近 {len(recent_snapshots)} 组历史快照)")
                except Exception as e_save:
                    logger.error(f"[SBCLauncher] 统一关闭写盘异常: {e_save}")

                # 3. 向窗口投递 WM_CLOSE 优雅退出
                def _enum_cb(hwnd, _):
                    try:
                        _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if w_pid in target_pids and win32gui.IsWindow(hwnd):
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    except Exception:
                        pass
                    return True

                try:
                    win32gui.EnumWindows(_enum_cb, None)
                except Exception:
                    pass

            # 💡 onefile 子进程退出时 bootloader 需要删除自身 _MEI* 临时目录，必须给予足够时间，
            #    超时过短会导致 bootloader atexit 未执行，遗留临时目录并触发父进程报
            #    "Failed to remove temporary directory" 警告 (PYI-10032)。
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                logger.warning(f"[SBCLauncher] 持仓盯盘进程 (PID={proc.pid}) 等待超时，执行 terminate")
                self._signal_sbc_process(proc, children)
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._signal_sbc_process(proc, children, force=True)
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        pass
            # 💡 彻底关闭子进程管道句柄，释放操作系统内核对 DLL 的文件锁
            try:
                for pipe in (proc.stdout, proc.stderr, proc.stdin):
                    if pipe and not getattr(pipe, 'closed', False):
                        pipe.close()
            except Exception:
                pass
            logger.info("[SBCLauncher] 持仓盯盘进程已安全退出并完成持久化。")
            return True
        except Exception as e:
            logger.error(f"[SBCLauncher] 关闭持仓盯盘进程异常: {e}")
            return False
        finally:
            status_path = getattr(proc, "_sbc_closed_path", None)
            if status_path and proc.poll() is not None:
                try:
                    os.remove(status_path)
                except OSError:
                    pass

    def activate_launcher_windows(self):
        """尝试将所有 SBC 窗口置顶激活 (同时支持进程内与独立子进程窗口)"""
        if self._in_process_holdings:
            try:
                for w in self._in_process_holdings:
                    if _is_widget_alive(w):
                        w.show()
                        w.raise_()
                        w.activateWindow()
            except Exception:
                pass

        try:
            import win32gui, win32con
            def _enum_cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if "SBC" in t or "分时走势" in t or "关键阶梯" in t:
                        if win32gui.IsIconic(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                return True
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            pass

    def launch(self, code: str, period_mode: Optional[str] = "10d") -> Optional[subprocess.Popen]:
        """
        启动或唤醒指定标的的 SBC 独立子进程走势图
        :param code: 6位标的代码 (如 '688826' 或 '000001')
        :param period_mode: 初始看盘周期 ('1m' | '5m' | '30m' | '10d' 等)
        :return: 启动的 subprocess.Popen 对象或已有进程对象
        """
        if not code:
            return None
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
        if not c_clean or c_clean == "000000":
            return None

        self.cleanup_dead_processes()

        # 1. 检查当前是否已有该股票的运行中子进程或进程内窗口
        existing_proc = self._procs.get(c_clean)
        if existing_proc and existing_proc.poll() is None:
            logger.info(f"[SBCLauncher] 标的 {c_clean} 已在独立子进程 (PID={existing_proc.pid}) 运行中，尝试唤醒窗口...")
            if _activate_window_by_title_keyword(f"【{c_clean}"):
                return existing_proc

        try:
            from PyQt6.QtWidgets import QApplication
            from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
            for w in QApplication.topLevelWidgets():
                if isinstance(w, SBCIntradayChartDialog) and _is_widget_alive(w):
                    if getattr(w, "code", None) == c_clean:
                        w.show()
                        w.raise_()
                        w.activateWindow()
                        logger.info(f"[SBCLauncher] 标的 {c_clean} 已在进程内窗口运行中，已激活置顶")
                        return w
        except Exception:
            pass

        # 2. 构造多进程启动命令 (全面支持源码开发与 PyInstaller 打包环境)
        cmd = _build_sbc_subprocess_command(code=c_clean, period_mode=period_mode, is_holdings=False)
        if cmd:
            app_root = get_app_root()
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            env = os.environ.copy()
            # 💡 核心隔离：剥离 PyInstaller 父进程临时解压目录环境变量
            env.pop("_MEIPASS2", None)
            env["ATS_SBC_SUBPROCESS"] = "1"
            env["ATS_MAIN_PID"] = str(os.getpid())

            # ⭐ [FIX] 同上：切断控制台句柄继承，防止 SBC bootloader 清理时与 ATS 争控制台锁
            sbc_log_path = _get_sbc_log_path(f"sbc_{c_clean}")
            sbc_log_fh = _open_sbc_log(sbc_log_path)

            logger.info(f"[SBCLauncher] 🚀 正在启动标的 {c_clean} 的独立 SBC 进程: {' '.join(cmd)}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=app_root,
                    env=env,
                    creationflags=creationflags,
                    close_fds=True,
                    stdout=sbc_log_fh,
                    stderr=sbc_log_fh,
                )
                # 父进程在子进程继承句柄后立即关闭自己持有的文件句柄，防止泄漏
                if sbc_log_fh is not subprocess.DEVNULL:
                    try: sbc_log_fh.close()
                    except Exception: pass
                self._procs[c_clean] = proc
                logger.info(f"[SBCLauncher] ✅ 标的 {c_clean} SBC 独立子进程启动成功 (PID={proc.pid})，日志: {sbc_log_path}")
                return proc
            except Exception as e:
                if sbc_log_fh is not subprocess.DEVNULL:
                    try: sbc_log_fh.close()
                    except Exception: pass
                logger.warning(f"[SBCLauncher] 启动标的 {c_clean} SBC 子进程失败，转为进程内降级: {e}")

        # 3. 💡 【兜底降级】若无法调起独立子进程，在当前进程内打开 SBC 走势图
        logger.info(f"[SBCLauncher] 无法调起独立子进程，在当前进程内调起标的 {c_clean} SBC 走势图...")
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            dlg = open_sbc_chart_dialog(None, code=c_clean, period_mode=period_mode or "10d")
            if dlg:
                dlg.show()
                dlg.raise_()
                dlg.activateWindow()
                return dlg
        except Exception as e_inproc:
            logger.error(f"[SBCLauncher] 进程内调起标的 {c_clean} SBC 异常: {e_inproc}", exc_info=True)
            return None

    @staticmethod
    def _sbc_bootloader_children(proc):
        """只识别同一 SBC 命令的 onefile 子进程，保留独立行情后端。"""
        if sys.platform != 'win32' or not is_packaged_env():
            return []
        try:
            import psutil
            expected_exe = os.path.normcase(os.path.abspath(proc.args[0]))
            expected_args = list(proc.args[1:])
            matches = []
            for child in psutil.Process(proc.pid).children(recursive=True):
                try:
                    if (os.path.normcase(child.exe()) == expected_exe
                            and child.cmdline()[1:] == expected_args):
                        matches.append(child)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return matches
        except Exception:
            return []

    @staticmethod
    def _signal_sbc_process(proc, children, force=False):
        for child in reversed(children):
            try:
                child.kill() if force else child.terminate()
            except Exception:
                pass
        # The onefile parent can finish its own cleanup after its child exits.
        if force or not children:
            proc.kill() if force else proc.terminate()

    @staticmethod
    def _wait_for_processes(procs, timeout):
        # All children share one deadline; window count cannot multiply the wait.
        deadline = time.monotonic() + timeout
        remaining = []
        for code, proc in procs:
            if proc.poll() is not None:
                continue
            try:
                proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except Exception:
                remaining.append((code, proc))
        return remaining

    def close_all(self):
        """GUI 提交整批关闭；atexit 仍同步回收尚未提交的进程。"""
        self._shutdown_requested = True
        self._pending_holdings_launch = None
        self._close_in_process_holdings()
        self.cleanup_dead_processes()
        procs, self._procs = self._procs, {}
        if not procs:
            return
        if self._on_gui_thread():
            self._start_close_worker(self._close_all_subprocesses, procs,
                                     holdings="__holdings_launcher__" in procs)
        else:
            self._close_all_subprocesses(procs)

    def _close_at_exit(self):
        # Python cannot start new threads during atexit. Existing non-daemon
        # close workers have already been joined by interpreter shutdown.
        procs, self._procs = self._procs, {}
        for pid, proc in self._closing_processes.items():
            if proc.poll() is None:
                procs[f'__closing_{pid}__'] = proc
        self._close_all_subprocesses(procs)

    def _close_all_subprocesses(self, procs):
        proc = procs.pop("__holdings_launcher__", None)
        if proc and proc.poll() is None:
            self._close_launcher_subprocess(proc)
        if not procs:
            return
        children_by_pid = {p.pid: self._sbc_bootloader_children(p) for p in procs.values()
                           if p and p.poll() is None}
        logger.info(f"[SBCLauncher] 🛑 正在统一优雅关闭 {len(procs)} 个 SBC 独立子进程...")
        # 1. 在 Windows 上优先向所有子进程顶层窗口投递 WM_CLOSE 消息，确保执行退出落盘
        if sys.platform == "win32":
            try:
                import win32gui
                import win32process
                import win32con
                pids = {p.pid for p in procs.values() if p and p.poll() is None}
                pids.update(child.pid for children in children_by_pid.values() for child in children)
                if pids:
                    def _enum_all(hwnd, _):
                        try:
                            _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                            if w_pid in pids and win32gui.IsWindow(hwnd):
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        except Exception:
                            pass
                        return True
                    win32gui.EnumWindows(_enum_all, None)
            except Exception:
                pass

        procs_to_wait = []
        for code, proc in list(procs.items()):
            if proc and proc.poll() is None:
                procs_to_wait.append((code, proc))

        # 2. 给予子进程在收到 WM_CLOSE 后优雅保存退出的缓冲时间
        #    onefile 子进程需要 2~3s 完成自身 bootloader _MEI* 临时目录清理，
        #    时间过短会导致子进程被强杀，遗留临时目录报 PYI-10032 警告。
        remaining = self._wait_for_processes(procs_to_wait, 2.0)
        for code, proc in remaining:
            try:
                self._signal_sbc_process(proc, children_by_pid.get(proc.pid, []))
            except Exception:
                pass
        remaining = self._wait_for_processes(remaining, 0.6)
        for code, proc in remaining:
            try:
                self._signal_sbc_process(proc, children_by_pid.get(proc.pid, []), force=True)
            except Exception:
                pass
        self._wait_for_processes(remaining, 0.4)

        # 4. 彻底关闭所有子进程的操作系统管道文件描述符，断开 DLL 文件锁
        for code, proc in procs_to_wait:
            try:
                for pipe in (proc.stdout, proc.stderr, proc.stdin):
                    if pipe and not getattr(pipe, 'closed', False):
                        pipe.close()
            except Exception:
                pass

        procs.clear()
        logger.info("[SBCLauncher] 🏁 所有 SBC 独立子进程已全部安全退出且句柄彻底释放。")

    def get_running_codes(self) -> List[str]:
        """获取当前正在运行的所有 SBC 子进程标的代码"""
        self.cleanup_dead_processes()
        return list(self._procs.keys())


# 暴露全局便捷调用接口
def launch_sbc_process(code: str, period_mode: Optional[str] = "10d") -> Optional[subprocess.Popen]:
    """启动或激活指定标的的 SBC 独立子进程走势图"""
    return SBCProcessManager.get_instance().launch(code, period_mode)


def close_all_sbc_processes():
    """统一关闭所有 SBC 独立子进程"""
    SBCProcessManager.get_instance().close_all()
