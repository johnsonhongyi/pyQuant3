import sys
import os
import re
import pandas as pd
import numpy as np
from datetime import datetime

from typing import Optional, Any, Callable, Dict

# Handle multiple Qt bindings (PyQt6, PySide6, PyQt5)
try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                 QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                 QLabel, QFileDialog, QSplitter, QComboBox)
    from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
    from PyQt6.QtGui import QIcon, QFont
except ImportError:
    try:
        from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                     QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                     QLabel, QFileDialog, QSplitter, QComboBox)
        from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
        from PySide6.QtGui import QIcon, QFont
    except ImportError:
        try:
            from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                         QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                         QLabel, QFileDialog, QSplitter, QComboBox)
            from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex
            from PyQt5.QtGui import QIcon, QFont
        except ImportError:
            try:
                from PySide2.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                             QHBoxLayout, QPushButton, QLineEdit, QTableView, 
                                             QLabel, QFileDialog, QSplitter, QComboBox)
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
            try:
                col_name = self._data.columns[index.column()]
                val = self._data.iloc[index.row(), index.column()]
                
                if role == _DisplayRole or role == Qt.ItemDataRole.EditRole:
                    # Time Formatting for display only
                    if role == _DisplayRole and col_name.lower() in ('time', 'timestamp'):
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
    def __init__(self, on_code_callback: Optional[Callable[[str], Any]] = None, service_proxy: Any = None, 
                 last6vol_map: Optional[Dict[str, float]] = None, main_app: Any = None):
        super().__init__()
        self.on_code_callback = on_code_callback
        self.service_proxy = service_proxy # RealtimeDataService proxy
        self.last6vol_map = last6vol_map if last6vol_map is not None else {}
        self.main_app = main_app # Reference to Tkinter app
        self.internal_dfs: Dict[str, pd.DataFrame] = {}

        self.current_file: Optional[str] = None
        self.is_memory_mode: bool = False
        self.setWindowTitle("Minute Kline Cache Viewer (Realtime Service)")
        self.resize(1100, 750)
        
        self.df_file = pd.DataFrame()     # Source Data Table (from file)
        self.df_mem = pd.DataFrame()      # Memory View (synced realtime data)
        self.df_display = pd.DataFrame() 
        
        self.setup_ui()
        self.auto_load()

    @property
    def active_df(self) -> pd.DataFrame:
        """根据当前模式返回活跃的数据集"""
        return self.df_mem if self.is_memory_mode else self.df_file

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
        
        toolbar_layout.addWidget(self.btn_open)
        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addWidget(self.btn_mem)
        toolbar_layout.addWidget(self.btn_add_row)
        toolbar_layout.addWidget(self.btn_del_row)
        toolbar_layout.addWidget(self.btn_save)
        toolbar_layout.addStretch(1) # Stretch before del-time
        toolbar_layout.addWidget(QLabel("Time:"))
        toolbar_layout.addWidget(self.time_input)
        toolbar_layout.addWidget(self.btn_del_time)
        toolbar_layout.addStretch(1) # Stretch before search
        toolbar_layout.addWidget(QLabel("Search Code:"))
        toolbar_layout.addWidget(self.search_input)
        
        # Source Selection
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("File")
        if self.service_proxy:
            self.source_combo.addItem("Memory Service")
        self.source_combo.currentIndexChanged.connect(self.on_source_changed)
        toolbar_layout.addWidget(self.source_combo)

        self.btn_scan = QPushButton("Scan")
        self.btn_scan.clicked.connect(self.discover_internal_dfs)
        toolbar_layout.addWidget(self.btn_scan)
        
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
        start_dir = ""
        if self.current_file and os.path.exists(self.current_file):
            start_dir = os.path.dirname(os.path.abspath(self.current_file))
            
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Cache File", start_dir, "Pickle Files (*.pkl);;All Files (*)"
        )
        if file_name:
            self.load_data(file_name)
            if self.source_combo.currentText() != "File":
                self.source_combo.setCurrentText("File")

    def discover_internal_dfs(self):
        """扫描 main_app 中的所有 pandas DataFrame"""
        if not self.main_app:
            self.statusBar().showMessage("Main app not connected.")
            return

        self.internal_dfs = {}
        seen_shapes = set() # 用来根据 shape 去重

        # 扫描主对象
        for attr_name in dir(self.main_app):
            if attr_name.startswith('_'): continue
            try:
                attr = getattr(self.main_app, attr_name)
                if isinstance(attr, pd.DataFrame) and not attr.empty:
                    shape = attr.shape
                    if shape not in seen_shapes:
                        self.internal_dfs[f"app.{attr_name}"] = attr
                        seen_shapes.add(shape)
            except: continue

        # 扫描一些已知的子对象
        for sub_obj_name in ['live_strategy', 'realtime_service']:
            sub_obj = getattr(self.main_app, sub_obj_name, None)
            if sub_obj:
                for attr_name in dir(sub_obj):
                    if attr_name.startswith('_'): continue
                    try:
                        attr = getattr(sub_obj, attr_name)
                        if isinstance(attr, pd.DataFrame) and not attr.empty:
                            shape = attr.shape
                            if shape not in seen_shapes:
                                self.internal_dfs[f"{sub_obj_name}.{attr_name}"] = attr
                                seen_shapes.add(shape)
                    except: continue

        # 更新下拉框
        current_sources = [self.source_combo.itemText(i) for i in range(self.source_combo.count())]
        for name in self.internal_dfs:
            if name not in current_sources:
                self.source_combo.addItem(name)
        
        self.statusBar().showMessage(f"Discovered {len(self.internal_dfs)} unique internal DataFrames.")

    def on_source_changed(self, index):
        source_name = self.source_combo.currentText()
        if source_name == "File":
            self.is_memory_mode = False
            self.update_summary()
        elif source_name == "Memory Service":
            self.on_memory_sync()
        elif source_name in self.internal_dfs:
            self.is_memory_mode = False # Treat as file-like for direct local modification
            self.df_file = self.internal_dfs[source_name].copy()
            self.update_summary()
            self.on_filter()
            self.statusBar().showMessage(f"Loaded internal source: {source_name} dataCount: {len(self.df_file)}")

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
            if df.empty:
                try:
                    df = self.service_proxy.kline_cache.to_dataframe()
                except:
                    pass

            if df.empty:
                self.statusBar().showMessage("Memory Cache is currently empty.")
                return

            self.df_mem = df
            self.update_summary()
            self.on_filter()
            
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
        try:
            self.current_file = file_path
            self.is_memory_mode = False
            self.statusBar().showMessage(f"Loading {file_path}...")
            
            df = pd.read_pickle(file_path)
            if df is None or df.empty:
                self.stats_label.setText(f"File {file_path} is empty.")
                return

            self.df_file = df
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
            self.statusBar().showMessage(f"Data loaded successfully. dateCount: {len(self.df_file)}")
            
        except Exception as e:
            self.stats_label.setText(f"Error loading data: {e}")
            self.statusBar().showMessage("Error loading data.")

    def update_summary(self):
        try:
            df = self.active_df
            if df.empty:
                self.summary_table.setModel(DataFrameModel(pd.DataFrame(columns=['code', 'count'])))
                if hasattr(self, 'stats_label'):
                    self.stats_label.setText(f"Count: 0 | {'MEMORY' if self.is_memory_mode else 'FILE'}")
                return
                
            # 解决 'code' 既是索引又是列名的歧义问题
            if 'code' in df.columns:
                codes = df['code']
            elif 'code' in df.index.names:
                codes = df.index.get_level_values('code')
            else:
                # 兜底：如果找不到 code 列/索引，打印错误
                raise KeyError("'code' column or index not found in DataFrame.")

            summary = codes.value_counts().reset_index()
            summary.columns = ['code', 'count']
            summary = summary.sort_values('count', ascending=False)
            
            model = DataFrameModel(summary)
            self.summary_table.setModel(model)
        except Exception as e:
            print(f"DEBUG: update_summary Error: {e}")

    def on_filter(self):
        try:
            search_text = self.search_input.text().strip().upper()
            df = self.active_df
            if df.empty:
                self.summary_table.setModel(DataFrameModel(pd.DataFrame(columns=['code', 'count'])))
                return
                
            if not search_text:
                self.update_summary()
            else:
                summary = df.groupby('code').size().reset_index(name='count')
                # Use regex=False to avoid crashes on special characters
                summary = summary[summary['code'].str.contains(search_text, regex=False)]
                summary = summary.sort_values('count', ascending=False)
                model = DataFrameModel(summary)
                self.summary_table.setModel(model)
        except Exception as e:
            print(f"DEBUG: on_filter Error: {e}")

    def on_summary_clicked(self, index: QModelIndex):
        df = self.active_df
        if df.empty:
            return
            
        model = index.model()
        if isinstance(model, DataFrameModel):
            # 假设代码在第一列
            code = str(model._data.iloc[index.row(), 0])
            detail_df = df[df['code'] == code].copy()
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
        if self.active_df.empty:
            return
            
        model = index.model()
        if isinstance(model, DataFrameModel):
            row_data = model._data.iloc[index.row()]
            code = str(row_data.get('code', row_data.iloc[0]))
            
            if self.on_code_callback:
                self.on_code_callback(code)
            else:
                # print(f"Double-clicked code: {code}")
                # Use it as triggering a refresh of detail if clicked in summary
                if model is self.summary_table.model():
                    self.on_summary_clicked(index)

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
                try:
                    self.statusBar().showMessage("Saving to remote memory cache...")
                    self.service_proxy.kline_cache.from_dataframe(df)
                    self.statusBar().showMessage("Successfully saved to Memory!")
                except Exception as e:
                    self.statusBar().showMessage(f"Save to Memory Failed: {e}")
            else:
                if not self.current_file:
                    self.statusBar().showMessage("File Mode: No file path.")
                    return
                
                self.statusBar().showMessage(f"Saving to {self.current_file}...")
                df.to_pickle(self.current_file)
                self.statusBar().showMessage(f"Successfully saved to {os.path.basename(self.current_file)}!")
                
        except Exception as e:
            self.statusBar().showMessage(f"Save Failed: {e}")
            print(f"DEBUG: Save General Error: {e}")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set style for modern look (vibrant colors)
    app.setStyle("Fusion")
    
    viewer = KlineBackupViewer()
    viewer.show()
    sys.exit(app.exec())
