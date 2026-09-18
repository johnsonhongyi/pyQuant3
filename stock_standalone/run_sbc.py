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
from typing import List, Optional, Tuple

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


def _sort_holding_items_by_spatial_order(items: List[dict]) -> List[dict]:
    """
    【🪟 按物理屏幕原有显示顺序排序】
    先自上而下逐行分组，同一行内自左向右（X递增），超出屏幕宽度则换行。
    确保保存进配置与快照中的窗口顺序与操盘手排布好的视觉顺序 100% 严格一致。
    """
    if len(items) <= 1:
        return items
    s_items = sorted(items, key=lambda it: (it.get("y", 0), it.get("x", 0)))
    rows = []
    for it in s_items:
        cy = it.get("y", 0) + it.get("height", 420) / 2.0
        placed = False
        for r in rows:
            avg_cy = sum(x.get("y", 0) + x.get("height", 420) / 2.0 for x in r) / len(r)
            avg_h = sum(x.get("height", 420) for x in r) / len(r)
            if abs(cy - avg_cy) < max(100, avg_h * 0.45):
                r.append(it)
                placed = True
                break
        if not placed:
            rows.append([it])
    result = []
    for r in rows:
        r.sort(key=lambda it: it.get("x", 0))
        result.extend(r)
    return result


def _calculate_safe_geometry_with_wrap(item: dict, sg, prev_bottom: int) -> Tuple[int, int, int, int, int]:
    """
    【🪟 原位恢复排布算法】
    原来在什么位置排布就在什么位置排布，严格保留持久化的物理尺寸与所在物理屏幕，绝不强行将副屏窗口拽回主屏。
    返回 (target_x, target_y, w, h, new_bottom)
    """
    w = max(320, item.get("width", 680))
    h = max(180, item.get("height", 420))
    orig_x = item.get("x", sg.left() + 12)
    orig_y = item.get("y", sg.top() + 12)

    from gui_utils import clamp_window_to_screens
    target_x, target_y = clamp_window_to_screens(orig_x, orig_y, w, h)

    new_bottom = max(prev_bottom, target_y + h)
    return target_x, target_y, w, h, new_bottom


_last_save_holdings_time = 0.0
_last_saved_content_fingerprint = ""
_is_restoring_holdings = False

