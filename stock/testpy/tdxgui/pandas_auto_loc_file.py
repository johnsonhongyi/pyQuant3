import os
import re
import pandas as pd

# 要处理的单个 Python 文件
target_file = r"D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\testpy\tdxgui\异动联动.py"

# 匹配链式赋值 df["col"][...] = value
chain_assign_pattern = re.compile(r'(\w+)\[["\'](\w+)["\']\]\[([^\]]+)\]\s*=\s*(.+)')
# 匹配简单赋值 df["col"] = value
simple_assign_pattern = re.compile(r'(\w+)\[["\'](\w+)["\']\]\s*=\s*(.+)')

# 已知 DataFrame 变量名（可手动维护）
known_dataframes = {"loaded_df", "temp_df"}

def is_dataframe_variable(var_name):
    """检查变量是否是 DataFrame"""
    return var_name in known_dataframes

def dry_run_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modifications = []

    for i, line in enumerate(lines, start=1):
        stripped_line = line.lstrip()
        indent = line[:len(line)-len(stripped_line)]  # 保留原始缩进

        # 跳过注释行
        if stripped_line.startswith("#"):
            continue

        # 链式赋值
        m = chain_assign_pattern.search(line)
        if m:
            df_var, col_name, row_indexer, value_expr = m.groups()
            if is_dataframe_variable(df_var):
                new_line = f'{indent}{df_var}.loc[{row_indexer}, "{col_name}"] = {value_expr}  # 改写链式赋值'
                modifications.append((i, line.rstrip(), new_line))
            continue

        # 简单赋值
        m2 = simple_assign_pattern.search(line)
        if m2:
            df_var, col_name, value_expr = m2.groups()
            if is_dataframe_variable(df_var) and ".loc" not in value_expr:
                new_line = f'{indent}{df_var}.loc[:, "{col_name}"] = {value_expr}  # 改写简单赋值'
                modifications.append((i, line.rstrip(), new_line))
            continue

    if not modifications:
        print(f"未检测到需要改写的赋值: {filepath}")
        return

    print(f"文件: {filepath}")
    for lineno, old, new in modifications:
        print(f"行 {lineno}:")
        print(f"  原始: {old}")
        print(f"  改写: {new}\n")

    # 等待用户确认
    user_input = input("是否应用以上修改？输入 'y' 确认，其他任意键退出: ").strip().lower()
    if user_input != 'y':
        print("退出，不修改文件。")
        return

    # 应用修改
    for lineno, old, new in modifications:
        lines[lineno - 1] = new + "\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ 文件已修改: {filepath}")


if __name__ == "__main__":
    if os.path.exists(target_file):
        dry_run_file(target_file)
    else:
        print(f"文件不存在: {target_file}")
