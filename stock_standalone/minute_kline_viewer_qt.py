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

    @property
    def active_df(self) -> pd.DataFrame:
        """根据当前模式返回活跃的数据集"""
        return self.df_mem if self.is_memory_mode else self.df_file

    def get_queried_df(self) -> pd.DataFrame:
        """应用全局 Query 后的数据集"""
        df = self.active_df
        query_str = self.query_input.text().strip()
        if not query_str:
            return df
        
        try:
            # 记录下查询字符串以便调试
            # print(f"[DEBUG] Applying query: {query_str}")
            return df.query(query_str)
        except Exception as e:
            # 如果查询失败，返回原数据并在状态栏显示错误
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
        
        # --- 第二栏：高级查询 (Advanced Query) ---
        query_layout = QHBoxLayout()
        query_layout.addWidget(QLabel("Query:"))
        
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("e.g. close > 10 and volume > 100000 (Supports pandas .query() syntax)")
        self.query_input.returnPressed.connect(self.on_apply_query)
        query_layout.addWidget(self.query_input, 1)
        
        self.btn_apply_query = QPushButton("Apply")
        self.btn_apply_query.setStyleSheet("background-color: #34495e; color: white;")
        self.btn_apply_query.clicked.connect(self.on_apply_query)
        query_layout.addWidget(self.btn_apply_query)
        
        self.btn_clear_query = QPushButton("Clear")
        self.btn_clear_query.clicked.connect(self.on_clear_query)
        query_layout.addWidget(self.btn_clear_query)
        
        main_layout.addLayout(query_layout)

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
        
        self.upper_splitter.addWidget(self.summary_table)
        self.upper_splitter.addWidget(self.detail_table)
        self.upper_splitter.setStretchFactor(0, 1)
        self.upper_splitter.setStretchFactor(1, 2)

        # Bottom Area: Full Queried Results
        self.full_results_table = QTableView()
        self.full_results_table.setAlternatingRowColors(True)
        self.full_results_table.setSelectionBehavior(_SelectRows)
        self.full_results_table.setSortingEnabled(True)
        self.full_results_table.doubleClicked.connect(self.on_double_click)
        
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

        self.statusBar().showMessage("Ready")
        
    def _smart_resize(self, table_view):
        """智能调整列宽：行数少时全量平衡，行数多时优先保证核心列（code, time）"""
        model = table_view.model()
        if not model or not hasattr(model, '_data'):
            return
        df = model._data
        if df.empty:
            return
            
        if len(df) < 1000:
            table_view.resizeColumnsToContents()
        else:
            # 仅针对核心长列进行调整，避免大表由于全列扫描导致的 UI 挂起
            for i, col in enumerate(df.columns):
                if str(col).lower() in ('code', 'time', 'ticktime', 'datetime'):
                    table_view.resizeColumnToContents(i)

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
            except:
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

        # 3. 字段映射集成 (统一使用 time 而不是 ticktime，但保留 ticktime 作为别名)
        if 'ticktime' in df.columns and 'time' not in df.columns:
            df['time'] = df['ticktime']
            
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
        start_dir = ""
        if self.current_file and os.path.exists(self.current_file):
            start_dir = os.path.dirname(os.path.abspath(self.current_file))

        # 修改这里，添加 HDF5 支持
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Cache File",
            start_dir,
            "HDF5 Files (*.h5);;All Files (*);;Pickle Files (*.pkl)"
        )

        if file_name:
            # 根据文件类型调用不同加载方式
            ext = os.path.splitext(file_name)[1].lower()
            if ext == ".pkl":
                self.load_data(file_name)
            elif ext == ".h5":
                self.load_data(file_name)
            else:
                # 默认尝试 pickle
                self.load_data(file_name)

            # 更新数据源显示
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

            self.df_mem = df
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

            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".pkl":
                df = pd.read_pickle(file_path)

            elif ext == ".h5":
                # 获取所有 key
                with pd.HDFStore(file_path, "r") as store:
                    keys = store.keys()  # 返回 ['/data1', '/data2', ...]
                    keys = [k.strip("/") for k in keys]  # 去掉前导斜杠

                if not keys:
                    self.stats_label.setText(f"No datasets found in {file_path}")
                    return

                # 只有一个 key 时直接使用
                if len(keys) == 1:
                    key = keys[0]
                else:
                    # 弹出选择框，让用户选择 key
                    key, ok = QInputDialog.getItem(
                        self,
                        "Select HDF5 Key",
                        "Choose dataset to load:",
                        keys,
                        0,
                        False
                    )
                    if not ok:
                        self.statusBar().showMessage("HDF5 load cancelled.")
                        return

                df = pd.read_hdf(file_path, key=key)

            else:
                self.stats_label.setText(f"Unsupported file type: {ext}")
                self.statusBar().showMessage("Error loading data.")
                return

            # 统一规范化
            df = self._normalize_dataframe(df)
            if df is None or df.empty:
                self.stats_label.setText(f"File {file_path} is empty.")
                return

            self.df_file = df
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

    def update_summary(self):
        """刷新摘要表 (使用当前查询结果)"""
        try:
            df = self.get_queried_df()
            if df.empty:
                self.summary_table.setModel(DataFrameModel(pd.DataFrame(columns=['code', 'count'])))
                if hasattr(self, 'stats_label'):
                    self.stats_label.setText(f"Count: 0 | {'MEMORY' if self.is_memory_mode else 'FILE'} | Query Active")
                return
                
            # 解决 'code' 既是索引又是列名的歧义问题
            if 'code' in df.columns:
                codes = df['code']
            elif 'code' in df.index.names:
                codes = df.index.get_level_values('code')
            else:
                # 兜底：取第一列
                codes = df.iloc[:, 0]

            summary = codes.value_counts().reset_index()
            summary.columns = ['code', 'count']
            summary = summary.sort_values('count', ascending=False)
            
            model = DataFrameModel(summary)
            self.summary_table.setModel(model)
            self._smart_resize(self.summary_table)
        except Exception as e:
            print(f"DEBUG: update_summary Error: {e}")

    def on_apply_query(self):
        """执行查询并刷新界面"""
        query_str = self.query_input.text().strip()
        self.statusBar().showMessage(f"Applying query: {query_str}" if query_str else "Refreshing data summary...")
        
        df_queried = self.get_queried_df()
        
        # 统计数据
        total_count = len(self.active_df)
        match_count = len(df_queried)
        stock_count = df_queried['code'].nunique() if 'code' in df_queried.columns else 0
        total_stocks = self.active_df['code'].nunique() if not self.active_df.empty else 0
        
        # 1. 更新底部统计标签与表格 (full_results_table)
        if query_str:
            self.full_results_label.setText(f"<b>Queried Results:</b> {match_count} found ({stock_count} stocks) / Total {total_count}")
            self.full_results_table.setModel(DataFrameModel(df_queried))
            self._smart_resize(self.full_results_table)
        else:
            # 无查询时显示总量统计
            self.full_results_label.setText(f"<b>Full Dataset:</b> {total_count} records ({total_stocks} stocks)")
            # 性能优化：无查询时底部表格不显示全量（除非极小），避免 UI 挂起
            if total_count < 500:
                self.full_results_table.setModel(DataFrameModel(self.active_df))
                self._smart_resize(self.full_results_table)
            else:
                # 显示空表但保留列名，防止 IndexError 并清晰提示
                self.full_results_table.setModel(DataFrameModel(pd.DataFrame(columns=self.active_df.columns)))
        
        # 2. 更新顶部 stats_label (持久化主要统计)
        if hasattr(self, 'stats_label'):
            mode_str = 'MEMORY' if self.is_memory_mode else 'FILE'
            if query_str:
                self.stats_label.setText(f"Matches: {match_count} ({stock_count} stocks) | Base: {total_count} | Mode: {mode_str}")
            else:
                self.stats_label.setText(f"Total: {total_count} records | Stocks: {total_stocks} | Mode: {mode_str}")

        # 3. 处理摘要表 (左侧)
        self.update_summary()
        self.on_filter()
        
        # 4. 处理右侧快照视图 (快照仅在有活跃查询且有结果时显示)
        if query_str and not df_queried.empty:
            # 找到每个 code 的最后一行
            time_col = 'time' if 'time' in df_queried.columns else 'ticktime'
            
            # 使用快速聚合
            if time_col in df_queried.columns:
                # 预排序，加速 groupby.tail
                df_snapshot = df_queried.sort_values(['code', time_col]).groupby('code').tail(1)
            else:
                df_snapshot = df_queried.groupby('code').tail(1)
            
            self.detail_table.setModel(DataFrameModel(df_snapshot.sort_values('code')))
            self._smart_resize(self.detail_table)
            self.statusBar().showMessage(f"Query Result: {match_count} rows | Snapshots: {len(df_snapshot)}", 3000)
        elif not query_str:
            # 如果是清空或初始化，右侧详情表重置为空（等待用户点击左侧）
            self.detail_table.setModel(DataFrameModel(pd.DataFrame()))
        else:
            # 有查询但无结果
            self.detail_table.setModel(DataFrameModel(pd.DataFrame()))
            self.statusBar().showMessage("Query applied. No matches found.", 3000)

    def on_clear_query(self):
        """清空查询"""
        self.query_input.clear()
        self.on_apply_query()
        self.statusBar().showMessage("Query cleared. Showing full summary counts.", 3000)

    def on_filter(self):
        try:
            search_text = self.search_input.text().strip().upper()
            df = self.get_queried_df()
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
                self._smart_resize(self.summary_table)
        except Exception as e:
            print(f"DEBUG: on_filter Error: {e}")

    def on_summary_clicked(self, index: QModelIndex):
        """处理摘要表点击事件，显示股票详情"""
        try:
            # 🛡️ 等待语音完成，避免 GIL 冲突
            self._wait_voice_safe()
            
            # print(f"[DEBUG] on_summary_clicked: index.row()={index.row()}, index.column()={index.column()}")
            
            # 使用 raw 数据集 (active_df) 而不是 filtered 数据集，以便看到该股票的完整多行历史 (横排多行)
            df_full = self.active_df
            if df_full.empty:
                return
                
            model = index.model()
            if not isinstance(model, DataFrameModel):
                return
            
            # 提取代码
            code = str(model._data.iloc[index.row(), 0])
            
            # 过滤该代码的所有历史记录
            if 'code' not in df_full.columns:
                detail_df = df_full.loc[[code]].copy()
            else:
                detail_df = df_full[df_full['code'] == code].copy()
            
            if 'time' in detail_df.columns:
                detail_df = detail_df.sort_values('time', ascending=False)
            elif 'ticktime' in detail_df.columns:
                detail_df = detail_df.sort_values('ticktime', ascending=False)
            
            # Calculate vol_ratio
            if hasattr(self, 'last6vol_map') and code in self.last6vol_map:
                l6v = self.last6vol_map[code]
                if l6v > 0:
                    minute_avg_vol = l6v / 240
                    if 'volume' in detail_df.columns:
                         detail_df['vol_ratio'] = detail_df['volume'] / minute_avg_vol

            new_model = DataFrameModel(detail_df)
            self.detail_table.setModel(new_model)
            self._smart_resize(self.detail_table)
            
            # 🛡️ 强制处理 Qt 事件，避免与 Tkinter 事件循环冲突
            QApplication.processEvents()
            
            # print(f"[DEBUG] on_summary_clicked: detail_table updated successfully")
            
            # [FIX] 恢复可视化器联动 (使用 tk_dispatch_queue 解决 GIL/线程安全问题)
            if self.main_app is not None and code:
                try:
                    # 检查是否有 dispatch queue (新版)
                    if hasattr(self.main_app, 'tk_dispatch_queue'):
                        def _safe_linkage_task():
                            # ✅ 在 Tkinter 主线程中检查 vis_var 和打开窗口
                            try:
                                if hasattr(self.main_app, 'vis_var') and self.main_app.vis_var.get():
                                    if hasattr(self.main_app, 'open_visualizer'):
                                        # print(f"[DEBUG] safe linkage: open_visualizer({code})")
                                        self.main_app.open_visualizer(str(code))
                            except Exception as e:
                                print(f"[ERROR] safe linkage task failed: {e}")

                        self.main_app.tk_dispatch_queue.put(_safe_linkage_task)
                    
                    # 旧版兼容 (仍然风险较高, 仅作备用)
                    elif hasattr(self.main_app, 'after'):
                        # print("[WARN] Legacy linkage: using .after() which involves cross-thread var access")
                        self.main_app.after(0, lambda: self.main_app.open_visualizer(str(code)) 
                                            if (hasattr(self.main_app, 'vis_var') and self.main_app.vis_var.get()) else None)

                except Exception as viz_e:
                    print(f"[ERROR] on_summary_clicked: linkage check failed: {viz_e}")
        
        except Exception as e:
            print(f"[ERROR] on_summary_clicked: {e}")
            import traceback
            traceback.print_exc()


    def on_double_click(self, index: QModelIndex):
        """处理双击事件"""
        try:
            print(f"[DEBUG] on_double_click: index.row()={index.row()}")
            
            if self.active_df.empty:
                print("[DEBUG] on_double_click: active_df is empty")
                return
                
            model = index.model()
            if isinstance(model, DataFrameModel):
                row_data = model._data.iloc[index.row()]
                code = str(row_data.get('code', row_data.iloc[0]))
                print(f"[DEBUG] on_double_click: code={code}")
                
                if self.on_code_callback:
                    print(f"[DEBUG] on_double_click: scheduling on_code_callback({code}) via Tkinter Dispatch Queue")
                    # 🛡️ 使用 tk_dispatch_queue 将调用调度到 Tkinter 主线程 (避免 GIL 崩溃)
                    if self.main_app and hasattr(self.main_app, 'tk_dispatch_queue'):
                        self.main_app.tk_dispatch_queue.put(lambda: self.on_code_callback(code))
                    elif self.main_app and hasattr(self.main_app, 'after'):
                        # Fallback (Unsafe, legacy)
                        print("[WARN] No dispatch queue found, falling back to unsafe .after()")
                        self.main_app.after(0, lambda c=code: self.on_code_callback(c))
                    else:
                        # 回退：直接调用（可能在独立模式下运行）
                        self.on_code_callback(code)
                else:
                    # Use it as triggering a refresh of detail if clicked in summary
                    if model is self.summary_table.model():
                        self.on_summary_clicked(index)
        except Exception as e:
            print(f"[ERROR] on_double_click: {e}")
            import traceback
            traceback.print_exc()

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
