import shutil
import os

files_to_sync = [
    "multi_period_strategies.json",
    "indicator_help_custom.json"
]

base_src = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\config"
target_dirs = [
    r"D:\JohnsonProgram\instockMonitorTK\config",
    r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\dist\config",
    r"D:\JohnsonProgram\instockMonitorTK\0719\config"
]

for fname in files_to_sync:
    src_file = os.path.join(base_src, fname)
    if not os.path.exists(src_file):
        continue
    for tdir in target_dirs:
        if os.path.exists(tdir):
            dst_file = os.path.join(tdir, fname)
            shutil.copy2(src_file, dst_file)
            print(f"Copied {fname} to {dst_file}")
