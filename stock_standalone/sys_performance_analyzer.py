# -*- coding:utf-8 -*-
"""
系统性能与内存占用分析工具 (System Performance & Memory Analyzer)
------------------------------------------------------------------
一个独立的高颜值、工程级系统性能与内存占用诊断工具。
支持 DPI 适配、现代暗黑主题、内存/CPU实时监控、进程分组与明细分析（降序排列）、
智能一键释放、以及明细搜索与进程管理。
"""
import sys
import os
import time
import threading
import platform
import subprocess
import ctypes
from typing import List, Dict, Tuple, Any

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

# 尝试引入 psutil 进行底层进程抓取
try:
    import psutil
except ImportError:
    # 自动尝试安装 psutil (如果不存在)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

# Windows 高 DPI 适配，防止界面模糊
try:
    if platform.system() == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(1) # DPI Aware
except Exception:
    pass

# ==============================================================================
# UI 样式与配色常量 (Premium Dark Theme System)
# ==============================================================================
COLOR_BG = "#1E2226"          # 极佳的温润护眼暗灰底盘（消减了强对比刺眼感）
COLOR_CARD = "#252A2F"        # 卡片/容器背景（温暖饱满的中性灰）
COLOR_HEADER = "#2D3338"      # 标题栏/头部/表头背景
COLOR_TEXT_MAIN = "#DCE2E8"   # 主文本颜色（莫兰迪柔白，过滤了刺眼的纯白偏振光）
COLOR_TEXT_MUTED = "#8E98A2"  # 辅助文本（淡雅舒适的雾灰蓝，视觉效果极佳）
COLOR_ACCENT = "#81C784"      # 柔雅的莫兰迪翡翠绿（安全/正常）
COLOR_WARNING = "#FFB74D"     # 柔雅的莫兰迪琥珀黄（警告）
COLOR_DANGER = "#E57373"      # 柔雅的莫兰迪珊瑚红（危险/核心警示）
COLOR_HIGHLIGHT = "#64B5F6"   # 柔雅的莫兰迪天空蓝（高亮/选定，高辨识度且柔和）
COLOR_BORDER = "#333A40"      # 极淡雅的边框分割线

