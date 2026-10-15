"""Width-constrained Qt layout with wrapping rows."""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout


class ResponsiveFlow(QLayout):
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        return QSize(0, max((item.minimumSize().height() for item in self._items), default=0))

    def sizeHint(self):
        return QSize(600, self.heightForWidth(600))

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        x, y, height = rect.x(), rect.y(), 0
        width = max(1, rect.width())
        for item in self._items:
            if item.isEmpty():
                continue
            # QWidgetItem suppresses the preferred width for Ignored policies.
            # The flow still needs the widget's natural size to place a row.
            widget = item.widget()
            size = widget.sizeHint() if widget is not None else item.sizeHint()
            maximum = widget.maximumWidth() if widget is not None else item.maximumSize().width()
            item_width = min(width, maximum, max(1, size.width()))
            item_height = max(size.height(), item.minimumSize().height())
            if item.hasHeightForWidth():
                item_height = max(item_height, item.heightForWidth(item_width))
            if x > rect.x() and x + item_width > rect.x() + width:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, item_width, item_height))
            x += item_width + self.spacing()
            height = max(height, item_height)
        return y + height - rect.y()
