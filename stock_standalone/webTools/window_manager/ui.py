# -*- coding: utf-8 -*-
"""
窗口配置管理器 UI 界面 (PyQt6)
支持可视化管理屏幕布局、查看/编辑窗口坐标、捕获桌面窗口、一键应用及分类持久化保存。
"""

import sys
import os
import re
import json
import threading
import ctypes
from ctypes import wintypes
import keyboard
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QInputDialog, QDialog, QListWidget,
    QListWidgetItem, QTextEdit, QGroupBox, QLineEdit, QMenu, QSystemTrayIcon,
    QSizePolicy, QTabWidget, QCheckBox, QRadioButton, QButtonGroup, QAbstractItemView,
    QSpinBox, QDoubleSpinBox, QFileDialog
)
from PyQt6.QtGui import QAction, QIcon, QColor, QBrush, QPen, QFont, QPainter, QLinearGradient

# 导入核心模块与同步引擎
from . import core
from . import sync_engine

import sys
# 动态将工作空间根目录及当前目录加入路径，保证 tk_gui_modules 等模块可以被顺利导入
class WindowMixin:
    def _get_dpi_scale_factor(self) -> float:
        """获取当前系统的物理 DPI 缩放比例"""
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    dpi = screen.logicalDotsPerInch()
                    scale = dpi / 96.0
                    if scale > 0:
                        return float(scale)
        except Exception:
            pass
        try:
            import ctypes
            hdc = ctypes.windll.user32.GetDC(0)
            dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
            ctypes.windll.user32.ReleaseDC(0, hdc)
            scale = dpi_x / 96.0
            if scale <= 0:
                scale = 1.0
            return scale
        except Exception:
            return 1.0

    def _get_config_file_path(self, base_file_path: str, scale: float) -> str:
        """根据缩放因子获取配置文件路径"""
        from . import core
        app_root = core.get_app_root()
        filename = base_file_path
        if scale > 1.5:
            filename = f"scale{int(scale)}_window_config.json"
        else:
            filename = "window_config.json"
        return os.path.join(app_root, filename)

    def load_window_position_qt(self, win, window_name: str, file_path: str = "window_config.json", 
                                default_width: int = 500, default_height: int = 500, offset_step: int = 100) -> tuple:
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()
            config_file_path = self._get_config_file_path(file_path, scale)

            x = None
            y = None
            width = default_width
            height = default_height

            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if window_name in data:
                    pos = data[window_name]
                    # Qt6 中 win.geometry() 原生使用 Logical Pixels，无需二次乘以 scale
                    width = int(pos.get("width", default_width))
                    height = int(pos.get("height", default_height))
                    x = int(pos.get("x", 100))
                    y = int(pos.get("y", 100))

                    # [SAFE-GUARD] 物理超大/越界窗口自适应防护与边界修正
                    try:
                        app = QApplication.instance()
                        if app:
                            screen = app.screenAt(QtCore.QPoint(x, y))
                            if not screen:
                                screen = app.primaryScreen()
                            if screen:
                                geom = screen.availableGeometry()
                                # 如果尺寸超过当前屏幕可用区域 90%，自适应收缩至屏宽高的 85%
                                if width > geom.width() * 0.9 or height > geom.height() * 0.9:
                                    logger.warning(f"[load_window_position_qt] 检测到窗口尺寸 [{width}x{height}] 溢出显示器 [{geom.width()}x{geom.height()}]，已自动调整为自适应比例。")
                                    width = min(width, int(geom.width() * 0.85))
                                    height = min(height, int(geom.height() * 0.85))
                                    if width > geom.width() or height > geom.height():
                                        width = min(default_width, geom.width())
                                        height = min(default_height, geom.height())
                                
                                # 坐标越界修正：若窗口中心脱离屏幕可用区域，自动重置到屏中心
                                if x < geom.left() or x > geom.right() - 100 or y < geom.top() or y > geom.bottom() - 100:
                                    x = geom.left() + max(0, (geom.width() - width) // 2)
                                    y = geom.top() + max(0, (geom.height() - height) // 2)
                    except Exception as ex:
                        logger.error(f"[load_window_position_qt] 溢出防护检查异常: {ex}")

            if x is None or y is None:
                x, y = 100, 100

            win.setGeometry(x, y, width, height)
            logger.debug(f"[load_window_position_qt] 成功加载 {config_file_path} {window_name}: {width}x{height} {x}+{y}")
            return width, height, x, y
        except Exception as e:
            logger.error(f"[load_window_position_qt] 失败: {e}")
            win.resize(default_width, default_height)
            return default_width, default_height, None, None

    def save_window_position_qt_visual(self, win, window_name: str, file_path: str = "window_config.json") -> None:
        import time
        if not hasattr(self, "_window_save_debounce"):
            self._window_save_debounce = {}
        current_time = time.time()
        last_time = self._window_save_debounce.get(window_name, 0)
        if current_time - last_time < 5:
            return
        self._window_save_debounce[window_name] = current_time

        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()
            geom = win.geometry()
            # Qt6 逻辑像素直接记录，避免除以 scale 导致的精度退化与混淆
            pos = {
                "x": int(geom.x()),
                "y": int(geom.y()),
                "width": int(geom.width()),
                "height": int(geom.height())
            }

            config_file_path = self._get_config_file_path(file_path, scale)
            data = {}
            data_changed = True
            
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if window_name in data:
                        old_pos = data[window_name]
                        if (old_pos.get('x') == pos['x'] and 
                            old_pos.get('y') == pos['y'] and 
                            old_pos.get('width') == pos['width'] and 
                            old_pos.get('height') == pos['height']):
                            data_changed = False
                except Exception as e:
                    logger.error(f"[save_window_position_qt] 读取失败: {e}")

            if data_changed:
                data[window_name] = pos
                tmp_file = config_file_path + ".tmp"
                try:
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    os.replace(tmp_file, config_file_path)
                    logger.debug(f"[save_window_position_qt] {config_file_path} 已保存 {window_name}: {pos}")
                except Exception as e:
                    logger.error(f"[save_window_position_qt] 写入失败: {e}")
                    if os.path.exists(tmp_file): os.remove(tmp_file)
            else:
                logger.debug(f"[save_window_position_qt] {config_file_path} 跳过保存 {window_name}: 数据未变化")
        except Exception as e:
            logger.error(f"[save_window_position_qt] 失败: {e}")


import logging

# 初始化标准日志记录器
logger = logging.getLogger("WindowManager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    
    # 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)d): %(message)s', datefmt='%m-%d %H:%M:%S')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件 Handler (写入当前目录下的 window_layout.log)
    try:
        from . import core
        log_dir = core.get_app_root()
        log_file = os.path.join(log_dir, "window_layout.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[WARN] Failed to setup file handler for window_layout.log: {e}", file=sys.stderr)



class HotkeyLineEdit(QLineEdit):
    """自动捕获按键组合的输入框"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置为只读模式以防止传统输入字符，改由事件拦截处理
        self.setReadOnly(True)
        self.setPlaceholderText("点击后直接按下快捷键...")
        self.textChanged.connect(self.adjust_width)
        self.adjust_width()

    def adjust_width(self):
        text = self.text()
        if not text:
            self.setFixedWidth(90)  # 初始没有绑定快捷键时，宽度保持收缩紧凑状态
            return
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(text)
        padding = 16  # 给两侧边界与光标等预留适度间距
        self.setFixedWidth(max(90, w + padding))


    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        # 退格、删除或 ESC 清空快捷键
        if key in (QtCore.Qt.Key.Key_Backspace, QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Escape):
            self.setText("")
            return
            
        # 忽略单纯的修饰键按下
        if key in (QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift, QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Meta, QtCore.Qt.Key.Key_unknown):
            return
            
        key_str = []
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            key_str.append("ctrl")
        if modifiers & QtCore.Qt.KeyboardModifier.AltModifier:
            key_str.append("alt")
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            key_str.append("shift")
        if modifiers & QtCore.Qt.KeyboardModifier.MetaModifier:
            key_str.append("win")
            
        # 提取最终键名
        key_name = QtGui.QKeySequence(key).toString().lower()
        # 剥离多余的修饰符字符串
        key_name = key_name.replace("ctrl+", "").replace("alt+", "").replace("shift+", "").replace("meta+", "")
        
        if key_name:
            key_str.append(key_name)
            self.setText("+".join(key_str))
class FlowLayout(QtWidgets.QLayout):
    """
    流式自适应折行布局管理器 (PyQt6)
    用于自动根据可用宽度折行排列按钮与控件，解决窗口缩小时按钮溢出或遮挡的痛点。
    支持指定索引之后的元素在有剩余宽度时自动右对齐。
    """
    def __init__(self, parent=None, margin=0, hspacing=5, vspacing=5, align_right_from_index=-1):
        super().__init__(parent)
        self._item_list = []
        self._h_spacing = hspacing
        self._v_spacing = vspacing
        self._align_right_from_index = align_right_from_index
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        start_x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        space_x = self._h_spacing
        space_y = self._v_spacing

        # 1. 按照原版的换行规则，将 items 划分到不同的行 (rows)
        rows = []
        current_row = []
        x = start_x
        line_height = 0

        # 过滤出有效的 items 及其原始索引
        valid_items_with_idx = []
        for idx, item in enumerate(self._item_list):
            if item.widget():
                valid_items_with_idx.append((idx, item))

        for idx, item in valid_items_with_idx:
            item_width = item.sizeHint().width()
            item_height = item.sizeHint().height()

            # 检查换行条件
            next_x = x + item_width + space_x
            if next_x - space_x > rect.right() - margins.right() and line_height > 0:
                rows.append((current_row, line_height))
                current_row = []
                x = start_x
                line_height = 0

            current_row.append((idx, item))
            x = x + item_width + space_x
            line_height = max(line_height, item_height)

        if current_row:
            rows.append((current_row, line_height))

        # 2. 依次布局每一行
        for row_items, row_height in rows:
            # 计算这一行的总宽度
            row_widths = [item.sizeHint().width() for _, item in row_items]
            total_items_width = sum(row_widths)
            total_spacing = space_x * (len(row_items) - 1)
            row_total_width = total_items_width + total_spacing

            # 计算剩余宽度
            avail_width = rect.right() - margins.right() - start_x
            extra_space = avail_width - row_total_width

            # 确定是否需要应用右对齐偏移
            offset_at_index = -1
            apply_offset_to_all = False

            if self._align_right_from_index >= 0 and extra_space > 0:
                row_indices = [idx for idx, _ in row_items]
                has_left = any(idx < self._align_right_from_index for idx in row_indices)
                has_right = any(idx >= self._align_right_from_index for idx in row_indices)

                if has_left and has_right:
                    # 混合行：在第一个右侧 item 处应用偏移
                    offset_at_index = self._align_right_from_index
                elif has_right and not has_left:
                    # 纯右侧行：整行向右偏移
                    apply_offset_to_all = True

            # 摆放这一行的 items
            curr_x = start_x
            for idx, item in row_items:
                if offset_at_index >= 0 and idx >= offset_at_index:
                    curr_x += extra_space
                    offset_at_index = -1  # 确保只在分水岭加一次
                elif apply_offset_to_all:
                    curr_x += extra_space
                    apply_offset_to_all = False  # 确保整行偏移只在起点加一次

                if not test_only:
                    item.setGeometry(QtCore.QRect(QtCore.QPoint(curr_x, y), item.sizeHint()))

                curr_x += item.sizeHint().width() + space_x

            y += row_height + space_y

        return y - space_y - rect.y() + margins.bottom()



class NewResolutionDialog(QDialog):
    """
    新建配置方案对话框
    支持输入方案标识，以及选择方案所属的显示器分类 (单屏、多屏、特殊)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建配置方案")
        self.resize(380, 180)
        self.res_name = ""
        self.category = ""
        self.init_ui()

    def init_ui(self):
        # 现代暗黑色调
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QComboBox {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
            }
            QPushButton#btnConfirm {
                background-color: #0ea5e9;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0284c7;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # 方案名
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("方案标识 (英文/数字): "))
        self.txt_name = QLineEdit("tdx_ths_position")
        row1.addWidget(self.txt_name)
        layout.addLayout(row1)
        
        # 分类
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("方案所属类别:          "))
        self.cb_cat = QComboBox()
        self.cb_cat.addItem("🖥️ 单屏配置", "single_display")
        self.cb_cat.addItem("🖥️🖥️ 多屏配置", "multi_display")
        self.cb_cat.addItem("⚙️ 特殊/历史", "custom_special")
        row2.addWidget(self.cb_cat)
        layout.addLayout(row2)
        
        layout.addSpacing(10)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton("确定")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.clicked.connect(self.accept_dialog)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)
        
    def accept_dialog(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "警告", "方案标识不能为空")
            return
        self.res_name = name
        self.category = self.cb_cat.currentData()
        self.accept()


