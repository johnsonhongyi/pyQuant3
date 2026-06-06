# -*- coding: utf-8 -*-
"""
生产环境配置文件一键备份与保护助手 (Windows 兼容版)
备份当前运行环境下的所有核心配置文件及变动的用户数据到当前目录下的 BackConfig 文件夹中。
支持历史时间戳备份，提供完整的目录结构恢复指引。
"""

import os
import sys
import time
import shutil
from datetime import datetime

# 排除扫描的无关文件夹，防止备份冗余文件
EXCLUDE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", "build", "dist", "venv", 
    "env", ".pytest_cache", ".agents", "BackConfig", "artifacts", 
    ".nuitka_cache", ".nuitka", "scratch", "test_vs_clang.build", 
    ".pytest_temp", "JohnsonUtil", "JSONData", "jupyterAlgo","archives"
}

# 关注的配置文件类型
CONFIG_EXTENSIONS = {".json", ".conf", ".ini", ".xlsx", ".db", ".db-wal", ".db-shm", ".json.gz", ".gz", ".jsonl"}

def get_app_root() -> str:
    """获取程序所在的绝对根目录"""
    try:
        from sys_utils import get_app_root as sys_get_app_root
        return sys_get_app_root()
    except Exception:
        # Fallback 兜底
        is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ
        if getattr(sys, "frozen", False) or is_nuitka:
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            # 源码开发环境下，以当前脚本所在目录为准
            return os.path.dirname(os.path.abspath(__file__))

def main():
    print("==================================================")
    print("   [Backup] 生产环境配置文件一键备份与安全保护助手")
    print("==================================================")
    
    app_root = get_app_root()
    print(f"[ROOT] 运行根目录定位: {app_root}")
    
    # 1. 创建备份目标主目录及本次备份的时间戳文件夹
    back_config_root = os.path.join(app_root, "BackConfig")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_backup_dir = os.path.join(back_config_root, f"Backup_{timestamp}")
    
    try:
        os.makedirs(current_backup_dir, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] 创建备份目录失败: {e}")
        return

    # 2. 从 sys_utils 中导入 RESOURCE_MAP 尝试精准匹配
    resource_map_files = []
    try:
        sys.path.append(app_root)
        from sys_utils import RESOURCE_MAP
        for key, info in RESOURCE_MAP.items():
            dst_rel = info.get("dst")
            if dst_rel:
                resource_map_files.append(dst_rel)
    except Exception as e:
        print(f"[WARNING] 未能导入 sys_utils.RESOURCE_MAP ({e})，将仅执行全盘配置文件扫描过滤。")

    # 3. 扫描根目录下所有符合条件的物理配置文件
    backup_list = []
    
    # 首先添加 RESOURCE_MAP 里存在的物理文件 (只保留在排除列表外的)
    for rel_path in resource_map_files:
        full_path = os.path.join(app_root, rel_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            parts = rel_path.replace('\\', '/').split('/')
            if not any(p in EXCLUDE_DIRS for p in parts):
                backup_list.append(rel_path)
            
    # 全盘扫描根目录下的配置文件
    for root, dirs, files in os.walk(app_root):
        # 过滤排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".nuitka")]
        
        # 额外安全性检查：如果当前 root 路径中包含任何被排除目录，直接跳过整个目录
        root_parts = os.path.relpath(root, app_root).replace('\\', '/').split('/')
        if any(p in EXCLUDE_DIRS for p in root_parts):
            continue
            
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if file.lower().endswith(".json.gz"):
                ext = ".json.gz"
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, app_root)
            rel_path_norm = rel_path.replace('\\', '/')
            
            # 如果是关注的配置文件扩展名/日志文件，或者位于 log/logs 文件夹下，则予以备份
            is_config_or_log = ext in CONFIG_EXTENSIONS or ext == ".log"
            is_log_dir = rel_path_norm.startswith("log/") or rel_path_norm.startswith("logs/")
            
            if is_config_or_log or is_log_dir:
                # 避免重复加入
                if rel_path not in backup_list:
                    backup_list.append(rel_path)

    # 4. 执行备份拷贝
    success_count = 0
    fail_count = 0
    
    print(f"\n[INFO] 正在扫描并备份文件至: BackConfig\\Backup_{timestamp} ...")
    print("-" * 60)
    
    for rel_path in sorted(backup_list):
        src_file = os.path.join(app_root, rel_path)
        dst_file = os.path.join(current_backup_dir, rel_path)
        
        try:
            # 自动创建目标子目录
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            # 物理拷贝并保持时间戳
            shutil.copy2(src_file, dst_file)
            print(f"[OK] 已备份: {rel_path} ({os.path.getsize(src_file)} 字节)")
            success_count += 1
        except Exception as ex:
            print(f"[ERROR] 备份失败: {rel_path} : {ex}")
            fail_count += 1

    # 5. 写入一键还原说明 readme.txt
    readme_path = os.path.join(current_backup_dir, "恢复指引_README.txt")
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("==================================================\n")
            f.write(f" 备份恢复指南 (创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
            f.write("==================================================\n\n")
            f.write("要一键恢复此备份的配置，请执行以下步骤：\n")
            f.write("1. 将当前文件夹内的所有文件和子目录（排除此 README 文件）拷贝。\n")
            f.write(f"2. 粘贴并覆盖到你的运行根目录：\n   {app_root}\n")
            f.write("3. 重启程序即可加载备份时的运行状态和配置。\n\n")
            f.write(f"本次备份统计：成功 {success_count} 个，失败 {fail_count} 个。\n")
    except:
        pass

    print("-" * 60)
    print(f"[INFO] 备份执行完成！")
    print(f"[INFO] 统计数据: 成功备份 {success_count} 个文件，失败 {fail_count} 个。")
    print(f"[INFO] 备份存储路径: {current_backup_dir}")
    print(f"[INFO] 恢复指南已自动写入：{readme_path}")
    print("==================================================")

if __name__ == "__main__":
    main()
