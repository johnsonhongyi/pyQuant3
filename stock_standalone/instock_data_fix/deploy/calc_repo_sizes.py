#!/usr/bin/env python3
import os
import subprocess

def du(path):
    p = subprocess.run(['du', '-sb', path], capture_output=True, text=True)
    return int(p.stdout.split()[0]) if p.returncode == 0 else 0

def fmt(b):
    for u in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f"{b:.2f} {u}"
        b /= 1024
    return f"{b:.2f} TB"

# 1. 纳管的代码文件
tracked = subprocess.run(['git', '-C', '/data/InStock', 'ls-files'], capture_output=True, text=True).stdout.splitlines()
tracked_bytes = sum(os.path.getsize(os.path.join('/data/InStock', f)) for f in tracked if os.path.exists(os.path.join('/data/InStock', f)))
git_dir_bytes = du('/data/InStock/.git')

# 2. 忽略的大文件与目录
forwardp_b = du('/data/InStock/instock/forwardp')
cache_b = du('/data/InStock/instock/cache')
log_b = du('/data/InStock/instock/log')
temp_b = du('/data/InStock/instock/core/temp')
strategy_b = du('/data/InStock/instock/core/strategy')
zip_b = sum(os.path.getsize(os.path.join('/data/InStock/instock/core', f)) for f in ['stock-master.zip', 'crawling-250218.zip'] if os.path.exists(os.path.join('/data/InStock/instock/core', f)))

print("=== 纳管代码资产统计 (Tracked Code Assets) ===")
print(f"代码文件总数: {len(tracked)} 个")
print(f"纯源码与资源净体积: {fmt(tracked_bytes)} ({tracked_bytes:,} 字节)")
print(f"Git 仓库元数据 (.git): {fmt(git_dir_bytes)} ({git_dir_bytes:,} 字节)")
print(f"代码+版本库合计: {fmt(tracked_bytes + git_dir_bytes)}")
print()
print("=== 忽略的数据、日志与大文件统计 (Ignored Large Data & Logs) ===")
print(f"通达信市场行情日K (instock/forwardp): {fmt(forwardp_b)} ({forwardp_b:,} 字节)")
print(f"持久化运行时缓存与锁 (instock/cache): {fmt(cache_b)} ({cache_b:,} 字节)")
print(f"系统运行与调优日志 (instock/log): {fmt(log_b)} ({log_b:,} 字节)")
print(f"历史备份压缩包 (*.zip): {fmt(zip_b)} ({zip_b:,} 字节)")
print(f"历史临时子项目 (instock/core/temp): {fmt(temp_b)} ({temp_b:,} 字节)")
print(f"外部策略挂载 (instock/core/strategy): {fmt(strategy_b)} ({strategy_b:,} 字节)")
total_ignored = forwardp_b + cache_b + log_b + temp_b + strategy_b + zip_b
print(f"忽略的大文件与数据合计: {fmt(total_ignored)} ({total_ignored:,} 字节)")
