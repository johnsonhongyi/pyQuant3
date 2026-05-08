with open("instock_MonitorTK.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if ".selector" in line or "self.selector" in line or "selector =" in line:
            print(f"Line {idx+1}: {line.strip()}")
