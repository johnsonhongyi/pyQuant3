import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

from typing import Optional, Any, Callable, Dict

# Handle multiple Qt bindings (PyQt6, PySide6, PyQt5)
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                 QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                 QLabel, QFileDialog, QSplitter)
    from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
    from PyQt6.QtGui import QIcon, QFont
except ImportError:
    try:
        from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                     QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                     QLabel, QFileDialog, QSplitter)
        from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
        from PySide6.QtGui import QIcon, QFont
    except ImportError:
        try:
            from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                         QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                         QLabel, QFileDialog, QSplitter)
            from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex
            from PyQt5.QtGui import QIcon, QFont
        except ImportError:
            try:
                from PySide2.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                             QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                             QLabel, QFileDialog, QSplitter)
                from PySide2.QtCore import Qt, QAbstractTableModel, QModelIndex
                from PySide2.QtGui import QIcon, QFont
            except ImportError:
                print("Please install PyQt6, PySide6, PyQt5 or PySide2 to run this tool.")
                sys.exit(1)

# try to import commonTips for path resolution
try:
    from JohnsonUtil import commonTips as cct
except ImportError:
    cct = None

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
            if role == _DisplayRole:
                try:
                    col_name = self._data.columns[index.column()]
                    val = self._data.iloc[index.row(), index.column()]
                    
                    # Time Formatting
                    if col_name.lower() in ('time', 'timestamp'):
                        try:
                            ts = float(val)
                            if ts > 1000000000:
                                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            pass

                    if isinstance(val, (float, np.float64)):
                        return f"{val:.2f}"

                    return str(val)
                except Exception:
                    return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == _Horizontal and role == _DisplayRole:
            return self._data.columns[col]
        return None

    def sort(self, column, order):
        """Sort table by given column number."""
        try:
            col_name = self._data.columns[column]
            self.layoutAboutToBeChanged.emit()
            self._data = self._data.sort_values(
                by=col_name, 
                ascending=(order == Qt.SortOrder.AscendingOrder)
            )
            self.layoutChanged.emit()
        except Exception as e:
            print(f"Sort Error: {e}")

