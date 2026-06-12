# -*- coding: utf-8 -*-
"""
ATS Sector Heatmap Widget
Provides a visual grid of sector momentum scores.
Colors range dynamically based on intensity of momentum.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QHBoxLayout, QPushButton, QComboBox, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont
import os
import json
import zlib
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct

class SectorHeatmapWidget(QWidget):
    sector_selected = pyqtSignal(str) # sector name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_live_sectors()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header controls
        header = QHBoxLayout()
        title = QLabel("🔥 行业板块强度热力图 (Sector Momentum)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 12pt;")
        header.addWidget(title)
        header.addStretch()

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["按强度得分降序", "按涨跌幅降序", "按活跃成员数降序"])
        self.sort_combo.currentIndexChanged.connect(self.sort_sectors)
        header.addWidget(self.sort_combo)
        
        layout.addLayout(header)

        # Scroll Area for Heatmap Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #121214; border: 1px solid #2e2e36;")
        
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #121214;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(6)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

    def load_mock_sectors(self):
        # Name, Score (0-100), Change %, Active Count
        self.sectors = [
            ("半导体", 85.5, "+3.45%", 12),
            ("光伏设备", 72.3, "+2.10%", 8),
            ("国防军工", 68.0, "+1.85%", 6),
            ("计算机设备", 62.1, "+0.95%", 15),
            ("证券", 55.4, "+0.45%", 11),
            ("白酒", 48.2, "-0.20%", 5),
            ("医疗器械", 42.0, "-0.80%", 9),
            ("银行", 38.5, "-1.15%", 10),
            ("煤炭开采", 25.4, "-2.40%", 4),
            ("房地产开发", 18.0, "-3.20%", 7),
            ("通信设备", 75.0, "+2.80%", 9),
            ("中药", 50.0, "+0.00%", 8),
        ]
        self.sort_sectors(self.sort_combo.currentIndex())

    def load_live_sectors(self):
        import glob
        import gzip
        import re
        import zlib
        
        # 1. Try to find the latest v_reversal_pool backup in logs/
        base = get_app_root()
        logs_dir = os.path.join(base, "logs")
        pattern = os.path.join(logs_dir, "v_reversal_pool_*.json.gz")
        files = sorted(glob.glob(pattern))
        
        v_reversal_data = None
        fpath = files[-1] if files else None
        
        # Determine latest reversal path and check if changed
        ram_path = None
        if not fpath:
            try:
                ram_path = cct.get_ramdisk_path("v_reversal_pool.json")
            except Exception:
                pass
                
        latest_reversal_path = fpath if fpath else ram_path
        latest_reversal_mtime = os.path.getmtime(latest_reversal_path) if latest_reversal_path and os.path.exists(latest_reversal_path) else 0
        
        if latest_reversal_path and os.path.exists(latest_reversal_path):
            if (getattr(self, '_last_reversal_path', None) != latest_reversal_path or 
                getattr(self, '_last_reversal_mtime', None) != latest_reversal_mtime or 
                not hasattr(self, '_cached_v_reversal_pool')):
                try:
                    if latest_reversal_path.endswith('.gz'):
                        with gzip.open(latest_reversal_path, 'rb') as f:
                            raw_data = f.read()
                    else:
                        with open(latest_reversal_path, 'rb') as f:
                            raw_data = f.read()
                    try:
                        v_reversal_data = json.loads(raw_data.decode('utf-8'))
                    except Exception:
                        json_str = zlib.decompress(raw_data).decode('utf-8')
                        v_reversal_data = json.loads(json_str)
                        
                    if v_reversal_data:
                        self._cached_v_reversal_pool = v_reversal_data.get('v_reversal_pool', [])
                        self._cached_consolidation_flags = v_reversal_data.get('consolidation_flags', {})
                        self._last_reversal_path = latest_reversal_path
                        self._last_reversal_mtime = latest_reversal_mtime
                except Exception as e:
                    print(f"[SectorHeatmapWidget] Error loading reversal pool {latest_reversal_path}: {e}")
        
        has_reversal = hasattr(self, '_cached_v_reversal_pool') and self._cached_v_reversal_pool
        
        if has_reversal:
            v_reversal_pool = self._cached_v_reversal_pool
            consolidation_flags = self._cached_consolidation_flags
            
            # Map codes to sector
            stock_to_sector = {}
            main_win = self.window()
            p = self.parent()
            while p:
                if hasattr(p, 'current_df'):
                    main_win = p
                    break
                p = p.parent()
                
            current_df = None
            if main_win and hasattr(main_win, 'current_df'):
                current_df = main_win.current_df
                
            # Vectorized category extraction from current_df (takes < 1ms instead of ~1500ms)
            if current_df is not None and not current_df.empty and 'category' in current_df.columns:
                try:
                    cats = current_df['category'].dropna()
                    temp_map = {str(k).strip(): str(v).split(';')[0].strip() for k, v in cats.to_dict().items() if str(v).strip()}
                    stock_to_sector.update(temp_map)
                except Exception as e:
                    print(f"[SectorHeatmapWidget] Error extracting categories: {e}")
                            
            # Lazy loaded fallback mapping from recent daily bidding snapshots (once)
            if not hasattr(self, '_bidding_stock_to_sector'):
                self._bidding_stock_to_sector = {}
                try:
                    snapshot_files = glob.glob(os.path.join(base, "snapshots", "bidding_*.json.gz"))
                    valid_snapshots = [f for f in snapshot_files if re.search(r'bidding_\d{8}\.json\.gz$', f)]
                    valid_snapshots = sorted(valid_snapshots, reverse=True)
                    for spath in valid_snapshots[:3]:
                        try:
                            with open(spath, 'rb') as f:
                                raw_data = f.read()
                            json_str = zlib.decompress(raw_data).decode('utf-8')
                            data = json.loads(json_str)
                            sector_data = data.get('sector_data', {})
                            for sec_name, info in sector_data.items():
                                if info.get('leader'):
                                    self._bidding_stock_to_sector[str(info.get('leader')).strip()] = sec_name
                                for fol in info.get('followers', []):
                                    if fol.get('code'):
                                        self._bidding_stock_to_sector[str(fol.get('code')).strip()] = sec_name
                        except Exception:
                            pass
                except Exception:
                    pass
            
            # Combine real-time categories and snapshot fallbacks
            for k, v in self._bidding_stock_to_sector.items():
                if k not in stock_to_sector:
                    stock_to_sector[k] = v
                    
            # Perform aggregation
            phase_weights = {
                "二次拉升": 100.0, "WAVE_UP_2": 100.0,
                "首波拉升": 80.0, "WAVE_UP": 80.0,
                "缩量回踩": 60.0, "PULLBACK": 60.0,
                "横盘潜伏": 40.0, "CONSOLIDATING": 40.0,
                "初始状态": 20.0, "INIT": 20.0
            }
            
            sector_scores = {}
            sector_counts = {}
            sector_changes = {}
            sector_leaders = {}
            
            for code in v_reversal_pool:
                code_str = str(code).strip()
                sec = stock_to_sector.get(code_str)
                if not sec:
                    continue
                    
                flag_info = consolidation_flags.get(code_str, {})
                phase = flag_info.get('phase', 'INIT')
                weight = phase_weights.get(phase, 20.0)
                
                sector_scores[sec] = sector_scores.get(sec, 0.0) + weight
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
                
                pct_val = 0.0
                stock_name = ""
                if current_df is not None and code_str in current_df.index:
                    row = current_df.loc[code_str]
                    stock_name = str(row.get('name', ''))
                    try:
                        pct_val = float(row.get('percent', 0.0))
                    except:
                        pass
                        
                if sec not in sector_changes:
                    sector_changes[sec] = []
                sector_changes[sec].append(pct_val)
                
                if sec not in sector_leaders or pct_val > sector_leaders[sec][1]:
                    sector_leaders[sec] = (code_str, pct_val, stock_name)
                    
            sectors_list = []
            for sec, count in sector_counts.items():
                avg_score = sector_scores[sec] / count
                avg_pct = sum(sector_changes[sec]) / len(sector_changes[sec])
                change_pct_str = f"{avg_pct:+.2f}%"
                
                leader_code, _, leader_name = sector_leaders.get(sec, ('', 0.0, ''))
                
                sectors_list.append((sec, round(avg_score, 1), change_pct_str, count, leader_code, leader_name))
                
            if sectors_list:
                self.sectors = sectors_list
                self.sort_sectors(self.sort_combo.currentIndex())
                return

        # 2. Fallback to bidding_session_data.json.gz (legacy logic with modification time cache)
        path = None
        try:
            ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
            if ram_path and os.path.exists(ram_path):
                path = ram_path
        except Exception:
            pass
            
        if not path:
            try:
                fallback_path = os.path.abspath(os.path.join(base, "snapshots", "bidding_session_data.json.gz"))
                if os.path.exists(fallback_path):
                    path = fallback_path
            except Exception:
                pass
                
        if path and os.path.exists(path):
            session_mtime = os.path.getmtime(path)
            if (getattr(self, '_last_session_path', None) != path or 
                getattr(self, '_last_session_mtime', None) != session_mtime or 
                not hasattr(self, '_cached_session_sectors')):
                try:
                    with open(path, 'rb') as f:
                        raw_data = f.read()
                    if raw_data:
                        json_str = zlib.decompress(raw_data).decode('utf-8')
                        data = json.loads(json_str)
                        sector_data = data.get('sector_data', {})
                        self._cached_session_sectors = []
                        if sector_data:
                            for sec_name, info in sector_data.items():
                                score = info.get('score', 0.0)
                                avg_pct = info.get('avg_pct_diff') or info.get('avg_pct') or 0.0
                                count = info.get('count') or len(info.get('followers', []))
                                change_pct_str = f"{avg_pct:+.2f}%"
                                leader_code = info.get('leader', '')
                                leader_name = info.get('leader_name', '')
                                self._cached_session_sectors.append((sec_name, round(score, 1), change_pct_str, count, leader_code, leader_name))
                        self._last_session_path = path
                        self._last_session_mtime = session_mtime
                except Exception as e:
                    print(f"[SectorHeatmapWidget] Error loading legacy bidding_session_data: {e}")
            
            if hasattr(self, '_cached_session_sectors') and self._cached_session_sectors:
                self.sectors = self._cached_session_sectors
                self.sort_sectors(self.sort_combo.currentIndex())
                return

        # 3. Fallback to mock sectors if all else fails
        if not hasattr(self, 'sectors') or not self.sectors:
            self.load_mock_sectors()

    def get_color_for_score(self, pct_str):
        try:
            val = float(pct_str.replace("%", ""))
        except:
            val = 0.0
        
        # Color mapping:
        # High positive -> bright crimson red
        # Zero -> dark charcoal/grey
        # High negative -> bright cyber green
        if val > 0:
            intensity = min(int(val * 50), 180) # scale factor
            return f"background-color: rgb({70 + intensity}, 18, 28); border: 1px solid #ff4444;"
        elif val < 0:
            intensity = min(int(abs(val) * 50), 180)
            return f"background-color: rgb(12, {50 + intensity}, 28); border: 1px solid #33cc5a;"
        else:
            return "background-color: #222228; border: 1px solid #3e3e4a;"

    def render_grid(self):
        # Clear layout first
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)

        cols = 4  # 4 columns grid
        for idx, item in enumerate(self.sectors):
            # Unpack safely supporting both 4-tuple and 6-tuple
            name, score, pct, count = item[:4]
            row = idx // cols
            col = idx % cols

            # Card Widget
            card = QPushButton()
            card.setMinimumSize(120, 80)
            
            # Label overlay
            style = self.get_color_for_score(pct)
            card.setStyleSheet(f"""
                QPushButton {{
                    {style}
                    border-radius: 6px;
                    color: white;
                    text-align: center;
                }}
                QPushButton:hover {{
                    border: 2.5px solid #ffffff;
                }}
            """)
            
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 5, 5, 5)
            card_layout.setSpacing(2)
            
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-weight: bold; color: #ffffff; background: transparent; font-size: 11pt;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            info_lbl = QLabel(f"分: {score} | {pct}")
            info_lbl.setStyleSheet("color: #e2e2e5; background: transparent; font-size: 9pt;")
            info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            count_lbl = QLabel(f"活跃数: {count}")
            count_lbl.setStyleSheet("color: #aad4ff; background: transparent; font-size: 8pt; font-style: italic;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            card_layout.addWidget(name_lbl)
            card_layout.addWidget(info_lbl)
            card_layout.addWidget(count_lbl)
            
            # Connect action
            card.clicked.connect(lambda checked, n=name: self.sector_selected.emit(n))
            self.grid_layout.addWidget(card, row, col)

    def sort_sectors(self, index):
        if index == 0: # By score desc
            self.sectors.sort(key=lambda x: x[1], reverse=True)
        elif index == 1: # By percent desc
            self.sectors.sort(key=lambda x: float(x[2].replace("%", "")), reverse=True)
        elif index == 2: # By active count desc
            self.sectors.sort(key=lambda x: x[3], reverse=True)
        self.render_grid()
