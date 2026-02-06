
import ast
import sys

filename = r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\JohnsonUtil\commonTips.py'

with open(filename, 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read(), filename)

for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            print(f"import {alias.name}")
    elif isinstance(node, ast.ImportFrom):
        module = node.module if node.module else ''
        for alias in node.names:
            print(f"from {module} import {alias.name}")
