# -*- coding: utf-8 -*-
"""
批量替换 trading_hub.py 中的 sqlite3.connect() 为 SQLiteConnectionManager
"""
import re

def migrate_sqlite_connections(file_path):
    """将 sqlite3.connect() 替换为 SQLiteConnectionManager"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换模式:
    # conn = sqlite3.connect(self.signal_db)
    # 替换为:
    # mgr = SQLiteConnectionManager.get_instance(self.signal_db)
    # conn = mgr.get_connection()
    
    # 模式1: conn = sqlite3.connect(self.signal_db)
    pattern1 = r'(\s+)conn = sqlite3\.connect\(self\.signal_db\)'
    replacement1 = r'\1mgr = SQLiteConnectionManager.get_instance(self.signal_db)\n\1conn = mgr.get_connection()'
    content = re.sub(pattern1, replacement1, content)
    
    # 模式2: conn = sqlite3.connect(self.trading_db)
    pattern2 = r'(\s+)conn = sqlite3\.connect\(self\.trading_db\)'
    replacement2 = r'\1mgr = SQLiteConnectionManager.get_instance(self.trading_db)\n\1conn = mgr.get_connection()'
    content = re.sub(pattern2, replacement2, content)
    
    # 模式3: conn = sqlite3.connect(self.signal_db, timeout=5)
    pattern3 = r'(\s+)conn = sqlite3\.connect\(self\.signal_db,\s*timeout=\d+\)'
    replacement3 = r'\1mgr = SQLiteConnectionManager.get_instance(self.signal_db)\n\1conn = mgr.get_connection()'
    content = re.sub(pattern3, replacement3, content)
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已完成 {file_path} 的 SQLite 连接迁移")
    print("替换统计:")
    print(f"  - signal_db 连接: {len(re.findall(pattern1, content))}")
    print(f"  - trading_db 连接: {len(re.findall(pattern2, content))}")
    print(f"  - 带超时的连接: {len(re.findall(pattern3, content))}")

if __name__ == "__main__":
    file_path = "trading_hub.py"
    migrate_sqlite_connections(file_path)
