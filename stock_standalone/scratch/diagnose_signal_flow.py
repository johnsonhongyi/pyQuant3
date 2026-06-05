# -*- coding: utf-8 -*-
import os
import sys
import json
import time
from datetime import datetime

# 将项目根目录加入模块搜索路径，保证能正常引入 cct 等
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 强制将标准输出和标准错误输出流设为支持替换错误字符的 utf-8 模式，防止 Windows 终端崩溃
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

def get_app_root():
    # 兼容打包环境与开发环境的路径查找
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return project_root

def diagnose():
    print("=" * 80)
    print("[HBeat] 交易系统实时数据信号与后台流程自检诊断工具")
    print("=" * 80)
    
    app_root = get_app_root()
    logs_dir = os.path.join(app_root, "logs")
    trace_path = os.path.join(logs_dir, "trading_kernel_trace.jsonl")
    log_path = os.path.join(logs_dir, "instock_tk.log")
    if not os.path.exists(log_path):
        log_path = os.path.join(app_root, "instock_tk.log")
    
    # 1. 基础环境与配置检查
    print(f"[*] 项目根目录: {project_root}")
    print(f"[*] 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 2. 交易流记录 (trading_kernel_trace.jsonl) 诊断
    print("\n[+] 诊断交易流水痕迹 (trading_kernel_trace.jsonl)...")
    if not os.path.exists(trace_path):
        print("    [!] 未检测到交易流水痕迹文件，这可能表明自本系统启动以来尚未触发任何信号或尚未写盘。")
    else:
        file_size = os.path.getsize(trace_path)
        mtime = os.path.getmtime(trace_path)
        last_update = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"    - 文件路径: {trace_path}")
        print(f"    - 文件大小: {file_size / 1024:.2f} KB")
        print(f"    - 最近写入时间: {last_update}")
        
        # 读取最后 10 行记录分析
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            valid_lines = [l.strip() for l in lines if l.strip()]
            total_records = len(valid_lines)
            print(f"    - 历史总流水记录数: {total_records} 条")
            
            print("    - 最近 5 条物理流水信号明细:")
            print("      " + "-" * 70)
            for idx, line in enumerate(valid_lines[-5:]):
                try:
                    data = json.loads(line)
                    created_at = data.get("journal_ts", "") or data.get("trade_date", "")
                    action = data.get("action", "") or data.get("kernel_action", "")
                    code = data.get("code", "")
                    name = data.get("name", "")
                    status = data.get("status", "")
                    detail = data.get("detail", "")
                    print(f"      [{idx+1}] 时间: {created_at} | 股票: {code}({name}) | 动作: {action} | 状态: {status} | 详情: {detail}")
                except Exception as parse_err:
                    print(f"      [!] 无法解析流水行: {parse_err}")
            print("      " + "-" * 70)
        except Exception as e:
            print(f"    [!] 读取交易流水文件失败: {e}")
            
    # 3. 运行日志 (instock_tk.log) 诊断
    print("\n[+] 诊断系统后台实时心跳运行日志 (instock_tk.log)...")
    if not os.path.exists(log_path):
        print("    [!] 未检测到主运行日志文件。")
    else:
        file_size = os.path.getsize(log_path)
        mtime = os.path.getmtime(log_path)
        last_update = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"    - 日志大小: {file_size / 1024 / 1024:.2f} MB")
        print(f"    - 最近写入时间: {last_update}")
        
        try:
            # 扫描最后 3000 行，提取最近的心跳和拦截日志
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                log_lines = f.readlines()[-3000:]
            
            heartbeats = []
            bg_kernels = []
            warnings = []
            
            for line in log_lines:
                line_str = line.strip()
                if "[交易内核心跳]" in line_str:
                    heartbeats.append(line_str)
                elif "[BgKernel]" in line_str:
                    bg_kernels.append(line_str)
                elif "WARNING" in line_str or "ERROR" in line_str:
                    if any(k in line_str for k in ["BgKernel", "Sync", "Panel", "Detector"]):
                        warnings.append(line_str)
            
            print(f"    - 检测到最近运行心跳次数: {len(heartbeats)} 次")
            print(f"    - 检测到最近交易内核信号判定次数: {len(bg_kernels)} 次")
            
            if heartbeats:
                print("    - 最新 3 条系统内核心跳日志:")
                for h in heartbeats[-3:]:
                    print(f"      {h}")
            else:
                print("    [!] 过去 3000 行日志中未发现 [交易内核心跳] 标记，请确认系统是否已在交易活跃期启动。")
                
            if bg_kernels:
                print("    - 最新 3 条交易决策与拦截日志:")
                for b in bg_kernels[-3:]:
                    print(f"      {b}")
            else:
                print("    [-] 过去 3000 行日志中未发现 [BgKernel] 决策动作日志，表明决策流尚无待执行或被拦截的股票信号。")
                
            if warnings:
                print("    - 最近核心 warning/error 异常检测(前5条):")
                for w in warnings[:5]:
                    print(f"      {w}")
            else:
                print("    [+] 核心模块运行纯净，无报警或错误日志。")
                
        except Exception as e:
            print(f"    [!] 扫描系统日志失败: {e}")
            
    print("=" * 80)
    print("[HBeat] 自检完成。提示：系统必须在主窗口运行且在交易期内（或手动启动行情更新）才会产生持续心跳与决策信号。")
    print("=" * 80)

if __name__ == "__main__":
    diagnose()
