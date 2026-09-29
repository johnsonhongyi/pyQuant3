"""The independent IPO window receives keyboard row linkage."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTableWidgetItem

from tools.run_ipo_learning_console import StandaloneLearningWindow


def test_outcome_up_down_reaches_standalone_window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    linked = []
    monkeypatch.setattr(
        StandaloneLearningWindow, "link_stock",
        lambda self, code, name="": linked.append((code, name)),
    )
    window = StandaloneLearningWindow(simulation_read_only=True)
    try:
        table = window.console.outcome_table
        table.setRowCount(2)
        for row, code in enumerate(("301716", "920202")):
            table.setItem(row, 0, QTableWidgetItem(code))
            table.setItem(row, 10, QTableWidgetItem(f"样本{row}"))
        window.show()
        table.setFocus()
        table.setCurrentCell(0, 0)
        QTest.qWait(40)
        QTest.keyClick(table, Qt.Key.Key_Down)
        QTest.qWait(40)
        assert linked[-1] == ("920202", "样本1")
    finally:
        window.close()
        app.processEvents()
