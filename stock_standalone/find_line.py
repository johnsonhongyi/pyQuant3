
filename = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\instock_MonitorTK.py"
with open(filename, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if "def update_tree(self):" in line:
            print(f"Found at line {i}: {line.strip()}")
