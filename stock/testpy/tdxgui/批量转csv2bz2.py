import os
import pandas as pd

# 获取当前目录
current_dir = os.getcwd()

# 遍历当前目录所有文件
for filename in os.listdir(current_dir):
    if filename.lower().endswith(".csv") and not filename.lower().endswith(".bz2"):
        csv_path = os.path.join(current_dir, filename)
        bz2_path = os.path.join(current_dir, filename + ".bz2")

        # 读取 CSV
        df = pd.read_csv(csv_path)

        # 保存为 bz2 压缩
        df.to_csv(bz2_path, index=False, compression="bz2")

        print(f"Converted {filename} -> {bz2_path}")
