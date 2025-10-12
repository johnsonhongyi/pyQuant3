from __future__ import print_function

import ctypes
from ctypes.wintypes import HWND, DWORD, RECT
import time
# dwmapi = ctypes.WinDLL("dwmapi")

from mouseMonitor.displayDetction import  Display_Detection
import os
import re
import win32gui

from screeninfo import get_monitors
def get_screen_resolution():
    monitors = get_monitors()
    width = 0
    if not monitors:
        print("No monitors detected.")
    else:
        print("Connected monitors:")
        for i, m in enumerate(monitors):
            print(f"Monitor {i + 1}:")
            print(f"  Name: {m.name}")
            print(f"  Resolution: {m.width}x{m.height}")
            print(f"  Position: x={m.x}, y={m.y}")
            print(f"  Is primary: {m.is_primary}")
            width +=m.width
    return width

def find_window_by_title(target_title: str):
    """
    Finds a window by a partial match of its title.
    Returns a list of (handle, title) tuples for all matching windows.
    """
    found_windows = []
    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            # Use a case-insensitive regex search for the target title
            if re.search(target_title, title, re.IGNORECASE):
                found_windows.append((hwnd, title))
    
    win32gui.EnumWindows(enum_handler, None)
    return found_windows

# # Example usage: Find all windows with "Chrome" in their title
# target = "AutoHotKey"
# target = "通达信金融终端"
# matching_windows = find_window_by_title(target)
# print(matching_windows)

def find_window_by_title_safe(target_title: str):
    """
    通过对目标标题使用 re.escape()，安全地查找包含空格和括号的窗口。
    """
    found_windows = []
    # 使用 re.escape() 自动转义所有特殊字符
    escaped_title = re.escape(target_title)
    # 使用正则表达式匹配，并忽略大小写
    title_pattern = re.compile(escaped_title, re.IGNORECASE)

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            # 使用编译后的模式进行搜索
            if title_pattern.search(window_title):
                found_windows.append((hwnd, window_title))
    
    win32gui.EnumWindows(enum_handler, None)
    return found_windows

# # 示例：查找标题为 "Visual Studio Code (Admin)" 的窗口
# target = "通达信金融终端(开心果交易版) 副屏二"
# target = "通达信金融终端"
# matching_windows = find_window_by_title_safe(target)

# if matching_windows:
#     print(f"找到 {len(matching_windows)} 个包含 '{target}' 的窗口:")
#     for hwnd, title in matching_windows:
#         print(f"  句柄: {hex(hwnd)}, 标题: \"{title}\"")
# else:
#     print(f"未找到包含 '{target}' 的窗口。")

import psutil
def find_window_by_title_background(process_name: str):
    """
    根據程序名稱查找所有正在運行的程序。
    返回一個匹配的 psutil.Process 對象列表。
    """
    matching_processes = []
    # 使用 re.escape() 自动转义所有特殊字符
    escaped_title = re.escape(process_name)
    # 使用正则表达式匹配，并忽略大小写
    title_pattern = re.compile(escaped_title, re.IGNORECASE)

    for proc in psutil.process_iter(['name', 'pid']):
        try:

            # if proc.info['name'].lower() == process_name.lower():
            if title_pattern.search(proc.info['name']):
                # found_windows.append((hwnd, proc))
                matching_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return matching_processes

# # 示例：查找所有名為 "notepad.exe" 的程序
# target_name = "AutoHotKey"
# found_procs = find_window_by_title_background(target_name)

# if found_procs:
#     print(f"找到 {len(found_procs)} 個名為 '{target_name}' 的程序:")
#     for proc in found_procs:
#         print(f"  PID: {proc.pid}, Name: {proc.name()}, 狀態: {proc.status()}")
# else:
#     print(f"未找到名為 '{target_name}' 的程序。")

# import os,sys
# sys.path.append("..")
# from JohnsonUtil import commonTips as cct

