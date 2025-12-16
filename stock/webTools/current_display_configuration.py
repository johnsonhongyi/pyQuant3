import win32api
import win32con
import json
import pywintypes
import os


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

    # monitor = get_monitor_details()
    # monitor = get_monitor_details_all()
    monitor = get_monitor_details_all_with_scale()
    detal_summary = monitor["summary"]
    filename = f'{detal_summary}_monitor{filename}'
    if os.path.exists(filename):
        print(f'filename is exists:{os.path.join(os.getcwd(), filename)}')
        print(f'return and no save')
        return
    try:
        # config = get_current_display_configuration()
        config = get_monitor_details_all_with_scale()
        if not config:
            return

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"当前显示器配置已成功保存到 '{filename}'。")
    except Exception as e:
        print(f"保存配置时出错: {e}")

def is_same_display_config(current, saved):
    """
    判断当前显示器配置与已保存配置是否一致
    支持逻辑分辨率 + scale 自动匹配
    """
    if len(current) != len(saved):
        return False
    # print(f'current:{current}')
    # print(f'saved:{saved}')
    # 建立 key 映射，使用 device_name 或 (logical_width, logical_height, scale)
    def build_key(m):
        # 如果 device_name 唯一可用就用它，否则用逻辑分辨率+scale
        return m.get("device_name") or (m.get("logical_width"), m.get("logical_height"), m.get("scale"))

    cur_map = {build_key(m): m for m in current}
    sav_map = {build_key(m): m for m in saved}

    if cur_map.keys() != sav_map.keys():
        return False

    # 核心字段对比
    fields = ("width", "height", "x", "y", "is_primary", "scale", "logical_width", "logical_height")

    for key, cur in cur_map.items():
        sav = sav_map[key]
        for f in fields:
            if cur.get(f) != sav.get(f):
                return False

    return True


# def is_same_display_config(current, saved):
#     """
#     判断当前显示器配置与已保存配置是否一致
#     """
#     if len(current) != len(saved):
#         return False

#     # 用 device_name 做 key，避免顺序问题
#     cur_map = {m["device_name"]: m for m in current}
#     sav_map = {m["device_name"]: m for m in saved}

#     if cur_map.keys() != sav_map.keys():
#         return False

#     fields = ("width", "height", "x", "y", "is_primary")

#     for dev, cur in cur_map.items():
#         sav = sav_map[dev]
#         for f in fields:
#             if cur.get(f) != sav.get(f):
#                 return False

#     return True

# def restore_display_configuration(filename="display_config.json"):
#     """
#     从 JSON 文件恢复显示器配置。
#     """

#     # monitor = get_monitor_details()
#     # filename = f'{monitor}_monitor{filename}'
#     monitor = get_monitor_details_all()
#     detal_summary = monitor["summary"]
#     saved_config_load = monitor["monitors"]
#     filename = f'{detal_summary}_monitor{filename}'
#     if not os.path.exists(filename):
#         print(f"filename is'not exists:{os.path.join(os.getcwd(), filename)}")
#         print(f'will to save and return')
#         save_display_configuration()
#         return
#     print(f"restore_display monitors:{filename}")
#     try:
#         with open(filename, "r", encoding="utf-8") as f:
#             saved_config = json.load(f)
#     except FileNotFoundError:
#         print(f"错误: 配置文件 '{filename}' 未找到。请先运行保存脚本。")
#         return
#     except Exception as e:
#         print(f"读取配置文件时出错: {e}")
#         return

def restore_display_configuration(filename="display_config.json"):
    """
    从 JSON 文件恢复显示器配置
    """
    # monitor_info = get_monitor_details_all()
    monitor_info = get_monitor_details_all_with_scale()
    detail_summary = monitor_info["summary"]
    current_monitors = monitor_info["monitors"]

    filename = f"{detail_summary}_monitor{filename}"

    if not os.path.exists(filename):
        print(f"[INFO] 配置文件不存在: {os.path.join(os.getcwd(), filename)}")
        print("[INFO] 将保存当前配置并退出")
        save_display_configuration()
        return

    print(f"[INFO] restore_display monitors: {filename}")

    try:
        with open(filename, "r", encoding="utf-8") as f:
            saved_config = json.load(f)
    except Exception as e:
        print(f"[ERROR] 读取配置文件失败: {e}")
        return


    save_monitors = saved_config["monitors"]
    # ✅ 关键判断点
    if is_same_display_config(current_monitors,save_monitors ):
        print("[INFO] 当前显示器配置与保存配置完全一致，跳过恢复")
        return

    current_str = "\n".join(str(m) for m in current_monitors)
    saved_str = "\n".join(str(m) for m in save_monitors)

    print(f"current_monitors:\n{current_str}")
    print(f"saved_config:\n{saved_str}")

    print("[WARN] 检测到显示器配置变化，开始恢复保存配置...")
    print(f'current_monitors :current_monitors')



    for monitor in save_monitors:
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


