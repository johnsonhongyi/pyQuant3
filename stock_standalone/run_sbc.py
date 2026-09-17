# -*- coding: utf-8 -*-
"""
run_sbc.py
----------
SBC 分时图独立启动器 (专门用来盯持仓的盘)
- 独立持久化：使用 config/sbc_launcher_holdings_layout.json，与 ATS 主系统原有 SBC 窗口持久化彻底隔离；
- 持仓自动盯盘：启动时优先恢复上次退出的盯盘窗口；若无历史记录，自动读取当前所有有效持仓代码并平铺启动；
- 统一退出保存：退出时自动持久化保存所有已打开的盯盘窗口尺寸、位置与设置。
"""

import sys
import os
import time
import json
import signal
import atexit
import multiprocessing
from typing import List, Optional

if __name__ == "__main__":
    multiprocessing.freeze_support()

# 确保工作区根目录在 Python 路径中
try:
    from sys_utils import get_app_root, setup_qt_clean_environment
    current_dir = get_app_root()
    setup_qt_clean_environment()
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QTimer
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    open_sbc_chart_dialog,
    rearrange_all_sbc_windows,
)
from sys_utils import ensure_backend_tk_running


def _get_launcher_layout_cfg_path() -> str:
    """【💾 独立持久化】SBC Launcher 专用持仓盯盘配置文件路径"""
    custom = os.environ.get("SBC_LAYOUT_CONFIG_PATH")
    if custom:
        return custom
    try:
        from sys_utils import get_app_root
        cfg_dir = os.path.join(get_app_root(), "config")
    except Exception:
        cfg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "sbc_launcher_holdings_layout.json")


def _get_current_holding_codes() -> List[str]:
    """【💰 自动读取当前持仓代码】从 IPCBridge 或交易核心中读取当前持仓标的"""
    try:
        from ats.ipc_bridge import IPCBridge
        bridge = IPCBridge()
        pos_df = bridge.get_open_positions()
        if pos_df is not None and not pos_df.empty and 'code' in pos_df.columns:
            codes = []
            for c in pos_df['code']:
                c_str = str(c).strip()
                digits = "".join(filter(str.isdigit, c_str)).zfill(6)
                if len(digits) == 6 and digits != "000000" and digits not in codes:
                    codes.append(digits)
            if codes:
                print(f"[SBC Launcher] 成功读取到当前有效持仓标的: {codes}")
                return codes
    except Exception as e:
        print(f"[SBC Launcher] 读取持仓标的提示: {e}")
    return []


_last_save_holdings_time = 0.0

def save_launcher_holdings_windows(force: bool = False):
    """【💾 持久化保存所有盯盘窗口】独立保存至 sbc_launcher_holdings_layout.json (支持增减，统一关闭时精准持久化未关闭窗口)"""
    global _last_save_holdings_time
    now = time.time()
    if not force and (now - _last_save_holdings_time < 0.8):
        return
    _last_save_holdings_time = now
    try:
        from PyQt6.sip import isdeleted
        active_list = []
        app_inst = QApplication.instance()
        is_exiting = bool(app_inst and app_inst.property("is_app_exiting"))
        for w in QApplication.topLevelWidgets():
            if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w):
                # 已经被手动关闭或标记正在关闭的实例，无论何时均严禁持久化
                if getattr(w, '_is_closing', False):
                    continue
                # 必须为当前可见窗口，或者处于贴边收缩隐藏状态 (is_hidden_state=True)
                if not w.isVisible() and not getattr(w, 'is_hidden_state', False):
                    continue
                # 即使处于贴边收缩隐藏状态 (is_hidden_state=True)，也精准读取其 normal_geometry
                geo = w.normal_geometry if (getattr(w, 'is_hidden_state', False) and getattr(w, 'normal_geometry', None)) else (w.normal_geometry or w.geometry())
                c = getattr(w, 'code', None)
                cur_period = getattr(w, '_current_period_mode', '10d')
                if c:
                    c_clean = str(c).zfill(6)
                    active_list.append({
                        "code": c_clean,
                        "x": geo.x(),
                        "y": geo.y(),
                        "width": geo.width(),
                        "height": geo.height(),
                        "period_mode": cur_period,
                    })

        cfg_path = _get_launcher_layout_cfg_path()
        # 💡 同步写入 sbc_holdings_windows 与 sbc_open_windows，并标记 initialized=True
        data = {
            "sbc_holdings_windows": active_list,
            "sbc_open_windows": active_list,
            "initialized": True
        }
        tmp_path = cfg_path + f".tmp_{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            if os.path.exists(cfg_path):
                os.replace(tmp_path, cfg_path)
            else:
                os.rename(tmp_path, cfg_path)
        except Exception:
            import shutil
            shutil.move(tmp_path, cfg_path)
        print(f"[SBC Launcher] 成功持久化保存 {len(active_list)} 个持仓盯盘窗口至 {cfg_path}")
    except Exception as err:
        print(f"[SBC Launcher] 保存持仓盯盘窗口异常: {err}")


