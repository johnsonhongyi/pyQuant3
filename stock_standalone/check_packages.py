#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re

# 大包候选
candidates = {
    'bokeh': 78.4,
    'scipy': 64.1,
    'plotly': 60.9,
    'statsmodels': 38.9,
    'astropy': 32.0,
    'matplotlib': 20.0,
    'IPython': 4.1
}

# 检查代码中是否真的使用了这些包
def check_usage(package_name):
    patterns = [
        f'import {package_name}',
        f'from {package_name}',
    ]
    
    for root, dirs, filenames in os.walk('.'):
        # 跳过build和__pycache__目录
        dirs[:] = [d for d in dirs if d not in ['build', '__pycache__', '.git', 'archives']]
        
        for file in filenames:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for pattern in patterns:
                            if re.search(pattern, content):
                                return True, filepath
                except:
                    pass
    return False, None

print('Package Usage Analysis:')
print('-' * 70)

total_unused = 0
unused_list = []

for pkg, size in sorted(candidates.items(), key=lambda x: x[1], reverse=True):
    used, filepath = check_usage(pkg)
    if used:
        print(f'{pkg:20} {size:8.1f} MB   USED')
    else:
        print(f'{pkg:20} {size:8.1f} MB   UNUSED   [可删除]')
        total_unused += size
        unused_list.append(pkg)

print('-' * 70)
print(f'Total unused (MB): {total_unused:.1f}')
print('\nUnused packages:')
for pkg in unused_list:
    print(f'  pip uninstall -y {pkg}')