def save_launcher_holdings_windows(force: bool = False, allow_empty: bool = False):
    """【💾 集中持久化保存持仓盯盘窗口】独立保存至 sbc_launcher_holdings_layout.json，支持维护最近 3 组历史快照与防清零保护"""
    global _last_save_holdings_time, _last_saved_content_fingerprint
    now = time.time()
    if not force and (now - _last_save_holdings_time < 0.8):
        return
    _last_save_holdings_time = now
    try:
        from PyQt6.sip import isdeleted
        from datetime import datetime
        active_list = []
        app_inst = QApplication.instance()
        is_exiting = bool(app_inst and app_inst.property("is_app_exiting"))

        # 1. 优先扫描 topLevelWidgets()
        for w in QApplication.topLevelWidgets():
            if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w):
                # 已经被手动关闭或标记正在关闭的实例，无论何时均严禁持久化
                if getattr(w, '_is_closing', False):
                    continue
                # 必须为当前可见窗口，或者处于贴边收缩隐藏状态 (is_hidden_state=True)
                if not w.isVisible() and not getattr(w, 'is_hidden_state', False) and not is_exiting:
                    continue
                geo = w.normal_geometry if (getattr(w, 'is_hidden_state', False) and getattr(w, 'normal_geometry', None)) else (w.normal_geometry or w.geometry())
                c = getattr(w, 'code', None)
                cur_period = getattr(w, '_current_period_mode', '10d')
                if c:
                    c_clean = str(c).zfill(6)
                    if not any(item["code"] == c_clean for item in active_list):
                        active_list.append({
                            "code": c_clean,
                            "x": geo.x(),
                            "y": geo.y(),
                            "width": geo.width(),
                            "height": geo.height(),
                            "period_mode": cur_period,
                        })

        # 2. 若 topLevelWidgets 为空，回退从内存注册中心 SBCWindowMemoryManager 提取
        if not active_list:
            try:
                from ats.ui.intraday_strategy_dialog import SBCWindowMemoryManager
                mem_wins = SBCWindowMemoryManager.get_instance().get_all_windows()
                if mem_wins:
                    active_list = [dict(item) for item in mem_wins if isinstance(item, dict) and item.get("code")]
            except Exception:
                pass

        # 💡 按屏幕物理空间显示顺序稳定排序 (先自上而下，同一行自左向右，除非换行)
        active_list = _sort_holding_items_by_spatial_order(active_list)

        cfg_path = _get_launcher_layout_cfg_path()
        old_data = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
            except Exception:
                old_data = {}

        # 💡 铁壁防冲洗守卫 (P0)：若 active_list 为空，但历史已有有效记录，且未显式允许清空，严禁覆盖写入 0 个！
        if len(active_list) == 0:
            if old_data.get("sbc_holdings_windows") or old_data.get("recent_history_snapshots"):
                print(f"[SBC Launcher] 🛡 保护机制触发: 退出或落盘探测窗口数为 0，保留现有有效配置，严禁覆盖写 0！")
                return
            if not allow_empty:
                return

        # 💡 内容指纹比对：若待保存内容与上次一致且文件已存在，且非强制退出流程，跳过无意义的重复落盘与控制台打印
        current_fingerprint = json.dumps(active_list, sort_keys=True)
        if not is_exiting and os.path.exists(cfg_path) and current_fingerprint == _last_saved_content_fingerprint:
            return

        # 💡 【核心：维护最近 3 组历史快照 recent_history_snapshots】
        recent_snapshots = old_data.get("recent_history_snapshots", [])
        if not isinstance(recent_snapshots, list):
            recent_snapshots = []

        if len(active_list) > 0:
            current_codes = sorted([item["code"] for item in active_list])
            # 只有当新快照与最近一组快照不同时才压入
            should_add_snapshot = True
            if recent_snapshots and isinstance(recent_snapshots[0], dict):
                last_codes = sorted(recent_snapshots[0].get("codes", []))
                if last_codes == current_codes:
                    should_add_snapshot = False

            if should_add_snapshot:
                new_snap = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "codes": [item["code"] for item in active_list],
                    "windows": active_list
                }
                recent_snapshots.insert(0, new_snap)
                recent_snapshots = recent_snapshots[:3]

        # 💡 同步写入 sbc_holdings_windows 与 sbc_open_windows，并标记 initialized=True 与 3 组历史快照
        data = {
            "sbc_holdings_windows": active_list,
            "sbc_open_windows": active_list,
            "initialized": True,
            "recent_history_snapshots": recent_snapshots
        }
        if "sbc_period_modes" in old_data:
            data["sbc_period_modes"] = old_data["sbc_period_modes"]

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
        _last_saved_content_fingerprint = current_fingerprint
        print(f"[SBC Launcher] 成功集中持久化保存 {len(active_list)} 个持仓盯盘窗口 (保留最近 {len(recent_snapshots)} 组历史快照) 至 {cfg_path}")
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


def get_launcher_history_snapshots() -> List[dict]:
    """【📂 获取最近保存的历史快照列表】最多 3 组"""
    cfg_path = _get_launcher_layout_cfg_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snapshots = data.get("recent_history_snapshots", [])
            if isinstance(snapshots, list):
                return snapshots
        except Exception:
            pass
    return []


