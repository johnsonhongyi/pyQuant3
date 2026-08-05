import sys
import os

# 将项目根目录放入 sys.path 避免 ModuleNotFoundError
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入 Acer 性能控制器
from webTools.window_manager.core import AcerPerformanceController

def verify_performance_integration():
    print("=== 测试 Acer Triton 500 性能与界面联动功能 ===")
    
    ctl = AcerPerformanceController()
    
    # 1. 检查 WMI 硬件驱动支持
    supported = ctl.is_supported()
    print(f"[1/3] Acer WMI 驱动支持判定: {supported}")
    
    if not supported:
        print("[-] 提示: 当前系统未检测到 Acer WMI 硬件控制类")
        return

    # 2. 批量应用 Profile 并一键呼出界面
    print("\n[2/2] 正在应用【狂暴 Extreme 超频 + 狂暴 Max 风扇】配置并一键前置显示 PredatorSense 界面...")
    profile = {
        "overclock_mode": "Extreme",
        "coolboost": True,
        "fan_mode": "Max",
        "show_gui": True  # 自动显化前置主界面
    }
    
    ok, msg = ctl.apply_performance_profile(profile)
    print(f"  -> 执行结果 ok={ok}")
    print(f"  -> 详细日志: {msg}")
    
    print("\n=== 测试完成！请查看屏幕上是否自动唤出了 PredatorSense 控制面板 ===")

if __name__ == "__main__":
    verify_performance_integration()