class KlineBackupViewer(QMainWindow):
    def __init__(self, on_code_callback: Optional[Callable[[str], Any]] = None, service_proxy: Any = None, last6vol_map: Optional[Dict[str, float]] = None):
        super().__init__()
        self.on_code_callback = on_code_callback
        self.service_proxy = service_proxy # RealtimeDataService proxy
        self.last6vol_map = last6vol_map if last6vol_map is not None else {}

        self.current_file: Optional[str] = None
        self.is_memory_mode: bool = False
        self.setWindowTitle("Minute Kline Cache Viewer (Realtime Service)")
        self.resize(1000, 700)
        
        self.df_all = pd.DataFrame()
        self.df_display = pd.DataFrame()
        
        self.setup_ui()
        self.auto_load()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.btn_open = QPushButton("Open File")
        self.btn_open.clicked.connect(self.on_open_file)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.on_refresh)
        
        self.btn_mem = QPushButton("Memory View")
        self.btn_mem.clicked.connect(self.on_memory_sync)
        if self.service_proxy:
            self.btn_mem.setEnabled(True)
            self.btn_mem.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        else:
            self.btn_mem.setEnabled(False)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter Stock Code...")
        self.search_input.textChanged.connect(self.on_filter)
        
        toolbar_layout.addWidget(self.btn_open)
        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addWidget(self.btn_mem)
        toolbar_layout.addWidget(QLabel("Search Code:"))
        toolbar_layout.addWidget(self.search_input)
        
        main_layout.addLayout(toolbar_layout)

        # Stats Label
        self.stats_label = QLabel("No data loaded. Please open a minute_kline_cache.pkl file.")
        self.stats_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(self.stats_label)

        # Splitter for Summary and Details
        splitter = QSplitter(_Vertical)
        
        # Summary Table (Grouped by code)
        self.summary_table = QTableView()
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.setSelectionBehavior(_SelectRows)
        self.summary_table.setSortingEnabled(True)
        self.summary_table.clicked.connect(self.on_summary_clicked)
        self.summary_table.doubleClicked.connect(self.on_double_click)
        
        # Detail Table
        self.detail_table = QTableView()
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setSelectionBehavior(_SelectRows)
        self.detail_table.setSortingEnabled(True)
        self.detail_table.doubleClicked.connect(self.on_double_click)
        
        splitter.addWidget(self.summary_table)
        splitter.addWidget(self.detail_table)
        
        main_layout.addWidget(splitter, 1)

        self.statusBar().showMessage("Ready")

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

    def on_open_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Cache File", "", "Pickle Files (*.pkl);;All Files (*)")
        if file_name:
            self.load_data(file_name)

    def on_refresh(self):
        if self.is_memory_mode:
            self.on_memory_sync()
        elif hasattr(self, 'current_file') and self.current_file and os.path.exists(self.current_file):
            self.load_data(self.current_file)

    def on_memory_sync(self):
        """直接从内存中的 realtime_service 读取最新快照"""
        if not self.service_proxy:
            self.statusBar().showMessage("Realtime Service not connected.")
            return
            
        try:
            self.statusBar().showMessage("Pulling snapshot from memory...")
            self.is_memory_mode = True
            
            # 这里调用 DataPublisher 或 MinuteKlineCache 的 to_dataframe
            # 假设 service_proxy 内部是通过 kline_cache 公开的
            df = self.service_proxy.get_55188_data().get('df_klines', pd.DataFrame())
            if df.empty:
                # 备选方案：如果上面的 API 没公开，尝试直接访问 kline_cache (如果是 Manager 代理)
                try:
                    df = self.service_proxy.kline_cache.to_dataframe()
                except:
                    pass

            if df.empty:
                self.statusBar().showMessage("Memory Cache is currently empty.")
                return

            self.df_all = df
            self.update_summary()
            self.on_filter()
            
            stock_count = len(df['code'].unique())
            total_nodes = len(df)
            
            self.stats_label.setText(
                f"🧠 MODE: REALTIME MEMORY | Stocks: {stock_count} | Total Nodes: {total_nodes}\n"
                f"Data synchronized at: {datetime.now().strftime('%H:%M:%S')}"
            )
            self.statusBar().showMessage("Memory data synchronized.")
        except Exception as e:
            self.statusBar().showMessage(f"Memory Sync Failed: {e}")

    def load_data(self, file_path):
        try:
            self.current_file = file_path
            self.statusBar().showMessage(f"Loading {file_path}...")
            
            df = pd.read_pickle(file_path)
            if df is None or df.empty:
                self.stats_label.setText(f"File {file_path} is empty.")
                return

            self.df_all = df
            self.update_summary()
            self.on_filter()
            
            mtime = os.path.getmtime(file_path)
            time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            stock_count = len(df['code'].unique())
            total_nodes = len(df)
            
            # calculate fingerprint for display
            try:
                from cache_utils import df_fingerprint
                fp = df_fingerprint(df, cols=['code', 'time', 'close', 'volume'])
            except ImportError:
                fp = "N/A (cache_utils not found)"

            self.stats_label.setText(
                f"📊 File: {os.path.basename(file_path)} | Last Modified: {time_str} | "
                f"Stocks: {stock_count} | Total Nodes: {total_nodes}\n"
                f"🔑 Fingerprint (MD5): {fp}"
            )
            self.statusBar().showMessage("Data loaded successfully.")
            
        except Exception as e:
            self.stats_label.setText(f"Error loading data: {e}")
            self.statusBar().showMessage("Error loading data.")

    def update_summary(self):
        if self.df_all.empty:
            return
            
        summary = self.df_all.groupby('code').size().reset_index(name='count')
        # Add basic info
        summary = summary.sort_values('count', ascending=False)
        
        model = DataFrameModel(summary)
        self.summary_table.setModel(model)

    def on_filter(self):
        search_text = self.search_input.text().strip()
        if self.df_all.empty:
            return
            
        if not search_text:
            self.update_summary()
        else:
            summary = self.df_all.groupby('code').size().reset_index(name='count')
            summary = summary[summary['code'].str.contains(search_text)]
            summary = summary.sort_values('count', ascending=False)
            model = DataFrameModel(summary)
            self.summary_table.setModel(model)

    def on_summary_clicked(self, index: QModelIndex):
        if self.df_all.empty:
            return
            
        model = index.model()
        if isinstance(model, DataFrameModel):
            # 假设代码在第一列
            code = str(model._data.iloc[index.row(), 0])
            detail_df = self.df_all[self.df_all['code'] == code].copy()
            if 'time' in detail_df.columns:
                detail_df = detail_df.sort_values('time', ascending=False)
            
            # Calculate vol_ratio
            if hasattr(self, 'last6vol_map') and code in self.last6vol_map:
                l6v = self.last6vol_map[code]
                if l6v > 0:
                    minute_avg_vol = l6v / 240
                    if 'volume' in detail_df.columns:
                         detail_df['vol_ratio'] = detail_df['volume'] / minute_avg_vol

            new_model = DataFrameModel(detail_df)
            self.detail_table.setModel(new_model)
            self.detail_table.resizeColumnsToContents()

    def on_double_click(self, index: QModelIndex):
        if self.df_all.empty:
            return
            
        model = index.model()
        if isinstance(model, DataFrameModel):
            row_data = model._data.iloc[index.row()]
            code = str(row_data.get('code', row_data.iloc[0]))
            
            if self.on_code_callback:
                self.on_code_callback(code)
            else:
                print(f"Double-clicked code: {code}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set style for modern look (vibrant colors)
    app.setStyle("Fusion")
    
    viewer = KlineBackupViewer()
    viewer.show()
    sys.exit(app.exec())