def switch_to_history_snapshot(snapshot_idx: int) -> List[SBCIntradayChartDialog]:
    """【📂 运行时一键切换至指定的历史快照组】
    snapshot_idx: 1 (最新第 1 组), 2 (上一组), 3 (更早一组)
    1. 关闭不在该快照中的当前窗口；
    2. 打开/定位该快照中的所有窗口；
    3. 自动触发平铺重排与前台激活。
    """
    snapshots = get_launcher_history_snapshots()
    if not snapshots or snapshot_idx < 1 or snapshot_idx > len(snapshots):
        print(f"[SBC Launcher] ⚠ 历史快照 {snapshot_idx} 不存在 (当前共有 {len(snapshots)} 组)")
        return []

    target_snap = snapshots[snapshot_idx - 1]
    snap_time = target_snap.get("time", "未知时间")
    win_list = target_snap.get("windows", [])
    if not win_list:
        return []

    target_codes = {str(item.get("code")).zfill(6) for item in win_list if item.get("code")}
    print(f"[SBC Launcher] 🚀 正在一键切换至快照 {snapshot_idx} (时间: {snap_time}): {list(target_codes)}...")

    # 1. 关闭不在目标快照中的窗口
    try:
        from PyQt6.sip import isdeleted
        for w in list(QApplication.topLevelWidgets()):
            if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w):
                c = getattr(w, "code", None)
                if c:
                    c_clean = str(c).zfill(6)
                    if c_clean not in target_codes:
                        w.close()
    except Exception as e_close:
        print(f"[SBC Launcher] 关闭非快照窗口提示: {e_close}")

    # 2. 打开或激活目标快照窗口 (原来在什么位置排布就在什么位置排布，除非换行)
    opened = []
    screen_obj = QApplication.primaryScreen()
    sg = screen_obj.availableGeometry() if screen_obj else QRect(0, 0, 1920, 1080)
    prev_bottom = sg.top() + 12

    for item in win_list:
        c = item.get("code")
        if not c:
            continue
        p = item.get("period_mode", "10d")
        dlg = open_sbc_chart_dialog(None, code=c, period_mode=p)
        if dlg:
            dlg.show()
            gx, gy, gw, gh, prev_bottom = _calculate_safe_geometry_with_wrap(item, sg, prev_bottom)
            dlg.setGeometry(gx, gy, gw, gh)
            opened.append(dlg)

    # 3. 自动触发平铺重排 (保持原有显示位置顺序)
    if opened:
        rearrange_all_sbc_windows()
        print(f"[SBC Launcher] ✅ 成功切换至快照 {snapshot_idx}，已恢复并平铺 {len(opened)} 个盯盘窗口！")

    return opened


def restore_launcher_holdings_windows(snapshot_index: Optional[int] = None) -> List[SBCIntradayChartDialog]:
    """【🚀 恢复持仓盯盘窗口】
    若指定 snapshot_index (1, 2, 3)，精准加载该组历史快照；
    未指定时优先从独立配置恢复未关闭标的，为空时自动从快照 1 灾备恢复。
    恢复位置遵循“原来在什么位置排布就在什么位置排布，除非换行”。
    """
    global _is_restoring_holdings
    _is_restoring_holdings = True
    restored = []
    cfg_path = _get_launcher_layout_cfg_path()
    has_initialized_config = False
    try:
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                has_initialized_config = bool(data.get("initialized", False) or "sbc_holdings_windows" in data or "sbc_open_windows" in data)
                snapshots = data.get("recent_history_snapshots", [])

                win_list = []
                if snapshot_index is not None and isinstance(snapshots, list) and 1 <= snapshot_index <= len(snapshots):
                    snap = snapshots[snapshot_index - 1]
                    win_list = snap.get("windows", [])
                    snap_time = snap.get("time", "历史快照")
                    print(f"[SBC Launcher] 📂 操盘手指定加载第 {snapshot_index} 组历史快照 ({snap_time})，共 {len(win_list)} 个窗口...")
                else:
                    win_list = data.get("sbc_holdings_windows") or data.get("sbc_open_windows") or []
                    # 💡 灾备兜底：若当前 win_list 为空，优先从 recent_history_snapshots[0] 历史快照提取
                    if not win_list:
                        if snapshots and isinstance(snapshots, list) and isinstance(snapshots[0], dict):
                            snap_win_list = snapshots[0].get("windows", [])
                            if snap_win_list:
                                win_list = snap_win_list
                                snap_time = snapshots[0].get("time", "历史快照")
                                print(f"[SBC Launcher] 🛡 当前盯盘配置为空，已自动从最近历史快照 ({snap_time}) 灾备回退恢复 {len(win_list)} 个窗口！")

                screen_obj = QApplication.primaryScreen()
                sg = screen_obj.availableGeometry() if screen_obj else QRect(0, 0, 1920, 1080)
                prev_bottom = sg.top() + 12

                for item in win_list:
                    code = item.get("code")
                    if not code:
                        continue
                    period = item.get("period_mode", "10d")
                    dlg = open_sbc_chart_dialog(None, code=code, period_mode=period, record_open=False)
                    if dlg:
                        dlg.show()
                        gx, gy, gw, gh, prev_bottom = _calculate_safe_geometry_with_wrap(item, sg, prev_bottom)
                        dlg.setGeometry(gx, gy, gw, gh)
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
                # 仅在初次根据真实持仓全新初始化生成新窗口时才持久化落盘一次
                if restored:
                    save_launcher_holdings_windows(force=True)
    finally:
        _is_restoring_holdings = False

    return restored