#hide 'ths-tdx-web.py': '-32000,-32000,199,34','pywin32_mouse.py': '-32000,-32000,199,34'
#triton 1.25 dpi
# tdx_ths_position1536={'通达信': '659,72,878,793','东方财富': '268,0,1067,833','同花顺': '0,20,1075,864','Firefox': '100,67,629,779'}
tdx_ths_position4K1536={'Edge': '64,123,910,886','Firefox': '343,79,1436,931','交易信号监控': '1335,180,566,389',\
        '东兴证券': '51,205,1083,717','行业跟随1': '29,220,677,404','人气综合排行榜2.2':'168,0,477,753',\
        '通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '233,0,1213,866','东方财富': '202,0,1187,833','同花顺': '79,74,1145,772',\
        'sina_Market-DurationDn.py': '-6,432,1326,423','sina_Market-DurationCXDN.py': '10,313,1329,438',\
        'sina_Market-DurationUp.py': '243,432,1323,438','sina_Monitor-Market-LH.py': '264,306,1307,407',\
        'sina_Monitor.py': '137,28,1319,560','singleAnalyseUtil.py': '647,0,895,358','LinePower.py': '26,150,761,407',\
        'instock_Monitor.py': '74,54,1319,439','chantdxpower.py': '33,115,649,407','ths-tdx-web.py': '70,200,59,51',\
        'pywin32_mouse.py': '-25600,-25600,59,51'}

tdx_ths_position1536={'Edge': '25,143,814,718','交易信号监控': '1335,180,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '29,220,677,404','人气综合排行榜2.2': '168,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '191,41,1258,815',\
        '东方财富': '407,72,1113,790','同花顺': '62,92,1189,772','sina_Market-DurationDn.exe': '-6,432,1326,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1359,438','sina_Market-DurationUP': '-6,432,1353,438','sina_Market-DurationDnUP': '278,406,1352,464',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '109,20,1356,520','singleAnalyseUtil.exe': '683,16,897,359',\
        'LinePower.exe': '9,216,761,407','instock_Monitor.exe': '32,86,1400,359','filter_resample_Monitor.exe': '241,233,1338,550',\
        'chantdxpower.exe': '86,128,649,407','ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25600,59,51',\
        }
# tdx_ths_position1536={'Edge': '25,143,814,718','交易信号监控': '1335,180,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '29,220,677,404','人气综合排行榜2.2': '168,0,477,753','通达信金融终端': '191,41,1258,815',\
#         '东方财富': '407,72,1113,790','同花顺': '62,92,1145,772','sina_Market-DurationDn.exe': '-6,432,1326,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationUp.exe': '-6,432,1323,438','sina_Market-DurationDnUp': '274,350,1322,560',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '109,20,1319,580','singleAnalyseUtil.exe': '683,16,897,359',\
#         'LinePower.exe': '9,216,761,407','instock_Monitor.exe': '32,86,1400,359','filter_resample_Monitor.py': '290,236,1348,550','chantdxpower.exe': '86,128,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25600,59,51',}

# tdx_ths_position1920={'通达信': '787,214,1104,835','东方财富': '418,138,1142,885','同花顺': '22,184,1075,864','Firefox': '45,156,706,797','sina_Market-DurationDn.py': '-7,664,1305,423','sina_Market-DurationCXDN.py': '-7,326,1329,423','sina_Market-DurationUp.py': '606,664,1321,423','sina_Monitor-Market-LH.py': '662,318,1307,409','sina_Monitor.py': '109,20,1313,519','singleAnalyseUtil.py': '1001,0,897,359','LinePower.py': '29,103,761,407','instock_Monitor.py': '70,79,1313,391','chantdxpower.py': '-7,129,649,407','ths-tdx-web.py': '70,200,153,39','pywin32_mouse.py': '70,200,153,39'}

# tdx_ths_position1920={'行业跟随1': '29,220,677,404','人气综合排行榜2.2':'168,0,477,753','通达信': '787,214,1104,835','东方财富': '418,138,1142,885','同花顺': '22,184,1075,864','Firefox': '45,156,706,797','sina_Market-DurationDn.py': '-7,664,1332,423','sina_Market-DurationCXDN.py': '-7,326,1329,423','sina_Market-DurationUp.py': '606,664,1321,423','sina_Monitor-Market-LH.py': '662,318,1307,409','sina_Monitor.py': '109,20,1313,519','singleAnalyseUtil.py': '1001,0,897,359','LinePower.py': '29,103,761,407','instock_Monitor.py': '70,79,1313,391','chantdxpower.py': '-7,129,649,407','ths-tdx-web.py': '70,200,59,51','pywin32_mouse.py': '-32000,-32000,59,51'}
# 4K LG
# tdx_ths_position1920={'Edge': '64,123,910,886','Firefox': '343,79,1436,931','交易信号监控': '1335,180,566,389',\
# tdx_ths_position1920={'Edge': '64,123,910,886','交易信号监控': '1335,180,566,389',\
#         '行业跟随1': '29,220,677,404','人气综合排行榜2.2':'168,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '30,246,1385,828',\
#         '东方财富': '655,261,1266,804','同花顺': '198,119,1659,785','东兴证券': '52,52,1283,704',\
#         'sina_Market-DurationDn.py': '-7,664,1332,423','sina_Market-DurationCXDN.py': '-7,326,1329,423',\
#         'sina_Market-DurationUp.py': '606,664,1321,423','sina_Monitor-Market-LH.py': '662,318,1307,409',\
#         'sina_Monitor.py': '109,20,1356,519','singleAnalyseUtil.py': '1001,0,897,359','LinePower.py': '29,103,761,407',\
#         'instock_Monitor.py': '70,79,1313,391','chantdxpower.py': '-7,129,649,407','ths-tdx-web.py': '70,200,59,51',\
#         'pywin32_mouse.py': '-32000,-32000,59,51'}

#LG
# tdx_ths_position1920={'Edge': '64,123,910,886','交易信号监控': '1335,180,566,389','行业跟随1': '29,220,677,404',\
#         '人气综合排行榜2.2': '168,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '30,246,1385,828',\
#         '东方财富': '655,261,1266,804','同花顺': '198,119,1659,785','东兴证券': '52,52,1283,704',\
#         'sina_Market-DurationDn.py': '-7,664,1332,423','sina_Market-DurationCXDN.py': '-7,326,1329,423','sina_Market-DurationUp.py': '606,664,1321,423',\
#         'sina_Monitor-Market-LH.py': '662,318,1307,409','sina_Monitor.py': '109,20,1356,519','singleAnalyseUtil.py': '1001,0,897,359',\
#         'LinePower.py': '29,103,761,407','instock_Monitor.py': '70,79,1356,502','chantdxpower.py': '-7,129,649,407',\
#         'ths-tdx-web.py': '70,200,159,27','pywin32_mouse.py': '-32000,-32000,59,51','开盘啦竞价板块观察1.0': '33,33,898,307',\
#         '股票异动数据监控': '1320,66,516,972',}

# tdx_ths_position1920={'Edge': '1253,97,680,891','交易信号监控': '1335,180,566,389','行业跟随1': '29,220,677,404',\
#         '人气综合排行榜2.2': '168,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '30,246,1385,828',\
#         '东方财富': '648,67,1267,804','同花顺': '70,33,1557,805','东兴证券': '52,52,1283,704',\
#         'sina_Market-DurationDn.exe': '-7,664,1332,423','sina_Market-DurationCXDN.exe': '-7,326,1329,423','sina_Market-DurationUp.exe': '606,664,1321,423',\
#         'sina_Monitor-Market-LH.exe': '662,318,1307,409','sina_Monitor.exe': '109,20,1356,519','singleAnalyseUtil.exe': '1001,0,897,359',\
#         'LinePower.exe': '29,103,761,407','instock_Monitor.exe': '70,79,1356,502','chantdxpower.exe': '-7,129,649,407',\
#         'ths-tdx-web.exe': '70,200,159,27','pywin32_mouse.py': '-32000,-32000,59,51','开盘啦竞价板块观察1.0': '33,33,898,307',\
#         '股票异动数据监控': '1320,66,516,972',}

tdx_ths_position1920={'Edge': '1253,97,680,891','交易信号监控': '1335,180,566,389','行业跟随1': '29,220,677,404',\
        '人气综合排行榜2.2': '168,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '30,246,1385,828',\
        '东方财富': '648,67,1267,804','同花顺': '70,33,1557,805','东兴证券': '52,52,1283,704',\
        'sina_Market-DurationDn.exe': '-7,664,1332,423','sina_Market-DurationCXDN.exe': '-7,326,1329,423','sina_Market-DurationUp.exe': '606,664,1321,423',\
        'sina_Monitor-Market-LH.exe': '662,318,1307,409','sina_Monitor.exe': '109,20,1356,519','singleAnalyseUtil.exe': '1001,0,897,359',\
        'LinePower.exe': '29,103,761,407','instock_Monitor.exe': '70,79,1356,502','chantdxpower.exe': '-7,129,649,407',\
        'ths-tdx-web.exe': '70,200,159,27','pywin32_mouse.py': '-32000,-32000,59,51','开盘啦竞价板块观察1.0': '33,33,898,307',\
        '股票异动数据监控': '1320,66,516,972','instock_MonitorTK.py': '8,638,761,407',}

# tdx_ths_positionDouble={'通达信': '-1334,37,878,828','东方财富': '21,249,1067,833','同花顺': '825,216,1075,864','Firefox': '-1925,37,602,831','sina_Market-DurationDn.py': '-1902,226,1306,438','sina_Market-DurationCXDN.py': '-1871,90,1329,438','sina_Market-DurationUP.py': '-1818,411,1323,438','sina_Monitor-Market-LH.py': '576,680,1307,407','sina_Monitor.py': '136,25,1321,519','singleAnalyseUtil.py': '949,0,897,359','LinePower.py': '55,233,761,407','instock_Monitor.py': '78,108,1319,439','chantdxpower.py': '108,232,649,407','ths-tdx-web.py': '88,250,313,199','pywin32_mouse.py': '88,250,217,151'}
#双屏
# tdx_ths_positionDouble={'行业跟随1.0':'-676,924,677,404','东兴证券': '-1536,877,1100,842','人气综合排行榜2.22': '-477,967,478,753',\
#             '通达信金融终端': '30,246,1216,828','东方财富': '-1250,878,1115,832','同花顺': '825,216,1075,864','Firefox': '-1870,67,602,801',\
# tdx_ths_positionDouble={'Edge': '64,123,910,886','Firefox': '343,79,1436,931','交易信号监控': '1335,180,566,389','行业跟随1.0':'-676,1257,677,404',\
tdx_ths_positionDouble={'Edge': '64,123,910,886','交易信号监控': '1335,180,566,389','行业跟随1.0':'-676,1257,677,404',\
            '东兴证券': '-1536,1257,1100,842','人气综合排行榜2.22': '-477,1357,478,753',\
            '通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '30,246,1216,828','东方财富': '-1250,1257,1115,832','同花顺': '825,216,1075,864',\
            'sina_Market-DurationDn.py': '-1926,222,1326,438','sina_Market-DurationCXDN.py': '-1897,122,1329,438',\
            'sina_Market-DurationUp.py': '-1701,432,1323,438','sina_Monitor-Market-LH.py': '576,680,1307,407',\
            'sina_Monitor.py': '150,27,1350,519','singleAnalyseUtil': '-6,727,897,359','LinePower.py': '16,176,761,402',\
            'instock_Monitor.py': '657,31,1400,359','chantdxpower.py': '43,138,649,407','ths-tdx-web.py': '70,200,59,51',\
            'sina_Market-DurationDnUP': '600,523,1326,560','pywin32_mouse.py': '-32000,-32000,59,51'}


# tdx_ths_position3072={'Edge': '27,72,910,798','Firefox': '343,79,1436,931','交易信号监控': '1335,180,566,389',\
#startTEST
tdx_ths_position3072_old={'Edge': '27,72,910,798','交易信号监控': '1335,180,566,389',\
        '东兴证券': '51,205,1083,717','行业跟随1': '29,220,677,404','人气综合排行榜2.2':'168,0,477,753',\
        '通达信金融终端(开心果交易版)V2025': '191,41,1258,815','东方财富': '122,50,1187,806','同花顺': '79,74,1145,772',\
        'sina_Market-DurationDn.py': '-6,432,1326,423','sina_Market-DurationCXDN.py': '10,313,1329,438',\
        'sina_Market-DurationUp.py': '243,432,1323,438','sina_Monitor-Market-LH.py': '264,306,1307,407',\
        'sina_Monitor.py': '137,28,1350,560','singleAnalyseUtil.py': '647,0,895,358','LinePower.py': '26,150,761,407',\
        'instock_Monitor.py': '74,54,1319,439','chantdxpower.py': '33,115,649,407','ths-tdx-web.py': '70,200,59,51',\
        'pywin32_mouse.py': '-25600,-25600,59,51'}

# tdx_ths_position3072={'Edge': '25,72,913,798','交易信号监控': '977,193,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '29,220,677,404','人气综合排行榜2.2': '152,53,477,753','通达信金融终端': '191,41,1258,815',\
#         '东方财富': '-1261,-367,1187,806','同花顺': '-1514,-334,1145,772','sina_Market-DurationDn.exe': '-6,432,1326,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUp.exe': '-6,432,1323,438','sina_Market-DurationUp.exe': '243,432,1323,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '137,28,1319,520','singleAnalyseUtil.exe': '647,0,895,358',\
#         'LinePower.exe': '-6,170,761,407','instock_Monitor.exe': '74,54,1319,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25602,59,51',}

#双屏显示全部
tdx_ths_position3072={'Edge': '25,72,913,798','交易信号监控': '-541,-107,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-677,68,677,404','人气综合排行榜2.2': '1059,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '191,41,1258,815',\
        '东方财富': '-1154,-247,1098,634','同花顺': '-1514,-160,995,598','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1359,438','sina_Market-DurationDnUP.exe': '-6,432,1353,438','sina_Market-DurationUP.exe': '230,432,1336,438',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '137,28,1350,520','singleAnalyseUtil.exe': '-889,-426,895,358',\
        'LinePower.exe': '-6,186,761,407','instock_Monitor.exe': '74,54,1340,439','chantdxpower.exe': '-1507,-426,649,273',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25602,59,51',}

tdx_ths_position3840={'Edge': '25,72,913,798','交易信号监控': '-541,-107,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-677,68,677,404','人气综合排行榜2.2': '1059,0,477,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '191,41,1258,815',\
        '东方财富': '-1154,-247,1098,634','同花顺': '-1514,-160,995,598','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1359,438','sina_Market-DurationDnUP.exe': '-6,432,1353,438','sina_Market-DurationUP.exe': '230,432,1336,438',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '137,28,1350,520','singleAnalyseUtil.exe': '-889,-426,895,358',\
        'LinePower.exe': '-6,186,761,407','instock_Monitor.exe': '74,54,1340,439','chantdxpower.exe': '-1507,-426,649,273',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25602,59,51',}

#双屏显示1920仅ths,dfcf
# tdx_ths_position3456ths={'Edge': '25,72,913,798','交易信号监控': '975,193,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '29,220,677,404','人气综合排行榜2.2': '152,53,477,753','通达信金融终端': '191,41,1258,815',\
#         '东方财富': '-1878,-172,1174,699','同花顺': '-1189,-67,1145,614','sina_Market-DurationDn.exe': '-6,432,1326,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,432,1323,438','sina_Market-DurationUP.exe': '219,432,1323,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '137,28,1319,520','singleAnalyseUtil.exe': '-869,-524,897,359',\
#         'LinePower.exe': '-6,170,761,407','instock_Monitor.exe': '74,54,1319,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-25600,-25602,59,51',}

#Lg + triton500
# tdx_ths_position3456={'Edge': '25,72,913,798','交易信号监控': '-526,-296,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '-1439,-533,677,404','人气综合排行榜2.2': '-1890,-533,477,753','通达信金融终端': '191,41,1258,815',\
#         '东方财富': '-1878,-172,1174,699','同花顺': '-1145,-140,1145,667','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '219,417,1323,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '110,22,1350,520','singleAnalyseUtil.exe': '-869,-524,897,359',\
#         'LinePower.exe': '-5,136,761,407','instock_Monitor.exe': '69,54,1319,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}


tdx_ths_position3456={'Edge': '25,66,913,798','交易信号监控': '1335,180,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-1439,-533,677,404','人气综合排行榜2.2': '47,41,478,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '225,24,1258,815',\
        '东方财富': '482,-788,1440,790','同花顺': '0,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '-7,-1080,1345,519','singleAnalyseUtil.exe': '1057,-1080,897,359',\
        'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1319,439','chantdxpower.exe': '25,98,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}

#samsung and triton500



# tdx_ths_position4644={'Edge': '891,-905,704,912','交易信号监控': '2549,-738,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '2535,-1012,677,404','人气综合排行榜2.2': '18,84,478,753','通达信金融终端(开心果交易版) 副屏一': '1260,-829,1174,655',\
#         '通达信金融终端(开心果交易版) 副屏二': '1303,-649,1150,620','通达信金融终端(开心果交易版) 副屏三': '1004,-734,1199,704','通达信金融终端(开心果交易版)V2025': '176,21,1316,815',\
#         '东方财富': '1449,-858,1354,790','同花顺': '1188,-770,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '1210,-1080,1345,519','singleAnalyseUtil.exe': '2196,-1080,897,359',\
#         'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1338,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}

tdx_ths_position4644nodfcf={'Edge': '891,-905,704,912','交易信号监控': '2549,-738,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '2535,-1012,677,404','人气综合排行榜2.2': '18,84,478,753','通达信金融终端(开心果交易版) 副屏一': '1260,-829,1174,655',\
        '通达信金融终端(开心果交易版) 副屏二': '1303,-649,1150,620','通达信金融终端(开心果交易版) 副屏三': '1004,-734,1199,704','通达信金融终端(开心果交易版)V2025': '176,21,1316,815',\
        '东方财富': '1449,-858,1354,790','同花顺': '1188,-770,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '1210,-1080,1345,519','singleAnalyseUtil.exe': '2196,-1080,897,359',\
        'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1338,439','chantdxpower.exe': '25,98,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '914,-1052,898,265',\
        '股票异动数据监控': '98,21,750,550',}

# tdx_ths_position4644={'Edge': '891,-905,704,912','交易信号监控': '1232,84,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '2231,-998,677,404','人气综合排行榜2.2': '18,84,478,753','通达信金融终端(开心果交易版) 副屏一': '1260,-829,1174,655',\
#         '通达信金融终端(开心果交易版) 副屏二': '1303,-649,1150,620','通达信金融终端(开心果交易版) 副屏三': '1004,-734,1199,704','通达信金融终端(开心果交易版)V2025': '176,21,1316,815',\
#         '东方财富': '1449,-858,1354,790','同花顺': '1188,-770,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '1210,-1080,1345,519','singleAnalyseUtil.exe': '2049,-1080,897,359',\
#         'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1338,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '914,-1052,898,265',\
#         '股票异动数据监控': '2058,-967,750,550','开盘啦竞价板块观察1.0': '914,-1052,898,265','股票异动数据监控': '2058,-967,750,550',\
# }

tdx_ths_position4644_exe={'Edge': '2154,-858,654,852','交易信号监控': '1232,84,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '861,0,677,404','人气综合排行榜2.2': '-2,0,478,753','通达信金融终端(开心果交易版) 副屏一': '1260,-829,1174,655',\
        '通达信金融终端(开心果交易版) 副屏二': '1303,-649,1150,620','通达信金融终端(开心果交易版) 副屏三': '856,-743,1199,704','通达信金融终端(开心果交易版)V2025': '209,60,1216,794',\
        '东方财富': '1449,-858,1354,790','同花顺': '927,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '119,329,1394,439',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '946,-1080,1353,521','singleAnalyseUtil.exe': '1890,-1080,897,359',\
        'LinePower.exe': '750,33,761,407','instock_Monitor.exe': '16,82,1346,439','chantdxpower.exe': '-6,463,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '891,-1043,898,265',\
        '股票异动数据监控': '2270,-1022,516,979','开盘啦竞价板块观察1.0': '891,-1043,898,265',\
}

tdx_ths_position4644={'Edge': '2153,-859,655,853','交易信号监控': '1232,84,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '861,0,677,404','人气综合排行榜2.2': '-2,0,478,753','通达信金融终端(开心果交易版) 副屏一': '1260,-829,1174,655',\
        '通达信金融终端(开心果交易版) 副屏二': '1303,-649,1150,620','通达信金融终端(开心果交易版) 副屏三': '856,-743,1199,704','通达信金融终端(开心果交易版)V2025': '209,60,1216,794',\
        '东方财富': '1449,-858,1354,790','同花顺': '927,-785,1440,785','sina_Market-DurationDn.py': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.py': '10,313,1329,438','sina_Market-DurationDnUP.py': '-6,411,1353,438','sina_Market-DurationUP.py': '119,329,1394,439',\
        'sina_Monitor-Market-LH.py': '264,306,1307,407','sina_Monitor.py': '946,-1080,1353,521','singleAnalyseUtil.py': '1890,-1080,897,359',\
        'LinePower.py': '750,33,761,407','instock_Monitor.py': '16,82,1346,439','chantdxpower.exe': '86,128,649,407',\
        'ths-tdx-web.py': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '891,-1043,898,265',\
        '股票异动数据监控': '2270,-1022,516,979','开盘啦竞价板块观察1.0': '891,-1043,898,265',\
}

#LG + samsung  + triton
tdx_ths_position5376_Triton={'Edge': '1013,-793,914,800','交易信号监控': '1361,-896,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1922,-622,478,753','通达信金融终端(开心果交易版) 副屏一': '984,-815,1258,815','通达信金融终端(开心果交易版)V2025': '234,21,1258,815',\
        '东方财富': '-1486,-408,1103,652','同花顺': '0,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        '通达信金融终端(开心果交易版) 副屏二': '984,-815,1258,815','通达信金融终端(开心果交易版) 副屏三': '984,-815,1199,704','sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '-7,-1080,1353,521','singleAnalyseUtil.exe': '1007,-1080,897,359',\
        'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1333,439','chantdxpower.exe': '25,98,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}


# tdx_ths_position5376={'Edge': '1013,-793,914,800','交易信号监控': '1361,-896,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1923,-622,478,753','通达信金融终端(开心果交易版)V2025': '-1606,-553,1216,794',\
#         '东方财富': '185,98,1238,768','同花顺': '0,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '-7,-1080,1353,521','singleAnalyseUtil.exe': '1007,-1080,897,359',\
#         'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1333,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}


tdx_ths_position5376nodfcf={'Edge': '1013,-793,914,800','交易信号监控': '1361,-935,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1922,-622,478,753','通达信金融终端(开心果交易版) 副屏一': '-37,-891,1153,652',\
        '通达信金融终端(开心果交易版) 副屏二': '-43,-27,1170,760','通达信金融终端(开心果交易版) 副屏三': '-1894,-407,1130,639','通达信金融终端(开心果交易版)V2025': '-1711,-560,1216,794',\
        '东方财富': '64,98,1353,768','同花顺': '29,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,374,1353,438','sina_Market-DurationUP.exe': '119,329,1394,439',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '32,-1080,1353,521','singleAnalyseUtil.exe': '992,-1080,897,359',\
        'LinePower.exe': '-1588,-622,761,407','instock_Monitor.exe': '16,82,1346,439','chantdxpower.exe': '-1926,-159,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '914,-1052,898,265',\
        '股票异动数据监控': '98,21,750,550',}

tdx_ths_position5376={'Edge': '1013,-793,914,800','交易信号监控': '971,87,566,389','东兴证券': '51,205,1083,717',\
        '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1922,-622,478,753','通达信金融终端(开心果交易版) 副屏一': '-37,-891,1153,652',\
        '通达信金融终端(开心果交易版) 副屏二': '-43,-27,1170,760','通达信金融终端(开心果交易版) 副屏三': '-1894,-407,1130,639','通达信金融终端(开心果交易版)V2025': '-1711,-560,1216,794',\
        '东方财富': '64,98,1353,768','同花顺': '29,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
        'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,374,1353,438','sina_Market-DurationUP.exe': '119,329,1394,439',\
        'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '48,-1080,1353,521','singleAnalyseUtil.exe': '992,-1080,897,359',\
        'LinePower.exe': '750,33,761,407','instock_Monitor.exe': '16,82,1346,439','chantdxpower.exe': '-1926,-159,649,407',\
        'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51','开盘啦竞价板块观察1.0': '-7,-1043,898,265',\
        '股票异动数据监控': '1161,-1005,766,589','开盘啦竞价板块观察1.0': '-7,-1043,898,265','股票异动数据监控': '1161,-1005,766,589',\
}

# tdx_ths_position5760={'Edge': '1013,-793,914,800','交易信号监控': '1361,-935,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1922,-622,478,753','通达信金融终端(开心果交易版) 副屏一': '-37,-891,1153,652',\
#         '通达信金融终端(开心果交易版) 副屏二': '-43,-27,1170,760','通达信金融终端(开心果交易版) 副屏三': '-1894,-407,1130,639','通达信金融终端(开心果交易版)V2025': '-1711,-560,1216,794',\
#         '东方财富': '64,98,1353,768','同花顺': '29,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,374,1353,438','sina_Market-DurationUP.exe': '119,329,1394,439',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '32,-1080,1353,521','singleAnalyseUtil.exe': '992,-1080,897,359',\
#         'LinePower.exe': '-1588,-622,761,407','instock_Monitor.exe': '16,82,1346,439','chantdxpower.exe': '-1926,-159,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}   

# tdx_ths_position5376={'Edge': '1013,-793,914,800','交易信号监控': '1361,-896,566,389','东兴证券': '51,205,1083,717',\
#         '行业跟随1': '-1059,-622,677,404','人气综合排行榜2.2': '-1922,-622,478,753','通达信金融终端(开心果交易版)V2025': '234,21,1258,815',\
#         '东方财富': '-1457,-408,1074,652','同花顺': '0,-785,1440,785','sina_Market-DurationDn.exe': '-6,432,1356,423',\
#         'sina_Market-DurationCXDN.exe': '10,313,1329,438','sina_Market-DurationDnUP.exe': '-6,411,1353,438','sina_Market-DurationUP.exe': '198,417,1344,438',\
#         'sina_Monitor-Market-LH.exe': '264,306,1307,407','sina_Monitor.exe': '-7,-1080,1345,519','singleAnalyseUtil.exe': '1007,-1080,897,359',\
#         'LinePower.exe': '-6,136,761,407','instock_Monitor.exe': '69,54,1333,439','chantdxpower.exe': '25,98,649,407',\
#         'ths-tdx-web.exe': '70,200,59,51','pywin32_mouse.py': '-20480,-20482,59,51',}
        
# tdx_ths_position={'通达信金融终端(开心果交易版)V2025': '-1334,72,878,793','东方财富': '21,249,1067,833','同花顺': '-1553,19,1075,864','Firefox': '-1910,5,602,864','sina_Market-DurationDn.py': '-1902,226,1306,438','sina_Market-DurationCXDN.py': '-1871,90,1329,438','sina_Market-DurationUP.py': '-1818,411,1323,438','sina_Monitor-Market-LH.py': '576,680,1307,407','sina_Monitor.py': '136,25,1321,519','singleAnalyseUtil.py': '949,0,897,359','LinePower.py': '55,233,761,407','instock_Monitor.py': '78,108,1319,439','chantdxpower.py': '108,232,649,407','ths-tdx-web.py': '88,250,313,199','pywin32_mouse.py': '88,250,217,151'}

# title:通达信金融终端V7.642 - [行情报价-Now090] pos: '1074,260,878,793'
# title:东方财富终端 pos: '21,249,1067,833'
# title:同花顺(v9.20.71) - 板块同列 pos: '-1553,19,1075,864'
# title:TDX_THS_联动 Previewer — Mozilla Firefox pos: '-25984,-25600,159,27'
# title:sina_Market-DurationDn.py 2023-11-30 dT:13:01 G:1975 zxg: 063.blk-all pos: '-1902,226,1306,438'
# title:sina_Market-DurationCXDN.py 2023-11-30 dT:13:00 G:1975 zxg: 065.blk-all pos: '-1871,90,1329,438'
# title:sina_Market-DurationUP.py 2023-05-08 dT:10:43 G:1934 zxg: 062.blk-all pos: '-1818,411,1323,438'
# title:sina_Monitor-Market-LH.py 2023-11-30 dT:13:02 G:28 zxg: 066.blk-066 pos: '576,680,1307,407'
# title:sina_Monitor.py 2023-11-30 G:4891 zxg: 064.blk-all pos: '136,25,1321,519'
# title:singleAnalyseUtil.py B:93755-94172 V:0.8 ZL: -315.1 To:13 D:1371 Sh: -0.03%  Vr:3551.4-3543.9-0.8%  MR: -2.9 ZL: -315.1 pos: '949,0,897,359'
# title:LinePower.py pos: '55,233,761,407'
# title:instock_Monitor.py 60 G:54 zxg: 063.blk-063 pos: '78,108,1319,439'
# title:chantdxpower.py pos: '108,232,649,407'
# title:ths-tdx-web.py pos: '-25984,-25600,159,27'
# title:pywin32_mouse.py pos: '88,250,217,151'

def set_windows_hwnd_pos(hwnd,pos):
    # # 设置窗口标题
    # window_title = "通达信金融终端V7.642 - [分析图表-平安银行]"
    # window_title = title
    # # # window_title = "tdxw.exe"
    # # # 查找窗口句柄
    # hwnd = ctypes.windll.user32.FindWindowW(None, window_title)

    # rect = RECT()
    # DMWA_EXTENDED_FRAME_BOUNDS = 9
    # dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
    #                              ctypes.byref(rect), ctypes.sizeof(rect))
    # print(rect.left, rect.top, rect.right, rect.bottom)

    # left=644, top=1471, right=44, bottom=874
    # left=805, top=44, right=1835, bottom=1080
    # 设置新的窗口位置
    # x = int(805/1.25) # 新的窗口左上角的x坐标

    # x = 644 # 新的窗口左上角的x坐标
    # y = 44 # 新的窗口左上角的y坐标
    # top=1471
    # bottom=874

    # right=1872
    # bottom=1228
    # 移动窗口
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, top, bottom, 1)

    # ctypes.windll.user32.SetForegroundWindow(hwnd)
    pos = pos.split(',')
    x,y = int(pos[0]),int(pos[1])
    width,height = int(pos[2]),int(pos[3])
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)
    print(x,y,width,height)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)

    # 设置新的窗口大小
    # left=644, top=44, width=827, height=830
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # 设定窗口大小
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 2)



def set_windows_pos(title,pos):
    # # 设置窗口标题
    # window_title = "通达信金融终端V7.642 - [分析图表-平安银行]"
    window_title = title
    # # window_title = "tdxw.exe"
    # # 查找窗口句柄
    hwnd = ctypes.windll.user32.FindWindowW(None, window_title)

    # rect = RECT()
    # DMWA_EXTENDED_FRAME_BOUNDS = 9
    # dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
    #                              ctypes.byref(rect), ctypes.sizeof(rect))
    # print(rect.left, rect.top, rect.right, rect.bottom)

    # left=644, top=1471, right=44, bottom=874
    # left=805, top=44, right=1835, bottom=1080
    # 设置新的窗口位置
    # x = int(805/1.25) # 新的窗口左上角的x坐标

    # x = 644 # 新的窗口左上角的x坐标
    # y = 44 # 新的窗口左上角的y坐标
    # top=1471
    # bottom=874

    # right=1872
    # bottom=1228
    # 移动窗口
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, top, bottom, 1)

    # ctypes.windll.user32.SetForegroundWindow(hwnd)
    pos = pos.split(',')
    x,y = int(pos[0]),int(pos[1])
    width,height = int(pos[2]),int(pos[3])
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)
    print(x,y,width,height)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)

    # 设置新的窗口大小
    # left=644, top=44, width=827, height=830
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # 设定窗口大小
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 2)


global list_hwnd
list_hwnd = []
import ctypes
from ctypes import wintypes
from collections import namedtuple

user32 = ctypes.WinDLL('user32', use_last_error=True)

def check_zero(result, func, args):    
    if not result:
        err = ctypes.get_last_error()
        if err:
            # raise ctypes.WinError(err)
            print(ctypes.WinError(err))
    return args

if not hasattr(wintypes, 'LPDWORD'): # PY2
    wintypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)

