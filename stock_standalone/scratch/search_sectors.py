import re

with open('bidding_momentum_detector.py', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()
for i, line in enumerate(lines):
    if 'active_sectors' in line or 'get_active_sectors' in line or 'active_sector' in line:
        safe_line = line.encode('ascii', 'ignore').decode('ascii')
        print(f"{i+1}: {safe_line}")
