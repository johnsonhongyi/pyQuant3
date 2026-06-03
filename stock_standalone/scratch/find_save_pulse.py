with open('instock_MonitorTK.py', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()
for i, line in enumerate(lines):
    if 'save_daily_pulse' in line or 'daily_reports' in line:
        safe_line = line.encode('ascii', 'ignore').decode('ascii')
        print(f"{i+1}: {safe_line}")