WindowInfo = namedtuple('WindowInfo', 'pid title,left, top, width, height')

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,    # _In_ hWnd
    wintypes.LPARAM,) # _In_ lParam

user32.EnumWindows.errcheck = check_zero
user32.EnumWindows.argtypes = (
   WNDENUMPROC,      # _In_ lpEnumFunc
   wintypes.LPARAM,) # _In_ lParam

user32.IsWindowVisible.argtypes = (
    wintypes.HWND,) # _In_ hWnd

user32.IsIconic.argtypes = (
    wintypes.HWND,) # _In_ hWnd


user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = wintypes.HWND,wintypes.BOOL
user32.ShowWindow.restype = wintypes.BOOL # _In_ hWnd

user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = (
  wintypes.HWND,     # _In_      hWnd
  wintypes.LPDWORD,) # _Out_opt_ lpdwProcessId


user32.GetWindowTextLengthW.errcheck = check_zero
user32.GetWindowTextLengthW.argtypes = (
   wintypes.HWND,) # _In_ hWnd

user32.GetWindowTextW.errcheck = check_zero
user32.GetWindowTextW.argtypes = (
    wintypes.HWND,   # _In_  hWnd
    wintypes.LPWSTR, # _Out_ lpString
    ctypes.c_int,)   # _In_  nMaxCount

