# -*- coding: utf-8 -*-
"""
验证通达信等软件附属浮窗（上证指数 999999）防拉伸保护与整体操作窗口功能的集成测试套件
"""
import sys
import os
import ctypes
from ctypes import wintypes
import time

user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW("winsta0", False, 0x00020000 | 0x037F)
if hwinsta:
    user32.SetProcessWindowStation(hwinsta)
    hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

sys.path.insert(0, r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\webTools")
from window_manager import core

def run_suite():
    print("=== 开始执行整体操作窗口与防拉伸保护验证测试 ===")
    
    # 1. 查找上证指数窗口
    hwnds = core.find_windows_by_title_safe("上证指数(999999)")
    if not hwnds:
        print("❌ 未在桌面找到'上证指数(999999)'窗口，尝试通过模糊搜索匹配...")
        hwnds = core.find_windows_by_title_safe("999999")
        
    assert len(hwnds) > 0, "未能定位到上证指数窗口"
    hwnd_sh, title_sh = hwnds[0]
    print(f"[OK] 定位到上证指数窗口: HWND={hwnd_sh} (0x{hwnd_sh:X})")

    # 2. 验证宿主从属关系识别
    rel_sh = core.get_window_host_relation(hwnd_sh)
    print(f"宿主关系检测结果: is_sub={rel_sh['is_sub_window']}, host_hwnd={rel_sh['host_hwnd']}")
    assert rel_sh["is_sub_window"] is True, "未能识别上证指数小窗为附属/从属窗口"
    assert rel_sh["host_hwnd"] > 0, "未能找到有效的宿主主窗口句柄"
    print(f"[OK] 成功判定为从属浮窗，宿主窗口: HWND={rel_sh['host_hwnd']}")

    # 3. 验证宿主主窗口的独立性
    rel_host = core.get_window_host_relation(rel_sh["host_hwnd"])
    print(f"宿主主窗口自身关系检测: is_sub={rel_host['is_sub_window']}")
    assert rel_host["is_sub_window"] is False, "宿主主窗口不应被误判为从属窗口"
    print("[OK] 宿主主窗口属性判定正确 (独立顶层主窗口)")

    # 4. 验证整体家族提取能力 (Family Group)
    family = core.get_window_family(hwnd_sh)
    print(f"整体窗口家族: 附属浮窗数量={len(family['children'])}")
    assert family["main_hwnd"] == rel_sh["host_hwnd"], "家族主窗口句柄不匹配"
    assert any(c["hwnd"] == hwnd_sh for c in family["children"]), "家族子列表未包含当前小窗口"
    print("[OK] 整体窗口家族归属识别完全正确")

    # 5. 核心测试：模拟用户移动与安全恢复，验证绝对不发生图4那样的横向拉伸变形
    orig_rect = core.get_window_rect(hwnd_sh)
    print(f"测试前原始坐标与尺寸: {orig_rect}")

    # 模拟图3移动到新位置 (1707, -322, 477, 333)
    target_move = "1707,-322,477,333"
    print(f"-> 模拟图3移动至: {target_move}")
    success_move = core.set_window_hwnd_pos(hwnd_sh, target_move, title=title_sh)
    time.sleep(0.1)
    rect_after_move = core.get_window_rect(hwnd_sh)
    print(f"-> 移动后实际位置: {rect_after_move}")
    assert abs(rect_after_move[0] - 1707) <= 4, "移动 X 坐标未对齐"
    assert abs(rect_after_move[1] - (-322)) <= 4, "移动 Y 坐标未对齐"
    assert rect_after_move[2] < 600, f"宽度异常拉伸: {rect_after_move[2]}"

    # 模拟恢复到目标配置位置 (1946, -296, 477, 333)
    target_restore = "1946,-296,477,333"
    print(f"-> 模拟执行应用布局恢复至: {target_restore}")
    success_restore = core.set_window_hwnd_pos(hwnd_sh, target_restore, title=title_sh)
    time.sleep(0.1)
    rect_after_restore = core.get_window_rect(hwnd_sh)
    print(f"-> 恢复后实际位置: {rect_after_restore}")
    assert abs(rect_after_restore[0] - 1946) <= 4, "恢复 X 坐标未对齐"
    assert abs(rect_after_restore[1] - (-296)) <= 4, "恢复 Y 坐标未对齐"
    assert rect_after_restore[2] < 600, f"严重缺陷：窗口依然被横向拉伸为长条！当前宽={rect_after_restore[2]}"
    print(f"[OK] 防拉伸保护与安全平移完全生效！恢复后宽度正常 ({rect_after_restore[2]}px)，完美保持图1浮窗形态！")

    print("\n[PASS] 全部断言通过！Bug 彻底解决，整体操作窗口与安全防拉伸通道功能完备！")

if __name__ == '__main__':
    run_suite()
