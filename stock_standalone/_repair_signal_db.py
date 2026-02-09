# -*- coding: utf-8 -*-
"""
修复 signal_strategy.db 数据库

策略：
1. 尝试强制 checkpoint 将 WAL 合并到主数据库
2. 如果失败，尝试使用 .recover 命令恢复数据
3. 创建备份以防万一
"""
import sqlite3
import shutil
import os
from datetime import datetime

DB_PATH = "signal_strategy.db"
BACKUP_PATH = f"signal_strategy_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

def repair_database():
    print(f"=== 开始修复 {DB_PATH} ===")
    
    # Step 1: 备份原始文件
    print(f"\n[1] 备份原始数据库...")
    try:
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"    ✓ 备份已创建: {BACKUP_PATH}")
        
        if os.path.exists(f"{DB_PATH}-wal"):
            shutil.copy2(f"{DB_PATH}-wal", f"{BACKUP_PATH}-wal")
            print(f"    ✓ WAL 备份已创建")
        if os.path.exists(f"{DB_PATH}-shm"):
            shutil.copy2(f"{DB_PATH}-shm", f"{BACKUP_PATH}-shm")
            print(f"    ✓ SHM 备份已创建")
    except Exception as e:
        print(f"    ✗ 备份失败: {e}")
        return False
    
    # Step 2: 尝试打开并 checkpoint
    print(f"\n[2] 尝试 WAL checkpoint...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print("    ✓ WAL checkpoint 成功")
        
        # 验证完整性
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] == "ok":
            print("    ✓ 数据库完整性检查通过")
            conn.close()
            return True
        else:
            print(f"    ✗ 完整性检查失败: {result}")
            conn.close()
    except Exception as e:
        print(f"    ✗ Checkpoint 失败: {e}")
    
    # Step 3: 尝试 recover 命令（需要 sqlite3 命令行工具）
    print(f"\n[3] 尝试 .recover 恢复...")
    try:
        import subprocess
        
        # 创建恢复后的新数据库文件
        recovered_path = "signal_strategy_recovered.db"
        
        # 使用 sqlite3 命令行的 .recover 命令
        cmd = f'sqlite3 {DB_PATH} ".recover" | sqlite3 {recovered_path}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        if os.path.exists(recovered_path) and os.path.getsize(recovered_path) > 0:
            # 验证恢复的数据库
            conn = sqlite3.connect(recovered_path)
            check = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            
            if check[0] == "ok":
                print(f"    ✓ 恢复成功: {recovered_path}")
                print(f"    → 请手动将 {recovered_path} 替换为 {DB_PATH}")
                return True
            else:
                print(f"    ✗ 恢复的数据库完整性检查失败")
        else:
            print(f"    ✗ .recover 命令未生成有效文件")
            if result.stderr:
                print(f"    错误信息: {result.stderr[:200]}")
    except Exception as e:
        print(f"    ✗ .recover 失败: {e}")
    
    # Step 4: 最后手段 - 导出并重建
    print(f"\n[4] 尝试导出可读取的表数据...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"    发现 {len(tables)} 个表: {[t[0] for t in tables]}")
        
        # 尝试读取每个表
        for table in tables:
            table_name = table[0]
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"    - {table_name}: {count} 条记录")
            except Exception as te:
                print(f"    - {table_name}: 读取失败 ({te})")
        
        conn.close()
    except Exception as e:
        print(f"    ✗ 表探索失败: {e}")
    
    print("\n=== 修复尝试完成 ===")
    return False

if __name__ == "__main__":
    success = repair_database()
    if success:
        print("\n✓ 数据库修复成功!")
    else:
        print("\n✗ 数据库修复失败，可能需要重建。")
        print(f"  备份文件位于: {BACKUP_PATH}")
