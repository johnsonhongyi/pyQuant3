import psutil
import subprocess
import datetime
import os

# ----------------------------
# 配置参数
# ----------------------------
MEMORY_THRESHOLD_MB = 500  # 内存占用超过多少 MB 视为高占用
EMPTY_STANDBY_PATH = r"C:\Tools\EmptyStandbyList.exe"  # 空闲缓存释放工具路径
LOG_FILE = r"C:\Temp\memory_opt_log.txt"

# ----------------------------
# 记录日志函数
# ----------------------------
def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}")

# ----------------------------
# 1. 查询内存占用高的进程
# ----------------------------
def get_high_memory_processes(threshold_mb=MEMORY_THRESHOLD_MB):
    high_mem = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info', 'create_time']):
        try:
            mem_mb = p.info['memory_info'].rss / 1024 / 1024
            if mem_mb >= threshold_mb:
                high_mem.append({
                    'pid': p.info['pid'],
                    'name': p.info['name'],
                    'mem_mb': mem_mb,
                    'start_time': datetime.datetime.fromtimestamp(p.info['create_time']).strftime("%Y-%m-%d %H:%M:%S")
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(high_mem, key=lambda x: x['mem_mb'], reverse=True)

# ----------------------------
# 2. 可选：结束高占用不常用进程
# ----------------------------
def terminate_process(pid, name):
    try:
        p = psutil.Process(pid)
        p.terminate()
        log(f"结束进程: {name} (PID: {pid})")
    except Exception as e:
        log(f"无法结束进程: {name} (PID: {pid}) -> {e}")

# ----------------------------
# 3. 释放 Standby / Cache 内存
# ----------------------------
def release_standby_memory():
    if os.path.exists(EMPTY_STANDBY_PATH):
        try:
            subprocess.run([EMPTY_STANDBY_PATH, "standbylist"], check=True)
            log("释放 Standby 内存完成")
        except Exception as e:
            log(f"释放 Standby 内存失败: {e}")
    else:
        log("EmptyStandbyList.exe 未找到")

# ----------------------------
# 4. 主函数
# ----------------------------
def main():
    log("=== 内存优化开始 ===")
    
    # 查询高占用进程
    high_mem_procs = get_high_memory_processes()
    if high_mem_procs:
        log("高内存占用进程:")
        for p in high_mem_procs:
            log(f"  {p['name']} (PID: {p['pid']}), 内存: {p['mem_mb']:.2f} MB, 启动: {p['start_time']}")
            # 可自动结束低频使用进程（谨慎打开）
            # terminate_process(p['pid'], p['name'])
    else:
        log("暂无高占用进程")
    
    # 释放系统缓存
    release_standby_memory()
    
    log("=== 内存优化结束 ===\n")

if __name__ == "__main__":
    main()