def GetWindowRectFromName(hwnd)-> tuple:
    # hwnd = ctypes.windll.user32.FindWindowW(0, name)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.pointer(rect))
    # print(hwnd)
    # print(rect)
    left = rect.left
    top = rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (left, top, width, height)
    # return (rect.left, rect.top, rect.right, rect.bottom)

def get_pos_dwmapi(hwnd):
    rect = RECT()
    DMWA_EXTENDED_FRAME_BOUNDS = 9
    dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
                                 ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.right, rect.top, rect.bottom

import subprocess
import platform

def find_proc_window_tasklist(procname,debug=False):
    # command = f'tasklist /FI "ImageName eq :{procname}" /FI "Status eq Running"'
    # command = f'lsof -i :{port}'
    system = platform.system()
    # print(f"尝试find proc:{procname}")
    check_dict ={}
    is_port_in_use = False
    

    # 对于Unix-like系统（包括macOS和Linux），尝试使用lsof命令
    if system in ["Linux", "Darwin"]:
        print("system in [Linux, Darwin]")
        command = f'lsof -i :{port}'
        output = subprocess.check_output(command, shell=True, text=True)
        # result = bool(output.strip())
        result = bool(output.strip())
        check_dict["Command_Line_lsof"] = result
        is_port_in_use |= result  # 如果lsof检查结果显示端口被占用，更新标志位

    # 对于Windows系统
    elif system == "Windows":
        # local_ip = get_host_ip()
        # print("system == Windows:%s"%(local_ip))
        # command = f'netstat -ano | findstr "{local_ip}:{port} 0.0.0.0:{port}"'
        # command = f'netstat -ano | findstr "0.0.0.0:{port}"'
        command = f'tasklist /FI "ImageName eq {procname}" /FI "Status eq Running"'
        output = subprocess.run(command, shell=True, capture_output=True, text=True)
        if not debug:
            outputdata= output.stdout.strip()
            result = bool(outputdata) if outputdata.find('没有运行的任务') < 0 else False
        else:
            result = (output.stdout.strip())
            print("command:%s"%(command))
        check_dict["Command_Line_netstat"] = result

        if not debug:
            is_port_in_use |= result  # 如果netstat检查结果显示端口被占用，更新标志位
    else:
        print("system == None")
        raise ValueError(f"Unsupported operating system: {system}")

    # 返回端口占用情况字典及是否被占用的布尔值
    # print(f"检查端口in_use:{is_port_in_use}")
    if debug:
        print(f"检查result:{check_dict['Command_Line_netstat']}")
    # return check_dict, is_port_in_use
    return result


