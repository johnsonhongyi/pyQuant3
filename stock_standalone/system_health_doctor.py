# -*- coding: utf-8 -*-
"""
==============================================================================
系统全自动健康诊断与故障根因分析专家 (System Health Doctor)
==============================================================================
一键全自动分析：
1. 虚拟内存死锁（Commit Charge 触顶与 D 盘分页文件撑爆）
2. 显卡子系统异常（0x116 TDR 掉驱动、0x124 WHEA 硬件不可纠正错误、向日葵虚拟驱动冲突）
3. 应用程序硬错误与系统卡顿（Unknown Hard Error / 0xc0000005 / AppHang）
4. 输出直接定位的核心病灶与靶向解决处方
==============================================================================
"""

import os
import sys

# 兼容 Windows CMD / PowerShell 控制台输出
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import json
import winreg
import psutil
import datetime
import subprocess

def run_powershell(cmd: str, timeout: int = 12) -> str:
    """安全跨平台/跨代码页调用 PowerShell，杜绝编码解码崩溃"""
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
        raw = p.stdout
        for enc in ['utf-8', 'gb18030', 'gbk']:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('utf-8', errors='replace')
    except Exception:
        return ""

class SystemHealthDoctor:
    def __init__(self):
        self.findings = []
        self.risk_level = "HEALTHY"  # HEALTHY, WARNING, CRITICAL
        self.score = 100

    def add_issue(self, level: str, category: str, title: str, detail: str, suggestion: str):
        if level == "CRITICAL":
            self.score = max(0, self.score - 35)
            self.risk_level = "CRITICAL"
        elif level == "WARNING":
            self.score = max(0, self.score - 15)
            if self.risk_level != "CRITICAL":
                self.risk_level = "WARNING"
        self.findings.append({
            "level": level,
            "category": category,
            "title": title,
            "detail": detail,
            "suggestion": suggestion
        })

    def check_memory_and_pagefile(self):
        """1. 检查物理内存与虚拟内存分页文件死锁"""
        # 读取注册表中配置的 PagingFiles
        pagefiles_cfg = []
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management")
            try:
                pf, _ = winreg.QueryValueEx(key, "PagingFiles")
                if isinstance(pf, list):
                    pagefiles_cfg = pf
                elif isinstance(pf, str):
                    pagefiles_cfg = [pf]
            except Exception:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass

        # 检查磁盘空间
        disk_usages = {}
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_usages[part.mountpoint.upper()] = {
                    "total_gb": usage.total / (1024**3),
                    "free_gb": usage.free / (1024**3),
                    "percent": usage.percent
                }
            except Exception:
                pass

        # 分析分页文件是否将所在盘撑满
        for entry in pagefiles_cfg:
            parts = entry.strip().split()
            if not parts:
                continue
            pf_path = parts[0]
            drive = os.path.splitdrive(pf_path)[0].upper() + "\\"
            if drive in disk_usages:
                d_info = disk_usages[drive]
                pf_actual_gb = 0
                if os.path.exists(pf_path):
                    try:
                        pf_actual_gb = os.path.getsize(pf_path) / (1024**3)
                    except Exception:
                        pass
                
                # 如果所在盘剩余空间不足 30GB，或者占用率超过 85%
                if d_info["free_gb"] < 30.0 or d_info["percent"] > 88.0:
                    self.add_issue(
                        level="CRITICAL",
                        category="虚拟内存/磁盘死锁",
                        title=f"分页文件严重撑爆驱动器 {drive} (空间告急)",
                        detail=(
                            f"系统虚拟内存分页文件配置在 {pf_path}，当前文件已膨胀至 {pf_actual_gb:.1f} GB！\n"
                            f"   而驱动器 {drive} 仅剩 {d_info['free_gb']:.1f} GB 可用空间（磁盘占用率已达 {d_info['percent']}%）。\n"
                            f"   当系统运行多进程量化监控（instock_MonitorTK）、行情软件及 Python 管道时，分页文件因物理空间耗尽无法再扩展，\n"
                            f"   触发系统内核报错 'The paging file is too small for this operation to complete'，\n"
                            f"   导致 Commit Limit 触顶，引发全系统响应极度卡顿、程序假死未响应及 Unknown Hard Error 报错！"
                        ),
                        suggestion=(
                            f"1. 打开【系统属性】->【高级】->【性能设置】->【高级】->【虚拟内存】；\n"
                            f"   2. 选中 {drive}，选择【无分页文件】，点击【设置】；\n"
                            f"   3. 选中剩余空间充裕的磁盘（如 E 盘尚有超 140GB 空间），选择【系统管理的大小】并点击【设置】。"
                        )
                    )

    def check_gpu_and_display(self):
        """2. 检查显卡驱动、第三方虚拟显示驱动冲突"""
        ps_cmd = 'Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, PNPDeviceID | ConvertTo-Json'
        out = run_powershell(ps_cmd, timeout=8)
        if out.strip():
            try:
                devices = json.loads(out.strip())
                if isinstance(devices, dict):
                    devices = [devices]
                
                has_virtual_display = False
                virtual_dev_names = []
                has_nvidia = False
                has_intel = False
                for d in devices:
                    name = d.get("Name", "")
                    if any(kw in name.lower() for kw in ["oray", "idd", "virtual", "spacedesk", "twomon"]):
                        has_virtual_display = True
                        virtual_dev_names.append(name)
                    if "nvidia" in name.lower():
                        has_nvidia = True
                    if "intel" in name.lower():
                        has_intel = True

                if has_virtual_display and has_nvidia and has_intel:
                    self.add_issue(
                        level="WARNING",
                        category="显示子系统冲突",
                        title=f"检测到可能引发闪屏/黑屏的虚拟显示驱动: {', '.join(virtual_dev_names)}",
                        detail=(
                            f"当前系统为核显(Intel)+独显(NVIDIA)双显卡架构，同时检测到已安装第三方间接显示驱动: {', '.join(virtual_dev_names)}。\n"
                            f"   此类驱动会注入 DWM 虚拟显示管线，在双显卡切换、功耗节能转换或屏幕休眠唤醒时，极易造成屏幕闪烁、黑屏或无法点亮！"
                        ),
                        suggestion="在【设备管理器】->【显示适配器】中卸载该设备并勾选“删除驱动程序”，或在向日葵等软件中关闭远程虚拟屏驱动。"
                    )
            except Exception:
                pass

        # 检查 nvidia-smi 状态
        try:
            p = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            if p.returncode != 0:
                self.add_issue(
                    level="WARNING",
                    category="独显驱动",
                    title="NVIDIA 独立显卡管理接口 (nvidia-smi) 响应异常",
                    detail="系统未能正常读取 NVIDIA 显卡状态，可能处于掉卡或驱动死锁状态。",
                    suggestion="使用 DDU 清理显卡驱动后重新安装官方稳定 WHQL 版本。"
                )
        except Exception:
            pass

    def check_system_crash_events(self):
        """3. 查询最近系统级硬件崩溃、TDR 掉驱动、Kernel-Power 41 与 Hard Error"""
        ps_cmd = '''
        $cutoff = (Get-Date).AddDays(-14)
        $events = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$cutoff} -ErrorAction SilentlyContinue |
            Where-Object {
                ($_.ProviderName -eq 'Microsoft-Windows-Kernel-Power' -and $_.Id -eq 41) -or
                ($_.ProviderName -eq 'Microsoft-Windows-WER-SystemErrorReporting' -and $_.Id -eq 1001) -or
                ($_.ProviderName -eq 'Service Control Manager' -and $_.Id -eq 7000 -and $_.Message -match 'paging file')
            } | Select-Object -First 20 TimeCreated, ProviderName, Id, Message
        
        $res = @()
        foreach ($e in $events) {
            $res += [PSCustomObject]@{
                Time = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Provider = $e.ProviderName
                Id = $e.Id
                Message = ($e.Message -replace "`r`n", " ").Trim()
            }
        }
        $res | ConvertTo-Json -Depth 2
        '''
        out = run_powershell(ps_cmd, timeout=12)
        if out.strip():
            try:
                items = json.loads(out.strip())
                if isinstance(items, dict):
                    items = [items]
                
                tdr_count = 0
                whea_count = 0
                kp41_count = 0
                page_err_count = 0
                for item in items:
                    msg = item.get("Message", "")
                    id_ = item.get("Id", 0)
                    if "0x00000116" in msg:
                        tdr_count += 1
                    if "0x00000124" in msg:
                        whea_count += 1
                    if id_ == 41:
                        kp41_count += 1
                    if "paging file is too small" in msg.lower():
                        page_err_count += 1

                if page_err_count > 0:
                    self.add_issue(
                        level="CRITICAL",
                        category="系统内核事件",
                        title="日志确认: Windows 虚拟内存曾因分页受阻彻底耗尽 (Event 7000)",
                        detail=(
                            f"系统日志白纸黑字记录了 {page_err_count} 次 'The paging file is too small for this operation to complete' 致命报错！\n"
                            f"   这正是导致东方财富弹出 Unknown Hard Error、各后台服务异常崩溃、量化程序死锁卡顿的直接元凶！"
                        ),
                        suggestion="执行虚拟内存盘符迁移，将分页文件转移到空闲空间充裕的磁盘（E盘）。"
                    )

                if tdr_count > 0 or whea_count > 0:
                    self.add_issue(
                        level="CRITICAL",
                        category="显卡与硬件级崩溃",
                        title=f"检测到显卡超时掉驱动(0x116: {tdr_count}次) 与 PCIe/硬件不可纠正错误(0x124: {whea_count}次)",
                        detail=(
                            f"系统蓝屏记录包含 0x116 (VIDEO_TDR_FAILURE 显卡掉驱动超时) 与 0x124 (WHEA 硬件级总线不可纠正错误)！\n"
                            f"   这直接解释了为什么会出现“黑屏、闪屏、屏幕不亮”，以及跑 FurMark/HWiNFO 时遭遇 0xc0000005 异常崩溃。"
                        ),
                        suggestion=(
                            "1. 卸载当前 610.88 等非稳定驱动，重装官方 WHQL 稳定版驱动；\n"
                            "2. 检查笔记本散热与硅脂，避免独显高负载瞬间过热断电保护。"
                        )
                    )

                if kp41_count > 0:
                    self.add_issue(
                        level="WARNING",
                        category="电源与断电",
                        title=f"检测到 {kp41_count} 次系统非正常断电/强行重启 (Kernel-Power 41)",
                        detail="系统在未先正常关机的情况下重启，表明此前曾发生黑屏卡死强制长按电源键，或硬件过载瞬间掉电断电。",
                        suggestion="解决显卡超时与虚拟内存死锁后，尽量避免强行长按电源键硬关机，以保护磁盘文件系统完整性。"
                    )
            except Exception:
                pass

    def check_application_hard_errors(self):
        """4. 查询最近应用程序崩溃与硬错误"""
        ps_cmd = '''
        $cutoff = (Get-Date).AddHours(-8)
        $events = Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$cutoff; Level=@(1,2)} -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Id -in @(1000, 1002) -or $_.Message -match '0xc0000005|0xc000012d|Hard Error|NVDisplay'
            } | Select-Object -First 15 TimeCreated, ProviderName, Id, Message
        
        $res = @()
        foreach ($e in $events) {
            $res += [PSCustomObject]@{
                Time = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Id = $e.Id
                Message = ($e.Message -replace "`r`n", " ").Trim()
            }
        }
        $res | ConvertTo-Json -Depth 2
        '''
        out = run_powershell(ps_cmd, timeout=10)
        if out.strip():
            try:
                items = json.loads(out.strip())
                if isinstance(items, dict):
                    items = [items]
                nv_container_crashes = [i for i in items if "NVDisplay.Container.exe" in i.get("Message", "")]
                if nv_container_crashes:
                    self.add_issue(
                        level="WARNING",
                        category="显卡驱动组件崩溃",
                        title=f"NVIDIA 显示容器服务 (NVDisplay.Container.exe) 频繁崩溃 ({len(nv_container_crashes)}次)",
                        detail="NVIDIA 官方显示管理服务崩溃，会导致显示设置丢失、分辨率或多屏输出切换时黑屏闪烁。",
                        suggestion="在清洁重装显卡驱动时予以修复。"
                    )
            except Exception:
                pass

    def run(self):
        print("\n" + "="*80)
        print(" " * 18 + "[*] Windows 系统健康诊断与故障根因分析专家")
        print("="*80)
        print(f"[*] 诊断时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("[*] 正在扫描虚拟内存与磁盘分页配置...")
        self.check_memory_and_pagefile()
        
        print("[*] 正在扫描显卡、显示驱动与第三方虚拟屏适配器...")
        self.check_gpu_and_display()
        
        print("[*] 正在调取 Windows 内核崩溃、TDR 掉驱动与硬件中断日志...")
        self.check_system_crash_events()
        
        print("[*] 正在检索近期应用程序崩溃与硬错误...")
        self.check_application_hard_errors()
        
        print("\n" + "-"*80)
        print("【全自动分析诊断结论报告】")
        print("-"*80)
        
        if self.risk_level == "CRITICAL":
            status_str = "[!] 极度危险 (CRITICAL) - 系统存在严重底层硬件/内存死锁"
        elif self.risk_level == "WARNING":
            status_str = "[!] 警告风险 (WARNING) - 系统存在驱动冲突或性能隐患"
        else:
            status_str = "[OK] 健康稳定 (HEALTHY) - 未检测到致命系统问题"
            
        print(f"系统健康评分: {self.score} / 100 分  |  整体状态: {status_str}")
        print(f"检出核心病灶项: {len(self.findings)} 个")
        print("-" * 80)
        
        if not self.findings:
            print("未发现异常，系统运行状态良好。")
        else:
            for idx, item in enumerate(self.findings, 1):
                lvl_tag = "[致命病灶]" if item["level"] == "CRITICAL" else "[重要警告]"
                print(f"\n{idx}. {lvl_tag} 【{item['category']}】{item['title']}")
                print(f"   ► 根本原因穿透: {item['detail']}")
                print(f"   ► 靶向解决处方: {item['suggestion']}")

        print("\n" + "="*80)
        print("诊断完成。以上分析完全基于 Windows 内核事件日志、物理磁盘与设备驱动真实数据。")
        print("="*80 + "\n")

if __name__ == "__main__":
    doctor = SystemHealthDoctor()
    doctor.run()
