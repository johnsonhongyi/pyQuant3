import win32api
import win32con
import json
import pywintypes

# def get_current_display_configuration():
#     """
#     获取所有连接的显示器的当前配置。
#     """
#     display_info = []
    
#     def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
#         info = win32api.GetMonitorInfo(hMonitor)
#         devmode = win32api.EnumDisplaySettings(info.get("Device", ""), win32con.ENUM_CURRENT_SETTINGS)
        
#         display_info.append({
#             "device_name": info.get("Device", ""),
#             "width": devmode.PelsWidth,
#             "height": devmode.PelsHeight,
#             "x": devmode.Position_x,
#             "y": devmode.Position_y,
#             "is_primary": (info.get("Flags") & win32con.MONITORINFOF_PRIMARY) != 0
#         })
#         return 1  # 继续枚举
    
#     win32api.EnumDisplayMonitors(None, None, monitor_enum_proc, 0)
#     return display_info

# def save_display_configuration(filename="display_config.json"):
#     """
#     保存当前显示器配置到 JSON 文件。
#     """
#     try:
#         config = get_current_display_configuration()
#         with open(filename, "w", encoding="utf-8") as f:
#             json.dump(config, f, indent=4)
#         print(f"当前显示器配置已成功保存到 '{filename}'。")
#     except Exception as e:
#         print(f"保存配置时出错: {e}")

def get_current_display_configuration():
    """
    获取所有连接的显示器的当前配置。
    """
    display_info = []

    # 直接调用 EnumDisplayMonitors() 获取所有监视器的句柄列表
    monitor_handles = win32api.EnumDisplayMonitors()

    if not monitor_handles:
        print("未检测到任何监视器。")
        return []

    for hMonitor, _, _ in monitor_handles:
        # 使用 GetMonitorInfo 和 EnumDisplaySettings 获取详细信息
        info = win32api.GetMonitorInfo(hMonitor)
        device_name = info.get("Device", "")
        devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)

        display_info.append({
            "device_name": device_name,
            "width": devmode.PelsWidth,
            "height": devmode.PelsHeight,
            "x": devmode.Position_x,
            "y": devmode.Position_y,
            "is_primary": (info.get("Flags") & win32con.MONITORINFOF_PRIMARY) != 0
        })

    return display_info

def save_display_configuration(filename="display_config.json"):
    """
    保存当前显示器配置到 JSON 文件。
    """

    monitor = get_monitor_details()
    filename = f'{monitor}_monitor{filename}'
    try:
        config = get_current_display_configuration()
        if not config:
            return

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"当前显示器配置已成功保存到 '{filename}'。")
    except Exception as e:
        print(f"保存配置时出错: {e}")

# import win32api
# import win32con
# import json

# def restore_display_configuration(filename="display_config.json"):
#     """
#     从 JSON 文件恢复显示器配置。
#     """
#     try:
#         with open(filename, "r", encoding="utf-8") as f:
#             saved_config = json.load(f)
#     except FileNotFoundError:
#         print(f"错误: 配置文件 '{filename}' 未找到。请先运行保存脚本。")
#         return
#     except Exception as e:
#         print(f"读取配置文件时出错: {e}")
#         return

#     for monitor in saved_config:
#         device_name = monitor["device_name"]
        
#         try:
#             devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
            
#             # 更新分辨率和位置
#             devmode.PelsWidth = monitor["width"]
#             devmode.PelsHeight = monitor["height"]
#             devmode.Position_x = monitor["x"]
#             devmode.Position_y = monitor["y"]

#             # 如果需要设置为主显示器，则进行特殊处理
#             if monitor["is_primary"]:
#                 # 使用 CDS_SET_PRIMARY 将其设置为主显示器
#                 flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET | win32con.CDS_SET_PRIMARY
#                 win32api.ChangeDisplaySettingsEx(device_name, devmode, None, flags, None)
#             else:
#                 flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET
#                 win32api.ChangeDisplaySettingsEx(device_name, devmode, None, flags, None)
                
#             print(f"显示器 '{device_name}' 已更新。")
#         except pywintypes.error as e:
#             print(f"更改显示器 '{device_name}' 配置失败: {e}")

#     # 重置显示模式以应用所有更改
#     win32api.ChangeDisplaySettings(None, 0)
#     print("所有显示器设置已应用。")


def restore_display_configuration(filename="display_config.json"):
    """
    从 JSON 文件恢复显示器配置。
    """

    monitor = get_monitor_details()
    filename = f'{monitor}_monitor{filename}'

    print(f"restore_display monitors:{filename}")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            saved_config = json.load(f)
    except FileNotFoundError:
        print(f"错误: 配置文件 '{filename}' 未找到。请先运行保存脚本。")
        return
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return

    for monitor in saved_config:
        device_name = monitor["device_name"]
        
        try:
            # 获取当前显示器的 DEVMODE 对象作为基础
            devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
            
            # 更新 DEVMODE 对象的属性
            devmode.PelsWidth = monitor["width"]
            devmode.PelsHeight = monitor["height"]
            devmode.Position_x = monitor["x"]
            devmode.Position_y = monitor["y"]

            # 根据是否为主显示器设置标志
            if monitor["is_primary"]:
                # 使用 CDS_SET_PRIMARY 将其设置为主显示器
                flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET | win32con.CDS_SET_PRIMARY
            else:
                flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET
                
            # 调用封装好的函数，只传入三个参数
            win32api.ChangeDisplaySettingsEx(device_name, devmode, flags)
            
            print(f"显示器 '{device_name}' 的设置已更新。")
        except pywintypes.error as e:
            print(f"更改显示器 '{device_name}' 配置失败: {e}")

    # 重置显示模式以应用所有更改
    win32api.ChangeDisplaySettings(None, 0)
    print("所有显示器设置已应用。")

# import win32api

def get_monitor_details():
    """
    Retrieves information for all connected monitors.
    """
    # Call EnumDisplayMonitors() with no arguments to get a list of monitors.
    # It returns a list of tuples, each containing a monitor handle.
    monitor_handles = win32api.EnumDisplayMonitors()
    count = 0
    if not monitor_handles:
        print("No monitors detected.")
        return

    print("Connected monitors:")
    for handle_tuple in monitor_handles:
        count +=1
        # The handle is the first element of the tuple.
        monitor_handle = handle_tuple[0]

        # Use GetMonitorInfo to get detailed information for the monitor.
        # This function returns a dictionary.
        info = win32api.GetMonitorInfo(monitor_handle)

        device_name = info.get("Device", "Unknown")
        is_primary = (info.get("Flags") & win32con.MONITORINFOF_PRIMARY) != 0

        # The 'Monitor' key contains the bounding box of the display.
        left, top, right, bottom = info["Monitor"]
        width = right - left
        height = bottom - top

        print(f"  Device Name: {device_name}")
        print(f"  Resolution: {width}x{height}")
        print(f"  Position: x={left}, y={top}")
        print(f"  Is Primary: {is_primary}")
        print("-" * 20)
    return count

# if __name__ == "__main__":
#     restore_display_configuration()

if __name__ == "__main__":
    monitor = get_monitor_details()
    print(f'monitor Count:{monitor}')
    # save_display_configuration()
    # restore_display_configuration()