def find_proc_windows(proc,visible=True,fuzzysearch=True):
    '''Return a sorted list of visible windows.'''
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if  visible:

            if user32.IsWindowVisible(hWnd):
                pid = wintypes.DWORD()
                tid = user32.GetWindowThreadProcessId(
                            hWnd, ctypes.byref(pid))
                length = user32.GetWindowTextLengthW(hWnd) + 1
                if (length == 1):return True
                # print(f'length:{length}')
                title = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hWnd, title, length)
                #debug
                # print(f'all:{title.value}')
                if len(title.value) > 0 and (fuzzysearch == True or len(title.value) == len(proc)):
                    #debug
                    # print(f'find:{title.value}')
                    # if 10 > title.value.find(proc) >= 0:
                    if title.value.find(proc) >= 0:
                        result.append(title.value)
        else:
            if user32.IsIconic(hWnd):return True;
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            if (length == 1):return True
            # print(f'length:{length}')
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            #show IsIconic app
            # if user32.IsIconic(hWnd):print("IsIconic:",title.value);
            if len(title.value) > 0:
                if title.value.find(proc) >= 0:
                    result.append(title.value)

        return True
    user32.EnumWindows(enum_proc, 0)
    return result


def list_find_windows(proc):
    '''Return a sorted list of visible windows.'''
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)

            if len(title.value) > 0:
                # print(title.value)
                # left, right, top, bottom = get_pos(hWnd)
                if title.value.find(proc) >= 0:
                    # print(title.value)
                    left, top, width, height = GetWindowRectFromName(hWnd)
                    if left < 0 and top < 0:

                        # user32.ShowWindow(hWnd, SW_Restore);
                        time.sleep(0.1)
                        user32.ShowWindow(hWnd, SW_Normal);
                        left, top, width, height = GetWindowRectFromName(hWnd)

                    # left, right, top, bottom = GetWindowRectFromName(hWnd)
                    # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                    result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return sorted(result)
    # return sorted(result)

