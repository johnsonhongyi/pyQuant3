"""Keep highlighted candidates first when sorting either code or name."""
from PyQt6.QtCore import Qt
from ats.ui.styles import NumericTableWidgetItem


class FusionFocusItem(NumericTableWidgetItem):
    def __init__(self, value, focus_rank=0):
        super().__init__(value=value, raw_val=value)
        self.focus_rank = focus_rank or 0

    def __lt__(self, other):
        focused, other_focused = bool(self.focus_rank), bool(getattr(other, "focus_rank", 0))
        if focused != other_focused:
            table = self.tableWidget()
            descending = table is not None and table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
            return focused < other_focused if descending else focused > other_focused
        return super().__lt__(other)
