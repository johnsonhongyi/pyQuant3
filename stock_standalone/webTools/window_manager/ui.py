# -*- coding: utf-8 -*-
"""
窗口配置管理器 UI 界面 (PyQt6)
支持可视化管理屏幕布局、查看/编辑窗口坐标、捕获桌面窗口、一键应用及分类持久化保存。
"""

import sys
import os
import re
import keyboard
from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QInputDialog, QDialog, QListWidget,
    QListWidgetItem, QTextEdit, QGroupBox, QLineEdit, QMenu, QSystemTrayIcon
)
from PyQt6.QtGui import QAction, QIcon

# 导入核心模块
try:
    from . import core
except ImportError:
    import core


class HotkeyLineEdit(QLineEdit):
    """自动捕获按键组合的输入框"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置为只读模式以防止传统输入字符，改由事件拦截处理
        self.setReadOnly(True)
        self.setPlaceholderText("点击后直接按下快捷键...")

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
        
        info_label = QLabel("勾选或多选你想要捕获并记录当前位置的桌面窗口：")
        layout.addWidget(info_label)

        # 窗口列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_refresh = QPushButton("刷新列表")
        self.btn_refresh.clicked.connect(self.refresh_windows)
        
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_refresh)
        
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

    def on_item_double_clicked(self, item):
        item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if item_data:
            title, pos_str, exe_path = item_data
            core.bring_window_to_top_by_title(title)


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
        if self.txt_path.text().strip():
            dir_name = os.path.dirname(self.txt_path.text().strip())
            if os.path.exists(dir_name):
                initial_dir = dir_name
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行程序/脚本", 
            initial_dir, 
            "可执行文件 (*.exe *.bat *.cmd *.py);;所有文件 (*.*)"
        )
        if file_path:
            self.txt_path.setText(os.path.normpath(file_path))

    def accept_path(self):
        self.final_path = self.txt_path.text().strip()
        self.accept()


class WindowPosManagerUI(QMainWindow):
    """主窗口：窗口坐标及分布管理器"""
    toggle_ui_signal = QtCore.pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("股票交易终端 - 窗口坐标分类管理器")
        self.resize(980, 700)
        self._hotkey_hook = None
        self.config_manager = core.ConfigManager()
        self.current_bound_hotkey = self.config_manager.config_data.get("global_hotkey", "ctrl+alt+w")
        self.init_ui()
        self.load_screen_info()
        self.refresh_resolutions_combo()
        self.setup_tray_icon()
        self.bind_hotkey(self.current_bound_hotkey)
        self.toggle_ui_signal.connect(self.toggle_visibility)
        
        # 允许驻留后台
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon))
        
        tray_menu = QMenu(self)
        show_action = tray_menu.addAction("显示主界面")
        show_action.triggered.connect(self.showNormal)
        quit_action = tray_menu.addAction("完全退出")
        quit_action.triggered.connect(self.force_quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)
        
    def force_quit(self):
        try:
            if getattr(self, '_hotkey_hook', None):
                keyboard.remove_hotkey(self._hotkey_hook)
        except:
            pass
        QApplication.instance().quit()
        
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visibility()
            
    def closeEvent(self, event):
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.hide()
            self.log("界面已隐藏至状态栏。")
            event.ignore()
        else:
            try:
                if getattr(self, '_hotkey_hook', None):
                    keyboard.remove_hotkey(self._hotkey_hook)
            except:
                pass
            event.accept()
            
    def toggle_visibility(self):
        if self.isVisible():
            if self.isActiveWindow():
                self.hide()
            else:
                self._force_show_and_top()
        else:
            self._force_show_and_top()
            
    def _force_show_and_top(self):
        # 取消永久置顶属性，改为正常显示状态
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, False)
        self.showNormal()
        self.activateWindow()
        self.raise_()
        
        # 使用底层 API 强制夺取 Windows 前台焦点
        try:
            import ctypes
            hwnd = int(self.winId())
            # 模拟轻按 Alt 键以绕过 Windows 系统的焦点抢夺拦截限制
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0) # Alt Down
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0) # Alt Up
        except Exception:
            pass
            
    def bind_hotkey(self, hotkey_str):
        if not hotkey_str:
            return False
        try:
            if getattr(self, '_hotkey_hook', None):
                keyboard.remove_hotkey(self._hotkey_hook)
                self._hotkey_hook = None
            self._hotkey_hook = keyboard.add_hotkey(hotkey_str, self.toggle_ui_signal.emit)
            self.current_bound_hotkey = hotkey_str
            self.log(f"已绑定全局热键: {hotkey_str}")
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
                min-width: 280px;
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
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

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
        gb_display_layout = QVBoxLayout(self.gb_display_info)
        gb_display_layout.setContentsMargins(10, 15, 10, 10)
        self.lbl_display_details = QLabel("无显示器数据")
        self.lbl_display_details.setWordWrap(True)
        self.lbl_display_details.setStyleSheet("color: #d1d5db; line-height: 1.4;")
        gb_display_layout.addWidget(self.lbl_display_details)
        
        # 增加显示器物理布局保存/恢复按钮栏
        screen_btn_bar = QHBoxLayout()
        self.btn_save_screen_layout = QPushButton("💾 保存显示器物理拓扑")
        self.btn_save_screen_layout.setStyleSheet("background-color: #0d9488; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_save_screen_layout.clicked.connect(self.save_physical_screen_layout)
        
        self.btn_restore_screen_layout = QPushButton("🔄 恢复显示器物理拓扑")
        self.btn_restore_screen_layout.setStyleSheet("background-color: #ea580c; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_restore_screen_layout.clicked.connect(self.restore_physical_screen_layout)
        
        screen_btn_bar.addWidget(self.btn_save_screen_layout)
        screen_btn_bar.addWidget(self.btn_restore_screen_layout)
        screen_btn_bar.addStretch()
        gb_display_layout.addLayout(screen_btn_bar)

        main_layout.addWidget(self.gb_display_info)

        # 配置管理控制栏
        config_bar = QHBoxLayout()
        config_bar.addWidget(QLabel("分类选择方案:"))
        
        self.cb_resolutions = QComboBox()
        self.cb_resolutions.currentIndexChanged.connect(self.on_resolution_changed)
        config_bar.addWidget(self.cb_resolutions)

        self.btn_new_res = QPushButton("➕ 新建方案")
        self.btn_new_res.clicked.connect(self.new_resolution)
        config_bar.addWidget(self.btn_new_res)
        
        self.btn_copy_res = QPushButton("📋 复制方案")
        self.btn_copy_res.clicked.connect(self.copy_resolution)
        config_bar.addWidget(self.btn_copy_res)

        self.btn_delete_res = QPushButton("🗑️ 删除方案")
        self.btn_delete_res.setObjectName("btnDeleteRes")
        self.btn_delete_res.clicked.connect(self.delete_resolution)
        config_bar.addWidget(self.btn_delete_res)
        
        config_bar.addStretch()
        
        self.btn_auto_detect = QPushButton("🔍 自动匹配当前屏幕")
        self.btn_auto_detect.clicked.connect(self.auto_detect_and_set)
        config_bar.addWidget(self.btn_auto_detect)
        
        main_layout.addLayout(config_bar)

        # 主配置列表编辑区 (Table)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels([
            "窗口匹配标识/关键字 (模糊匹配)", 
            "配置坐标 (X,Y,Width,Height)", 
            "当前桌面实际位置 (不一致标红/点击可单项回填)"
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
        self.btn_add_row = QPushButton("➕ 添加映射行")
        self.btn_add_row.clicked.connect(self.add_table_row)
        table_op_layout.addWidget(self.btn_add_row)
        
        self.btn_delete_row = QPushButton("➖ 删除选中行")
        self.btn_delete_row.clicked.connect(self.delete_table_row)
        table_op_layout.addWidget(self.btn_delete_row)
        
        table_op_layout.addSpacing(20)
        
        self.btn_capture_wins = QPushButton("📸 捕获桌面窗口")
        self.btn_capture_wins.setStyleSheet("background-color: #4f46e5; border: none; font-weight: bold;")
        self.btn_capture_wins.clicked.connect(self.capture_desktop_windows)
        table_op_layout.addWidget(self.btn_capture_wins)
        
        table_op_layout.addSpacing(10)
        
        self.btn_update_existing = QPushButton("🔄 更新已有窗口坐标")
        self.btn_update_existing.setStyleSheet("background-color: #059669; border: none; font-weight: bold;")
        self.btn_update_existing.clicked.connect(self.update_existing_windows_pos)
        table_op_layout.addWidget(self.btn_update_existing)
        
        table_op_layout.addStretch()
        mid_layout.addLayout(table_op_layout, stretch=1)
        main_layout.addLayout(mid_layout)

        # 日志控制台
        log_group = QGroupBox("执行状态日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(110)
        log_layout.addWidget(self.log_output)
        main_layout.addWidget(log_group)

        # 底部应用栏
        bottom_bar = QHBoxLayout()
        
        # --- 全局热键配置 ---
        self.lbl_hotkey = QLabel("全局热键:")
        bottom_bar.addWidget(self.lbl_hotkey)
        
        self.le_hotkey = HotkeyLineEdit()
        self.le_hotkey.setFixedWidth(150)
        self.le_hotkey.setText(getattr(self, 'current_bound_hotkey', ''))
        bottom_bar.addWidget(self.le_hotkey)
        
        self.btn_bind_hotkey = QPushButton("绑定")
        self.btn_bind_hotkey.clicked.connect(self.on_bind_hotkey_clicked)
        bottom_bar.addWidget(self.btn_bind_hotkey)
        
        bottom_bar.addStretch()
        
        self.btn_save_config = QPushButton("💾 保存配置")
        self.btn_save_config.setObjectName("btnSave")
        self.btn_save_config.clicked.connect(self.save_all_config)
        bottom_bar.addWidget(self.btn_save_config)
        
        self.btn_apply_layout = QPushButton("🚀 立即应用布局")
        self.btn_apply_layout.setObjectName("btnApply")
        self.btn_apply_layout.clicked.connect(self.apply_current_layout)
        bottom_bar.addWidget(self.btn_apply_layout)
        
        self.btn_full_exit = QPushButton("❌ 完全退出")
        self.btn_full_exit.setObjectName("btnDeleteRes") # 复用红色的删除按钮样式
        self.btn_full_exit.clicked.connect(self.force_quit)
        bottom_bar.addWidget(self.btn_full_exit)
        
        main_layout.addLayout(bottom_bar)

        self.log("界面加载完毕。")

    def log(self, text: str):
        """输出一条日志"""
        self.log_output.append(f"[{QtCore.QTime.currentTime().toString('hh:mm:ss')}] {text}")

    def save_physical_screen_layout(self):
        """保存当前多显示器的物理排布与相对坐标到磁盘"""
        success, msg = core.save_display_configuration()
        if success:
            QMessageBox.information(self, "保存成功", f"当前显示器拓扑结构已保存！\n配置文件: {msg}")
            self.log(f"💾 多显示器物理排布保存成功: {msg}")
        else:
            QMessageBox.critical(self, "保存失败", f"无法保存显示器配置: {msg}")
            self.log(f"❌ 保存显示器配置失败: {msg}")

    def restore_physical_screen_layout(self):
        """一键从磁盘恢复当前屏幕组合下保存的物理排布与拓扑"""
        reply = QMessageBox.question(
            self, 
            "确认恢复", 
            "是否确定恢复已保存的显示器物理排布相对位置？\n这会瞬间刷新您的系统显示设置并重新排布桌面上所有屏幕。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.log("正在尝试还原多显示器物理拓扑...")
            success, msg = core.restore_display_configuration()
            if success:
                QMessageBox.information(self, "恢复完成", msg)
                self.log(f"🔄 {msg}")
                self.load_screen_info()
            else:
                QMessageBox.warning(self, "恢复提示", msg)
                self.log(f"⚠️ {msg}")

    def load_screen_info(self):
        """探测当前连接的显示器参数并在 UI 呈现"""
        info = core.get_screen_resolution_summary()
        self.lbl_screen_status.setText(f"检测到显示器: {info['display_num']} 个  总宽度: {info['total_width']}px")
        
        details = []
        for m in info["monitors"]:
            primary_tag = " [主屏幕]" if m["is_primary"] else ""
            details.append(
                f"设备 {m['index']}: 名称: {m['name']} | 分辨率: {m['width']}x{m['height']} | "
                f"起始坐标: ({m['x']}, {m['y']}){primary_tag}"
            )
        self.lbl_display_details.setText("\n".join(details))
        
        # 推荐配置名
        rec_name = core.detect_display_config_name()
        self.log(f"系统智能推荐的分辨率配置为: {rec_name}")

    def refresh_resolutions_combo(self, select_name=None):
        """刷新下拉配置选择框，带上中文分类标识"""
        self.cb_resolutions.blockSignals(True)
        self.cb_resolutions.clear()
        
        categories = {
            "single_display": "🖥️ 单屏",
            "multi_display": "🖥️🖥️ 多屏",
            "custom_special": "⚙️ 特殊"
        }
        
        found_index = -1
        index_counter = 0
        
        for cat_name in self.config_manager.get_categories():
            cat_cn = categories.get(cat_name, cat_name)
            for res_name in self.config_manager.get_resolutions_by_category(cat_name):
                display_text = f"[{cat_cn}] {res_name}"
                # 绑定二元组 (category, res_name) 作为 UserData
                self.cb_resolutions.addItem(display_text, (cat_name, res_name))
                if select_name and res_name == select_name:
                    found_index = index_counter
                index_counter += 1
                
        if found_index >= 0:
            self.cb_resolutions.setCurrentIndex(found_index)
        else:
            # 自动选择最匹配的
            rec_name = core.detect_display_config_name()
            matched_index = -1
            for i in range(self.cb_resolutions.count()):
                data = self.cb_resolutions.itemData(i)
                if data and data[1] == rec_name:
                    matched_index = i
                    break
            if matched_index >= 0:
                self.cb_resolutions.setCurrentIndex(matched_index)
            elif self.cb_resolutions.count() > 0:
                self.cb_resolutions.setCurrentIndex(0)
                
        self.cb_resolutions.blockSignals(False)
        self.on_resolution_changed()

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
        rec_name = core.detect_display_config_name()
        
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
                f"当前屏幕探测到对应的配置标识为 '{rec_name}'，但当前配置库中没有该方案。\n是否使用此名字新建一个空白配置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 默认基于物理显示器数量放置于 single_display 或 multi_display
                info = core.get_screen_resolution_summary()
                cat = "single_display" if info["display_num"] <= 1 else "multi_display"
                
                self.config_manager.set_resolution_mapping(rec_name, {}, cat)
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
                
                # 若缺失路径则顺便自愈
                if pos_item and not old_exe_path and found_exe_path:
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
                # 若原来没有 exe_path，但现在程序运行了，自动自愈补齐并保存到单元格
                if not pos_item.data(QtCore.Qt.ItemDataRole.UserRole) and found_exe_path:
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
                
            if core.set_window_hwnd_pos(found_hwnd, new_pos_str):
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
        if exe_path and os.path.exists(exe_path):
            start_action = menu.addAction(f"🚀 启动程序 ({os.path.basename(exe_path)})")
            start_admin_action = menu.addAction(f"🛡️ 以管理员身份启动 ({os.path.basename(exe_path)})")
            menu.addSeparator()

        activate_action = menu.addAction("📌 窗口置顶并激活")
        center_action = menu.addAction("📺 居中显示于程序所在屏幕")
        edit_action = menu.addAction("✏️ 编辑该单元格")
        edit_path_action = menu.addAction("⚙️ 编辑程序启动路径")
        action = menu.exec(self.table_widget.mapToGlobal(pos))
        
        if start_action and action == start_action:
            self.log(f"正在启动程序: {exe_path}")
            try:
                import subprocess
                subprocess.Popen(exe_path, cwd=os.path.dirname(exe_path))
                self._setup_post_launch_layout_timer(title, pos_item)
            except OSError as e:
                # 针对 WinError 740 (需要管理员权限) 进行自适应提权启动
                if getattr(e, 'winerror', None) == 740 or "740" in str(e):
                    self.log(f"⚠️ 检测到启动需要权限 (WinError 740)，尝试以管理员身份提权启动...")
                    self._launch_as_admin(exe_path, title, pos_item)
                else:
                    QMessageBox.warning(self, "启动失败", f"无法启动程序: {e}")
                    self.log(f"启动程序失败: {e}")
            except Exception as e:
                QMessageBox.warning(self, "启动失败", f"无法启动程序: {e}")
                self.log(f"启动程序失败: {e}")
        elif start_admin_action and action == start_admin_action:
            self.log(f"正在以管理员身份启动程序: {exe_path}")
            self._launch_as_admin(exe_path, title, pos_item)
        elif action == activate_action:
            self.on_table_cell_double_clicked(row, 0)
        elif action == center_action:
            self.center_window_on_current_screen(row)
        elif action == edit_action:
            self.table_widget.editItem(item)
        elif action == edit_path_action:
            dialog = EditPathDialog(title, exe_path, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_path = dialog.final_path
                if pos_item:
                    pos_item.setData(QtCore.Qt.ItemDataRole.UserRole, new_path)
                    self.save_current_table_to_memory()
                    self.request_save_config_debounced()
                    self.log(f"🎯 已更新程序 '{title}' 的启动路径 ➡ {new_path}")
                    self.on_resolution_changed()

    def _setup_post_launch_layout_timer(self, title, pos_item):
        """程序启动后启动定时器，高频轮询检测窗口创建并应用坐标"""
        pos_str = pos_item.text().strip()
        def wait_and_apply(attempts=0):
            if attempts > 30: # 尝试30次，共15秒
                self.log(f"⚠️ 启动程序 '{title}' 等待窗口创建超时，放弃自动应用布局。")
                return
                
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            moved = False
            for t in titles_to_try:
                if core.set_window_pos_by_title(t, pos_str):
                    self.log(f"✅ 自动布局: 成功捕捉刚启动的 '{t}' 并移动到配置坐标 [{pos_str}]")
                    self.refresh_current_positions()
                    moved = True
                    break
                    
            if not moved:
                QtCore.QTimer.singleShot(500, lambda: wait_and_apply(attempts + 1))
                
        # 给予进程初始创建时间 1.5 秒后开始高频轮询探测
        QtCore.QTimer.singleShot(1500, wait_and_apply)

    def _launch_as_admin(self, exe_path, title, pos_item):
        """通过 os.startfile(..., 'runas') 提权以管理员身份启动程序"""
        try:
            import os
            os.startfile(exe_path, 'runas')
            self._setup_post_launch_layout_timer(title, pos_item)
        except OSError as e:
            # WinError 1223 表示用户取消了 UAC 提权
            if getattr(e, 'winerror', None) == 1223 or "1223" in str(e):
                self.log(f"ℹ️ 用户取消了 UAC 权限请求，放弃以管理员身份启动。")
            else:
                QMessageBox.warning(self, "启动失败", f"无法以管理员身份启动程序: {e}")
                self.log(f"以管理员身份启动程序失败: {e}")
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法以管理员身份启动程序: {e}")
            self.log(f"以管理员身份启动程序失败: {e}")

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

    def apply_current_layout(self):
        """一键应用当前方案的所有规则到桌面运行中的窗口"""
        current_res = self.get_current_selected_resolution()
        if not current_res:
            return
            
        self.save_current_table_to_memory()
        self.log(f"开始应用布局 '{current_res}' 到桌面窗口...")
        
        mapping = self.config_manager.get_resolution_mapping(current_res)
        if not mapping:
            self.log("配置为空，没有需要移动的窗口。")
            return
            
        success_count = 0
        missing_count = 0
        
        for title, raw_pos_str in mapping.items():
            parts = raw_pos_str.split('|')
            pos_str = parts[0]
            
            titles_to_try = [title]
            if title.endswith('.py') and not title.startswith('py'):
                titles_to_try.append(title.replace('.py', '.exe'))
            elif title.endswith('.exe'):
                titles_to_try.append(title.replace('.exe', '.py'))
                
            moved = False
            for t in titles_to_try:
                if core.set_window_pos_by_title(t, pos_str):
                    moved = True
                    self.log(f"✅ 成功定位并设置窗口: '{t}' -> [{pos_str}]")
                    success_count += 1
                    break
            if not moved:
                missing_count += 1
                
        self.log(f"🏁 布局应用完毕！成功移动 {success_count} 个窗口，忽略 {missing_count} 个未启动窗口。")
        self.refresh_current_positions()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#121214"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#e0e0e0"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#16161a"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#1e1e24"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#ffffff"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#ffffff"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e0e0e0"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#2e2e38"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#ffffff"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ff0000"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor("#0ea5e9"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#0ea5e9"))
    dark_palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(dark_palette)

    window = WindowPosManagerUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
