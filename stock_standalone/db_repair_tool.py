# -*- coding: utf-8 -*-
"""
独立数据库修复工具

用法: python db_repair_tool.py [database_path]

默认修复 signal_strategy.db，支持以下功能：
1. 完整性检查
2. WAL checkpoint 合并
3. 尝试 .recover 恢复
4. 表数据导出
5. 数据库重建
"""
import sqlite3
import shutil
import os
import sys
from datetime import datetime
from sys_utils import get_base_path

class DatabaseRepairTool:
    """SQLite 数据库修复工具"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.backup_path = None
        
    def run(self):
        """执行完整修复流程"""
        print(f"\n{'='*50}")
        print(f"  SQLite 数据库修复工具")
        print(f"{'='*50}")
        print(f"\n目标数据库: {self.db_path}")
        
        if not os.path.exists(self.db_path):
            print(f"✗ 文件不存在: {self.db_path}")
            return False
        
        # Step 1: 检查完整性
        if self.check_integrity():
            print("\n✓ 数据库已是健康状态，无需修复")
            return True
        
        # Step 2: 备份
        self.backup_database()
        
        # Step 3: 尝试 WAL checkpoint
        if self.try_wal_checkpoint():
            if self.check_integrity():
                print("\n✓ WAL checkpoint 后数据库恢复正常")
                return True
        
        # Step 4: 尝试 recover
        recovered_path = self.try_recover()
        if recovered_path:
            print(f"\n✓ 数据已恢复到: {recovered_path}")
            print(f"  请手动将其替换为原数据库")
            return True
        
        # Step 5: 导出可读数据并重建
        print("\n[5] 尝试导出数据并重建...")
        tables_data = self.export_tables()
        if tables_data:
            return self.rebuild_database(tables_data)
        
        print("\n✗ 所有修复方法均失败")
        print(f"  备份文件: {self.backup_path}")
        return False
    
    def check_integrity(self) -> bool:
        """检查数据库完整性"""
        print("\n[检查] 完整性检测...")
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            
            if result[0] == 'ok':
                print("  ✓ 完整性: OK")
                return True
            else:
                print(f"  ✗ 完整性: {result[0][:100]}...")
                return False
        except Exception as e:
            print(f"  ✗ 无法检查: {e}")
            return False
    
    def backup_database(self):
        """备份数据库文件"""
        print("\n[备份] 创建备份...")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = f"{self.db_path}.backup_{timestamp}"
        
        try:
            shutil.copy2(self.db_path, self.backup_path)
            print(f"  ✓ 主数据库备份: {self.backup_path}")
            
            # 备份 WAL 和 SHM
            for ext in ['-wal', '-shm']:
                src = f"{self.db_path}{ext}"
                if os.path.exists(src):
                    shutil.copy2(src, f"{self.backup_path}{ext}")
                    print(f"  ✓ {ext} 备份已创建")
        except Exception as e:
            print(f"  ✗ 备份失败: {e}")
    
    def try_wal_checkpoint(self) -> bool:
        """尝试 WAL checkpoint"""
        print("\n[修复] 尝试 WAL checkpoint...")
        wal_path = f"{self.db_path}-wal"
        
        if not os.path.exists(wal_path):
            print("  - 无 WAL 文件，跳过")
            return False
        
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            conn.close()
            print(f"  ✓ Checkpoint 结果: {result}")
            return True
        except Exception as e:
            print(f"  ✗ Checkpoint 失败: {e}")
            return False
    
    def try_recover(self) -> str:
        """尝试使用 sqlite3 .recover 命令恢复"""
        print("\n[修复] 尝试 .recover 恢复...")
        
        try:
            import subprocess
            
            recovered_path = f"{self.db_path}.recovered"
            
            # 使用 sqlite3 命令行
            cmd = f'sqlite3 "{self.db_path}" ".recover" | sqlite3 "{recovered_path}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            
            if os.path.exists(recovered_path) and os.path.getsize(recovered_path) > 0:
                # 验证恢复的数据库
                conn = sqlite3.connect(recovered_path)
                check = conn.execute("PRAGMA integrity_check").fetchone()
                conn.close()
                
                if check[0] == 'ok':
                    print(f"  ✓ 恢复成功")
                    return recovered_path
                else:
                    print(f"  ✗ 恢复的数据库仍有问题")
                    os.remove(recovered_path)
            else:
                print("  ✗ .recover 命令未生成有效文件")
                if result.stderr:
                    print(f"    错误: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ✗ 恢复失败: {e}")
        
        return ""
    
    def export_tables(self) -> dict:
        """尝试导出所有可读取的表数据"""
        print("\n[导出] 尝试读取表数据...")
        tables_data = {}
        
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row  # 方便获取列名
            cursor = conn.cursor()
            
            # 获取表列表
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            tables_info = cursor.fetchall()
            print(f"  发现 {len(tables_info)} 个表")
            
            for table_row in tables_info:
                table_name = table_row['name']
                create_sql = table_row['sql']
                
                # 跳过 sqlite 系统表
                if table_name.startswith('sqlite_'):
                    continue
                
                tables_data[table_name] = {
                    'sql': create_sql,
                    'rows': []
                }
                
                try:
                    cursor.execute(f'SELECT * FROM "{table_name}"')
                    rows = [dict(row) for row in cursor.fetchall()]
                    tables_data[table_name]['rows'] = rows
                    print(f"  ✓ {table_name}: {len(rows)} 条记录")
                except Exception as te:
                    print(f"  ✗ {table_name}: 数据读取失败，将重建空表 ({te})")
            
            conn.close()
        except Exception as e:
            print(f"  ✗ 导出阶段失败: {e}")
        
        return tables_data

    def rebuild_database(self, tables_data: dict) -> bool:
        """重建数据库"""
        print("\n[重建] 创建新数据库...")
        
        new_path = f"{self.db_path}.new"
        if os.path.exists(new_path):
            os.remove(new_path)
            
        try:
            conn = sqlite3.connect(new_path)
            cursor = conn.cursor()
            
            for table_name, data in tables_data.items():
                create_sql = data['sql']
                rows = data['rows']
                
                if not create_sql:
                    continue
                
                try:
                    # 使用原始 SQL 创建表
                    cursor.execute(create_sql)
                    
                    # 插入数据
                    if rows:
                        cols = list(rows[0].keys())
                        placeholders = ', '.join(['?' for _ in cols])
                        # 构建 INSERT 语句
                        col_names = ', '.join([f'"{c}"' for c in cols])
                        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'
                        
                        # 转换并插入
                        vals = [tuple(r[c] for c in cols) for r in rows]
                        cursor.executemany(insert_sql, vals)
                    
                    print(f"  ✓ {table_name}: 已重建 ({len(rows)} 条)")
                except Exception as te:
                    print(f"  ✗ {table_name}: 重建失败 ({te})")
            
            conn.commit()
            conn.close()
            
            print(f"\n✓ 新数据库已就绪: {new_path}")
            
            # Step 6: 自动替换 (如果成功)
            print("\n[替换] 正在替换原始数据库...")
            try:
                # 已经有备份了，直接替换
                if os.path.exists(self.db_path):
                    # 再次通过重命名备份以防万一
                    final_backup = f"{self.db_path}.old_{datetime.now().strftime('%H%M%S')}"
                    os.rename(self.db_path, final_backup)
                
                os.rename(new_path, self.db_path)
                print(f"  ✓ 已替换原始文件: {self.db_path}")
                return True
            except Exception as re:
                print(f"  ✗ 替换失败: {re}")
                print(f"    请手动将 {new_path} 替换为 {self.db_path}")
                return True # 依然算成功，因为新文件已经生成
                
        except Exception as e:
            print(f"  ✗ 重建阶段失败: {e}")
            if os.path.exists(new_path):
                os.remove(new_path)
            return False


def main():
    # 默认目标数据库
    default_db = "signal_strategy.db"
    
    if len(sys.argv) > 1:
        target_db = sys.argv[1]
    else:
        target_db = default_db
    
    # 如果是相对路径，转换为绝对路径
    if not os.path.isabs(target_db):
        target_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), target_db)
    
    tool = DatabaseRepairTool(target_db)
    success = tool.run()
    
    print(f"\n{'='*50}")
    if success:
        print("  修复完成!")
    else:
        print("  修复失败，请手动处理")
    print(f"{'='*50}\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