def main():
    import signal
    # 解析命令行参数：过滤掉标志参数，提取有效的股票代码、看盘周期与历史快照索引
    non_flag_args = []
    is_holdings_mode = False
    snapshot_idx = None

    args = sys.argv[1:]
    idx = 0
    while idx < len(args):
        arg = args[idx].strip()
        if arg in ("--holdings", "--sbc-holdings", "--holdings-sbc"):
            is_holdings_mode = True
        elif arg in ("--snapshot", "-s"):
            if idx + 1 < len(args):
                try:
                    snapshot_idx = int(args[idx + 1])
                    idx += 1
                except Exception:
                    pass
        elif arg.startswith("--snapshot="):
            try:
                snapshot_idx = int(arg.split("=")[1])
            except Exception:
                pass
        elif arg == "--sbc":
            pass
        elif not arg.startswith("-"):
            non_flag_args.append(arg)
        idx += 1

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

    # 💡 设置全局暗黑调色板与 QToolTip 样式，确保独立进程中所有 ToolTip 呈现高质感暗黑金融配色
    try:
        from PyQt6.QtGui import QPalette, QColor
        app_pal = app.palette()
        app_pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#14141f"))
        app_pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#f1f5f9"))
        app.setPalette(app_pal)
        app.setStyleSheet((app.styleSheet() or "") + """
            QToolTip {
                background-color: #14141f;
                color: #f1f5f9;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 6px 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 9pt;
                font-weight: normal;
            }
        """)
    except Exception:
        pass

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

    # 💡 心跳定时器与孤儿进程自动守护 (P0)：
    # 1. 在 Windows 下定期让 Python 解释器获得 GIL 响应 SIGINT/Ctrl+C；
    # 2. 定期检测父进程 (ATS_MAIN_PID) 存活性，若父进程已退出，自动持久化保存并安全退出，绝不残留后台孤儿进程！
    parent_pid_str = os.environ.get("ATS_MAIN_PID")
    _parent_pid = int(parent_pid_str) if (parent_pid_str and parent_pid_str.isdigit()) else None

    def _on_keep_alive_and_orphan_check():
        if _parent_pid:
            try:
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    SYNCHRONIZE = 0x00100000
                    h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, _parent_pid)
                    if h_proc:
                        kernel32.CloseHandle(h_proc)
                    else:
                        print(f"\n[SBC Launcher] 探针检测到父进程 (PID={_parent_pid}) 已关闭，自动保存持仓盯盘并退出...")
                        quit_and_save_all_sbc_windows()
                        app_inst = QApplication.instance()
                        if app_inst:
                            app_inst.quit()
                else:
                    os.kill(_parent_pid, 0)
            except Exception:
                print(f"\n[SBC Launcher] 父进程已终止，自动安全保存并退出...")
                quit_and_save_all_sbc_windows()
                app_inst = QApplication.instance()
                if app_inst:
                    app_inst.quit()

    _keep_alive_timer = QTimer()
    _keep_alive_timer.timeout.connect(_on_keep_alive_and_orphan_check)
    _keep_alive_timer.start(500)

    if cli_code:
        print(f"[SBC Launcher] 启动指定 SBC 实盘分时窗口: 标的代码={cli_code}, 初始周期={period}")
        window = open_sbc_chart_dialog(code=cli_code, period_mode=period)
        if window:
            window.show()
    else:
        # 💡 无参启动：专门用来盯持仓的盘 (支持通过 --snapshot N 指定加载哪一组历史快照)
        restored = restore_launcher_holdings_windows(snapshot_index=snapshot_idx)
        if not restored:
            # 若持仓亦为空，启动默认 600733 (严禁读取 ATS 的 recent_codes，彻底杜绝配置串扰)
            code = "600733"
            period = "10d"
            print(f"[SBC Launcher] 无持仓与历史记录，启动默认 SBC 窗口: 标的代码={code}, 周期={period}")
            window = open_sbc_chart_dialog(code=code, period_mode=period)
            if window:
                window.show()
        else:
            codes_str = ", ".join(getattr(d, 'code', '') for d in restored)
            print(f"[SBC Launcher] 成功自动恢复上次退出的 {len(restored)} 个持仓盯盘窗口: [{codes_str}]")

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
