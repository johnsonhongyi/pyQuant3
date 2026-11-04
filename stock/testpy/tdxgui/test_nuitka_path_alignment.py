import os
import sys
import tkinter as tk

# 切换到 tdxgui 目录测试
sys.path.insert(0, r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\testpy\tdxgui')

from sys_utils import get_app_root, get_conf_path, is_packaged_env, _is_inside_temp_dir

def test_nuitka_onefile_simulation():
    print("=== Testing Nuitka Onefile Simulation ===")
    
    # 模拟真实存在的 exe 物理目录 (如 C:\Temp)
    fake_exe_dir = r"C:\Temp"
    fake_exe_path = os.path.join(fake_exe_dir, "异动联动_Nuitka.exe")
    fake_temp_dir = r"C:\Temp\stockAlerts_Nuitka"
    
    os.environ["NUITKA_ONEFILE_BINARY"] = fake_exe_path
    os.environ["NUITKA_ONEFILE_DIRECTORY"] = fake_temp_dir
    
    # 重置内部缓存
    import sys_utils
    sys_utils._CACHED_APP_ROOT = None
    if "INSTOCK_APP_ROOT" in os.environ:
        del os.environ["INSTOCK_APP_ROOT"]
        
    app_root = get_app_root()
    print(f"Detected app_root: {app_root}")
    assert app_root.lower() == fake_exe_dir.lower(), f"Expected {fake_exe_dir}, got {app_root}"
    
    # 测试临时目录判断
    assert _is_inside_temp_dir(r"C:\Temp\stockAlerts_Nuitka\window_config.json") == True
    assert _is_inside_temp_dir(r"D:\JohnsonApp\Alerts\window_config.json") == False
    
    # 测试配置文件路径解析
    cfg_path = get_conf_path("window_config.json", app_root)
    print(f"Resolved window_config.json path: {cfg_path}")
    assert cfg_path.lower() == os.path.join(fake_exe_dir, "window_config.json").lower()
    
    # 测试 query_history.json 路径解析
    root = tk.Tk()
    root.withdraw()
    try:
        from history_manager import QueryHistoryManager
        mgr = QueryHistoryManager(root=root, history_file="query_history.json")
        print(f"Resolved history_file in QueryHistoryManager: {mgr.history_file}")
        assert mgr.history_file.lower() == os.path.join(fake_exe_dir, "query_history.json").lower()
    finally:
        root.destroy()
    
    print("=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_nuitka_onefile_simulation()