def get_monitor_details_all_with_scale():
    """
    获取所有显示器信息，同时计算 scale（DPI缩放）
    - 主显示器排在最前
    - 返回 monitors 列表 + 汇总字符串
    """
    import win32api, win32con

    monitor_handles = win32api.EnumDisplayMonitors()
    if not monitor_handles:
        return {"monitors": [], "summary": "0"}

    monitors = []

    for handle_tuple in monitor_handles:
        monitor_handle = handle_tuple[0]

        # 逻辑分辨率（系统显示逻辑）
        info = win32api.GetMonitorInfo(monitor_handle)
        device_name = info.get("Device", "Unknown")
        is_primary = (info.get("Flags", 0) & win32con.MONITORINFOF_PRIMARY) != 0
        left, top, right, bottom = info["Monitor"]
        logical_width = right - left
        logical_height = bottom - top

        # 物理分辨率（实际设置）
        devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
        physical_width = devmode.PelsWidth
        physical_height = devmode.PelsHeight

        # 根据逻辑/物理分辨率计算 scale
        scale_x = physical_width / logical_width if logical_width else 1.0
        scale_y = physical_height / logical_height if logical_height else 1.0
        # 一般 x/y 相同，取平均
        scale = round((scale_x + scale_y) / 2, 2)

        monitors.append({
            "device_name": device_name,
            "width": physical_width,
            "height": physical_height,
            "x": devmode.Position_x,
            "y": devmode.Position_y,
            "is_primary": is_primary,
            "logical_width": logical_width,
            "logical_height": logical_height,
            "scale": scale
        })

    # 主显示器排前
    monitors.sort(key=lambda x: not x["is_primary"])

    # 汇总字符串，可用于文件命名
    summary = "_".join(f"{m['width']}x{m['height']}@{m['scale']}" for m in monitors)

    return {"monitors": monitors, "summary": summary}

def get_monitor_details_all():
    """
    获取所有显示器信息
    - 主显示器排在最前
    - 返回 monitors 列表 + 汇总字符串
    """
    
    monitor_all = get_monitor_details_all_with_scale()
    monitors = monitor_all["monitors"]  # 列表
    # 主显示器排前
    monitors.sort(key=lambda x: not x["is_primary"])

    # 生成 summary
    count = len(monitors)
    primary_width = None
    other_widths = []

    for m in monitors:
        if m["is_primary"] and primary_width is None:
            primary_width = m["width"]
        else:
            other_widths.append(m["width"])

    parts = [str(count)]
    if primary_width is not None:
        parts.append(str(primary_width))
    parts.extend(str(w) for w in other_widths)

    summary = "_".join(parts)

    print("summary:", summary)
    return monitor_all

    # monitor_handles = win32api.EnumDisplayMonitors()
    # if not monitor_handles:
    #     return {
    #         "monitors": [],
    #         "summary": "0"
    #     }

    # monitors = []

    # for handle_tuple in monitor_handles:
    #     monitor_handle = handle_tuple[0]
    #     info = win32api.GetMonitorInfo(monitor_handle)

    #     device_name = info.get("Device", "Unknown")
    #     is_primary = (info.get("Flags", 0) & win32con.MONITORINFOF_PRIMARY) != 0

    #     left, top, right, bottom = info["Monitor"]
    #     width = right - left
    #     height = bottom - top

    #     monitors.append({
    #         "device_name": device_name,
    #         "width": width,
    #         "height": height,
    #         "x": left,
    #         "y": top,
    #         "is_primary": is_primary
    #     })

    # # ① 主显示器排前
    # monitors.sort(key=lambda x: not x["is_primary"])

    # # ② 生成 summary
    # count = len(monitors)
    # primary_width = None
    # other_widths = []

    # for m in monitors:
    #     if m["is_primary"] and primary_width is None:
    #         primary_width = m["width"]
    #     else:
    #         other_widths.append(m["width"])

    # parts = [str(count)]
    # if primary_width is not None:
    #     parts.append(str(primary_width))
    # parts.extend(str(w) for w in other_widths)

    # summary = "_".join(parts)

    # return {
    #     "monitors": monitors,
    #     "summary": summary
    # }

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

if __name__ == "__main__":
    # monitor = get_monitor_details()
    # print(f'monitor Count:{monitor}')
    monitor_all = get_monitor_details_all()
    # monitor_all = get_monitor_details_all_with_scale()
    print(f'monitor_all: {monitor_all["summary"]}')
    print("\n".join(str(m) for m in monitor_all["monitors"]))



    # print("\n".join(
    #     f'{m["device_name"]} {m["width"]}x{m["height"]} '
    #     f'pos=({m["x"]},{m["y"]}) primary={m["is_primary"]}'
    #     for m in monitor_all["monitors"]
    # ))

    # save_display_configuration()
    restore_display_configuration()
