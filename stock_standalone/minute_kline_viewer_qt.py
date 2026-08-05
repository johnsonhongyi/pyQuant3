import sys
import os
import re
import pandas as pd
import numpy as np
import json
import gzip
from datetime import datetime

from typing import Optional, Any, Callable, Dict
from tk_gui_modules.gui_config import (MINUTE_KLINE_VIEWER_HISTORY)
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, 
                                 QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                 QLabel, QFileDialog, QSplitter, QComboBox, QPlainTextEdit,
                                 QInputDialog, QMessageBox, QMenu, QFormLayout, QLayout)
    from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint, QSize, QRect
    from PyQt6.QtGui import QIcon, QFont
except ImportError:
    try:
        from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, 
                                     QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                     QLabel, QFileDialog, QSplitter, QComboBox, QPlainTextEdit,
                                     QInputDialog, QMessageBox, QMenu, QFormLayout, QLayout)
        from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint, QSize, QRect
        from PySide6.QtGui import QIcon, QFont
    except ImportError:
        try:
            from PyQt5.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, 
                                         QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                         QLabel, QFileDialog, QSplitter, QComboBox, QPlainTextEdit,
                                         QInputDialog, QMessageBox, QMenu, QFormLayout, QLayout)
            from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint, QSize, QRect
            from PyQt5.QtGui import QIcon, QFont
        except ImportError:
            try:
                from PySide2.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, 
                                             QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                             QLabel, QFileDialog, QSplitter, QComboBox, QPlainTextEdit,
                                             QInputDialog, QMessageBox, QMenu, QFormLayout, QLayout)
                from PySide2.QtCore import Qt, QAbstractTableModel, QModelIndex, QPoint, QSize, QRect
                from PySide2.QtGui import QIcon, QFont
            except ImportError:
                print("Please install PyQt6, PySide6, PyQt5 or PySide2 to run this tool.")
                sys.exit(1)

from tk_gui_modules.window_mixin import WindowMixin

# try to import commonTips for path resolution
try:
    from JohnsonUtil import commonTips as cct
except ImportError:
    cct = None

# Integrated Query Engine
try:
    from query_engine_util import query_engine
except ImportError:
    query_engine = None

# Qt Constant Shims for PyQt6/PySide6/PyQt5 compatibility
# PyQt6 uses nested namespaces (e.g., Qt.ItemDataRole.DisplayRole)
# PyQt5 and others use flat namespaces (e.g., Qt.DisplayRole)
if hasattr(Qt, "ItemDataRole"):
    _DisplayRole = Qt.ItemDataRole.DisplayRole
    _Horizontal = Qt.Orientation.Horizontal
    _Vertical = Qt.Orientation.Vertical
else:
    _DisplayRole = getattr(Qt, "DisplayRole", 0)
    _Horizontal = getattr(Qt, "Horizontal", 0x1)
    _Vertical = getattr(Qt, "Vertical", 0x2)

# Qt6 Key namespace shim
if hasattr(Qt, "Key"):
    _Key_Escape = Qt.Key.Key_Escape
else:
    _Key_Escape = getattr(Qt, "Key_Escape", 0x01000000)

# Qt6 moved SelectionBehavior too
try:
    from PyQt6.QtWidgets import QAbstractItemView
    _SelectRows = QAbstractItemView.SelectionBehavior.SelectRows
except (ImportError, AttributeError):
    try:
        from PySide6.QtWidgets import QAbstractItemView
        _SelectRows = QAbstractItemView.SelectionBehavior.SelectRows
    except (ImportError, AttributeError):
        _SelectRows = QTableView.SelectRows if hasattr(QTableView, "SelectRows") else 1

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspacing=5, vspacing=5):
        super().__init__(parent)
        self._item_list = []
        self._h_spacing = hspacing
        self._v_spacing = vspacing
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
        try:
            return Qt.Orientation(0)
        except Exception:
            return getattr(Qt, "Horizontal", 0x1) & 0

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0

        for item in self._item_list:
            wid = item.widget()
            if not wid:
                continue
            
            space_x = self._h_spacing
            space_y = self._v_spacing

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() - margins.right() and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()


class DataFrameModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame()):
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()):
        return self._data.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return self._data.shape[1]

    def data(self, index, role=_DisplayRole):
        if index.isValid():
            try:
                col_name = self._data.columns[index.column()]
                val = self._data.iloc[index.row(), index.column()]
                
                if role == _DisplayRole or role == Qt.ItemDataRole.EditRole:
                    # Time Formatting for display only
                    if role == _DisplayRole and col_name.lower() in ('time', 'timestamp', 'ticktime', 'datetime', 'date', '时间'):
                        try:
                            ts = float(val)
                            if ts > 1000000000:
                                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            pass

                    if isinstance(val, (float, np.float64)):
                        if role == Qt.ItemDataRole.EditRole:
                            return val # Keep original float for editing
                        return f"{val:.2f}"

                    return str(val)
                
                # Add background color for editable columns if needed
                # elif role == Qt.ItemDataRole.BackgroundRole:
                #     return QBrush(Qt.GlobalColor.white)
                    
            except Exception:
                if role == _DisplayRole:
                    return str(self._data.iloc[index.row(), index.column()])
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.isValid() and role == Qt.ItemDataRole.EditRole:
            try:
                col_name = self._data.columns[index.column()]
                # Attempt to cast to correct type
                orig_val = self._data.iloc[index.row(), index.column()]
                if isinstance(orig_val, (int, np.integer)):
                    value = int(value)
                elif isinstance(orig_val, (float, np.float64)):
                    value = float(value)
                
                self._data.iloc[index.row(), index.column()] = value
                self.dataChanged.emit(index, index, [role])
                return True
            except (ValueError, TypeError) as e:
                print(f"SetData Error (Type Mismatch): {e}")
                return False
        return False

    def headerData(self, col, orientation, role):
        if orientation == _Horizontal and role == _DisplayRole:
            if 0 <= col < self._data.shape[1]:
                return self._data.columns[col]
        return None

    def sort(self, column, order):
        """Sort table by given column number."""
        try:
            if 0 <= column < self._data.shape[1]:
                col_name = self._data.columns[column]
                self.layoutAboutToBeChanged.emit()
                self._data = self._data.sort_values(
                    by=col_name, 
                    ascending=(order == Qt.SortOrder.AscendingOrder)
                )
                self.layoutChanged.emit()
        except Exception as e:
            print(f"Sort Error: {e}")

# Import Signal/pyqtSignal and QThread dynamically
try:
    from PyQt6.QtCore import QThread, pyqtSignal as Signal
except ImportError:
    try:
        from PySide6.QtCore import QThread, Signal
    except ImportError:
        try:
            from PyQt5.QtCore import QThread, pyqtSignal as Signal
        except ImportError:
            try:
                from PySide2.QtCore import QThread, Signal
            except ImportError:
                Signal = None
                QThread = None

class BacktestWorker(QThread):
    finished = Signal(str, str, str)  # code, name, report

    def __init__(self, code, name):
        super().__init__()
        self.code = code
        self.name = name

    def run(self):
        try:
            from scratch.test_reentry_backtest import run_backtest_and_get_report
            report = run_backtest_and_get_report(self.code, self.name, only_report=True)
            self.finished.emit(self.code, self.name, report)
        except Exception as e:
            self.finished.emit(self.code, self.name, f"运行回测出错: {e}")