def quit_and_save_all_sbc_windows():
    """【🛑 统一一键退出并持久化保存全部 SBC 窗口】
    支持：
    1. 操盘手按住 Alt 点击窗口右上角关闭 [X] 键；
    2. 点击窗口顶部工具栏 [🚪 退出保存] 按钮；
    3. 快捷键 Ctrl+Shift+Q 或 Alt+Escape；
    4. 终端收到 Ctrl+C (KeyboardInterrupt/SIGINT) 信号或 Windows 控制台关闭事件；
    自动判断当前是否处于持仓盯盘模式，执行精准的原子落盘并安全退出 Qt。
    """
    app = QApplication.instance()
    if app:
        app.setProperty("is_app_exiting", True)
        if app.property("_has_saved_on_quit"):
            try:
                app.quit()
            except Exception:
                pass
            return
        app.setProperty("_has_saved_on_quit", True)

    is_holdings_mode = (os.environ.get("SBC_IS_HOLDINGS_LAUNCHER") == "1")
    try:
        if is_holdings_mode:
            save_launcher_holdings_windows(force=True)
        else:
            from ats.ui.intraday_strategy_dialog import save_all_open_sbc_windows
            save_all_open_sbc_windows()
    except Exception as e:
        print(f"[SBC Launcher] 退出持久化异常: {e}")

    if app:
        try:
            app.quit()
        except Exception:
            pass


_win_console_ctrl_handler_ref = None

def _setup_signal_handlers():
    """💡 信号与异常处理器：双重捕获控制台 Ctrl+C (SIGINT)、SIGTERM、sys.excepthook 与 Windows 原生控制台事件，确保 100% 自动保存"""
    def _sig_handler(sig, frame):
        print("\n[SBC Launcher] 收到退出信号 (Ctrl+C)，正在自动保存持仓盯盘窗口...")
        try:
            quit_and_save_all_sbc_windows()
        except Exception as err:
            print(f"[SBC Launcher] 信号退出保存异常: {err}")
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _sig_handler)
    except Exception:
        pass

    # 💡 核心保护：自定义 sys.excepthook 拦截 Qt 槽函数（如 _check_hover、QTimer 等）中抛出的 KeyboardInterrupt
    # 严格禁止在 sys.excepthook 中抛出异常或调用 sys.exit()，否则 Python 会打印 "Error in sys.excepthook"！
    def _sbc_excepthook(exc_type, exc_val, exc_tb):
        try:
            if isinstance(exc_type, type) and issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                print("\n[SBC Launcher] 捕获键盘中断/退出信号 (Ctrl+C)，已自动持久化保存持仓盯盘窗口。")
                try:
                    quit_and_save_all_sbc_windows()
                except Exception as err:
                    print(f"[SBC Launcher] 异常钩子持久化保存异常: {err}")
                app = QApplication.instance()
                if app:
                    app.quit()
                return  # 直接返回，绝不 raise / sys.exit()，彻底杜绝 "Error in sys.excepthook"
            else:
                try:
                    quit_and_save_all_sbc_windows()
                except Exception:
                    pass
                if sys.__excepthook__:
                    sys.__excepthook__(exc_type, exc_val, exc_tb)
        except Exception:
            pass

    sys.excepthook = _sbc_excepthook

    # 💡 Windows 原生控制台事件处理器：
    # 当操盘手按 Ctrl+C (CTRL_C_EVENT=0) 或 Ctrl+Break (CTRL_BREAK_EVENT=1) 时，返回 True，
    # 明确告知 Windows 系统此事件已由程序接管处理，让 Python 主线程通过 SIGINT 信号和 excepthook 正常保存退出，不要提前强杀！
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            PHANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

            def _console_ctrl_handler(ctrl_type):
                # 0=CTRL_C_EVENT, 1=CTRL_BREAK_EVENT, 2=CTRL_CLOSE_EVENT
                if ctrl_type in (0, 1):
                    # 返回 True：通知 Windows 不要强杀进程，由 Python 主线程正常落盘退出
                    return True
                elif ctrl_type == 2:
                    # 操盘手直接点 [X] 强行关闭控制台窗口，由 atexit 紧急兜底
                    try:
                        quit_and_save_all_sbc_windows()
                    except Exception:
                        pass
                    return True
                return False

            global _win_console_ctrl_handler_ref
            _win_console_ctrl_handler_ref = PHANDLER_ROUTINE(_console_ctrl_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_win_console_ctrl_handler_ref, True)
        except Exception as e:
            print(f"[SBC Launcher] 注册 Windows 控制台处理器异常: {e}")


