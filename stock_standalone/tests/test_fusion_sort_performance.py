from types import SimpleNamespace

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTableWidget

from ats.ui.fusion_ladder_dialog import FusionLadderDialog, FusionSortItem, FusionSortFocusItem


def test_cached_sort_values_invalidate_after_edits():
    item = FusionSortItem("2", raw_val=2)
    assert item._get_sort_val() == 2
    item.setText("10")
    assert item._get_sort_val() == 10
    item.setData(Qt.ItemDataRole.UserRole, 5)
    assert item._get_sort_val() == 5
    item.setText("--")
    assert item._is_empty()
    item.setText("3")
    assert not item._is_empty()
    assert item._get_sort_val() == 3


def test_numeric_sort_keeps_empty_values_last_in_both_directions():
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(3, 1)
    for row, value in enumerate(("--", "2", "10")):
        table.setItem(row, 0, FusionSortItem(value))
    for order, expected in ((Qt.SortOrder.AscendingOrder, ["2", "10", "--"]),
                            (Qt.SortOrder.DescendingOrder, ["10", "2", "--"])):
        table.horizontalHeader().setSortIndicator(0, order)
        table.sortItems(0, order)
        assert [table.item(row, 0).text() for row in range(3)] == expected


def test_header_sort_scrolls_to_top_and_keeps_focus_priority(monkeypatch):
    import ats.ui.styles as styles

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(styles, "setup_header_persistence", lambda *args, **kwargs: None)
    owner = SimpleNamespace(
        _on_table_item_clicked=lambda *args: None,
        _on_table_current_changed=lambda *args: None,
        _on_table_item_double_clicked=lambda *args: None,
        _on_table_context_menu=lambda *args: None,
    )
    table = FusionLadderDialog._create_interactive_table(owner, ["代码"], "test")
    table.setSortingEnabled(False)
    table.setRowCount(120)
    for row in range(120):
        table.setItem(row, 0, FusionSortFocusItem(str(row), focus_rank=1 if row == 99 else 0))
    table.resize(240, 180)
    table.show()
    table.setSortingEnabled(True)
    app.processEvents()
    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
    assert table.verticalScrollBar().value() > 0
    QTest.mouseClick(table.horizontalHeader().viewport(), Qt.MouseButton.LeftButton,
                     pos=table.horizontalHeader().rect().center())
    app.processEvents()
    assert table.verticalScrollBar().value() == 0
    assert table.item(0, 0).text() == "99"
    table.close()