class BacktestReportQtDialog(QDialog):
    def __init__(self, parent, code, name, report):
        super().__init__(parent)
        self.setWindowTitle(f"Re-entry 历史回测报告 - {name} ({code})")
        self.resize(750, 550)
        self.setStyleSheet("""
            QDialog {
                background-color: #0c101b;
                color: #eeeeee;
            }
            QPlainTextEdit {
                background-color: #05080e;
                color: #55ffff;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11pt;
                border: 1px solid #1a2233;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #1b3a4b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2b5a75;
            }
            QLabel {
                color: #ffcc00;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Title Label
        title_label = QLabel(f"🧬 【{name} ({code})】 Re-entry 历史模拟交易回测结论：")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Text Area
        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(report)
        layout.addWidget(self.text_area)
        
        # Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

class KlineBackupViewer(QMainWindow, WindowMixin):
    def __init__(self, on_code_callback: Optional[Callable[[str], Any]] = None, service_proxy: Any = None, 
                 last6vol_map: Optional[Dict[str, float]] = None, main_app: Any = None):
        super().__init__()
        self.on_code_callback = on_code_callback
        self.service_proxy = service_proxy # RealtimeDataService proxy
        self.last6vol_map = last6vol_map if last6vol_map is not None else {}
        self.main_app = main_app # Reference to Tkinter app
        self.internal_dfs: Dict[str, pd.DataFrame] = {}
        self.sender = None # For standalone linkage
        # 尝试初始化 StockSender (独立运行时联动外部通达信/行情软件)
        self._select_code = None
        if not self.on_code_callback:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.sender = StockSender(callback=None)
                print("[INFO] StockSender initialized for standalone linkage.")
            except Exception as e:
                print(f"[DEBUG] StockSender init skip/failed: {e}")

        self.current_file: Optional[str] = None
        self.current_key: Optional[str] = None
        self.is_memory_mode: bool = False
        self.setWindowTitle("Minute Kline Cache Viewer (Realtime Service)")
        self.df_file = pd.DataFrame()
        self.df_mem = pd.DataFrame()
        self._is_querying = False 
        
        # 历史记录数据 - 存储在 datacsv 目录下
        # self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datacsv", "minute_kline_viewer_history.json")
        self.history_file = MINUTE_KLINE_VIEWER_HISTORY
        self.file_history = []
        self.query_history = []
        self.load_history()
        
        self.setup_ui()
        self.load_window_position_qt(self, "minute_kline_viewer", default_width=1200, default_height=800)
        self.auto_load()

    def _wait_voice_safe(self) -> bool:
        """
        🛡️ 等待语音播放完成，避免 Qt 操作与 pyttsx3 COM 冲突导致 GIL 崩溃
        返回: True 如果成功等待，False 如果超时或无法检查
        """
        if not self.main_app:
            return True
        
        try:
            # 检查是否有 live_strategy 和语音引擎
            if not hasattr(self.main_app, 'live_strategy') or not self.main_app.live_strategy:
                return True
            
            voice = getattr(self.main_app.live_strategy, '_voice', None)
            if not voice:
                return True
            
            # 等待语音完成
            if hasattr(voice, 'wait_for_safe'):
                return voice.wait_for_safe(timeout=3.0)
            elif hasattr(voice, 'is_speaking'):
                import time
                start = time.time()
                while voice.is_speaking:
                    if time.time() - start > 3.0:
                        print("[WARN] _wait_voice_safe: timeout waiting for voice")
                        return False
                    time.sleep(0.1)
                return True
            
            return True
        except Exception as e:
            print(f"[WARN] _wait_voice_safe error: {e}")
            return True

    def closeEvent(self, event):
        """窗口关闭事件：保存位置与历史记录"""
        try:
            self.save_window_position_qt_visual(self, "minute_kline_viewer")
            self.save_history()
            
            # 如果是从主程序启动，清理引用
            if hasattr(self, 'main_app') and self.main_app:
                if hasattr(self.main_app, '_kline_viewer_qt'):
                    self.main_app._kline_viewer_qt = None
        except Exception as e:
            print(f"[WARN] Error in closeEvent: {e}")
        
        event.accept()

    def keyPressEvent(self, event):
        """快捷键处理：ESC 切换日志窗口"""
        if event.key() == _Key_Escape:
            if self.log_output.isVisible():
                self.log_output.hide()
            else:
                self.log_output.show()
        else:
            super().keyPressEvent(event)

    @property
    def active_df(self) -> pd.DataFrame:
        """根据当前模式返回活跃的数据集"""
        return self.df_mem if self.is_memory_mode else self.df_file

    @active_df.setter
    def active_df(self, df: pd.DataFrame):
        """同步设置对应的活跃数据集"""
        if self.is_memory_mode:
            self.df_mem = df
        else:
            self.df_file = df

    def load_history(self):
        """加载历史记录"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.file_history = data.get('file_history', [])
                    self.query_history = data.get('query_history', [])
        except Exception as e:
            print(f"Load History Error: {e}")

    def save_history(self):
        """保存历史记录"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'file_history': self.file_history[:20],  # 保留最近 20 条
                    'query_history': self.query_history[:20]
                }, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Save History Error: {e}")

    def add_file_to_history(self, path):
        if not path:
            return
        if path in self.file_history:
            self.file_history.remove(path)
        self.file_history.insert(0, path)
        self.save_history()
        self._update_history_combos()

    def add_query_to_history(self, query):
        if not query:
            return
        if query in self.query_history:
            self.query_history.remove(query)
        self.query_history.insert(0, query)
        self.save_history()
        self._update_history_combos()

    def _update_history_combos(self):
        """同步 UI 中的历史下拉框"""
        if hasattr(self, 'file_history_combo'):
            self.file_history_combo.blockSignals(True)
            self.file_history_combo.clear()
            self.file_history_combo.addItem("-- Recent Files --")
            self.file_history_combo.addItems(self.file_history)
            self.file_history_combo.blockSignals(False)
            
        if hasattr(self, 'query_history_combo'):
            self.query_history_combo.blockSignals(True)
            self.query_history_combo.clear()
            self.query_history_combo.addItem("-- Recent Queries --")
            self.query_history_combo.addItems([q.replace('\n', ' ')[:50] + "..." if len(q) > 50 else q for q in self.query_history])
            self.query_history_combo.blockSignals(False)

    def log(self, message):
        """Append message to log area and console with Time (HH:MM:SS.mmm)"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_msg = f"[{timestamp}] {message}"
        if hasattr(self, 'log_output'):
            self.log_output.appendPlainText(formatted_msg)
            self.log_output.verticalScrollBar().setValue(
                self.log_output.verticalScrollBar().maximum()
            )
        print(formatted_msg)

    def get_queried_df(self) -> pd.DataFrame:
        """应用全局 Query 后的数据集 (支持 Expression, Eval 和 Script 模式)"""
        if self._is_querying:
            return self.active_df
            
        df = self.active_df
        query_str = self.query_input.toPlainText().strip()
        if not query_str:
            return df
        
        self._is_querying = True
        try:
            return self._execute_query_logic(df, query_str)
        finally:
            self._is_querying = False

    def _execute_query_logic(self, df: pd.DataFrame, query_str: str) -> pd.DataFrame:
        """调用通用查询引擎执行逻辑"""
        if not query_engine:
            self.log("Error: query_engine_util not found. Use legacy or skip.")
            return df
            
        self.log(f"--- Applying Advanced Query on df ({len(df)} rows) ---")
        try:
            return query_engine.execute(df, query_str)
        except Exception as e:
            self.log(f"Query Engine Error: {e}")
            self.statusBar().showMessage(f"Query Error: {e}")
            return df

    @active_df.setter
    def active_df(self, value: pd.DataFrame):
        """根据当前模式更新活跃的数据集"""
        if self.is_memory_mode:
            self.df_mem = value
        else:
            self.df_file = value

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.btn_open = QPushButton("Open File")
        self.btn_open.clicked.connect(self.on_open_file)
        
        # 文件历史下拉框
        self.file_history_combo = QComboBox()
        self.file_history_combo.setFixedWidth(150)
        self.file_history_combo.currentIndexChanged.connect(self.on_file_history_selected)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.on_refresh)
        
        self.btn_mem = QPushButton("Memory View")
        self.btn_mem.clicked.connect(self.on_memory_sync)
        if self.service_proxy:
            self.btn_mem.setEnabled(True)
            self.btn_mem.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        else:
            self.btn_mem.setEnabled(False)

        # Edit Operations
        self.btn_add_row = QPushButton("Add Row")
        self.btn_add_row.setStyleSheet("background-color: #2ecc71; color: white;")
        self.btn_add_row.clicked.connect(self.on_add_row)

        self.btn_del_row = QPushButton("Delete Row")
        self.btn_del_row.setStyleSheet("background-color: #e74c3c; color: white;")
        self.btn_del_row.clicked.connect(self.on_delete_row)

        self.btn_save = QPushButton("💾 Save Changes")
        self.btn_save.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.on_save_changes)

        self.btn_save_as = QPushButton("📤 Save As / Export")
        self.btn_save_as.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        self.btn_save_as.clicked.connect(self.on_save_as)

        self.btn_read_table = QPushButton("📖 Read Table")
        self.btn_read_table.setStyleSheet("background-color: #34495e; color: white;")
        self.btn_read_table.clicked.connect(self.on_read_table)

        self.btn_del_table = QPushButton("🗑️ Delete Table")
        self.btn_del_table.setStyleSheet("background-color: #607d8b; color: white;")
        self.btn_del_table.clicked.connect(self.on_delete_table)

        self.btn_repair_h5 = QPushButton("🔧 修复合并HDF5")
        self.btn_repair_h5.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        self.btn_repair_h5.clicked.connect(self.on_repair_h5_clicked)

        # Delete by Time Controls
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("UnixTS or Start, End")
        self.time_input.setFixedWidth(180)
        
        self.btn_del_time = QPushButton("Del by Time")
        self.btn_del_time.setStyleSheet("background-color: #9b59b6; color: white;")
        self.btn_del_time.clicked.connect(self.on_delete_by_time)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter Stock Code...")
        self.search_input.textChanged.connect(self.on_filter)
        
        # Source Selection
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(180)  # 默认变宽
        self.source_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.source_combo.addItem("File")
        if self.service_proxy:
            self.source_combo.addItem("Memory Service")
        self.source_combo.currentIndexChanged.connect(self.on_source_changed)

        self.btn_scan = QPushButton("Scan")
        self.btn_scan.clicked.connect(self.discover_internal_dfs)

        # Toolbar - Row 1: Operations (使用 FlowLayout 实现自适应流式排版)
        top_toolbar = FlowLayout()
        top_toolbar.addWidget(self.btn_open)
        top_toolbar.addWidget(self.file_history_combo)
        top_toolbar.addWidget(self.btn_refresh)
        top_toolbar.addWidget(self.btn_mem)
        
        spacer1 = QWidget()
        spacer1.setFixedWidth(10)
        top_toolbar.addWidget(spacer1)
        
        top_toolbar.addWidget(self.btn_add_row)
        top_toolbar.addWidget(self.btn_del_row)
        top_toolbar.addWidget(self.btn_save)
        top_toolbar.addWidget(self.btn_save_as)
        top_toolbar.addWidget(self.btn_read_table)
        top_toolbar.addWidget(self.btn_del_table)
        top_toolbar.addWidget(self.btn_repair_h5)
        
        lbl_source = QLabel("Source:")
        top_toolbar.addWidget(lbl_source)
        top_toolbar.addWidget(self.source_combo)
        top_toolbar.addWidget(self.btn_scan)
        main_layout.addLayout(top_toolbar)

        # Toolbar - Row 2: Filters
        filter_layout = FlowLayout()
        lbl_time_filter = QLabel("Time Filter:")
        filter_layout.addWidget(lbl_time_filter)
        filter_layout.addWidget(self.time_input)
        filter_layout.addWidget(self.btn_del_time)
        
        # 诊断个股功能
        lbl_diag = QLabel("诊断个股:")
        filter_layout.addWidget(lbl_diag)
        
        self.diag_input = QLineEdit()
        self.diag_input.setPlaceholderText("Code...")
        self.diag_input.setFixedWidth(80)
        self.diag_input.returnPressed.connect(self.on_diagnose_click)
        filter_layout.addWidget(self.diag_input)
        
        self.btn_diag = QPushButton("🔍 诊断")
        self.btn_diag.clicked.connect(self.on_diagnose_click)
        self.btn_diag.setStyleSheet("background-color: #0288D1; color: white; font-weight: bold;")
        filter_layout.addWidget(self.btn_diag)
        
        spacer2 = QWidget()
        spacer2.setFixedWidth(10)
        filter_layout.addWidget(spacer2)
        
        lbl_search = QLabel("Search Code:")
        filter_layout.addWidget(lbl_search)
        
        self.search_input.setFixedWidth(120)
        filter_layout.addWidget(self.search_input)
        main_layout.addLayout(filter_layout)
        
        # --- 第二栏：高级查询 (Advanced Query) ---
        query_layout = QHBoxLayout()
        query_layout.addWidget(QLabel("Query (df):"))
        
        self.query_input = QPlainTextEdit()
        self.query_input.setPlaceholderText("Variable: df\ne.g. close > 10 and volume > 100000\nOr Python script: signal = (close > high41) & (close.shift(1) < high41.shift(1))")
        self.query_input.setMaximumHeight(80)
        query_layout.addWidget(self.query_input, 3)
        
        # 查询历史
        query_side_layout = QVBoxLayout()
        
        # 历史查询行 (带删除按钮)
        query_hist_row = QHBoxLayout()
        self.query_history_combo = QComboBox()
        self.query_history_combo.setFixedWidth(180)
        self.query_history_combo.currentIndexChanged.connect(self.on_query_history_selected)
        
        self.btn_del_query = QPushButton("×")
        self.btn_del_query.setFixedWidth(25)
        self.btn_del_query.setToolTip("Delete selected history item")
        self.btn_del_query.setStyleSheet("color: #e74c3c; font-weight: bold; border: 1px solid #e74c3c; border-radius: 3px;")
        self.btn_del_query.clicked.connect(self.on_delete_query_history)
        
        query_hist_row.addWidget(self.query_history_combo)
        query_hist_row.addWidget(self.btn_del_query)
        query_side_layout.addLayout(query_hist_row)
        
        self.btn_apply_query = QPushButton("Apply")
        self.btn_apply_query.setStyleSheet("background-color: #34495e; color: white; font-weight: bold;")
        self.btn_apply_query.clicked.connect(self.on_apply_query)
        self.btn_apply_query.setFixedHeight(40)
        query_side_layout.addWidget(self.btn_apply_query)
        
        self.btn_clear_query = QPushButton("Clear")
        self.btn_clear_query.clicked.connect(self.on_clear_query)
        query_side_layout.addWidget(self.btn_clear_query)
        
        query_layout.addLayout(query_side_layout)
        main_layout.addLayout(query_layout)
        
        # 初始化下拉框内容
        self._update_history_combos()

        # --- 第三栏：日志与状态 ---
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(80)
        self.log_output.setPlaceholderText("Execution Logs... (Press ESC to Toggle)")
        self.log_output.setStyleSheet("background-color: #fdf6e3; color: #586e75; font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt;")
        main_layout.addWidget(self.log_output)
        self.log_output.hide() # 默认隐藏

        # Stats Label
        self.stats_label = QLabel("No data loaded. Please open a minute_kline_cache.pkl file.")
        self.stats_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(self.stats_label)

        # Splitter for Summary and Details
        self.main_splitter = QSplitter(_Vertical)
        
        # Upper Splitter: Summary + Details (Horizontal)
        self.upper_splitter = QSplitter(_Horizontal)
        
        # Summary Table (Grouped by code)
        self.summary_table = QTableView()
        self.summary_table.setModel(DataFrameModel(pd.DataFrame()))
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setSelectionBehavior(_SelectRows)
        self.summary_table.setSortingEnabled(True)
        # 🛡️ 统一信号连接
        self._connect_table_signals(self.summary_table, self.on_summary_clicked)
        
        # Detail Table
        self.detail_table = QTableView()
        self.detail_table.setModel(DataFrameModel(pd.DataFrame()))
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setSelectionBehavior(_SelectRows)
        self.detail_table.setSortingEnabled(True)
        self._connect_table_signals(self.detail_table, self.on_row_selection_linkage)
        
        self.upper_splitter.addWidget(self.summary_table)
        self.upper_splitter.addWidget(self.detail_table)
        self.upper_splitter.setStretchFactor(0, 1)
        self.upper_splitter.setStretchFactor(1, 2)

        # Bottom Area: Full Queried Results
        self.full_results_table = QTableView()
        self.full_results_table.setModel(DataFrameModel(pd.DataFrame()))
        self.full_results_table.setAlternatingRowColors(True)
        self.full_results_table.setSelectionBehavior(_SelectRows)
        self.full_results_table.setSortingEnabled(True)
        self._connect_table_signals(self.full_results_table, self.on_row_selection_linkage)
        
        # Add a label for the bottom area
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 5, 0, 0)
        self.full_results_label = QLabel("<b>Full Queried Results:</b> 0 records")
        bottom_layout.addWidget(self.full_results_label)
        bottom_layout.addWidget(self.full_results_table)

        self.main_splitter.addWidget(self.upper_splitter)
        self.main_splitter.addWidget(bottom_container)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.main_splitter, 1)

        self.setup_context_menus()
        self.statusBar().showMessage("Ready")
        self.resize(1100, 800)
        
    def _connect_table_signals(self, table_view: QTableView, linkage_slot: Callable[[QModelIndex], Any]):
        """
        🛡️ 集中处理 TableView 的信号连接，确保 setModel 后信号依然存活
        连接: 单击(clicked)、选择变更(currentRowChanged)
        """
        try:
            # 1. 连接基础点击信号
            try:
                table_view.clicked.disconnect()
            except Exception: pass
            table_view.clicked.connect(linkage_slot)
            
            # 2. 连接双击信号 (确保 on_double_click 始终可用)
            try:
                table_view.doubleClicked.disconnect()
            except Exception: pass
            table_view.doubleClicked.connect(self.on_double_click)

            # 3. 连接选择模型信号 (处理键盘上下键联动)
            selection_model = table_view.selectionModel()
            if selection_model:
                try:
                    selection_model.currentRowChanged.disconnect()
                except Exception: pass
                selection_model.currentRowChanged.connect(lambda curr, prev: linkage_slot(curr))
        except Exception as e:
            print(f"[DEBUG] _connect_table_signals error: {e}")

    def _smart_resize(self, table_view):
        """极致性能优化：使用 QFontMetrics 对前 100 行采样计算宽度，彻底杜绝 UI 挂起"""
        model = table_view.model()
        if not model or not hasattr(model, '_data'):
            return
        df = model._data
        if df.empty:
            return
            
        # 1. 准备计算环境 (采样前 100 行以兼顾性能与自适应)
        fm = table_view.fontMetrics()
        # 处理宽度函数的兼容性 (Qt6 为 horizontalAdvance, 之前为 width)
        width_func = getattr(fm, "horizontalAdvance", getattr(fm, "width", lambda x: 80))
        sample_df = df.head(100)
        
        for i, col in enumerate(df.columns):
            col_name = str(col)
            col_lower = col_name.lower()
            
            # 2. 计算标题宽度
            header_w = width_func(col_name) + 30
            
            # 3. 采样数据宽度
            max_data_w = 0
            if not sample_df.empty:
                # 针对不同列型进行快速探测
                col_data = sample_df[col]
                for val in col_data:
                    val_str = str(val)
                    if len(val_str) > 30: val_str = val_str[:30] # 防止垃圾数据撑满
                    max_data_w = max(max_data_w, width_func(val_str))
            
            # 4. 结合业务场景确定最终宽度
            target_w = max(header_w, max_data_w + 12)
            
            # 硬编码针对性微调
            if col_lower == 'code':
                target_w = max(target_w, 75)
            elif col_lower in ('time', 'ticktime', 'datetime', 'timestamp', 'date', '时间'):
                target_w = max(target_w, 160)
            elif col_lower == 'name':
                target_w = max(target_w, 110)
            elif col_lower == 'count':
                target_w = max(target_w, 55)
            
            if target_w > 450: target_w = 450
            table_view.setColumnWidth(i, target_w)

    def auto_load(self):
        # Default path resolution
        path = None
        if cct:
            ram_path = cct.get_ramdisk_path("minute_kline_cache.pkl")
            if ram_path and os.path.exists(ram_path):
                path = str(ram_path)
        
        if not path:
            # Check current directory
            local_path = "minute_kline_cache.pkl"
            if os.path.exists(local_path):
                path = local_path
        
        if path:
            self.load_data(path)

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        统一 DataFrame 结构：
        - 确保 'code' 和 'time' 是列记录
        - 解决索引与列名冲突问题
        """
        df = df.copy()

        # 1. 彻底解决索引名与列名冲突 (ValueError: 'code' is both an index level and a column label)
        # 在 reset_index 之前，如果索引名或 level 名与列名冲突，pandas 会报错。
        # 我们采用最激进策略：先强制清除索引名称
        col_list = df.columns.tolist()
        
        if isinstance(df.index, pd.MultiIndex):
            # 记录旧索引值，以便后续手动提取（如果列中缺失）
            try:
                # 检查是否有名为 code 的 level
                if 'code' in df.index.names and 'code' not in col_list:
                    df['code'] = df.index.get_level_values('code').astype(str)
                # 检查是否有名为 time/ticktime 的 level
                for tname in ['time', 'ticktime', 'datetime']:
                    if tname in df.index.names and tname not in col_list:
                        df[tname] = df.index.get_level_values(tname)
                        break
            except Exception:
                pass
            # 强制清空索引名以消除歧义
            df.index.names = [None] * len(df.index.names)
        else:
            # 单层索引的情况
            if df.index.name in col_list:
                # 如果 index name 冲突，直接重置时会报错，所以先改名
                df.index.name = f"fixed_idx_{df.index.name}"
            elif df.index.name is None and 'index' in col_list:
                df.index.name = "original_index"

        # 2. 处理索引转列 (MultiIndex 后 reset，或者单层 index 包含 code)
        if isinstance(df.index, pd.MultiIndex):
            df.reset_index(drop=True, inplace=True)
        else:
            # 如果 index 不是 RangeIndex，且我们还没拿到 code 列
            if not isinstance(df.index, pd.RangeIndex) and 'code' not in df.columns:
                df = df.reset_index()
                # 尝试通过位置或名称找 code
                if 'code' not in df.columns:
                    col0 = df.columns[0]
                    if 'level' in str(col0) or 'index' in str(col0):
                        df.rename(columns={col0: 'code'}, inplace=True)

        # 3. 字段映射集成 (双兼容模式: time / ticktime 有那个用那个)
        # if 'ticktime' in df.columns and 'time' not in df.columns:
        #     df['time'] = df['ticktime']
        # 注意: 这里保持注释状态以维持数据列清洁，逻辑在 Model 和联动中适配
            
        # 4. 确保核心列存在且类型正确
        if 'code' in df.columns:
            df['code'] = df['code'].astype(str)
        else:
            # 如果实在没拿到 code，造一个占位符或取第一列
            df['code'] = "000000"

        return df


    # def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
    #     """
    #     统一 DataFrame 结构：
    #     - MultiIndex(code, ticktime) → 普通列 code, time
    #     - 保证 Viewer 内部只使用列，不使用索引
    #     """
    #     if isinstance(df.index, pd.MultiIndex):
    #         df = df.copy()

    #         # 提取 index → columns
    #         idx_names = df.index.names

    #         if 'code' in idx_names:
    #             df['code'] = df.index.get_level_values('code')
    #         else:
    #             df['code'] = df.index.get_level_values(0)

    #         # ticktime / time / datetime
    #         time_level = None
    #         for name in idx_names:
    #             if name and name.lower() in ('ticktime', 'time', 'datetime', 'date'):
    #                 time_level = name
    #                 break

    #         if time_level:
    #             ts = df.index.get_level_values(time_level)
    #         else:
    #             ts = df.index.get_level_values(1)

    #         # 统一成 float timestamp（你后面逻辑都用这个）
    #         if np.issubdtype(ts.dtype, np.datetime64):
    #             df['time'] = ts.astype('int64') / 1e9
    #         else:
    #             df['time'] = ts.astype(float)

    #         df.reset_index(drop=True, inplace=True)

    #     return df

    # def on_open_file(self):
    #     start_dir = ""
    #     if self.current_file and os.path.exists(self.current_file):
    #         start_dir = os.path.dirname(os.path.abspath(self.current_file))
            
    #     file_name, _ = QFileDialog.getOpenFileName(
    #         self, "Open Cache File", start_dir, "Pickle Files (*.pkl);;All Files (*)"
    #     )
    #     if file_name:
    #         self.load_data(file_name)
    #         if self.source_combo.currentText() != "File":
    #             self.source_combo.setCurrentText("File")

    def on_open_file(self):
        start_path = ""
        if self.current_file and os.path.exists(self.current_file):
            start_path = self.current_file
        elif self.file_history:
            for path in self.file_history:
                if os.path.exists(path):
                    start_path = path
                    break

        # 修改这里，添加 HDF5 支持
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Cache File",
            start_path,
            "All Support (*.h5 *.pkl *.csv *.json *.gz);;CSV Files (*.csv);;HDF5 Files (*.h5);;Session Files (*.json *.json.gz);;Pickle Files (*.pkl);;All Files (*)"
        )

        if file_name:
            self.load_data(file_name)

            # 更新数据源显示
            if self.source_combo.currentText() != "File":
                self.source_combo.setCurrentText("File")


    def discover_internal_dfs(self):
        """扫描 main_app 及其子模块中后来添加的所有 pandas DataFrame"""
        if not self.main_app:
            self.statusBar().showMessage("Main app not connected.")
            return

        self.internal_dfs = {}

        def _scan_obj(obj, prefix="", depth=0, visited=None):
            if depth > 3:  # 防止递归过深
                return
            if visited is None:
                visited = set()
            obj_id = id(obj)
            if obj_id in visited:
                return
            visited.add(obj_id)

            try:
                attr_names = dir(obj)
            except Exception:
                return

            for attr_name in attr_names:
                if attr_name.startswith('_'):
                    continue
                # 过滤掉冗余的 live_strategy 历史缓存字典等庞大碎片
                if attr_name in ('daily_history_cache', 'history_cache', 'stock_history_cache'):
                    continue
                try:
                    attr = getattr(obj, attr_name)
                    full_name = f"{prefix}.{attr_name}" if prefix else attr_name

                    # 1. 直接是 DataFrame
                    if isinstance(attr, pd.DataFrame) and not attr.empty:
                        self.internal_dfs[full_name] = attr
                    # 2. 是 dict 字典容器，遍历内部的 DataFrame（跳过某些特定名字）
                    elif isinstance(attr, dict) and attr_name not in ('daily_history_cache', 'history_cache', 'stock_history_cache'):
                        for k, v in attr.items():
                            if isinstance(v, pd.DataFrame) and not v.empty:
                                self.internal_dfs[f"{full_name}[{k}]"] = v
                    # 3. 是 list/tuple 列表容器
                    elif isinstance(attr, (list, tuple)):
                        for idx, item in enumerate(attr):
                            if isinstance(item, pd.DataFrame) and not item.empty:
                                self.internal_dfs[f"{full_name}[{idx}]"] = item
                    # 4. 是自定义子对象（避免扫描基本模块和常见标准库）
                    elif hasattr(attr, '__dict__') and not isinstance(attr, (str, int, float, bool, bytes, type)):
                        _scan_obj(attr, prefix=full_name, depth=depth+1, visited=visited)
                except Exception:
                    continue

        # 开始扫描 main_app 根对象
        _scan_obj(self.main_app, prefix="app")

        # 显式抓取 market_bus 行情状态总线中的 DataFrame 数据集
        market_bus = getattr(self.main_app, 'market_bus', None)
        if market_bus is None:
            try:
                from market_state_bus import MarketStateBus
                market_bus = MarketStateBus.get_instance()
            except Exception:
                market_bus = None

        if market_bus:
            for b_attr in ['_df_all', '_df_filtered', '_df_all_res', '_df_filtered_res']:
                try:
                    b_df = getattr(market_bus, b_attr, None)
                    if isinstance(b_df, pd.DataFrame) and not b_df.empty:
                        clean_name = b_attr.lstrip('_')
                        self.internal_dfs[f"market_bus.{clean_name}"] = b_df
                except Exception:
                    pass

        # 重新构建与刷新下拉框
        # 保留 File 和 Memory Service（如果存在）
        base_items = ["File"]
        if self.service_proxy:
            base_items.append("Memory Service")

        current_selected = self.source_combo.currentText()
        
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for item in base_items:
            self.source_combo.addItem(item)
        
        for name in sorted(self.internal_dfs.keys()):
            self.source_combo.addItem(name)
        
        # 恢复选择
        idx = self.source_combo.findText(current_selected)
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)
        else:
            self.source_combo.setCurrentIndex(0)
        self.source_combo.blockSignals(False)

        # 动态计算最宽条目文本像素，使弹出视图与下拉框自适应展开
        fm = self.source_combo.fontMetrics()
        max_w = 180  # 默认变宽基础底线
        for i in range(self.source_combo.count()):
            text_w = getattr(fm, "horizontalAdvance", getattr(fm, "width", lambda s: 120))(self.source_combo.itemText(i)) + 45
            if text_w > max_w:
                max_w = text_w
        
        # 限制自适应最大上界，防止异常超长文本
        if max_w > 450:
            max_w = 450

        self.source_combo.setMinimumWidth(max_w)
        combo_view = self.source_combo.view()
        if combo_view:
            combo_view.setMinimumWidth(max_w)

        self.statusBar().showMessage(f"Discovered {len(self.internal_dfs)} internal DataFrames.")

    def on_source_changed(self, index):
        source_name = self.source_combo.currentText()
        if source_name == "File":
            self.is_memory_mode = False
            self.update_summary()
        elif source_name == "Memory Service":
            self.on_memory_sync()
        elif source_name in self.internal_dfs:
            self.is_memory_mode = False # Treat as file-like for direct local modification
            raw_df = self.internal_dfs[source_name]
            # 🛡️ 进行格式规范化，确保包含 code 列及正确的 Index 映射
            normalized_df = self._normalize_dataframe(raw_df)
            self.active_df = normalized_df
            self.df_file = normalized_df.copy()
            self.update_summary()
            self.on_apply_query()
            self.statusBar().showMessage(f"Loaded internal source: {source_name} count: {len(self.df_file)}", 3000)

    def on_refresh(self):
        if self.is_memory_mode:
            self.on_memory_sync()
        elif hasattr(self, 'current_file') and self.current_file and os.path.exists(self.current_file):
            self.load_data(self.current_file)

    def on_memory_sync(self):
        """直接从内存中的实时服务同步快照"""
        if not self.service_proxy:
            self.statusBar().showMessage("Realtime Service not connected.")
            return
            
        try:
            self.statusBar().showMessage("Pulling snapshot from memory...")
            self.is_memory_mode = True
            
            # 这里调用 DataPublisher 或 MinuteKlineCache 的 to_dataframe
            df = self.service_proxy.get_55188_data().get('df_klines', pd.DataFrame())
            # df = self._normalize_dataframe(df)
            if df.empty:
                try:
                    df = self.service_proxy.kline_cache.to_dataframe()
                except:
                    pass

            if df.empty:
                self.statusBar().showMessage("Memory Cache is currently empty.")
                return

            self.active_df = df
            
            # [FIX] 强制清空旧 Model 释放 130 万级数据的内存句柄
            empty_model = DataFrameModel(pd.DataFrame())
            self.summary_table.setModel(empty_model)
            self.detail_table.setModel(empty_model)
            self.full_results_table.setModel(empty_model)
            QApplication.processEvents()
            
            self.on_apply_query()
            
            stock_count = len(df['code'].unique())
            total_nodes = len(df)
            
            self.stats_label.setText(
                f"🧠 MODE: REALTIME MEMORY | Stocks: {stock_count} | Total Nodes: {total_nodes}\n"
                f"Data synchronized at: {datetime.now().strftime('%H:%M:%S')}"
            )
            self.statusBar().showMessage("Memory data synchronized. Edits will apply to Memory Snapshot.")
        except Exception as e:
            self.statusBar().showMessage(f"Memory Sync Failed: {e}")


    def load_data(self, file_path):
        from PyQt6.QtWidgets import QInputDialog
        try:
            self.current_file = file_path
            self.is_memory_mode = False
            self.statusBar().showMessage(f"Loading {file_path}...")
            
            # 添加到历史
            self.add_file_to_history(file_path)

            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".pkl":
                # 获取配置中的首选压缩方式
                config_ini = cct.get_ramdisk_path('h5config.txt') if cct else None
                if not config_ini:
                    config_ini = os.path.join(os.getcwd(), 'h5config.txt')
                cfg_compression = cct.get_config_value(config_ini, 'kline_viewer', xtype='compression', read=True) if cct else None
                if not cfg_compression:
                    cfg_compression = 'zstd'
                if str(cfg_compression).lower() == 'none':
                    cfg_compression = None

                attempts = [cfg_compression, 'zstd', 'gzip', 'bz2', 'zip', 'xz', 'infer', None]
                unique_attempts = []
                for att in attempts:
                    if att not in unique_attempts:
                        unique_attempts.append(att)

                df = None
                last_err = None
                for compression_mode in unique_attempts:
                    try:
                        df = pd.read_pickle(file_path, compression=compression_mode)
                        break
                    except Exception as e:
                        last_err = e
                        continue
                
                if df is None:
                    raise last_err

            elif ext == ".csv":
                try:
                    # 🛡️ 智能表头与多周期数据处理
                    import csv
                    header_idx = 0
                    encoding = 'utf-8'
                    
                    # 1. 探测编码与表头行
                    def scout_csv(f_path, enc):
                        lines = []
                        with open(f_path, 'r', encoding=enc) as f:
                            for i, line in enumerate(f):
                                lines.append(line.strip())
                                if i > 15: break
                        return lines

                    lines = []
                    try:
                        lines = scout_csv(file_path, 'utf-8')
                        encoding = 'utf-8'
                    except UnicodeDecodeError:
                        lines = scout_csv(file_path, 'gbk')
                        encoding = 'gbk'

                    # 2. 寻找最佳表头行 (通过特征权值：同时包含 open/high/low/trade 的行优先级最高)
                    header_idx = 0
                    max_score = 0
                    for i, line in enumerate(lines):
                        low_line = line.lower()
                        score = 0
                        # 核心权重字段
                        for kw in ['open', 'high', 'low', 'close', 'trade', 'volume']:
                            if kw in low_line: score += 2
                        # 次要权重字段
                        if 'name' in low_line: score += 1
                        if 'code' in low_line: score += 1
                        
                        if score > max_score:
                            max_score = score
                            header_idx = i
                        # 如果分数很高，大概率就是表头了
                        if score >= 6: 
                            header_idx = i
                            break
                    
                    # 3. 加载初始数据 (添加 compression='infer' 支持自适应解压)
                    df = pd.read_csv(file_path, encoding=encoding, skiprows=header_idx, index_col=False, compression='infer')
                    
                    # 4. 修复表头偏移与 Unnamed 列问题
                    if not df.empty:
                        # 🛡️ 特殊处理：如果第一行数据仅包含 "code" 这种标记，说明它是占位行
                        first_val_s = str(df.iloc[0, 0]).strip().lower()
                        if first_val_s == 'code':
                            # 将这个 "code" 标记作为第一列的正确列名
                            if 'unnamed' in str(df.columns[0]).lower() or str(df.columns[0]) == '':
                                df.rename(columns={df.columns[0]: 'code'}, inplace=True)
                            # 删掉这个占位行
                            df = df.drop(df.index[0]).reset_index(drop=True)

                        # 继续常规检查第一列代码
                        if not df.empty:
                            first_col_name = str(df.columns[0])
                            first_val = str(df.iloc[0, 0]).split('.')[0]
                            is_digit_code = bool(re.match(r'^\d{6}$', first_val))
                            
                            if is_digit_code:
                                if 'unnamed' in first_col_name.lower() or first_col_name == '' or first_col_name == '0':
                                    df.rename(columns={df.columns[0]: 'code'}, inplace=True)

                        # 情况 B: 处理用户提到的 "code 列被放在最后" 或偏移
                        if 'code' not in df.columns or not bool(re.match(r'^\d{6}$', str(df['code'].iloc[0]).split('.')[0])):
                            # 遍历所有列找 6 位数字列
                            for col in df.columns:
                                sample_val = str(df[col].iloc[0]).split('.')[0]
                                if bool(re.match(r'^\d{6}$', sample_val)):
                                    # 如果找到了 6 位数序列，且当前 code 列名被误用到其他列（如索引）
                                    if 'code' in df.columns:
                                        df.rename(columns={'code': 'original_index_or_other'}, inplace=True)
                                    df.rename(columns={col: 'code'}, inplace=True)
                                    break

                    # 5. 清理“占位行”并确保 code 列在前
                    if not df.empty and 'code' in df.columns:
                        # 过滤非数字杂质
                        df = df[df['code'].astype(str).str.match(r'^\d{5,6}')].copy()
                        
                        # 字段补全与补零
                        df['code'] = df['code'].astype(str).str.split('.').str[0].str.zfill(6)
                        
                        # 将 code 移到第一列
                        cols = ['code'] + [c for c in df.columns if c != 'code']
                        df = df[cols]

                    # 6. 其他字段名一致化
                    if not df.empty:
                        rename_map = {}
                        for col in df.columns:
                            col_lower = str(col).lower()
                            if col_lower in ('股票名称', '名称') and 'name' not in df.columns:
                                rename_map[col] = 'name'
                        if rename_map:
                            df.rename(columns=rename_map, inplace=True)
                    
                    # 处理重复列名
                    if df.columns.duplicated().any():
                        df = df.loc[:, ~df.columns.duplicated()]

                except Exception as e:
                    self.statusBar().showMessage(f"CSV Load Error: {e}")
                    return

            elif ext == ".h5":
                # 获取所有 key
                with pd.HDFStore(file_path, "r") as store:
                    keys = store.keys()  # 返回 ['/data1', '/data2', ...]
                    keys = list(map(lambda k: k.strip("/"), keys))  # 去掉前导斜杠

                if not keys:
                    self.stats_label.setText(f"No datasets found in {file_path}")
                    return

                # 只有一个 key 时直接使用
                if len(keys) == 1:
                    key = keys[0]
                else:
                    # 尝试默认选中当前的 key
                    default_idx = 0
                    if self.current_key in keys:
                        default_idx = keys.index(self.current_key)

                    # 弹出选择框，让用户选择 key
                    key, ok = QInputDialog.getItem(
                        self,
                        "Select HDF5 Key",
                        "Choose dataset to load:",
                        keys,
                        default_idx,
                        False
                    )
                    if not ok:
                        self.statusBar().showMessage("HDF5 load cancelled.")
                        return

                df = pd.read_hdf(file_path, key=key)
                self.current_key = key

            elif ext in (".json", ".gz"):
                df = self._load_session_json(file_path)

            else:
                self.stats_label.setText(f"Unsupported file type: {ext}")
                self.statusBar().showMessage("Error loading data.")
                return

            # 统一规范化
            df = self._normalize_dataframe(df)
            if df is None or df.empty:
                return
            
            # [FIX] 核心：在注入新数据前，彻底切断与 130 万旧数据的 Model 绑定
            # 这一步能防止 Qt 的视图组件在数据切换间隙通过旧索引访问新数据导致卡死
            empty = DataFrameModel(pd.DataFrame())
            self.summary_table.setModel(empty)
            self.detail_table.setModel(empty)
            self.full_results_table.setModel(empty)
            QApplication.processEvents()

            self.active_df = df
            self.df_file = df # df_file 仅用于文件模式下的原始数据备份
            self.on_apply_query()

            # --- 元数据统计 (放在独立 try-except 中，避免报错导致加载失败) ---
            try:
                # 文件信息
                mtime = os.path.getmtime(file_path)
                time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

                stock_count = len(df['code'].unique())
                total_nodes = len(df)

                # calculate fingerprint for display
                fp = "N/A"
                try:
                    from cache_utils import df_fingerprint
                    # 尝试自适应列名
                    fp_cols = [c for c in ['code', 'time', 'ticktime', 'close', 'volume'] if c in df.columns]
                    fp = df_fingerprint(df, cols=fp_cols)
                except:
                    pass

                self.stats_label.setText(
                    f"📊 File: {os.path.basename(file_path)} | Last Modified: {time_str} | "
                    f"Stocks: {stock_count} | Total Nodes: {total_nodes}\n"
                    f"🔑 Fingerprint (MD5): {fp}"
                )
            except Exception as stats_e:
                print(f"Stats Error: {stats_e}")
                self.stats_label.setText(f"Loaded {os.path.basename(file_path)} (Stats failed)")

            self.statusBar().showMessage(f"Data loaded successfully. count: {len(self.df_file)}", 3000)

        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print(f"\n[ERROR] Load Data Failed: {file_path}")
            print(err_msg)
            self.stats_label.setText(f"Error loading data: {e}")
            self.statusBar().showMessage("Error loading data. Check console for details.")



    # def load_data(self, file_path):
    #     try:
    #         self.current_file = file_path
    #         self.is_memory_mode = False
    #         self.statusBar().showMessage(f"Loading {file_path}...")
            
    #         df = pd.read_pickle(file_path)
    #         df = self._normalize_dataframe(df)
    #         if df is None or df.empty:
    #             self.stats_label.setText(f"File {file_path} is empty.")
    #             return

    #         self.df_file = df
    #         self.update_summary()
    #         self.on_filter()
            
    #         mtime = os.path.getmtime(file_path)
    #         time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
    #         stock_count = len(df['code'].unique())
    #         total_nodes = len(df)
            
    #         # calculate fingerprint for display
    #         try:
    #             from cache_utils import df_fingerprint
    #             fp = df_fingerprint(df, cols=['code', 'time', 'close', 'volume'])
    #         except ImportError:
    #             fp = "N/A (cache_utils not found)"

    #         self.stats_label.setText(
    #             f"📊 File: {os.path.basename(file_path)} | Last Modified: {time_str} | "
    #             f"Stocks: {stock_count} | Total Nodes: {total_nodes}\n"
    #             f"🔑 Fingerprint (MD5): {fp}"
    #         )
    #         self.statusBar().showMessage(f"Data loaded successfully. dateCount: {len(self.df_file)}")
            
    #     except Exception as e:
    #         self.stats_label.setText(f"Error loading data: {e}")
    #         self.statusBar().showMessage("Error loading data.")

    def update_summary(self, df_input=None):
        """更新左侧股票摘要表"""
        try:
            df_curr = df_input if df_input is not None else self.get_queried_df()
            if df_curr is None or df_curr.empty:
                self.summary_table.setModel(DataFrameModel(pd.DataFrame(columns=['code', 'count'])))
                return
            
            # 性能与字段显示优化：确保摘要表中包含 code 和 name (如果存在)
            if 'code' in df_curr.columns:
                if 'name' in df_curr.columns:
                    # [PERF] 百万行级别下，value_counts + drop_duplicates 组合比 groupby.agg 快数倍
                    counts = df_curr['code'].value_counts()
                    name_map = df_curr[['code', 'name']].drop_duplicates('code').set_index('code')['name']
                    
                    summary = counts.to_frame(name='count')
                    summary['name'] = name_map
                    summary = summary.reset_index().rename(columns={'index': 'code'})
                    # 补充可能缺失的 name
                    if summary['name'].isnull().any():
                        summary['name'] = summary['name'].fillna('--')
                    
                    summary = summary[['code', 'name', 'count']]
                else:
                    counts = df_curr['code'].value_counts().reset_index()
                    counts.columns = ['code', 'count']
                    summary = counts
            else:
                summary = pd.DataFrame(columns=['code', 'count'])
                
            model = DataFrameModel(summary)
            self.summary_table.setModel(model)
            self._connect_table_signals(self.summary_table, self.on_summary_clicked)
            self._smart_resize(self.summary_table)
        except Exception as e:
            print(f"DEBUG: update_summary Error: {e}")

    def on_apply_query(self):
        """执行查询并刷新界面"""
        import time
        start_t = time.time()
        
        query_str = self.query_input.toPlainText().strip()
        if query_str and not getattr(self, '_is_loading_from_history', False):
            self.add_query_to_history(query_str) # 添加历史记录
            
        self.statusBar().showMessage("Applying query..." if query_str else "Refreshing data summary...")
        
        # [PERF] 核心优化：只在这里计算一次查询结果
        df_queried = self.get_queried_df()
        duration = (time.time() - start_t) * 1000
        self.log(f"Query Process completed in {duration:.1f}ms (Result: {len(df_queried)} rows)")
        
        # 统计数据
        total_count = len(self.active_df)
        match_count = len(df_queried)
        stock_count = df_queried['code'].nunique() if 'code' in df_queried.columns else 0
        total_stocks = self.active_df['code'].nunique() if not self.active_df.empty else 0
        
        # 1. 更新底部统计标签与表格 (full_results_table)
        if query_str:
            self.full_results_label.setText(f"<b>Queried Results:</b> {match_count} found ({stock_count} stocks) / Total {total_count}")
            
            # [PERF] 性能保护：底表展示限制在 5000 行以内，避免 UI 渲染百万行数据挂起
            display_df = df_queried
            if match_count > 5000:
                self.log(f"UI Limit: Displaying top 5000 of {match_count} matches in bottom table.")
                display_df = df_queried.head(5000)

            # [UI] 智能列显示：提取查询中涉及到的列名，优先展示
            if not display_df.empty:
                # 提取查询中出现的列名
                query_cols = []
                all_cols = list(display_df.columns)
                # 提取 query_str 中所有可能的单词，检查是否为列名
                discovered_cols = re.findall(r'\b[a-zA-Z_]\w*\b', query_str)
                for c in discovered_cols:
                    if c in all_cols and c not in query_cols and c not in ('code', 'time'):
                        query_cols.append(c)
                
                # 构建展示顺序：优先 code, name, time，随后是查询涉及列，最后是其他列
                all_cols = list(display_df.columns)
                priority_cols = []
                for c in ['code', 'name', 'time', 'ticktime']:
                    if c in all_cols:
                        priority_cols.append(c)
                
                remaining_cols = [c for c in all_cols if c not in priority_cols and c not in query_cols]
                final_cols = priority_cols + query_cols + remaining_cols
                df_view = display_df[final_cols]
            else:
                df_view = display_df
                
            self.full_results_table.setModel(DataFrameModel(df_view))
            self._connect_table_signals(self.full_results_table, self.on_row_selection_linkage)
            self._smart_resize(self.full_results_table)
            QApplication.processEvents() # 保持响应
        else:
            # 无查询时显示总量统计
            self.full_results_label.setText(f"<b>Full Dataset:</b> {total_count} records ({total_stocks} stocks)")
            # 性能优化：无查询时底部表格不显示全量（除非极小），避免 UI 挂起
            if total_count < 500:
                self.full_results_table.setModel(DataFrameModel(self.active_df))
                self._connect_table_signals(self.full_results_table, self.on_row_selection_linkage)
                self._smart_resize(self.full_results_table)
            else:
                # 显示空表但保留列名，防止 IndexError 并清晰提示
                self.full_results_table.setModel(DataFrameModel(pd.DataFrame(columns=self.active_df.columns)))
                self._connect_table_signals(self.full_results_table, self.on_row_selection_linkage)
        
        # 2. 更新顶部 stats_label (持久化主要统计)
        if hasattr(self, 'stats_label'):
            mode_str = 'MEMORY' if self.is_memory_mode else 'FILE'
            if query_str:
                self.stats_label.setText(f"Matches: {match_count} ({stock_count} stocks) | Base: {total_count} | Mode: {mode_str}")
            else:
                self.stats_label.setText(f"Total: {total_count} records | Stocks: {total_stocks} | Mode: {mode_str}")

        # [UI SYNC START]
        self.log("UI Rendering start...")
        
        # 3. 处理摘要表 (左侧)
        self.update_summary(df_queried)
        self.on_filter(df_queried)
        
        # 4. 处理右侧快照视图
        if query_str and not df_queried.empty:
            # [PERF] 优化快照生成逻辑：使用 drop_duplicates 代替 groupby.tail(1)
            df_snapshot = df_queried.drop_duplicates('code', keep='last')
            
            # 优先展示 code, name, time 等核心列
            all_cols = list(df_snapshot.columns)
            priority_cols = [c for c in ['code', 'name', 'time', 'ticktime'] if c in all_cols]
            final_cols = priority_cols + [c for c in all_cols if c not in priority_cols]
            df_snapshot = df_snapshot[final_cols]
            
            self.detail_table.setModel(DataFrameModel(df_snapshot))
            self._connect_table_signals(self.detail_table, self.on_row_selection_linkage)
            self._smart_resize(self.detail_table)
            self.statusBar().showMessage(f"Query Result: {match_count} rows", 3000)
        elif not query_str:
            self.detail_table.setModel(DataFrameModel(pd.DataFrame()))
            self._connect_table_signals(self.detail_table, self.on_row_selection_linkage)
        else:
            self.detail_table.setModel(DataFrameModel(pd.DataFrame()))
            self._connect_table_signals(self.detail_table, self.on_row_selection_linkage)
            self.statusBar().showMessage("No matches found.", 3000)
            
        self.log("UI Sync complete. System ready.")

    def on_clear_query(self):
        """清空查询"""
        self.query_input.setPlainText("")
        # 🛡️ 增加：一并清空个股搜索框，确保“显示全部”
        if hasattr(self, 'search_input'):
            self.search_input.clear()
            
        self.on_apply_query()
        self.statusBar().showMessage("Query cleared. Showing full summary counts.", 3000)

    def on_filter(self, df_input=None):
        """处理搜索框输入，实时过滤股票摘要"""
        try:
            # 🛡️ 信号兼容性处理：如果从 search_input.textChanged 触发，df_input 会是 str，需忽略之
            if not isinstance(df_input, pd.DataFrame):
                df_input = None

            search_text = self.search_input.text().strip().upper()
            df = df_input if df_input is not None else self.get_queried_df()
            
            if df.empty:
                self.summary_table.setModel(DataFrameModel(pd.DataFrame(columns=['code', 'count'])))
                return
                
            if not search_text:
                self.update_summary(df)
            else:
                if 'name' in df.columns:
                    # [PERF] 重新计算过滤后的摘要，保持与 update_summary 逻辑一致
                    counts = df['code'].value_counts()
                    name_map = df[['code', 'name']].drop_duplicates('code').set_index('code')['name']
                    
                    summary = counts.to_frame(name='count')
                    summary['name'] = name_map
                    summary = summary.reset_index().rename(columns={'index': 'code'})
                    
                    summary = summary[(summary['code'].str.contains(search_text, regex=False)) | 
                                     (summary['name'].str.contains(search_text, regex=False, na=False))]
                    summary = summary[['code', 'name', 'count']]
                else:
                    # 快速计数
                    summary = df['code'].value_counts().reset_index()
                    summary.columns = ['code', 'count']
                    summary = summary[summary['code'].str.contains(search_text, regex=False)]
                
                summary = summary.sort_values('count', ascending=False)
                model = DataFrameModel(summary)
                self.summary_table.setModel(model)
                self._connect_table_signals(self.summary_table, self.on_summary_clicked)
                self._smart_resize(self.summary_table)
        except Exception as e:
            print(f"DEBUG: on_filter Error: {e}")

    def on_summary_clicked(self, index: QModelIndex):
        """处理摘要表选择变化，同步右侧详情"""
        if not index.isValid():
            return
        try:
            self._wait_voice_safe()
            model = index.model()
            if not isinstance(model, DataFrameModel):
                return
            
            # 🛡️ 优先通过列名定位 code，更健壮
            df_data = model._data
            if 'code' in df_data.columns:
                code = str(df_data.iloc[index.row()]['code'])
            else:
                code = str(df_data.iloc[index.row(), 0])
            
            df_full = self.active_df
            if df_full.empty:
                return

            if 'code' not in df_full.columns:
                detail_df = df_full.loc[[code]].copy()
            else:
                detail_df = df_full[df_full['code'] == code].copy()
            
            time_cols = [c for c in ['time', 'ticktime', 'timestamp'] if c in detail_df.columns]
            if time_cols:
                detail_df = detail_df.sort_values(time_cols[0], ascending=False)
            
            # 优先展示 code, name, time 等核心列
            all_cols = list(detail_df.columns)
            priority_cols = [c for c in ['code', 'name', 'time', 'ticktime'] if c in all_cols]
            final_cols = priority_cols + [c for c in all_cols if c not in priority_cols]
            detail_df = detail_df[final_cols]

            new_model = DataFrameModel(detail_df)
            self.detail_table.setModel(new_model)
            self._connect_table_signals(self.detail_table, self.on_row_selection_linkage)
            self._smart_resize(self.detail_table)
            
            QApplication.processEvents()
            self._execute_linkage(code, source="summary")
            
        except Exception as e:
            print(f"[ERROR] on_summary_clicked: {e}")

    def on_row_selection_linkage(self, index: QModelIndex):
        """通用表行选择联动"""
        if not index.isValid():
            return
        try:
            model = index.model()
            if isinstance(model, DataFrameModel):
                # 🛡️ 优先通过列名定位 code，更健壮
                df_data = model._data
                if 'code' in df_data.columns:
                    code = str(df_data.iloc[index.row()]['code'])
                else:
                    code = str(df_data.iloc[index.row(), 0])
                self._execute_linkage(code, source="table_nav")
        except Exception as e:
            print(f"DEBUG: on_row_selection_linkage error: {e}")

    def _execute_linkage(self, code, source=""):
        """跨进程联动核心逻辑"""
        if not code or self._select_code == str(code):
            return
            
        # 🛡️ 记录当前选中，确保状态同步
        self._select_code = str(code)

        if self.sender:
            try:
                self.sender.send(str(code))
            except Exception:
                pass
        
        if self.main_app and self.on_code_callback:
            try:
                if hasattr(self.main_app, 'tk_dispatch_queue'):
                    if self.main_app and getattr(self.main_app, "_vis_enabled_cache", False):
                        if hasattr(self.main_app, 'open_visualizer'):
                            self.main_app.tk_dispatch_queue.put(lambda: self.main_app.open_visualizer(str(code)))
                    self.main_app.tk_dispatch_queue.put(lambda: self.on_code_callback(str(code)))
                else:
                    self.on_code_callback(str(code))
            except Exception:
                pass


    def on_double_click(self, index: QModelIndex):
        """处理双击事件"""
        try:
            model = index.model()
            if isinstance(model, DataFrameModel):
                row_data = model._data.iloc[index.row()]
                code = str(row_data.get('code', row_data.iloc[0]))
                
                # [UNIFIED-LINKAGE] 使用统一联动逻辑
                self._execute_linkage(code, source="double_click")
                
                # 如果是从摘要表双击，额外触发一下右侧详情刷新
                if model is self.summary_table.model():
                    self.on_summary_clicked(index)
                    
        except Exception as e:
            print(f"[ERROR] on_double_click: {e}")
            import traceback
            traceback.print_exc()

    def on_diagnose_click(self):
        """点击诊断按钮或回车时的触发逻辑"""
        code = self.diag_input.text().strip()
        if not code:
            code = self._get_selected_code_from_tables()
            
        if not code:
            QMessageBox.warning(self, "警告", "请输入要诊断的股票代码，或在列表中选择一只股票！")
            return
        # 提取并补全6位代码
        code = "".join(x for x in code if x.isdigit()).zfill(6)
        self.diagnose_stock_strategy(code)

    def _get_selected_code_from_tables(self):
        """尝试从各个数据表中提取当前选中的股票代码"""
        for table in (self.summary_table, self.detail_table, self.full_results_table):
            if not table:
                continue
            selection_model = table.selectionModel()
            if not selection_model:
                continue
            index = selection_model.currentIndex()
            if index.isValid():
                model = index.model()
                if isinstance(model, DataFrameModel):
                    df_data = model._data
                    row = index.row()
                    if 0 <= row < len(df_data):
                        if 'code' in df_data.columns:
                            return str(df_data.iloc[row]['code'])
                        elif len(df_data.columns) > 0:
                            return str(df_data.iloc[row, 0])
        return ""

    def diagnose_stock_strategy(self, code, name=None):
        """诊断个股特征数据与查询条件匹配情况"""
        import re
        import pandas as pd
        
        code = str(code).strip().zfill(6)
        
        # 1. 尝试获取股票名称
        if not name:
            df = self.active_df
            if not df.empty and 'code' in df.columns:
                sub_df = df[df['code'] == code]
                if not sub_df.empty and 'name' in sub_df.columns:
                    name = sub_df.iloc[0]['name']
            if not name:
                try:
                    from JSONData import tdx_data_Day as tdd
                    name = tdd.get_name_code(code)
                except Exception:
                    name = "未知股票"
            if not name or name == "未知股票":
                name = "未知股票"
                
        # 2. 提取当前选中的策略与周期 (对于 K-line viewer，用户当前输入的 query 表达式)
        query_str = self.query_input.toPlainText().strip()
        queries = []
        if query_str:
            queries.append({
                "name": "当前查询过滤条件",
                "expr": query_str
            })
            
        # 3. 构造平铺该个股特征数据的单行 DataFrame
        df_full = self.active_df
        if df_full.empty:
            QMessageBox.warning(self, "警告", "当前没有加载任何数据，无法诊断！")
            return
            
        if 'code' not in df_full.columns:
            QMessageBox.warning(self, "警告", "数据结构中未找到 code 列，无法诊断！")
            return
            
        stock_df = df_full[df_full['code'] == code]
        if stock_df.empty:
            QMessageBox.warning(self, "警告", f"在当前数据中未找到个股 {code} 的记录，无法诊断！")
            return
            
        df_flat = stock_df.iloc[-1:].copy()
        df_flat.set_index('code', inplace=True, drop=False)
        
        # 4. 调用系统自带的 check_code 接口 (注意: parent 传 None，防止 PyQt/Tkinter 窗口冲突)
        try:
            from stock_logic_utils import check_code
            check_code(df_flat, code, queries, parent=None)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"调起股票检查报告失败: {e}")

    def setup_context_menus(self):
        """设置表格的右键上下文菜单"""
        for table in (self.summary_table, self.detail_table, self.full_results_table):
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(lambda pos, t=table: self.show_table_context_menu(pos, t))

    def show_table_context_menu(self, pos, table_view):
        """显示右键菜单"""
        index = table_view.indexAt(pos)
        if not index.isValid():
            return
            
        model = index.model()
        if not isinstance(model, DataFrameModel):
            return
            
        df_data = model._data
        row_idx = index.row()
        
        # 获取 code 和 name
        code = ""
        name = ""
        if 'code' in df_data.columns:
            code = str(df_data.iloc[row_idx]['code'])
        else:
            code = str(df_data.iloc[row_idx, 0])
            
        if 'name' in df_data.columns:
            name = str(df_data.iloc[row_idx]['name'])
            
        code = code.strip().zfill(6)
        if name:
            name = name.replace("★", "").replace("【重点】", "").strip()
            
        # [🚀 NEW] GlobalFavoriteManager 设为重点个股和取消重点个股选项
        is_fav = False
        fav_mgr = None
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            is_fav = code in fav_mgr.get_favorite_stocks()
        except Exception as e:
            print(f"[DEBUG] GlobalFavoriteManager load skip: {e}")
            
        menu = QMenu(self)
        
        # 1. 联动定位股票
        action_link = menu.addAction(f"📂 联动定位股票 ({code} {name})")
        action_link.triggered.connect(lambda: self._execute_linkage(code, source="right_click"))
        
        menu.addSeparator()
        
        # 2. 重点关注 Action
        if fav_mgr is not None:
            if is_fav:
                action_fav = menu.addAction("❌ 取消重点个股")
                action_fav.triggered.connect(lambda c=code: [fav_mgr.remove_favorite_stock(c), self.statusBar().showMessage(f"已取消重点个股: {c}", 2000)])
            else:
                action_fav = menu.addAction("⭐ 设为重点个股")
                action_fav.triggered.connect(lambda c=code: [fav_mgr.add_favorite_stock(c), self.statusBar().showMessage(f"已设为重点个股: {c}", 2000)])
            menu.addSeparator()
            
        # 3. 诊断个股 Action
        action_diag = menu.addAction(f"🔬 诊断个股数据 ({code} {name})")
        action_diag.triggered.connect(lambda: self.diagnose_stock_strategy(code, name))
        
        # 4. 运行回测 Action
        action_backtest = menu.addAction(f"🔍 运行 Re-entry 历史回测 ({code})")
        action_backtest.triggered.connect(lambda: self.run_reentry_backtest(code, name))
        
        menu.addSeparator()
        
        # 5. 复制代码 Action
        action_copy_code = menu.addAction("📋 复制代码")
        action_copy_code.triggered.connect(lambda: self.copy_code(code))
        
        # 6. 复制行信息 Action
        action_copy_row = menu.addAction("📝 复制行信息")
        action_copy_row.triggered.connect(lambda: self.copy_row_info(table_view, row_idx))
        
        menu.exec(table_view.viewport().mapToGlobal(pos))

    def run_reentry_backtest(self, code, name):
        """异步运行 Re-entry 历史回测"""
        # Create a progress dialog/message
        self._progress_dialog = QDialog(self)
        self._progress_dialog.setWindowTitle("📡 正在计算")
        self._progress_dialog.setFixedSize(320, 120)
        self._progress_dialog.setStyleSheet("""
            QDialog {
                background-color: #0c101b;
                color: white;
            }
            QLabel {
                color: #55ffff;
                font-weight: bold;
            }
        """)
        
        prog_layout = QVBoxLayout(self._progress_dialog)
        lbl_msg = QLabel(f"正在对 【{name} ({code})】\n进行 Re-entry 历史回测分析...")
        lbl_msg.setStyleSheet("font-size: 11pt; qproperty-alignment: AlignCenter;")
        prog_layout.addWidget(lbl_msg)
        
        lbl_status = QLabel("请稍候，抓取数据并计算特征...")
        lbl_status.setStyleSheet("color: #888888; font-size: 9pt; qproperty-alignment: AlignCenter;")
        prog_layout.addWidget(lbl_status)
        
        self._worker = BacktestWorker(code, name)
        self._worker.finished.connect(self.on_backtest_finished)
        self._worker.start()
        
        self._progress_dialog.exec()

    def on_backtest_finished(self, code, name, report):
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None
            
        dialog = BacktestReportQtDialog(self, code, name, report)
        dialog.exec()

    def copy_code(self, code):
        """复制代码到剪贴板"""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(code)
            self.statusBar().showMessage(f"已复制代码: {code}", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制代码失败: {e}")

    def copy_row_info(self, table_view, row_idx):
        """复制整行信息到剪贴板"""
        try:
            model = table_view.model()
            if not isinstance(model, DataFrameModel):
                return
            df = model._data
            if df.empty or row_idx >= len(df):
                return
            row = df.iloc[row_idx]
            row_str_parts = []
            for col in df.columns:
                val = row[col]
                row_str_parts.append(f"{col}:{val}")
            row_str = " | ".join(row_str_parts)
            
            clipboard = QApplication.clipboard()
            clipboard.setText(row_str)
            self.statusBar().showMessage(f"已复制行信息", 2000)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制行信息失败: {e}")

    def on_add_row(self):
        """在当前选中的代码下新增一行"""
        selection = self.summary_table.selectionModel().currentIndex()
        if not selection.isValid():
            self.statusBar().showMessage("Please select a stock in summary first.")
            return
            
        code = str(selection.model()._data.iloc[selection.row(), 0])
        df = self.active_df
        
        # 创建一个新行模版
        new_row = {col: 0.0 for col in df.columns}
        new_row['code'] = code
        new_row['time'] = datetime.now().timestamp()
        
        # 追加到活跃数据集
        self.active_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
        # 刷新当前显示
        self.on_summary_clicked(selection)
        self.statusBar().showMessage(f"Added new row for {code} in {'Memory' if self.is_memory_mode else 'File'} buffer.")

    def on_delete_row(self):
        """删除详情表中选中的行"""
        indexes = self.detail_table.selectionModel().selectedRows()
        if not indexes:
            self.statusBar().showMessage("Please select rows in detail table to delete.")
            return
            
        model = self.detail_table.model()
        if not isinstance(model, DataFrameModel):
            return
            
        df = self.active_df
        deleted_count = 0
        for idx in sorted(indexes, key=lambda x: x.row(), reverse=True):
            row_to_del = model._data.iloc[idx.row()]
            mask = (df['code'] == row_to_del['code']) & (df['time'] == row_to_del['time'])
            df = df.drop(df[mask].index)
            deleted_count += 1
            
        self.active_df = df
        # 刷新视图
        selection = self.summary_table.selectionModel().currentIndex()
        if selection.isValid():
            self.on_summary_clicked(selection)
            
        self.statusBar().showMessage(f"Deleted {deleted_count} rows from active buffer.")

    def on_save_changes(self):
        """保存更改到原始文件或内存"""
        df = self.active_df
        if df.empty:
            self.statusBar().showMessage("Nothing to save.")
            return

        try:
            if self.is_memory_mode:
                if not self.service_proxy:
                    self.statusBar().showMessage("Memory Mode: No service proxy found.")
                    return
                # 弹出确认框
                reply = QMessageBox.question(
                    self, 
                    "确认同步", 
                    "确定要同步更改到远程内存缓存中吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

                try:
                    self.statusBar().showMessage("Saving to remote memory cache...")
                    self.service_proxy.kline_cache.from_dataframe(df)
                    self.statusBar().showMessage("Successfully saved to Memory!")
                    QMessageBox.information(self, "同步成功", "更改已成功同步到内存缓存！")
                except Exception as e:
                    self.statusBar().showMessage(f"Save to Memory Failed: {e}")
                    QMessageBox.critical(self, "同步失败", f"同步到内存失败: {e}")
            else:
                if not self.current_file:
                    self.statusBar().showMessage("File Mode: No file path.")
                    return
                
                ext = os.path.splitext(self.current_file)[1].lower()
                
                # 弹出保存确认框并显示保存路径
                reply = QMessageBox.question(
                    self, 
                    "确认保存", 
                    f"确定要保存当前更改到以下文件吗？\n\n{self.current_file}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

                # 从配置文件中读取指定的压缩格式 (compression)
                config_ini = cct.get_ramdisk_path('h5config.txt') if cct else None
                if not config_ini:
                    config_ini = os.path.join(os.getcwd(), 'h5config.txt')
                cfg_compression = cct.get_config_value(config_ini, 'kline_viewer', xtype='compression', read=True) if cct else None
                if not cfg_compression:
                    cfg_compression = 'zstd' # 默认使用 zstd
                if str(cfg_compression).lower() == 'none':
                    cfg_compression = None

                if ext == ".pkl":
                    self.statusBar().showMessage(f"Saving to {self.current_file} ({cfg_compression} compressed)...")
                    df.to_pickle(self.current_file, compression=cfg_compression)
                    self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)} ({cfg_compression})!")
                elif ext == ".csv":
                    # 支持 CSV 格式压缩存储，如果 cfg_compression 属于 pandas to_csv 支持的压缩格式 (gzip, bz2, zip, xz)
                    csv_compression = cfg_compression if cfg_compression in ('gzip', 'bz2', 'zip', 'xz') else None
                    if csv_compression:
                        self.statusBar().showMessage(f"Saving to {self.current_file} ({csv_compression} compressed)...")
                        df.to_csv(self.current_file, index=False, compression=csv_compression)
                        self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)} ({csv_compression})!")
                    else:
                        self.statusBar().showMessage(f"Saving to {self.current_file}...")
                        df.to_csv(self.current_file, index=False)
                        self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)}!")
                elif ext in (".json", ".gz"):
                    # 支持 JSON / gzip 压缩存储
                    if ext == ".gz" or (cfg_compression in ('gzip', 'infer') and self.current_file.endswith('.gz')):
                        self.statusBar().showMessage(f"Saving to {self.current_file} (gzip compressed)...")
                        df.to_json(self.current_file, orient='records', force_ascii=False, indent=4, compression='gzip')
                    else:
                        self.statusBar().showMessage(f"Saving to {self.current_file}...")
                        df.to_json(self.current_file, orient='records', force_ascii=False, indent=4)
                    self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)}!")
                elif ext in (".h5", ".hdf5", ".hdf"):
                    h5_key = self.current_key if self.current_key else 'df'
                    self._save_and_repack_hdf5(self.current_file, df, h5_key)
                else:
                    # 兜底保存为 pickle
                    self.statusBar().showMessage(f"Saving to {self.current_file} ({cfg_compression} compressed)...")
                    df.to_pickle(self.current_file, compression=cfg_compression)
                    self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)} ({cfg_compression})!")

                QMessageBox.information(
                    self, 
                    "保存成功", 
                    f"更改已成功保存至文件：\n{self.current_file}"
                )
                
        except Exception as e:
            self.statusBar().showMessage(f"Save Failed: {e}")
            print(f"DEBUG: Save General Error: {e}")
            QMessageBox.critical(self, "错误", f"保存失败: {e}")

    def on_save_as(self):
        """将数据转存为新文件"""
        df = self.active_df
        if df.empty:
            self.statusBar().showMessage("Nothing to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "转存为新文件",
            self.current_file if self.current_file else os.getcwd(),
            "Pickle Files (*.pkl);;CSV Files (*.csv);;Session Files (*.json *.json.gz);;HDF5 Files (*.h5 *.hdf5 *.hdf);;All Files (*)"
        )

        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        # 如果保存为 HDF5，当原文件也是 HDF5 时，复制原文件以防丢失其他 table/key
        if ext in ('.h5', '.hdf5', '.hdf'):
            current_ext = os.path.splitext(self.current_file)[1].lower() if self.current_file else ''
            if current_ext in ('.h5', '.hdf5', '.hdf') and self.current_file and os.path.exists(self.current_file):
                import shutil
                if os.path.abspath(self.current_file) != os.path.abspath(file_path):
                    shutil.copy2(self.current_file, file_path)

        reply = QMessageBox.question(
            self, 
            "确认转存", 
            f"确定要将当前数据转存到以下路径吗？\n\n{file_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            config_ini = cct.get_ramdisk_path('h5config.txt') if cct else None
            if not config_ini:
                config_ini = os.path.join(os.getcwd(), 'h5config.txt')
            cfg_compression = cct.get_config_value(config_ini, 'kline_viewer', xtype='compression', read=True) if cct else None
            if not cfg_compression:
                cfg_compression = 'zstd'
            if str(cfg_compression).lower() == 'none':
                cfg_compression = None

            if ext == ".pkl":
                self.statusBar().showMessage(f"Saving to {file_path} ({cfg_compression} compressed)...")
                df.to_pickle(file_path, compression=cfg_compression)
                self.statusBar().showMessage(f"Successfully saved to {os.path.basename(file_path)} ({cfg_compression})!")
            elif ext == ".csv":
                csv_compression = cfg_compression if cfg_compression in ('gzip', 'bz2', 'zip', 'xz') else None
                if csv_compression:
                    self.statusBar().showMessage(f"Saving to {file_path} ({csv_compression} compressed)...")
                    df.to_csv(file_path, index=False, compression=csv_compression)
                    self.statusBar().showMessage(f"Successfully saved to {os.path.basename(file_path)} ({csv_compression})!")
                else:
                    self.statusBar().showMessage(f"Saving to {file_path}...")
                    df.to_csv(file_path, index=False)
                    self.statusBar().showMessage(f"Successfully saved to {os.path.basename(file_path)}!")
            elif ext in (".json", ".gz"):
                if file_path.endswith('.gz') or (cfg_compression in ('gzip', 'infer') and file_path.endswith('.gz')):
                    self.statusBar().showMessage(f"Saving to {file_path} (gzip compressed)...")
                    df.to_json(file_path, orient='records', force_ascii=False, indent=4, compression='gzip')
                else:
                    self.statusBar().showMessage(f"Saving to {file_path}...")
                    df.to_json(file_path, orient='records', force_ascii=False, indent=4)
                self.statusBar().showMessage(f"Successfully saved to {os.path.basename(file_path)}!")
            elif ext in ('.h5', '.hdf5', '.hdf'):
                h5_key = self.current_key if self.current_key else 'df'
                self._save_and_repack_hdf5(file_path, df, h5_key)
            else:
                self.statusBar().showMessage(f"Saving to {file_path} ({cfg_compression} compressed)...")
                df.to_pickle(file_path, compression=cfg_compression)
                self.statusBar().showMessage(f"Successfully saved to {os.path.basename(file_path)} ({cfg_compression})!")

            QMessageBox.information(
                self, 
                "转存成功", 
                f"更改已成功转存至新文件：\n{file_path}"
            )
            
            # 转存成功后，把当前活跃文件更新为转存后的文件
            self.current_file = file_path
            self.setWindowTitle(f"K-Line Backup Viewer - {os.path.basename(file_path)}")
            if file_path not in self.file_history:
                self.file_history.insert(0, file_path)
                self.save_history()

        except Exception as e:
            self.statusBar().showMessage(f"Save As Failed: {e}")
            print(f"DEBUG: Save As General Error: {e}")
            QMessageBox.critical(self, "错误", f"转存失败: {e}")

    def _save_and_repack_hdf5(self, file_path, df, h5_key):
        """
        保存 DataFrame 到 HDF5 并运行 ptrepack 进行重新打包压缩与清理减肥
        """
        self.statusBar().showMessage(f"Writing dataset '{h5_key}' to HDF5...")
        # 写入 HDF5 数据集
        df.to_hdf(file_path, key=h5_key)

        # 获取配置里的压缩格式信息
        config_ini = cct.get_ramdisk_path('h5config.txt') if cct else None
        if not config_ini:
            config_ini = os.path.join(os.getcwd(), 'h5config.txt')
        cfg_compression = cct.get_config_value(config_ini, 'kline_viewer', xtype='compression', read=True) if cct else None
        
        complib = 'zlib'
        if cfg_compression and str(cfg_compression).lower() != 'none':
            complib = str(cfg_compression).lower()

        # 准备执行 ptrepack 重新打包压缩与整理减肥
        temp_file = file_path + '_tmp'
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

        back_path = os.getcwd()
        basedir = os.path.dirname(os.path.abspath(file_path))
        fname_abs = os.path.abspath(file_path)
        temp_abs = os.path.abspath(temp_file)

        pt_success = False
        pt_msg = ""
        try:
            # 1. 备份原文件到 temp
            os.rename(fname_abs, temp_abs)

            # 2. 切换路径，生成相对路径以避免命令行中文空格报错
            os.chdir(basedir)
            temp_rel = os.path.relpath(temp_abs, basedir)
            fname_rel = os.path.relpath(fname_abs, basedir)

            # 3. 构造与 tdx_hdf5_api 内部完全对齐的 ptrepack 指令
            ptrepack_cmds = "ptrepack --overwrite-nodes --chunkshape=auto --alignment=1024 --complevel=9 --complib=%s %s %s"
            pt_cmd = ptrepack_cmds % (complib, temp_rel, fname_rel)
            self.statusBar().showMessage(f"Running HDF5 ptrepack compression ({complib})...")

            import subprocess
            p = subprocess.Popen(
                pt_cmd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            out = p.communicate()[0]
            pt_msg = out.decode('gbk', errors='ignore')

            # 如果首选的对齐对齐参数被当前 PyTables 报错（比如 unrecognized arguments: --alignment），则进行自动退避重试
            if p.returncode != 0 and ("unrecognized arguments" in pt_msg and "alignment" in pt_msg):
                self.statusBar().showMessage("ptrepack: '--alignment' unrecognized, retrying without alignment...")
                ptrepack_cmds_fallback = "ptrepack --overwrite-nodes --chunkshape=auto --complevel=9 --complib=%s %s %s"
                pt_cmd_fallback = ptrepack_cmds_fallback % (complib, temp_rel, fname_rel)
                p = subprocess.Popen(
                    pt_cmd_fallback, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                out = p.communicate()[0]
                pt_msg = out.decode('gbk', errors='ignore')

            if p.returncode == 0:
                pt_success = True
                if os.path.exists(temp_abs):
                    os.remove(temp_abs)
            else:
                raise RuntimeError(f"ptrepack failed: {pt_msg}")
        except Exception as e:
            # 发生任何异常，自动回滚重命名原文件，保证数据安全
            if os.path.exists(temp_abs) and not os.path.exists(fname_abs):
                try:
                    os.rename(temp_abs, fname_abs)
                except Exception:
                    pass
            raise e
        finally:
            os.chdir(back_path)

        if pt_success:
            self.statusBar().showMessage(f"Successfully saved and compressed HDF5 ({complib})!")
        else:
            self.statusBar().showMessage(f"Saved HDF5 without compression.")

    def on_read_table(self):
        """读取/切换当前 HDF5 文件中的其他数据集 (Table)"""
        if not self.current_file or not self.current_file.lower().endswith('.h5'):
            self.statusBar().showMessage("Only HDF5 files support table reading/switching.")
            return
        self.load_data(self.current_file)

    def on_delete_table(self):
        """删除 HDF5 文件中的特定数据集 (Table)"""
        if not self.current_file or not self.current_file.lower().endswith('.h5'):
            self.statusBar().showMessage("Only HDF5 files support table deletion.")
            return

        file_path = self.current_file
        try:
            # 1. 获取所有 Key (不直接加载数据，只读 metadata)
            with pd.HDFStore(file_path, "r") as store:
                keys = [k.strip("/") for k in store.keys()]
            
            if not keys:
                self.statusBar().showMessage("No datasets found in HDF5 file.")
                return

            # 2. 弹出选择框
            key, ok = QInputDialog.getItem(
                self,
                "Delete HDF5 Table",
                f"Choose table to DELETE from {os.path.basename(file_path)}:",
                keys,
                0,
                False
            )
            
            if not (ok and key):
                return

            # 3. 反复确认，防止误删 (HDF5 删除不可撤销)
            reply = QMessageBox.question(
                self, 'Confirm Deletion', 
                f"Are you sure you want to delete table '{key}'?\n\nThis will PERMANENTLY remove the data from the file.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return

            # 4. 执行删除操作
            self.statusBar().showMessage(f"Deleting table '{key}'...")
            with pd.HDFStore(file_path, "a") as store:
                if "/" + key in store.keys():
                    del store[key]
            
            self.log(f"HDF5 Table Deleted: {key} from {file_path}")
            self.statusBar().showMessage(f"Table '{key}' deleted successfully.")

            # 5. 如果删除的是当前正在查看的表，清理视图
            if key == self.current_key:
                self.current_key = None
                self.active_df = pd.DataFrame()
                self.df_file = pd.DataFrame()
                
                # 强制刷新 UI 到空状态
                empty = DataFrameModel(pd.DataFrame())
                self.summary_table.setModel(empty)
                self.detail_table.setModel(empty)
                self.full_results_table.setModel(empty)
                self.stats_label.setText(f"Table '{key}' was deleted. Please load another dataset.")
            
        except Exception as e:
            self.statusBar().showMessage(f"Delete Table Failed: {e}")
            self.log(f"Delete Table Error: {e}")

    def on_delete_by_time(self):
        """按时间或时间范围删除所有股票的该行数据
        支持:
        1. 单个 Unix 时间戳 (如 1767945960)
        2. 时间戳范围 (如 1767944700, 1767945960 或 1767945960 到 1767944700)
        3. 日期字符串 (如 2026-01-10 10:00:00)
        """
        raw_str = self.time_input.text().strip()
        if not raw_str:
            self.statusBar().showMessage("Please enter Unix timestamp or Range (Start, End)")
            return
            
        df = self.active_df
        if df.empty:
            self.statusBar().showMessage("Dataset is empty.")
            return

        if 'time' not in df.columns:
            self.statusBar().showMessage("Error: 'time' column not found.")
            return

        try:
            # 1. 尝试解析范围 (逗号, 短横线, 空格, 或 "到")
            # 过滤掉空的 parts
            parts = [p.strip() for p in re.split(r'[, \-到|]+', raw_str) if p.strip()]
            
            mask = None
            desc = ""
            
            if len(parts) >= 2:
                # 范围模式
                t1 = parts[0]
                t2 = parts[1]
                
                try:
                    ts1 = float(t1)
                    ts2 = float(t2)
                    start_ts, end_ts = min(ts1, ts2), max(ts1, ts2)
                    mask = (df['time'] >= start_ts) & (df['time'] <= end_ts)
                    desc = f"range {start_ts} to {end_ts}"
                except ValueError:
                    self.statusBar().showMessage("Range mode only supports Unix timestamps.")
                    return
            else:
                # 2. 单个值模式
                val = raw_str
                try:
                    # 2a. 尝试作为 UnixTS
                    target_ts = float(val)
                    mask = df['time'] == target_ts
                    if not (isinstance(mask, pd.Series) and mask.any()):
                        mask = df['time'].astype(int) == int(target_ts)
                    desc = f"timestamp {target_ts}"
                except ValueError:
                    # 2b. 尝试作为日期字符串
                    try:
                        dt = datetime.strptime(val, '%Y-%m-%d %H:%M:%S')
                        target_ts = dt.timestamp()
                        mask = df['time'] == target_ts
                        if not (isinstance(mask, pd.Series) and mask.any()):
                            mask = df['time'].astype(int) == int(target_ts)
                        desc = f"time {val}"
                    except ValueError:
                        self.statusBar().showMessage("Invalid format. Use UnixTS or YYYY-MM-DD HH:MM:SS")
                        return

            if mask is None:
                return

            # 执行删除
            before_count = len(df)
            # 显式转换为 bool 序列，避免潜在的类型问题
            final_mask = mask.fillna(False).astype(bool)
            updated_df = df[~final_mask].copy() 
            self.active_df = updated_df
            after_count = len(updated_df)
            
            del_count = before_count - after_count
            if del_count > 0:
                self.statusBar().showMessage(f"Deleted {del_count} rows for {desc}")
                # 刷新视图
                self.update_summary()
                self.on_filter()
                self.detail_table.setModel(DataFrameModel(pd.DataFrame(columns=df.columns)))
            else:
                self.statusBar().showMessage(f"No records found for {desc}")
                
        except Exception as e:
            self.statusBar().showMessage(f"Delete Failed: {e}")
            print(f"DEBUG: Delete by Time Error: {e}")

    def _load_session_json(self, file_path: str) -> pd.DataFrame:
        """解析 bidding_session_data.json.gz 或 json 格式"""
        try:
            if file_path.endswith('.gz'):
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            # 转换为 DataFrame
            rows = []
            stock_scores = data.get('stock_scores', {})
            momentum_scores = data.get('momentum_scores', {})
            watchlist = data.get('watchlist', {})
            sector_data = data.get('sector_data', {})
            meta_data = data.get('meta_data', {})
            
            # [FALLBACK] 从本地 selection_log.csv 加载名称与形态作为补充
            fallback_meta = {}
            try:
                local_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selection_log.csv")
                if os.path.exists(local_csv):
                    f_df = pd.read_csv(local_csv)
                    if 'code' in f_df.columns:
                        f_df['code'] = f_df['code'].astype(str).str.zfill(6)
                        if 'date' in f_df.columns:
                            f_df = f_df.sort_values('date', ascending=False)
                        f_df = f_df.drop_duplicates('code')
                        for r in f_df.itertuples():
                            fallback_meta[r.code] = {
                                'name': getattr(r, 'name', ''),
                                'reason': getattr(r, 'reason', '')
                            }
            except Exception:
                pass

            # 并联所有个股信息
            all_codes = set(stock_scores.keys()) | set(momentum_scores.keys()) | set(watchlist.keys()) | set(meta_data.keys())
            
            # 建立板块反向映射 code -> [sectors]
            code_to_sectors = {}
            for sector, info in sector_data.items():
                leader = info.get('leader')
                followers = info.get('followers', [])
                if leader:
                    code_to_sectors.setdefault(leader, []).append(f"{sector}(L)")
                for f in followers:
                    code_to_sectors.setdefault(f, []).append(sector)

            for code in all_codes:
                w_info = watchlist.get(code, {})
                m_info = meta_data.get(code, {})
                f_info = fallback_meta.get(code, {})
                
                # 优先级：关注池 > 会话元数据 > 本地历史日志
                final_name = w_info.get('name') or m_info.get('name') or f_info.get('name') or ''
                final_pattern = w_info.get('pattern_hint') or m_info.get('reason') or f_info.get('reason') or ''

                rows.append({
                    'code': code,
                    'name': final_name,
                    'score': stock_scores.get(code, 0.0),
                    'momentum': momentum_scores.get(code, 0.0),
                    'watchlist': 1 if code in watchlist else 0,
                    'reason': w_info.get('reason', ''),
                    'pattern': final_pattern,
                    'sectors': ",".join(code_to_sectors.get(code, [])),
                    'time': os.path.getmtime(file_path),
                    'type': 'SESSION'
                })
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows)
            # 排序：有分数的排前面
            if not df.empty:
                df.sort_values(['score', 'momentum'], ascending=False, inplace=True)
            return df
            
        except Exception as e:
            print(f"Error parsing session JSON: {e}")
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"JSON Parse Error: {e}")
            return pd.DataFrame()

    def on_file_history_selected(self, index):
        """文件历史切换"""
        if index <= 0:
            return
        path = self.file_history_combo.currentText()
        if os.path.exists(path):
            self.load_data(path)
            if self.source_combo.currentText() != "File":
                self.source_combo.setCurrentText("File")

    def on_query_history_selected(self, index):
        """查询历史切换"""
        if index <= 0 or index - 1 >= len(self.query_history):
            return
            
        full_query = self.query_history[index - 1]
        self.query_input.setPlainText(full_query)
        
        # [UI SYNC] 设置标记，防止刷新时导致列表重排，保持当前索引稳定
        self._is_loading_from_history = True
        try:
            self.on_apply_query() 
            # 选中后，让下拉框停留在当前索引，方便删除
            self.query_history_combo.blockSignals(True)
            self.query_history_combo.setCurrentIndex(index)
            self.query_history_combo.blockSignals(False)
        finally:
            self._is_loading_from_history = False
        
        self.statusBar().showMessage("History query loaded and executed.", 3000)

    def on_delete_query_history(self):
        """删除当前选中的查询历史记录"""
        idx = self.query_history_combo.currentIndex()
        if idx <= 0:
            return
            
        query_idx = idx - 1
        if 0 <= query_idx < len(self.query_history):
            self.query_history.pop(query_idx)
            self.save_history()
            self._update_history_combos()
            self.statusBar().showMessage("Query history item removed.", 3000)

    def on_repair_h5_clicked(self):
        """点击修复合并 HDF5 按钮"""
        default_base = self.current_file if (self.current_file and self.current_file.endswith(('.h5', '.hdf5'))) else None
        dialog = H5MergeRepairDialog(self, default_base_file=default_base)
        dialog.exec()


class H5MergeRepairDialog(QDialog):
    def __init__(self, parent=None, default_base_file=None):
        super().__init__(parent)
        self.setWindowTitle("HDF5 数据修复与去重合并")
        self.resize(650, 520)
        self.init_ui(default_base_file)

    def init_ui(self, default_base_file):
        layout = QVBoxLayout(self)

        # 提示信息
        tip_label = QLabel("本工具用于将【干净的基础历史 HDF5 文件】与【今日追加的 HDF5 新数据】进行去重合并，并自动排除已损坏或被污染的数据（如 07-06）。")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        layout.addWidget(tip_label)

        # 表单布局
        form = QFormLayout()

        # 1. 基础历史数据文件
        self.base_edit = QLineEdit()
        # 默认填入
        default_base = default_base_file or r"D:\Ramdisk\backup\20260703\sina_MultiIndex_data.h5"
        if not os.path.exists(default_base):
            # 自动退避尝试 20260702
            alt_base = r"D:\Ramdisk\backup\20260702\sina_MultiIndex_data.h5"
            if os.path.exists(alt_base):
                default_base = alt_base
        self.base_edit.setText(default_base)
        
        base_btn = QPushButton("浏览...")
        base_btn.clicked.connect(self.browse_base)
        base_row = QHBoxLayout()
        base_row.addWidget(self.base_edit)
        base_row.addWidget(base_btn)
        form.addRow("源数据 (基础历史文件):", base_row)

        # 2. 追加的新数据文件
        self.new_edit = QLineEdit()
        self.new_edit.setText(r"g:\sina_MultiIndex_data.h5")
        new_btn = QPushButton("浏览...")
        new_btn.clicked.connect(self.browse_new)
        new_row = QHBoxLayout()
        new_row.addWidget(self.new_edit)
        new_row.addWidget(new_btn)
        form.addRow("新数据 (追加日新文件):", new_row)

        # 3. HDF5 Key
        self.key_edit = QLineEdit()
        self.key_edit.setText("/all_30")
        form.addRow("目标数据集 Key:", self.key_edit)

        # 4. 追加过滤起始时间
        self.date_edit = QLineEdit()
        # 默认使用今天日期
        self.date_edit.setText(datetime.now().strftime("%Y-%m-%d"))
        form.addRow("新数据追加起始日期 (含):", self.date_edit)

        # 日期快捷选择与范围检测
        self.lbl_date_range = QLabel("新数据日期范围: 未检测")
        self.lbl_date_range.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        
        self.btn_detect_date = QPushButton("检测日期")
        self.btn_detect_date.setFixedWidth(80)
        self.btn_detect_date.clicked.connect(self.detect_new_file_dates)
        
        self.combo_dates = QComboBox()
        self.combo_dates.setFixedWidth(150)
        self.combo_dates.addItem("-- 选择历史日期 --")
        self.combo_dates.currentIndexChanged.connect(self.on_date_combo_changed)
        
        date_opt_layout = QHBoxLayout()
        date_opt_layout.addWidget(self.lbl_date_range)
        date_opt_layout.addWidget(self.btn_detect_date)
        date_opt_layout.addWidget(self.combo_dates)
        form.addRow("检测/选择新数据日期:", date_opt_layout)

        # 5. 保存的目标文件路径
        self.target_edit = QLineEdit()
        # 自动关联更新临时输出文件名以防止覆盖源文件
        self.new_edit.textChanged.connect(self.update_target_temp_path)
        self.base_edit.textChanged.connect(self.update_target_temp_path)
        self.update_target_temp_path()
        
        target_btn = QPushButton("浏览...")
        target_btn.clicked.connect(self.browse_target)
        target_row = QHBoxLayout()
        target_row.addWidget(self.target_edit)
        target_row.addWidget(target_btn)
        form.addRow("目标输出文件路径:", target_row)

        layout.addLayout(form)

        # 日志区
        layout.addWidget(QLabel("合并运行日志:"))
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #2c3e50; color: #ecf0f1; font-family: Consolas;")
        layout.addWidget(self.log_text)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("开始合并修复")
        self.run_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; height: 30px;")
        self.run_btn.clicked.connect(self.run_merge)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_btn.setStyleSheet("height: 30px;")
        
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def get_existing_dir_or_parent(self, path: str) -> str:
        """从给定路径自动提取已存在的目录，若不存在则逐级向上查找直到找到存在的路径"""
        if not path:
            return ""
        try:
            path = os.path.abspath(path.strip())
            # 如果是已存在的文件，取其目录
            if os.path.exists(path) and os.path.isfile(path):
                curr_dir = os.path.dirname(path)
            else:
                # 尝试看它是不是潜在文件路径（有后缀名）
                _, ext = os.path.splitext(os.path.basename(path))
                if ext:
                    curr_dir = os.path.dirname(path)
                else:
                    curr_dir = path
            
            # 逐级向上查找直到目录真实存在
            while curr_dir:
                if os.path.exists(curr_dir) and os.path.isdir(curr_dir):
                    return curr_dir
                parent = os.path.dirname(curr_dir)
                if parent == curr_dir: # 到达盘符根目录
                    break
                curr_dir = parent
        except Exception:
            pass
        return ""

    def browse_base(self):
        init_path = self.base_edit.text().strip()
        init_dir = self.get_existing_dir_or_parent(init_path)
        f, _ = QFileDialog.getOpenFileName(self, "选择源数据 (基础历史文件)", init_dir, "HDF5 Files (*.h5 *.hdf5)")
        if f:
            self.base_edit.setText(f)

    def browse_new(self):
        init_path = self.new_edit.text().strip()
        init_dir = self.get_existing_dir_or_parent(init_path)
        f, _ = QFileDialog.getOpenFileName(self, "选择新数据 (追加文件)", init_dir, "HDF5 Files (*.h5 *.hdf5)")
        if f:
            self.new_edit.setText(f)

    def browse_target(self):
        init_path = self.target_edit.text().strip()
        init_dir = self.get_existing_dir_or_parent(init_path)
        
        # 尽量保留文件名，若直接父目录不存在则回退至已存在的祖先目录
        init_val = init_path
        if init_path:
            parent_dir = os.path.dirname(os.path.abspath(init_path))
            if not os.path.exists(parent_dir):
                init_val = init_dir
                
        f, _ = QFileDialog.getSaveFileName(self, "选择目标输出文件", init_val, "HDF5 Files (*.h5 *.hdf5)")
        if f:
            self.target_edit.setText(f)

    def update_target_temp_path(self):
        """当基础历史文件或追加新数据文件变化时，自动智能生成一个临时合并输出文件名以防止覆盖损坏源文件"""
        new_path = self.new_edit.text().strip()
        if new_path:
            try:
                dir_name = os.path.dirname(os.path.abspath(new_path))
                base_name = os.path.basename(new_path)
                name, ext = os.path.splitext(base_name)
                temp_name = f"{name}_temp_merge{ext}"
                target_val = os.path.join(dir_name, temp_name)
                
                curr_target = self.target_edit.text().strip()
                # 只有当当前为空，或者直接指向源数据，或者本来就是一个临时名时，才动态更新以贴合新路径
                if not curr_target or curr_target == new_path or curr_target == self.base_edit.text().strip() or "_temp_merge" in curr_target:
                    self.target_edit.setText(target_val)
            except Exception:
                pass

    def detect_new_file_dates(self):
        new_path = self.new_edit.text().strip()
        h5_key = self.key_edit.text().strip()
        if not new_path or not os.path.exists(new_path):
            QMessageBox.warning(self, "警告", "请先选择有效的新数据文件路径！")
            return
        if not h5_key:
            QMessageBox.warning(self, "警告", "请先填写数据集 Key！")
            return
            
        self.btn_detect_date.setEnabled(False)
        self.btn_detect_date.setText("检测中...")
        QApplication.processEvents()
        
        try:
            # 使用只读模式加载索引，避免引起多进程死锁或大内存分配
            with pd.HDFStore(new_path, mode='r') as store:
                if h5_key not in store:
                    QMessageBox.warning(self, "警告", f"新数据文件中不存在 Key: {h5_key}")
                    return
                # 仅选择索引加载
                df_idx = store.select(h5_key, columns=[])
                
            times = pd.to_datetime(df_idx.index.get_level_values('ticktime')).dropna()
            # 向量化去除时间分量并去重，转换为 Timestamp 序列
            unique_ts = times.normalize().unique()
            # 提取具体的 date 对象并完成排序，完美规避 NaT 比较的 FutureWarning
            unique_dates = sorted([t.date() for t in unique_ts])
            
            if unique_dates:
                min_date = unique_dates[0]
                max_date = unique_dates[-1]
                self.lbl_date_range.setText(f"范围: {min_date} 至 {max_date}")
                
                # 更新选择下拉框
                self.combo_dates.blockSignals(True)
                self.combo_dates.clear()
                self.combo_dates.addItem("-- 选择历史日期 --")
                for d in unique_dates:
                    self.combo_dates.addItem(str(d))
                self.combo_dates.blockSignals(False)
                
                # 默认设为最新的最后一天日期作为追加开始时间
                self.date_edit.setText(str(max_date))
                QMessageBox.information(self, "检测成功", f"成功检测到新数据日期范围:\n{min_date} 至 {max_date}\n共 {len(unique_dates)} 个交易日。")
            else:
                self.lbl_date_range.setText("范围: 无有效日期")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"检测新数据文件日期范围失败: {e}")
        finally:
            self.btn_detect_date.setEnabled(True)
            self.btn_detect_date.setText("检测日期")

    def on_date_combo_changed(self, idx):
        if idx > 0:
            date_str = self.combo_dates.currentText()
            self.date_edit.setText(date_str)

    def append_log(self, text):
        self.log_text.appendPlainText(text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        QApplication.processEvents() # 刷新UI界面，不阻塞

    def run_merge(self):
        import time
        import shutil
        
        base_path = self.base_edit.text().strip()
        new_path = self.new_edit.text().strip()
        target_path = self.target_edit.text().strip()
        h5_key = self.key_edit.text().strip()
        start_date = self.date_edit.text().strip()

        if not base_path or not os.path.exists(base_path):
            QMessageBox.warning(self, "警告", "源数据基础文件路径无效或不存在！")
            return
        if not new_path or not os.path.exists(new_path):
            QMessageBox.warning(self, "警告", "追加的新数据文件路径无效或不存在！")
            return
            
        # 强防数据覆盖安全卡口
        if target_path == base_path or target_path == new_path:
            QMessageBox.critical(self, "安全警告", "目标输出文件路径与源数据（基础历史文件）或新数据（追加文件）相同！\n为防止重要历史数据被意外覆盖损坏，请指定一个不同的目标文件名（例如在原文件名后加上 _temp_merge.h5 后缀）。")
            return
        if not target_path:
            QMessageBox.warning(self, "警告", "必须指定目标输出路径！")
            return
        if not h5_key:
            QMessageBox.warning(self, "警告", "必须指定数据集 Key！")
            return

        self.run_btn.setEnabled(False)
        self.log_text.clear()
        
        try:
            self.append_log("=" * 60)
            self.append_log("开始进行 HDF5 历史数据去重合并流程")
            self.append_log("=" * 60)
            
            # Step 1: 读取基础文件
            self.append_log(f"1. 正在读取基础历史文件: {base_path} ...")
            t0 = time.time()
            df_base = pd.read_hdf(base_path, key=h5_key)
            self.append_log(f"   读取成功: {len(df_base)} 行, 耗时 {time.time()-t0:.1f} 秒")
            
            times_base = pd.to_datetime(df_base.index.get_level_values('ticktime'))
            self.append_log(f"   基础历史日期范围: {times_base.min().date()} ~ {times_base.max().date()}")

            # Step 2: 读取新追加文件
            self.append_log(f"\n2. 正在读取新追加文件: {new_path} ...")
            t0 = time.time()
            df_new = pd.read_hdf(new_path, key=h5_key)
            self.append_log(f"   读取成功: {len(df_new)} 行, 耗时 {time.time()-t0:.1f} 秒")

            # Step 3: 进行过滤
            self.append_log(f"\n3. 正在过滤数据，保留日期 >= {start_date} ...")
            times_new = pd.to_datetime(df_new.index.get_level_values('ticktime'))
            mask_keep = times_new >= pd.Timestamp(start_date)
            df_new_clean = df_new[mask_keep]
            
            self.append_log(f"   追加数据中保留: {len(df_new_clean)} 行")
            if not df_new_clean.empty:
                t2 = pd.to_datetime(df_new_clean.index.get_level_values('ticktime'))
                self.append_log(f"   保留的数据日期范围: {t2.min().date()} ~ {t2.max().date()}")

            # Step 4: 合并与去重
            self.append_log("\n4. 正在对合并的数据进行去重与索引排序 ...")
            t0 = time.time()
            combined = pd.concat([df_base, df_new_clean], axis=0)
            before_len = len(combined)
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()
            after_len = len(combined)
            self.append_log(f"   合并去重完成: 合并前 {before_len} 行 -> 合并后 {after_len} 行 (去重掉 {before_len-after_len} 行重复)")
            self.append_log(f"   去重排序耗时 {time.time()-t0:.1f} 秒")

            times_all = pd.to_datetime(combined.index.get_level_values('ticktime'))
            self.append_log(f"   合并后总日期范围: {times_all.min().date()} ~ {times_all.max().date()}")

            # Step 5: 写入目标输出文件
            temp_target = target_path + ".tmp_merge"
            if os.path.exists(temp_target):
                os.remove(temp_target)
            
            self.append_log(f"\n5. 正在写入临时文件: {temp_target} ...")
            t0 = time.time()
            combined.to_hdf(temp_target, key=h5_key, mode='w', format='table', 
                            complevel=9, complib='blosc', data_columns=True)
            self.append_log(f"   写入成功! 大小: {os.path.getsize(temp_target)/1024/1024:.1f} MB, 耗时 {time.time()-t0:.1f} 秒")

            # Step 6: 验证物理写入
            self.append_log("\n6. 正在验证写入的 HDF5 文件 ...")
            with pd.HDFStore(temp_target, mode='r') as store:
                nrows = store.get_storer(h5_key).nrows
                self.append_log(f"   已验证 Key '{h5_key}' 包含: {nrows} 行")

            # Step 7: 安全替换
            self.append_log(f"\n7. 执行安全物理替换 => {target_path}")
            if os.path.exists(target_path):
                backup_path = target_path + ".bak_repair_ts" + str(int(time.time()))
                try:
                    os.rename(target_path, backup_path)
                    self.append_log(f"   成功备份旧文件至: {backup_path}")
                except Exception as e:
                    self.append_log(f"   [警告] 备份原目标文件失败 (可能正被占用): {e}")
                    raise e
            
            shutil.copy2(temp_target, target_path)
            if os.path.exists(temp_target):
                os.remove(temp_target)
                
            self.append_log("\n" + "=" * 60)
            self.append_log("恭喜！HDF5 数据合并修复流程全部成功完成！")
            self.append_log("=" * 60)
            QMessageBox.information(self, "成功", f"HDF5 合并修复成功！已替换目标文件:\n{target_path}")
            
        except Exception as e:
            self.append_log(f"\n[错误] 合并修复流程中断: {e}")
            QMessageBox.critical(self, "错误", f"合并修复失败，堆栈异常:\n{e}")
        finally:
            self.run_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set style for modern look (vibrant colors)
    app.setStyle("Fusion")
    
    viewer = KlineBackupViewer()
    viewer.show()
    sys.exit(app.exec())