class CaptureWindowsDialog(QDialog):
    """
    捕获桌面窗口的对话框
    列出当前桌面所有可见窗口及其坐标，供用户选择并添加到配置中。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("捕获当前桌面窗口坐标")
        self.resize(650, 450)
        self.selected_windows = []
        self.all_windows = []
        self.selected_set = set()
        self.init_ui()
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.refresh_windows()

    def init_ui(self):
        # 现代暗黑色调样式
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 6px;
            }
            QListWidget {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #d8d8d8;
                padding: 5px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #25252b;
            }
            QListWidget::item:hover {
                background-color: #2b2b36;
                color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #0ea5e9;
                color: #ffffff;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
                border-color: #0ea5e9;
            }
            QPushButton#btnConfirm {
                background-color: #0ea5e9;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0284c7;
            }
        """)

        layout = QVBoxLayout(self)
        
        info_label = QLabel("选择你想要捕获并记录当前位置的桌面窗口 (默认点击单选，按住 Ctrl 多选 / Shift 连选)：")
        layout.addWidget(info_label)

        # 窗口列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget)

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_refresh = QPushButton("刷新列表")
        self.btn_refresh.clicked.connect(self.refresh_windows)
        self.btn_update_coords = QPushButton("🔄 更新最新坐标")
        self.btn_update_coords.clicked.connect(self.update_active_coordinates)
        
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_update_coords)
        
        # 添加关键字过滤搜索框
        btn_layout.addWidget(QLabel(" 🔍 过滤:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("输入关键字快速匹配...")
        self.txt_search.setFixedWidth(160)
        self.txt_search.textChanged.connect(self.filter_windows)
        btn_layout.addWidget(self.txt_search)
        
        # 添加清空按钮
        self.btn_clear_search = QPushButton("清空")
        self.btn_clear_search.clicked.connect(self.clear_search)
        btn_layout.addWidget(self.btn_clear_search)
        
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton("导入选中的窗口坐标")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.clicked.connect(self.accept_selection)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setSelected(True)

    def on_selection_changed(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item.isSelected():
                self.selected_set.add(item_data)
            else:
                self.selected_set.discard(item_data)

    def refresh_windows(self):
        self.selected_set.clear()
        # 获取所有可见窗口
        win_list = core.list_visible_windows()
        
        # 过滤掉一些无意义的短名称窗口或系统窗口
        filtered_wins = []
        exclude_patterns = [
            r"^$", r"^Settings$", r"^Microsoft Text Input Application$", r"^Program Manager$",
            r"^Windows 任务管理器$", r"^NVIDIA GeForce Overlay$", r"^Task View$", r"^Language bar$"
        ]
        
        for w in win_list:
            exclude = False
            for pat in exclude_patterns:
                if re.match(pat, w.title, re.IGNORECASE):
                    exclude = True
                    break
            # 如果窗口宽或高太小，大概率是不可见的背景哨兵窗口
            if w.width <= 100 or w.height <= 100:
                exclude = True
            # 过滤本配置管理器窗口本身
            if "窗口坐标管理器" in w.title or "Capture桌面窗口" in w.title:
                exclude = True
                
            if not exclude:
                filtered_wins.append(w)
                
        # 按标题排序并存入 self.all_windows
        filtered_wins.sort(key=lambda x: x.title.lower())
        self.all_windows = []
        for w in filtered_wins:
            exe_path = getattr(w, 'exe_path', '')
            self.all_windows.append((w.title, f"{w.left},{w.top},{w.width},{w.height}", exe_path))
            
        self.filter_windows()

    def filter_windows(self):
        # 暂时断开选择变化信号，防止 clear() 以及重新填充时频繁触发 selected_set 的更新
        try:
            self.list_widget.itemSelectionChanged.disconnect(self.on_selection_changed)
        except (TypeError, RuntimeError):
            pass

        self.list_widget.clear()
        search_kw = self.txt_search.text().strip().lower()
        
        for title, pos_str, exe_path in self.all_windows:
            if search_kw and search_kw not in title.lower() and search_kw not in exe_path.lower():
                continue
            
            item = QListWidgetItem(f"{title}  [{pos_str}]")
            item_data = (title, pos_str, exe_path)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, item_data)
            self.list_widget.addItem(item)
            
            # 如果之前在选中列表中，恢复选中状态
            if item_data in self.selected_set:
                item.setSelected(True)
                
        # 重新绑定选择变化信号
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)

    def accept_selection(self):
        self.selected_windows = list(self.selected_set)
        self.accept()

    def clear_search(self):
        self.txt_search.clear()

    def update_active_coordinates(self):
        """手动获取列表中所有窗口当前在桌面上的最新物理坐标，并刷新列表文字，保留选中状态"""
        if self.list_widget.count() == 0:
            return
            
        self.list_widget.blockSignals(True)
        try:
            try:
                self.list_widget.itemSelectionChanged.disconnect(self.on_selection_changed)
            except (TypeError, RuntimeError):
                pass
                
            updated_count = 0
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if not item_data:
                    continue
                    
                title, pos_str, exe_path = item_data
                
                titles_to_try = [title]
                if title.endswith('.py') and not title.startswith('py'):
                    titles_to_try.append(title.replace('.py', '.exe'))
                elif title.endswith('.exe'):
                    titles_to_try.append(title.replace('.exe', '.py'))
                    
                found_hwnd = None
                for t in titles_to_try:
                    found = core.find_windows_by_title_safe(t)
                    if found:
                        found_hwnd, _ = found[0]
                        break
                        
                if found_hwnd:
                    left, top, width, height = core.get_window_rect(found_hwnd)
                    if left < -10000 and top < -10000:
                        continue
                    new_pos_str = f"{left},{top},{width},{height}"
                    
                    if new_pos_str != pos_str:
                        item.setText(f"{title}  [{new_pos_str}]")
                        new_item_data = (title, new_pos_str, exe_path)
                        item.setData(QtCore.Qt.ItemDataRole.UserRole, new_item_data)
                        
                        # 同步更新 self.all_windows 里的对应项
                        for idx, (t_all, p_all, e_all) in enumerate(self.all_windows):
                            if t_all == title:
                                self.all_windows[idx] = (title, new_pos_str, exe_path)
                                break
                                
                        # 如果是已选中，同步更新 selected_set 里的数据
                        if item.isSelected():
                            self.selected_set.discard(item_data)
                            self.selected_set.add(new_item_data)
                            
                        updated_count += 1
                        
            if updated_count > 0:
                QMessageBox.information(self, "更新成功", f"成功手动更新了 {updated_count} 个运行中窗口的最新物理坐标！")
            else:
                QMessageBox.information(self, "提示", "未检测到任何窗口位置发生变化。")
                
        finally:
            self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
            self.list_widget.blockSignals(False)

    def on_item_double_clicked(self, item):
        item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if item_data:
            title, pos_str, exe_path = item_data
            core.bring_window_to_top_by_title(title)

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e24;
                color: #e0e0e0;
                border: 1px solid #3a3a42;
            }
            QMenu::item {
                padding: 6px 20px;
            }
            QMenu::item:selected {
                background-color: #0ea5e9;
                color: #ffffff;
            }
        """)
        
        selected_items = self.list_widget.selectedItems()
        
        center_this = menu.addAction("居中显示于程序所在屏幕")
        center_all = None
        if len(selected_items) > 1 and item in selected_items:
            center_all = menu.addAction(f"居中所有选中窗口 ({len(selected_items)}个) 于程序所在屏幕")
            
        item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        open_dir_action = None
        if item_data and len(item_data) > 2 and item_data[2]:
            menu.addSeparator()
            open_dir_action = menu.addAction("📂 打开程序目录")

        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == center_this:
            self.center_windows_on_current_screen([item])
        elif center_all and action == center_all:
            self.center_windows_on_current_screen(selected_items)
        elif open_dir_action and action == open_dir_action:
            exe_path = item_data[2]
            import subprocess
            target_path = exe_path.strip().strip('"').strip("'")
            if os.path.exists(target_path):
                if os.path.isfile(target_path):
                    subprocess.Popen(f'explorer /select,"{os.path.normpath(target_path)}"')
                else:
                    os.startfile(target_path)
            else:
                dir_name = os.path.dirname(target_path)
                if dir_name and os.path.exists(dir_name):
                    os.startfile(dir_name)

    def center_windows_on_current_screen(self, items):
        if not items:
            return
            
        import win32api
        import win32con
        
        # 1. 获取当前对话框所在物理屏幕的工作区坐标
        hwnd_dialog = int(self.winId())
        try:
            hmonitor = win32api.MonitorFromWindow(hwnd_dialog, win32con.MONITOR_DEFAULTTONEAREST)
            monitor_info = win32api.GetMonitorInfo(hmonitor)
            left, top, right, bottom = monitor_info["Work"]
            screen_x = left
            screen_y = top
            screen_w = right - left
            screen_h = bottom - top
        except Exception as e:
            screen_x = 0
            screen_y = 0
            screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            
        success_count = 0
        fail_count = 0
        
        # 暂时断开信号，避免批量修改列表时频繁触发 list_widget 相关的信号或事件
        self.list_widget.blockSignals(True)
        try:
            try:
                self.list_widget.itemSelectionChanged.disconnect(self.on_selection_changed)
            except (TypeError, RuntimeError):
                pass
                
            for item in items:
                item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if not item_data:
                    continue
                title, pos_str, exe_path = item_data
                
                # 2. 查找窗口 HWND
                titles_to_try = [title]
                if title.endswith('.py') and not title.startswith('py'):
                    titles_to_try.append(title.replace('.py', '.exe'))
                elif title.endswith('.exe'):
                    titles_to_try.append(title.replace('.exe', '.py'))
                    
                found_hwnd = None
                for t in titles_to_try:
                    found = core.find_windows_by_title_safe(t)
                    if found:
                        found_hwnd, _ = found[0]
                        break
                        
                if not found_hwnd:
                    fail_count += 1
                    continue
                    
                # 3. 获取目标窗口的宽高
                w_left, w_top, width, height = core.get_window_rect(found_hwnd)
                # 兜底
                if width <= 0 or height <= 0:
                    try:
                        parts = [int(p.strip()) for p in pos_str.split(',')]
                        if len(parts) == 4:
                            width = parts[2]
                            height = parts[3]
                    except Exception:
                        width, height = 800, 600
                        
                # 4. 计算居中坐标
                new_x = screen_x + (screen_w - width) // 2
                new_y = screen_y + (screen_h - height) // 2
                new_pos_str = f"{new_x},{new_y},{width},{height}"
                
                # 5. 移动窗口 (如果是最小化状态，先还原)
                if w_left < -10000 and w_top < -10000:
                    # 最小化时还原
                    core.user32.ShowWindow(found_hwnd, 1) # SW_SHOWNORMAL = 1
                    import time
                    time.sleep(0.05)
                    
                moved = core.set_window_pos_by_title(title, new_pos_str)
                if not moved:
                    moved = core.set_window_hwnd_pos(found_hwnd, new_pos_str, title=title)
                    
                if moved:
                    # 6. 更新 UI 数据
                    item.setText(f"{title}  [{new_pos_str}]")
                    new_item_data = (title, new_pos_str, exe_path)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, new_item_data)
                    
                    # 更新所有窗口列表缓存
                    for idx, (t_all, p_all, e_all) in enumerate(self.all_windows):
                        if t_all == title:
                            self.all_windows[idx] = (title, new_pos_str, exe_path)
                            break
                            
                    # 更新已选择的集合数据
                    if item_data in self.selected_set:
                        self.selected_set.discard(item_data)
                        self.selected_set.add(new_item_data)
                        
                    success_count += 1
                else:
                    fail_count += 1
                    
        finally:
            self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
            self.list_widget.blockSignals(False)
            
        if len(items) == 1:
            if success_count > 0:
                logger.info(f"窗口 [{items[0].data(QtCore.Qt.ItemDataRole.UserRole)[0]}] 已成功居中")
            else:
                QMessageBox.warning(self, "错误", "无法移动目标窗口，请检查窗口是否已被关闭或权限不足。")
        else:
            QMessageBox.information(
                self, 
                "操作完成", 
                f"批量居中处理完毕：\n成功移动: {success_count} 个窗口\n失败: {fail_count} 个窗口"
            )


class EditPathDialog(QDialog):
    """编辑程序路径对话框，支持手动输入与文件浏览"""
    def __init__(self, title, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑程序路径 - {title}")
        self.resize(500, 140)
        self.final_path = ""
        self.current_path = current_path
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
            }
            QPushButton#btnConfirm {
                background-color: #0ea5e9;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0284c7;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        layout.addWidget(QLabel("程序可执行文件路径 (留空表示不自动启动):"))
        
        row = QHBoxLayout()
        self.txt_path = QLineEdit(self.current_path)
        row.addWidget(self.txt_path, stretch=4)
        
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.browse_file)
        row.addWidget(self.btn_browse, stretch=1)
        layout.addLayout(row)
        
        layout.addSpacing(10)
        
        btn_layout = QHBoxLayout()
        # 清空按钮放左侧，方便快速清除错误路径
        self.btn_clear = QPushButton("🗑 清空路径")
        self.btn_clear.setToolTip("清空路径（留空表示不自动启动）")
        self.btn_clear.clicked.connect(lambda: self.txt_path.clear())
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton("确定")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.clicked.connect(self.accept_path)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

    def browse_file(self):
        from PyQt6.QtWidgets import QFileDialog
        import os
        initial_dir = ""
        path_text = self.txt_path.text().strip()
        # 剥离可能存在的外层引号以找到正确的目录
        if (path_text.startswith('"') and path_text.endswith('"')) or (path_text.startswith("'") and path_text.endswith("'")):
            path_text = path_text[1:-1]
        if path_text:
            dir_name = os.path.dirname(path_text)
            if os.path.exists(dir_name):
                initial_dir = dir_name
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行程序/脚本", 
            initial_dir, 
            "可执行文件 (*.exe *.bat *.cmd *.py);;所有文件 (*.*)"
        )
        if file_path:
            norm_path = os.path.normpath(file_path)
            # 如果路径中含有空格，且没有被引号包裹，则自动包裹双引号
            if " " in norm_path:
                if not ((norm_path.startswith('"') and norm_path.endswith('"')) or (norm_path.startswith("'") and norm_path.endswith("'"))):
                    norm_path = f'"{norm_path}"'
            self.txt_path.setText(norm_path)

    def accept_path(self):
        path = self.txt_path.text().strip()
        # 如果路径中含有空格，且没有被包裹，则自动加上双引号
        # 但对于复杂 shell 命令（含分隔符、引号或特殊前缀），不做自动包裹
        is_shell_cmd = (
            any(marker in path for marker in (";", "&&", "||", "|")) or
            path.strip().lower().startswith(("start ", "cmd ", "powershell ", "python ", "py ", "cd ", "cd/")) or
            '"' in path or "'" in path
        )
        if not is_shell_cmd:
            if " " in path:
                if not ((path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'"))):
                    path = f'"{path}"'
        self.final_path = path
        self.accept()


class RouteConfigDialog(QDialog):
    """
    高级系统配置对话框：支持静态路由网关配置 + 🧲 磁吸窗口关键字管理
    """
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("🌐 静态路由与 🧲 磁吸窗口配置")
        self.resize(540, 480)
        self.init_ui()

    def init_ui(self):
        # 统一使用暗黑色调
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QTabWidget::pane {
                border: 1px solid #3a3a42;
                background-color: #1a1a20;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #2a2a32;
                color: #a0a0a0;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0ea5e9;
                color: #ffffff;
                font-weight: bold;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QListWidget {
                background-color: #15151a;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #00ffcc;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px;
            }
            QListWidget::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
            }
            QPushButton#btnConfirm {
                background-color: #0ea5e9;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0284c7;
            }
            QPushButton#btnTest {
                background-color: #10b981;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnTest:hover {
                background-color: #059669;
            }
            QPushButton#btnAddKw {
                background-color: #0284c7;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnDeleteKw {
                background-color: #ef4444;
                border: none;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        self.tab_widget = QTabWidget(self)
        
        # ==========================================
        # Tab 1: 🌐 静态路由配置
        # ==========================================
        tab_route = QWidget()
        route_layout = QVBoxLayout(tab_route)
        route_layout.setSpacing(12)
        
        self.chk_enabled = QtWidgets.QCheckBox("启用启动时自动检测/添加此静态路由")
        route_layout.addWidget(self.chk_enabled)
        
        routing_cfg = self.config_manager.config_data.get("routing_config", {})
        enabled = routing_cfg.get("enabled", False)
        dest = routing_cfg.get("destination", "")
        mask = routing_cfg.get("mask", "255.255.255.0")
        gw = routing_cfg.get("gateway", "")
        
        self.chk_enabled.setChecked(enabled)
        
        # 目标网段
        row_dest = QHBoxLayout()
        lbl_dest = QLabel("目标网段:")
        lbl_dest.setFixedWidth(80)
        self.txt_dest = QLineEdit(dest)
        row_dest.addWidget(lbl_dest)
        row_dest.addWidget(self.txt_dest)
        route_layout.addLayout(row_dest)
        
        # 子网掩码
        row_mask = QHBoxLayout()
        lbl_mask = QLabel("子网掩码:")
        lbl_mask.setFixedWidth(80)
        self.txt_mask = QLineEdit(mask)
        row_mask.addWidget(lbl_mask)
        row_mask.addWidget(self.txt_mask)
        route_layout.addLayout(row_mask)
        
        # 默认网关
        row_gw = QHBoxLayout()
        lbl_gw = QLabel("默认网关:")
        lbl_gw.setFixedWidth(80)
        self.txt_gw = QLineEdit(gw)
        row_gw.addWidget(lbl_gw)
        row_gw.addWidget(self.txt_gw)
        route_layout.addLayout(row_gw)
        
        route_layout.addSpacing(10)
        
        self.btn_test = QPushButton("🔍 立即检测/应用路由")
        self.btn_test.setObjectName("btnTest")
        self.btn_test.clicked.connect(self.test_and_apply_route)
        route_layout.addWidget(self.btn_test)
        route_layout.addStretch()
        
        # ==========================================
        # Tab 2: 🧲 磁吸窗口关键字管理
        # ==========================================
        tab_magnetic = QWidget()
        mag_layout = QVBoxLayout(tab_magnetic)
        mag_layout.setSpacing(8)
        
        lbl_tip = QLabel("💡 提示：包含以下关键字的窗口才会触发贴边隐藏，常规日常软件不受干涉。")
        lbl_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        mag_layout.addWidget(lbl_tip)
        
        self.list_kw = QListWidget()
        self.list_kw.itemClicked.connect(self._on_kw_item_clicked)
        mag_layout.addWidget(self.list_kw)
        
        # 输入与编辑行
        edit_layout = QHBoxLayout()
        self.txt_kw_input = QLineEdit()
        self.txt_kw_input.setPlaceholderText("输入关键字 (如: 涨跌分布个股明细, 加速龙头跟踪器)...")
        
        self.btn_add_kw = QPushButton("➕ 添加/修改")
        self.btn_add_kw.setObjectName("btnAddKw")
        self.btn_add_kw.clicked.connect(self._add_or_update_kw)
        
        self.btn_del_kw = QPushButton("❌ 删除选中")
        self.btn_del_kw.setObjectName("btnDeleteKw")
        self.btn_del_kw.clicked.connect(self._delete_selected_kw)
        
        edit_layout.addWidget(self.txt_kw_input)
        edit_layout.addWidget(self.btn_add_kw)
        edit_layout.addWidget(self.btn_del_kw)
        mag_layout.addLayout(edit_layout)
        
        # 加载初始关键字列表
        self._load_magnetic_keywords()

        # ==========================================
        # Tab 3: 🚀 Acer 性能与风扇控制
        # ==========================================
        tab_acer = QWidget()
        acer_layout = QVBoxLayout(tab_acer)
        acer_layout.setSpacing(12)

        self.acer_controller = core.AcerPerformanceController()
        status = self.acer_controller.get_current_status()
        is_supported = status.get("supported", False)

        # 硬件支持 Badge 指示
        lbl_badge = QLabel()
        if is_supported:
            lbl_badge.setText("✅ 已检测到 Acer 硬件控制驱动 (WMI 支持已就绪)")
            lbl_badge.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px;")
        else:
            lbl_badge.setText("⚠️ 未检测到 Acer WMI 接口 (非 Acer 设备或缺少 PredatorSense 服务)")
            lbl_badge.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 12px;")
        acer_layout.addWidget(lbl_badge)

        # 读取保存的配置
        acer_cfg = self.config_manager.get_acer_performance_config()

        # 1. 超频模式分组框
        grp_oc = QGroupBox("超频模式 (Overclocking Mode)")
        oc_layout = QHBoxLayout(grp_oc)
        self.rad_oc_default = QtWidgets.QRadioButton("普通 / 默认 (Default)")
        self.rad_oc_fast = QtWidgets.QRadioButton("⚡ 快速 (Fast)")
        self.rad_oc_extreme = QtWidgets.QRadioButton("🔥 极速 (Extreme)")

        oc_mode_saved = str(acer_cfg.get("overclock_mode", "Fast")).upper()
        if oc_mode_saved in ["DEFAULT", "NORMAL", "0"]:
            self.rad_oc_default.setChecked(True)
        elif oc_mode_saved in ["EXTREME", "2"]:
            self.rad_oc_extreme.setChecked(True)
        else:
            self.rad_oc_fast.setChecked(True)

        oc_layout.addWidget(self.rad_oc_default)
        oc_layout.addWidget(self.rad_oc_fast)
        oc_layout.addWidget(self.rad_oc_extreme)
        acer_layout.addWidget(grp_oc)

        # 2. 风扇与 CoolBoost 分组框
        grp_fan = QGroupBox("散热与风扇控制 (Fan & CoolBoost)")
        fan_layout = QVBoxLayout(grp_fan)
        
        self.chk_coolboost = QCheckBox("开启 CoolBoost™ 动态加压散热辅助")
        self.chk_coolboost.setChecked(acer_cfg.get("coolboost", True))
        fan_layout.addWidget(self.chk_coolboost)

        row_fan_mode = QHBoxLayout()
        row_fan_mode.addWidget(QLabel("风扇转速模式: "))
        self.rad_fan_auto = QtWidgets.QRadioButton("自动 (Auto)")
        self.rad_fan_max = QtWidgets.QRadioButton("最大 (Max)")
        self.rad_fan_custom = QtWidgets.QRadioButton("自定义 (Custom)")
        
        fan_mode_saved = str(acer_cfg.get("fan_mode", "Auto")).upper()
        if fan_mode_saved in ["MAX", "1"]:
            self.rad_fan_max.setChecked(True)
        elif fan_mode_saved in ["CUSTOM", "2"]:
            self.rad_fan_custom.setChecked(True)
        else:
            self.rad_fan_auto.setChecked(True)

        row_fan_mode.addWidget(self.rad_fan_auto)
        row_fan_mode.addWidget(self.rad_fan_max)
        row_fan_mode.addWidget(self.rad_fan_custom)
        row_fan_mode.addStretch()
        fan_layout.addLayout(row_fan_mode)
        acer_layout.addWidget(grp_fan)

        # 3. 完成后的窗口处理方式 (Post Action Mode)
        grp_post = QGroupBox("执行完成后控制面板处理方式")
        post_layout = QHBoxLayout(grp_post)
        self.rad_post_hide = QtWidgets.QRadioButton("🙈 静默隐藏至后台 (Hide，推荐)")
        self.rad_post_close = QtWidgets.QRadioButton("❌ 关闭控制窗口 (Close，测试唤起)")
        self.rad_post_kill = QtWidgets.QRadioButton("💀 彻底杀掉前台进程 (Kill，测试冷启动)")

        post_action_saved = str(acer_cfg.get("post_action", "hide")).lower()
        if post_action_saved in ["close", "关闭"]:
            self.rad_post_close.setChecked(True)
        elif post_action_saved in ["kill", "杀掉"]:
            self.rad_post_kill.setChecked(True)
        else:
            self.rad_post_hide.setChecked(True)

        post_layout.addWidget(self.rad_post_hide)
        post_layout.addWidget(self.rad_post_close)
        post_layout.addWidget(self.rad_post_kill)
        post_layout.addStretch()
        acer_layout.addWidget(grp_post)

        # 4. 自动化开机/启动设置 (带秒数微调)
        row_autostart = QHBoxLayout()
        self.chk_acer_autostart = QCheckBox(" 开启 Windows 开机自启动 (开机登录后在后台托盘静默运行，全局唯一)")
        self.chk_acer_autostart.setChecked(core.is_autostart_enabled_for_current_app())
        
        row_autostart.addWidget(self.chk_acer_autostart)
        row_autostart.addWidget(QLabel("   ⏳ 启动延迟应用: "))
        
        self.spn_startup_delay = QtWidgets.QSpinBox()
        self.spn_startup_delay.setRange(0, 120)
        self.spn_startup_delay.setValue(int(acer_cfg.get("startup_delay_seconds", 10)))
        self.spn_startup_delay.setSuffix(" 秒")
        self.spn_startup_delay.setToolTip("开机启动后静默等待此秒数，待 Windows 后台驱动服务彻底到位后再自动应用设置")
        
        row_autostart.addWidget(self.spn_startup_delay)
        row_autostart.addStretch()
        acer_layout.addLayout(row_autostart)

        # 5. 立即应用按钮
        btn_apply_acer = QPushButton("⚡ 立即应用 Acer 性能设置")
        btn_apply_acer.setObjectName("btnApplyAcer")
        btn_apply_acer.clicked.connect(self._apply_acer_performance_now)
        acer_layout.addWidget(btn_apply_acer)

        acer_layout.addStretch()
        
        self.tab_widget.addTab(tab_route, "🌐 静态路由")
        self.tab_widget.addTab(tab_magnetic, "🧲 磁吸窗口")
        self.tab_widget.addTab(tab_acer, "🚀 Acer 性能控制")
        layout.addWidget(self.tab_widget)
        
        # 底部确认/取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton("💾 保存设置")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

    def _apply_acer_performance_now(self):
        selected_oc = "Fast"
        if self.rad_oc_default.isChecked():
            selected_oc = "Default"
        elif self.rad_oc_extreme.isChecked():
            selected_oc = "Extreme"

        selected_fan = "Auto"
        if self.rad_fan_max.isChecked():
            selected_fan = "Max"
        elif self.rad_fan_custom.isChecked():
            selected_fan = "Custom"

        selected_post = "hide"
        if self.rad_post_close.isChecked():
            selected_post = "close"
        elif self.rad_post_kill.isChecked():
            selected_post = "kill"

        profile = {
            "overclock_mode": selected_oc,
            "coolboost": self.chk_coolboost.isChecked(),
            "fan_mode": selected_fan,
            "post_action": selected_post
        }
        success, msg = self.acer_controller.apply_performance_profile(profile, force=True)
        if success:
            QMessageBox.information(self, "应用成功", f"Acer 性能模式配置已生效：\n{msg}")
        else:
            QMessageBox.warning(self, "应用提示", f"Acer 性能设置结果：\n{msg}")

    def _load_magnetic_keywords(self):
        """加载已保存的所有磁吸关键字到 ListWidget"""
        self.list_kw.clear()
        kws = core.get_magnetic_keywords()
        for kw in kws:
            item = QListWidgetItem(str(kw))
            self.list_kw.addItem(item)

    def _on_kw_item_clicked(self, item):
        if item:
            self.txt_kw_input.setText(item.text())

    def _add_or_update_kw(self):
        text = self.txt_kw_input.text().strip()
        if not text:
            return
            
        current_item = self.list_kw.currentItem()
        existing = [self.list_kw.item(i).text() for i in range(self.list_kw.count())]

        if current_item and current_item.isSelected():
            current_item.setText(text)
        else:
            if text in existing:
                QMessageBox.information(self, "提示", f"关键字 '{text}' 已在列表中！")
                return
            item = QListWidgetItem(text)
            self.list_kw.addItem(item)
            
        self.txt_kw_input.clear()

    def _delete_selected_kw(self):
        row = self.list_kw.currentRow()
        if row >= 0:
            self.list_kw.takeItem(row)
            self.txt_kw_input.clear()

    def save_settings(self):
        # 1. 保存静态路由配置
        dest = self.txt_dest.text().strip()
        mask = self.txt_mask.text().strip()
        gw = self.txt_gw.text().strip()
        
        ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
        if not re.match(ip_pattern, dest) or not re.match(ip_pattern, mask) or not re.match(ip_pattern, gw):
            QMessageBox.warning(self, "格式错误", "请输入有效的IP地址或子网掩码格式！")
            return
            
        routing_cfg = {
            "enabled": self.chk_enabled.isChecked(),
            "destination": dest,
            "mask": mask,
            "gateway": gw
        }
        self.config_manager.config_data["routing_config"] = routing_cfg
        
        # 2. 保存磁吸关键字配置
        new_kws = [self.list_kw.item(i).text() for i in range(self.list_kw.count())]
        self.config_manager.config_data["magnetic_keywords"] = new_kws

        # 3. 保存 Acer 性能模式配置
        selected_oc = "Fast"
        if self.rad_oc_default.isChecked():
            selected_oc = "Default"
        elif self.rad_oc_extreme.isChecked():
            selected_oc = "Extreme"

        selected_fan = "Auto"
        if self.rad_fan_max.isChecked():
            selected_fan = "Max"
        elif self.rad_fan_custom.isChecked():
            selected_fan = "Custom"

        selected_post = "hide"
        if self.rad_post_close.isChecked():
            selected_post = "close"
        elif self.rad_post_kill.isChecked():
            selected_post = "kill"

        acer_cfg = {
            "overclock_mode": selected_oc,
            "coolboost": self.chk_coolboost.isChecked(),
            "fan_mode": selected_fan,
            "post_action": selected_post,
            "auto_apply_on_startup": self.chk_acer_autostart.isChecked(),
            "startup_delay_seconds": self.spn_startup_delay.value()
        }
        self.config_manager.save_acer_performance_config(acer_cfg)
        
        if self.config_manager.save():
            # 刷新内存中的磁吸关键字缓存
            core._MAGNETIC_KEYWORDS_CACHE = None
            
            # 1. 设置 Windows 注册表开机自启状态（全局唯一，用户显式确认与更新，严禁启动隐式添加）
            is_autostart_checked = self.chk_acer_autostart.isChecked()
            is_currently_autostart = core.is_autostart_enabled_for_current_app()
            has_existing, existing_cmd = core.get_current_autostart_command()
            expected_cmd = core.get_autostart_command()
            
            auto_ok = True
            auto_msg = ""
            if is_autostart_checked:
                if has_existing and not is_currently_autostart:
                    reply = QMessageBox.question(
                        self,
                        "更新开机自启动路径确认",
                        f"检测到 Windows 注册表中已存在其他开机自启动路径：\n【已有路径】: {existing_cmd}\n\n"
                        f"当前程序运行路径为：\n【当前路径】: {expected_cmd}\n\n"
                        f"整个系统只允许一个 manage_window_layout 开机自启。\n"
                        f"是否将开机自启动路径更新为当前程序？\n\n"
                        f"• 点击【是 (Yes)】：覆盖更新为当前程序路径\n"
                        f"• 点击【否 (No)】：保留原有开机自启路径不修改",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        auto_ok, auto_msg = core.set_autostart_enabled(True)
                    else:
                        auto_ok, auto_msg = True, f"保留已有注册表自启路径: {existing_cmd}"
                else:
                    auto_ok, auto_msg = core.set_autostart_enabled(True)
            else:
                # 用户未勾选当前程序开机自启：
                # 只有当注册表里配置的确实是当前程序时，才执行删除；若为外部程序路径则保持原样不触碰
                if is_currently_autostart:
                    auto_ok, auto_msg = core.set_autostart_enabled(False)
                else:
                    auto_ok, auto_msg = True, "当前程序未开启开机自启 (保持系统设置不变)"
            
            # 2. 在主窗口日志文本框输出结构化通知
            autostart_str = "已开启" if is_autostart_checked else "已关闭/已删除"
            delay_str = f"{self.spn_startup_delay.value()} 秒"
            
            main_win = getattr(self, 'parent_ui', None) or self.parent()
            if main_win and hasattr(main_win, 'log'):
                main_win.log(f"🚀 Acer 性能模式配置已保存: 超频={selected_oc}, 风扇={selected_fan}, CoolBoost={self.chk_coolboost.isChecked()}, 处理方式={selected_post}")
                main_win.log(f"⏳ [AutoStart] {auto_msg} (启动延迟应用: {delay_str})")

            QMessageBox.information(
                self, 
                "保存成功", 
                f"静态路由、磁吸关键字及 Acer 性能配置已成功落盘！\n\n"
                f"• 超频模式: {selected_oc}\n"
                f"• 风扇模式: {selected_fan}\n"
                f"• 后置处理: {selected_post}\n"
                f"• 开机后台自启: {autostart_str}\n"
                f"• 自启路径/日志: {auto_msg}\n"
                f"• 启动延迟应用: {delay_str}"
            )
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "配置文件写盘失败，请检查文件写权限！")

    def test_and_apply_route(self):
        dest = self.txt_dest.text().strip()
        mask = self.txt_mask.text().strip()
        gw = self.txt_gw.text().strip()
        
        ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
        if not re.match(ip_pattern, dest) or not re.match(ip_pattern, mask) or not re.match(ip_pattern, gw):
            QMessageBox.warning(self, "格式错误", "请输入有效的IP地址或子网掩码格式！")
            return

        old_cfg = self.config_manager.config_data.get("routing_config", {})
        self.config_manager.config_data["routing_config"] = {
            "enabled": self.chk_enabled.isChecked(),
            "destination": dest,
            "mask": mask,
            "gateway": gw
        }
        
        from .core import check_and_add_route
        success, msg = check_and_add_route(self.config_manager)
        
        if success:
            QMessageBox.information(self, "检测成功", msg)
        else:
            QMessageBox.warning(self, "检测失败", msg)


class RamDiskSyncDialog(QDialog):
    """
    RamDisk 实时数据自动同步与备份配置对话框
    支持：
    1. 浏览文件夹并多选关键数据文件（QFileDialog.getOpenFileNames 批量多选）
    2. 源目录自动探测与切换
    3. 仅同步列表多选文件 (specific_files) vs 全目录通配符扫描 (all_directory)
    4. 待同步列表的添加、删除、清空、一键勾选
    5. 备份路径、同步间隔、交易时段、原子安全替换设置
    6. 即时同步测试与诊断日志输出
    """
    def __init__(self, sync_config, sync_engine, sync_worker=None, parent=None):
        super().__init__(parent)
        self.sync_config = sync_config
        self.sync_engine = sync_engine
        self.sync_worker = sync_worker
        self.setWindowTitle("💾 RamDisk 实时数据自动同步与多选备份设置")
        self.resize(660, 750)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QGroupBox {
                border: 1px solid #3a3a42;
                border-radius: 6px;
                margin-top: 8px;
                font-weight: bold;
                color: #38bdf8;
                background-color: #16161b;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #121215;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #ffffff;
                padding: 5px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
                border-color: #0ea5e9;
            }
            QCheckBox, QRadioButton {
                color: #ffffff;
                font-size: 12px;
            }
            QListWidget {
                background-color: #121215;
                border: 1px solid #3a3a42;
                border-radius: 4px;
                color: #f3f4f6;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #23232b;
            }
            QListWidget::item:hover {
                background-color: #262630;
            }
            QListWidget::item:selected {
                background-color: #0369a1;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #0f0f12;
                border: 1px solid #25252b;
                border-radius: 4px;
                color: #34d399;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        # 1. 基础开关与路径 GroupBox
        gb_basic = QGroupBox("📁 路径设置与自动同步开关")
        basic_layout = QVBoxLayout(gb_basic)
        basic_layout.setSpacing(6)

        self.chk_enabled = QCheckBox("启用 RamDisk 实时数据自动同步与备份")
        self.chk_enabled.setChecked(self.sync_config.enabled)
        self.chk_enabled.setStyleSheet("font-weight: bold; color: #10b981; font-size: 13px;")
        basic_layout.addWidget(self.chk_enabled)

        # 源目录
        row_src = QHBoxLayout()
        lbl_src = QLabel("源目录(Ramdisk):")
        lbl_src.setFixedWidth(110)
        self.txt_src = QLineEdit(self.sync_config.source_dir)
        self.txt_src.textChanged.connect(self._on_source_dir_changed)
        btn_browse_src = QPushButton("📂 浏览目录...")
        btn_browse_src.clicked.connect(self._browse_source)
        btn_detect_src = QPushButton("⚡ 自动探测")
        btn_detect_src.setToolTip("自动探测系统中挂载的 RamDisk 盘符或内存盘目录")
        btn_detect_src.clicked.connect(self._auto_detect_source)
        row_src.addWidget(lbl_src)
        row_src.addWidget(self.txt_src, stretch=1)
        row_src.addWidget(btn_browse_src)
        row_src.addWidget(btn_detect_src)
        basic_layout.addLayout(row_src)

        # 目标备份目录
        row_tgt = QHBoxLayout()
        lbl_tgt = QLabel("目标备份位置:")
        lbl_tgt.setFixedWidth(110)
        self.txt_tgt = QLineEdit(self.sync_config.target_dir)
        btn_browse_tgt = QPushButton("📂 浏览目录...")
        btn_browse_tgt.clicked.connect(self._browse_target)
        btn_open_tgt = QPushButton("📂 打开目录")
        btn_open_tgt.setToolTip("在资源管理器中直接打开目标备份目录")
        btn_open_tgt.clicked.connect(self._open_target_dir)
        row_tgt.addWidget(lbl_tgt)
        row_tgt.addWidget(self.txt_tgt, stretch=1)
        row_tgt.addWidget(btn_browse_tgt)
        row_tgt.addWidget(btn_open_tgt)
        basic_layout.addLayout(row_tgt)

        layout.addWidget(gb_basic)

        # 2. 同步模式与多选文件管理 GroupBox
        gb_files = QGroupBox("📄 同步文件多选管理 (按需挑选，拒绝全部盲目同步)")
        files_layout = QVBoxLayout(gb_files)
        files_layout.setSpacing(6)

        # 模式切换单选按钮
        mode_box = QHBoxLayout()
        self.rb_specific = QRadioButton("🔘 【推荐】浏览多选指定文件 (仅同步下方列表中的文件)")
        self.rb_all = QRadioButton("🔘 同步源目录下全部匹配文件")
        self.rb_specific.setChecked(self.sync_config.sync_scope == "specific_files")
        self.rb_all.setChecked(self.sync_config.sync_scope != "specific_files")
        self.rb_specific.toggled.connect(self._on_sync_scope_toggled)
        mode_box.addWidget(self.rb_specific)
        mode_box.addWidget(self.rb_all)
        mode_box.addStretch()
        files_layout.addLayout(mode_box)

        # 多选文件操作工具栏
        self.files_toolbar = QHBoxLayout()
        self.btn_add_files = QPushButton("➕ 浏览文件夹多选文件(Ctrl/Shift)...")
        self.btn_add_files.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        self.btn_add_files.setToolTip("打开文件浏览窗口，按住 Ctrl 或 Shift 键可多选多个需要同步的关键文件")
        self.btn_add_files.clicked.connect(self._browse_and_add_files)

        self.btn_scan_add = QPushButton("🔍 快速添加源目录量化文件")
        self.btn_scan_add.setToolTip("自动扫描源目录下的 .h5/.json/.pkl/.csv 文件并加入待同步列表")
        self.btn_scan_add.clicked.connect(self._scan_and_add_source_files)

        self.btn_remove_file = QPushButton("❌ 移除选中")
        self.btn_remove_file.clicked.connect(self._remove_selected_files)

        self.btn_clear_files = QPushButton("🧹 清空列表")
        self.btn_clear_files.clicked.connect(self._clear_files_list)

        self.files_toolbar.addWidget(self.btn_add_files)
        self.files_toolbar.addWidget(self.btn_scan_add)
        self.files_toolbar.addWidget(self.btn_remove_file)
        self.files_toolbar.addWidget(self.btn_clear_files)
        self.files_toolbar.addStretch()
        files_layout.addLayout(self.files_toolbar)

        # 待同步文件列表展示
        self.list_files = QListWidget()
        self.list_files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_files.setFixedHeight(130)
        files_layout.addWidget(self.list_files)

        self.lbl_files_summary = QLabel("暂未添加任何文件")
        self.lbl_files_summary.setStyleSheet("color: #94a3b8; font-size: 11px;")
        files_layout.addWidget(self.lbl_files_summary)

        # 通配符输入（当切到全量模式时生效）
        self.row_pat = QHBoxLayout()
        lbl_pat = QLabel("全目录通配符:")
        lbl_pat.setFixedWidth(110)
        self.txt_patterns = QLineEdit(", ".join(self.sync_config.file_patterns))
        self.txt_patterns.setPlaceholderText("*.h5, *.json, *.pkl, *.csv, *.txt, *.db")
        self.row_pat.addWidget(lbl_pat)
        self.row_pat.addWidget(self.txt_patterns, stretch=1)
        files_layout.addLayout(self.row_pat)

        layout.addWidget(gb_files)

        # 3. 调度与时段规则 GroupBox
        gb_schedule = QGroupBox("⏰ 调度周期与交易时段约束")
        sched_layout = QVBoxLayout(gb_schedule)
        sched_layout.setSpacing(6)

        row_int = QHBoxLayout()
        lbl_int = QLabel("同步巡检间隔:")
        lbl_int.setFixedWidth(110)
        self.spn_interval = QtWidgets.QSpinBox()
        self.spn_interval.setRange(5, 3600)
        self.spn_interval.setSingleStep(5)
        self.spn_interval.setValue(self.sync_config.sync_interval_sec)
        self.spn_interval.setSuffix(" 秒")
        self.spn_interval.setFixedWidth(100)
        lbl_int_tip = QLabel("（仅当选定文件 mtime/大小变动时才会真正触发写入备份）")
        lbl_int_tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        row_int.addWidget(lbl_int)
        row_int.addWidget(self.spn_interval)
        row_int.addWidget(lbl_int_tip, stretch=1)
        sched_layout.addLayout(row_int)

        row_checks = QHBoxLayout()
        self.chk_workdays = QCheckBox("仅在工作日/交易日执行")
        self.chk_workdays.setChecked(self.sync_config.only_workdays)
        self.chk_trading_hours = QCheckBox("仅在指定交易时段执行")
        self.chk_trading_hours.setChecked(self.sync_config.only_trading_hours)
        row_checks.addWidget(self.chk_workdays)
        row_checks.addWidget(self.chk_trading_hours)
        row_checks.addStretch()
        sched_layout.addLayout(row_checks)

        # 交易时段输入
        row_th = QHBoxLayout()
        lbl_th = QLabel("交易时段区间:")
        lbl_th.setFixedWidth(110)
        th_str = ", ".join([f"{slot[0]}-{slot[1]}" for slot in self.sync_config.trading_hours if len(slot) == 2])
        self.txt_trading_hours = QLineEdit(th_str)
        self.txt_trading_hours.setPlaceholderText("09:15-11:35, 13:00-15:10")
        row_th.addWidget(lbl_th)
        row_th.addWidget(self.txt_trading_hours, stretch=1)
        sched_layout.addLayout(row_th)

        layout.addWidget(gb_schedule)

        # 4. 备份模式与安全机制
        gb_safe = QGroupBox("🛡️ 备份模式与安全机制")
        safe_layout = QHBoxLayout(gb_safe)
        safe_layout.setSpacing(8)

        lbl_mode = QLabel("存储模式:")
        self.cb_backup_mode = QComboBox()
        self.cb_backup_mode.addItem("📅 每日日期归档 (按年月日创建文件夹，当天内覆盖最新)", "date_folder")
        self.cb_backup_mode.addItem("⭐ 【推荐】差异快照版本归档 (按日归档 + 变动保留历史时间戳版本)", "diff_snapshot")
        self.cb_backup_mode.addItem("🪞 镜像覆盖 (直接更新目标根目录最新单份)", "mirror")
        
        saved_mode = getattr(self.sync_config, "backup_mode", "date_folder")
        if saved_mode == "diff_snapshot":
            self.cb_backup_mode.setCurrentIndex(1)
        elif saved_mode == "mirror":
            self.cb_backup_mode.setCurrentIndex(2)
        else:
            self.cb_backup_mode.setCurrentIndex(0)
            
        safe_layout.addWidget(lbl_mode)
        safe_layout.addWidget(self.cb_backup_mode)

        self.lbl_keep_days = QLabel("保留历史:")
        self.spn_keep_days = QSpinBox()
        self.spn_keep_days.setRange(0, 365)
        self.spn_keep_days.setValue(getattr(self.sync_config, "keep_backup_days", 7))
        self.spn_keep_days.setSuffix(" 天 (0为永久)")
        self.spn_keep_days.setToolTip("自动清理超过此天数的历史日期归档文件夹，设置为 0 表示不限制天数永久保留")
        safe_layout.addWidget(self.lbl_keep_days)
        safe_layout.addWidget(self.spn_keep_days)

        self.chk_atomic = QCheckBox("原子安全替换 (先写临时文件后原子替换)")
        self.chk_atomic.setChecked(self.sync_config.atomic_swap)
        safe_layout.addWidget(self.chk_atomic)

        self.chk_log_enabled = QCheckBox("开启详细同步日志 (调试模式 · 自动持久化并在主控制台记录每次巡检)")
        self.chk_log_enabled.setChecked(getattr(self.sync_config, "log_enabled", False))
        self.chk_log_enabled.toggled.connect(self._on_log_enabled_toggled)
        safe_layout.addWidget(self.chk_log_enabled)

        safe_layout.addStretch()

        self.cb_backup_mode.currentIndexChanged.connect(self._on_backup_mode_changed)
        self._on_backup_mode_changed()

        layout.addWidget(gb_safe)

        # 5. 同步测试与实时日志
        gb_log = QGroupBox("📋 同步测试与诊断日志")
        log_layout = QVBoxLayout(gb_log)
        log_layout.setSpacing(6)

        btn_row = QHBoxLayout()
        self.btn_sync_test = QPushButton("⚡ 立即执行同步测试 (增量)")
        self.btn_sync_test.setStyleSheet("background-color: #0ea5e9; font-weight: bold;")
        self.btn_sync_test.clicked.connect(lambda: self._execute_test_sync(force=False))
        
        self.btn_force_test = QPushButton("🚀 强制全量同步")
        self.btn_force_test.setStyleSheet("background-color: #ea580c; font-weight: bold;")
        self.btn_force_test.clicked.connect(lambda: self._execute_test_sync(force=True))
        
        btn_row.addWidget(self.btn_sync_test)
        btn_row.addWidget(self.btn_force_test)
        btn_row.addStretch()
        log_layout.addLayout(btn_row)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(75)
        self.txt_log.setPlaceholderText("点击【立即执行同步测试】可在此查看扫描文件、指纹比对与同步详情...")
        log_layout.addWidget(self.txt_log)

        layout.addWidget(gb_log)

        # 6. 底部保存与取消按钮
        bottom_box = QHBoxLayout()
        bottom_box.addStretch()
        
        self.btn_save = QPushButton("💾 保存并应用配置")
        self.btn_save.setStyleSheet("background-color: #10b981; font-weight: bold; padding: 6px 16px;")
        self.btn_save.clicked.connect(self._save_and_apply)
        
        self.btn_cancel = QPushButton("❌ 取消")
        self.btn_cancel.clicked.connect(self.reject)
        
        bottom_box.addWidget(self.btn_save)
        bottom_box.addWidget(self.btn_cancel)
        layout.addLayout(bottom_box)

        # 初始化待同步文件列表数据
        self._populate_files_list(self.sync_config.specific_files)
        self._update_ui_state()

    def _on_sync_scope_toggled(self):
        self._update_ui_state()

    def _update_ui_state(self):
        is_specific = self.rb_specific.isChecked()
        self.list_files.setEnabled(is_specific)
        self.btn_add_files.setEnabled(is_specific)
        self.btn_scan_add.setEnabled(is_specific)
        self.btn_remove_file.setEnabled(is_specific)
        self.btn_clear_files.setEnabled(is_specific)
        self.txt_patterns.setEnabled(not is_specific)

    def _populate_files_list(self, files_list: list):
        self.list_files.clear()
        src_root = self.txt_src.text().strip() if hasattr(self, 'txt_src') else self.sync_config.source_dir
        
        total_size = 0
        valid_count = 0

        for f_p in files_list:
            if not f_p:
                continue
            abs_p = f_p if os.path.isabs(f_p) else os.path.join(src_root, f_p)
            exists = os.path.exists(abs_p) and os.path.isfile(abs_p)
            
            size_str = "文件不存在"
            if exists:
                try:
                    sz = os.path.getsize(abs_p)
                    total_size += sz
                    valid_count += 1
                    if sz > 1024 * 1024 * 1024:
                        size_str = f"{sz / (1024*1024*1024):.2f} GB"
                    elif sz > 1024 * 1024:
                        size_str = f"{sz / (1024*1024):.1f} MB"
                    elif sz > 1024:
                        size_str = f"{sz / 1024:.1f} KB"
                    else:
                        size_str = f"{sz} B"
                except Exception:
                    size_str = "就绪"

            rel_p = f_p
            if src_root and exists and abs_p.startswith(src_root):
                try:
                    rel_p = os.path.relpath(abs_p, src_root)
                except Exception:
                    rel_p = os.path.basename(abs_p)

            item = QListWidgetItem(f"📄 {rel_p}  ({size_str})")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, rel_p)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            self.list_files.addItem(item)

        size_mb = total_size / (1024 * 1024)
        self.lbl_files_summary.setText(f"📋 共添加 {self.list_files.count()} 个文件 (其中 {valid_count} 个就绪，合计 {size_mb:.2f} MB)")

    def _get_current_files_list(self) -> list:
        res = []
        for i in range(self.list_files.count()):
            item = self.list_files.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                p = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if p:
                    res.append(p)
        return res

    def _browse_and_add_files(self):
        """打开文件浏览器，支持按住 Ctrl/Shift 键多选文件加入列表"""
        start_dir = self.txt_src.text().strip()
        if not start_dir or not os.path.exists(start_dir):
            start_dir = self.sync_config.source_dir
        if not os.path.exists(start_dir):
            start_dir = ""

        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "浏览文件夹并多选需要同步的 RamDisk 文件 (按住 Ctrl 或 Shift 可多选)",
            start_dir,
            "量化数据与关键文件 (*.h5 *.hdf5 *.db *.json *.pkl *.csv *.txt *.parquet);;所有文件 (*.*)"
        )
        if not files:
            return

        current_list = self._get_current_files_list()
        src_root = self.txt_src.text().strip()

        # 如果源目录为空，自动以选定文件的所在目录作为源目录
        if (not src_root or not os.path.exists(src_root)) and files:
            src_root = os.path.dirname(files[0])
            self.txt_src.setText(src_root)

        added_count = 0
        for f in files:
            try:
                rel_p = os.path.relpath(f, src_root) if src_root and f.startswith(src_root) else os.path.basename(f)
            except Exception:
                rel_p = os.path.basename(f)
            
            if rel_p not in current_list:
                current_list.append(rel_p)
                added_count += 1

        self._populate_files_list(current_list)
        self.txt_log.append(f"➕ [多选添加] 成功添加 {added_count} 个文件至同步列表。")

    def _scan_and_add_source_files(self):
        """自动快速扫描当前源目录中的关键文件"""
        src_root = self.txt_src.text().strip()
        if not src_root or not os.path.exists(src_root):
            QMessageBox.warning(self, "扫描失败", f"源目录不存在或无效:\n{src_root}")
            return

        patterns = ["*.h5", "*.json", "*.pkl", "*.csv", "*.txt", "*.db", "*.parquet"]
        found = []
        try:
            for root, dirs, files in os.walk(src_root):
                dirs[:] = [d for d in dirs if not d.startswith("$") and d.lower() not in ["temp", "tmp", ".git"]]
                for f in files:
                    if f.startswith("~$") or f.endswith(".tmp") or f.endswith(".lock"):
                        continue
                    if any(fnmatch.fnmatch(f, pat) for pat in patterns):
                        abs_p = os.path.join(root, f)
                        rel_p = os.path.relpath(abs_p, src_root)
                        found.append(rel_p)
        except Exception as e:
            QMessageBox.warning(self, "扫描异常", f"扫描源目录异常:\n{e}")
            return

        if not found:
            QMessageBox.information(self, "扫描结果", f"在源目录【{src_root}】中未发现符合规则的量化数据文件。")
            return

        current_list = self._get_current_files_list()
        added_count = 0
        for f in found:
            if f not in current_list:
                current_list.append(f)
                added_count += 1

        self._populate_files_list(current_list)
        self.txt_log.append(f"🔍 [扫描添加] 扫描到 {len(found)} 个量化文件，已新增 {added_count} 个文件至同步列表。")

    def _remove_selected_files(self):
        selected_items = self.list_files.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            row = self.list_files.row(item)
            self.list_files.takeItem(row)
        self._populate_files_list(self._get_current_files_list())

    def _clear_files_list(self):
        self.list_files.clear()
        self.lbl_files_summary.setText("暂未添加任何文件")

    def _on_source_dir_changed(self, text):
        pass

    def _browse_source(self):
        dir_p = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 RamDisk 源目录", self.txt_src.text().strip())
        if dir_p:
            self.txt_src.setText(os.path.abspath(dir_p))
            # 刷新列表中的大小与存在性
            self._populate_files_list(self._get_current_files_list())

    def _auto_detect_source(self):
        from .sync_engine import detect_default_ramdisk_dir
        detected = detect_default_ramdisk_dir()
        self.txt_src.setText(detected)
        self.txt_log.append(f"⚡ [探测] 系统检测到的推荐 RamDisk 目录: {detected}")
        self._populate_files_list(self._get_current_files_list())

    def _browse_target(self):
        dir_p = QtWidgets.QFileDialog.getExistingDirectory(self, "选择目标备份目录", self.txt_tgt.text().strip())
        if dir_p:
            self.txt_tgt.setText(os.path.abspath(dir_p))

    def _open_target_dir(self):
        # 智能直接打开当前实际生效的目标备份目录（如 D:\Ramdisk_Backup\20260828）
        tgt_p = self.txt_tgt.text().strip()
        if not tgt_p:
            tgt_p = self.sync_config.target_dir
        
        mode = self.cb_backup_mode.currentData() if hasattr(self, 'cb_backup_mode') else getattr(self.sync_config, "backup_mode", "date_folder")
        effective_p = tgt_p
        if mode in ["date_folder", "diff_snapshot"] and tgt_p:
            today_str = datetime.datetime.now().strftime("%Y%m%d")
            effective_p = os.path.join(tgt_p, today_str)

        if not os.path.exists(effective_p):
            try:
                os.makedirs(effective_p, exist_ok=True)
            except Exception:
                effective_p = tgt_p

        try:
            os.startfile(effective_p)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开目录:\n{e}")

    def _parse_trading_hours(self) -> list:
        raw = self.txt_trading_hours.text().strip()
        slots = []
        if raw:
            parts = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
            for p in parts:
                if "-" in p:
                    s, e = p.split("-", 1)
                    s, e = s.strip(), e.strip()
                    if s and e:
                        slots.append([s, e])
        if not slots:
            slots = [["09:15", "11:35"], ["13:00", "15:10"]]
        return slots

    def _parse_patterns(self) -> list:
        raw = self.txt_patterns.text().strip()
        pats = []
        if raw:
            pats = [p.strip() for p in raw.replace("，", ",").replace(";", ",").split(",") if p.strip()]
        if not pats:
            pats = ["*.h5", "*.json", "*.pkl", "*.csv", "*.txt", "*.db", "*.parquet"]
        return pats

    def _execute_test_sync(self, force: bool = False):
        """执行测试同步"""
        src = self.txt_src.text().strip()
        tgt = self.txt_tgt.text().strip()
        
        if not os.path.exists(src):
            self.txt_log.append(f"❌ [错误] 源目录不存在: {src}")
            return

        self.sync_engine.config.enabled = True
        self.sync_engine.config.source_dir = src
        self.sync_engine.config.target_dir = tgt
        self.sync_engine.config.sync_scope = "specific_files" if self.rb_specific.isChecked() else "all_directory"
        self.sync_engine.config.specific_files = self._get_current_files_list()
        self.sync_engine.config.file_patterns = self._parse_patterns()
        self.sync_engine.config.backup_mode = self.cb_backup_mode.currentData() or "date_folder"
        self.sync_engine.config.atomic_swap = self.chk_atomic.isChecked()

        scope_desc = f"多选指定 {len(self.sync_engine.config.specific_files)} 个文件" if self.sync_engine.config.sync_scope == "specific_files" else "全目录通配符扫描"
        start_msg = f"🚀 开始测试 ({'强制全量' if force else '智能增量'} · 模式: {scope_desc})..."
        self.txt_log.append(start_msg)
        if self.parent() and hasattr(self.parent(), "log"):
            self.parent().log(f"🚀 [RamDisk Sync] {start_msg}")
            
        res = self.sync_engine.sync_once(force=force, ignore_time_filter=True)
        
        status_tag = "✅" if res.get("status") == "ok" else "⚠️"
        res_msg = f"{status_tag} {res.get('message')}"
        self.txt_log.append(res_msg)
        if self.parent() and hasattr(self.parent(), "log"):
            self.parent().log(f"💾 [RamDisk Sync] {res_msg}")

        if res.get("synced_files"):
            for f in res["synced_files"]:
                self.txt_log.append(f"   -> 写入: {f}")
        if res.get("failed_files"):
            for f, err in res["failed_files"]:
                self.txt_log.append(f"   ❌ 失败: {f} ({err})")

    def _on_log_enabled_toggled(self, checked: bool):
        """复选框状态改变时，即时自动持久化保存日志开关状态"""
        self.sync_config.log_enabled = checked
        self.sync_engine.config.log_enabled = checked
        self.sync_config.save()
        state_str = "已开启 (将在主窗口控制台输出每次巡检明细)" if checked else "已关闭 (保持静默，仅同步变动/错误时提示)"
        self.txt_log.append(f"ℹ️ [日志开关] 详细同步日志状态{state_str}，已自动持久化保存。")
        if self.parent() and hasattr(self.parent(), "log"):
            self.parent().log(f"ℹ️ [RamDisk Sync] 详细同步日志状态{state_str}")

    def _on_backup_mode_changed(self):
        """当存储模式改变时，动态启用/禁用保留天数配置控件"""
        mode = self.cb_backup_mode.currentData()
        is_date_mode = mode in ["date_folder", "diff_snapshot"]
        self.lbl_keep_days.setEnabled(is_date_mode)
        self.spn_keep_days.setEnabled(is_date_mode)

    def _save_and_apply(self):
        src = self.txt_src.text().strip()
        tgt = self.txt_tgt.text().strip()

        if not src:
            QMessageBox.warning(self, "参数错误", "请输入或选择 RamDisk 源目录！")
            return
        if not tgt:
            QMessageBox.warning(self, "参数错误", "请输入或选择目标备份目录！")
            return

        self.sync_config.enabled = self.chk_enabled.isChecked()
        self.sync_config.source_dir = src
        self.sync_config.target_dir = tgt
        self.sync_config.sync_scope = "specific_files" if self.rb_specific.isChecked() else "all_directory"
        self.sync_config.specific_files = self._get_current_files_list()
        self.sync_config.sync_interval_sec = self.spn_interval.value()
        self.sync_config.only_workdays = self.chk_workdays.isChecked()
        self.sync_config.only_trading_hours = self.chk_trading_hours.isChecked()
        self.sync_config.trading_hours = self._parse_trading_hours()
        self.sync_config.file_patterns = self._parse_patterns()
        self.sync_config.backup_mode = self.cb_backup_mode.currentData() or "date_folder"
        self.sync_config.keep_backup_days = self.spn_keep_days.value()
        self.sync_config.atomic_swap = self.chk_atomic.isChecked()
        self.sync_config.log_enabled = self.chk_log_enabled.isChecked()

        success = self.sync_config.save()
        if success:
            self.sync_engine.config = self.sync_config
            if self.sync_worker:
                if self.sync_config.enabled:
                    if hasattr(self.sync_worker, "isRunning") and not self.sync_worker.isRunning():
                        self.sync_worker.start()
                    else:
                        self.sync_worker.trigger_sync_now(force=False)
                else:
                    self.sync_worker.stop()
            
            scope_info = f"多选指定 {len(self.sync_config.specific_files)} 个文件" if self.sync_config.sync_scope == "specific_files" else "全目录通配符扫描"
            QMessageBox.information(
                self, 
                "保存成功", 
                f"RamDisk 自动同步配置已成功保存并生效！\n\n"
                f"• 状态: {'开启' if self.sync_config.enabled else '停用'}\n"
                f"• 同步范围: {scope_info}\n"
                f"• 巡检间隔: 每 {self.sync_config.sync_interval_sec} 秒\n"
                f"• 源目录: {self.sync_config.source_dir}\n"
                f"• 备份目录: {self.sync_config.target_dir}\n"
                f"• 仅交易时段: {'是' if self.sync_config.only_trading_hours else '否'}\n"
                f"• 详细日志: {'已开启' if self.sync_config.log_enabled else '已关闭'}"
            )
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "配置文件写盘失败，请检查文件写权限！")


class TopologyCanvasWidget(QWidget):
    """
    多显示器物理拓扑可视化绘制画布
    根据各显示器的相对坐标与尺寸，等比例居中绘制屏幕分布几何图
    """
    def __init__(self, monitors=None, parent=None):
        super().__init__(parent)
        self.monitors = monitors or []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #121216; border: 1px solid #2d2d38; border-radius: 6px;")

    def set_monitors(self, monitors):
        self.monitors = monitors or []
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
        from PyQt6.QtCore import QRectF, Qt

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 绘制背景深色渐变与微网格
        bg_gradient = QLinearGradient(0, 0, 0, h)
        bg_gradient.setColorAt(0.0, QColor("#141419"))
        bg_gradient.setColorAt(1.0, QColor("#0d0d11"))
        painter.fillRect(0, 0, w, h, bg_gradient)

        # 绘制浅微网格点
        grid_pen = QPen(QColor(255, 255, 255, 12))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        grid_step = 24
        for gx in range(0, w, grid_step):
            painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, grid_step):
            painter.drawLine(0, gy, w, gy)

        if not self.monitors:
            painter.setPen(QColor("#6b7280"))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "暂无显示器物理拓扑数据")
            return

        # 计算所有显示器的虚拟桌面坐标范围
        min_x = min(m.get("x", 0) for m in self.monitors)
        min_y = min(m.get("y", 0) for m in self.monitors)
        max_x = max(m.get("x", 0) + m.get("width", 1920) for m in self.monitors)
        max_y = max(m.get("y", 0) + m.get("height", 1080) for m in self.monitors)

        total_w = max(1, max_x - min_x)
        total_h = max(1, max_y - min_y)

        # 留白 padding
        padding = 32
        avail_w = max(10, w - padding * 2)
        avail_h = max(10, h - padding * 2)

        # 统一比例尺
        scale = min(avail_w / total_w, avail_h / total_h)
        draw_total_w = total_w * scale
        draw_total_h = total_h * scale

        offset_x = (w - draw_total_w) / 2.0
        offset_y = (h - draw_total_h) / 2.0

        # 逐个绘制显示器矩形
        for idx, m in enumerate(self.monitors):
            mx = m.get("x", 0)
            my = m.get("y", 0)
            mw = m.get("width", 1920)
            mh = m.get("height", 1080)
            is_pri = m.get("is_primary", False)
            scale_factor = m.get("scale", 1.0)
            dev_name = m.get("device_name", f"DISPLAY{idx+1}")
            model_name = m.get("model_name", "") or dev_name

            rect_x = offset_x + (mx - min_x) * scale
            rect_y = offset_y + (my - min_y) * scale
            rect_w = mw * scale
            rect_h = mh * scale
            rect = QRectF(rect_x, rect_y, rect_w, rect_h)

            # 主屏使用翡翠绿/天空蓝渐变，副屏使用深青/深蓝灰
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if is_pri:
                grad.setColorAt(0.0, QColor(14, 165, 233, 160))
                grad.setColorAt(1.0, QColor(16, 185, 129, 140))
                border_pen = QPen(QColor("#38bdf8"), 2.5)
            else:
                grad.setColorAt(0.0, QColor(30, 41, 59, 190))
                grad.setColorAt(1.0, QColor(15, 23, 42, 210))
                border_pen = QPen(QColor("#64748b"), 1.8)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(rect, 8.0, 8.0)

            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 8.0, 8.0)

            # 绘制屏幕内部文本标注
            painter.setPen(QColor("#ffffff"))
            font_title = QFont("Microsoft YaHei", max(9, int(min(rect_w, rect_h) * 0.085)), QFont.Weight.Bold)
            painter.setFont(font_title)

            pri_tag = " [👑 主屏]" if is_pri else f" [设备 {idx+1}]"
            # 优先显示厂商型号
            title_text = f"{model_name}{pri_tag}"
            res_text = f"{mw}x{mh} (@{int(scale_factor*100)}%)"
            pos_text = f"坐标: ({mx}, {my})"

            text_rect_top = QRectF(rect_x + 4, rect_y + 6, rect_w - 8, rect_h * 0.35)
            painter.drawText(text_rect_top, Qt.AlignmentFlag.AlignCenter, title_text)

            painter.setFont(QFont("Microsoft YaHei", max(8, int(min(rect_w, rect_h) * 0.075))))
            painter.setPen(QColor("#e2e8f0"))
            text_rect_mid = QRectF(rect_x + 4, rect_y + rect_h * 0.36, rect_w - 8, rect_h * 0.3)
            painter.drawText(text_rect_mid, Qt.AlignmentFlag.AlignCenter, res_text)

            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Microsoft YaHei", max(7, int(min(rect_w, rect_h) * 0.065))))
            text_rect_bot = QRectF(rect_x + 4, rect_y + rect_h * 0.66, rect_w - 8, rect_h * 0.3)
            painter.drawText(text_rect_bot, Qt.AlignmentFlag.AlignCenter, pos_text)


class DisplayTopologyPreviewDialog(QDialog):
    """
    多显示器物理拓扑可视化预览与恢复对话框
    """
    def __init__(self, config_info, parent=None):
        super().__init__(parent)
        self.config_info = config_info or {}
        self.filepath = self.config_info.get("filepath", "")
        self.filename = self.config_info.get("filename", os.path.basename(self.filepath))
        self.monitors = self.config_info.get("monitors", [])
        
        self.setWindowTitle(f"👁️ 显示器物理拓扑预览 - {self.filename}")
        self.resize(720, 580)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a22;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QTableWidget {
                background-color: #141419;
                border: 1px solid #2d2d38;
                border-radius: 4px;
                color: #e2e8f0;
                gridline-color: #2a2a36;
            }
            QHeaderView::section {
                background-color: #24242e;
                color: #38bdf8;
                padding: 5px;
                border: 1px solid #2d2d38;
                font-weight: bold;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
            }
            QPushButton#btnRestoreNow {
                background-color: #ea580c;
                border: none;
                font-weight: bold;
                color: white;
            }
            QPushButton#btnRestoreNow:hover {
                background-color: #c2410c;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部概览栏
        top_box = QHBoxLayout()
        icon_lbl = QLabel("🖥️")
        icon_lbl.setStyleSheet("font-size: 24px;")
        top_box.addWidget(icon_lbl)
        
        m_count = len(self.monitors)
        pri = next((m for m in self.monitors if m.get("is_primary")), self.monitors[0] if self.monitors else {})
        pri_model = pri.get("model_name", "") or pri.get("device_name", "")
        pri_desc = f"{pri_model} ({pri.get('width', 0)}x{pri.get('height', 0)})" if pri else "未知"
        
        info_vbox = QVBoxLayout()
        title_lbl = QLabel(f"<b>拓扑配置文件:</b> {self.filename}")
        title_lbl.setStyleSheet("color: #38bdf8; font-size: 14px;")
        sub_lbl = QLabel(f"显示器总数: {m_count} 块 | 主屏幕: {pri_desc} | 路径: {self.filepath}")
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        sub_lbl.setWordWrap(True)
        info_vbox.addWidget(title_lbl)
        info_vbox.addWidget(sub_lbl)
        top_box.addLayout(info_vbox)
        top_box.addStretch()
        layout.addLayout(top_box)

        # 若是数据布局重复副本，增加醒目的黄色警示提示条
        if self.config_info.get("is_duplicate"):
            dup_of = self.config_info.get("duplicate_of", "其他配置文件")
            dup_banner = QLabel(f"⚠️ <b>注意：</b> 本文件的显示器物理拓扑数据与 <b>[{dup_of}]</b> 完全一致，属于重复备份副本。")
            dup_banner.setStyleSheet("""
                background-color: #451a03; 
                border: 1px solid #b45309; 
                border-radius: 4px; 
                color: #fcd34d; 
                padding: 6px 10px; 
                font-size: 12px;
            """)
            dup_banner.setWordWrap(True)
            layout.addWidget(dup_banner)

        # 中间：可视化多屏排布几何画布
        layout.addWidget(QLabel("<b>📐 屏幕相对排布空间几何示意图 (自适应比例):</b>"))
        self.canvas = TopologyCanvasWidget(self.monitors, self)
        layout.addWidget(self.canvas, stretch=1)

        # 下方：显示器参数列表表格
        layout.addWidget(QLabel("<b>📋 显示器硬件型号与排布清单:</b>"))
        self.table = QTableWidget(len(self.monitors), 6, self)
        self.table.setHorizontalHeaderLabels(["厂商型号 / 设备名", "硬件 PNP ID", "物理分辨率", "DPI缩放比", "起始坐标 (X, Y)", "主屏幕"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setFixedHeight(120)

        for row, m in enumerate(self.monitors):
            dev = m.get("device_name", f"DISPLAY{row+1}")
            model = m.get("model_name", "") or dev
            pnp = m.get("pnp_id", "") or "-"
            pw = m.get("width", 1920)
            ph = m.get("height", 1080)
            sc = m.get("scale", 1.0)
            mx = m.get("x", 0)
            my = m.get("y", 0)
            is_pri = m.get("is_primary", False)

            dev_display = f"{model} ({dev})" if model != dev else dev
            self.table.setItem(row, 0, QTableWidgetItem(dev_display))
            self.table.setItem(row, 1, QTableWidgetItem(pnp))
            self.table.setItem(row, 2, QTableWidgetItem(f"{pw} x {ph}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{int(sc * 100)}% ({sc})"))
            self.table.setItem(row, 4, QTableWidgetItem(f"({mx}, {my})"))
            pri_item = QTableWidgetItem("👑 主屏" if is_pri else "副屏")
            if is_pri:
                pri_item.setForeground(QColor("#38bdf8"))
            self.table.setItem(row, 5, pri_item)

        layout.addWidget(self.table)

        # 底部操作栏
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)

        self.btn_restore = QPushButton("🔄 恢复应用此拓扑配置")
        self.btn_restore.setObjectName("btnRestoreNow")
        self.btn_restore.clicked.connect(self.restore_current_topology)

        bottom_bar.addWidget(self.btn_close)
        bottom_bar.addWidget(self.btn_restore)
        layout.addLayout(bottom_bar)

    def restore_current_topology(self):
        """在预览对话框中恢复应用当前拓扑，包含详细二次确认"""
        m_count = len(self.monitors)
        reply = QMessageBox.question(
            self,
            "确认恢复显示器物理拓扑",
            f"是否确认将当前桌面显示器排布恢复为此配置？\n\n"
            f"【配置文件】: {self.filename}\n"
            f"【显示器数】: {m_count} 块屏幕\n"
            f"【文件路径】: {self.filepath}\n\n"
            f"⚠️ 恢复操作会刷新系统显示设置并重新定位所有连接屏幕。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = core.restore_display_configuration(self.filepath)
            if success:
                QMessageBox.information(self, "恢复完成", msg)
                self.accept()
            else:
                QMessageBox.warning(self, "恢复提示", msg)


class ManagerHotkeyThread(threading.Thread):
    """
    独立子线程：通过 RegisterHotKey(None, ...) 将热键注册到本线程消息队列。
    使用 PeekMessageW 非阻塞轮询，捕获 WM_HOTKEY 后通过 Qt 信号线程安全地通知主 UI。
    彻底避免在 nativeEvent 中操作原始指针导致的 Access Violation 崩溃。
    """
    WM_HOTKEY = 0x0312
    HOTKEY_ID = 0xAFC0

    def __init__(self, toggle_callback):
        super().__init__(daemon=True)
        self._toggle_callback = toggle_callback
        self._running = False
        self._modifiers = 0
        self._vk = 0
        self._registered = False

    def set_hotkey(self, modifiers, vk):
        self._modifiers = modifiers
        self._vk = vk

    def run(self):
        import ctypes
        import ctypes.wintypes
        self._running = True
        # RegisterHotKey(None, id, mod, vk) -> 注册到本线程消息队列
        res = ctypes.windll.user32.RegisterHotKey(
            None, self.HOTKEY_ID, self._modifiers, self._vk
        )
        self._registered = bool(res)
        if not self._registered:
            return  # 注册失败直接退出

        msg = ctypes.wintypes.MSG()
        while self._running:
            # PeekMessageW 非阻塞，无需 GetMessage 阻塞等待
            if ctypes.windll.user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE=1
            ):
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    try:
                        self._toggle_callback()
                    except Exception:
                        pass
            else:
                import time
                time.sleep(0.05)  # 空闲时降低 CPU 占用

        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False

    def stop(self):
        self._running = False


class WindowPosManagerUI(QMainWindow, WindowMixin):
    """主窗口：窗口坐标及分布管理器"""
    toggle_ui_signal = QtCore.pyqtSignal()
    show_ui_signal = QtCore.pyqtSignal()
    log_signal = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("股票交易终端 - 窗口坐标分类管理器")
        self._wm_show_msg_id = core.get_wm_show_msg_id()
        
        self.scale_factor = self._get_dpi_scale_factor()
            
        self._hotkey_hook = None
        self.config_manager = core.ConfigManager()
        self.current_bound_hotkey = self.config_manager.config_data.get("global_hotkey", "ctrl+alt+w")
        
        # 自动检测/添加静态路由，并保存结果以在 UI 准备好后输出日志
        try:
            success, route_msg = core.check_and_add_route(self.config_manager)
            self.startup_route_msg = route_msg
        except Exception as e:
            self.startup_route_msg = f"检测静态路由异常: {e}"

        self.init_ui()
        
        # 恢复上次保存的窗口位置与尺寸
        self.load_window_position_qt(self, "WindowPosManagerUI", default_width=980, default_height=700)
        
        self.load_screen_info()
        self.refresh_resolutions_combo()
        self.setup_tray_icon()
        self.bind_hotkey(self.current_bound_hotkey)
        self.toggle_ui_signal.connect(self.toggle_visibility)
        self.show_ui_signal.connect(self._force_show_and_top)
        self.log_signal.connect(self.log)
        self.setup_single_instance_server()
        
        # 记录当前屏幕拓扑指纹并配置屏幕热插拔/拓扑动态监听（免冷启动程序）
        self._last_topology_signature = core.get_screen_topology_signature()
        self._setup_screen_topology_listener()
        
        if hasattr(self, 'startup_route_msg') and self.startup_route_msg:
            self.log(f"[Route Startup] {self.startup_route_msg}")
            
        # 自动探测与在后台应用 Acer 硬件性能模式配置 (结合 system uptime 开机冷启动与 startup_delay_seconds 秒数延迟)
        # 🛡️ 严格约束：仅当【当前程序本身】被设置为 Windows 开机自启动，或本次启动带有开机后台静默参数 (-hide) 时才自动调度运行；非自启设置时不用自动运行程序
        try:
            acer_cfg = self.config_manager.get_acer_performance_config()
            is_auto_in_cfg = acer_cfg.get("auto_apply_on_startup", True)
            is_current_autostart = core.is_autostart_enabled_for_current_app()
            is_silent_startup = getattr(self, "start_hidden", False) or ("-hide" in sys.argv or "--hide" in sys.argv)

            if is_auto_in_cfg and (is_current_autostart or is_silent_startup):
                user_delay = int(acer_cfg.get("startup_delay_seconds", 10))
                uptime = core.get_system_uptime()
                sys_cold = core.is_system_cold_boot(300)

                if sys_cold:
                    cold_target_delay = 25
                    actual_delay = max(user_delay, cold_target_delay)
                    self.log(f"⏳ [AutoStart] 检测到系统开机 (Uptime: {uptime:.1f}s)，将在 {actual_delay} 秒后自动调度应用 Acer 性能预设...")
                else:
                    actual_delay = max(0, user_delay)
                    if actual_delay > 0:
                        self.log(f"⏳ [AutoStart] 启动延迟引擎已就绪 (Uptime: {uptime:.1f}s)，将在 {actual_delay} 秒后自动调度应用 Acer 性能预设...")

                delay_ms = max(0, int(actual_delay * 1000))
                QtCore.QTimer.singleShot(delay_ms, lambda: self.apply_acer_performance_async(acer_cfg, custom_msg_prefix="开机自动应用 Acer 性能预设"))
            else:
                if not is_current_autostart and not is_silent_startup:
                    self.log("ℹ️ [AutoStart] 当前程序未配置为开机自启动，跳过后台自动调度。")
        except Exception as e:
            logger.error(f"启动自动应用 Acer 性能模式初始化异常: {e}")

        # 初始化 RamDisk 实时数据自动同步与备份守护引擎
        try:
            self.ramdisk_sync_config = sync_engine.RamDiskSyncConfig()
            self.ramdisk_sync_engine = sync_engine.RamDiskSyncEngine(self.ramdisk_sync_config)
            self.ramdisk_sync_worker = sync_engine.RamDiskSyncWorker(self.ramdisk_sync_engine, self)
            self.ramdisk_sync_worker.sync_completed.connect(self._on_ramdisk_sync_completed)
            self.ramdisk_sync_worker.status_updated.connect(self._on_ramdisk_sync_status_updated)
            if self.ramdisk_sync_config.enabled:
                self.ramdisk_sync_worker.start()
                self.log(f"💾 [RamDisk Sync] 自动同步守护已启动 (每 {self.ramdisk_sync_config.sync_interval_sec} 秒巡检)")
        except Exception as e:
            self.log(f"⚠️ [RamDisk Sync] 初始化同步守护异常: {e}")
            
        # 允许驻留后台
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def setup_single_instance_server(self):
        """建立 Qt QLocalServer 单实例 IPC 本地命名管道服务"""
        try:
            from PyQt6.QtNetwork import QLocalServer
            server_name = core.SINGLE_INSTANCE_SERVER_NAME
            
            # 清理残留的命名管道
            QLocalServer.removeServer(server_name)
            
            self.single_instance_server = QLocalServer(self)
            self.single_instance_server.newConnection.connect(self._on_single_instance_connection)
            if self.single_instance_server.listen(server_name):
                self.log(f"[SingleInstance] 单实例本地 IPC 服务已成功监听: {server_name}")
            else:
                self.log(f"[SingleInstance] 单实例 IPC 监听失败: {self.single_instance_server.errorString()}")
        except Exception as e:
            self.log(f"[SingleInstance] setup_single_instance_server 异常: {e}")

    def _on_single_instance_connection(self):
        client_socket = self.single_instance_server.nextPendingConnection()
        if client_socket:
            client_socket.readyRead.connect(lambda: self._handle_single_instance_data(client_socket))

    def _handle_single_instance_data(self, client_socket):
        try:
            data = client_socket.readAll().data().decode('utf-8', errors='ignore')
            if "WAKEUP" in data:
                self.log("[SingleInstance] 收到跨进程唤醒消息 WAKEUP，正在打开/置顶界面...")
                self.show_ui_signal.emit()
            client_socket.disconnectFromServer()
        except Exception as e:
            self.log(f"[SingleInstance] 管道数据解析异常: {e}")

    def apply_acer_performance_async(self, profile: dict = None, custom_msg_prefix: str = ""):
        """在后台守护线程中异步应用 Acer 性能配置 (用于托盘右键极速响应与全流程详细打点)"""
        def _bg_worker():
            try:
                controller = core.AcerPerformanceController()
                if controller.is_supported():
                    target_profile = profile if profile is not None else self.config_manager.get_acer_performance_config()
                    def _log_cb(msg):
                        self.log_signal.emit(f"[Acer Hardware] {msg}")

                    ok, acer_msg = controller.apply_performance_profile(target_profile, log_cb=_log_cb)
                    prefix = custom_msg_prefix or "应用 Acer 性能模式"
                    msg_str = f"[Acer Hardware] {prefix}: {acer_msg}"
                else:
                    msg_str = "[Acer Hardware] 设备无 Acer WMI 支持，静默跳过性能调优"
                self.log_signal.emit(msg_str)
            except Exception as e:
                logger.error(f"异步执行 Acer 性能模式调优异常: {e}")
                self.log_signal.emit(f"⚠️ [Acer Hardware] 执行 Acer 性能模式调优异常: {e}")

        threading.Thread(target=_bg_worker, daemon=True).start()

    def setup_tray_icon(self):
        """初始化系统托盘图标及右键快捷控制菜单"""
        self.tray_icon = QtWidgets.QSystemTrayIcon(QApplication.instance())
        self.tray_icon.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
        
        self.tray_menu = QtWidgets.QMenu(self)
        show_action = self.tray_menu.addAction("🖥️ 显示主界面")
        show_action.triggered.connect(self._force_show_and_top)
        
        self.tray_menu.addSeparator()
        
        # 🚀 窗口布局快捷控制菜单
        apply_layout_action = self.tray_menu.addAction("🚀 应用当前窗口布局")
        apply_layout_action.triggered.connect(lambda: self.apply_current_layout(show_tray_message=True))
        
        detect_layout_action = self.tray_menu.addAction("🎯 探测并应用推荐布局")
        detect_layout_action.triggered.connect(self.detect_and_apply_layout_from_tray)
        
        self.tray_layout_menu = self.tray_menu.addMenu("📐 切换并应用布局方案")
        self.tray_layout_menu.aboutToShow.connect(self._update_tray_layout_submenu)
        
        # 🚀 Acer 硬件性能控制快捷右键菜单
        try:
            controller = core.AcerPerformanceController()
            if controller.is_supported():
                self.tray_menu.addSeparator()
                apply_preset_action = self.tray_menu.addAction("⚡ 应用当前 Acer 性能预设")
                apply_preset_action.triggered.connect(lambda: self.apply_acer_performance_async(custom_msg_prefix="右键托盘极速应用"))
                
                acer_sub_menu = self.tray_menu.addMenu("🚀 Acer 性能极速切换")
                
                # 统一获取用户全局保存的 post_action 处理方式 (hide/close/kill)
                def _get_global_post_action():
                    try:
                        return self.config_manager.get_acer_performance_config().get("post_action", "kill")
                    except Exception:
                        return "kill"

                act_turbo = acer_sub_menu.addAction("🔥 狂暴模式 (Extreme + 最大风扇)")
                act_turbo.triggered.connect(lambda: self.apply_acer_performance_async(
                    {"overclock_mode": "Extreme", "coolboost": True, "fan_mode": "Max", "post_action": _get_global_post_action()},
                    custom_msg_prefix="托盘一键切【狂暴模式】"
                ))

                act_fast = acer_sub_menu.addAction("⚡ 快速模式 (Fast + 自动风扇)")
                act_fast.triggered.connect(lambda: self.apply_acer_performance_async(
                    {"overclock_mode": "Fast", "coolboost": True, "fan_mode": "Auto", "post_action": _get_global_post_action()},
                    custom_msg_prefix="托盘一键切【快速模式】"
                ))

                act_normal = acer_sub_menu.addAction("🍃 默认模式 (Normal + 自动风扇)")
                act_normal.triggered.connect(lambda: self.apply_acer_performance_async(
                    {"overclock_mode": "Default", "coolboost": False, "fan_mode": "Auto", "post_action": _get_global_post_action()},
                    custom_msg_prefix="托盘一键切【默认模式】"
                ))
        except Exception as e:
            logger.error(f"托盘图标 Acer 快捷菜单初始化异常: {e}")

        # 💾 RamDisk 实时数据自动同步与备份快捷菜单
        try:
            self.tray_menu.addSeparator()
            sync_now_action = self.tray_menu.addAction("💾 立即备份 RamDisk 数据")
            sync_now_action.triggered.connect(self._trigger_ramdisk_sync_from_tray)
            
            sync_cfg_action = self.tray_menu.addAction("⚙️ RamDisk 自动同步设置...")
            sync_cfg_action.triggered.connect(self.open_ramdisk_sync_settings)
        except Exception as e:
            logger.error(f"托盘图标 RamDisk 快捷菜单初始化异常: {e}")

        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("❌ 完全退出")
        quit_action.triggered.connect(self.force_quit)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

    def _update_tray_layout_submenu(self):
        """动态构建系统托盘右键中的‘切换并应用方案’子菜单"""
        if not hasattr(self, 'tray_layout_menu'):
            return
        self.tray_layout_menu.clear()
        
        current_res = self.get_current_selected_resolution()
        rec_name = core.detect_display_config_name(self.config_manager)
        
        categories = {
            "single_display": "🖥️ 单屏方案",
            "multi_display": "🖥️🖥️ 多屏方案",
            "custom_special": "⚙️ 特殊方案"
        }
        
        # 1. 探测推荐项
        rec_action = self.tray_layout_menu.addAction(f"🎯 智能推荐: {rec_name}")
        rec_action.triggered.connect(self.detect_and_apply_layout_from_tray)
        self.tray_layout_menu.addSeparator()
        
        # 2. 遍历分类方案
        has_any = False
        for cat_name in self.config_manager.get_categories():
            res_list = self.config_manager.get_resolutions_by_category(cat_name)
            if not res_list:
                continue
            has_any = True
            cat_cn = categories.get(cat_name, cat_name)
            cat_menu = self.tray_layout_menu.addMenu(cat_cn)
            for res in res_list:
                mark = " ✔" if res == current_res else ""
                act = cat_menu.addAction(f"{res}{mark}")
                act.triggered.connect(lambda checked=False, r=res: self.apply_layout_by_name(r, show_tray_message=True))
                
        if not has_any:
            empty_act = self.tray_layout_menu.addAction("(暂无已保存方案)")
            empty_act.setEnabled(False)

    def detect_and_apply_layout_from_tray(self):
        """从托盘右键触发自动探测屏幕并应用推荐布局"""
        self.load_screen_info()
        rec_name = core.detect_display_config_name(self.config_manager)
        self.log(f"[托盘快捷] 探测到推荐配置方案: {rec_name}，正在应用...")
        self.apply_layout_by_name(rec_name, show_tray_message=True)

    def apply_layout_by_name(self, res_name: str, show_tray_message: bool = True):
        """按指定的方案名切换并应用布局"""
        matched = False
        for i in range(self.cb_resolutions.count()):
            data = self.cb_resolutions.itemData(i)
            if data and data[1] == res_name:
                self.cb_resolutions.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self.refresh_resolutions_combo(select_name=res_name)
        
        self.apply_current_layout(show_tray_message=show_tray_message)
        
    def force_quit(self):
        """彻底安全退出管理器，释放所有资源并完全终止进程"""
        try:
            if hasattr(self, "_window_save_debounce"):
                self._window_save_debounce.clear()
            self.save_window_position_qt_visual(self, "WindowPosManagerUI")
        except Exception as e:
            print(f"[WARN] Failed to save position on force_quit: {e}")
        try:
            # 停止拓扑检测定时器
            if hasattr(self, '_topology_timer') and self._topology_timer:
                self._topology_timer.stop()
            if hasattr(self, '_topology_debounce_timer') and self._topology_debounce_timer:
                self._topology_debounce_timer.stop()
            # 关闭 IPC 本地服务
            if hasattr(self, 'single_instance_server') and self.single_instance_server:
                self.single_instance_server.close()
            # 隐藏托盘图标
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()
            # 停止全局热键线程
            if getattr(self, '_hotkey_thread', None):
                self._hotkey_thread.stop()
                self._hotkey_thread = None
                self._hotkey_hook = None
            # 停止 RamDisk 同步守护线程
            if hasattr(self, 'ramdisk_sync_worker') and self.ramdisk_sync_worker:
                self.ramdisk_sync_worker.stop()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
        import os
        os._exit(0)
        
    def on_tray_activated(self, reason):
        try:
            if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
                self.toggle_visibility()
        except Exception as e:
            logger.error(f"托盘激活事件处理异常: {e}")
            
    def closeEvent(self, event):
        try:
            if hasattr(self, "_window_save_debounce"):
                self._window_save_debounce.clear()
            self.save_window_position_qt_visual(self, "WindowPosManagerUI")
        except Exception as e:
            print(f"[WARN] Failed to save position on closeEvent: {e}")
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.hide()
            self.log("界面已隐藏至状态栏。")
            event.ignore()
        else:
            try:
                if getattr(self, '_hotkey_thread', None):
                    self._hotkey_thread.stop()
                    self._hotkey_thread = None
                    self._hotkey_hook = None
                if hasattr(self, 'ramdisk_sync_worker') and self.ramdisk_sync_worker:
                    self.ramdisk_sync_worker.stop()
            except:
                pass
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.save_window_position_qt_visual(self, "WindowPosManagerUI")
        except:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        try:
            self.save_window_position_qt_visual(self, "WindowPosManagerUI")
        except:
            pass

    def _ensure_window_fits_screen(self):
        """唤醒/打开窗口时自适应适配当前屏幕分辨率与DPI，防止分辨率切换后窗口变巨大或脱离可见屏幕"""
        try:
            app = QApplication.instance()
            if not app:
                return
            screen = app.screenAt(self.geometry().center())
            if not screen:
                screen = app.primaryScreen()
            if not screen:
                return
            
            avail = screen.availableGeometry()
            win_geom = self.geometry()
            
            need_adjust = False
            w = win_geom.width()
            h = win_geom.height()
            x = win_geom.x()
            y = win_geom.y()
            
            # 如果尺寸超过屏幕可用区域 90%，自适应调整为不超过屏宽高的 85%
            if w > avail.width() * 0.9:
                w = int(avail.width() * 0.85)
                need_adjust = True
            if h > avail.height() * 0.9:
                h = int(avail.height() * 0.85)
                need_adjust = True
                
            w = max(w, 800)
            h = max(h, 550)
            
            # 如果坐标超出屏幕可见范围，置于屏幕中心
            if x < avail.left() or x + w > avail.right() or y < avail.top() or y + h > avail.bottom():
                x = avail.left() + max(0, (avail.width() - w) // 2)
                y = avail.top() + max(0, (avail.height() - h) // 2)
                need_adjust = True
                
            if need_adjust:
                self.setGeometry(x, y, w, h)
        except Exception as e:
            logger.error(f"[_ensure_window_fits_screen] 自适应调整失败: {e}")

    def _setup_screen_topology_listener(self):
        """配置屏幕拓扑热插拔/切换动态监听器（免冷启动程序自适应）"""
        try:
            app = QApplication.instance()
            if app:
                app.screenAdded.connect(self._schedule_topology_check)
                app.screenRemoved.connect(self._schedule_topology_check)
                app.primaryScreenChanged.connect(self._schedule_topology_check)
                for screen in app.screens():
                    screen.geometryChanged.connect(self._schedule_topology_check)
        except Exception as e:
            logger.error(f"绑定 QApplication 屏幕信号异常: {e}")

        # 后台定时比对心跳（每 5 秒比对拓扑指纹）
        self._topology_timer = QtCore.QTimer(self)
        self._topology_timer.timeout.connect(self._check_screen_topology_heartbeat)
        self._topology_timer.start(5000)
        
        # 防抖定时器：在接收到屏幕插拔事件后延时 600ms 触发拓扑重检
        self._topology_debounce_timer = QtCore.QTimer(self)
        self._topology_debounce_timer.setSingleShot(True)
        self._topology_debounce_timer.timeout.connect(self._on_display_topology_changed)

    def _schedule_topology_check(self, *args):
        """接收到 Qt 屏幕增减/主屏切换/尺寸改变信号时触发防抖检查"""
        if hasattr(self, '_topology_debounce_timer'):
            self._topology_debounce_timer.start(600)

    def _check_screen_topology_heartbeat(self):
        """定时心跳检查当前屏幕拓扑是否有变动"""
        try:
            info = core.get_screen_resolution_summary()
            # 🛡️ 息屏/休眠/锁屏瞬态异常防护：若无有效显示器或总宽度过小，直接跳过心跳判定
            if not info or info.get("display_num", 0) <= 0 or info.get("total_width", 0) < 640:
                return
            current_sig = info.get("summary_signature", "")
            if hasattr(self, '_last_topology_signature') and current_sig and current_sig != self._last_topology_signature:
                self._on_display_topology_changed()
        except Exception:
            pass

    def _on_display_topology_changed(self):
        """物理显示器拓扑结构发生变更时的自适应处理（免冷启动）"""
        info = core.get_screen_resolution_summary()
        if not info or info.get("display_num", 0) <= 0 or info.get("total_width", 0) < 640:
            return
            
        current_sig = info.get("summary_signature", "")
        self._last_topology_signature = current_sig
        
        self.log(f"⚡ [Screen Topology] 检测到物理显示器拓扑发生变更 (显示器: {info['display_num']} 个，物理总宽: {info['total_width']}px)，正在自适应重新匹配...")
        
        # 重新检测与自适应切换方案 (保持当前用户已选方案优先)
        self.detect_and_refresh_state(auto_switch_scheme=True)

    def detect_and_refresh_state(self, auto_switch_scheme=False):
        """自动检测物理屏幕拓扑结构并刷新当前桌面各窗口的实际坐标位置"""
        self._ensure_window_fits_screen()
        self.load_screen_info()
        if auto_switch_scheme:
            self.refresh_resolutions_combo()
        self.refresh_current_positions()

    def on_refresh_pos_clicked(self):
        self.detect_and_refresh_state(auto_switch_scheme=True)
        self.log("已手动刷新当前桌面各窗口的实际坐标位置与显示器拓扑。")

    def showEvent(self, event):
        """窗口被显示时自动刷新位置检测与绘图重整"""
        super().showEvent(event)
        try:
            self.update()
            self.repaint()
        except Exception:
            pass
        self.detect_and_refresh_state()

    def changeEvent(self, event):
        """窗口状态改变时，如从最小化恢复，自动刷新位置检测"""
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            if not self.isMinimized():
                try:
                    self.update()
                    self.repaint()
                except Exception:
                    pass
                self.detect_and_refresh_state()
            
    def toggle_visibility(self):
        if self.isVisible():
            if self.isActiveWindow():
                self.hide()
            else:
                self._force_show_and_top()
        else:
            self._force_show_and_top()
            
    def _hide_tray_message_window(self):
        """物理将 QTrayIconMessageWindow 与 PyInstaller Onefile Hidden Window 等后台辅助遮罩窗口移出屏幕外部(-10000, -10000)并强行隐蔽，彻底消灭打包后的白屏遮罩"""
        try:
            import win32gui, win32con
            def _kill_aux_wnd(hwnd, _):
                if win32gui.IsWindow(hwnd):
                    title = win32gui.GetWindowText(hwnd) or ""
                    cls = win32gui.GetClassName(hwnd) or ""
                    if any(k in title for k in ("QTrayIconMessageWindow", "PyInstaller", "Hidden Window")) or \
                       any(k in cls for k in ("QTrayIconMessageWindow", "PyInstaller", "Hidden Window")):
                        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                        win32gui.SetWindowPos(hwnd, 0, -10000, -10000, 0, 0,
                                            win32con.SWP_HIDEWINDOW | win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER)
                return True

            main_hwnd = int(self.winId()) if hasattr(self, 'winId') and self.winId() else 0
            if main_hwnd:
                try:
                    win32gui.EnumChildWindows(main_hwnd, _kill_aux_wnd, None)
                except Exception:
                    pass
            win32gui.EnumWindows(_kill_aux_wnd, None)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._hide_tray_message_window()

    def _force_show_and_top(self):
        # 1. 无论在托盘还是任务栏最小化，均强制拉起显示
        self.show()
        if self.isMinimized():
            self.showNormal()
        else:
            self.showNormal()

        # 2. 隐蔽 Qt 内部生成的 QTrayIconMessageWindow 原生遮罩窗口，彻底消除白板遮罩
        self._hide_tray_message_window()

        # 3. 提升视窗层级并抢占 Qt 激活焦点
        self.raise_()
        self.activateWindow()

        # 4. 强制 Qt 绘图引擎与事件队列立刻刷新并重绘界面，彻底消除白板无响应现象
        try:
            self.update()
            self.repaint()
            QApplication.processEvents()
        except Exception:
            pass

        self._hide_tray_message_window()

        # 5. 使用底层 Win32 工业级 API 强力夺取 Windows 系统前台焦点与置顶
        try:
            hwnd = int(self.winId())
            core.force_topmost_activate_hwnd(hwnd)
        except Exception:
            pass

        # 6. 激活前台后自动同步检测桌面位置状态
        self.detect_and_refresh_state()

            
    def parse_hotkey_string(self, hotkey_str: str) -> tuple:
        """
        将热键字符串如 'ctrl+alt+w' 解析为 (modifiers, vk)
        """
        parts = hotkey_str.lower().split('+')
        modifiers = 0
        vk = 0
        
        # 常见的修饰键映射
        mod_map = {
            'ctrl': 0x0002,  # MOD_CONTROL
            'alt': 0x0001,   # MOD_ALT
            'shift': 0x0004, # MOD_SHIFT
            'win': 0x0008,   # MOD_WIN
        }
        
        for part in parts:
            part = part.strip()
            if part in mod_map:
                modifiers |= mod_map[part]
            else:
                # 尝试解析普通字符键或特殊功能键
                if len(part) == 1:
                    vk = ord(part.upper())
                else:
                    special_keys = {
                        'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
                        'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
                        'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
                        'enter': 0x0D, 'return': 0x0D, 'space': 0x20,
                        'tab': 0x09, 'backspace': 0x08, 'delete': 0x2E,
                        'insert': 0x2D, 'home': 0x24, 'end': 0x23,
                        'pageup': 0x21, 'pagedown': 0x22,
                        'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
                        'escape': 0x1B, 'esc': 0x1B
                    }
                    if part in special_keys:
                        vk = special_keys[part]
        return modifiers, vk


    def bind_hotkey(self, hotkey_str):
        """
        使用 ManagerHotkeyThread 独立子线程注册全局热键。
        RegisterHotKey(None,...) 将热键绑定到子线程消息队列，
        彻底避免在 nativeEvent 中操作裸指针导致 Access Violation 崩溃。
        """
        if not hotkey_str:
            return False
        try:
            modifiers, vk = self.parse_hotkey_string(hotkey_str)
            if not vk:
                self.log(f"解析热键失败或无效按键组合: {hotkey_str}")
                return False

            # 停止旧线程（会自动 UnregisterHotKey）
            old_thread = getattr(self, '_hotkey_thread', None)
            if old_thread and old_thread.is_alive():
                old_thread.stop()
                old_thread.join(timeout=1.0)
            self._hotkey_thread = None

            # 创建并启动新的热键监听子线程
            thread = ManagerHotkeyThread(self.toggle_ui_signal.emit)
            thread.set_hotkey(modifiers, vk)
            thread.start()

            # 等待短暂时间确认注册成功
            import time
            time.sleep(0.15)
            if not thread._registered:
                self.log(f"RegisterHotKey 注册热键失败: {hotkey_str} (可能已被其他程序抢占)")
                thread.stop()
                return False

            self._hotkey_thread = thread
            self.current_bound_hotkey = hotkey_str
            self._hotkey_hook = hotkey_str
            self.log(f"[OK] 已绑定全局热键 (独立线程): {hotkey_str}")
            return True
        except Exception as e:
            self.log(f"绑定热键失败: {e}")
            return False
            
    def on_bind_hotkey_clicked(self):
        new_hk = self.le_hotkey.text().strip()
        if new_hk:
            success = self.bind_hotkey(new_hk)
            if success:
                self.config_manager.config_data["global_hotkey"] = new_hk
                self.config_manager.save()
                QMessageBox.information(self, "绑定测试成功", f"✅ 热键【{new_hk}】测试绑定成功并已保存！\n您可以立即按下该组合键测试隐藏/呼出效果。")
            else:
                QMessageBox.warning(self, "绑定测试失败", f"❌ 热键【{new_hk}】绑定失败！\n这可能是因为系统热键冲突或是不支持该按键组合。\n请重新点击输入框录入其他快捷键。")

    def init_ui(self):
        # 全局深色现代 QSS 样式设计
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121214;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
            QWidget#mainWidget {
                background-color: #121214;
            }
            QLabel {
                color: #a0a0ab;
                font-size: 13px;
            }
            QLabel#titleLabel {
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
            }
            QGroupBox {
                border: 1px solid #2a2a32;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #ffffff;
                background-color: #1a1a1e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QComboBox {
                background-color: #24242b;
                border: 1px solid #3e3e4a;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
                min-width: 150px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #3e3e4a;
                border-left-style: solid;
            }
            QComboBox QAbstractItemView {
                background-color: #24242b;
                border: 1px solid #3e3e4a;
                selection-background-color: #0ea5e9;
                color: #ffffff;
            }
            QPushButton {
                background-color: #2e2e38;
                border: 1px solid #4a4a56;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3e3e4a;
                border-color: #0ea5e9;
            }
            QPushButton:pressed {
                background-color: #22222a;
            }
            QPushButton#btnSave {
                background-color: #10b981;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnSave:hover {
                background-color: #059669;
            }
            QPushButton#btnApply {
                background-color: #0ea5e9;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnApply:hover {
                background-color: #0284c7;
            }
            QPushButton#btnDeleteRes {
                background-color: #ef4444;
                border: none;
            }
            QPushButton#btnDeleteRes:hover {
                background-color: #dc2626;
            }
            QPushButton#btnPerf {
                background-color: #8b5cf6;
                border: none;
                font-weight: bold;
            }
            QPushButton#btnPerf:hover {
                background-color: #7c3aed;
            }
            QTableWidget {
                background-color: #16161a;
                border: 1px solid #2a2a32;
                gridline-color: #25252b;
                color: #dcdcdc;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:hover {
                background-color: #262630;
            }
            QTableWidget::item:selected {
                background-color: #2e3e50;
                color: #0ea5e9;
            }
            QHeaderView::section {
                background-color: #22222a;
                color: #a0a0ab;
                padding: 6px;
                border: none;
                font-weight: bold;
                border-bottom: 1px solid #3a3a42;
            }
            QTextEdit {
                background-color: #0f0f12;
                border: 1px solid #25252b;
                border-radius: 4px;
                color: #10b981;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
        """)

        main_widget = QWidget()
        main_widget.setObjectName("mainWidget")
        self.setCentralWidget(main_widget)
        self.setMinimumSize(450, 420)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(4)

        # 顶部标题与显示器检测面板
        top_bar = QHBoxLayout()
        title_lbl = QLabel("🖥️ 桌面窗口坐标分类布局管理器")
        title_lbl.setObjectName("titleLabel")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        
        self.lbl_screen_status = QLabel("检测屏幕中...")
        self.lbl_screen_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
        top_bar.addWidget(self.lbl_screen_status)
        main_layout.addLayout(top_bar)

        # 显示器详情显示区 (GroupBox)
        self.gb_display_info = QGroupBox("当前物理显示器拓扑结构")
        self.gb_display_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gb_display_layout = QVBoxLayout(self.gb_display_info)
        gb_display_layout.setContentsMargins(10, 10, 10, 8)
        gb_display_layout.setSpacing(6)
        
        self.lbl_display_details = QLabel("无显示器数据")
        self.lbl_display_details.setWordWrap(True)
        self.lbl_display_details.setStyleSheet("color: #d1d5db; line-height: 1.4;")
        gb_display_layout.addWidget(self.lbl_display_details)
        
        # 显示器物理布局配置管理与操作栏（紧凑两行自适应排版，开启自动折行，杜绝横向拉伸）
        topo_manage_box = QVBoxLayout()
        topo_manage_box.setSpacing(6)
        
        # 第一行：拓扑配置下拉选择 + 刷新 + 预览
        row_topo_select = QHBoxLayout()
        row_topo_select.setSpacing(6)
        
        lbl_topo = QLabel("📂 拓扑排布:")
        lbl_topo.setStyleSheet("color: #93c5fd; font-weight: bold;")
        row_topo_select.addWidget(lbl_topo)
        
        self.cb_topology_configs = QComboBox()
        self.cb_topology_configs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cb_topology_configs.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cb_topology_configs.setMinimumContentsLength(15)
        self.cb_topology_configs.view().setWordWrap(True)  # 下拉列表开启自动换行
        self.cb_topology_configs.setStyleSheet("""
            QComboBox {
                background-color: #1e1e24;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                font-weight: 500;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #3b82f6;
                border-left-style: solid;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e24;
                color: #ffffff;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
                padding: 4px;
            }
        """)
        row_topo_select.addWidget(self.cb_topology_configs, stretch=1)
        
        self.btn_refresh_topo_configs = QPushButton("🔄 刷新")
        self.btn_refresh_topo_configs.setToolTip("重新扫描运行目录下的显示器拓扑配置文件")
        self.btn_refresh_topo_configs.setStyleSheet("background-color: #374151; color: white; padding: 4px 8px;")
        self.btn_refresh_topo_configs.clicked.connect(lambda: self.refresh_topology_configs_combo())
        row_topo_select.addWidget(self.btn_refresh_topo_configs)
        
        self.btn_preview_topo_config = QPushButton("👁️ 预览拓扑")
        self.btn_preview_topo_config.setToolTip("查看当前下拉框选中配置文件的屏幕空间相对排布与详细参数")
        self.btn_preview_topo_config.setStyleSheet("background-color: #0284c7; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_preview_topo_config.clicked.connect(self.preview_selected_topology)
        row_topo_select.addWidget(self.btn_preview_topo_config)
        
        topo_manage_box.addLayout(row_topo_select)

        # 第二行：拓扑动作按钮工具栏 (FlowLayout 自动折行，保证窄屏不溢出)
        row_topo_actions = FlowLayout(hspacing=6, vspacing=6)

        self.btn_restore_screen_layout = QPushButton("🔄 恢复选中拓扑")
        self.btn_restore_screen_layout.setToolTip("将当前桌面显示器排列智能恢复为下拉框选中的配置（需二次确认）")
        self.btn_restore_screen_layout.setStyleSheet("background-color: #ea580c; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_restore_screen_layout.clicked.connect(self.restore_physical_screen_layout)
        row_topo_actions.addWidget(self.btn_restore_screen_layout)

        self.btn_save_screen_layout = QPushButton("💾 保存当前拓扑")
        self.btn_save_screen_layout.setToolTip("将当前系统实际屏幕物理排布保存为新配置文件")
        self.btn_save_screen_layout.setStyleSheet("background-color: #0d9488; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_save_screen_layout.clicked.connect(self.save_physical_screen_layout)
        row_topo_actions.addWidget(self.btn_save_screen_layout)

        self.btn_delete_topo_config = QPushButton("🗑️ 删除配置")
        self.btn_delete_topo_config.setToolTip("从磁盘删除下拉框当前选中的拓扑配置文件")
        self.btn_delete_topo_config.setStyleSheet("background-color: #b91c1c; color: white; padding: 4px 8px;")
        self.btn_delete_topo_config.clicked.connect(self.delete_selected_topology)
        row_topo_actions.addWidget(self.btn_delete_topo_config)

        self.btn_clean_duplicate_topos = QPushButton("🧹 清理重复拓扑")
        self.btn_clean_duplicate_topos.setToolTip("自动扫描并清理所有与已有配置数据完全一致的重复备份文件")
        self.btn_clean_duplicate_topos.setStyleSheet("background-color: #4b5563; color: #f3f4f6; padding: 4px 8px;")
        self.btn_clean_duplicate_topos.clicked.connect(self.clean_duplicate_topologies)
        row_topo_actions.addWidget(self.btn_clean_duplicate_topos)

        topo_manage_box.addLayout(row_topo_actions)
        gb_display_layout.addLayout(topo_manage_box)

        main_layout.addWidget(self.gb_display_info)

        # 常用程序快捷启动面板（横向滚动，固定/运行中优先，可容纳更多程序）
        self.gb_app_shortcuts = QGroupBox("常用程序快捷启动 (⭐固定优先 · ▶运行次之 · 滚轮切换更多)")
        self.gb_app_shortcuts.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        gb_shortcuts_outer = QVBoxLayout(self.gb_app_shortcuts)
        gb_shortcuts_outer.setContentsMargins(8, 10, 8, 6)
        gb_shortcuts_outer.setSpacing(0)

        self._shortcuts_scroll = QtWidgets.QScrollArea()
        self._shortcuts_scroll.setWidgetResizable(True)
        self._shortcuts_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._shortcuts_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._shortcuts_scroll.setFixedHeight(62)
        self._shortcuts_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:horizontal { height: 5px; background: #1e1e24; border-radius: 3px; }"
            "QScrollBar::handle:horizontal { background: #4b5563; border-radius: 3px; min-width: 30px; }"
            "QScrollBar::handle:horizontal:hover { background: #6b7280; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
        )

        self._shortcuts_inner = QWidget()
        self._shortcuts_inner.setStyleSheet("background: transparent;")
        self.shortcuts_grid_layout = QHBoxLayout(self._shortcuts_inner)
        self.shortcuts_grid_layout.setContentsMargins(5, 2, 5, 2)
        self.shortcuts_grid_layout.setSpacing(8)
        self.shortcuts_grid_layout.addStretch()
        self._shortcuts_scroll.setWidget(self._shortcuts_inner)
        gb_shortcuts_outer.addWidget(self._shortcuts_scroll)

        def _on_shortcuts_wheel(event):
            sb = self._shortcuts_scroll.horizontalScrollBar()
            delta = event.angleDelta().y()
            sb.setValue(sb.value() - delta // 3)
        self._shortcuts_scroll.wheelEvent = _on_shortcuts_wheel

        self.shortcut_buttons = {}
        self.lbl_shortcuts_tip = QLabel("暂无快捷启动程序配置，请先在下方表格中为窗口配置'程序路径'。")
        self.lbl_shortcuts_tip.setStyleSheet("color: #6b7280; font-style: italic;")
        self.shortcuts_grid_layout.insertWidget(0, self.lbl_shortcuts_tip)

        main_layout.addWidget(self.gb_app_shortcuts)

        # 配置管理控制栏
        config_bar = QHBoxLayout()
        config_bar.setSpacing(6)
        config_bar.setContentsMargins(0, 0, 0, 0)
        
        lbl_res = QLabel("分类选择方案:")
        lbl_res.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(lbl_res)
        
        self.cb_resolutions = QComboBox()
        self.cb_resolutions.currentIndexChanged.connect(self.on_resolution_changed)
        self.cb_resolutions.setMinimumWidth(120)
        self.cb_resolutions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(self.cb_resolutions)

        self.btn_new_res = QPushButton("➕ 新建方案")
        self.btn_new_res.clicked.connect(self.new_resolution)
        self.btn_new_res.setMinimumWidth(60)
        self.btn_new_res.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(self.btn_new_res)
        
        self.btn_copy_res = QPushButton("📋 复制方案")
        self.btn_copy_res.clicked.connect(self.copy_resolution)
        self.btn_copy_res.setMinimumWidth(60)
        self.btn_copy_res.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(self.btn_copy_res)

        self.btn_delete_res = QPushButton("🗑️ 删除方案")
        self.btn_delete_res.setObjectName("btnDeleteRes")
        self.btn_delete_res.clicked.connect(self.delete_resolution)
        self.btn_delete_res.setMinimumWidth(60)
        self.btn_delete_res.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(self.btn_delete_res)
        
        self.btn_auto_detect = QPushButton("🔍 自动匹配当前屏幕")
        self.btn_auto_detect.clicked.connect(self.auto_detect_and_set)
        self.btn_auto_detect.setMinimumWidth(100)
        self.btn_auto_detect.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        config_bar.addWidget(self.btn_auto_detect)
        
        main_layout.addLayout(config_bar)

        # 主配置列表编辑区 (Table)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels([
            "窗口匹配标识/关键字 (模糊匹配)", 
            "配置坐标 (X,Y,Width,Height)", 
            "当前桌面实际位置 (不一致标红)"
        ])
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.itemChanged.connect(self.on_table_item_changed)
        self.table_widget.cellClicked.connect(self.on_table_cell_clicked)
        self.table_widget.cellDoubleClicked.connect(self.on_table_cell_double_clicked)
        self.table_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # 中部表格及表格右侧操作按钮
        mid_layout = QHBoxLayout()
        mid_layout.addWidget(self.table_widget, stretch=4)
        
        table_op_layout = QVBoxLayout()
        table_op_layout.setSpacing(10)
        table_op_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_add_row = QPushButton("➕ 添加映射行")
        self.btn_add_row.setFixedHeight(32)
        self.btn_add_row.clicked.connect(self.add_table_row)
        table_op_layout.addWidget(self.btn_add_row)
        
        self.btn_delete_row = QPushButton("➖ 删除选中行")
        self.btn_delete_row.setFixedHeight(32)
        self.btn_delete_row.clicked.connect(self.delete_table_row)
        table_op_layout.addWidget(self.btn_delete_row)
        
        # 两组按钮之间的自适应大间隔弹簧，空间富余时拉开 15px，空间紧张时压缩至 0
        table_op_layout.addSpacerItem(QtWidgets.QSpacerItem(0, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum))
        
        self.btn_refresh_pos = QPushButton("🔄 刷新当前位置")
        self.btn_refresh_pos.setFixedHeight(32)
        self.btn_refresh_pos.setStyleSheet("background-color: #0891b2; border: none; font-weight: bold;")
        self.btn_refresh_pos.clicked.connect(self.on_refresh_pos_clicked)
        table_op_layout.addWidget(self.btn_refresh_pos)
        
        self.btn_capture_wins = QPushButton("📸 捕获桌面窗口")
        self.btn_capture_wins.setFixedHeight(32)
        self.btn_capture_wins.setStyleSheet("background-color: #4f46e5; border: none; font-weight: bold;")
        self.btn_capture_wins.clicked.connect(self.capture_desktop_windows)
        table_op_layout.addWidget(self.btn_capture_wins)
        
        self.btn_update_existing = QPushButton("🔄 更新已有窗口坐标")
        self.btn_update_existing.setFixedHeight(32)
        self.btn_update_existing.setStyleSheet("background-color: #059669; border: none; font-weight: bold;")
        self.btn_update_existing.clicked.connect(self.update_existing_windows_pos)
        table_op_layout.addWidget(self.btn_update_existing)
        
        table_op_layout.addStretch()
        mid_layout.addLayout(table_op_layout, stretch=1)
        main_layout.addLayout(mid_layout)

        # 自适应纵向弹簧，空间充足时留出 15px 间隔，空间局促时自动缩减至 0
        spacer1 = QtWidgets.QSpacerItem(0, 15, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum)
        main_layout.addItem(spacer1)

        # 日志控制台
        log_group = QGroupBox("执行状态日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(110)
        log_layout.addWidget(self.log_output)
        main_layout.addWidget(log_group)

        # 自适应纵向弹簧，空间充足时留出 10px 间隔，空间局促时自动缩减至 0
        spacer2 = QtWidgets.QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum)
        main_layout.addItem(spacer2)

        # 底部应用栏
        bottom_bar = FlowLayout(hspacing=6, vspacing=6, align_right_from_index=3)
        
        # --- 全局热键配置 ---
        self.lbl_hotkey = QLabel("全局热键:")
        bottom_bar.addWidget(self.lbl_hotkey)
        
        self.le_hotkey = HotkeyLineEdit()
        self.le_hotkey.setText(getattr(self, 'current_bound_hotkey', ''))
        bottom_bar.addWidget(self.le_hotkey)
        
        self.btn_bind_hotkey = QPushButton("绑定")
        self.btn_bind_hotkey.clicked.connect(self.on_bind_hotkey_clicked)
        bottom_bar.addWidget(self.btn_bind_hotkey)
        
        # --- 开机自启复选框 ---
        self.chk_autostart = QCheckBox("开机自启")
        self.chk_autostart.setToolTip("勾选后系统开机时将通过 Windows 注册表以托盘后台隐藏不弹窗模式启动程序 (-hide)")
        self.chk_autostart.setChecked(core.is_autostart_enabled_for_current_app())
        self.chk_autostart.stateChanged.connect(self.on_autostart_changed)
        bottom_bar.addWidget(self.chk_autostart)

        self.btn_open_perf = QPushButton("📐 性能分析")
        self.btn_open_perf.setObjectName("btnPerf")
        self.btn_open_perf.clicked.connect(self.open_performance_analyzer)
        bottom_bar.addWidget(self.btn_open_perf)
        
        self.btn_route_settings = QPushButton("⚡ 路由设置")
        self.btn_route_settings.clicked.connect(self.open_route_settings)
        bottom_bar.addWidget(self.btn_route_settings)
        
        self.btn_ramdisk_sync = QPushButton("💾 RamDisk同步")
        self.btn_ramdisk_sync.setToolTip("配置 RamDisk 实时数据自动同步与备份规则，防止死机数据丢失")
        self.btn_ramdisk_sync.clicked.connect(self.open_ramdisk_sync_settings)
        bottom_bar.addWidget(self.btn_ramdisk_sync)
        
        self.btn_save_config = QPushButton("💾 保存配置")
        self.btn_save_config.setObjectName("btnSave")
        self.btn_save_config.clicked.connect(self.save_all_config)
        bottom_bar.addWidget(self.btn_save_config)
        
        self.btn_apply_layout = QPushButton("🚀应用布局")
        self.btn_apply_layout.setObjectName("btnApply")
        self.btn_apply_layout.clicked.connect(self.apply_current_layout)
        bottom_bar.addWidget(self.btn_apply_layout)
        
        self.btn_full_exit = QPushButton("❌退出")
        self.btn_full_exit.setObjectName("btnDeleteRes") # 复用红色的删除按钮样式
        self.btn_full_exit.clicked.connect(self.force_quit)
        bottom_bar.addWidget(self.btn_full_exit)
        
        main_layout.addLayout(bottom_bar)

        self.log("界面加载完毕。")

    def on_autostart_changed(self, state):
        """开机自启复选框勾选状态改变时的响应回调"""
        enable = (state == QtCore.Qt.CheckState.Checked.value or state == 2)
        has_existing, existing_cmd = core.get_current_autostart_command()
        is_current = core.is_autostart_enabled_for_current_app()
        expected_cmd = core.get_autostart_command()

        if enable:
            if has_existing and not is_current:
                reply = QMessageBox.question(
                    self,
                    "更新开机自启动路径确认",
                    f"检测到 Windows 注册表中已存在其他开机自启动路径：\n【已有路径】: {existing_cmd}\n\n"
                    f"当前程序运行路径为：\n【当前路径】: {expected_cmd}\n\n"
                    f"整个系统只允许一个 manage_window_layout 开机自启。\n"
                    f"是否将开机自启动路径更新为当前程序？\n\n"
                    f"• 点击【是 (Yes)】：覆盖更新为当前程序路径\n"
                    f"• 点击【否 (No)】：取消本次操作并保持原有路径",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.chk_autostart.blockSignals(True)
                    self.chk_autostart.setChecked(False)
                    self.chk_autostart.blockSignals(False)
                    return
            success, msg = core.set_autostart_enabled(True)
        else:
            if is_current:
                success, msg = core.set_autostart_enabled(False)
            else:
                success, msg = True, "当前程序未开启开机自启"

        if success:
            self.log(f"🎯 {msg}")
        else:
            self.log(f"❌ {msg}")
            # 如果操作失败，还原复选框真实状态
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(core.is_autostart_enabled_for_current_app())
            self.chk_autostart.blockSignals(False)
            QMessageBox.warning(self, "开机自启注册表设置失败", msg)

    def log(self, text: str):
        """输出一条日志"""
        self.log_output.append(f"[{QtCore.QTime.currentTime().toString('hh:mm:ss')}] {text}")
        try:
            scrollbar = self.log_output.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
        except Exception:
            pass
        try:
            logger.info(text)
        except Exception:
            pass

    def open_performance_analyzer(self):
        """以独立多进程/子进程形式拉起系统性能与内存诊断分析器"""
        is_running = False
        if hasattr(self, '_detailed_analysis_process') and self._detailed_analysis_process:
            # 兼容 mp.Process 和 subprocess.Popen
            if hasattr(self._detailed_analysis_process, 'is_alive'):
                is_running = self._detailed_analysis_process.is_alive()
            elif hasattr(self._detailed_analysis_process, 'poll'):
                is_running = self._detailed_analysis_process.poll() is None
                
        if is_running:
            try:
                # 尝试置顶已有的窗口
                core.bring_window_to_top_by_title("量化系统后台性能")
                self.log("ℹ️ 系统性能分析器已在后台运行中，请检查任务栏。")
                return
            except Exception:
                pass

        # 尝试使用 multiprocessing 安全拉起
        try:
            import multiprocessing as mp
            mp.freeze_support()
            
            # 为了能在 sys.path 中找到 sys_performance_analyzer，我们需要将项目根目录加入 sys.path
            app_root = core.get_app_root()
            if app_root not in sys.path:
                sys.path.insert(0, app_root)
                
            from sys_performance_analyzer import launch_analyzer
            
            proc = mp.Process(
                target=launch_analyzer,
                name="SystemPerformanceAnalyzer",
                daemon=True
            )
            proc.start()
            self._detailed_analysis_process = proc
            self.log(f"🚀 系统性能分析诊断器子进程成功拉起 (PID: {proc.pid})")
        except Exception as e:
            self.log(f"❌ 无法以多进程形式启动系统性能分析器: {e}")
            # fallback: 尝试用 subprocess.Popen 拉起
            try:
                import subprocess
                app_root = core.get_app_root()
                script_path = os.path.join(app_root, "sys_performance_analyzer.py")
                if os.path.exists(script_path):
                    # 在非 frozen 环境下使用 python 运行脚本
                    proc = subprocess.Popen([sys.executable, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0)
                    self._detailed_analysis_process = proc
                    self.log(f"🚀 [Fallback] 通过 subprocess 成功拉起性能分析器脚本 (PID: {proc.pid})")
                else:
                    QMessageBox.critical(self, "启动失败", f"找不到性能分析器脚本，且多进程启动失败:\n{e}")
            except Exception as ex:
                self.log(f"❌ Fallback 启动也失败: {ex}")
                QMessageBox.critical(self, "启动失败", f"无法启动系统性能分析器:\n{ex}")

    def open_route_settings(self):
        """打开静态路由网关配置对话框"""
        dialog = RouteConfigDialog(self.config_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.log("🎯 静态路由配置保存成功！")
            success, msg = core.check_and_add_route(self.config_manager)
            self.log(f"[Route Settings] {msg}")

    def open_ramdisk_sync_settings(self):
        """打开 RamDisk 实时数据自动同步与备份配置对话框"""
        if not hasattr(self, 'ramdisk_sync_config') or not self.ramdisk_sync_config:
            self.ramdisk_sync_config = sync_engine.RamDiskSyncConfig()
        if not hasattr(self, 'ramdisk_sync_engine') or not self.ramdisk_sync_engine:
            self.ramdisk_sync_engine = sync_engine.RamDiskSyncEngine(self.ramdisk_sync_config)
        if not hasattr(self, 'ramdisk_sync_worker'):
            self.ramdisk_sync_worker = None

        dialog = RamDiskSyncDialog(self.ramdisk_sync_config, self.ramdisk_sync_engine, self.ramdisk_sync_worker, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            log_status_desc = "详细日志: 已开启" if getattr(self.ramdisk_sync_config, "log_enabled", False) else "详细日志: 已关闭"
            self.log(f"💾 RamDisk 自动同步与备份配置已更新保存！({log_status_desc} · 每 {self.ramdisk_sync_config.sync_interval_sec} 秒巡检)")

    def _trigger_ramdisk_sync_from_tray(self):
        """从托盘右键一键手动触发立即同步备份"""
        if not hasattr(self, 'ramdisk_sync_worker') or not self.ramdisk_sync_worker:
            if not hasattr(self, 'ramdisk_sync_config'):
                self.ramdisk_sync_config = sync_engine.RamDiskSyncConfig()
            if not hasattr(self, 'ramdisk_sync_engine'):
                self.ramdisk_sync_engine = sync_engine.RamDiskSyncEngine(self.ramdisk_sync_config)
            self.ramdisk_sync_worker = sync_engine.RamDiskSyncWorker(self.ramdisk_sync_engine, self)

        self.log("🚀 [托盘快捷] 正在立即执行 RamDisk 增量同步备份...")
        res = self.ramdisk_sync_worker.trigger_sync_now(force=False)
        msg = res.get("message", "执行完毕")
        self.log(f"💾 [托盘同步结果] {msg}")
        if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "RamDisk 同步备份",
                msg,
                QtWidgets.QSystemTrayIcon.MessageIcon.Information if res.get("status") == "ok" else QtWidgets.QSystemTrayIcon.MessageIcon.Warning,
                3000
            )

    def _on_ramdisk_sync_completed(self, res: dict):
        """后台 Worker 每次同步巡检完成后的信号槽回调"""
        status = res.get("status", "ok")
        msg = res.get("message", "")
        synced = res.get("synced_files", [])
        
        if synced:
            self.log(f"💾 [RamDisk Sync] {msg}")
        elif status == "error":
            self.log(f"⚠️ [RamDisk Sync] {msg}")
        elif getattr(self.ramdisk_sync_config, "log_enabled", False):
            # 开启日志开关时，输出巡检明细（如耗时、无变动跳过）
            self.log(f"ℹ️ [RamDisk Sync] {msg}")

    def _on_ramdisk_sync_status_updated(self, text: str):
        """后台 Worker 状态更新回调"""
        # 默认模式下仅输出关键事件（启动初检/守护启停/异常），开启日志开关时输出全部状态
        is_key_event = any(k in text for k in ["启动初检", "启动", "停止", "异常", "错误", "失败"])
        if getattr(self.ramdisk_sync_config, "log_enabled", False) or is_key_event:
            self.log(f"ℹ️ [RamDisk Sync] {text}")

    def refresh_topology_configs_combo(self, select_filepath=None):
        """刷新运行目录下的显示器拓扑配置文件下拉框"""
        if not hasattr(self, "cb_topology_configs"):
            return
            
        self.cb_topology_configs.blockSignals(True)
        self.cb_topology_configs.clear()

        configs = core.list_display_configurations()
        if not configs:
            self.cb_topology_configs.addItem("⚠️ 运行目录未找到任何拓扑备份文件 (请点击[💾保存当前拓扑])", None)
            self.cb_topology_configs.setEnabled(False)
            if hasattr(self, "btn_preview_topo_config"):
                self.btn_preview_topo_config.setEnabled(False)
            if hasattr(self, "btn_restore_screen_layout"):
                self.btn_restore_screen_layout.setEnabled(False)
            if hasattr(self, "btn_delete_topo_config"):
                self.btn_delete_topo_config.setEnabled(False)
            if hasattr(self, "btn_clean_duplicate_topos"):
                self.btn_clean_duplicate_topos.setEnabled(False)
            self.cb_topology_configs.blockSignals(False)
            return

        self.cb_topology_configs.setEnabled(True)
        if hasattr(self, "btn_preview_topo_config"):
            self.btn_preview_topo_config.setEnabled(True)
        if hasattr(self, "btn_restore_screen_layout"):
            self.btn_restore_screen_layout.setEnabled(True)
        if hasattr(self, "btn_delete_topo_config"):
            self.btn_delete_topo_config.setEnabled(True)
            
        has_duplicate = any(cfg.get("is_duplicate") for cfg in configs)
        if hasattr(self, "btn_clean_duplicate_topos"):
            self.btn_clean_duplicate_topos.setEnabled(has_duplicate)

        info = core.get_screen_resolution_summary()
        cur_count = info.get("display_num", 1)

        matched_index = -1
        for idx, cfg in enumerate(configs):
            is_match = cfg.get("is_current_match", False)
            tag = " ⭐ [当前匹配]" if is_match else ""
            label = f"{cfg.get('display_name')}{tag}"
            self.cb_topology_configs.addItem(label, cfg)
            
            # 为每一项注入多行完整参数 ToolTip
            tip_lines = [
                f"【文件名称】: {cfg.get('filename')}",
                f"【屏幕总数】: {cfg.get('monitor_count')} 块",
                f"【相对方位】: {cfg.get('orientation_tag', '标准')}",
                f"【保存时间】: {cfg.get('mtime')}",
                f"【物理路径】: {cfg.get('filepath')}"
            ]
            if cfg.get('is_duplicate'):
                tip_lines.append(f"⚠️ [数据重复] 与 [{cfg.get('duplicate_of')}] 数据完全一致")
            self.cb_topology_configs.setItemData(
                self.cb_topology_configs.count() - 1, 
                "\n".join(tip_lines), 
                QtCore.Qt.ItemDataRole.ToolTipRole
            )
            
            if is_match and matched_index == -1:
                matched_index = idx
            if select_filepath and os.path.abspath(cfg.get("filepath", "")) == os.path.abspath(select_filepath):
                matched_index = idx

        if matched_index >= 0:
            self.cb_topology_configs.setCurrentIndex(matched_index)
        else:
            # 当前屏幕硬件没有匹配的历史配置文件，在第 0 位插入提示项，引导用户点击保存
            self.cb_topology_configs.insertItem(
                0, 
                f"⚠️ 当前拓扑未保存 (当前共 {cur_count} 屏 · 点击[💾保存当前拓扑])", 
                None
            )
            self.cb_topology_configs.setCurrentIndex(0)

        self.cb_topology_configs.blockSignals(False)

    def preview_selected_topology(self):
        """弹出可视化对话框预览当前选中的拓扑配置文件"""
        cfg = self.cb_topology_configs.currentData()
        if not cfg or not isinstance(cfg, dict):
            QMessageBox.information(
                self, 
                "提示", 
                "当前选中的屏幕排布尚未保存为配置文件。\n如需保存此屏幕排布，请点击【💾 保存当前拓扑】按钮！"
            )
            return

        dialog = DisplayTopologyPreviewDialog(cfg, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_screen_info()

    def delete_selected_topology(self):
        """删除当前选中的显示器拓扑配置文件"""
        cfg = self.cb_topology_configs.currentData()
        if not cfg or not isinstance(cfg, dict):
            QMessageBox.warning(self, "提示", "请先在下拉列表中选择要删除的有效配置文件！")
            return

        filename = cfg.get("filename", "")
        filepath = cfg.get("filepath", "")

        reply = QMessageBox.question(
            self,
            "确认删除配置文件",
            f"是否确认将以下显示器物理拓扑配置文件移入回收站？\n\n"
            f"【文件名称】: {filename}\n"
            f"【完整路径】: {filepath}\n\n"
            f"🛡️ 安全说明：文件将移入 Windows 系统回收站并在 BackConfig/deleted_topologies 自动备份，随时可一键撤销还原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = core.delete_display_configuration(filepath)
            if success:
                QMessageBox.information(self, "移至回收站成功", msg)
                self.log(f"🗑️ {msg}")
                self.refresh_topology_configs_combo()
            else:
                QMessageBox.critical(self, "操作失败", msg)
                self.log(f"❌ {msg}")

    def clean_duplicate_topologies(self):
        """扫描并一键清理所有与已有配置数据完全一致的重复拓扑配置文件"""
        configs = core.list_display_configurations()
        duplicate_items = [c for c in configs if c.get("is_duplicate")]

        if not duplicate_items:
            QMessageBox.information(
                self, 
                "提示", 
                "✨ 经检测，当前运行目录下未发现任何数据一致的重复拓扑文件！"
            )
            return

        dup_lines = []
        for d in duplicate_items:
            fname = d.get("filename", "")
            dup_of = d.get("duplicate_of", "")
            dup_lines.append(f"• {fname} (与 [{dup_of}] 拓扑数据完全重复)")

        dup_msg = "\n".join(dup_lines)
        reply = QMessageBox.question(
            self,
            "清理重复拓扑配置文件",
            f"检测到以下 {len(duplicate_items)} 个与已有配置数据完全一致的冗余备份文件：\n\n"
            f"{dup_msg}\n\n"
            f"是否确认将以上重复副本安全移入 Windows 系统回收站？\n"
            f"（将完整保留对应的原配置文件，并在 BackConfig/deleted_topologies 自动备份，随时可撤销还原）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del_count, del_files = core.clean_duplicate_display_configurations()
            self.log(f"🧹 已安全移入回收站 {del_count} 个重复拓扑文件: {', '.join(del_files)}")
            QMessageBox.information(
                self, 
                "清理完成", 
                f"成功将 {del_count} 个重复拓扑配置文件移入 Windows 回收站！\n（已自动在 BackConfig 建立安全备份）"
            )
            self.refresh_topology_configs_combo()
            self.refresh_topology_configs_combo()

    def save_physical_screen_layout(self):
        """保存当前多显示器的物理排布与相对坐标到磁盘"""
        success, msg = core.save_display_configuration()
        if success:
            QMessageBox.information(self, "保存成功", f"当前显示器物理拓扑结构已成功保存！\n\n【配置文件】:\n{msg}")
            self.log(f"💾 多显示器物理排布保存成功: {msg}")
            self.refresh_topology_configs_combo(select_filepath=msg)
        else:
            QMessageBox.critical(self, "保存失败", f"无法保存显示器配置: {msg}")
            self.log(f"❌ 保存显示器配置失败: {msg}")

    def restore_physical_screen_layout(self):
        """根据当前下拉框选中的配置恢复屏幕物理排布，必须弹窗二次确认"""
        cfg = self.cb_topology_configs.currentData()
        if not cfg or not isinstance(cfg, dict):
            QMessageBox.warning(
                self, 
                "提示", 
                "当前屏幕排布尚未保存为备份文件，无法恢复。\n如需将当前屏幕排布作为备份保存，请点击【💾 保存当前拓扑】按钮！"
            )
            return

        filename = cfg.get("filename", "")
        filepath = cfg.get("filepath", "")
        display_name = cfg.get("display_name", filename)
        m_count = cfg.get("monitor_count", len(cfg.get("monitors", [])))

        reply = QMessageBox.question(
            self, 
            "确认恢复显示器物理拓扑", 
            f"是否确定将当前多显示器排布恢复为此配置？\n\n"
            f"【配置文件】: {filename}\n"
            f"【拓扑概要】: {display_name}\n"
            f"【屏幕数量】: {m_count} 块显示器\n"
            f"【文件路径】: {filepath}\n\n"
            f"⚠️ 恢复操作会瞬间刷新您的系统显示设置并重新排布桌面上所有屏幕。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.log(f"正在尝试将多显示器物理拓扑还原为: {filename}...")
            success, msg = core.restore_display_configuration(filepath)
            if success:
                QMessageBox.information(self, "恢复完成", msg)
                self.log(f"🔄 {msg}")
                self.load_screen_info()
            else:
                QMessageBox.warning(self, "恢复提示", msg)
                self.log(f"⚠️ {msg}")

    def load_screen_info(self):
        """探测当前连接的显示器参数并在 UI 呈现，展示真实厂商型号信息"""
        info = core.get_screen_resolution_summary()
        self.lbl_screen_status.setText(f"检测到显示器: {info['display_num']} 个  总宽度: {info['total_width']}px")
        
        details = []
        for m in info["monitors"]:
            primary_tag = " [👑 主屏幕]" if m["is_primary"] else ""
            model_tag = f"[{m['model_name']}] " if m.get("model_name") and m['model_name'] != m['name'] else ""
            pnp_tag = f" (PNP: {m['pnp_id']})" if m.get("pnp_id") else ""
            details.append(
                f"设备 {m['index']}: {model_tag}名称: {m['name']}{pnp_tag} | 分辨率: {m['width']}x{m['height']} (@{int(m['scale']*100)}%) | "
                f"起始坐标: ({m['x']}, {m['y']}){primary_tag}"
            )
        self.lbl_display_details.setText("\n".join(details))
        
        # 刷新拓扑配置文件下拉框
        self.refresh_topology_configs_combo()

        # 推荐配置名
        rec_name = core.detect_display_config_name(self.config_manager)
        self.log(f"系统智能推荐的分辨率配置为: {rec_name}")

    def refresh_resolutions_combo(self, select_name=None):
        """刷新下拉配置选择框，带上中文分类标识"""
        # 🛡️ 若未显式指定 select_name，优先保留当前下拉框中已经选中的方案（防止后台心跳刷新把 5376_Triton 篡改为 5376）
        if not select_name:
            current_selected = self.get_current_selected_resolution()
            if current_selected and current_selected in self.config_manager.get_resolutions():
                select_name = current_selected

        self.cb_resolutions.blockSignals(True)
        self.cb_resolutions.clear()
        
        categories = {
            "single_display": "🖥️ 单屏",
            "multi_display": "🖥️🖥️ 多屏",
            "custom_special": "⚙️ 特殊"
        }
        
        found_index = -1
        index_counter = 0
        dup_resolutions = self.config_manager.get_duplicate_resolutions_info()
        
        for cat_name in self.config_manager.get_categories():
            cat_cn = categories.get(cat_name, cat_name)
            for res_name in self.config_manager.get_resolutions_by_category(cat_name):
                dup_tag = ""
                if res_name in dup_resolutions:
                    orig_name, _ = dup_resolutions[res_name]
                    dup_tag = f" ⚠️[与 {orig_name} 布局一致]"
                display_text = f"[{cat_cn}] {res_name}{dup_tag}"
                # 绑定二元组 (category, res_name) 作为 UserData
                self.cb_resolutions.addItem(display_text, (cat_name, res_name))
                if select_name and res_name == select_name:
                    found_index = index_counter
                index_counter += 1
                
        if found_index >= 0:
            self.cb_resolutions.setCurrentIndex(found_index)
        else:
            # 自动选择最匹配的
            rec_name = core.detect_display_config_name(self.config_manager)
            matched_index = -1
            for i in range(self.cb_resolutions.count()):
                data = self.cb_resolutions.itemData(i)
                if data and data[1] == rec_name:
                    matched_index = i
                    break
            if matched_index >= 0:
                self.cb_resolutions.setCurrentIndex(matched_index)
            else:
                # 内存中创建匹配当前显示器的推荐配置方案，但不在此处自动调用 save() 覆盖磁盘，防止后台息屏时将挤压错乱坐标落盘
                self.log(f"⚡ 发现新屏幕拓扑，自动挂载新方案: {rec_name}...")
                info = core.get_screen_resolution_summary()
                cat = "single_display" if info["display_num"] <= 1 else "multi_display"
                
                # 融合当前已存所有方案中的窗口规则列表，并探测当前桌面上实际位置作为初始位置
                initial_mapping = self.create_merged_initial_mapping()
                self.config_manager.set_resolution_mapping(rec_name, initial_mapping, cat)
                
                # 递归重新刷新一次下拉框，此时就能找到这个新创建的方案
                self.cb_resolutions.blockSignals(False)
                self.refresh_resolutions_combo(rec_name)
                return
                
        self.cb_resolutions.blockSignals(False)
        self.on_resolution_changed()

    def create_merged_initial_mapping(self) -> dict:
        """
        融合所有已配置方案的窗口规则并自动探测当前桌面窗口坐标，
        生成用于新分辨率方案的初始窗口坐标映射字典。
        """
        # 1. 搜集所有方案中定义过的窗口 title 及其 exe_path 的并集
        all_titles = {}
        for cat_name in self.config_manager.get_categories():
            for res_name in self.config_manager.get_resolutions_by_category(cat_name):
                mapping = self.config_manager.get_resolution_mapping(res_name)
                for title, raw_pos_str in mapping.items():
                    parts = str(raw_pos_str).split('|')
                    pos_str = parts[0]
                    exe_path = parts[1] if len(parts) > 1 else ""
                    if title not in all_titles or exe_path:
                        all_titles[title] = exe_path
                        
        # 2. 对于每一个 title，检查其当前是否在桌面上运行并获取坐标
        initial_mapping = {}
        for title, exe_path in all_titles.items():
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            found_hwnd = None
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    found_hwnd = found[0][0]
                    break
                    
            if found_hwnd:
                left, top, w, h = core.get_window_rect(found_hwnd)
                # 只有在非最小化并且大小有效的窗口下才采信实际坐标
                if not (left < -10000 and top < -10000) and w > 50 and h > 50:
                    pos_str = f"{left},{top},{w},{h}"
                else:
                    pos_str = "100,100,800,600" # 最小化时使用默认安全大小
            else:
                # 没在运行，则找该窗口在已有配置中的任意坐标作为默认
                pos_str = "100,100,800,600"
                for cat_name in self.config_manager.get_categories():
                    for res_name in self.config_manager.get_resolutions_by_category(cat_name):
                        mapping = self.config_manager.get_resolution_mapping(res_name)
                        if title in mapping:
                            p_str = mapping[title].split('|')[0]
                            if re.match(r"^-?\d+,-?\d+,\d+,\d+$", p_str):
                                pos_str = p_str
                                break
                    if pos_str != "100,100,800,600":
                        break
                        
            if exe_path:
                initial_mapping[title] = f"{pos_str}|{exe_path}"
            else:
                initial_mapping[title] = pos_str
                
        return initial_mapping

    def get_current_selected_resolution(self) -> str:
        """获取当前下拉选中的方案名称 (解包后的真实 res_name)"""
        data = self.cb_resolutions.currentData()
        if data:
            return data[1]
        return ""

    def on_resolution_changed(self):
        """当所选分辨率方案改变时，载入其坐标映射表格"""
        res_name = self.get_current_selected_resolution()
        if not res_name:
            self.table_widget.setRowCount(0)
            return
            
        self.table_widget.blockSignals(True)
        self.table_widget.setRowCount(0)
        
        mapping = self.config_manager.get_resolution_mapping(res_name)
        
        # 分离运行中与未运行的规则，优先级：运行中 > 有路径 > 无路径
        running_items = []
        ready_items = []
        stopped_items = []
        for title, raw_pos_str in mapping.items():
            parts = raw_pos_str.split('|')
            pos_str = parts[0]
            exe_path = parts[1] if len(parts) > 1 else ""
            
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            is_running = False
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    is_running = True
                    if not exe_path:
                        exe_path = core.get_exe_path(found[0][0])
                        if exe_path:
                            self.request_save_config_debounced()
                    break
                    
            if is_running:
                running_items.append((title, pos_str, exe_path))
            elif exe_path and os.path.exists(exe_path):
                ready_items.append((title, pos_str, exe_path))
            else:
                stopped_items.append((title, pos_str, exe_path))
                
        sorted_mapping = running_items + ready_items + stopped_items
        
        for title, pos_str, exe_path in sorted_mapping:
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)
            
            # 匹配规则名称项
            name_item = QTableWidgetItem(title)
            name_item.setForeground(QtGui.QColor("#ffffff"))
            self.table_widget.setItem(row, 0, name_item)
            
            # 位置数据项
            pos_item = QTableWidgetItem(pos_str)
            pos_item.setForeground(QtGui.QColor("#10b981"))
            if exe_path:
                pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, exe_path)
            self.table_widget.setItem(row, 1, pos_item)
            
            # 当前位置列初始化
            cur_item = QTableWidgetItem("[检测中]")
            cur_item.setForeground(QtGui.QColor("#6b7280"))
            self.table_widget.setItem(row, 2, cur_item)
            
        self.table_widget.blockSignals(False)
        self.refresh_current_positions()
        self.refresh_app_shortcuts(rebuild=True)
        self.log(f"已载入配置方案: {res_name} (含 {len(mapping)} 条窗口移动规则)")

    def get_table_data(self) -> dict:
        """从 QTableWidget 抓取当前表格中的数据映射"""
        mapping = {}
        for row in range(self.table_widget.rowCount()):
            name_item = self.table_widget.item(row, 0)
            pos_item = self.table_widget.item(row, 1)
            
            if name_item and pos_item:
                title = name_item.text().strip()
                pos_str = pos_item.text().strip()
                exe_path = pos_item.data(QtCore.Qt.ItemDataRole.UserRole)
                
                if title and re.match(r"^-?\d+,-?\d+,\d+,\d+$", pos_str):
                    if exe_path:
                        mapping[title] = f"{pos_str}|{exe_path}"
                    else:
                        mapping[title] = pos_str
        return mapping

    def save_current_table_to_memory(self):
        """将当前表格的修改暂存进内存中的 config_manager"""
        current_res = self.get_current_selected_resolution()
        if current_res:
            mapping = self.get_table_data()
            self.config_manager.set_resolution_mapping(current_res, mapping)

    def on_table_item_changed(self, item):
        """当单元格数据改变时，自动同步暂存到内存，并刷新状态比对"""
        if item.column() in (0, 1):
            self.save_current_table_to_memory()
            self.refresh_current_positions()

    def add_table_row(self):
        """在表格底部插入一行空规则"""
        self.table_widget.blockSignals(True)
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)
        
        name_item = QTableWidgetItem("新窗口匹配字符")
        name_item.setForeground(QtGui.QColor("#ffffff"))
        self.table_widget.setItem(row, 0, name_item)
        
        pos_item = QTableWidgetItem("0,0,800,600")
        pos_item.setForeground(QtGui.QColor("#10b981"))
        self.table_widget.setItem(row, 1, pos_item)
        
        cur_item = QTableWidgetItem("[新添加]")
        cur_item.setForeground(QtGui.QColor("#6b7280"))
        self.table_widget.setItem(row, 2, cur_item)
        
        self.table_widget.blockSignals(False)
        self.save_current_table_to_memory()
        self.refresh_current_positions()
        self.table_widget.scrollToBottom()

    def delete_table_row(self):
        """删除表格中被选中的行"""
        selected_ranges = self.table_widget.selectedRanges()
        if not selected_ranges:
            QMessageBox.information(self, "提示", "请先在左侧列表中点击选择一行")
            return
            
        rows_to_delete = sorted(list(set(
            row for r in selected_ranges for row in range(r.topRow(), r.bottomRow() + 1)
        )), reverse=True)
        
        self.table_widget.blockSignals(True)
        for r in rows_to_delete:
            self.table_widget.removeRow(r)
        self.table_widget.blockSignals(False)
        
        self.save_current_table_to_memory()
        self.log(f"删除了 {len(rows_to_delete)} 条移动规则")

    def new_resolution(self):
        """新建一个分类配置方案"""
        dialog = NewResolutionDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.res_name
            cat = dialog.category
            if name in self.config_manager.get_resolutions():
                QMessageBox.warning(self, "警告", "方案标识已存在")
                return
            # 写入对应分类
            self.config_manager.set_resolution_mapping(name, {}, cat)
            self.refresh_resolutions_combo(name)
            self.log(f"成功创建新配置方案: {name} (所属分类: {cat})")

    def copy_resolution(self):
        """复制当前选中的方案为新方案，保留在原分类中"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            return
            
        name, ok = QInputDialog.getText(
            self, "复制当前配置方案", 
            f"请输入复制出来的方案名称 (原方案: {current_res}):", 
            text=f"{current_res}_copy"
        )
        if ok and name.strip():
            name = name.strip()
            if name in self.config_manager.get_resolutions():
                QMessageBox.warning(self, "警告", "方案名称已存在")
                return
                
            current_mapping = self.config_manager.get_resolution_mapping(current_res)
            current_cat = self.config_manager.get_category_of_resolution(current_res)
            
            # 拷贝一份
            self.config_manager.set_resolution_mapping(name, current_mapping.copy(), current_cat)
            self.refresh_resolutions_combo(name)
            self.log(f"成功将 {current_res} 复制为新配置: {name} (所属分类: {current_cat})")

    def delete_resolution(self):
        """删除当前选中的方案"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            return
            
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要永久删除方案 {current_res} 吗？\n此操作仅在内存生效，若已保存配置文件，需点击底部的‘保存配置’才会真正写入磁盘。", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.delete_resolution(current_res)
            self.refresh_resolutions_combo()
            self.log(f"删除了配置方案: {current_res}")

    def auto_detect_and_set(self):
        """一键识别当前系统应匹配的配置名，并应用到 UI"""
        self.load_screen_info()
        self._last_topology_signature = core.get_screen_topology_signature()
        rec_name = core.detect_display_config_name(self.config_manager)
        
        matched_index = -1
        for i in range(self.cb_resolutions.count()):
            data = self.cb_resolutions.itemData(i)
            if data and data[1] == rec_name:
                matched_index = i
                break
                
        if matched_index >= 0:
            self.cb_resolutions.setCurrentIndex(matched_index)
            self.log(f"已根据当前分辨率自动切换配置方案为: {rec_name}")
        else:
            # 询问是否新建
            reply = QMessageBox.question(
                self, "未找到对应匹配方案", 
                f"当前屏幕探测到对应的配置标识为 '{rec_name}'，但当前配置库中没有该方案。\n是否使用此名字新建并融合当前桌面坐标生成配置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 默认基于物理显示器数量放置于 single_display 或 multi_display
                info = core.get_screen_resolution_summary()
                cat = "single_display" if info["display_num"] <= 1 else "multi_display"
                
                initial_mapping = self.create_merged_initial_mapping()
                self.config_manager.set_resolution_mapping(rec_name, initial_mapping, cat)
                self.config_manager.save()
                self.refresh_resolutions_combo(rec_name)

    def capture_desktop_windows(self):
        """运行桌面窗口抓取对话框，并将选定坐标合并入当前方案"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            QMessageBox.warning(self, "提示", "请先选择或创建一个配置方案")
            return
            
        dialog = CaptureWindowsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selected_windows
            if not selected:
                return
                
            self.table_widget.blockSignals(True)
            added_count = 0
            updated_count = 0
            
            for title, pos_str, exe_path in selected:
                found_row = -1
                for row in range(self.table_widget.rowCount()):
                    t_item = self.table_widget.item(row, 0)
                    if t_item and t_item.text().strip() == title:
                        found_row = row
                        break
                        
                if found_row >= 0:
                    pos_item = self.table_widget.item(found_row, 1)
                    pos_item.setText(pos_str)
                    if exe_path:
                        pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, exe_path)
                    updated_count += 1
                else:
                    row = self.table_widget.rowCount()
                    self.table_widget.insertRow(row)
                    
                    name_item = QTableWidgetItem(title)
                    name_item.setForeground(QtGui.QColor("#ffffff"))
                    self.table_widget.setItem(row, 0, name_item)
                    
                    pos_item = QTableWidgetItem(pos_str)
                    pos_item.setForeground(QtGui.QColor("#10b981"))
                    if exe_path:
                        pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, exe_path)
                    self.table_widget.setItem(row, 1, pos_item)
                    added_count += 1
                    
            self.table_widget.blockSignals(False)
            self.save_current_table_to_memory()
            self.log(f"捕获窗口导入完成：追加了 {added_count} 条，覆盖更新了 {updated_count} 条。")

    def update_existing_windows_pos(self):
        """一键从桌面上获取当前配置表中已存在的窗口的实际坐标，并原地回填更新"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            QMessageBox.warning(self, "提示", "请先选择或创建一个配置方案")
            return
            
        # 获取当前表格中已存在的全部规则名 (匹配标识)
        existing_rules = []
        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.item(row, 0)
            if item:
                existing_rules.append((row, item.text().strip()))
                
        if not existing_rules:
            self.log("当前配置方案无任何规则，无需更新。")
            return
            
        self.table_widget.blockSignals(True)
        updated_count = 0
        
        for row, title in existing_rules:
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            found_hwnd = None
            found_exe_path = ""
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    found_hwnd, found_title = found[0]
                    found_exe_path = core.get_exe_path(found_hwnd)
                    break
                    
            if found_hwnd:
                # 获取桌面当前真实的坐标大小
                left, top, width, height = core.get_window_rect(found_hwnd)
                # 排除被最小化隐藏的异常大负值坐标
                if left < -10000 and top < -10000:
                    self.log(f"⚠️ 窗口 '{title}' 当前被最小化，已跳过捕获。")
                    continue
                    
                pos_str = f"{left},{top},{width},{height}"
                
                # 检查是否和原配置不同，或者是否缺 exe_path
                pos_item = self.table_widget.item(row, 1)
                old_pos = pos_item.text().strip() if pos_item else ""
                old_exe_path = pos_item.data(QtCore.Qt.ItemDataRole.UserRole) if pos_item else ""
                
                # 只有当前配置中 exe_path 为空时，才自动填入
                # （已有配置的路径不覆盖，防止把自定义命令行覆盖为系统可执行文件）
                if pos_item and found_exe_path and not old_exe_path:
                    pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, found_exe_path)
                    self.request_save_config_debounced()
                
                if old_pos != pos_str:
                    if not pos_item:
                        pos_item = QTableWidgetItem(pos_str)
                        pos_item.setForeground(QtGui.QColor("#10b981"))
                        if found_exe_path:
                            pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, found_exe_path)
                        self.table_widget.setItem(row, 1, pos_item)
                    else:
                        pos_item.setText(pos_str)
                        
                    # 给这行坐标加粗以作视觉标记
                    pos_item.setFont(QtGui.QFont("Segoe UI", weight=QtGui.QFont.Weight.Bold))
                    
                    self.log(f"🔄 更新成功: '{title}' 坐标 [{old_pos}] ➡ [{pos_str}]")
                    updated_count += 1
                else:
                    self.log(f"➖ 窗口 '{title}' 位置未改变。")
                    
        self.table_widget.blockSignals(False)
        self.refresh_current_positions()
        self.save_current_table_to_memory()
        
        if updated_count > 0:
            self.log(f"一键更新完成！成功更新了 {updated_count} 个运行中窗口的最新坐标。")
            QMessageBox.information(self, "更新完成", f"已成功更新 {updated_count} 个窗口在当前桌面上的位置坐标！\n请不要忘记点击右下角‘保存配置’将其写入磁盘。")
        else:
            self.log("一键更新完成！当前桌面运行中的窗口位置与配置表中一致。")
            QMessageBox.information(self, "提示", "所有窗口位置均与配置表中一致，无需更新。")

    def refresh_current_positions(self):
        """刷新第三列：当前桌面上各窗口的实际位置，并比对颜色 (一致显绿, 不一致显红, 未运行显灰)"""
        self.table_widget.blockSignals(True)
        for row in range(self.table_widget.rowCount()):
            title_item = self.table_widget.item(row, 0)
            pos_item = self.table_widget.item(row, 1)
            if not title_item or not pos_item:
                continue
                
            title = title_item.text().strip()
            cfg_pos = pos_item.text().strip()
            
            # 支持 .py / .exe 互相匹配
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            found_hwnd = None
            found_exe_path = ""
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    found_hwnd, _ = found[0]
                    found_exe_path = core.get_exe_path(found_hwnd)
                    break
                    
            cur_item = self.table_widget.item(row, 2)
            if not cur_item:
                cur_item = QTableWidgetItem()
                self.table_widget.setItem(row, 2, cur_item)
                
            # 设置只读，只允许查看和点击更新
            cur_item.setFlags(cur_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            
            if found_hwnd:
                # 只有当前配置中 exe_path 为空时，才自动填入探测到的进程路径
                # （已有配置的路径不覆盖，防止把 'start cmd /k ...' 这类自定义命令行覆盖为 cmd.exe）
                old_exe_path_cur = pos_item.data(QtCore.Qt.ItemDataRole.UserRole) if pos_item else ""
                if found_exe_path and not old_exe_path_cur:
                    pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, found_exe_path)
                    self.request_save_config_debounced()
                    
                left, top, width, height = core.get_window_rect(found_hwnd)
                if left < -10000 and top < -10000:
                    cur_item.setText("[最小化中]")
                    cur_item.setForeground(QtGui.QColor("#eab308")) # 黄色
                else:
                    real_pos = f"{left},{top},{width},{height}"
                    cur_item.setText(real_pos)
                    
                    if real_pos == cfg_pos:
                        cur_item.setForeground(QtGui.QColor("#10b981")) # 绿色，完全一致
                    else:
                        cur_item.setForeground(QtGui.QColor("#ef4444")) # 红色，不一致
            else:
                cur_item.setText("[未运行]")
                cur_item.setForeground(QtGui.QColor("#6b7280")) # 灰色，未检测到
                
        self.table_widget.blockSignals(False)
        self.refresh_app_shortcuts(rebuild=False)

    def refresh_app_shortcuts(self, rebuild=True):
        """
        刷新快捷启动程序格子面板
        rebuild=True: 重新根据排序规则构建按钮控件
        rebuild=False: 仅刷新每个按钮的运行状态与颜色，但如果发现有新运行或停止运行的未固定程序，会自动升级为 rebuild=True
        """
        try:
            # 获取点击热度与固定列表
            hotness = self.config_manager.config_data.setdefault("app_click_counts", {})
            pinned = self.config_manager.config_data.setdefault("pinned_shortcuts", [])
            
            # 检测候选程序是否正在运行
            def _is_running(t):
                ttry = [t]
                if t.endswith('.py') and not t.startswith('py'):
                    ttry.append(t.replace('.py', '.exe'))
                elif t.endswith('.exe'):
                    ttry.append(t.replace('.exe', '.py'))
                for x in ttry:
                    if core.find_windows_by_title_safe(x):
                        return True
                return False

            # 搜集所有方案中去重后的 candidates 程序 (title -> exe_path)
            candidates = {}
            current_res = self.get_current_selected_resolution()
            for cat_name in self.config_manager.get_categories():
                for res_name in self.config_manager.get_resolutions_by_category(cat_name):
                    if res_name == current_res:
                        continue
                    mapping = self.config_manager.get_resolution_mapping(res_name)
                    for title, raw_pos_str in mapping.items():
                        parts = str(raw_pos_str).split('|')
                        if len(parts) > 1 and parts[1].strip():
                            if title not in candidates:
                                candidates[title] = parts[1].strip()
            
            if current_res:
                current_mapping = self.config_manager.get_resolution_mapping(current_res)
                for title, raw_pos_str in current_mapping.items():
                    parts = str(raw_pos_str).split('|')
                    if len(parts) > 1 and parts[1].strip():
                        candidates[title] = parts[1].strip()

            # 过滤：仅保留已固定（常用）或正在运行的程序，默认不自动显示其他多余的未运行未固定程序
            expected_visible_items = [
                (title, exe_path) for title, exe_path in candidates.items()
                if title in pinned or _is_running(title)
            ]
            expected_visible_titles = {item[0] for item in expected_visible_items}
            current_visible_titles = set(self.shortcut_buttons.keys())

            # 如果检测到当前显示的按钮集合与期望显示的不一致（比如有未固定的程序启动或退出），强制 rebuild
            if not rebuild and expected_visible_titles != current_visible_titles:
                rebuild = True

            if rebuild:
                # 如果没有任何需要显示的程序，显示占位提示
                if not expected_visible_items:
                    while self.shortcuts_grid_layout.count() > 1:
                        child = self.shortcuts_grid_layout.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
                    self.lbl_shortcuts_tip = QLabel("暂无快捷启动程序配置，请先在下方表格中为窗口配置'程序路径'并添加到常用。")
                    self.lbl_shortcuts_tip.setStyleSheet("color: #6b7280; font-style: italic;")
                    self.shortcuts_grid_layout.insertWidget(0, self.lbl_shortcuts_tip)
                    self.shortcut_buttons = {}
                    return
                
                # 存在显示程序，移除提示
                if hasattr(self, 'lbl_shortcuts_tip') and self.lbl_shortcuts_tip:
                    try:
                        self.lbl_shortcuts_tip.deleteLater()
                    except:
                        pass
                    self.lbl_shortcuts_tip = None
                
                # 排序规则：⭐固定优先（按固定顺序）> ▶运行中优先 > 热度次之
                def _sort_key(item):
                    t = item[0]
                    if t in pinned:
                        return (0, pinned.index(t), 0)
                    running_status = 0 if _is_running(t) else 1
                    return (1, running_status, -hotness.get(t, 0))
                
                sorted_candidates = sorted(expected_visible_items, key=_sort_key)
                
                # 清除旧按钮（保留末尾的 addStretch 弹簧）
                while self.shortcuts_grid_layout.count() > 1:
                    child = self.shortcuts_grid_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                self.shortcut_buttons = {}
                
                # 重新构建按钮并插入到布局
                for i, (title, exe_path) in enumerate(sorted_candidates):
                    is_pinned = title in pinned
                    prefix = "⭐ " if is_pinned else ""
                    display_title = prefix + title
                    if len(display_title) > 18:
                        display_title = display_title[:16] + "..."
                        
                    btn = QPushButton(display_title)
                    btn.setMinimumWidth(110)
                    click_count = hotness.get(title, 0)
                    import textwrap, html as _html
                    path_str = exe_path or '(未配置)'
                    path_html = '<br>&nbsp;&nbsp;&nbsp;&nbsp;'.join(
                        _html.escape(p) for p in textwrap.wrap(path_str, width=50)
                    ) or _html.escape(path_str)
                    pin_hint = "已固定" if is_pinned else "右键可固定到常用"
                    tooltip_text = (
                        f"<b style='color:#ffffff;'>{_html.escape(title)}</b><br>"
                        f"<span style='color:#10b981;'>启动路径:</span> "
                        f"<span style='color:#d1d5db;'>{path_html}</span><br>"
                        f"<span style='color:#6b7280;'>点击次数: {click_count} 次 · {pin_hint}</span>"
                    )
                    btn.setToolTip(tooltip_text)
                    btn.setMinimumHeight(42)
                    btn.setMaximumHeight(42)
                    
                    btn.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
                    btn.customContextMenuRequested.connect(
                        lambda pos, t=title, p=exe_path: self.show_shortcut_context_menu(pos, t, p)
                    )
                    btn.clicked.connect(lambda checked, t=title, p=exe_path: self.on_shortcut_clicked(t, p))
                    self.shortcut_buttons[title] = btn
                    self.shortcuts_grid_layout.insertWidget(i, btn)
            
            # 刷新状态与颜色样式
            for title, btn in self.shortcut_buttons.items():
                titles_to_try = [title]
                if title.endswith('.py') and not title.startswith('py'):
                    titles_to_try.append(title.replace('.py', '.exe'))
                elif title.endswith('.exe'):
                    titles_to_try.append(title.replace('.exe', '.py'))
                
                is_running = False
                for t in titles_to_try:
                    if core.find_windows_by_title_safe(t):
                        is_running = True
                        break
                
                if is_running:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #0284c7;
                            border: 1px solid #0ea5e9;
                            border-radius: 4px;
                            color: #ffffff;
                            font-weight: bold;
                            font-size: 12px;
                        }
                        QPushButton:hover {
                            background-color: #0ea5e9;
                            border-color: #38bdf8;
                        }
                        QPushButton:pressed {
                            background-color: #0369a1;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #1e1e24;
                            border: 1px dashed #4b5563;
                            border-radius: 4px;
                            color: #9ca3af;
                            font-size: 12px;
                        }
                        QPushButton:hover {
                            background-color: #2d2d39;
                            border-color: #9ca3af;
                            color: #ffffff;
                        }
                        QPushButton:pressed {
                            background-color: #15151a;
                        }
                    """)
        except Exception as e:
            self.log(f"⚠️ 刷新快捷启动区出错: {e}")

    def open_program_dir(self, exe_path: str):
        """在 Windows 资源管理器中打开程序所在目录并定位物理文件"""
        if not exe_path or not exe_path.strip():
            self.log("⚠️ 无法打开目录：程序启动路径未配置或为空")
            QMessageBox.information(self, "提示", "当前程序未配置启动路径，请先右键选择‘编辑程序启动路径’。")
            return
            
        import os
        import subprocess
        
        is_valid, final_exe, _, _, _ = self.resolve_and_validate_cmd(exe_path)
        target_path = final_exe if (is_valid and final_exe) else exe_path.strip().strip('"').strip("'")
        
        if os.path.exists(target_path):
            if os.path.isfile(target_path):
                try:
                    subprocess.Popen(f'explorer /select,"{os.path.normpath(target_path)}"')
                    self.log(f"📂 已在资源管理器中定位并打开文件: {target_path}")
                except Exception as e:
                    self.log(f"❌ 打开程序目录失败: {e}")
            else:
                try:
                    os.startfile(target_path)
                    self.log(f"📂 已打开程序目录: {target_path}")
                except Exception as e:
                    self.log(f"❌ 打开程序目录失败: {e}")
        else:
            dir_name = os.path.dirname(target_path)
            if dir_name and os.path.exists(dir_name):
                try:
                    os.startfile(dir_name)
                    self.log(f"📂 目标文件不存在，已打开上级目录: {dir_name}")
                except Exception as e:
                    self.log(f"❌ 打开目录失败: {e}")
            else:
                self.log(f"⚠️ 打开目录失败：找不到物理路径 -> {target_path}")
                QMessageBox.warning(self, "路径错误", f"无法打开程序目录，目标物理路径或目录不存在:\n{target_path}")

    def show_shortcut_context_menu(self, pos, title, exe_path):
        """常用程序快捷按钮的右键上下文菜单"""
        btn = self.sender()
        if not btn:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #1e1e24; color: #ffffff; border: 1px solid #4b5563; } QMenu::item:selected { background-color: #374151; }")
        
        # 1. 启动与目录选项
        open_dir_action = None
        if exe_path:
            display_name = os.path.basename(exe_path)
            if not display_name:
                display_name = exe_path
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."
            start_action = menu.addAction(f"🚀 启动程序 ({display_name})")
            start_admin_action = menu.addAction(f"🛡️ 以管理员身份启动 ({display_name})")
            open_dir_action = menu.addAction(f"📂 打开程序目录")
            menu.addSeparator()
        else:
            start_action = None
            start_admin_action = None

        # 2. 应用布局选项
        apply_shortcut_action = menu.addAction("🎯 应用该窗口坐标 (对齐位置)")
        menu.addSeparator()

        # 3. 移除/固定常用选项
        pinned_list = self.config_manager.config_data.setdefault("pinned_shortcuts", [])
        is_pinned = title in pinned_list
        
        if is_pinned:
            pin_action = menu.addAction("✖ 从常用移除")
        else:
            pin_action = menu.addAction("📌 固定到常用")
            
        action = menu.exec(btn.mapToGlobal(pos))
        
        if start_action and action == start_action:
            self._launch_program(exe_path, title, None)
        elif start_admin_action and action == start_admin_action:
            self._launch_as_admin(exe_path, title, None)
        elif open_dir_action and action == open_dir_action:
            self.open_program_dir(exe_path)
        elif apply_shortcut_action and action == apply_shortcut_action:
            status, msg = self.apply_window_layout_by_title(title)
            if status == "not_found":
                QMessageBox.information(self, "提示", f"桌面当前未检测到运行中的窗口: '{title}'\n可尝试通过右键菜单‘🚀 启动程序’启动它。")
            elif status == "error":
                QMessageBox.warning(self, "错误", msg)
        elif action == pin_action:
            if is_pinned:
                pinned_list.remove(title)
                self.log(f"✖ 已从常用移除: '{title}'")
            else:
                if title not in pinned_list:
                    pinned_list.append(title)
                self.log(f"📌 已成功将 '{title}' 固定到常用。")
            self.config_manager.config_data["pinned_shortcuts"] = pinned_list
            self.config_manager.save()
            self.refresh_app_shortcuts(rebuild=True)

    def on_shortcut_clicked(self, title, exe_path):
        """快捷键点击事件：增加热度，判断运行状态，激活或启动"""
        try:
            hotness = self.config_manager.config_data.setdefault("app_click_counts", {})
            hotness[title] = hotness.get(title, 0) + 1
            self.config_manager.save()
            
            # 判断是否运行
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
            
            is_running = False
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    is_running = True
                    break
            
            if is_running:
                self.log(f"正在切换至前台激活窗口: '{title}'...")
                success = core.bring_window_to_top_by_title(title)
                if success:
                    self.log(f"✅ 已激活窗口: '{title}'")
                else:
                    self.log(f"⚠️ 激活窗口 '{title}' 失败")
            else:
                # 探测并在窗口出现后自动对齐
                pos_str = "0,0,800,600"
                current_res = self.get_current_selected_resolution()
                if current_res:
                    mapping = self.config_manager.get_resolution_mapping(current_res)
                    if title in mapping:
                        pos_str = mapping[title].split('|')[0]
                
                class DummyPosItem:
                    def text(self):
                        return pos_str
                
                self._launch_program(exe_path, title, DummyPosItem())
            
            # 重新根据热度排版
            self.refresh_app_shortcuts(rebuild=True)
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法启动程序: {e}")
            self.log(f"启动程序失败: {e}")

    def on_table_cell_clicked(self, row, column):
        """点击单元格触发快速交互：保留接口备用，原本的第2列单击回填已移至双击触发"""
        pass

    def center_window_on_current_screen(self, row):
        """将选定行的窗口物理居中移动到其自身当前所在的屏幕(未运行时回退至本程序所在屏幕)，并同步回写配置与当前位置"""
        import time
        title_item = self.table_widget.item(row, 0)
        pos_item = self.table_widget.item(row, 1)
        if not title_item or not pos_item:
            return
            
        title = title_item.text().strip()
        cfg_pos = pos_item.text().strip()
        
        # 1. 默认大小与坐标解析
        w, h = 800, 600  # 默认兜底大小
        parts = [p.strip() for p in cfg_pos.split(',')]
        if len(parts) == 4:
            try:
                w = int(parts[2])
                h = int(parts[3])
            except ValueError:
                pass
                
        # 2. 检查窗口是否正在运行，如果正在运行，尝试获取其实际大小
        titles_to_try = [title]
        if title.endswith('.py') and not title.startswith('py'):
            titles_to_try.append(title.replace('.py', '.exe'))
        elif title.endswith('.exe'):
            titles_to_try.append(title.replace('.exe', '.py'))
            
        found_hwnd = None
        for t in titles_to_try:
            found = core.find_windows_by_title_safe(t)
            if found:
                found_hwnd, _ = found[0]
                break
                
        window_center_point = None
        if found_hwnd:
            left, top, rw, rh = core.get_window_rect(found_hwnd)
            # 排除最小化状态下的负数位置
            if not (left < -10000 and top < -10000) and rw > 50 and rh > 50:
                w, h = rw, rh
                # 计算运行中窗口的中心点
                window_center_point = QtCore.QPoint(left + rw // 2, top + rh // 2)

        # 3. 确定目标屏幕：若窗口运行中，则取其中心点所在的屏幕；否则取当前坐标管理器本身所在的屏幕
        screen = None
        if window_center_point:
            screen = QtGui.QGuiApplication.screenAt(window_center_point)
            
        if not screen:
            # 未运行或获取失败，回退至坐标管理器 UI 所在的显示器
            screen = self.screen()
            
        if not screen:
            # 终极回退至主屏幕
            screen = QtGui.QGuiApplication.primaryScreen()
            
        if not screen:
            self.log(f"⚠️ 无法获取目标显示器信息")
            return
            
        # 4. 获取屏幕可用工作区
        geom = screen.availableGeometry()
        screen_x = geom.x()
        screen_y = geom.y()
        screen_w = geom.width()
        screen_h = geom.height()
        
        # 5. 计算居中位置
        new_x = screen_x + (screen_w - w) // 2
        new_y = screen_y + (screen_h - h) // 2
        new_pos_str = f"{new_x},{new_y},{w},{h}"
        
        # 6. 同步更新 UI 配置与回写内存
        self.table_widget.blockSignals(True)
        pos_item.setText(new_pos_str)
        # 坐标加粗以作视觉标记
        pos_item.setFont(QtGui.QFont("Segoe UI", weight=QtGui.QFont.Weight.Bold))
        self.table_widget.blockSignals(False)
        
        self.save_current_table_to_memory()
        
        # 7. 物理移动窗口 (如果窗口运行中)
        if found_hwnd:
            self.log(f"正在尝试将窗口 '{title}' 在其所在显示器居中移动...")
            # 如果最小化，先还原
            left, top, _, _ = core.get_window_rect(found_hwnd)
            if left < -10000 and top < -10000:
                core.user32.ShowWindow(found_hwnd, core.SW_SHOWNORMAL)
                time.sleep(0.1)
                
            if core.set_window_hwnd_pos(found_hwnd, new_pos_str, title=title):
                self.log(f"📺 居中显示: 成功将窗口 '{title}' 移动到其屏幕居中位置: [{new_pos_str}]")
            else:
                self.log(f"⚠️ 物理移动窗口 '{title}' 失败")
        else:
            self.log(f"📺 居中显示: 窗口 '{title}' 当前未运行，已在默认屏幕同步居中配置坐标为 [{new_pos_str}]。")
            
        # 8. 刷新当前状态列
        self.refresh_current_positions()

    def show_context_menu(self, pos):
        """表格右键菜单：支持将选中的窗口置顶并激活、在当前屏幕居中"""
        item = self.table_widget.itemAt(pos)
        if not item:
            return
            
        row = item.row()
        title_item = self.table_widget.item(row, 0)
        if not title_item or not title_item.text().strip():
            return
            
        title = title_item.text().strip()
        
        # 弹窗式右键菜单，匹配整体暗黑风格
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #f3f4f6;
                border: 1px solid #475569;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 18px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: white;
            }
        """)
        
        pos_item = self.table_widget.item(row, 1)
        exe_path = pos_item.data(QtCore.Qt.ItemDataRole.UserRole) if pos_item else ""
        
        # 自动自愈：如果右键时发现没有 exe_path，动态抓取一下（对付刚启动还没保存的情况）
        if not exe_path and pos_item:
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            for t in titles_to_try:
                found = core.find_windows_by_title_safe(t)
                if found:
                    extracted_path = core.get_exe_path(found[0][0])
                    if extracted_path:
                        exe_path = extracted_path
                        pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, exe_path)
                        self.request_save_config_debounced()
                    break
        
        start_action = None
        start_admin_action = None
        open_dir_action = None
        is_valid = False
        if exe_path:
            is_valid, _, _, _, _ = self.resolve_and_validate_cmd(exe_path)
            
        if is_valid:
            display_name = os.path.basename(exe_path)
            if not display_name:
                display_name = exe_path
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."
            start_action = menu.addAction(f"🚀 启动程序 ({display_name})")
            start_admin_action = menu.addAction(f"🛡️ 以管理员身份启动 ({display_name})")
            open_dir_action = menu.addAction("📂 打开程序目录")
            menu.addSeparator()
        elif exe_path:
            open_dir_action = menu.addAction("📂 打开程序目录")
            menu.addSeparator()

        menu.addSeparator()
        apply_single_action = menu.addAction("🎯 应用该窗口坐标 (移动至配置位置)")
        apply_all_action = menu.addAction("🚀 应用当前方案所有窗口布局")
        menu.addSeparator()

        pinned_list = self.config_manager.config_data.setdefault("pinned_shortcuts", [])
        is_pinned = title in pinned_list
        if is_pinned:
            pin_action = menu.addAction("✖ 从常用移除")
        else:
            pin_action = menu.addAction("📌 固定到常用")
        activate_action = menu.addAction("📌 窗口置顶并激活")
        center_action = menu.addAction("📺 居中显示于程序所在屏幕")
        edit_action = menu.addAction("✏️ 编辑该单元格")
        edit_path_action = menu.addAction("⚙️ 编辑程序启动路径")
        action = menu.exec(self.table_widget.mapToGlobal(pos))
        
        if start_action and action == start_action:
            self._launch_program(exe_path, title, pos_item)
        elif start_admin_action and action == start_admin_action:
            self._launch_as_admin(exe_path, title, pos_item)
        elif open_dir_action and action == open_dir_action:
            self.open_program_dir(exe_path)
        elif apply_single_action and action == apply_single_action:
            pos_text = pos_item.text().strip() if pos_item else ""
            status, msg = self.apply_window_layout_by_title(title, pos_text)
            if status == "not_found":
                QMessageBox.information(self, "提示", f"桌面当前未检测到运行中的窗口: '{title}'\n可尝试通过右键菜单‘🚀 启动程序’启动它。")
            elif status == "error":
                QMessageBox.warning(self, "错误", msg)
        elif apply_all_action and action == apply_all_action:
            self.apply_current_layout()
        elif action == pin_action:
            # 如果未配置启动路径，先引导配置路径，配置完自动拉入常用
            if not exe_path:
                self.log(f"⚠️ 无法添加，程序 '{title}' 的启动路径为空，正在打开路径配置对话框...")
                self._editing_path = True
                try:
                    dialog = EditPathDialog(title, "", self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        new_path = dialog.final_path
                        if pos_item:
                            pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, new_path)
                            self.save_current_table_to_memory()
                            self.request_save_config_debounced()
                            self.log(f"🎯 已成功设置程序 '{title}' 的启动路径 ➡ {new_path}")
                            self.on_resolution_changed()
                            exe_path = new_path
                finally:
                    self._editing_path = False

            if exe_path:
                if is_pinned:
                    pinned_list.remove(title)
                    self.log(f"✖ 已从常用移除: '{title}'")
                else:
                    if title not in pinned_list:
                        pinned_list.append(title)
                    self.log(f"📌 已成功将 '{title}' 固定到常用。")
                self.config_manager.config_data["pinned_shortcuts"] = pinned_list
                self.config_manager.save()
                self.refresh_app_shortcuts(rebuild=True)
        elif action == activate_action:
            self.on_table_cell_double_clicked(row, 0)
        elif action == center_action:
            self.center_window_on_current_screen(row)
        elif action == edit_action:
            self.table_widget.editItem(item)
        elif action == edit_path_action:
            # 标记正在编辑路径，防止 wait_and_apply 定时器因模糊匹配对话框标题而误移位
            self._editing_path = True
            try:
                dialog = EditPathDialog(title, exe_path, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    new_path = dialog.final_path
                    if pos_item:
                        pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, new_path)
                        self.save_current_table_to_memory()
                        self.request_save_config_debounced()
                        self.log(f"🎯 已更新程序 '{title}' 的启动路径 ➡ {new_path}")
                        self.on_resolution_changed()
            finally:
                self._editing_path = False

    def _setup_post_launch_layout_timer(self, title, pos_item):
        """程序启动后启动定时器，高频轮询检测窗口创建并应用坐标"""
        pos_str = pos_item.text().strip()
        def wait_and_apply(attempts=0):
            if attempts > 30: # 尝试30次，共15秒
                self.log(f"⚠️ 启动程序 '{title}' 等待窗口创建超时，放弃自动应用布局。")
                return
            
            # 若正在编辑路径对话框，跳过本轮（防止模糊标题匹配误移对话框）
            if getattr(self, '_editing_path', False):
                QtCore.QTimer.singleShot(500, lambda: wait_and_apply(attempts + 1))
                return
                
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            moved = False
            for t in titles_to_try:
                if core.set_window_pos_by_title(t, pos_str, activate_topmost=True):
                    self.log(f"✅ 自动布局: 成功捕捉刚启动的 '{t}' 并移动到配置坐标 [{pos_str}] 且已前台置顶激活")
                    self.refresh_current_positions()
                    self.refresh_app_shortcuts(rebuild=True)
                    moved = True
                    break
                    
            if not moved:
                QtCore.QTimer.singleShot(500, lambda: wait_and_apply(attempts + 1))
                
        # 给予进程初始创建时间 1.5 秒后开始高频轮询探测
        QtCore.QTimer.singleShot(1500, wait_and_apply)

    def resolve_and_validate_cmd(self, cmd_str):
        """
        智能解析并校验命令行字符串。
        返回元组 (is_valid, final_exe, final_args, is_shell, error_msg)
        - is_valid: 是否校验通过
        - final_exe: 解析出的可执行程序路径或命令
        - final_args: 参数列表或参数字符串
        - is_shell: 是否需要 shell=True 模式运行
        - error_msg: 校验失败时的提示
        """
        import shutil
        import os
        import shlex
        
        cmd_str = cmd_str.strip()
        # 💥 自适应清理可能被错误包裹的外部整体引号 (例如 "start cmd /k ..." 或 "D:\My Path\App.exe -arg")
        if (cmd_str.startswith('"') and cmd_str.endswith('"')) or (cmd_str.startswith("'") and cmd_str.endswith("'")):
            inner = cmd_str[1:-1].strip()
            if " " in inner or any(marker in inner for marker in (";", "&&", "||", "|", '"', "'")):
                cmd_str = inner

        if not cmd_str:
            return False, "", "", False, "路径配置为空"

        # 首先检查：如果整个字符串作为一个物理路径存在，直接通过并返回
        # 这对 Windows 上包含空格但未包裹双引号的完整可执行路径提供了直接支持
        if os.path.exists(cmd_str) and not os.path.isdir(cmd_str):
            return True, cmd_str, [], False, ""

        # 如果包含 cd，或者包含多条命令连接符如 ;, &&, ||，则是复杂的 shell 命令
        if any(marker in cmd_str for marker in (";", "&&", "||")) or cmd_str.startswith("cd ") or cmd_str.startswith("cd/"):
            return True, "", cmd_str, True, ""
            
        # 用简单方式分割命令行（考虑带引号的路径）
        try:
            # 在 Windows 上可以使用 posix=False 防止反斜杠被转义
            parts = shlex.split(cmd_str, posix=False)
        except Exception:
            parts = cmd_str.split()
            
        if not parts:
            return False, "", "", False, "解析命令行失败"

        # 贪婪地拼合前面的 parts 块，以支持 Windows 上未包裹引号但包含空格的物理路径
        found_exe = None
        args_list = []
        for i in range(len(parts)):
            candidate = " ".join(parts[:i+1])
            # 去除首尾的多余引号
            if (candidate.startswith('"') and candidate.endswith('"')) or (candidate.startswith("'") and candidate.endswith("'")):
                candidate_clean = candidate[1:-1]
            else:
                candidate_clean = candidate
            
            if os.path.isfile(candidate_clean):
                found_exe = candidate_clean
                args_list = parts[i+1:]
                break
                
        if found_exe:
            # 清理剩余参数的多余引号
            cleaned_args = []
            for arg in args_list:
                if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                    cleaned_args.append(arg[1:-1])
                else:
                    cleaned_args.append(arg)
            return True, found_exe, cleaned_args, False, ""

        # 如果没有通过物理贪婪拼接找到，回退到 parts[0] 的标准校验逻辑
        first_part = parts[0]
        # 去除首尾的引号
        if (first_part.startswith('"') and first_part.endswith('"')) or (first_part.startswith("'") and first_part.endswith("'")):
            first_part = first_part[1:-1]
            
        # 1. 物理路径存在
        if os.path.exists(first_part):
            return True, first_part, parts[1:], False, ""
            
        # 2. 系统 Path 中存在 (如 python, cmd 等)
        which_path = shutil.which(first_part)
        if which_path:
            return True, which_path, parts[1:], False, ""
            
        # 3. 兼容没有后缀名的系统命令
        for ext in ('.exe', '.bat', '.cmd'):
            which_path = shutil.which(first_part + ext)
            if which_path:
                return True, which_path, parts[1:], False, ""
                
        # 4. 如果是 python 开头，有可能在 path 里，也可能是特殊的 python 别名，做宽松通过
        if first_part.lower() in ("python", "python3", "py", "cmd", "cmd.exe", "powershell", "powershell.exe"):
            return True, first_part, parts[1:], True, ""
            
        return False, "", "", False, f"找不到可执行程序: '{first_part}'"

    def _get_quoted_cmd(self, final_exe, final_args, raw_exe_path):
        """
        根据解析出来的 final_exe 和 final_args，重新构建带双引号保护的命令行。
        防止包含空格的物理路径在 Windows cmd.exe 环境下解析执行出错。
        """
        if not final_exe:
            return raw_exe_path
            
        # 如果是复杂的 shell 连接命令，直接返回原始的
        if any(marker in raw_exe_path for marker in (";", "&&", "||")) or raw_exe_path.strip().startswith("cd ") or raw_exe_path.strip().startswith("cd/"):
            return raw_exe_path
            
        exe_quoted = final_exe
        if " " in final_exe and not (final_exe.startswith('"') and final_exe.endswith('"')):
            exe_quoted = f'"{final_exe}"'
            
        if isinstance(final_args, list):
            quoted_args = []
            for arg in final_args:
                if " " in arg and not (arg.startswith('"') and arg.endswith('"')) and not (arg.startswith("'") and arg.endswith("'")):
                    quoted_args.append(f'"{arg}"')
                else:
                    quoted_args.append(arg)
            return " ".join([exe_quoted] + quoted_args)
        else:
            return exe_quoted

    def _launch_program(self, exe_path, title, pos_item):
        """智能解析并拉起普通程序（支持命令行与多段脚本），若需权限则自动提权 (带 5 秒防抖)"""
        import time
        now = time.time()
        if not hasattr(self, '_last_launch_timestamps'):
            self._last_launch_timestamps = {}
            
        launch_key = f"{title}_{exe_path.strip().lower()}"
        last_t = self._last_launch_timestamps.get(launch_key, 0.0)
        debounce_interval = 5.0  # 5 秒防抖冷却防护
        if now - last_t < debounce_interval:
            remaining = debounce_interval - (now - last_t)
            self.log(f"⚠️ 防抖拦截: [{title}] 刚触发启动中 (冷却剩余 {remaining:.1f}s)，防止重复打开")
            return True

        self._last_launch_timestamps[launch_key] = now
        exe_path = exe_path.strip()
        if (exe_path.startswith('"') and exe_path.endswith('"')) or (exe_path.startswith("'") and exe_path.endswith("'")):
            inner = exe_path[1:-1].strip()
            if " " in inner or any(marker in inner for marker in (";", "&&", "||", "|", '"', "'")):
                exe_path = inner

        is_valid, final_exe, final_args, is_shell, error_msg = self.resolve_and_validate_cmd(exe_path)
        if not is_valid:
            QMessageBox.warning(self, "启动失败", f"无效的启动配置：\n{error_msg}")
            return False
            
        import subprocess
        import sys
        import re
        old_cwd = os.getcwd()
        try:
            target_dir = ""
            # 1. 探查 final_exe (例如 D:\path\to\app.exe)
            if final_exe and os.path.isabs(final_exe) and os.path.exists(final_exe):
                target_dir = os.path.dirname(os.path.abspath(final_exe))
                
            # 2. 如果 final_exe 只是 python/cmd 等全局解释器命令，从 final_args 中精确定位被调起脚本/程序自身的物理目录
            if not target_dir and isinstance(final_args, list):
                for arg in final_args:
                    arg_clean = arg.strip('"').strip("'")
                    if not arg_clean or arg_clean.startswith("-"):
                        continue
                    if os.path.isabs(arg_clean) and os.path.exists(arg_clean):
                        target_dir = os.path.dirname(os.path.abspath(arg_clean))
                        break
                    abs_p = os.path.abspath(arg_clean)
                    if os.path.exists(abs_p):
                        target_dir = os.path.dirname(abs_p)
                        break
                    # 尝试项目根目录下的脚本文件 (例如 stock_standalone/popularity_resonance_gui.py)
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    parent_p = os.path.join(project_root, arg_clean)
                    if os.path.exists(parent_p):
                        target_dir = os.path.dirname(os.path.abspath(parent_p))
                        break

            # 3. 兜底退回项目根目录或当前 CWD
            if not target_dir or not os.path.exists(target_dir):
                target_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            if target_dir and os.path.exists(target_dir):
                os.chdir(target_dir)

            # 使用安全拼装后的 cmd_run，解决带有空格的路径在 Windows cmd.exe 下无法被正确解析运行 of Bug
            cmd_run = self._get_quoted_cmd(final_exe, final_args, exe_path)
            
            # 格式化命令（主要是 windows 上的分号连接和 cd 问题）
            if sys.platform == 'win32':
                # 将分号替换为 &&
                cmd_run = cmd_run.replace(";", " && ")
                # 自动将 cd D:\ 替换为 cd /d D:\ 以支持跨盘符切换
                cmd_run = re.sub(r'\bcd\s+([a-zA-Z]:)', r'cd /d \1', cmd_run)

            # 默认进入程序目录再执行程序
            if target_dir and os.path.exists(target_dir):
                cmd_clean_lower = cmd_run.lower().strip()
                if not (cmd_clean_lower.startswith('cd ') or cmd_clean_lower.startswith('cd/d')):
                    cmd_run = f'cd /d "{target_dir}" && {cmd_run}'

            self.log(f"正在拉起进程: {cmd_run} (工作目录: {target_dir})")

            # 隔离父进程环境变量，防止管理器自身的 INSTOCK_APP_ROOT 污染被启动的独立子程序
            sub_env = os.environ.copy()
            sub_env.pop("INSTOCK_APP_ROOT", None)
            sub_env.pop("NUITKA_ONEFILE_DIRECTORY", None)

            # 在 windows 上，使用 shell=True 启动任何脚本或命令最稳妥
            subprocess.Popen(cmd_run, shell=True, cwd=target_dir, env=sub_env)
            self._setup_post_launch_layout_timer(title, pos_item)
            return True
        except OSError as e:
            # 针对 WinError 740 (需要管理员权限) 进行自适应提权启动
            if getattr(e, 'winerror', None) == 740 or "740" in str(e):
                self.log(f"⚠️ 检测到启动需要权限 (WinError 740)，尝试以管理员身份提权启动...")
                return self._launch_as_admin(exe_path, title, pos_item)
            else:
                QMessageBox.warning(self, "启动失败", f"无法启动程序: {e}")
                self.log(f"启动程序失败: {e}")
                return False
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法启动程序: {e}")
            self.log(f"启动程序失败: {e}")
            return False
        finally:
            os.chdir(old_cwd)

    def _launch_as_admin(self, exe_path, title, pos_item):
        """通过 ctypes.windll.shell32.ShellExecuteW 提权以管理员身份启动程序，支持复杂命令行与参数"""
        exe_path = exe_path.strip()
        if (exe_path.startswith('"') and exe_path.endswith('"')) or (exe_path.startswith("'") and exe_path.endswith("'")):
            inner = exe_path[1:-1].strip()
            if " " in inner or any(marker in inner for marker in (";", "&&", "||", "|", '"', "'")):
                exe_path = inner

        try:
            import ctypes
            import os
            import sys
            import re
            
            is_valid, final_exe, final_args, is_shell, error_msg = self.resolve_and_validate_cmd(exe_path)
            if not is_valid:
                QMessageBox.warning(self, "启动失败", f"无效的启动配置：\n{error_msg}")
                return False
                
            old_cwd = os.getcwd()
            target_dir = ""
            if final_exe and os.path.isabs(final_exe):
                target_dir = os.path.dirname(final_exe)
            if not target_dir:
                if isinstance(final_args, list) and final_args:
                    for arg in final_args:
                        arg_clean = arg.strip('"').strip("'")
                        if os.path.isabs(arg_clean) and os.path.exists(os.path.dirname(arg_clean)):
                            target_dir = os.path.dirname(arg_clean)
                            break
            if not target_dir:
                target_dir = old_cwd
                
            # Windows 平台替换
            cmd_run = self._get_quoted_cmd(final_exe, final_args, exe_path)
            if sys.platform == 'win32':
                cmd_run = cmd_run.replace(";", " && ")
                cmd_run = re.sub(r'\bcd\s+([a-zA-Z]:)', r'cd /d \1', cmd_run)
                
            # 默认进入程序目录再执行程序
            if target_dir and os.path.exists(target_dir):
                cmd_clean_lower = cmd_run.lower().strip()
                if not (cmd_clean_lower.startswith('cd ') or cmd_clean_lower.startswith('cd/d')):
                    cmd_run = f'cd /d "{target_dir}" && {cmd_run}'
                
            # 执行提权启动
            if is_shell or ";" in exe_path or "&&" in exe_path:
                file_to_run = "cmd.exe"
                params = f'/c "{cmd_run}"'
            else:
                file_to_run = final_exe if final_exe else "cmd.exe"
                if isinstance(final_args, list):
                    # 将参数拼回字符串，并保证带空格的参数被包裹
                    quoted_args = []
                    for arg in final_args:
                        if " " in arg and not (arg.startswith('"') and arg.endswith('"')) and not (arg.startswith("'") and arg.endswith("'")):
                            quoted_args.append(f'"{arg}"')
                        else:
                            quoted_args.append(arg)
                    params = " ".join(quoted_args)
                else:
                    params = final_args
            
            self.log(f"正在以管理员身份启动: {file_to_run} {params} (工作目录: {target_dir})")
            
            # 使用 ShellExecuteW 提权启动
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,          # hwnd
                "runas",       # lpOperation
                file_to_run,   # lpFile
                params,        # lpParameters
                target_dir if target_dir else None, # lpDirectory
                1              # nShowCmd (SW_SHOWNORMAL)
            )
            
            if ret <= 32:
                raise OSError(f"ShellExecuteW 返回错误代码: {ret}")
                
            self._setup_post_launch_layout_timer(title, pos_item)
            return True
        except OSError as e:
            if getattr(e, 'winerror', None) == 1223 or "1223" in str(e):
                self.log(f"ℹ️ 用户取消了 UAC 权限请求，放弃以管理员身份启动。")
            else:
                QMessageBox.warning(self, "启动失败", f"无法以管理员身份启动程序: {e}")
                self.log(f"以管理员身份启动程序失败: {e}")
            return False
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法以管理员身份启动程序: {e}")
            self.log(f"以管理员身份启动程序失败: {e}")
            return False

    def on_table_cell_double_clicked(self, row, column):
        """双击单元格动作：
        - 窗口匹配标识(第0列)双击：自动置顶并激活窗口
        - 当前桌面实际位置(第2列)双击：触发单项快速回填配置坐标
        - 其他列(如第1列)双击：恢复双击编辑功能
        """
        if column == 0:
            title_item = self.table_widget.item(row, 0)
            if not title_item or not title_item.text().strip():
                return
                
            title = title_item.text().strip()
            self.log(f"正在尝试将窗口置顶并激活: '{title}'...")
            success = core.bring_window_to_top_by_title(title)
            if success:
                self.log(f"✅ 成功置顶并激活窗口: '{title}'")
            else:
                QMessageBox.warning(
                    self, 
                    "置顶失败", 
                    f"未能在桌面上匹配定位到运行中的窗口: '{title}'\n\n"
                    "请确认:\n1. 目标程序是否确实已正常运行且主界面已打开。\n"
                    "2. 窗口标题是否匹配该关键字（支持模糊匹配）。"
                )
                self.log(f"⚠️ 置顶激活失败，未匹配到窗口: '{title}'")
        elif column == 2:
            cur_item = self.table_widget.item(row, 2)
            pos_item = self.table_widget.item(row, 1)
            title_item = self.table_widget.item(row, 0)
            
            if cur_item and pos_item and title_item:
                cur_text = cur_item.text().strip()
                # 只有是合格的 X,Y,W,H 坐标格式才可更新
                if re.match(r"^-?\d+,-?\d+,\d+,\d+$", cur_text):
                    cfg_text = pos_item.text().strip()
                    if cur_text != cfg_text:
                        pos_item.setText(cur_text)
                        self.refresh_current_positions()
                        self.save_current_table_to_memory()
                        self.log(f"🎯 单项快速回填: 已将 '{title_item.text()}' 的配置坐标更新为桌面实际位置 [{cur_text}]")
        else:
            item = self.table_widget.item(row, column)
            if item and (item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable):
                self.table_widget.editItem(item)

    def save_all_config(self):
        """物理保存当前内存中的所有配置到 config.json 文件"""
        self.save_current_table_to_memory()
        
        new_hk = self.le_hotkey.text().strip()
        if new_hk:
            self.config_manager.config_data["global_hotkey"] = new_hk
            self.bind_hotkey(new_hk)
            
        if self.config_manager.save():
            QMessageBox.information(self, "成功", "配置文件已成功按分类持久化保存到磁盘！")
            self.log("配置文件已写入磁盘 window_layout_config.json。")
        else:
            QMessageBox.critical(self, "错误", "配置文件写入磁盘失败，请检查文件写权限！")

    def request_save_config_debounced(self):
        """触发防抖存盘，10秒内如果有多次调用仅在10秒后执行一次静默保存"""
        if not hasattr(self, '_save_timer'):
            self._save_timer = QtCore.QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._execute_silent_save)
            
        if not self._save_timer.isActive():
            self._save_timer.start(10000) # 10 秒防抖
            
    def _execute_silent_save(self):
        """执行静默防抖存盘"""
        self.save_current_table_to_memory()
        if self.config_manager.save():
            self.log("✅ 探测到配置自愈，已自动触发静默防抖保存机制落盘。")
        else:
            self.log("❌ 自动防抖保存配置文件失败。")

    def apply_window_layout_by_title(self, title: str, pos_str: str = None) -> tuple:
        """
        根据窗口标题（支持 .py / .exe 互相匹配）将该窗口移动到指定或当前方案中配置的位置。
        返回: (status: str, message: str) 其中 status 为 'moved', 'same', 'not_found', 'error'
        """
        import time
        if not pos_str or not pos_str.strip():
            current_res = self.get_current_selected_resolution()
            if current_res:
                mapping = self.config_manager.get_resolution_mapping(current_res)
                if title in mapping:
                    pos_str = mapping[title].split('|')[0].strip()
        
        if not pos_str:
            return "error", f"未找到窗口 '{title}' 的坐标配置"
            
        pos_str = pos_str.strip().split('|')[0].strip()
        try:
            cfg_parts = [int(p.strip()) for p in pos_str.split(',')]
        except Exception:
            cfg_parts = []
            
        if len(cfg_parts) != 4:
            return "error", f"坐标格式错误: {pos_str}"
            
        titles_to_try = [title]
        if title.endswith('.py') and not title.startswith('py'):
            titles_to_try.append(title.replace('.py', '.exe'))
        elif title.endswith('.exe'):
            titles_to_try.append(title.replace('.exe', '.py'))
            
        found_any = False
        moved_any = False
        same_any = False
        
        for t in titles_to_try:
            hwnds = core.find_windows_by_title_safe(t)
            if hwnds:
                found_any = True
                for hwnd, actual_title in hwnds:
                    left, top, w, h = core.get_window_rect(hwnd)
                    is_maximized = core.user32.IsZoomed(hwnd)
                    is_minimized = (left < -10000 and top < -10000) or core.user32.IsIconic(hwnd)
                    is_diff = (left != cfg_parts[0] or top != cfg_parts[1] or w != cfg_parts[2] or h != cfg_parts[3])
                    
                    if is_maximized or is_minimized or is_diff:
                        if is_maximized or is_minimized:
                            core.cancel_window_maximized_or_fullscreen(hwnd)
                        if core.set_window_hwnd_pos(hwnd, pos_str, title=actual_title):
                            self.log(f"✅ 成功对齐窗口: '{actual_title}' -> [{pos_str}]")
                            moved_any = True
                    else:
                        self.log(f"➖ 窗口 '{actual_title}' 位置已是一致 [{pos_str}]")
                        same_any = True
                break
                
        if not found_any:
            return "not_found", f"桌面未运行窗口: '{title}'"
        elif moved_any:
            self.refresh_current_positions()
            return "moved", f"已成功将 '{title}' 移动到配置坐标 [{pos_str}]"
        elif same_any:
            return "same", f"窗口 '{title}' 当前位置已与配置一致"
        return "same", "位置无变动"

    def apply_current_layout(self, show_tray_message: bool = False):
        """一键应用当前方案的所有规则到桌面运行中的窗口 (仅对位置有变动的窗口执行操作)"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            return
            
        self.save_current_table_to_memory()
        self.log(f"开始应用布局 '{current_res}' 到桌面窗口...")
        
        mapping = self.config_manager.get_resolution_mapping(current_res)
        if not mapping:
            self.log("配置为空，没有需要移动的窗口。")
            if show_tray_message and hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    "桌面窗口布局管理器",
                    f"方案 [{current_res}] 无任何窗口规则配置",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Warning,
                    2500
                )
            return
            
        moved_count = 0
        skip_count = 0
        missing_count = 0
        
        for title, raw_pos_str in mapping.items():
            parts = raw_pos_str.split('|')
            pos_str = parts[0]
            
            try:
                cfg_parts = [int(p.strip()) for p in pos_str.split(',')]
            except Exception:
                cfg_parts = []
                
            if len(cfg_parts) != 4:
                self.log(f"⚠️ 规则 '{title}' 的坐标格式错误: {pos_str}")
                continue
                
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            found_any = False
            moved_any = False
            skip_any = False
            
            for t in titles_to_try:
                hwnds = core.find_windows_by_title_safe(t)
                if hwnds:
                    found_any = True
                    for hwnd, actual_title in hwnds:
                        left, top, w, h = core.get_window_rect(hwnd)
                        is_maximized = core.user32.IsZoomed(hwnd)
                        is_minimized = (left < -10000 and top < -10000) or core.user32.IsIconic(hwnd)
                        is_diff = (left != cfg_parts[0] or top != cfg_parts[1] or w != cfg_parts[2] or h != cfg_parts[3])
                        
                        if is_maximized or is_minimized or is_diff:
                            if is_maximized or is_minimized:
                                core.cancel_window_maximized_or_fullscreen(hwnd)
                            if core.set_window_hwnd_pos(hwnd, pos_str, title=actual_title):
                                self.log(f"✅ 成功设置窗口: '{actual_title}' -> [{pos_str}]")
                                moved_any = True
                        else:
                            self.log(f"➖ 窗口 '{actual_title}' 位置一致 [{pos_str}]，跳过应用")
                            skip_any = True
                    break
                    
            if not found_any:
                missing_count += 1
            else:
                if moved_any:
                    moved_count += 1
                elif skip_any:
                    skip_count += 1
                    
        summary_msg = f"🏁 布局应用完毕！移动/调整 {moved_count} 个，保持/跳过 {skip_count} 个，忽略 {missing_count} 个未启动。"
        self.log(summary_msg)
        self.refresh_current_positions()
        
        if show_tray_message and hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "桌面窗口布局管理器",
                f"方案 [{current_res}] 布局应用完成！\n移动: {moved_count} | 保持: {skip_count} | 未运行: {missing_count}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                3000
            )


def main(hide_window: bool = False):
    # 动态根据环境变量调整日志级别
    app_debug = os.environ.get("APP_DEBUG")
    if app_debug:
        import logging
        level_val = getattr(logging, app_debug.upper(), None)
        if level_val is not None:
            logger.setLevel(level_val)

    # 💥 在实例化 QApplication 前，强制声明高 DPI 意识，彻底避免高 DPI/多屏拓扑切换下坐标放大级联Bug
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#121214"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#e0e0e0"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#16161a"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#1e1e24"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#1e1e24"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#e0e0e0"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e0e0e0"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#2e2e38"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#ffffff"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ff0000"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor("#0ea5e9"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#0ea5e9"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(dark_palette)

    window = WindowPosManagerUI()
    
    # 判读是否隐藏启动（开机自启、-hide、-min、-hidetray）
    is_hide = hide_window or any(arg.lower() in ("-hide", "--hide", "-min", "--min", "-hidetray") for arg in sys.argv[1:])
    if is_hide:
        window.hide()
        window.log("🙈 程序已以 [-hide 托盘后台不弹窗] 模式启动，常驻系统托盘，静默待命。")
    else:
        window._force_show_and_top()
        
    sys.exit(app.exec())

if __name__ == "__main__":
    main()