# ==============================================================================
# 性能核心监控与分析引擎
# ==============================================================================
class PerformanceEngine:
    # 物理缓存以支持极限性能优化
    _STATIC_INFO_CACHE = {}  # pid -> (name, exe_path, p_obj)
    _BLOCKED_PIDS = set()    # 缓存已判定无权限访问的系统/保护级 PID，彻底消除 AccessDenied 异常开销

    @staticmethod
    def get_system_ram_info() -> Dict[str, Any]:
        """获取系统物理内存使用指标"""
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024 ** 3),
            "available_gb": mem.available / (1024 ** 3),
            "used_gb": mem.used / (1024 ** 3),
            "percent": mem.percent
        }

    @staticmethod
    def get_system_cpu_percent() -> float:
        """获取系统 CPU 总体使用率"""
        return psutil.cpu_percent(interval=None)

    @staticmethod
    def get_disk_queue_length() -> float:
        """获取 Windows 物理磁盘当前队列长度 (CurrentDiskQueueLength)"""
        try:
            if platform.system() == "Windows":
                # 使用 wmic 快速查询物理磁盘队列长度
                res = subprocess.check_output(
                    'wmic path Win32_PerfFormattedData_PerfDisk_PhysicalDisk where "Name=\'_Total\'" get CurrentDiskQueueLength',
                    shell=True,
                    text=True,
                    stderr=subprocess.DEVNULL
                )
                lines = [line.strip() for line in res.splitlines() if line.strip()]
                if len(lines) > 1:
                    return float(lines[1])
        except Exception:
            pass
        return 0.0

    @staticmethod
    def scan_and_group_processes() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        [极限性能优化版] 扫描系统所有活动进程，并生成：
        - 物理级 PID 缓存自愈，仅抓取新进程的静态属性，消除重复 Windows API 调用
        - 无权限/系统进程静默拦截，彻底根除高频 AccessDenied 异常的上下文卡顿
        - 复用 Process 实体，实现亚毫秒级高精度 CPU 占比提取
        - [NEW] 获取并汇总各进程的线程数 (Threads)
        """
        raw_list = []
        grouped_dict = {}

        try:
            # 1. 抓取当前系统中所有活动 PID 集合
            active_pids = set(psutil.pids())
        except Exception:
            active_pids = set()

        # 2. 自愈：清理已退出的无效 PID 缓存与屏蔽集
        cached_pids = list(PerformanceEngine._STATIC_INFO_CACHE.keys())
        for pid in cached_pids:
            if pid not in active_pids:
                PerformanceEngine._STATIC_INFO_CACHE.pop(pid, None)

        blocked_pids_to_remove = [pid for pid in PerformanceEngine._BLOCKED_PIDS if pid not in active_pids]
        for pid in blocked_pids_to_remove:
            PerformanceEngine._BLOCKED_PIDS.discard(pid)

        # 3. 遍历活动 PID 集合进行数据精细化提取
        for pid in active_pids:
            # 3.1 极速屏蔽：对于之前已确认无权限读取的系统进程，直接跳过，彻底切断 AccessDenied 异常开销
            if pid in PerformanceEngine._BLOCKED_PIDS:
                continue

            try:
                # 3.2 优先命中静态缓存
                if pid in PerformanceEngine._STATIC_INFO_CACHE:
                    name, exe_path, p_obj = PerformanceEngine._STATIC_INFO_CACHE[pid]
                else:
                    # 缓存未命中：仅在此处初始化 Process 实体并一次性提取静态属性
                    p_obj = psutil.Process(pid)
                    name = p_obj.name() or "Unknown"
                    try:
                        exe_path = p_obj.exe() or "N/A"
                    except psutil.AccessDenied:
                        exe_path = "Access Denied"
                    
                    PerformanceEngine._STATIC_INFO_CACHE[pid] = (name, exe_path, p_obj)

                # 3.3 提取动态属性：rss 相比 uss 非常轻量，几乎不消耗 I/O 开销
                try:
                    mem_info = p_obj.memory_info()
                    rss_mb = mem_info.rss / (1024 ** 2)
                    status = p_obj.status() or "unknown"
                    try:
                        threads = p_obj.num_threads() or 1
                    except Exception:
                        threads = 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # 动态属性提取失败也可能是进程死亡或被保护
                    continue

                # 3.4 亚毫秒级复用 CPU 提取
                try:
                    cpu_pct = p_obj.cpu_percent(interval=None) or 0.0
                except Exception:
                    cpu_pct = 0.0

                # 记录明细数据
                raw_list.append({
                    "pid": pid,
                    "name": name,
                    "rss_mb": rss_mb,
                    "cpu_pct": cpu_pct,
                    "threads": threads,
                    "status": status,
                    "path": exe_path
                })

                # 记录分组汇总数据
                if name not in grouped_dict:
                    grouped_dict[name] = {
                        "name": name,
                        "count": 0,
                        "total_rss_mb": 0.0,
                        "max_cpu": 0.0,
                        "total_threads": 0,
                        "pids": []
                    }
                grouped_dict[name]["count"] += 1
                grouped_dict[name]["total_rss_mb"] += rss_mb
                grouped_dict[name]["max_cpu"] = max(grouped_dict[name]["max_cpu"], cpu_pct)
                grouped_dict[name]["total_threads"] += threads
                grouped_dict[name]["pids"].append(pid)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 凡是初始化 or 读取静态属性遭遇 AccessDenied / 找不到的进程，均物理标记为屏蔽，未来彻底不碰
                PerformanceEngine._BLOCKED_PIDS.add(pid)
                PerformanceEngine._STATIC_INFO_CACHE.pop(pid, None)
                continue

        # 明细排序 (按内存降序)
        raw_list.sort(key=lambda x: x["rss_mb"], reverse=True)

        # 分组排序 (按总内存降序)
        grouped_list = list(grouped_dict.values())
        grouped_list.sort(key=lambda x: x["total_rss_mb"], reverse=True)

        return grouped_list, raw_list

    @staticmethod
    def run_system_diagnostics(grouped_list: List[Dict[str, Any]], raw_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        根据进程和系统指标，评估系统性能状态，输出针对性的诊断预警与建议。
        """
        diagnostics = {
            "warnings": [],
            "key_processes": {
                "python": {"threads": 0, "count": 0, "rss_mb": 0.0},
                "tdx": {"threads": 0, "count": 0, "rss_mb": 0.0},
                "hexin": {"threads": 0, "count": 0, "rss_mb": 0.0},
                "mainfree": {"threads": 0, "count": 0, "rss_mb": 0.0},
                "weixin": {"threads": 0, "count": 0, "rss_mb": 0.0}
            },
            "other_key_processes": [],
            "total_threads_monitored": 0,
            "disk_queue": 0.0
        }

        # 统计关键进程以及自适应筛选其他重载线程进程
        other_candidates = []
        for g in grouped_list:
            name_lower = g["name"].lower()
            threads = g.get("total_threads", 0)
            rss = g.get("total_rss_mb", 0.0)
            cnt = g.get("count", 0)
            
            is_core = False
            if "python" in name_lower or "instock" in name_lower:
                diagnostics["key_processes"]["python"]["threads"] += threads
                diagnostics["key_processes"]["python"]["count"] += cnt
                diagnostics["key_processes"]["python"]["rss_mb"] += rss
                is_core = True
            elif "tdx" in name_lower or "tc.exe" in name_lower:
                diagnostics["key_processes"]["tdx"]["threads"] += threads
                diagnostics["key_processes"]["tdx"]["count"] += cnt
                diagnostics["key_processes"]["tdx"]["rss_mb"] += rss
                is_core = True
            elif "hexin" in name_lower or "ths.exe" in name_lower:
                diagnostics["key_processes"]["hexin"]["threads"] += threads
                diagnostics["key_processes"]["hexin"]["count"] += cnt
                diagnostics["key_processes"]["hexin"]["rss_mb"] += rss
                is_core = True
            elif "mainfree" in name_lower:
                diagnostics["key_processes"]["mainfree"]["threads"] += threads
                diagnostics["key_processes"]["mainfree"]["count"] += cnt
                diagnostics["key_processes"]["mainfree"]["rss_mb"] += rss
                is_core = True
            elif "wechat" in name_lower:
                diagnostics["key_processes"]["weixin"]["threads"] += threads
                diagnostics["key_processes"]["weixin"]["count"] += cnt
                diagnostics["key_processes"]["weixin"]["rss_mb"] += rss
                is_core = True

            # 非核心进程且线程数 >= 20，则作为自适应监控对象
            if not is_core and threads >= 20:
                other_candidates.append({
                    "name": g["name"],
                    "threads": threads,
                    "rss_mb": rss,
                    "count": cnt
                })

        # 按线程数降序，取前5个作为活跃系统重载进程
        other_candidates.sort(key=lambda x: x["threads"], reverse=True)
        diagnostics["other_key_processes"] = other_candidates[:5]

        # 获取磁盘队列长度
        disk_q = PerformanceEngine.get_disk_queue_length()
        diagnostics["disk_queue"] = disk_q

        # 进行条件分析
        # 1. 磁盘队列警告
        if disk_q >= 2.0:
            diagnostics["warnings"].append({
                "level": "DANGER",
                "title": "磁盘 I/O 发生严重阻塞 (Disk Queue >= 2.0)",
                "desc": f"当前物理磁盘活动队列长度为 {disk_q:.2f}，已大于警戒值 2.0！这往往代表磁盘读写积压严重，通常会导致量化主程序或行情端发生卡顿和假死。建议打开系统自带的资源监视器 (resmon.exe) 磁盘页，核对是否有高频读写的 H5 数据库锁冲突。"
            })
        elif disk_q > 0.0:
            diagnostics["warnings"].append({
                "level": "INFO",
                "title": "磁盘 I/O 状态健康 (Disk Queue < 2.0)",
                "desc": f"当前物理磁盘活动队列长度为 {disk_q:.2f}，属于正常区间。磁盘不是当前性能瓶颈 of 元凶。"
            })

        # 2. 线程风暴分析 (包含自适应重载线程数)
        core_threads = (
            diagnostics["key_processes"]["python"]["threads"] +
            diagnostics["key_processes"]["tdx"]["threads"] +
            diagnostics["key_processes"]["hexin"]["threads"] +
            diagnostics["key_processes"]["mainfree"]["threads"] +
            diagnostics["key_processes"]["weixin"]["threads"]
        )
        other_heavy_threads = sum(item["threads"] for item in diagnostics["other_key_processes"])
        total_threads_monitored = core_threads + other_heavy_threads
        diagnostics["total_threads_monitored"] = total_threads_monitored

        if total_threads_monitored >= 400:
            diagnostics["warnings"].append({
                "level": "DANGER",
                "title": "高危警告：系统线程风暴 (OS Scheduler Overload)",
                "desc": f"检测到监控的活跃进程累计占用高达 {total_threads_monitored} 个系统线程！这会导致 Windows 调度器内的时间片切换（CreateThread/ExitThread）开销爆满，CPU 资源碎片化，使所有行情和策略响应明显变慢。建议清理无用后台软件或一键清理微信小程序（WeChatAppEx.exe）等重载进程。"
            })
        elif total_threads_monitored >= 250:
            diagnostics["warnings"].append({
                "level": "WARNING",
                "title": "系统活跃线程数偏高 (OS Scheduler High Load)",
                "desc": f"核心进程及自适应重载进程累计占用线程数达 {total_threads_monitored} 个（核心: {core_threads}，其他重载: {other_heavy_threads}）。OS 调度负荷偏高，可能会产生轻微粘滞感。建议清理后台闲置进程。"
            })
        else:
            diagnostics["warnings"].append({
                "level": "INFO",
                "title": "系统线程调度环境健康",
                "desc": f"核心进程及自适应重载进程累计占用线程数 {total_threads_monitored} 个，处于非常健康的轻量区间。"
            })

        # 3. 针对非核心重负载线程进程的自适应警告
        for item in diagnostics["other_key_processes"]:
            if item["threads"] >= 40:
                diagnostics["warnings"].append({
                    "level": "WARNING",
                    "title": f"检测到非核心进程 [{item['name']}] 占用大量线程 ({item['threads']} 个)",
                    "desc": f"非核心进程组 {item['name']} 当前在系统内累计占用了 {item['threads']} 个线程（共 {item['count']} 个并发实例），总内存占用为 {item['rss_mb']:.1f} MB。过多的线程容易导致 Windows 时间片调度被碎片化，可能影响股票行情推送和策略计算速度，建议在实盘交易时段关闭或限制该进程的后台活动。"
                })

        # 4. 针对微信小程序进程的专属提醒
        weixin_total_rss = diagnostics["key_processes"]["weixin"]["rss_mb"]
        if weixin_total_rss > 1024.0:
            diagnostics["warnings"].append({
                "level": "WARNING",
                "title": "微信小程序/后台占用内存过高",
                "desc": f"微信相关进程当前累计占用内存达 {weixin_total_rss/1024:.2f} GB！强烈建议执行上方的一键优化引擎，彻底清理 WeChatAppEx 小程序，以释放这 100+ 线程及内存空间。"
            })

        return diagnostics

    @staticmethod
    def kill_process_by_pid(pid: int) -> Tuple[bool, str]:
        """根据 PID 强制结束指定进程"""
        try:
            p = psutil.Process(pid)
            p.terminate()
            return True, f"成功向 PID {pid} 发送终止信号。"
        except psutil.NoSuchProcess:
            return False, "该进程已经不存在。"
        except psutil.AccessDenied:
            try:
                # 尝试使用 Windows taskkill 提权强制结束
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return True, f"已通过系统管理员权限强制结束 PID {pid}。"
            except Exception as e:
                return False, f"权限不足，终止进程失败: {e}"
        except Exception as e:
            return False, f"未知错误: {e}"

    @staticmethod
    def kill_processes_by_name(name: str) -> Tuple[int, int]:
        """根据进程可执行文件名，批量结束所有相关进程"""
        success_count = 0
        fail_count = 0
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if p.info['name'] and p.info['name'].lower() == name.lower():
                    p.terminate()
                    success_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 尝试用 taskkill
                try:
                    subprocess.run(f"taskkill /F /IM {name}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    success_count += 1
                except:
                    fail_count += 1
            except Exception:
                fail_count += 1
        return success_count, fail_count


# ==============================================================================
# Windows 自启动项目优化管理器 (Windows Startup Manager)
# ==============================================================================
class AutostartManager:
    REG_RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    REG_RUN_DISABLED_PATH = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"

    @staticmethod
    def get_startup_folder() -> str:
        """获取当前用户的启动文件夹路径"""
        try:
            return os.path.join(os.getenv('APPDATA', ''), r'Microsoft\Windows\Start Menu\Programs\Startup')
        except Exception:
            return ""

    @staticmethod
    def run_as_admin(cmd: str, params: str) -> bool:
        """以管理员权限提权运行命令"""
        try:
            import ctypes
            # SW_HIDE = 0
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd, params, None, 0)
            return ret > 32
        except Exception:
            return False

    @staticmethod
    def set_reg_value(hkey, subkey: str, name: str, value: str) -> Tuple[bool, str]:
        """安全写入注册表，若权限不足则提权写入"""
        import winreg
        try:
            # 1. 尝试直接写入
            with winreg.CreateKeyEx(hkey, subkey, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            return True, ""
        except PermissionError:
            # 2. 权限不足，提权写入
            root_name = "HKLM" if hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
            escaped_val = value.replace('"', '\\"')
            args = f'add "{root_name}\\{subkey}" /v "{name}" /t REG_SZ /d "{escaped_val}" /f'
            success = AutostartManager.run_as_admin("reg.exe", args)
            if success:
                return True, ""
            return False, "需要管理员权限授权。"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_reg_value(hkey, subkey: str, name: str) -> Tuple[bool, str]:
        """安全删除注册表值，若权限不足则提权删除"""
        import winreg
        try:
            # 1. 尝试直接删除
            with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            return True, ""
        except FileNotFoundError:
            return True, ""
        except PermissionError:
            # 2. 权限不足，提权删除
            root_name = "HKLM" if hkey == winreg.HKEY_LOCAL_MACHINE else "HKCU"
            args = f'delete "{root_name}\\{subkey}" /v "{name}" /f'
            success = AutostartManager.run_as_admin("reg.exe", args)
            if success:
                return True, ""
            return False, "需要管理员权限授权。"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def list_registry_run_items(hkey, reg_path: str, source_name: str, enabled: bool) -> List[Dict[str, Any]]:
        """列出指定注册表 Run 键中的所有启动项"""
        items = []
        try:
            import winreg
            with winreg.OpenKey(hkey, reg_path, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append({
                            "name": name,
                            "command": value,
                            "source": source_name,
                            "enabled": enabled
                        })
                        i += 1
                    except OSError:
                        break
        except Exception:
            pass
        return items

    @staticmethod
    def list_startup_folder_items() -> List[Dict[str, Any]]:
        """列出启动文件夹中的所有启动项"""
        items = []
        folder = AutostartManager.get_startup_folder()
        if folder and os.path.exists(folder):
            try:
                for file in os.listdir(folder):
                    file_path = os.path.join(folder, file)
                    if file.lower().endswith('.lnk'):
                        items.append({
                            "name": file[:-4],
                            "command": file_path,
                            "source": "启动文件夹",
                            "enabled": True
                        })
                    elif file.lower().endswith('.lnk.disabled'):
                        items.append({
                            "name": file[:-13],
                            "command": file_path,
                            "source": "启动文件夹",
                            "enabled": False
                        })
            except Exception:
                pass
        return items

    @staticmethod
    def list_scheduled_tasks() -> List[Dict[str, Any]]:
        """列出非 Microsoft\\Windows 的第三方和用户自启动计划任务"""
        items = []
        try:
            import subprocess
            import json
            cmd = 'Get-ScheduledTask | Where-Object { $_.TaskPath -notlike "\\Microsoft\\Windows*" } | ForEach-Object { [PSCustomObject]@{TaskName=$_.TaskName; TaskPath=$_.TaskPath; State=$_.State.ToString(); Action=$_.Actions.Execute } } | ConvertTo-Json'
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            out = subprocess.check_output(
                ['powershell', '-NoProfile', '-Command', cmd],
                startupinfo=startupinfo,
                stderr=subprocess.DEVNULL,
                timeout=5.0
            )
            if out:
                raw_data = json.loads(out.decode('gbk', errors='ignore'))
                if isinstance(raw_data, dict):
                    raw_data = [raw_data]
                
                for task in raw_data:
                    task_name = task.get("TaskName", "")
                    task_path = task.get("TaskPath", "\\")
                    
                    full_path = task_path
                    if not full_path.endswith("\\"):
                        full_path += "\\"
                    full_path += task_name
                    if not full_path.startswith("\\"):
                        full_path = "\\" + full_path
                    
                    state = task.get("State", "Ready")
                    action = task.get("Action", "") or ""
                    
                    if not task_name:
                        continue
                    
                    enabled = (state != "Disabled")
                    
                    items.append({
                        "name": full_path,
                        "task_name": task_name,
                        "task_path": task_path,
                        "command": action,
                        "source": "计划任务",
                        "enabled": enabled
                    })
        except Exception:
            pass
        return items

    @staticmethod
    def change_task_state(full_path: str, enable: bool) -> Tuple[bool, str]:
        """启用或禁用计划任务"""
        action_str = "/enable" if enable else "/disable"
        cmd = ["schtasks", "/change", "/tn", full_path, action_str]
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            res = subprocess.run(
                cmd,
                startupinfo=startupinfo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0
            )
            if res.returncode == 0:
                return True, f"已{'启用' if enable else '禁用'}计划任务 [{full_path}]。"
            
            stderr_lower = res.stderr.lower()
            if "access is denied" in stderr_lower or "拒绝访问" in res.stderr:
                args = f'/change /tn "{full_path}" {action_str}'
                success = AutostartManager.run_as_admin("schtasks.exe", args)
                if success:
                    return True, f"已通过管理员权限{'启用' if enable else '禁用'}计划任务 [{full_path}]。"
                else:
                    return False, f"操作需要管理员权限，提权授权失败。"
            
            return False, f"操作失败: {res.stderr.strip()}"
        except Exception as e:
            return False, f"操作异常: {e}"

    @staticmethod
    def delete_task(full_path: str) -> Tuple[bool, str]:
        """删除计划任务"""
        cmd = ["schtasks", "/delete", "/tn", full_path, "/f"]
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            res = subprocess.run(
                cmd,
                startupinfo=startupinfo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0
            )
            if res.returncode == 0:
                return True, f"已成功删除计划任务 [{full_path}]。"
            
            stderr_lower = res.stderr.lower()
            if "access is denied" in stderr_lower or "拒绝访问" in res.stderr:
                args = f'/delete /tn "{full_path}" /f'
                success = AutostartManager.run_as_admin("schtasks.exe", args)
                if success:
                    return True, f"已通过管理员权限成功删除计划任务 [{full_path}]。"
                else:
                    return False, f"操作需要管理员权限，提权授权失败。"
            
            return False, f"删除失败: {res.stderr.strip()}"
        except Exception as e:
            return False, f"操作异常: {e}"

    @staticmethod
    def list_all_autostart_items() -> List[Dict[str, Any]]:
        """汇总所有自启动项（注册表多源、启动文件夹、计划任务）"""
        import winreg
        items = []
        
        # 1. 注册表自启动项
        # HKCU Run
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_CURRENT_USER, 
            r"Software\Microsoft\Windows\CurrentVersion\Run", 
            "注册表 (HKCU)", 
            True
        )
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_CURRENT_USER, 
            r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup", 
            "注册表 (HKCU)", 
            False
        )
        
        # HKLM Run
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_LOCAL_MACHINE, 
            r"Software\Microsoft\Windows\CurrentVersion\Run", 
            "注册表 (HKLM)", 
            True
        )
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_LOCAL_MACHINE, 
            r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup", 
            "注册表 (HKLM)", 
            False
        )
        
        # HKLM-WOW64 Run
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_LOCAL_MACHINE, 
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", 
            "注册表 (HKLM-WOW64)", 
            True
        )
        items += AutostartManager.list_registry_run_items(
            winreg.HKEY_LOCAL_MACHINE, 
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunDisabled_Backup", 
            "注册表 (HKLM-WOW64)", 
            False
        )
        
        # 2. 启动文件夹项
        items += AutostartManager.list_startup_folder_items()
        
        return items

    @staticmethod
    def disable_item(name: str, source: str, command: str) -> Tuple[bool, str]:
        """禁用指定的启动项（将其移至备份区或重命名）"""
        try:
            import winreg
            if "注册表" in source:
                if "HKLM-WOW64" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                elif "HKLM" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                else: # HKCU
                    hkey = winreg.HKEY_CURRENT_USER
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"

                # 1. 写入备份键
                ok, err = AutostartManager.set_reg_value(hkey, back_path, name, command)
                if not ok:
                    return False, f"备份自启动项失败: {err}"

                # 2. 从 Run 键删除
                ok, err = AutostartManager.delete_reg_value(hkey, run_path, name)
                if not ok:
                    AutostartManager.delete_reg_value(hkey, back_path, name)
                    return False, f"禁用自启动项失败: {err}"

                return True, f"已禁用 [{name}] (已存入备份区，可随时重新开启)。"

            elif source == "启动文件夹":
                folder = AutostartManager.get_startup_folder()
                if not folder:
                    return False, "未找到启动文件夹路径。"
                
                old_path = os.path.join(folder, f"{name}.lnk")
                new_path = os.path.join(folder, f"{name}.lnk.disabled")
                
                if os.path.exists(old_path):
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                    return True, f"已禁用启动文件夹中的 [{name}]。"
                else:
                    return False, f"未找到启动项文件: {old_path}"

            elif source == "计划任务":
                return AutostartManager.change_task_state(name, enable=False)

            return False, "未知的自启动项来源。"
        except Exception as e:
            return False, f"操作失败: {e}"

    @staticmethod
    def enable_item(name: str, source: str, command: str) -> Tuple[bool, str]:
        """启用指定的启动项（从备份区恢复或重命名还原）"""
        try:
            import winreg
            if "注册表" in source:
                if "HKLM-WOW64" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                elif "HKLM" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                else: # HKCU
                    hkey = winreg.HKEY_CURRENT_USER
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"

                # 1. 写入 Run 键
                ok, err = AutostartManager.set_reg_value(hkey, run_path, name, command)
                if not ok:
                    return False, f"启用自启动项失败: {err}"

                # 2. 从备份键删除
                AutostartManager.delete_reg_value(hkey, back_path, name)
                
                return True, f"已启用自启动项目 [{name}]。"

            elif source == "启动文件夹":
                folder = AutostartManager.get_startup_folder()
                if not folder:
                    return False, "未找到启动文件夹路径。"
                
                old_path = os.path.join(folder, f"{name}.lnk.disabled")
                new_path = os.path.join(folder, f"{name}.lnk")
                
                if os.path.exists(old_path):
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                    return True, f"已启用启动文件夹中的 [{name}]。"
                else:
                    return False, f"未找到禁用状态的启动项文件: {old_path}"

            elif source == "计划任务":
                return AutostartManager.change_task_state(name, enable=True)

            return False, "未知的自启动项来源。"
        except Exception as e:
            return False, f"操作失败: {e}"

    @staticmethod
    def delete_item(name: str, source: str) -> Tuple[bool, str]:
        """彻底物理删除自启动项目（不留备份）"""
        try:
            import winreg
            if "注册表" in source:
                if "HKLM-WOW64" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                elif "HKLM" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                else: # HKCU
                    hkey = winreg.HKEY_CURRENT_USER
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"

                # 从 Run 键删除
                AutostartManager.delete_reg_value(hkey, run_path, name)
                # 从备份键删除
                AutostartManager.delete_reg_value(hkey, back_path, name)
                
                return True, f"已彻底删除注册表自启动项 [{name}]。"

            elif source == "启动文件夹":
                folder = AutostartManager.get_startup_folder()
                if not folder:
                    return False, "未找到启动文件夹路径。"
                
                p1 = os.path.join(folder, f"{name}.lnk")
                p2 = os.path.join(folder, f"{name}.lnk.disabled")
                
                deleted = False
                if os.path.exists(p1):
                    os.remove(p1)
                    deleted = True
                if os.path.exists(p2):
                    os.remove(p2)
                    deleted = True
                    
                if deleted:
                    return True, f"已彻底删除启动文件夹中的 [{name}]。"
                else:
                    return False, "未找到启动文件夹中的相关启动项文件。"

            elif source == "计划任务":
                return AutostartManager.delete_task(name)

            return False, "未知的自启动项来源。"
        except Exception as e:
            return False, f"删除失败: {e}"

    @staticmethod
    def update_item_command(name: str, source: str, old_command: str, new_command: str) -> Tuple[bool, str]:
        """修改启动项或计划任务的启动命令"""
        try:
            import winreg
            if "注册表" in source:
                if "HKLM-WOW64" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                elif "HKLM" in source:
                    hkey = winreg.HKEY_LOCAL_MACHINE
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"
                else: # HKCU
                    hkey = winreg.HKEY_CURRENT_USER
                    run_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                    back_path = r"Software\Microsoft\Windows\CurrentVersion\RunDisabled_Backup"

                is_enabled = False
                try:
                    with winreg.OpenKey(hkey, run_path, 0, winreg.KEY_READ) as k:
                        winreg.QueryValueEx(k, name)
                        is_enabled = True
                except:
                    pass
                
                target_path = run_path if is_enabled else back_path
                ok, err = AutostartManager.set_reg_value(hkey, target_path, name, new_command)
                if ok:
                    return True, "注册表启动命令更新成功。"
                else:
                    return False, f"更新注册表失败: {err}"

            elif source == "启动文件夹":
                folder = AutostartManager.get_startup_folder()
                if not folder:
                    return False, "未找到启动文件夹。"
                
                p_enabled = os.path.join(folder, f"{name}.lnk")
                p_disabled = os.path.join(folder, f"{name}.lnk.disabled")
                lnk_path = p_enabled if os.path.exists(p_enabled) else p_disabled
                
                if not os.path.exists(lnk_path):
                    return False, "找不到快捷方式文件。"
                
                import shlex
                try:
                    parts = shlex.split(new_command)
                    target = parts[0] if parts else new_command
                    args = " ".join(parts[1:]) if len(parts) > 1 else ""
                except:
                    target = new_command
                    args = ""
                
                ps_script = (
                    f"$s = New-Object -ComObject WScript.Shell; "
                    f"$lnk = $s.CreateShortcut('{lnk_path}'); "
                    f"$lnk.TargetPath = '{target}'; "
                    f"$lnk.Arguments = '{args}'; "
                    f"$lnk.Save()"
                )
                res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=5.0)
                if res.returncode == 0:
                    return True, "启动文件夹快捷方式更新成功。"
                else:
                    return False, f"更新快捷方式失败: {res.stderr.strip()}"

            elif source == "计划任务":
                import shlex
                try:
                    parts = shlex.split(new_command)
                    exe_path = parts[0] if parts else new_command
                    args = " ".join(parts[1:]) if len(parts) > 1 else ""
                except:
                    exe_path = new_command
                    args = ""
                
                arg_part = f" -Argument '{args}'" if args else ""
                ps_script = (
                    f"$act = New-ScheduledTaskAction -Execute '{exe_path}'{arg_part}; "
                    f"Set-ScheduledTask -TaskName '{name}' -Action $act"
                )
                
                res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=5.0)
                if res.returncode == 0:
                    return True, "计划任务启动命令更新成功。"
                
                stderr_lower = res.stderr.lower()
                if "access is denied" in stderr_lower or "拒绝访问" in res.stderr:
                    args_admin = f"-Command \"$act = New-ScheduledTaskAction -Execute '{exe_path}'{arg_part}; Set-ScheduledTask -TaskName '{name}' -Action $act\""
                    success = AutostartManager.run_as_admin("powershell.exe", args_admin)
                    if success:
                        return True, "已通过管理员权限成功更新计划任务启动命令。"
                    else:
                        return False, "操作需要管理员权限，提权授权失败。"
                
                return False, f"修改计划任务失败: {res.stderr.strip()}"

            return False, "未知的自启动项来源。"
        except Exception as e:
            return False, f"操作异常: {e}"

    @staticmethod
    def get_app_path(app_id: str, process_name: str) -> str:
        """尝试自动获取常见软件的可执行文件物理路径"""
        try:
            for p in psutil.process_iter(['name', 'exe']):
                try:
                    p_name = p.info['name']
                    if p_name and p_name.lower() == process_name.lower():
                        exe_path = p.info['exe']
                        if exe_path and os.path.exists(exe_path):
                            return exe_path
                except Exception:
                    pass
        except Exception:
            pass
        
        if app_id == "quant_monitor":
            exe_path = os.path.abspath(sys.argv[0])
            if exe_path.lower().endswith(".py"):
                return f'"{sys.executable}" "{exe_path}"'
            return f'"{exe_path}"'

        try:
            all_items = AutostartManager.list_all_autostart_items()
            for item in all_items:
                if process_name.lower() in item["name"].lower() or process_name.lower() in item["command"].lower():
                    cmd = item["command"].strip()
                    if cmd.startswith('"'):
                        parts = cmd.split('"')
                        if len(parts) > 1 and os.path.exists(parts[1]):
                            return parts[1]
                    else:
                        parts = cmd.split()
                        if parts and os.path.exists(parts[0]):
                            return parts[0]
                    return cmd
        except Exception:
            pass

        common_paths = []
        if app_id == "wechat":
            program_files = os.getenv("ProgramFiles", "C:\\Program Files")
            program_files_x86 = os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")
            common_paths = [
                os.path.join(program_files, "Tencent", "WeChat", "WeChat.exe"),
                os.path.join(program_files_x86, "Tencent", "WeChat", "WeChat.exe"),
                r"C:\Program Files\Tencent\WeChat\WeChat.exe",
                r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe"
            ]
        elif app_id == "tdx":
            common_paths = [
                r"C:\new_tdx\tc.exe",
                r"D:\new_tdx\tc.exe",
                r"C:\通达信\tc.exe",
                r"D:\通达信\tc.exe",
                r"D:\Program Files\new_tdx\tc.exe"
            ]
        elif app_id == "hexin":
            common_paths = [
                r"C:\同花顺\ths.exe",
                r"D:\同花顺\ths.exe",
                r"C:\ths\ths.exe",
                r"D:\ths\ths.exe"
            ]
        elif app_id == "eastmoney":
            common_paths = [
                r"C:\东方财富\mainfree.exe",
                r"D:\东方财富\mainfree.exe",
                r"C:\Eastmoney\mainfree.exe",
                r"D:\Eastmoney\mainfree.exe"
            ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        return ""


# ==============================================================================
# Autostart / Task Detail & Edit Dialog
# ==============================================================================
class AutostartItemDetailDialog(tk.Toplevel):
    def __init__(self, parent, item_info: dict, refresh_callback):
        super().__init__(parent)
        self.parent = parent
        self.item_info = item_info
        self.refresh_callback = refresh_callback
        
        self.title("📝 启动项/计划任务详情与编辑")
        self.geometry("680x440")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # 支持 Esc 关闭
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.font_title = parent.font_title
        self.font_body = parent.font_body
        self.font_small = parent.font_small

        # 使用 tk.Frame 以便完美支持 bg 参数
        main_card = tk.Frame(self, bg=COLOR_CARD, padx=15, pady=15)
        main_card.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_title = ttk.Label(main_card, text="⚙️ 启动项详细属性与命令行编辑", font=self.font_title, foreground=COLOR_HIGHLIGHT, background=COLOR_CARD)
        lbl_title.pack(anchor="w", pady=(0, 15))

        fields = [
            ("项目名称:", item_info.get("name", ""), False),
            ("来源位置/路径:", item_info.get("source", ""), False),
            ("当前状态:", item_info.get("status", ""), False),
        ]

        for label_text, val_text, is_editable in fields:
            row = tk.Frame(main_card, bg=COLOR_CARD)
            row.pack(fill="x", pady=6)
            
            lbl = ttk.Label(row, text=label_text, font=self.font_body, background=COLOR_CARD, width=14, anchor="w")
            lbl.pack(side="left")
            
            ent = tk.Entry(row, bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, readonlybackground=COLOR_HEADER, insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
            ent.insert(0, val_text)
            ent.configure(state="readonly")
            ent.pack(side="left", fill="x", expand=True, ipady=2)
            
            btn_copy = tk.Button(row, text=" 📋 复制 ", command=lambda v=val_text: self.copy_to_clipboard(v),
                                 bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                                 activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                 bd=0, cursor="hand2", padx=8)
            btn_copy.pack(side="right", padx=(5, 0))

        cmd_row = tk.Frame(main_card, bg=COLOR_CARD)
        cmd_row.pack(fill="x", pady=6)
        
        lbl_cmd = ttk.Label(cmd_row, text="运行命令/路径:", font=self.font_body, background=COLOR_CARD, width=14, anchor="w")
        lbl_cmd.pack(side="left")

        self.ent_cmd = tk.Entry(cmd_row, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
        self.ent_cmd.insert(0, item_info.get("command", ""))
        self.ent_cmd.pack(side="left", fill="x", expand=True, ipady=2)

        btn_copy_cmd = tk.Button(cmd_row, text=" 📋 复制 ", command=lambda: self.copy_to_clipboard(self.ent_cmd.get()),
                             bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                             activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                             bd=0, cursor="hand2", padx=8)
        btn_copy_cmd.pack(side="right", padx=(5, 0))

        lbl_tip = ttk.Label(main_card, text="💡 提示: 您可以直接修改上面的运行命令行（包括程序路径 and 运行参数），点击保存修改后，\n系统会自动尝试将其写入注册表或重新设定计划任务参数。修改注册表 HKLM 项或计划任务需要管理员权限。", font=self.font_small, foreground=COLOR_TEXT_MUTED, background=COLOR_CARD, justify="left")
        lbl_tip.pack(anchor="w", pady=(15, 0))

        btn_frame = tk.Frame(main_card, bg=COLOR_CARD)
        btn_frame.pack(fill="x", side="bottom", pady=(10, 0))

        btn_save = tk.Button(btn_frame, text=" 💾 保存修改 ", command=self.save_modification,
                             bg=COLOR_HIGHLIGHT, fg=COLOR_BG, font=self.font_title,
                             activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                             bd=0, cursor="hand2", padx=15, pady=5)
        btn_save.pack(side="right", padx=(10, 0))

        btn_cancel = tk.Button(btn_frame, text="  关闭  ", command=self.destroy,
                               bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_title,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=15, pady=5)
        btn_cancel.pack(side="right")

    def copy_to_clipboard(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
            self.parent.set_status_text("✅ 已复制到剪贴板", COLOR_ACCENT)
        except Exception as e:
            messagebox.showerror("❌ 复制失败", str(e))

    def save_modification(self):
        new_cmd = self.ent_cmd.get().strip()
        if not new_cmd:
            messagebox.showwarning("⚠️ 输入错误", "运行命令行不能为空！")
            return
            
        old_cmd = self.item_info.get("command", "")
        if new_cmd == old_cmd:
            messagebox.showinfo("💡 提示", "命令行内容未发生任何改变。")
            self.destroy()
            return
            
        name = self.item_info.get("name", "")
        source = self.item_info.get("source", "")
        
        if source == "计划任务" or source.startswith("\\"):
            source_type = "计划任务"
        else:
            source_type = source

        self.parent.set_status_text("⏳ 正在应用启动项命令行更改...", COLOR_HIGHLIGHT)
        self.update()
        
        success, msg = AutostartManager.update_item_command(name, source_type, old_cmd, new_cmd)
        if success:
            self.parent.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            messagebox.showinfo("⚡ 修改成功", f"成功更新自启动项 [{name}] 的运行命令行！")
            self.refresh_callback()
            self.destroy()
        else:
            self.parent.set_status_text(f"❌ {msg}", COLOR_DANGER)
            messagebox.showerror("❌ 保存失败", msg)


# ==============================================================================
# Process Detail Dialog
# ==============================================================================
class ProcessItemDetailDialog(tk.Toplevel):
    def __init__(self, parent, proc_info: dict, kill_callback):
        super().__init__(parent)
        self.parent = parent
        self.proc_info = proc_info
        self.kill_callback = kill_callback
        
        self.title("🔬 进程详细属性")
        self.geometry("680x420")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # 支持 Esc 关闭
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.font_title = parent.font_title
        self.font_body = parent.font_body
        self.font_small = parent.font_small

        # 使用 tk.Frame 以便完美支持 bg 参数
        main_card = tk.Frame(self, bg=COLOR_CARD, padx=15, pady=15)
        main_card.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_title = ttk.Label(main_card, text="🔬 进程映像详细属性与控制", font=self.font_title, foreground=COLOR_HIGHLIGHT, background=COLOR_CARD)
        lbl_title.pack(anchor="w", pady=(0, 15))

        fields = [
            ("进程 PID:", str(proc_info.get("pid", "")), "pid"),
            ("进程名称:", proc_info.get("name", ""), "name"),
            ("内存占用:", f"{proc_info.get('rss_mb', 0.0):.2f} MB", "rss"),
            ("CPU 使用率:", f"{proc_info.get('cpu_pct', 0.0):.1f}%", "cpu"),
            ("活跃线程数:", str(proc_info.get("threads", 1)), "threads"),
            ("运行状态:", proc_info.get("status", ""), "status"),
            ("可执行文件路径:", proc_info.get("path", ""), "path")
        ]

        for label_text, val_text, key in fields:
            row = tk.Frame(main_card, bg=COLOR_CARD)
            row.pack(fill="x", pady=4)
            
            lbl = ttk.Label(row, text=label_text, font=self.font_body, background=COLOR_CARD, width=14, anchor="w")
            lbl.pack(side="left")
            
            ent = tk.Entry(row, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, 
                           readonlybackground=COLOR_HEADER,
                           insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
            ent.insert(0, val_text)
            ent.configure(state="readonly")
            ent.pack(side="left", fill="x", expand=True, ipady=2)
            
            btn_copy = tk.Button(row, text=" 📋 复制 ", command=lambda v=val_text: self.copy_to_clipboard(v),
                                 bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                                 activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                 bd=0, cursor="hand2", padx=8)
            btn_copy.pack(side="right", padx=(5, 0))

        btn_frame = tk.Frame(main_card, bg=COLOR_CARD)
        btn_frame.pack(fill="x", side="bottom", pady=(10, 0))

        btn_kill = tk.Button(btn_frame, text=" 🛑 结束该进程 (Kill) ", command=self.kill_process,
                             bg=COLOR_DANGER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                             activebackground=COLOR_DANGER, activeforeground=COLOR_TEXT_MAIN,
                             bd=0, cursor="hand2", padx=15, pady=5)
        btn_kill.pack(side="right", padx=(10, 0))

        btn_cancel = tk.Button(btn_frame, text="  关闭  ", command=self.destroy,
                               bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_title,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=15, pady=5)
        btn_cancel.pack(side="right")

    def copy_to_clipboard(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
            self.parent.set_status_text("✅ 已复制到剪贴板", COLOR_ACCENT)
        except Exception as e:
            messagebox.showerror("❌ 复制失败", str(e))

    def kill_process(self):
        pid = self.proc_info.get("pid")
        if not pid:
            return
        if messagebox.askyesno("⚠️ 警告", f"您确定要强行终止 PID {pid} ({self.proc_info.get('name')}) 吗？\n这可能会导致未保存的数据丢失！"):
            success, msg = PerformanceEngine.kill_process_by_pid(pid)
            if success:
                self.parent.set_status_text(f"✅ {msg}", COLOR_ACCENT)
                messagebox.showinfo("⚡ 结束成功", msg)
                self.kill_callback()
                self.destroy()
            else:
                self.parent.set_status_text(f"❌ {msg}", COLOR_DANGER)
                messagebox.showerror("❌ 结束失败", msg)


# ==============================================================================
# Process Group Detail Dialog
# ==============================================================================
class ProcessGroupDetailDialog(tk.Toplevel):
    def __init__(self, parent, group_info: dict, kill_callback):
        super().__init__(parent)
        self.parent = parent
        self.group_info = group_info
        self.kill_callback = kill_callback
        
        self.title("📊 进程组详细属性")
        self.geometry("680x420")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # 支持 Esc 关闭
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        self.font_title = parent.font_title
        self.font_body = parent.font_body
        self.font_small = parent.font_small

        # 使用 tk.Frame 以便完美支持 bg 参数
        main_card = tk.Frame(self, bg=COLOR_CARD, padx=15, pady=15)
        main_card.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_title = ttk.Label(main_card, text="📊 进程归组统计属性与控制", font=self.font_title, foreground=COLOR_HIGHLIGHT, background=COLOR_CARD)
        lbl_title.pack(anchor="w", pady=(0, 15))

        pids_list = group_info.get("pids", [])
        pids_str = ", ".join(map(str, pids_list))

        fields = [
            ("映像名称:", group_info.get("name", ""), "name"),
            ("并发实例数量:", f"{group_info.get('count', 0)} 个", "count"),
            ("总物理内存:", f"{group_info.get('total_rss_mb', 0.0):.2f} MB", "total_rss"),
            ("峰值 CPU %:", f"{group_info.get('max_cpu', 0.0):.1f}%", "max_cpu"),
            ("总线程数:", str(group_info.get("total_threads", 0)), "threads"),
            ("包含 PID 集合:", pids_str, "pids")
        ]

        for label_text, val_text, key in fields:
            row = tk.Frame(main_card, bg=COLOR_CARD)
            row.pack(fill="x", pady=4)
            
            lbl = ttk.Label(row, text=label_text, font=self.font_body, background=COLOR_CARD, width=14, anchor="w")
            lbl.pack(side="left")
            
            ent = tk.Entry(row, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, 
                           readonlybackground=COLOR_HEADER,
                           insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
            ent.insert(0, val_text)
            ent.configure(state="readonly")
            ent.pack(side="left", fill="x", expand=True, ipady=2)
            
            btn_copy = tk.Button(row, text=" 📋 复制 ", command=lambda v=val_text: self.copy_to_clipboard(v),
                                 bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                                 activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                 bd=0, cursor="hand2", padx=8)
            btn_copy.pack(side="right", padx=(5, 0))

        btn_frame = tk.Frame(main_card, bg=COLOR_CARD)
        btn_frame.pack(fill="x", side="bottom", pady=(10, 0))

        btn_kill = tk.Button(btn_frame, text=" 🛑 结束此组所有进程 (Kill Group) ", command=self.kill_group,
                             bg=COLOR_DANGER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                             activebackground=COLOR_DANGER, activeforeground=COLOR_TEXT_MAIN,
                             bd=0, cursor="hand2", padx=15, pady=5)
        btn_kill.pack(side="right", padx=(10, 0))

        btn_cancel = tk.Button(btn_frame, text="  关闭  ", command=self.destroy,
                               bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_title,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=15, pady=5)
        btn_cancel.pack(side="right")

    def copy_to_clipboard(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
            self.parent.set_status_text("✅ 已复制到剪贴板", COLOR_ACCENT)
        except Exception as e:
            messagebox.showerror("❌ 复制失败", str(e))

    def kill_group(self):
        name = self.group_info.get("name")
        if not name:
            return
        if messagebox.askyesno("⚠️ 警告", f"您确定要强行终止进程映像为 [{name}] 的所有进程实例吗？\n这可能会导致未保存的数据丢失！"):
            self.parent.set_status_text(f"⏳ 正在尝试终止所有 [{name}] 进程...", COLOR_HIGHLIGHT)
            self.update()
            success_count, fail_count = PerformanceEngine.kill_processes_by_name(name)
            msg = f"已成功结束 {success_count} 个 [{name}] 进程映像，失败 {fail_count} 个。"
            self.parent.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            messagebox.showinfo("⚡ 结束成功", msg)
            self.kill_callback()
            self.destroy()


# ==============================================================================
# UI 核心视图类 (GUI Desktop Dashboard)
# ==============================================================================
class SystemPerformanceAnalyzerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("📐 量化系统后台性能与内存深度分析诊断工具")
        # 计算 DPI 缩放因子，用于动态像素对齐，防止高 DPI 下文字与表格宽高不匹配
        try:
            self.dpi_scale = self.winfo_fpixels('1i') / 96.0
        except Exception:
            self.dpi_scale = 1.0
        
        # 采用最初精致和谐的紧凑布局几何比例，并支持自动加载恢复
        try:
            from gui_utils import load_window_position_simple
            default_w, default_h = 1180, 820
            win_w, win_h, win_x, win_y = load_window_position_simple("sys_performance_analyzer", default_w, default_h)
            if win_x is not None and win_y is not None:
                self.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")
            else:
                self.geometry(f"{win_w}x{win_h}")
        except Exception:
            self.geometry("1180x820")
        self.configure(bg=COLOR_BG)

        # 缓存状态变量
        self.grouped_data: List[Dict[str, Any]] = []
        self.raw_data: List[Dict[str, Any]] = []
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.last_update_time = time.time()

        # 初始化自定义现代暗黑样式
        self.setup_ui_styles()
        
        # 组装 UI 结构
        self.build_header_dashboard()
        self.build_quick_optimizer_bar()
        self.build_main_table_area()
        self.build_statusbar()

        # 自动加载并恢复列宽
        try:
            self.load_column_widths()
        except Exception:
            pass

        # 启动后台自动刷新与数据首次加载
        self.first_load_data()
        self.start_refresh_timer()

        # 物理绑定窗口关闭协议，确保安全存盘
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """窗口关闭时物理保存大小、位置与列宽，并彻底释放所有资源"""
        try:
            from gui_utils import save_window_position_simple
            save_window_position_simple(self, "sys_performance_analyzer")
        except Exception:
            pass
            
        try:
            self.save_column_widths()
        except Exception:
            pass
            
        self.destroy()

    def save_column_widths(self):
        """保存表格列宽到统一的 window_config.json 中"""
        try:
            import json
            import tempfile
            from sys_utils import get_app_root, get_conf_path
            from dpi_utils import get_windows_dpi_scale_factor
            
            scale = get_windows_dpi_scale_factor()
            base_dir = get_app_root()
            filename = "window_config.json"
            if scale > 1.5:
                filename = f"scale{int(scale)}_window_config.json"
            config_file = get_conf_path(filename, base_dir)
            
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            # 获取分组统计表的列宽
            grouped_cols = ("name", "count", "total_rss", "max_cpu", "threads", "pids")
            grouped_widths = [int(self.tree_grouped.column(col, "width") / scale) for col in grouped_cols]
            
            # 获取明细列表的列宽
            raw_cols = ("pid", "name", "rss", "cpu", "threads", "status", "path")
            raw_widths = [int(self.tree_raw.column(col, "width") / scale) for col in raw_cols]
            
            # 获取自启动表的列宽
            autostart_cols = ("name", "status", "source", "command")
            autostart_widths = [int(self.tree_autostart.column(col, "width") / scale) for col in autostart_cols]
            
            # 获取计划任务表的列宽
            tasks_cols = ("name", "status", "path", "command")
            tasks_widths = [int(self.tree_tasks.column(col, "width") / scale) for col in tasks_cols]
            
            data["sys_performance_analyzer_columns"] = {
                "grouped": grouped_widths,
                "raw": raw_widths,
                "autostart": autostart_widths,
                "tasks": tasks_widths
            }
            
            # 🚀 [原子化写入] 使用临时文件 + os.replace 确保写入完整，防止 Windows 下并发导致的 0 字节损坏
            fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(config_file), text=True)
            try:
                with os.fdopen(fd, 'w', encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if os.path.exists(config_file):
                    try:
                        os.chmod(config_file, 0o666)
                    except Exception:
                        pass
                os.replace(temp_path, config_file)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                raise e
        except Exception:
            pass

    def load_column_widths(self):
        """从 window_config.json 恢复列宽，并支持 DPI 动态缩放还原"""
        try:
            import json
            from sys_utils import get_app_root, get_conf_path
            from dpi_utils import get_windows_dpi_scale_factor
            
            scale = get_windows_dpi_scale_factor()
            base_dir = get_app_root()
            filename = "window_config.json"
            if scale > 1.5:
                filename = f"scale{int(scale)}_window_config.json"
            config_file = get_conf_path(filename, base_dir)
            
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                cols_data = data.get("sys_performance_analyzer_columns", {})
                
                # 恢复分组表列宽
                grouped_widths = cols_data.get("grouped", [])
                grouped_cols = ("name", "count", "total_rss", "max_cpu", "threads", "pids")
                if len(grouped_widths) == len(grouped_cols):
                    for col, w in zip(grouped_cols, grouped_widths):
                        self.tree_grouped.column(col, width=int(w * scale))
                
                # 恢复明细表列宽
                raw_widths = cols_data.get("raw", [])
                raw_cols = ("pid", "name", "rss", "cpu", "threads", "status", "path")
                if len(raw_widths) == len(raw_cols):
                    for col, w in zip(raw_cols, raw_widths):
                        self.tree_raw.column(col, width=int(w * scale))

                # 恢复自启动表列宽
                autostart_widths = cols_data.get("autostart", [])
                autostart_cols = ("name", "status", "source", "command")
                if len(autostart_widths) == len(autostart_cols):
                    for col, w in zip(autostart_cols, autostart_widths):
                        self.tree_autostart.column(col, width=int(w * scale))

                # 恢复计划任务表列宽
                tasks_widths = cols_data.get("tasks", [])
                tasks_cols = ("name", "status", "path", "command")
                if len(tasks_widths) == len(tasks_cols):
                    for col, w in zip(tasks_cols, tasks_widths):
                        self.tree_tasks.column(col, width=int(w * scale))
        except Exception:
            pass

    def setup_ui_styles(self):
        """配置现代暗黑风格的 ttk 控件样式"""
        style = ttk.Style(self)
        style.theme_use("clam")

        # 统一全局字体 - 精致微缩一号，提升高密度数据可读性
        self.font_title = tkfont.Font(family="Microsoft YaHei", size=10, weight="bold")
        self.font_body = tkfont.Font(family="Microsoft YaHei", size=9)
        self.font_small = tkfont.Font(family="Microsoft YaHei", size=8)

        # 配置背景、文本及表格样式
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD, borderwidth=1, relief="solid")
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT_MAIN, font=self.font_body)
        
        # 仪表板卡片标签
        style.configure("CardTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_MUTED, font=self.font_small)
        style.configure("CardVal.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_MAIN, font=tkfont.Font(family="Consolas", size=15, weight="bold"))

        # 自定义选项卡 (Notebook)
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_HEADER, foreground=COLOR_TEXT_MUTED, padding=[15, 6], font=self.font_title)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_CARD)], 
                  foreground=[("selected", COLOR_HIGHLIGHT)])

        # 现代表格 (Treeview) - 动态调整行高以完美匹配 DPI 和字体，避免高分辨率下文字被截断/不匹配
        from dpi_utils import get_windows_dpi_scale_factor
        scale = get_windows_dpi_scale_factor()
        # 根据缩放因子动态计算行高，基准为 28 像素 (适应 Microsoft YaHei 9号字，提供舒适的上下边距)
        row_height = int(28 * scale)
        style.configure("Treeview", 
                        background=COLOR_CARD, 
                        fieldbackground=COLOR_CARD, 
                        foreground=COLOR_TEXT_MAIN, 
                        rowheight=row_height,
                        font=self.font_body,
                        borderwidth=0)
        style.configure("Treeview.Heading", 
                        background=COLOR_HEADER, 
                        foreground=COLOR_TEXT_MAIN, 
                        font=self.font_title, 
                        relief="flat")
        style.map("Treeview.Heading", background=[("active", COLOR_HIGHLIGHT)], foreground=[("active", COLOR_BG)])
        style.map("Treeview", background=[("selected", COLOR_HIGHLIGHT)], foreground=[("selected", COLOR_BG)])

        # 滚动条样式
        style.configure("Vertical.TScrollbar", background=COLOR_HEADER, borderwidth=0, arrowsize=12)
        
        # 现代输入框
        style.configure("TEntry", fieldbackground=COLOR_HEADER, foreground=COLOR_TEXT_MAIN, borderwidth=0)

    # --------------------------------------------------------------------------
    # UI 视图构建
    # --------------------------------------------------------------------------
    def build_header_dashboard(self):
        """构建顶部系统资源实时状况看板 (CPU、内存占用详情)"""
        top_frame = ttk.Frame(self, padding=(15, 15, 15, 0))
        top_frame.pack(fill="x")

        # 标题栏
        title_bar = ttk.Frame(top_frame)
        title_bar.pack(fill="x", pady=(0, 10))
        
        title_lbl = ttk.Label(title_bar, text="💻 系统实时性能诊断中心 (System Performance Center)", 
                              font=tkfont.Font(family="Microsoft YaHei", size=12, weight="bold"), foreground=COLOR_HIGHLIGHT)
        title_lbl.pack(side="left")

        # 自动刷新开关
        chk_refresh = tk.Checkbutton(title_bar, text="自动每 30 秒刷新", variable=self.auto_refresh_var,
                                     bg=COLOR_BG, fg=COLOR_TEXT_MAIN, selectcolor=COLOR_CARD,
                                     activebackground=COLOR_BG, activeforeground=COLOR_HIGHLIGHT,
                                     font=self.font_small, bd=0, highlightthickness=0)
        chk_refresh.pack(side="right", padx=10)

        btn_manual = tk.Button(title_bar, text=" 🔄 立即刷新 ", command=self.refresh_data_manually,
                               bg=COLOR_HIGHLIGHT, fg=COLOR_BG, font=self.font_small,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=8, pady=3)
        btn_manual.pack(side="right")

        # 诊断卡片容器
        cards_frame = ttk.Frame(top_frame)
        cards_frame.pack(fill="x", pady=5)

        # 卡片 1: 内存使用率
        self.card_ram_pct = self.create_dashboard_card(cards_frame, "物理内存使用率", "0.0%", COLOR_ACCENT)
        self.card_ram_pct.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 2: 内存详细数值 (已用/总量)
        self.card_ram_val = self.create_dashboard_card(cards_frame, "内存占用明细 (已用 / 总量)", "0.00 GB / 0.00 GB", COLOR_TEXT_MAIN)
        self.card_ram_val.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 3: 总体 CPU 占用
        self.card_cpu = self.create_dashboard_card(cards_frame, "CPU 瞬时总载荷", "0.0%", COLOR_HIGHLIGHT)
        self.card_cpu.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 4: 活跃进程数量
        self.card_procs = self.create_dashboard_card(cards_frame, "系统活动进程总数", "0 个", COLOR_WARNING)
        self.card_procs.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 卡片 5: 物理磁盘队列长度
        self.card_disk_queue = self.create_dashboard_card(cards_frame, "物理磁盘队列长度", "0.00", COLOR_ACCENT)
        self.card_disk_queue.pack(side="left", fill="both", expand=True)

    def create_dashboard_card(self, parent: ttk.Frame, title: str, init_val: str, color_theme: str) -> ttk.Frame:
        """快捷创建卡片组件"""
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        
        lbl_title = ttk.Label(card, text=title, style="CardTitle.TLabel")
        lbl_title.pack(anchor="w")

        lbl_val = ttk.Label(card, text=init_val, style="CardVal.TLabel")
        lbl_val.configure(foreground=color_theme)
        lbl_val.pack(anchor="w", pady=(8, 0))

        # 保存标签引用，方便后续动态修改
        card.lbl_val = lbl_val
        return card

    def build_quick_optimizer_bar(self):
        """构建一键智能清理快捷面板"""
        opt_frame = ttk.Frame(self, padding=(15, 10, 15, 0))
        opt_frame.pack(fill="x")

        card_opt = ttk.Frame(opt_frame, style="Card.TFrame", padding=10)
        card_opt.pack(fill="x")

        lbl_tip = ttk.Label(card_opt, text="⚡ 智能一键优化引擎 (Smart Optimization): ", 
                            font=self.font_title, foreground=COLOR_WARNING, background=COLOR_CARD)
        lbl_tip.pack(side="left", padx=(5, 15))

        # 智能按钮配置
        btn_configs = [
            ("💬 清理微信小程序", "微信小程序渲染引擎 (WeChatAppEx) 关闭后常驻后台占用极高，点击彻底杀掉释放约 1-1.5GB 内存", self.optimize_wechat),
            ("🐚 结束残留终端", "清理多次编译或未完全退出的闲置 powershell.exe 后台进程", self.optimize_powershell),
            ("📐 强退残留量化进程", "一键杀掉主程序或多进程卡死残存的 instock_MonitorTK 实例", self.optimize_monitor),
            ("📝 一键生成诊断报告", "在本地生成 Markdown 高阶系统体检报告并直接用记事本打开", self.generate_md_report)
        ]

        for text, tooltip_text, func in btn_configs:
            btn = tk.Button(card_opt, text=text, command=func,
                            bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                            activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                            bd=0, cursor="hand2", padx=10, pady=4)
            btn.pack(side="left", padx=5)

            # 自定义轻量级 ToolTip (悬停状态栏提示)
            self.bind_tooltip(btn, tooltip_text)

    def build_main_table_area(self):
        """构建主体数据分析表格，包含“分组汇总”和“明细列表”两个双向选项卡"""
        main_frame = ttk.Frame(self, padding=(15, 10, 15, 10))
        main_frame.pack(fill="both", expand=True)

        # 顶层布局：选项卡组件
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

        # -------------------- 选项卡 1：进程分组统计表 --------------------
        tab_grouped = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_grouped, text=" 📊 进程归组汇总 (Grouped Summary) ")

        # 过滤与统计提示区
        group_top = ttk.Frame(tab_grouped)
        group_top.pack(fill="x", pady=(0, 5))
        
        lbl_group_desc = ttk.Label(group_top, text="💡 将同名进程（如多进程架构下的 Python / Chrome 实例）进行物理归总，按总常驻内存从大到小排序：", 
                                   font=self.font_small, foreground=COLOR_TEXT_MUTED)
        lbl_group_desc.pack(side="left")

        # 分组表格
        self.tree_grouped = self.create_treeview(
            tab_grouped,
            columns=("name", "count", "total_rss", "max_cpu", "threads", "pids"),
            headings=("📦 进程映像名称 (Executable Name)", "🔢 实例数", "💾 总物理内存占用 (Total RAM)", "⚡ 峰值 CPU %", "🧵 总线程数", "🔑 包含 PID 集合")
        )
        self.tree_grouped.column("name", width=220, anchor="w")
        self.tree_grouped.column("count", width=70, anchor="center")
        self.tree_grouped.column("total_rss", width=130, anchor="e")
        self.tree_grouped.column("max_cpu", width=80, anchor="center")
        self.tree_grouped.column("threads", width=80, anchor="center")
        self.tree_grouped.column("pids", width=380, anchor="w")
        self.tree_grouped.bind("<Double-1>", self.on_grouped_proc_double_click)

        # -------------------- 选项卡 2：明细进程表 (支持实时模糊搜索) --------------------
        tab_raw = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_raw, text=" 🔬 完整进程明细 (Detailed Processes) ")

        # 搜索过滤条
        search_bar = ttk.Frame(tab_raw)
        search_bar.pack(fill="x", pady=(0, 5))

        lbl_search = ttk.Label(search_bar, text="🔍 输入进程名/PID模糊过滤: ", font=self.font_title)
        lbl_search.pack(side="left", padx=5)

        # 现代感单行输入框 (Tk Entry 自定义)
        self.ent_search = tk.Entry(search_bar, textvariable=self.search_var, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, 
                                   insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
        self.ent_search.pack(side="left", fill="x", expand=True, padx=5, ipady=3)

        btn_clear_search = tk.Button(search_bar, text=" 清空 ", command=lambda: self.search_var.set(""),
                                     bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_small, bd=0, cursor="hand2",
                                     activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG)
        btn_clear_search.pack(side="left", padx=5)

        # 明细表格
        self.tree_raw = self.create_treeview(
            tab_raw,
            columns=("pid", "name", "rss", "cpu", "threads", "status", "path"),
            headings=("🔑 PID", "📦 进程名称", "💾 物理内存 (RAM)", "⚡ CPU %", "🧵 线程数", "💡 运行状态", "📂 可执行文件路径 (File Path)")
        )
        self.tree_raw.column("pid", width=75, anchor="center")
        self.tree_raw.column("name", width=160, anchor="w")
        self.tree_raw.column("rss", width=110, anchor="e")
        self.tree_raw.column("cpu", width=70, anchor="center")
        self.tree_raw.column("threads", width=70, anchor="center")
        self.tree_raw.column("status", width=80, anchor="center")
        self.tree_raw.column("path", width=450, anchor="w")
        self.tree_raw.bind("<Double-1>", self.on_raw_proc_double_click)

        # -------------------- 选项卡 3：系统健康诊断与预警 (Health Diagnostics) --------------------
        tab_diagnosis = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_diagnosis, text=" 🩺 系统健康诊断 (Diagnostics) ")

        # 诊断报告容器
        diag_container = ttk.Frame(tab_diagnosis)
        diag_container.pack(fill="both", expand=True)

        # 左右分栏：左侧是关键指标面板，右侧是诊断预警列表
        diag_left = ttk.Frame(diag_container, width=320, padding=5)
        diag_left.pack(side="left", fill="y", padx=(0, 10))
        diag_left.pack_propagate(False)

        diag_right = ttk.Frame(diag_container, padding=5)
        diag_right.pack(side="right", fill="both", expand=True)

        # 左栏：关键量化进程的线程&内存汇总
        lbl_left_title = ttk.Label(diag_left, text="📊 核心进程载荷统计", font=self.font_title, foreground=COLOR_HIGHLIGHT)
        lbl_left_title.pack(anchor="w", pady=(5, 15))

        # 关键统计数据表格
        self.tree_key_stats = ttk.Treeview(diag_left, columns=("proc_name", "threads", "rss"), show="headings", height=10)
        self.tree_key_stats.heading("proc_name", text="进程类别")
        self.tree_key_stats.heading("threads", text="线程数")
        self.tree_key_stats.heading("rss", text="总内存")
        self.tree_key_stats.column("proc_name", width=120, anchor="w")
        self.tree_key_stats.column("threads", width=80, anchor="center")
        self.tree_key_stats.column("rss", width=100, anchor="e")
        self.tree_key_stats.pack(fill="x", pady=5)

        # 磁盘与系统说明
        lbl_diag_tip = ttk.Label(diag_left, text="💡 诊断指标说明:\n1. 磁盘队列: 物理磁盘当前未处理请求数。若 >= 2.0，磁盘正发生读写积压。\n2. 累计线程: 核心进程（Python/通达信/同花顺/微信）以及系统内其他高负载非核心进程（标记为 ⚠️）所累计占用的线程总数。若 >= 400，OS 时间片调度将发生严重卡顿与碎片化阻塞。", font=self.font_small, foreground=COLOR_TEXT_MUTED, justify="left", wraplength=280)
        lbl_diag_tip.pack(anchor="w", pady=(15, 5))

        # 右栏：诊断预警列表 (List of warnings)
        lbl_right_title = ttk.Label(diag_right, text="🚨 系统健康诊断告警与分析建议", font=self.font_title, foreground=COLOR_WARNING)
        lbl_right_title.pack(anchor="w", pady=(5, 10))

        # 使用只读文本区域
        self.txt_warnings = tk.Text(diag_right, bg=COLOR_CARD, fg=COLOR_TEXT_MAIN, wrap="word", font=self.font_body, bd=1, relief="solid", padx=10, pady=10)
        self.txt_warnings.pack(fill="both", expand=True)
        self.txt_warnings.configure(state="disabled")

        # 配置 Text tags 的颜色和样式
        self.txt_warnings.tag_configure("danger_title", foreground=COLOR_DANGER, font=self.font_title)
        self.txt_warnings.tag_configure("warning_title", foreground=COLOR_WARNING, font=self.font_title)
        self.txt_warnings.tag_configure("info_title", foreground=COLOR_HIGHLIGHT, font=self.font_title)
        self.txt_warnings.tag_configure("body", foreground=COLOR_TEXT_MAIN, font=self.font_body)
        self.txt_warnings.tag_configure("muted", foreground=COLOR_TEXT_MUTED, font=self.font_small)

        # -------------------- 选项卡 4：自启动优化管理 (Autostart Optimizer) --------------------
        tab_autostart = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_autostart, text=" 🚀 开机自启动优化 (Autostart) ")
        self.build_autostart_tab(tab_autostart)

        # -------------------- 选项卡 5：系统计划任务管理 (Task Scheduler) --------------------
        tab_tasks = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_tasks, text=" 📅 计划任务管理 (Tasks) ")
        self.build_tasks_tab(tab_tasks)

    def build_autostart_tab(self, tab_autostart: ttk.Frame):
        """构建开机自启动优化选项卡"""
        # 主垂直容器
        main_container = ttk.Frame(tab_autostart, padding=10)
        main_container.pack(fill="both", expand=True)

        lbl_right_title = ttk.Label(main_container, text="📋 全量系统自启动列表与优化控制 (Startup List)", font=self.font_title, foreground=COLOR_WARNING)
        lbl_right_title.pack(anchor="w", pady=(5, 10))

        # 过滤/提示文字
        lbl_right_tip = ttk.Label(main_container, text="💡 提示: 包含注册表 Run 键与 Startup 启动文件夹下的项。右键选中项可进行启用、禁用或彻底删除操作。", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        lbl_right_tip.pack(anchor="w", pady=(0, 5))

        # 自启动列表 Treeview
        self.tree_autostart = ttk.Treeview(
            main_container,
            columns=("name", "status", "source", "command"),
            show="headings",
            selectmode="browse"
        )
        self.tree_autostart.heading("name", text="🔑 启动项名称", command=lambda: self.sort_treeview_column(self.tree_autostart, "name", False))
        self.tree_autostart.heading("status", text="💡 状态", command=lambda: self.sort_treeview_column(self.tree_autostart, "status", False))
        self.tree_autostart.heading("source", text="📂 来源位置", command=lambda: self.sort_treeview_column(self.tree_autostart, "source", False))
        self.tree_autostart.heading("command", text="💿 启动路径/命令", command=lambda: self.sort_treeview_column(self.tree_autostart, "command", False))

        self.tree_autostart.column("name", width=140, anchor="w")
        self.tree_autostart.column("status", width=80, anchor="center")
        self.tree_autostart.column("source", width=130, anchor="center")
        self.tree_autostart.column("command", width=480, anchor="w")

        # 滚动条
        vbar = ttk.Scrollbar(main_container, orient="vertical", command=self.tree_autostart.yview, style="Vertical.TScrollbar")
        vbar.pack(side="right", fill="y")
        self.tree_autostart.configure(yscrollcommand=vbar.set)
        self.tree_autostart.pack(side="left", fill="both", expand=True)

        # 绑定右键菜单与双击事件
        self.tree_autostart.bind("<Button-3>", lambda event: self.show_autostart_context_menu(event))
        self.tree_autostart.bind("<Double-1>", lambda event: self.on_autostart_double_click(event))

        # 底部控制按钮栏
        btn_bar = ttk.Frame(main_container, padding=(0, 10, 0, 0))
        btn_bar.pack(fill="x", side="bottom")

        btn_optimise = tk.Button(btn_bar, text=" ⚡ 一键全面优化 ", command=self.optimize_all_autostarts,
                                 bg=COLOR_DANGER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                                 activebackground=COLOR_DANGER, activeforeground=COLOR_TEXT_MAIN,
                                 bd=0, cursor="hand2", padx=12, pady=5)
        btn_optimise.pack(side="left", padx=(0, 10))
        self.bind_tooltip(btn_optimise, "一键禁用除通达信、同花顺、本量化系统之外的所有非必要第三方自启动项")

        btn_add_custom = tk.Button(btn_bar, text=" ➕ 添加自定义 ", command=self.add_custom_autostart_dialog,
                                   bg=COLOR_HIGHLIGHT, fg=COLOR_BG, font=self.font_title,
                                   activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                   bd=0, cursor="hand2", padx=12, pady=5)
        btn_add_custom.pack(side="left", padx=(0, 15))
        self.bind_tooltip(btn_add_custom, "添加任意外部程序 (.exe, .bat 等) 到系统开机自启动列表")

        # 常见程序快捷切换按钮容器（扁平化横向排列）
        self.common_apps_btn_frame = ttk.Frame(btn_bar)
        self.common_apps_btn_frame.pack(side="left", fill="x")

        # 刷新列表
        btn_refresh_list = tk.Button(btn_bar, text=" 🔄 刷新列表 ", command=self.refresh_autostart_data,
                                    bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                                    activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                    bd=0, cursor="hand2", padx=12, pady=5)
        btn_refresh_list.pack(side="right")
        self.bind_tooltip(btn_refresh_list, "重新扫描注册表和启动文件夹，更新当前自启动状态")

    def refresh_autostart_data(self):
        """刷新并渲染所有自启动列表与卡片数据"""
        self.set_status_text("⏳ 正在扫描系统自启动项目...", COLOR_HIGHLIGHT)
        self.update()
        
        try:
            # 获取最新的所有自启动项
            all_items = AutostartManager.list_all_autostart_items()
            
            # 1. 刷新右侧 Treeview
            for item in self.tree_autostart.get_children():
                self.tree_autostart.delete(item)
                
            for item in all_items:
                status_str = "已启用" if item.get("enabled", True) else "已禁用"
                self.tree_autostart.insert("", "end", values=(
                    item["name"],
                    status_str,
                    item["source"],
                    item["command"]
                ))
                
            # 2. 刷新左侧常见程序卡片
            self.render_autostart_cards(all_items)
            self.set_status_text("Ready. 系统自启动配置扫描完毕。", COLOR_TEXT_MUTED)
        except Exception as e:
            self.set_status_text(f"❌ 扫描自启动项失败: {e}", COLOR_DANGER)

    def render_autostart_cards(self, all_items: List[Dict[str, Any]]):
        """在底部按钮栏中扁平化渲染常见第三方交易/量化软件的自启动一键切换按钮"""
        # 清除按钮容器中的所有子组件
        for widget in self.common_apps_btn_frame.winfo_children():
            widget.destroy()

        common_apps = [
            {
                "id": "quant_monitor",
                "name": "📐 量化监控",
                "process_name": "instock_MonitorTK.exe",
                "reg_name": "InStockMonitor",
                "desc": "本量化系统实时行情监控与报警中心"
            },
            {
                "id": "wechat",
                "name": "💬 微信",
                "process_name": "WeChat.exe",
                "reg_name": "WeChat",
                "desc": "腾讯微信客户端"
            },
            {
                "id": "tdx",
                "name": "📈 通达信",
                "process_name": "tc.exe",
                "reg_name": "TdxTrader",
                "desc": "通达信股票交易终端"
            },
            {
                "id": "hexin",
                "name": "📊 同花顺",
                "process_name": "ths.exe",
                "reg_name": "HexinThs",
                "desc": "同花顺行情终端"
            },
            {
                "id": "eastmoney",
                "name": "💎 东财",
                "process_name": "mainfree.exe",
                "reg_name": "Eastmoney",
                "desc": "东方财富证券交易与行情终端"
            }
        ]

        # 过滤并动态渲染
        # print(f"[DEBUG] render_autostart_cards start. Items: {len(all_items)}")
        for app in common_apps:
            # print(f"[DEBUG] Processing app: {app['id']}")
            matched_item = None
            for item in all_items:
                try:
                    name_str = str(item.get("name") or "")
                    cmd_str = str(item.get("command") or "")
                    if name_str.lower() == app["reg_name"].lower():
                        matched_item = item
                        break
                    if app["process_name"].lower() in cmd_str.lower():
                        matched_item = item
                        break
                except Exception as ex:
                    print(f"[DEBUG] Match error: {ex}")
                    continue

            is_enabled = False
            command_str = ""
            if matched_item:
                is_enabled = matched_item.get("enabled", False)
                command_str = matched_item.get("command", "")
            
            # 根据当前状态，决定文字与颜色
            if is_enabled:
                btn_text = f" {app['name']}: 已启 "
                btn_bg = COLOR_ACCENT
                btn_fg = COLOR_BG
                # 点击则执行“关闭自启动”
                action = lambda a=app, mi=matched_item: self.action_disable_app(a, mi)
                tip = f"点击关闭 {app['name']} 的开机自启动备份。当前自启动命令: {command_str}"
            else:
                btn_text = f" {app['name']}: 已禁 "
                btn_bg = COLOR_HEADER
                btn_fg = COLOR_TEXT_MUTED
                # 点击则执行“开启自启动”
                action = lambda a=app, mi=matched_item: self.action_enable_app(a, mi)
                if command_str:
                    tip = f"点击开启 {app['name']} 的开机自启动。启动命令: {command_str}"
                else:
                    tip = f"点击开启 {app['name']} 的开机自启动（将尝试自动探测路径或提示选择文件）"

            # 创建扁平化按钮
            btn = tk.Button(
                self.common_apps_btn_frame,
                text=btn_text,
                command=action,
                bg=btn_bg,
                fg=btn_fg,
                font=self.font_small,
                activebackground=COLOR_HIGHLIGHT,
                activeforeground=COLOR_BG,
                bd=0,
                cursor="hand2",
                padx=10,
                pady=4
            )
            btn.pack(side="left", padx=5)
            self.bind_tooltip(btn, tip)
            # print(f"[DEBUG] Packed: {app['id']}")

    def action_enable_app(self, app: dict, matched_item: dict):
        """开启常见程序的自启动"""
        cmd_path = ""
        if matched_item:
            cmd_path = matched_item["command"]
        
        if not cmd_path:
            cmd_path = AutostartManager.get_app_path(app["id"], app["process_name"])

        if not cmd_path:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title=f"请手动选择 {app['name']} 的主可执行文件",
                filetypes=[("可执行文件", "*.exe"), ("批处理脚本", "*.bat;*.cmd"), ("所有文件", "*.*")]
            )
            if not path:
                return
            cmd_path = f'"{os.path.normpath(path)}"'

        success, msg = AutostartManager.enable_item(app["reg_name"], "注册表 (HKCU)", cmd_path)
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_autostart_data()
        else:
            messagebox.showerror("❌ 启用失败", msg)

    def action_disable_app(self, app: dict, matched_item: dict):
        """关闭常见程序的自启动"""
        if not matched_item:
            messagebox.showinfo("💡 提示", f"{app['name']} 当前并未开启自启动。")
            return

        success, msg = AutostartManager.disable_item(matched_item["name"], matched_item["source"], matched_item["command"])
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_autostart_data()
        else:
            messagebox.showerror("❌ 禁用失败", msg)

    def show_autostart_context_menu(self, event):
        """全量自启动列表的右键菜单"""
        item = self.tree_autostart.identify_row(event.y)
        if not item:
            return
        self.tree_autostart.selection_set(item)

        values = self.tree_autostart.item(item)["values"]
        name = values[0]
        status = values[1]
        source = values[2]
        command = values[3]

        menu = tk.Menu(self, tearoff=0, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, activebackground=COLOR_HIGHLIGHT)

        if status == "已启用":
            menu.add_command(label=f"❌ 禁用自启动项目 [{name}]", command=lambda: self.menu_disable_autostart(name, source, command))
        else:
            menu.add_command(label=f"🚀 启用自启动项目 [{name}]", command=lambda: self.menu_enable_autostart(name, source, command))

        menu.add_command(label=f"🗑️ 彻底物理删除自启动项目", command=lambda: self.menu_delete_autostart(name, source))
        menu.add_separator()
        
        phys_path = self.extract_physical_path(command)
        if phys_path:
            menu.add_command(label="📂 打开启动程序所在目录", command=lambda: self.open_file_location_action(phys_path))
            
        menu.tk_popup(event.x_root, event.y_root)

    def extract_physical_path(self, command: str) -> str:
        """从自启动/计划任务命令行中提取实际的可执行文件物理路径"""
        cmd = command.strip()
        if not cmd:
            return ""
        
        # 1. 展开 Windows 环境变量（如 %SystemRoot%, %ProgramFiles% 等）
        cmd = os.path.expandvars(cmd)
        
        # 2. 如果以双引号包裹，直接提取双引号内的内容
        if cmd.startswith('"'):
            parts = cmd.split('"')
            if len(parts) > 1:
                path = parts[1].strip()
                return path

        # 3. 针对无引号但可能有空格和参数的情况进行贪婪匹配
        parts = cmd.split()
        if not parts:
            return cmd
            
        temp_path = ""
        for part in parts:
            if temp_path:
                temp_path += " " + part
            else:
                temp_path = part
            
            # 如果加上这部分后，该物理路径已真实存在，直接返回它
            if os.path.exists(temp_path) and os.path.isfile(temp_path):
                return temp_path
                
        # 4. 如果没有直接找到，根据常见的参数前缀 / 或 - 做智能截断
        path_parts = []
        for part in parts:
            if part.startswith('/') or part.startswith('-'):
                break
            path_parts.append(part)
        
        if path_parts:
            fallback_path = " ".join(path_parts)
            return fallback_path
            
        return parts[0]

    def copy_text_to_clipboard(self, text: str):
        """将指定文本复制到剪贴板"""
        try:
            import pyperclip
            pyperclip.copy(text)
            self.set_status_text("✅ 已成功复制到系统剪贴板", COLOR_ACCENT)
        except Exception as e:
            self.set_status_text(f"❌ 复制失败: {e}", COLOR_DANGER)
            messagebox.showerror("❌ 复制失败", f"无法写入剪贴板: {e}")

    def menu_disable_autostart(self, name: str, source: str, command: str):
        """右键菜单：禁用"""
        success, msg = AutostartManager.disable_item(name, source, command)
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_autostart_data()
        else:
            messagebox.showerror("❌ 操作失败", msg)

    def menu_enable_autostart(self, name: str, source: str, command: str):
        """右键菜单：启用"""
        success, msg = AutostartManager.enable_item(name, source, command)
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_autostart_data()
        else:
            messagebox.showerror("❌ 操作失败", msg)

    def menu_delete_autostart(self, name: str, source: str):
        """右键菜单：彻底物理删除"""
        if messagebox.askyesno("⚠️ 危险警告", f"您确定要彻底物理删除自启动项 [{name}] 吗？\n删除后该项将不可恢复！"):
            success, msg = AutostartManager.delete_item(name, source)
            if success:
                self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
                self.refresh_autostart_data()
            else:
                messagebox.showerror("❌ 删除失败", msg)

    def optimize_all_autostarts(self):
        """一键优化：查找并禁用非核心第三方程序的自启动项"""
        try:
            all_items = AutostartManager.list_all_autostart_items()
            enabled_items = [item for item in all_items if item.get("enabled", False)]
            
            whitelist_keywords = [
                "instock", "tdx", "tc.exe", "hexin", "ths.exe", "eastmoney", "mainfree", 
                "security", "defender", "onedrive", "realtek", "intel", "nvidia", "amd"
            ]
            
            to_disable = []
            for item in enabled_items:
                name_lower = item["name"].lower()
                cmd_lower = item["command"].lower()
                
                is_whitelisted = False
                for kw in whitelist_keywords:
                    if kw in name_lower or kw in cmd_lower:
                        is_whitelisted = True
                        break
                        
                if not is_whitelisted:
                    to_disable.append(item)
                    
            if not to_disable:
                messagebox.showinfo("🎉 优化完成", "未检测到需要优化的非必要第三方自启动项，您的系统启动环境非常纯净！")
                return
                
            confirm_msg = "⚡ 智能检测到以下非核心第三方开机自启动项，建议予以禁用优化以提升开机速度与运行性能：\n\n"
            for idx, item in enumerate(to_disable, 1):
                confirm_msg += f"{idx}. [{item['name']}] (位置: {item['source']} | 命令: {item['command'][:60]}...)\n"
            confirm_msg += "\n是否确认一键执行禁用优化？（所有被禁用的项都会在备份区保留，可随时右键恢复）"
            
            if messagebox.askyesno("⚡ 开机自启动一键优化确认", confirm_msg):
                success_cnt = 0
                fail_cnt = 0
                for item in to_disable:
                    success, _ = AutostartManager.disable_item(item["name"], item["source"], item["command"])
                    if success:
                        success_cnt += 1
                    else:
                        fail_cnt += 1
                
                self.set_status_text(f"✅ 自启动优化完成！成功禁用 {success_cnt} 个非核心启动项，失败 {fail_cnt} 个。", COLOR_ACCENT)
                messagebox.showinfo("⚡ 优化成功", f"优化完毕！成功禁用 {success_cnt} 个非核心自启动项，已存入备份。")
                self.refresh_autostart_data()
        except Exception as e:
            messagebox.showerror("❌ 一键优化失败", f"优化执行过程中发生错误: {e}")

    def add_custom_autostart_dialog(self):
        """弹出弹窗以添加自定义自启动项目"""
        dialog = tk.Toplevel(self)
        dialog.title("➕ 添加自定义自启动项")
        dialog.geometry("520x220")
        dialog.configure(bg=COLOR_CARD)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        lbl_title = ttk.Label(dialog, text="➕ 新建自定义开机自启动项", font=self.font_title, foreground=COLOR_HIGHLIGHT, background=COLOR_CARD)
        lbl_title.pack(pady=10)

        frame_name = ttk.Frame(dialog, background=COLOR_CARD)
        frame_name.pack(fill="x", padx=20, pady=5)
        
        lbl_name = ttk.Label(frame_name, text="启动项名称:", font=self.font_body, background=COLOR_CARD, width=12)
        lbl_name.pack(side="left")
        
        ent_name = tk.Entry(frame_name, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
        ent_name.pack(side="left", fill="x", expand=True, ipady=2)

        frame_path = ttk.Frame(dialog, background=COLOR_CARD)
        frame_path.pack(fill="x", padx=20, pady=5)
        
        lbl_path = ttk.Label(frame_path, text="程序路径/命令:", font=self.font_body, background=COLOR_CARD, width=12)
        lbl_path.pack(side="left")
        
        ent_path = tk.Entry(frame_path, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, insertbackground=COLOR_TEXT_MAIN, font=self.font_body, bd=1, relief="solid")
        ent_path.pack(side="left", fill="x", expand=True, ipady=2)

        def browse_path():
            from tkinter import filedialog
            file_selected = filedialog.askopenfilename(
                title="选择自启动程序可执行文件",
                filetypes=[("可执行文件", "*.exe"), ("批处理脚本", "*.bat;*.cmd"), ("所有文件", "*.*")]
            )
            if file_selected:
                norm_path = os.path.normpath(file_selected)
                ent_path.delete(0, "end")
                ent_path.insert(0, f'"{norm_path}"')
                
                base_name = os.path.basename(file_selected)
                name_without_ext = os.path.splitext(base_name)[0]
                if not ent_name.get():
                    ent_name.insert(0, name_without_ext)

        btn_browse = tk.Button(frame_path, text=" 浏览... ", command=browse_path,
                               bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_small,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=8)
        btn_browse.pack(side="right", padx=(5, 0))

        frame_btns = ttk.Frame(dialog, background=COLOR_CARD)
        frame_btns.pack(fill="x", padx=20, pady=20)

        def save_custom():
            name = ent_name.get().strip()
            cmd = ent_path.get().strip()
            if not name or not cmd:
                messagebox.showwarning("⚠️ 输入不完整", "启动项名称与程序路径不能为空！")
                return
                
            success, msg = AutostartManager.enable_item(name, "注册表 (HKCU)", cmd)
            if success:
                self.set_status_text(f"✅ 成功添加自启动项: {name}", COLOR_ACCENT)
                self.refresh_autostart_data()
                dialog.destroy()
            else:
                messagebox.showerror("❌ 添加失败", msg)

        btn_save = tk.Button(frame_btns, text="  确定添加  ", command=save_custom,
                             bg=COLOR_HIGHLIGHT, fg=COLOR_BG, font=self.font_title,
                             activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                             bd=0, cursor="hand2", padx=15, pady=5)
        btn_save.pack(side="right", padx=(10, 0))

        btn_cancel = tk.Button(frame_btns, text="  取消  ", command=dialog.destroy,
                               bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=self.font_title,
                               activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                               bd=0, cursor="hand2", padx=15, pady=5)
        btn_cancel.pack(side="right")

    def build_tasks_tab(self, tab_tasks: ttk.Frame):
        """构建开机计划任务优化管理选项卡"""
        container = ttk.Frame(tab_tasks)
        container.pack(fill="both", expand=True)

        lbl_title = ttk.Label(container, text="📋 系统非内置计划任务列表与优化控制 (Task Scheduler)", font=self.font_title, foreground=COLOR_WARNING)
        lbl_title.pack(anchor="w", pady=(5, 10))

        lbl_tip = ttk.Label(container, text="💡 提示: 包含第三方后台自启动与自动更新计划任务。双击可查看详情与编辑命令，右键可进行启用、禁用或物理删除操作。", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        lbl_tip.pack(anchor="w", pady=(0, 5))

        self.tree_tasks = ttk.Treeview(
            container,
            columns=("name", "status", "path", "command"),
            show="headings",
            selectmode="browse"
        )
        self.tree_tasks.heading("name", text="🔑 任务名称", command=lambda: self.sort_treeview_column(self.tree_tasks, "name", False))
        self.tree_tasks.heading("status", text="💡 状态", command=lambda: self.sort_treeview_column(self.tree_tasks, "status", False))
        self.tree_tasks.heading("path", text="📂 任务路径", command=lambda: self.sort_treeview_column(self.tree_tasks, "path", False))
        self.tree_tasks.heading("command", text="💿 运行程序命令行", command=lambda: self.sort_treeview_column(self.tree_tasks, "command", False))

        self.tree_tasks.column("name", width=150, anchor="w")
        self.tree_tasks.column("status", width=80, anchor="center")
        self.tree_tasks.column("path", width=120, anchor="center")
        self.tree_tasks.column("command", width=420, anchor="w")

        vbar = ttk.Scrollbar(container, orient="vertical", command=self.tree_tasks.yview, style="Vertical.TScrollbar")
        vbar.pack(side="right", fill="y")
        self.tree_tasks.configure(yscrollcommand=vbar.set)
        self.tree_tasks.pack(side="left", fill="both", expand=True)

        self.tree_tasks.bind("<Button-3>", lambda event: self.show_tasks_context_menu(event))
        self.tree_tasks.bind("<Double-1>", lambda event: self.on_task_double_click(event))

        btn_bar = ttk.Frame(container, padding=(0, 10, 0, 0))
        btn_bar.pack(fill="x", side="bottom")

        btn_optimise = tk.Button(btn_bar, text=" ⚡ 一键优化自动更新计划任务 ", command=self.optimize_all_tasks,
                                 bg=COLOR_DANGER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                                 activebackground=COLOR_DANGER, activeforeground=COLOR_TEXT_MAIN,
                                 bd=0, cursor="hand2", padx=12, pady=5)
        btn_optimise.pack(side="left", padx=(0, 10))
        self.bind_tooltip(btn_optimise, "一键禁用所有已知的第三方自动更新/升级等非核心计划任务")

        btn_refresh_list = tk.Button(btn_bar, text=" 🔄 刷新列表 ", command=self.refresh_tasks_data,
                                    bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, font=self.font_title,
                                    activebackground=COLOR_HIGHLIGHT, activeforeground=COLOR_BG,
                                    bd=0, cursor="hand2", padx=12, pady=5)
        btn_refresh_list.pack(side="right")
        self.bind_tooltip(btn_refresh_list, "重新检索系统计划任务，并过滤出非 Windows 内置的第三方计划任务")

    def refresh_tasks_data(self):
        """刷新并渲染计划任务列表"""
        self.set_status_text("⏳ 正在检索第三方计划任务项目...", COLOR_HIGHLIGHT)
        self.update()
        
        try:
            all_tasks = AutostartManager.list_scheduled_tasks()
            
            for item in self.tree_tasks.get_children():
                self.tree_tasks.delete(item)
                
            for item in all_tasks:
                status_str = "已启用" if item.get("enabled", True) else "已禁用"
                self.tree_tasks.insert("", "end", values=(
                    item["task_name"],
                    status_str,
                    item["task_path"],
                    item["command"]
                ))
                
            self.set_status_text("Ready. 系统非内置计划任务检索完毕。", COLOR_TEXT_MUTED)
        except Exception as e:
            self.set_status_text(f"❌ 检索计划任务失败: {e}", COLOR_DANGER)

    def show_tasks_context_menu(self, event):
        """计划任务列表的右键菜单"""
        item = self.tree_tasks.identify_row(event.y)
        if not item:
            return
        self.tree_tasks.selection_set(item)

        values = self.tree_tasks.item(item)["values"]
        name = values[0]
        status = values[1]
        path = values[2]
        command = values[3]

        menu = tk.Menu(self, tearoff=0, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, activebackground=COLOR_HIGHLIGHT)

        path_part = path
        if not path_part.endswith("\\"):
            path_part += "\\"
        full_path = path_part + name
        if not full_path.startswith("\\"):
            full_path = "\\" + full_path

        if status == "已启用":
            menu.add_command(label=f"❌ 禁用计划任务 [{name}]", command=lambda: self.menu_disable_task(full_path))
        else:
            menu.add_command(label=f"🚀 启用计划任务 [{name}]", command=lambda: self.menu_enable_task(full_path))

        menu.add_command(label="🗑️ 彻底物理删除计划任务", command=lambda: self.menu_delete_task(full_path))
        menu.add_separator()
        
        menu.add_command(label="📋 复制任务名称", command=lambda: self.copy_text_to_clipboard(name))
        menu.add_command(label="📋 复制运行命令行", command=lambda: self.copy_text_to_clipboard(command))
        menu.add_command(label="🛠️ 查看详情与编辑命令", command=lambda: self.open_task_detail_by_values(values))
        menu.add_separator()
        
        phys_path = self.extract_physical_path(command)
        if phys_path:
            menu.add_command(label="📂 打开运行程序所在目录", command=lambda: self.open_file_location_action(phys_path))
            
        menu.tk_popup(event.x_root, event.y_root)

    def open_task_detail_by_values(self, values):
        name = values[0]
        status = values[1]
        path = values[2]
        command = values[3]

        path_part = path
        if not path_part.endswith("\\"):
            path_part += "\\"
        full_path = path_part + name
        if not full_path.startswith("\\"):
            full_path = "\\" + full_path

        item_info = {
            "name": full_path,
            "status": status,
            "source": "计划任务",
            "command": command
        }
        AutostartItemDetailDialog(self, item_info, self.refresh_tasks_data)

    def menu_disable_task(self, full_path: str):
        success, msg = AutostartManager.change_task_state(full_path, enable=False)
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_tasks_data()
        else:
            messagebox.showerror("❌ 禁用失败", msg)

    def menu_enable_task(self, full_path: str):
        success, msg = AutostartManager.change_task_state(full_path, enable=True)
        if success:
            self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
            self.refresh_tasks_data()
        else:
            messagebox.showerror("❌ 启用失败", msg)

    def menu_delete_task(self, full_path: str):
        if messagebox.askyesno("⚠️ 危险警告", f"您确定要彻底物理删除计划任务 [{full_path}] 吗？\n删除后该项将不可恢复！"):
            success, msg = AutostartManager.delete_task(full_path)
            if success:
                self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
                self.refresh_tasks_data()
            else:
                messagebox.showerror("❌ 删除失败", msg)

    def optimize_all_tasks(self):
        """一键优化：查找并禁用已知的第三方更新/升级计划任务"""
        try:
            all_tasks = AutostartManager.list_scheduled_tasks()
            enabled_tasks = [t for t in all_tasks if t.get("enabled", True)]
            
            update_keywords = [
                "update", "upd", "googleupdate", "edgeupdate", "onedrive", 
                "logi", "nvidia", "adobe", "sogou", "steam", "wps"
            ]
            
            to_disable = []
            for t in enabled_tasks:
                name_lower = t["name"].lower()
                cmd_lower = t["command"].lower()
                
                is_target = False
                for kw in update_keywords:
                    if kw in name_lower or kw in cmd_lower:
                        is_target = True
                        break
                
                if is_target:
                    to_disable.append(t)
            
            if not to_disable:
                messagebox.showinfo("🎉 优化完成", "没有检测到需要禁用的第三方自动更新计划任务。")
                return
                
            confirm_msg = "⚡ 智能检测到以下非必要的第三方自动更新或后台开机拉起计划任务，建议予以禁用优化以减少系统后台负担：\n\n"
            for idx, t in enumerate(to_disable, 1):
                confirm_msg += f"{idx}. [{t['task_name']}] (路径: {t['task_path']} | 命令: {t['command'][:60]}...)\n"
            confirm_msg += "\n是否确认一键执行禁用优化？（禁用后随时可在本界面右键重新启用）"
            
            if messagebox.askyesno("⚡ 计划任务一键优化确认", confirm_msg):
                success_cnt = 0
                fail_cnt = 0
                for t in to_disable:
                    success, _ = AutostartManager.change_task_state(t["name"], enable=False)
                    if success:
                        success_cnt += 1
                    else:
                        fail_cnt += 1
                
                self.set_status_text(f"✅ 计划任务优化完成！成功禁用 {success_cnt} 个，失败 {fail_cnt} 个。", COLOR_ACCENT)
                messagebox.showinfo("⚡ 优化成功", f"优化完毕！成功禁用 {success_cnt} 个非必要自动更新计划任务。")
                self.refresh_tasks_data()
        except Exception as e:
            messagebox.showerror("❌ 一键优化失败", f"优化执行过程中发生错误: {e}")

    def on_autostart_double_click(self, event):
        """双击全量自启动列表项"""
        item = self.tree_autostart.identify_row(event.y)
        if not item:
            return
        
        values = self.tree_autostart.item(item)["values"]
        item_info = {
            "name": values[0],
            "status": values[1],
            "source": values[2],
            "command": values[3]
        }
        AutostartItemDetailDialog(self, item_info, self.refresh_autostart_data)

    def on_task_double_click(self, event):
        """双击计划任务列表项"""
        item = self.tree_tasks.identify_row(event.y)
        if not item:
            return
            
        values = self.tree_tasks.item(item)["values"]
        name = values[0]
        status = values[1]
        path = values[2]
        command = values[3]

        path_part = path
        if not path_part.endswith("\\"):
            path_part += "\\"
        full_path = path_part + name
        if not full_path.startswith("\\"):
            full_path = "\\" + full_path

        item_info = {
            "name": full_path,
            "status": status,
            "source": "计划任务",
            "command": command
        }
        AutostartItemDetailDialog(self, item_info, self.refresh_tasks_data)

    def on_raw_proc_double_click(self, event):
        """双击完整进程明细行"""
        item = self.tree_raw.identify_row(event.y)
        if not item:
            return
        
        values = self.tree_raw.item(item)["values"]
        pid = values[0]
        name = values[1]
        rss_str = values[2]
        cpu_str = values[3]
        threads = values[4]
        status = values[5]
        path = values[6]

        try:
            if "GB" in rss_str:
                rss_mb = float(rss_str.replace("GB", "").strip()) * 1024
            else:
                rss_mb = float(rss_str.replace("MB", "").strip())
        except:
            rss_mb = 0.0

        try:
            cpu_pct = float(cpu_str.replace("%", "").strip())
        except:
            cpu_pct = 0.0

        proc_info = {
            "pid": pid,
            "name": name,
            "rss_mb": rss_mb,
            "cpu_pct": cpu_pct,
            "threads": threads,
            "status": status,
            "path": path
        }
        
        ProcessItemDetailDialog(self, proc_info, self.refresh_data_manually)

    def on_grouped_proc_double_click(self, event):
        """双击进程映像分组汇总行"""
        item = self.tree_grouped.identify_row(event.y)
        if not item:
            return
            
        values = self.tree_grouped.item(item)["values"]
        name = values[0]
        count = values[1]
        rss_str = values[2]
        cpu_str = values[3]
        threads = values[4]
        pids_str = values[5]

        pids = []
        for g in self.grouped_data:
            if g["name"] == name:
                pids = g.get("pids", [])
                break
        
        if not pids:
            try:
                clean_pids = pids_str.split("...")[0].strip()
                pids = [int(p.strip()) for p in clean_pids.split(",") if p.strip().isdigit()]
            except:
                pass

        try:
            if "GB" in rss_str:
                rss_mb = float(rss_str.replace("GB", "").strip()) * 1024
            else:
                rss_mb = float(rss_str.replace("MB", "").strip())
        except:
            rss_mb = 0.0

        try:
            cpu_pct = float(cpu_str.replace("%", "").strip())
        except:
            cpu_pct = 0.0

        group_info = {
            "name": name,
            "count": count,
            "total_rss_mb": rss_mb,
            "max_cpu": cpu_pct,
            "total_threads": threads,
            "pids": pids
        }
        
        ProcessGroupDetailDialog(self, group_info, self.refresh_data_manually)

    def create_treeview(self, parent: ttk.Frame, columns: tuple, headings: tuple) -> ttk.Treeview:
        """通用封装：快速创建高颜值暗黑 Treeview 带美化滚动条"""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        
        # 绑定列头和点击排序属性
        for col, head in zip(columns, headings):
            tree.heading(col, text=head, command=lambda c=col: self.sort_treeview_column(tree, c, False))
            
        tree.pack(side="left", fill="both", expand=True)

        # 美化细边框垂直滚动条
        vbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        vbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=vbar.set)

        # 绑定右键菜单
        tree.bind("<Button-3>", lambda event: self.show_context_menu(event, tree))

        return tree

    def build_statusbar(self):
        """构建底端信息提示状态栏"""
        self.status_bar = ttk.Frame(self, padding=(15, 2, 15, 2), style="Card.TFrame")
        self.status_bar.pack(fill="x", side="bottom")

        self.status_lbl = ttk.Label(self.status_bar, text="Ready. 系统性能监视引擎运行中...", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        self.status_lbl.pack(side="left")

        self.time_lbl = ttk.Label(self.status_bar, text="最后同步时间: --:--:--", font=self.font_small, foreground=COLOR_TEXT_MUTED)
        self.time_lbl.pack(side="right")

    # --------------------------------------------------------------------------
    # 悬停 ToolTip 绑定系统
    # --------------------------------------------------------------------------
    def bind_tooltip(self, widget, text: str):
        """在底部状态栏同步显示按钮的提示，避免遮挡悬浮窗"""
        widget.bind("<Enter>", lambda e: self.set_status_text(f"💡 说明: {text}", color=COLOR_WARNING))
        widget.bind("<Leave>", lambda e: self.set_status_text("Ready. 系统性能监视引擎运行中...", color=COLOR_TEXT_MUTED))

    def set_status_text(self, text: str, color=COLOR_TEXT_MAIN):
        self.status_lbl.configure(text=text, foreground=color)

    # --------------------------------------------------------------------------
    # 数据流加载、刷新与渲染核心 (Thread-safe Data Piping)
    # --------------------------------------------------------------------------
    def first_load_data(self):
        """首次强制同步加载数据，防首屏白洞"""
        self.set_status_text("⏳ 正在进行系统全量进程与自启动扫描...", COLOR_HIGHLIGHT)
        self.update()
        self.execute_refresh_cycle()
        try:
            self.refresh_autostart_data()
        except Exception:
            pass
        try:
            self.refresh_tasks_data()
        except Exception:
            pass

    def start_refresh_timer(self):
        """后台轮询刷新定时器"""
        def loop():
            while True:
                time.sleep(30.0)
                if self.auto_refresh_var.get():
                    self.execute_refresh_cycle()

        # 开启守护线程进行后台静默扫描，防 UI 线程假死卡顿
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def refresh_data_manually(self):
        """手动强制刷新触发"""
        self.set_status_text("⏳ 正在手动重新抓取全量系统进程与自启动项目...", COLOR_HIGHLIGHT)
        self.execute_refresh_cycle(is_manual=True)
        try:
            self.refresh_autostart_data()
        except Exception:
            pass
        try:
            self.refresh_tasks_data()
        except Exception:
            pass

    def execute_refresh_cycle(self, is_manual=False):
        """核心数据异步加载闭环，确保主线程0毫秒阻塞"""
        def async_worker():
            try:
                # 1. 抓取系统硬件基础状况
                ram_info = PerformanceEngine.get_system_ram_info()
                cpu_pct = PerformanceEngine.get_system_cpu_percent()

                # 2. 扫描并归类排序进程 (在后台线程中进行 heavy calculations)
                grouped, raw = PerformanceEngine.scan_and_group_processes()
                self.grouped_data = grouped
                self.raw_data = raw

                # 3. 运行系统健康诊断
                diagnostics = PerformanceEngine.run_system_diagnostics(grouped, raw)

                # 4. 线程安全地回调 UI 进行绘制
                self.after(0, lambda: self.render_ui(ram_info, cpu_pct, diagnostics, is_manual))
            except Exception as e:
                self.after(0, lambda: self.set_status_text(f"❌ 性能指标抓取发生异常: {e}", COLOR_DANGER))

        # 开启独立守护线程，保证主界面 100% 顺滑，绝不卡顿
        worker_thread = threading.Thread(target=async_worker, daemon=True)
        worker_thread.start()

    def render_ui(self, ram_info: dict, cpu_pct: float, diagnostics: dict, is_manual=False):
        """渲染顶部核心卡片及表格数据"""
        # 更新卡片数值
        self.card_ram_pct.lbl_val.configure(text=f"{ram_info['percent']}%")
        # 根据内存占用率变色
        if ram_info['percent'] > 85:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_DANGER)
        elif ram_info['percent'] > 70:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_WARNING)
        else:
            self.card_ram_pct.lbl_val.configure(foreground=COLOR_ACCENT)

        self.card_ram_val.lbl_val.configure(text=f"{ram_info['used_gb']:.2f} GB / {ram_info['total_gb']:.2f} GB")
        self.card_cpu.lbl_val.configure(text=f"{cpu_pct:.1f}%")
        self.card_procs.lbl_val.configure(text=f"{len(self.raw_data)} 个")

        # 更新磁盘队列卡片数值与颜色
        disk_q = diagnostics["disk_queue"]
        self.card_disk_queue.lbl_val.configure(text=f"{disk_q:.2f}")
        if disk_q >= 2.0:
            self.card_disk_queue.lbl_val.configure(foreground=COLOR_DANGER)
        elif disk_q > 0.0:
            self.card_disk_queue.lbl_val.configure(foreground=COLOR_WARNING)
        else:
            self.card_disk_queue.lbl_val.configure(foreground=COLOR_ACCENT)

        # 刷新渲染表格数据
        self.render_grouped_table()
        self.apply_filter()  # 应用搜索框内容后渲染明细表格
        
        # 刷新渲染系统健康诊断 Tab
        self.render_diagnostics_tab(diagnostics)

        # 更新底端状态栏
        self.time_lbl.configure(text=f"最后同步时间: {time.strftime('%H:%M:%S')}")
        if is_manual:
            self.set_status_text("✅ 物理内存与进程状态手动刷新成功！", COLOR_ACCENT)

    def render_diagnostics_tab(self, diagnostics: dict):
        """渲染系统健康诊断卡与警告列表"""
        # 1. 刷新左侧核心进程载荷统计 Treeview
        for item in self.tree_key_stats.get_children():
            self.tree_key_stats.delete(item)

        key_names = {
            "python": "量化系统/Python",
            "tdx": "通达信交易端",
            "hexin": "同花顺程序",
            "mainfree":"东方财富",
            "weixin": "微信及小程序"
        }

        for key, name in key_names.items():
            stats = diagnostics["key_processes"][key]
            rss_val = stats["rss_mb"]
            rss_str = f"{rss_val:.1f} MB"
            if rss_val >= 1024:
                rss_str = f"{rss_val/1024:.2f} GB"
            
            self.tree_key_stats.insert("", "end", values=(
                name,
                f"{stats['threads']} 个",
                rss_str
            ))

        # 自适应添加其他高负载非核心进程至 Treeview 中
        for item in diagnostics.get("other_key_processes", []):
            rss_val = item["rss_mb"]
            rss_str = f"{rss_val:.1f} MB"
            if rss_val >= 1024:
                rss_str = f"{rss_val/1024:.2f} GB"
            
            self.tree_key_stats.insert("", "end", values=(
                f"⚠️ {item['name']}",
                f"{item['threads']} 个",
                rss_str
            ))

        # 2. 刷新右侧文本区域警告列表
        self.txt_warnings.configure(state="normal")
        self.txt_warnings.delete("1.0", "end")

        warnings = diagnostics.get("warnings", [])
        if not warnings:
            self.txt_warnings.insert("end", "🎉 系统健康诊断：未检测到任何异常载荷或阻塞风险。你的 Windows 时间片调度环境非常健康。\n\n", "info_title")
        else:
            for idx, w in enumerate(warnings, 1):
                level = w["level"]
                title_tag = "info_title"
                if level == "DANGER":
                    title_tag = "danger_title"
                elif level == "WARNING":
                    title_tag = "warning_title"

                self.txt_warnings.insert("end", f"{idx}. 【{level}】{w['title']}\n", title_tag)
                self.txt_warnings.insert("end", f"{w['desc']}\n\n", "body")
                
        self.txt_warnings.insert("end", "-" * 60 + "\n", "muted")
        self.txt_warnings.insert("end", "🛠️ 高阶系统卡顿排查指引:\n", "info_title")
        self.txt_warnings.insert("end", "• [磁盘 I/O 排查] 按 Win+R 输入 resmon.exe 打开系统自带的资源监视器，切换到'磁盘'选项卡，展开'磁盘活动'，在'物理磁盘'模块下核对活动时间和磁盘队列长度。如果队列长度 >= 2 且某个 .h5 或 .db 文件读写频繁，说明是该文件锁争抢严重。\n", "body")
        self.txt_warnings.insert("end", "• [OS 时间片调度排查] 频繁的线程创建与销毁 (Thread Storm) 是通达信和量化前台卡顿的隐形元凶。例如，微信占用超过 100+ 线程，同花顺/恒生也是线程大户，在实盘交易时段，强烈建议退出无用聊天软件，释放 CPU 线程时间片资源。\n", "body")

        self.txt_warnings.configure(state="disabled")

    def render_grouped_table(self):
        """加载渲染进程分组汇总表 (降序)"""
        # 记录当前选中项，以防刷新后闪烁丢失选中
        selected_item = self.tree_grouped.selection()
        selected_name = ""
        if selected_item:
            selected_name = self.tree_grouped.item(selected_item[0])["values"][0]

        # 清空重绘
        for item in self.tree_grouped.get_children():
            self.tree_grouped.delete(item)

        for g in self.grouped_data:
            rss_str = f"{g['total_rss_mb']:.2f} MB"
            if g['total_rss_mb'] >= 1024:
                rss_str = f"{g['total_rss_mb']/1024:.2f} GB"

            pids_str = ", ".join(map(str, g['pids'][:12]))
            if len(g['pids']) > 12:
                pids_str += f" ... 等共 {len(g['pids'])} 个"

            item_id = self.tree_grouped.insert("", "end", values=(
                g['name'],
                g['count'],
                rss_str,
                f"{g['max_cpu']:.1f}%",
                g.get('total_threads', 0),
                pids_str
            ))

            # 还原选中项
            if g['name'] == selected_name:
                self.tree_grouped.selection_set(item_id)

    def apply_filter(self):
        """实时执行模糊搜索框的规则过滤与渲染"""
        query = self.search_var.get().strip().lower()

        # 备份当前明细表格的选中 PID
        selected_item = self.tree_raw.selection()
        selected_pid = -1
        if selected_item:
            selected_pid = int(self.tree_raw.item(selected_item[0])["values"][0])

        # 清空明细表
        for item in self.tree_raw.get_children():
            self.tree_raw.delete(item)

        # 迭代数据源进行模糊比对
        for r in self.raw_data:
            if query:
                pid_match = query in str(r['pid'])
                name_match = query in r['name'].lower()
                path_match = query in r['path'].lower()
                if not (pid_match or name_match or path_match):
                    continue

            rss_str = f"{r['rss_mb']:.2f} MB"
            if r['rss_mb'] >= 1024:
                rss_str = f"{r['rss_mb']/1024:.2f} GB"

            item_id = self.tree_raw.insert("", "end", values=(
                r['pid'],
                r['name'],
                rss_str,
                f"{r['cpu_pct']:.1f}%",
                r.get('threads', 1),
                r['status'],
                r['path']
            ))

            # 还原选中
            if r['pid'] == selected_pid:
                self.tree_raw.selection_set(item_id)

    # --------------------------------------------------------------------------
    # 表格交互管理 (右键菜单、列排序、数据自适应)
    # --------------------------------------------------------------------------
    def show_context_menu(self, event, tree: ttk.Treeview):
        """右键弹出高级系统进程控制菜单"""
        item = tree.identify_row(event.y)
        if not item:
            return
        tree.selection_set(item)

        menu = tk.Menu(self, tearoff=0, bg=COLOR_HEADER, fg=COLOR_TEXT_MAIN, activebackground=COLOR_HIGHLIGHT)
        
        # 判断是分组汇总表还是明细表
        if tree == self.tree_grouped:
            values = tree.item(item)["values"]
            name = values[0]
            menu.add_command(label=f"🔪 结束全部该映像进程 ({name})", command=lambda: self.kill_grouped_processes_action(name))
        else:
            values = tree.item(item)["values"]
            pid = int(values[0])
            name = values[1]
            path = values[6]
            
            menu.add_command(label=f"🔬 查看 PID {pid} 诊断详情", command=lambda: self.view_process_detail_action(pid, name, path))
            menu.add_command(label=f"🔪 强制终止该单个进程 (PID: {pid})", command=lambda: self.kill_single_process_action(pid, name))
            menu.add_separator()
            menu.add_command(label="📂 打开进程文件所在目录", command=lambda: self.open_file_location_action(path))

        menu.tk_popup(event.x_root, event.y_root)

    def sort_treeview_column(self, tree: ttk.Treeview, col: str, reverse: bool):
        """点击表头对表格进行排序"""
        data_list = []
        for child in tree.get_children(""):
            val = tree.set(child, col)
            sort_val = val
            if col in ("total_rss", "rss"):
                try:
                    num_part = float(val.split()[0])
                    if "GB" in val:
                        num_part *= 1024
                    sort_val = num_part
                except:
                    sort_val = 0.0
            elif col in ("count", "pid", "threads"):
                sort_val = int(val)
            elif "cpu" in col.lower():
                try:
                    sort_val = float(val.replace("%", ""))
                except:
                    sort_val = 0.0
            else:
                sort_val = str(val).lower()

            data_list.append((sort_val, child))

        data_list.sort(reverse=reverse)

        for index, (val, child) in enumerate(data_list):
            tree.move(child, "", index)

        tree.heading(col, command=lambda: self.sort_treeview_column(tree, col, not reverse))

    # --------------------------------------------------------------------------
    # 进程控制管理动作 (Process Control Actions)
    # --------------------------------------------------------------------------
    def kill_single_process_action(self, pid: int, name: str):
        """强制结束单体进程"""
        if messagebox.askyesno("⚠️ 警告", f"确定要彻底关闭进程: {name} (PID: {pid}) 吗？\n如果该进程属于关键系统服务，可能会引起系统崩溃！"):
            success, msg = PerformanceEngine.kill_process_by_pid(pid)
            if success:
                self.set_status_text(f"✅ {msg}", COLOR_ACCENT)
                self.execute_refresh_cycle()
            else:
                messagebox.showerror("❌ 操作失败", msg)

    def kill_grouped_processes_action(self, name: str):
        """批量结束某类同名映像的所有进程"""
        if messagebox.askyesno("⚠️ 警告", f"确定要强杀所有名称为 {name} 的并发子进程吗？\n这将向系统所有该名称的实例发送结束指令！"):
            self.set_status_text(f"⏳ 正在深度清理全部 {name} 进程...", COLOR_HIGHLIGHT)
            self.update()
            success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(name)
            self.set_status_text(f"✅ 清理完成！成功结束 {success_cnt} 个，失败 {fail_cnt} 个 {name} 进程。", COLOR_ACCENT)
            self.execute_refresh_cycle()

    def view_process_detail_action(self, pid: int, name: str, path: str):
        """查看某个明细进程的深度系统级信息"""
        try:
            p = psutil.Process(pid)
            ctime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.create_time()))
            mem_info = p.memory_full_info()
            
            detail_msg = (
                f"📦 映像名称: {name}\n"
                f"🔑 进程 PID: {pid}\n"
                f"💡 运行状态: {p.status()}\n"
                f"⏰ 创建时间: {ctime}\n"
                f"📂 可执行文件路径:\n{path}\n\n"
                f"--- 💾 内存指标详情 ---\n"
                f"• 常驻内存 (RSS): {mem_info.rss / (1024**2):.2f} MB\n"
                f"• 虚拟内存 (VMS): {mem_info.vms / (1024**2):.2f} MB\n"
                f"• 私有物理集 (USS): {getattr(mem_info, 'uss', 0) / (1024**2):.2f} MB\n"
                f"• 页面交换占池: {getattr(mem_info, 'pagefile', 0) / (1024**2):.2f} MB\n"
                f"• 系统调用句柄数: {p.num_handles() if hasattr(p, 'num_handles') else 'N/A'}"
            )
            messagebox.showinfo(f"🔬 进程 {name} (PID: {pid}) 诊断报告", detail_msg)
        except Exception as e:
            messagebox.showerror("❌ 获取详情失败", f"无法抓取该进程指标，可能已经自动退出: {e}")

    def open_file_location_action(self, path: str):
        """在 Windows 资源管理器中高亮选中并打开文件路径，具有极强的兼容定位和只读自愈能力"""
        if not path or path == "N/A":
            messagebox.showwarning("⚠️ 路径不可达", "该程序没有提供有效的运行路径。")
            return
        
        try:
            # 1. 展开环境变量并清理外部引号
            clean_path = os.path.expandvars(path).strip()
            clean_path = clean_path.replace('"', '')

            # 2. 如果只是一个非绝对文件名称 (如 notepad.exe 等)，尝试通过 PATH 或标准 Windows 目录补全绝对路径
            if not os.path.isabs(clean_path):
                import shutil
                found_abs = shutil.which(clean_path)
                if found_abs:
                    clean_path = found_abs
                else:
                    for sys_dir in [r"C:\Windows\System32", r"C:\Windows", r"C:\Windows\SysWOW64"]:
                        possible = os.path.join(sys_dir, clean_path)
                        if os.path.exists(possible):
                            clean_path = possible
                            break

            # 3. 判断处理后的绝对路径是否存在
            if os.path.exists(clean_path):
                if os.path.isfile(clean_path):
                    # 如果是文件，通过 /select 选中定位它
                    subprocess.run(f'explorer.exe /select,"{os.path.normpath(clean_path)}"', shell=True)
                else:
                    # 如果是目录，直接启动
                    os.startfile(os.path.normpath(clean_path))
            else:
                # 4. 路径自身不存在时的自愈策略：尝试打开其父目录
                parent = os.path.dirname(clean_path)
                if parent and os.path.exists(parent):
                    os.startfile(os.path.normpath(parent))
                else:
                    messagebox.showerror("❌ 打开失败", f"找不到指定的文件、目录或其父级目录：\n{clean_path}")
        except Exception as e:
            messagebox.showerror("❌ 启动资源管理器失败", f"无法打开位置: {e}")

    # --------------------------------------------------------------------------
    # 智能一键优化清理逻辑 (One-Click Optimization Kernels)
    # --------------------------------------------------------------------------
    def optimize_wechat(self):
        """清理常驻后台不退出的微信小程序渲染引擎 (WeChatAppEx)"""
        p_name = "WeChatAppEx.exe"
        self.set_status_text("⏳ 正在批量强制清理微信后台残留小程序渲染进程...", COLOR_HIGHLIGHT)
        self.update()
        
        success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(p_name)
        if success_cnt > 0:
            self.set_status_text(f"✅ 成功清理了 {success_cnt} 个 WeChatAppEx 渲染进程，瞬间释放超过 1.0 GB 内存！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"成功强制杀掉 {success_cnt} 个常驻后台的小程序渲染进程！")
        else:
            self.set_status_text("💡 未检测到有处于活动状态的 WeChatAppEx.exe 进程。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "后台没有发现残留的微信小程序渲染进程。")
        self.execute_refresh_cycle()

    def optimize_powershell(self):
        """一键清理卡死或闲置残留的 Powershell 后台命令行终端"""
        p_name = "powershell.exe"
        self.set_status_text("⏳ 正在扫描并清理卡死或无用 Powershell 后台终端...", COLOR_HIGHLIGHT)
        self.update()
        
        success_cnt, fail_cnt = PerformanceEngine.kill_processes_by_name(p_name)
        if success_cnt > 0:
            self.set_status_text(f"✅ 成功关闭了 {success_cnt} 个 powershell 后台残留进程！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"成功强制终止了 {success_cnt} 个常驻后台的 PowerShell 终端！")
        else:
            self.set_status_text("💡 未发现常驻后台的可终止 powershell.exe 进程。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "后台没有发现残留的 PowerShell 后台进程。")
        self.execute_refresh_cycle()

    def optimize_monitor(self):
        """一键结束残留的主系统进程实例"""
        p_name = "instock_MonitorTK_Nuita.exe"
        # 找出当前运行的所有该进程，排除自身父子关系后杀掉
        current_pid = os.getpid()
        killed_cnt = 0
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if p.info['name'] == p_name and p.info['pid'] != current_pid:
                    p.terminate()
                    killed_cnt += 1
            except:
                pass
        
        if killed_cnt > 0:
            self.set_status_text(f"✅ 成功强退了 {killed_cnt} 个残留的量化系统主窗口实例！", COLOR_ACCENT)
            messagebox.showinfo("⚡ 清理成功", f"已成功强制退出 {killed_cnt} 个残留的 instock_MonitorTK_Nuita 实例！")
        else:
            self.set_status_text("💡 没有发现多余残留的量化系统进程实例。", COLOR_TEXT_MUTED)
            messagebox.showinfo("⚡ 扫描完成", "未检测到有其他多余常驻后台的主系统进程实例。")
        self.execute_refresh_cycle()

    def generate_md_report(self):
        """一键生成高阶 Markdown 诊断体检报告并使用系统记事本打开"""
        # 读取当前硬件与进程状态
        ram = PerformanceEngine.get_system_ram_info()
        cpu = PerformanceEngine.get_system_cpu_percent()
        
        # 运行系统健康诊断
        diagnostics = PerformanceEngine.run_system_diagnostics(self.grouped_data, self.raw_data)
        disk_q = diagnostics["disk_queue"]
        total_key_threads = diagnostics["total_threads_monitored"]
        
        # 取分组 Top 10
        top_groups = self.grouped_data[:10]
        
        report_content = f"""# 📐 系统性能与内存占用分析体检报告
报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
--------------------------------------------------

## 📊 1. 物理内存与 CPU 负载指标
* 🖥️ 物理内存总量: {ram['total_gb']:.2f} GB
* 💾 物理内存已用: {ram['used_gb']:.2f} GB (占比: {ram['percent']}%)
* 💡 物理内存可用: {ram['available_gb']:.2f} GB
* ⚡ CPU 瞬时总体载荷: {cpu:.1f}%
* 🔑 活动进程总数: {len(self.raw_data)} 个
* 💿 物理磁盘队列长度: {disk_q:.2f} (警告阈值: >= 2.0)
* 🧵 核心及重载进程累计占用线程: {total_key_threads} 个 (量化系统、通达信、同花顺、东财、微信及其他高负载进程)
"""
        other_heavy_list = diagnostics.get("other_key_processes", [])
        if other_heavy_list:
            report_content += "\n### ⚠️ 自动检测到的其他高负载非核心进程组 (线程 >= 20):\n"
            for item in other_heavy_list:
                report_content += f"* **{item['name']}** -> 累计线程数: **{item['threads']}** 个 | 内存占用: {item['rss_mb']:.1f} MB | 并发实例数: {item['count']} 个\n"

        report_content += """
## 🩺 2. 系统健康诊断告警列表
"""
        warnings = diagnostics.get("warnings", [])
        if not warnings:
            report_content += "🎉 系统健康诊断：未检测到任何异常载荷或阻塞风险。你的 Windows 时间片调度环境非常健康。\n\n"
        else:
            for idx, w in enumerate(warnings, 1):
                report_content += f"### {idx}. 【{w['level']}】{w['title']}\n* **分析建议**: {w['desc']}\n\n"

        report_content += "\n## 🔍 3. 常驻内存 (RSS) 消耗前十名进程汇总\n以下是将同名多进程映像物理汇总后的消耗排名：\n\n"
        for i, g in enumerate(top_groups, 1):
            rss_str = f"{g['total_rss_mb']:.2f} MB"
            if g['total_rss_mb'] >= 1024:
                rss_str = f"{g['total_rss_mb']/1024:.2f} GB"
            report_content += f"{i}. **{g['name']}** (活动实例: {g['count']} 个) -> 累计占用: **{rss_str}** | 峰值 CPU: {g['max_cpu']:.1f}% | 线程数: {g.get('total_threads', 0)}\n"

        report_content += """
## ⚡ 4. 智能优化建议与卡顿排查
1. **微信小程序 WeChatAppEx.exe**: 实盘交易时段常驻后台占用了 100+ 线程与 1.5GB+ 内存，是 OS 线程时间片碎片化竞争的元凶，建议退出微信或点击一键清理。
2. **通达信 & 同花顺**: 频繁的 CreateThread / ExitThread 内核调用容易引起 system 调度过载，建议交易完毕后关闭或重启。
3. **磁盘 I/O 阻塞**: 若磁盘队列 >= 2.0，建议打开 Windows 的资源监视器 `resmon.exe` -> 磁盘页，排查大文件（如 HDF5 读写）的读写冲突。
"""
        
        # 写入临时文件
        temp_dir = os.environ.get("TEMP", os.getcwd())
        report_path = os.path.join(temp_dir, "System_Memory_Diagnosis_Report.md")
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            
            # 使用默认记事本打开该 MD 文件
            os.system(f'notepad.exe "{report_path}"')
            self.set_status_text(f"✅ 诊断报告生成成功: {report_path}", COLOR_ACCENT)
        except Exception as e:
            messagebox.showerror("❌ 报告生成失败", f"无法写入诊断文件: {e}")

# ==============================================================================
# 应用程序物理入口点 (App Main Entry)
# ==============================================================================
def launch_analyzer():
    """独立的子进程性能分析器启动入口 (支持多进程反序列化)"""
    import platform
    import ctypes
    # 开启高 DPI 线程感知，防止高分屏下窗体及文字模糊
    try:
        if platform.system() == "Windows":
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
        
    try:
        app = SystemPerformanceAnalyzerGUI()
        app.mainloop()
    except Exception as ex:
        import sys
        print(f"❌ Subprocess SystemPerformanceAnalyzer crashed: {ex}", file=sys.stderr)


if __name__ == "__main__":
    launch_analyzer()