SW_Normal = 1
SW_MAXIMIZE = 3
SW_SHOWMINIMIZED = 2
SW_MINIMIZE = 6
SW_Restore = 9
SW_Show = 5
SW_HIDE = 0
SW_SHOWMINNOACTIVE = 7
# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow
def set_proc_windows_position(proc,tdx_ths_position=tdx_ths_position1536,SW_Positon=SW_Normal):
    '''Return a sorted list of visible windows.'''
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)

            if len(title.value) > 0:
                # print(title.value)
                # left, right, top, bottom = get_pos(hWnd)
                if isinstance(proc, list):
                    for tdx in proc:
                        # if title.value.find(tdx) >= 0:
                        # print(f'proc:{tdx}')
                        # if 10 > title.value.find(tdx) >= 0:
                        if title.value.find(tdx) >= 0:

                            left, top, width, height = GetWindowRectFromName(hWnd)
                            if left < 0 and top < 0:
                                # user32.ShowWindow(hWnd, SW_MAXIMIZE);
                                time.sleep(0.1)
                                # user32.ShowWindow(hWnd, SW_Normal);
                                user32.ShowWindow(hWnd, SW_Positon);
                                left, top, width, height = GetWindowRectFromName(hWnd)
                                print(left, top, width, height)

                            if tdx in tdx_ths_position.keys():
                                print(f'set {tdx} :{tdx_ths_position[tdx]}')
                                set_windows_hwnd_pos(hWnd,tdx_ths_position[tdx])

                            # if SW_Positon != SW_Normal:
                            #     user32.ShowWindow(hWnd, SW_Positon);

                else:
                    if title.value.find(proc) >= 0:
                        # print(title.value)

                        left, top, width, height = GetWindowRectFromName(hWnd)

                        if left < 0 and top < 0:
                            # user32.ShowWindow(hWnd, SW_MAXIMIZE);
                            time.sleep(0.1)
                            user32.ShowWindow(hWnd, SW_Positon);
                            left, top, width, height = GetWindowRectFromName(hWnd)
                            print(left, top, width, height)

                        if proc in tdx_ths_position.keys():
                            set_windows_hwnd_pos(hWnd,tdx_ths_position[proc])

                        if SW_Positon != SW_Normal:
                            user32.ShowWindow(hWnd, SW_Positon);
                            # ctypes.windll.user32.ShowWindow(hWnd, SW_Positon);
                    # print(title.value)
                        # left, top, width, height = GetWindowRectFromName(hWnd)
                        # if left < 0 and top < 0:
                        #     time.sleep(0.1)
                        #     user32.ShowWindow(hwnd, SW_Normal);
                        #     left, top, width, height = GetWindowRectFromName(hWnd)

                        # # left, right, top, bottom = GetWindowRectFromName(hWnd)
                        # # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                        # result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return True


def list_user_windows():
    '''Return a sorted list of visible windows.'''
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            if len(title.value) > 0:
            # left, right, top, bottom = get_pos(hWnd)
                left, top, width, height = GetWindowRectFromName(hWnd)
                # left, right, top, bottom = GetWindowRectFromName(hWnd)
                # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return (result)



# private enum ShowWindowEnum{Hide = 0,
# ShowNormal = 1,ShowMinimized = 2,ShowMaximized = 3,
# Maximize = 3,ShowNormalNoActivate = 4,Show = 5,
# Minimize = 6,ShowMinNoActivate = 7,ShowNoActivate = 8,
# Restore = 9,ShowDefault = 10,ForceMinimized = 11};

def FindWindowRectFromName(title)-> tuple:
    # not ok 
    # hwnd = ctypes.windll.user32.FindWindowW(0, name)
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    global list_hwnd
    if len(list_hwnd) == 0:
        list_hwnd = list_user_windows()
    hwnd = 0
    for win in list_hwnd:
        if win.title.find(title) >= 0:
            if not (win.left < -10000 and win.top < -10000 ):
                print("'%s': '%s,%s,%s,%s',"%(title,win.left,win.top,win.width,win.height),end='')
                hwnd = win.pid
                # break
                #需要前置步骤showwindow
                # hwnd = user32.GetForegroundWindow()
                # user32.ShowWindow(hwnd, SW_MINIMIZE);
                # import time 
                # time.sleep(0.5)
                # user32.ShowWindow(hwnd, SW_Normal);
                left, top, width, height = GetWindowRectFromName(hwnd)
                # print(hwnd)
                # print(rect)
                # return (left, top, width, height)
                return (win.left,win.top,win.width,win.height)
            # else:
            #     print('title:%s'%(win.title))
    return (0,0,0,0)

