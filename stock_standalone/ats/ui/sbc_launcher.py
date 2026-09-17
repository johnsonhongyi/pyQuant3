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
import sys
import atexit
import subprocess
from typing import Optional, Dict, List

from sys_utils import get_app_root, is_packaged_env
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("ATS.SBCLauncher")


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


def _build_sbc_subprocess_command(code: Optional[str] = None, period_mode: Optional[str] = "10d", is_holdings: bool = False) -> Optional[List[str]]:
    """
    智能构造多进程调起 SBC 的命令行 (全面支持源码开发与 PyInstaller 打包环境)
    - 源码环境: [sys.executable, run_sbc.py, <code>, <period>] 或 [sys.executable, run_sbc.py]
    - 打包环境: [target_exe, "--sbc", <code>, <period>] 或 [target_exe, "--sbc-holdings"]
    """
    app_root = get_app_root()
    is_frozen = is_packaged_env()
    is_py_interpreter = ("python" in os.path.basename(sys.executable).lower())

    # 1. 源码开发环境: 若当前为 Python 解释器且源码 run_sbc.py 存在，优先使用 python 解释器执行
    run_sbc_path = os.path.join(app_root, "run_sbc.py")
    if not is_frozen and is_py_interpreter and os.path.exists(run_sbc_path):
        if is_holdings:
            return [sys.executable, run_sbc_path]
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
            return [target_exe, "--sbc-holdings"]
        else:
            cmd = [target_exe, "--sbc", str(code)]
            if period_mode:
                cmd.append(str(period_mode))
            return cmd

    # 3. 兜底尝试外部存在 python 且存在 run_sbc.py
    if os.path.exists(run_sbc_path):
        py_exe = sys.executable if is_py_interpreter else "python"
        if is_holdings:
            return [py_exe, run_sbc_path]
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
        atexit.register(self.close_all)

    def cleanup_dead_processes(self):
        """清理已经自然退出的子进程对象"""
        dead_keys = []
        for key, proc in list(self._procs.items()):
            if proc is None or proc.poll() is not None:
                dead_keys.append(key)
        for k in dead_keys:
            self._procs.pop(k, None)

    def is_launcher_running(self) -> bool:
        """检查持仓盯盘启动器是否正在运行 (同时支持独立子进程与进程内降级模式)"""
        self.cleanup_dead_processes()
        proc = self._procs.get("__holdings_launcher__")
        if proc and proc.poll() is None:
            return True
        if self._in_process_holdings:
            self._in_process_holdings = [w for w in self._in_process_holdings if _is_widget_alive(w)]
            if self._in_process_holdings:
                return True
        return False

    def launch_holdings_watcher(self):
        """【🚀 启动持仓盯盘】在开发环境与打包环境下均优先调起独立子进程运行"""
        self.cleanup_dead_processes()
        if self.is_launcher_running():
            logger.info("[SBCLauncher] 持仓盯盘已在运行中，尝试激活窗口...")
            self.activate_launcher_windows()
            return self._procs.get("__holdings_launcher__") or self._in_process_holdings

        cmd = _build_sbc_subprocess_command(is_holdings=True)
        if cmd:
            app_root = get_app_root()
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            env = os.environ.copy()
            # 💡 核心隔离：剥离 PyInstaller 父进程临时解压目录环境变量，避免子进程锁死父进程 _MEIxxxxx 导致退出报 PYI-10032 警告
            env.pop("_MEIPASS2", None)
            env["ATS_SBC_SUBPROCESS"] = "1"
            env["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
            try:
                import run_sbc
                env["SBC_LAYOUT_CONFIG_PATH"] = run_sbc._get_launcher_layout_cfg_path()
            except Exception:
                pass
            env["ATS_MAIN_PID"] = str(os.getpid())

            logger.info(f"[SBCLauncher] 🚀 正在启动持仓盯盘独立多进程: {' '.join(cmd)}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=app_root,
                    env=env,
                    creationflags=flags,
                    close_fds=(sys.platform != "win32")
                )
                self._procs["__holdings_launcher__"] = proc
                logger.info(f"[SBCLauncher] ✅ 成功调起持仓盯盘独立进程 (PID={proc.pid})")
                return proc
            except Exception as e:
                logger.warning(f"[SBCLauncher] 调起持仓盯盘子进程异常，转为内存模式降级: {e}")

        # 💡 【兜底降级】若无法调起独立子进程，在当前进程内打开持仓盯盘窗口
        logger.info("[SBCLauncher] 无法调起外部子进程，在当前进程内调起持仓盯盘窗口...")
        try:
            import run_sbc
            os.environ["SBC_LAYOUT_CONFIG_PATH"] = run_sbc._get_launcher_layout_cfg_path()
            os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
            restored = run_sbc.restore_launcher_holdings_windows()
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

    def close_launcher_process(self) -> bool:
        """【🛑 统一关闭持仓盯盘】优雅关闭并持久化保存持仓盯盘窗口 (支持独立子进程与进程内降级模式)"""
        # 1. 优先关闭并持久化保存在当前进程内打开的持仓盯盘窗口
        if self._in_process_holdings:
            try:
                import run_sbc
                alive_wins = [w for w in self._in_process_holdings if _is_widget_alive(w)]
                if alive_wins:
                    logger.info(f"[SBCLauncher] 正在关闭进程内 {len(alive_wins)} 个持仓盯盘窗口并持久化...")
                    run_sbc.save_launcher_holdings_windows()
                    for w in alive_wins:
                        try:
                            w.close()
                        except Exception:
                            pass
                self._in_process_holdings.clear()
                logger.info("[SBCLauncher] 进程内持仓盯盘窗口已统一关闭并完成持久化。")
            except Exception as e_inproc_close:
                logger.error(f"[SBCLauncher] 关闭进程内持仓盯盘窗口异常: {e_inproc_close}")
        self.cleanup_dead_processes()
        proc = self._procs.get("__holdings_launcher__")
        if not proc or proc.poll() is not None:
            self._procs.pop("__holdings_launcher__", None)
            return True

        logger.info(f"[SBCLauncher] 正在优雅关闭持仓盯盘独立进程 (PID={proc.pid}) 并等待持久化...")
        try:
            # 💡 【核心持久化】在关闭前精确捕获当前仍然处于打开显示状态的窗口列表，已经手动关闭的窗口 HWND 已消亡，绝对不会被持久化！
            active_launcher_windows = []
            if sys.platform == "win32":
                import win32gui
                import win32process
                import win32con
                import re

                target_pid = proc.pid

                # 1. 优先扫描当前真正存活且可见的持仓盯盘窗口
                def _scan_visible_cb(hwnd, _):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                            if w_pid == target_pid:
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
                    from run_sbc import _get_launcher_layout_cfg_path
                    cfg_path = _get_launcher_layout_cfg_path()
                    old_data = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                old_data = json.load(f)
                        except Exception:
                            old_data = {}

                    old_period_map = old_data.get("sbc_period_modes", {})
                    for item in active_launcher_windows:
                        c = item["code"]
                        if c in old_period_map:
                            item["period_mode"] = old_period_map[c]

                    save_data = {
                        "sbc_holdings_windows": active_launcher_windows,
                        "sbc_open_windows": active_launcher_windows,
                        "initialized": True
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
                    logger.info(f"[SBCLauncher] ✅ 统一关闭时成功精准持久化当前打开的 {len(active_launcher_windows)} 个盯盘窗口 (已手动关闭的彻底排除)")
                except Exception as e_save:
                    logger.error(f"[SBCLauncher] 统一关闭写盘异常: {e_save}")

                # 3. 向窗口投递 WM_CLOSE 优雅退出
                def _enum_cb(hwnd, _):
                    try:
                        _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if w_pid == target_pid and win32gui.IsWindow(hwnd):
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    except Exception:
                        pass
                    return True

                try:
                    win32gui.EnumWindows(_enum_cb, None)
                except Exception:
                    pass

            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                logger.warning(f"[SBCLauncher] 持仓盯盘进程 (PID={proc.pid}) 等待超时，执行 terminate")
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
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
            self._procs.pop("__holdings_launcher__", None)
            logger.info("[SBCLauncher] 持仓盯盘进程已安全退出并完成持久化。")
            return True
        except Exception as e:
            logger.error(f"[SBCLauncher] 关闭持仓盯盘进程异常: {e}")
            return False

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

            logger.info(f"[SBCLauncher] 🚀 正在启动标的 {c_clean} 的独立 SBC 进程: {' '.join(cmd)}")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=app_root,
                    env=env,
                    creationflags=creationflags,
                    close_fds=(sys.platform != "win32")
                )
                self._procs[c_clean] = proc
                logger.info(f"[SBCLauncher] ✅ 标的 {c_clean} SBC 独立子进程启动成功 (PID={proc.pid})")
                return proc
            except Exception as e:
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

    def close_all(self):
        """统一终止并清理所有拉起的 SBC 独立子进程"""
        self.cleanup_dead_processes()
        if not self._procs:
            return

        logger.info(f"[SBCLauncher] 🛑 正在统一优雅关闭 {len(self._procs)} 个 SBC 独立子进程...")
        # 1. 在 Windows 上优先向所有子进程顶层窗口投递 WM_CLOSE 消息，确保执行退出落盘
        if sys.platform == "win32":
            try:
                import win32gui
                import win32process
                import win32con
                pids = {p.pid for p in self._procs.values() if p and p.poll() is None}
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
        for code, proc in list(self._procs.items()):
            if proc and proc.poll() is None:
                procs_to_wait.append((code, proc))

        # 2. 给予子进程在收到 WM_CLOSE 后优雅保存退出的缓冲时间 (最多 0.8s)
        remaining = []
        for code, proc in procs_to_wait:
            try:
                proc.wait(timeout=0.8)
            except (subprocess.TimeoutExpired, Exception):
                remaining.append((code, proc))

        # 3. 对未能优雅退出的子进程执行分级终止并严格等待
        if remaining:
            for code, proc in remaining:
                try:
                    proc.terminate()
                except Exception:
                    pass
            for code, proc in remaining:
                try:
                    proc.wait(timeout=0.6)
                except (subprocess.TimeoutExpired, Exception):
                    try:
                        proc.kill()
                        proc.wait(timeout=0.4)
                    except Exception:
                        pass

        # 4. 彻底关闭所有子进程的操作系统管道文件描述符，断开 DLL 文件锁
        for code, proc in procs_to_wait:
            try:
                for pipe in (proc.stdout, proc.stderr, proc.stdin):
                    if pipe and not getattr(pipe, 'closed', False):
                        pipe.close()
            except Exception:
                pass

        if sys.platform == "win32" and procs_to_wait:
            import time
            time.sleep(0.05)

        self._procs.clear()
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
