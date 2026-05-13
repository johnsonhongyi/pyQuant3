import sys
import time
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt

app = QApplication(sys.argv)
table = QTableWidget(1000, 8)
for r in range(1000):
    for c in range(8):
        table.setItem(r, c, QTableWidgetItem(f"item {r}-{c}"))

# Method: takeItem and setItem
start = time.time()
rows_data = []
for r in range(table.rowCount()):
    items = [table.takeItem(r, c) for c in range(table.columnCount())]
    rows_data.append((r, items))

rows_data.sort(key=lambda x: x[0], reverse=True)

for r, (val, items) in enumerate(rows_data):
    for c, item in enumerate(items):
        if item:
            table.setItem(r, c, item)

print(f"Time: {time.time() - start:.4f}s")
