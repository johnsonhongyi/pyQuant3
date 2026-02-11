# -*- coding: utf-8 -*-
"""
移除 trading_hub.py 中所有的 conn.close() 调用
因为使用 SQLiteConnectionManager 时不应该手动关闭连接
"""
import re

def remove_conn_close(file_path):
    """移除所有 conn.close() 调用"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified_lines = []
    removed_count = 0
    
    for i, line in enumerate(lines, 1):
        # 检查是否包含 conn.close()
        if 'conn.close()' in line and not line.strip().startswith('#'):
            # 如果这一行只有 conn.close() 和空白,则完全删除
            if line.strip() == 'conn.close()':
                removed_count += 1
                print(f"  第 {i} 行: 删除 '{line.strip()}'")
                continue  # 跳过这一行
            # 如果有其他内容,只移除 conn.close() 部分
            else:
                new_line = line.replace('conn.close()', '').strip()
                if new_line:
                    modified_lines.append(new_line + '\n')
                    removed_count += 1
                    print(f"  第 {i} 行: 修改为 '{new_line}'")
                else:
                    removed_count += 1
                    print(f"  第 {i} 行: 删除 '{line.strip()}'")
                    continue
        else:
            modified_lines.append(line)
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(modified_lines)
    
    print(f"\n✅ 已完成 {file_path} 的 conn.close() 移除")
    print(f"总共移除: {removed_count} 处")

if __name__ == "__main__":
    file_path = "trading_hub.py"
    remove_conn_close(file_path)