def list_windows(all=False):
    '''Return a sorted list of visible windows.'''
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        # if user32.IsWindowVisible(hWnd):
        # if user32.IsIconic(hWnd):return True;
        if all:
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            if (length == 1):return True
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            # left, right, top, bottom = get_pos(hWnd)
            # left, right, top, bottom = GetWindowRectFromName(hWnd)
            left, top, width, height = GetWindowRectFromName(hWnd)
            # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
            result.append(WindowInfo(pid.value, title.value,left, top, width, height))
        else:
            if user32.IsWindowVisible(hWnd):
                pid = wintypes.DWORD()
                tid = user32.GetWindowThreadProcessId(
                            hWnd, ctypes.byref(pid))
                length = user32.GetWindowTextLengthW(hWnd) + 1
                if (length == 1):return True
                title = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hWnd, title, length)
                # left, right, top, bottom = get_pos(hWnd)
                # left, right, top, bottom = GetWindowRectFromName(hWnd)
                left, top, width, height = GetWindowRectFromName(hWnd)
                # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                result.append(WindowInfo(pid.value, title.value,left, top, width, height))

            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    # return sorted(result)
    return (result)

psapi = ctypes.WinDLL('psapi', use_last_error=True)

psapi.EnumProcesses.errcheck = check_zero
psapi.EnumProcesses.argtypes = (
   wintypes.LPDWORD,  # _Out_ pProcessIds
   wintypes.DWORD,    # _In_  cb
   wintypes.LPDWORD,) # _Out_ pBytesReturned

def list_pids():
    '''Return sorted list of process IDs.'''
    length = 4096
    PID_SIZE = ctypes.sizeof(wintypes.DWORD)
    while True:
        pids = (wintypes.DWORD * length)()
        cb = ctypes.sizeof(pids)
        cbret = wintypes.DWORD()
        psapi.EnumProcesses(pids, cb, ctypes.byref(cbret))
        if cbret.value < cb:
            length = cbret.value // PID_SIZE
            return sorted(pids[:length])
        length *= 2

def run_system_fpath(fpath):
    if cct.check_file_exist(fpath): 
        os.system('cmd /c start %s'%(fpath))
    else:
        print("fpath:%s isn't exist"%(fpath))