def restore_launcher_holdings_windows() -> List[SBCIntradayChartDialog]:
    """【🚀 恢复持仓盯盘窗口】优先从独立配置恢复未关闭的标的；仅在从未初始化的初次启动时才自动读取持仓"""
    restored = []
    cfg_path = _get_launcher_layout_cfg_path()
    has_initialized_config = False
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            has_initialized_config = bool(data.get("initialized", False) or "sbc_holdings_windows" in data or "sbc_open_windows" in data)
            win_list = data.get("sbc_holdings_windows") or data.get("sbc_open_windows") or []
            for item in win_list:
                code = item.get("code")
                if not code:
                    continue
                period = item.get("period_mode", "10d")
                dlg = open_sbc_chart_dialog(None, code=code, period_mode=period)
                if dlg:
                    dlg.show()
                    w = max(640, item.get("width", 680))
                    h = max(420, item.get("height", 420))
                    dlg.setGeometry(item.get("x", 100), item.get("y", 100), w, h)
                    restored.append(dlg)
        except Exception as e:
            print(f"[SBC Launcher] 读取历史盯盘配置异常: {e}")

    # 💡 只有在配置文件彻底不存在且未曾初始化过时，才自动从当前真实持仓标的启动盯盘
    # 一旦操盘手曾启动并手动增减过标的，严禁在恢复时擅自把用户关闭的股票重新拉出来！
    if not restored and not has_initialized_config:
        holdings = _get_current_holding_codes()
        if holdings:
            print(f"[SBC Launcher] 初次启动无历史配置，自动为当前 {len(holdings)} 只持仓股启动独立盯盘窗口...")
            for code in holdings:
                dlg = open_sbc_chart_dialog(None, code=code, period_mode="10d")
                if dlg:
                    dlg.show()
                    restored.append(dlg)
            # 自动平铺重排
            if restored:
                rearrange_all_sbc_windows()

    if restored:
        save_launcher_holdings_windows(force=True)

    return restored


def main():
    import signal
    # 解析命令行参数：过滤掉标志参数，提取有效的股票代码与看盘周期
    non_flag_args = []
    is_holdings_mode = False
    for arg in sys.argv[1:]:
        a = arg.strip()
        if a in ("--holdings", "--sbc-holdings", "--holdings-sbc"):
            is_holdings_mode = True
        elif a == "--sbc":
            continue
        elif not a.startswith("-"):
            non_flag_args.append(a)

    cli_code = None
    period = "10d"
    if non_flag_args:
        cli_code = non_flag_args[0]
        if len(non_flag_args) > 1:
            period = non_flag_args[1]

    if not cli_code:
        is_holdings_mode = True

    if is_holdings_mode:
        # 💡 核心持久化隔离：明确重定向持久化路径到持仓专用配置文件，并标记为持仓盯盘启动器
        os.environ["SBC_LAYOUT_CONFIG_PATH"] = _get_launcher_layout_cfg_path()
        os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"

    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[SBC Launcher] 检查行情服务警告: {e}")

    app = QApplication.instance() or QApplication(sys.argv)

    # 💡 注册 atexit 底层兜底：无论 Python 进程以何种方式终止，退出时均尝试落盘
    import atexit
    atexit.register(quit_and_save_all_sbc_windows)

    # 💡 核心特性：退出时自动独立持久化保存所有盯盘窗口 (双重保险: aboutToQuit + atexit)
    def _on_app_about_to_quit():
        try:
            quit_and_save_all_sbc_windows()
        except Exception as err:
            print(f"[SBC Launcher] 退出持久化警告: {err}")

    app.aboutToQuit.connect(_on_app_about_to_quit)
    _setup_signal_handlers()

    # 💡 心跳定时器：在 Windows 下定期让 Python 解释器获得 GIL 响应 SIGINT/Ctrl+C，避免信号仅在密集槽函数内爆发致命异常
    _keep_alive_timer = QTimer()
    _keep_alive_timer.timeout.connect(lambda: None)
    _keep_alive_timer.start(200)

    if cli_code:
        print(f"[SBC Launcher] 启动指定 SBC 实盘分时窗口: 标的代码={cli_code}, 初始周期={period}")
        window = open_sbc_chart_dialog(code=cli_code, period_mode=period)
        if window:
            window.show()
            if is_holdings_mode:
                save_launcher_holdings_windows(force=True)
    else:
        # 💡 无参启动：专门用来盯持仓的盘
        restored = restore_launcher_holdings_windows()
        if not restored:
            # 若持仓亦为空，启动默认 600733 (严禁读取 ATS 的 recent_codes，彻底杜绝配置串扰)
            code = "600733"
            period = "10d"
            print(f"[SBC Launcher] 无持仓与历史记录，启动默认 SBC 窗口: 标的代码={code}, 周期={period}")
            window = open_sbc_chart_dialog(code=code, period_mode=period)
            if window:
                window.show()
                save_launcher_holdings_windows(force=True)
        else:
            codes_str = ", ".join(getattr(d, 'code', '') for d in restored)
            print(f"[SBC Launcher] 成功自动恢复上次退出的 {len(restored)} 个持仓盯盘窗口: [{codes_str}]")
            save_launcher_holdings_windows(force=True)

    exit_code = 0
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        print("\n[SBC Launcher] 捕获键盘中断 (Ctrl+C)，已自动持久化保存盯盘窗口。")
        quit_and_save_all_sbc_windows()
        exit_code = 0
    except (SystemExit, BaseException) as e:
        quit_and_save_all_sbc_windows()
        if isinstance(e, SystemExit):
            exit_code = e.code if isinstance(e.code, int) else 0
        else:
            exit_code = 0
    finally:
        try:
            quit_and_save_all_sbc_windows()
        except Exception:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
