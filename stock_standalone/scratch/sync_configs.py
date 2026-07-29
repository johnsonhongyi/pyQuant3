import shutil
import os

src = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\config\multi_period_strategies.json"
targets = [
    r"D:\JohnsonProgram\instockMonitorTK\config\multi_period_strategies.json",
    r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\dist\config\multi_period_strategies.json",
    r"D:\JohnsonProgram\instockMonitorTK\0719\config\multi_period_strategies.json"
]

for t in targets:
    if os.path.exists(os.path.dirname(t)):
        shutil.copy2(src, t)
        print(f"Copied to {t}")