if __name__ == '__main__':
    print('Process IDs:')
    # print(*list_pids(), sep='\n')
    print('\nWindows:\n')
    # print(*list_windows(all=False), sep='\n')

    # result3=find_proc_windows('行业跟随1.0',visible=True)
    # print(result3)
    print(FindWindowRectFromName('股票异动数据监控'))
    print(f"ths-tdx-web.py: {find_window_by_title_safe('ths-tdx-web.py')}")


    print(FindWindowRectFromName('ths-tdx-web.py'))
    
    print(FindWindowRectFromName('开盘啦竞价板块观察1.0'))
    # print(find_proc_windows('股票异动数据监控',fuzzysearch=True))

    # print(find_proc_windows('交易信号监控',fuzzysearch=True))
    # print(find_proc_windows('通达信金融终端',fuzzysearch=True))
    # print(find_proc_windows('Firefox',fuzzysearch=True))
    # print(find_proc_windows('Microsoft\u200b Edge',fuzzysearch=True))
    # print(find_proc_windows('通达信金融终端(开心果交易版) 副屏一',fuzzysearch=True))
    # print(find_proc_windows('通达信金融终端(开心果交易版)V2025',fuzzysearch=True))
    # print(get_screen_resolution())
    print(find_window_by_title_background('开盘啦板块竞价'))
    print(find_window_by_title_background('异动联动'))
    print(find_window_by_title_background('通达信金融终端'))
    result = find_window_by_title_background('涨停采集工具共享版')
    if result:
        print(f'find 涨停采集工具共享版 :{result}')
    else:
        print(f'not find 涨停采集工具共享版 :{result}')
    
    # print(f'ths-tdx-web.py: {find_window_by_title_safe('ths-tdx-web.py')}')
    print(find_window_by_title_safe('Microsoft\u200b Edge'))
    print(find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏一'))
    print(find_window_by_title_safe('通达信金融终端(开心果交易版)V2025'))
    proc_title = ['股票异动数据监控','通达信金融终端(开心果交易版) 副屏一','通达信金融终端(开心果交易版) 副屏二','通达信金融终端(开心果交易版) 副屏三','通达信金融终端(开心果交易版)V2025','sina_Market-DurationUP','sina_Market-DurationDnUP','sina_Monitor','filter_resample_Monitor','同花顺','Microsoft\u200b Edge','Firefox','交易信号监控','instock_Monitor','sina_Market-DurationDnUp','sina_Market-DurationUp','singleAnalyseUtil','人气综合排行榜2.22','行业跟随1.0','东兴证券','通达信金融终端','东方财富']
    for title in proc_title:
        FindWindowRectFromName(title)
    print('\n')
    # title = '人气综合排行榜2.2'
    # title = '行业跟随1'
    # result=find_proc_windows(title,fuzzysearch=False)
    # FindWindowRectFromName(title)
    # import ipdb;ipdb.set_trace()
    # set_proc_windows_position(title,tdx_ths_position=positon)

    # if not find_proc_windows('同花顺'):
    #     # os.system('cmd /c start D:\\MacTools\\WinTools\\同花顺\\hexin.exe')
    #     run_system_fpath('D:\\MacTools\\WinTools\\同花顺\\hexin.exe')
    #     time.sleep(6)
    # if not find_proc_windows('东方财富'):
    #     # os.system('cmd /c start D:\\MacTools\\WinTools\\eastmoney\\swc8\\mainfree.exe')
    #     run_system_fpath('D:\\MacTools\\WinTools\\eastmoney\\swc8\\mainfree.exe')
    #     time.sleep(6)


    # if not find_proc_windows('通达信金融终端',fuzzysearch=True):
    #     run_system_fpath('%s\\tdxw.exe'%(cct.get_tdx_dir()))
    #     time.sleep(8)

    tasklist = ['通达信金融终端(开心果交易版) 副屏一','通达信金融终端(开心果交易版) 副屏二','通达信金融终端(开心果交易版) 副屏三','Edge','行业跟随1.0','link.exe']
    for task in tasklist:
        result1 = (find_window_by_title_safe(task))
        # result1 = find_proc_window_tasklist('通达信')
        print("find_proc_window_tasklist:%s"%(result1))
        # time.sleep(0.2)


    # import copy_tools as cptools #open_tdx_mscreen,set_tdx_screen_show
    # active_window = cptools.ahk.active_window

    # # if find_proc_windows('通达信金融终端',fuzzysearch=True):
    # if find_window_by_title_safe('通达信金融终端'):
    #     # if not (find_proc_windows('通达信金融终端(开心果交易版) 副屏一',fuzzysearch=True)):
    #     # if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏一')):
    #     #     print('start : 通达信金融终端(开心果交易版) 副屏')
    #     #     print(cptools.open_tdx_mscreen(1))
    #     # if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏二')):
    #     #     print(cptools.open_tdx_mscreen(2))
    #     if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏三')):
    #         print(cptools.open_tdx_mscreen(3))

    #     cptools.set_tdx_screen_show()
    #     time.sleep(5)
    
    # active_window.activate()


    
    # result=find_proc_windows('联动精灵',visible=False)
    result=find_window_by_title_safe('联动精灵')
    print(result)

    # result2=find_proc_windows('人气综合排行榜2.22',visible=False)
    result2=find_window_by_title_safe('人气综合排行榜2.22')
    print(result2)


    # import os
    # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')

    # set_proc_windows_position('联动精灵',SW_Positon=SW_Restore)
    
    # set_proc_windows_position('联动精灵',SW_Positon=SW_SHOWMINNOACTIVE)
    # set_proc_windows_position('联动精灵',SW_Positon=SW_Normal)
    # set_proc_windows_position('联动精灵',SW_Positon=SW_HIDE)    # Hide no restore

    import sys
    sys.path.append("..")
    # from JSONData import tdx_data_Day as tdd
    # from JohnsonUtil import LoggerFactory as LoggerFactory
    # from JohnsonUtil import johnson_cons as ct
    from JohnsonUtil import commonTips as cct
    
    displaySet =Display_Detection()
    displayNum = displaySet[0]
    displayMainRes = displaySet[1][0]
    if displaySet[0] > 1:
        print(f"displaySet:{displaySet}")
        proc_title =  [proc for proc in tdx_ths_positionDouble.keys()]
        # proc_title =  [proc for proc in sorted(tdx_ths_positionDouble.keys(),reverse=False)]
        # positon = tdx_ths_positionDouble
        displayRes = 0 
        # displayRes = displaySet[1][0] + displaySet[2][0]
        for i in range(1, displaySet[0]+1 ):
            displayRes = displayRes + displaySet[i][0]
            print(f'i:{i} displayRes;{displayRes} , displaySet[{i}][0]: {displaySet[i][0]}')
        # tdx_ths_position_eval = 'tdx_ths_position%s'%(displayMainRes)
        print(f"displayMainRes:{displayMainRes} displayRes:{displayRes} displaySet: {displaySet[0]}, 1: {displaySet[1][0]} 2: {displaySet[2][0]}")
        if 3800 < displayRes < 4700:
            displayRes = 4644
        elif 4700 < displayRes:
            displayRes = 5376
        tdx_ths_position_eval = 'tdx_ths_position%s'%(displayRes)
        positon = eval(tdx_ths_position_eval)
        proc_title =  [proc for proc in positon.keys()]
        print(f'proc_title:{proc_title}')
        print("positionDouble:%s  "%(tdx_ths_position_eval))

    else:
        print(f"displaySet:{displaySet}")
        print("displaySet:%s %s"%(displaySet[0],displaySet[1][0]))
        tdx_ths_position_eval = 'tdx_ths_position%s'%(displayMainRes)
        
        print("positon:%s  "%(tdx_ths_position_eval))
        positon = eval(tdx_ths_position_eval)
        proc_title =  [proc for proc in positon.keys()]
        print(f'proc_title:{proc_title}')

    # displayMainRes = get_screen_resolution()
    # tdx_ths_position_eval = 'tdx_ths_position%s'%(displayMainRes)
    # print("positon:%s  "%(tdx_ths_position_eval))
    # positon = eval(tdx_ths_position_eval)
    # proc_title =  [proc for proc in positon.keys()]
    # print(f'proc_title:{proc_title}')

        # proc_title =  [proc for proc in sorted(positon.keys(),reverse=False)]

        # sina = [ title for title in cct.terminal_positionKey1K_triton.keys()]

        # proc_title = ['通达信','东方财富','同花顺']
        
        # # proc_title =  [proc for proc in tdx_ths_position.keys()]
        # proc_title =  [proc for proc in proc_title]

    
    # set_proc_windows_position(tasklist,tdx_ths_position=positon)

    # proc_title.extend(sina)
    # title = 'sina_Monitor'
    #set position
    # proc_title = ['instock_Monitor','sina_Market-DurationDnUP','singleAnalyseUtil','人气综合排行榜2.22','行业跟随1.0','东兴证券','通达信金融终端','东方财富','同花顺']
    # proc_title = ['Edge','Firefox','交易信号监控','instock_Monitor','sina_Market-DurationDnUP','人气综合排行榜2.22','行业跟随1.0','东兴证券','通达信金融终端','东方财富','同花顺']
    proc_title = [proc for proc in positon.keys()]
    idx = 0
    idx_status=0

    workExePath = "D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\sina_Monitor.exe"

    exe_status = os.path.exists(workExePath)
    # EXE
    if exe_status:
        print(f'exe_status: {exe_status}')
        proc_title = [proc.replace('.py','.exe') if not proc.startswith('py') else proc for proc in proc_title]
        positon_exe = {}
        for key in positon.keys():
            value = positon[key]
            positon_exe[key.replace('.py','.exe') if not key.startswith('py') else key] = value
        print(f'positon_exe:{positon_exe}')
        positon = positon_exe


    # py2exe
    # proc_title_exe = [name for proc in proc_title for name in (proc, proc.replace('.py', '.exe') if proc.endswith('.py') else proc)]
    # for key, value in positon.items():
    #     # 保留原始 .py 键
    #     positon_exe[key] = value
    #     # 生成对应的 .exe 键（如果不是以 py 开头）
    #     exe_key = key.replace('.py', '.exe') if not key.startswith('py') else key
    #     positon_exe[exe_key] = value

    # exe2py
    # proc_title_new = [p2 for proc in proc_title for p2 in ([proc, proc.replace('.exe', '.py')] if proc.endswith('.exe') else [proc])]
    # proc_title_new = []
    # for proc in proc_title:
    #     if proc.endswith('.exe'):
    #         proc_title_new.append(proc)            # 保留 .exe
    #         proc_title_new.append(proc.replace('.exe', '.py'))  # 生成对应 .py
    #     else:
    #         proc_title_new.append(proc)            # 非 .exe 保留原名

    # positon_exe = {}
    # for key, value in positon.items():
    #     positon_exe[key] = value  # 保留原 key
    #     if key.endswith('.py'):
    #         positon_exe[key.replace('.py', '.exe')] = value  # 添加对应 .exe


    #新加的时候

    appendProc = ['开盘啦竞价板块观察1.0','股票异动数据监控','instock_MonitorTK.py']

    for proc in appendProc:
        if proc not in positon.keys():
            proc_title.append(proc)   # good src 
            print(f'add pro :{proc} to proc_title')



    # proc_title_new.extend(appendProc)
    # positon = positon_exe | appendProc   #dict
    #new dict
    # for title in proc_title:
    #     result=FindWindowRectFromName(title)
    #     if result != (0,0,0,0):
    #         idx+=1
    #         if idx%3 == 0:
    #             print(f'idx:{idx}\\\n')
    idx_all = len(proc_title)
    print("%s={"%(tdx_ths_position_eval),end='')
    for title in proc_title:
        idx+=1
        if idx >3 and idx%3 == 1:
            print("\t\t",end='')
        result=FindWindowRectFromName(title)

        if result == (0,0,0,0):
            # print("'%s': '%s',"%(title,positon[title]),end='')
            if exe_status:
                if title in positon:
                    print("'%s': '%s',"%(title,positon[title]),end='')
            else:
                if title in positon:
                    print("'%s': '%s',"%(title.replace('.exe','.py') if not title.startswith('py') else title,positon[title]),end='')
        if idx%3 == 0:
            print(f'\\')

    print('}\n')     
    # for proc in proc_title:
    #     win_info=list_find_windows(proc)
    #     for win in win_info:
    #         print(win)
    #         set_windows_pos(win.title,tdx_ths_position[proc])

    # proc_title = ['通达信','东方财富','同花顺']
    # # proc_title =  [proc for proc in tdx_ths_position.keys()]
    # proc_title =  [proc for proc in proc_title]

    # print("set pos")
    # set_proc_windows_position(sorted(proc_title,reverse=False),tdx_ths_position=positon)
    print(f'set_proc:')
    # print(f'title: {proc_title},exe: {positon_exe}')
    # import ipdb;ipdb.set_trace()

    set_proc_windows_position(proc_title,tdx_ths_position=positon)


    # print(find_proc_windows('ths-tdx-web'))

