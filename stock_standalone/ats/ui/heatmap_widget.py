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
        import time
        now = time.time()
        if hasattr(self, '_last_load_time') and now - self._last_load_time < 10.0:
            return
        self._last_load_time = now
        
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
            self.sector_to_codes = {}
            
            for code in v_reversal_pool:
                code_str = str(code).strip()
                sec = stock_to_sector.get(code_str)
                if not sec:
                    continue
                    
                if sec not in self.sector_to_codes:
                    self.sector_to_codes[sec] = []
                self.sector_to_codes[sec].append(code_str)
                
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
                # Incorporate active count momentum into sector intensity scoring to prioritize highly resonant hot sectors
                intensity_score = avg_score * (1.0 + 0.15 * count)
                avg_pct = sum(sector_changes[sec]) / len(sector_changes[sec])
                change_pct_str = f"{avg_pct:+.2f}%"
                
                leader_code, _, leader_name = sector_leaders.get(sec, ('', 0.0, ''))
                
                sectors_list.append((sec, round(intensity_score, 1), change_pct_str, count, leader_code, leader_name))
                
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
                        self.sector_to_codes = {}
                        if sector_data:
                            for sec_name, info in sector_data.items():
                                self.sector_to_codes[sec_name] = []
                                score = info.get('score', 0.0)
                                avg_pct = info.get('avg_pct_diff') or info.get('avg_pct') or 0.0
                                count = info.get('count') or len(info.get('followers', []))
                                change_pct_str = f"{avg_pct:+.2f}%"
                                leader_code = info.get('leader', '')
                                leader_name = info.get('leader_name', '')
                                self._cached_session_sectors.append((sec_name, round(score, 1), change_pct_str, count, leader_code, leader_name))
                                if leader_code:
                                    self.sector_to_codes[sec_name].append(str(leader_code).strip())
                                for fol in info.get('followers', []):
                                    f_code = fol.get('code')
                                    if f_code:
                                        self.sector_to_codes[sec_name].append(str(f_code).strip())
                        self._last_session_path = path
                        self._last_session_mtime = session_mtime
                except Exception as e:
                    print(f"[SectorHeatmapWidget] Error loading legacy bidding_session_data: {e}")
            
            if hasattr(self, '_cached_session_sectors') and self._cached_session_sectors:
                self.sectors = self._cached_session_sectors
                self.sort_sectors(self.sort_combo.currentIndex())
                return

        # 3. Fallback to mock sectors if all else fails
        if not hasattr(self, 'sector_to_codes'):
            self.sector_to_codes = {}
        if not hasattr(self, 'sectors') or not self.sectors:
            self.load_mock_sectors()

    def get_color_for_score(self, pct_str):
        try:
            val = float(pct_str.replace("%", "").replace("+", ""))
        except:
            val = 0.0
        
        # Premium dark technology translucent theme matching core styling
        if val > 0:
            intensity = min(int(val * 40), 100)
            bg = f"rgba({110 + intensity}, 20, 35, {0.18 + intensity/220.0:.2f})"
            border = f"rgba(255, 68, 90, {0.35 + intensity/220.0:.2f})"
        elif val < 0:
            intensity = min(int(abs(val) * 40), 100)
            bg = f"rgba(15, {90 + intensity}, 45, {0.18 + intensity/220.0:.2f})"
            border = f"rgba(40, 210, 95, {0.35 + intensity/220.0:.2f})"
        else:
            bg = "rgba(38, 38, 45, 0.25)"
            border = "rgba(70, 70, 80, 0.35)"
            
        return bg, border

    def render_grid(self):
        # Clear layout first
        for i in reversed(range(self.grid_layout.count())): 
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_stocks = fav_mgr.get_favorite_stocks()
        fav_sectors = fav_mgr.get_favorite_sectors()

        cols = 4  # 4 columns grid
        for idx, item in enumerate(self.sectors):
            name, score, pct, count = item[:4]
            row = idx // cols
            col = idx % cols

            # Card Widget
            card = QPushButton()
            card.setMinimumSize(120, 85)
            
            # Check if this sector or any stock inside is favorite
            is_fav_sec = name in fav_sectors
            sec_codes = getattr(self, 'sector_to_codes', {}).get(name, [])
            has_fav_stock = any(c in fav_stocks for c in sec_codes)
            is_highlight = is_fav_sec or has_fav_stock

            if is_highlight:
                bg_style = "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A2A1A, stop:1 #111E11);"
                border_style = "border: 1.5px solid rgba(255, 215, 0, 0.8);"
                display_name = f"⭐ {name}"
            else:
                bg, border = self.get_color_for_score(pct)
                bg_style = f"background-color: {bg};"
                border_style = f"border: 1px solid {border};"
                display_name = name
            
            # Premium card stylesheet with glowing borders and smooth scale/hover transition
            card.setStyleSheet(f"""
                QPushButton {{
                    {bg_style}
                    {border_style}
                    border-radius: 6px;
                    color: white;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1.5px solid #ffffff;
                }}
            """)
            
            # Enable custom context menu for favorites management
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, n=name: self._show_sector_context_menu(pos, n))
            
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(4, 4, 4, 4)
            card_layout.setSpacing(2)
            
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet("font-weight: bold; color: #ffffff; background: transparent; font-size: 11pt;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            info_lbl = QLabel(f"分: {score} | {pct}")
            info_lbl.setStyleSheet("color: #e2e2e5; background: transparent; font-size: 9pt;")
            info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            count_lbl = QLabel(f"成员: {count}")
            count_lbl.setStyleSheet("color: #aad4ff; background: transparent; font-size: 8pt; font-style: italic;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            card_layout.addWidget(name_lbl)
            card_layout.addWidget(info_lbl)
            card_layout.addWidget(count_lbl)
            
            card.clicked.connect(lambda checked, n=name: self.sector_selected.emit(n))
            self.grid_layout.addWidget(card, row, col)

    def sort_sectors(self, index):
        def safe_float_pct(val_str):
            try:
                return float(str(val_str).replace("%", "").replace("+", ""))
            except:
                return 0.0

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_stocks = fav_mgr.get_favorite_stocks()
        fav_sectors = fav_mgr.get_favorite_sectors()
        
        def get_sort_key(x):
            sec_name = x[0]
            is_fav_sec = sec_name in fav_sectors
            sec_codes = getattr(self, 'sector_to_codes', {}).get(sec_name, [])
            has_fav_stock = any(c in fav_stocks for c in sec_codes)
            is_highlight = is_fav_sec or has_fav_stock
            
            # Primary key: 0 if highlighted, 1 if not
            prim = 0 if is_highlight else 1
            
            if index == 0:
                sec_val = -float(x[1])
            elif index == 1:
                sec_val = -safe_float_pct(x[2])
            else:
                sec_val = -int(x[3])
                
            return (prim, sec_val)

        self.sectors.sort(key=get_sort_key)
        self.render_grid()

    def _show_sector_context_menu(self, pos, sector_name):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        from global_favorites import GlobalFavoriteManager
        
        fav_mgr = GlobalFavoriteManager()
        is_fav = sector_name in fav_mgr.get_favorite_sectors()
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #ffffff;
            }
        """)
        
        if is_fav:
            fav_action = QAction(f"❌ 取消重点关注板块 {sector_name}", self)
        else:
            fav_action = QAction(f"⭐ 设为重点关注板块 {sector_name}", self)
        
        fav_action.triggered.connect(lambda: self._toggle_favorite_sector(sector_name))
        menu.addAction(fav_action)
        
        sender_card = self.sender()
        if sender_card:
            global_pos = sender_card.mapToGlobal(pos)
        else:
            global_pos = self.mapToGlobal(pos)
            
        menu.exec(global_pos)

    def _toggle_favorite_sector(self, sector_name):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_sector(sector_name)
        except Exception as e:
            print(f"[SectorHeatmap] Toggle favorite sector error: {e}")
