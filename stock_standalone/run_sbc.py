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
import json
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
from PyQt6.QtCore import QRect
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    open_sbc_chart_dialog,
    rearrange_all_sbc_windows,
)
from sys_utils import ensure_backend_tk_running


def _get_launcher_layout_cfg_path() -> str:
    """【💾 独立持久化】SBC Launcher 专用持仓盯盘配置文件路径"""
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


def save_launcher_holdings_windows():
    """【💾 持久化保存所有盯盘窗口】独立保存至 sbc_launcher_holdings_layout.json"""
    try:
        from PyQt6.sip import isdeleted
        active_list = []
        for w in QApplication.topLevelWidgets():
            if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w) and w.isVisible():
                geo = w.normal_geometry if (getattr(w, 'is_hidden_state', False) and getattr(w, 'normal_geometry', None)) else w.geometry()
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
        data = {"sbc_holdings_windows": active_list}
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


def restore_launcher_holdings_windows() -> List[SBCIntradayChartDialog]:
    """【🚀 恢复持仓盯盘窗口】优先从独立配置恢复；若无则自动读取持仓标的"""
    restored = []
    cfg_path = _get_launcher_layout_cfg_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            win_list = data.get("sbc_holdings_windows", [])
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

    # 若无历史记录，自动从当前真实持仓标的启动盯盘
    if not restored:
        holdings = _get_current_holding_codes()
        if holdings:
            print(f"[SBC Launcher] 无历史配置，自动为当前 {len(holdings)} 只持仓股启动独立盯盘窗口...")
            for code in holdings:
                dlg = open_sbc_chart_dialog(None, code=code, period_mode="10d")
                if dlg:
                    dlg.show()
                    restored.append(dlg)
            # 自动平铺重排
            if restored:
                rearrange_all_sbc_windows()

    return restored


def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[SBC Launcher] 检查行情服务警告: {e}")

    app = QApplication(sys.argv)

    # 💡 核心特性：退出时自动独立持久化保存所有盯盘窗口
    def _on_app_about_to_quit():
        try:
            app.setProperty("is_app_exiting", True)
            save_launcher_holdings_windows()
        except Exception as err:
            print(f"[SBC Launcher] 退出持久化警告: {err}")

    app.aboutToQuit.connect(_on_app_about_to_quit)

    # 解析命令行参数
    has_cli_code = len(sys.argv) > 1 and sys.argv[1].strip()
    if has_cli_code:
        code = sys.argv[1].strip()
        period = sys.argv[2].strip() if len(sys.argv) > 2 else "10d"
        print(f"[SBC Launcher] 启动指定 SBC 实盘分时窗口: 标的代码={code}, 初始周期={period}")
        window = open_sbc_chart_dialog(code=code, period_mode=period)
        if window:
            window.show()
    else:
        # 💡 无参启动：专门用来盯持仓的盘
        restored = restore_launcher_holdings_windows()
        if not restored:
            # 若持仓亦为空，从最近访问或默认 600733 启动
            try:
                from ats.ui.intraday_strategy_dialog import _load_sbc_recent_codes
                recent = _load_sbc_recent_codes()
                code = recent[0] if recent else "600733"
            except Exception:
                code = "600733"
            period = "10d"
            print(f"[SBC Launcher] 无持仓与历史记录，启动默认/最近标的: {code}")
            window = open_sbc_chart_dialog(code=code, period_mode=period)
            if window:
                window.show()
        else:
            codes_str = ", ".join(getattr(d, 'code', '') for d in restored)
            print(f"[SBC Launcher] 成功自动启动并加载 {len(restored)} 个持仓盯盘窗口: [{codes_str}]")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
