# -*- coding: utf-8 -*-
"""
ATS Sector Heatmap Widget
Provides a visual grid of sector momentum scores.
Colors range dynamically based on intensity of momentum.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QHBoxLayout, QPushButton, QComboBox, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont
import os
import json
import zlib
from typing import Dict, Any, List, Optional
import pandas as pd
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
from ats.hot_sector_engine import is_valid_sector_name

class SectorHeatmapWidget(QWidget):
    sector_selected = pyqtSignal(str) # sector name
    sector_selected_with_codes = pyqtSignal(str, list) # sector name, member codes list
    hot_leaders_clicked = pyqtSignal() # 龙头突击榜点击
    sort_changed = pyqtSignal(int) # 排序维度切换 (0: 强度得分, 1: 涨跌幅, 2: 活跃成员数)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_cols = 4
        self._init_ui()
        self.render_grid()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.load_live_sectors)

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

        self.btn_hot_leaders = QPushButton("🚀 龙头突击榜")
        self.btn_hot_leaders.setStyleSheet("""
            QPushButton { background-color: #2a1b1b; color: #ff5577; border: 1px solid #ff4466; border-radius: 4px; font-weight: bold; font-size: 9pt; padding: 3px 8px; }
            QPushButton:hover { background-color: #ff4466; color: #ffffff; }
        """)
        self.btn_hot_leaders.clicked.connect(self._on_hot_leaders_clicked)
        header.addWidget(self.btn_hot_leaders)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["按强度得分降序", "按涨跌幅降序", "按活跃成员数降序"])
        
        # 💾 自动加载持久化保存的排序规则 (0: 强度得分, 1: 涨跌幅, 2: 活跃成员数)
        from ats.ui.styles import load_config_node, save_config_node
        saved_sort_idx = load_config_node("ats_heatmap_sort_index", 0)
        try:
            saved_sort_idx = int(saved_sort_idx)
            if 0 <= saved_sort_idx < self.sort_combo.count():
                self.sort_combo.setCurrentIndex(saved_sort_idx)
        except Exception:
            pass

        self.sort_combo.currentIndexChanged.connect(self.sort_sectors)
        header.addWidget(self.sort_combo)

        
        layout.addLayout(header)

        # Scroll Area for Heatmap Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumWidth(120)
        self.scroll.setStyleSheet("background-color: #121214; border: 1px solid #2e2e36;")
        self.setMinimumWidth(120)
        
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #121214;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(6)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        from PyQt6.QtWidgets import QLayout
        self.grid_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        
        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll)


    def _on_hot_leaders_clicked(self):
        self.hot_leaders_clicked.emit()
        main_win = self.window()
        p = self.parent()
        while p:
            if hasattr(p, "open_hot_sector_leaderboard"):
                main_win = p
                break
            p = p.parent()
        if hasattr(main_win, "open_hot_sector_leaderboard"):
            main_win.open_hot_sector_leaderboard()

    def get_top_sectors(self, top_n: int = 3) -> list:
        """
        根据当前所选的排序维度 (0: 强度得分降序, 1: 涨跌幅降序, 2: 活跃成员数降序)
        提取排名前 top_n 的真实强势板块名称 (联动龙头突击跟单榜)
        """
        if not hasattr(self, 'sectors') or not self.sectors:
            return []
        import re
        current_sort_idx = self.sort_combo.currentIndex() if hasattr(self, 'sort_combo') else 0

        def safe_float_pct(val_str):
            try:
                return float(str(val_str).replace("%", "").replace("+", ""))
            except Exception:
                return -9999.0

        def _get_metric_val(item):
            # item: (name, score, pct_str, count, leader_code, leader_name)
            try:
                if current_sort_idx == 0:
                    return float(item[1]) if len(item) > 1 else -9999.0
                elif current_sort_idx == 1:
                    return safe_float_pct(item[2]) if len(item) > 2 else -9999.0
                else:
                    return int(item[3]) if len(item) > 3 else -9999
            except Exception:
                return -9999.0

        sorted_by_metric = sorted(self.sectors, key=_get_metric_val, reverse=True)
        top_secs = []
        for item in sorted_by_metric:
            if item:
                raw_name = str(item[0]).strip()
                if not is_valid_sector_name(raw_name):
                    continue
                clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', raw_name).strip()
                sec_name = clean_sec if clean_sec else raw_name
                if not is_valid_sector_name(sec_name):
                    continue
                # 🛡️ 自动过滤虚拟系统聚合池 (如 "实时报警" / "🔔 实时报警")，保留真实题材概念赛道 (竞价挖掘)
                if any(ex in sec_name for ex in ("实时报警", "系统报警", "异动汇总")):
                    continue
                if sec_name and sec_name not in top_secs:
                    top_secs.append(sec_name)
                if len(top_secs) >= top_n:
                    break
        return top_secs



    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        card_target_w = 92
        calc_cols = max(2, min(5, (w - 20) // (card_target_w + 6)))
        if getattr(self, '_current_cols', None) != calc_cols:
            self._current_cols = calc_cols
            self.render_grid()

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

    def update_from_tk_sector_data(self, sector_data: Dict[str, Any]):
        """
        [SSOT 极限性能复用] 直接消费 TK 计算好的权威板块强度与龙头数据
        彻底消除前端自创加权公式，彻底对齐左侧赛马监控窗口 (89.1, 74.7, 60.8...)
        """
        if not sector_data:
            return
        sectors_list = []
        self.sector_to_codes = {}
        for sec_name, info in sector_data.items():
            clean_sec = str(sec_name).strip()
            # 🛡️ 严格过滤 '--', '0', 'nan', '未知' 等非明确板块
            if not is_valid_sector_name(clean_sec):
                continue
            score = float(info.get('score', 0.0) or 0.0)
            avg_pct = info.get('avg_pct_diff')
            if avg_pct is None or (avg_pct == 0.0 and info.get('avg_pct') is not None):
                avg_pct = info.get('avg_pct', 0.0)
            avg_pct = float(avg_pct or 0.0)
            change_pct_str = f"{avg_pct:+.2f}%"

            leader_code = str(info.get('leader', '')).strip().zfill(6) if info.get('leader') else ''
            leader_name = str(info.get('leader_name', '')).strip()

            codes_set = set()
            if leader_code and leader_code != '000000':
                codes_set.add(leader_code)

            for rc in info.get('race_candidates', []):
                c = str(rc.get('code', '')).strip().zfill(6)
                if c and c != '000000':
                    codes_set.add(c)

            for fol in info.get('followers', []):
                c = str(fol.get('code', '')).strip().zfill(6)
                if c and c != '000000':
                    codes_set.add(c)

            count = len(codes_set) if codes_set else int(info.get('count', 0) or 0)
            self.sector_to_codes[clean_sec] = list(codes_set)
            sectors_list.append(
                (clean_sec, round(score, 1), change_pct_str, count, leader_code, leader_name)
            )

        if sectors_list:
            self._has_live_ipc_data = True
            self.sectors = sectors_list
            self._cached_session_sectors = list(sectors_list)
            self.sort_sectors(self.sort_combo.currentIndex())

    def load_live_sectors(self, force=False, current_df=None):
        # 🛡️ [权威实时保护] 若已接收到活跃的盘中 IPC 实时推送，绝不用本地早盘静态旧快照反向冲刷覆盖最新数据！
        if getattr(self, '_has_live_ipc_data', False) and not force:
            return

        import time
        now = time.time()
        if not force and hasattr(self, '_last_load_time') and now - self._last_load_time < 2.0:
            return
        self._last_load_time = now
        
        import glob
        import gzip
        import re
        import zlib
        
        base = get_app_root()

        # ── 0. 智能解析主窗口正在轮询的最新策略 DataFrame (current_df) ──
        if current_df is None or (isinstance(current_df, pd.DataFrame) and current_df.empty):
            main_win = self.window()
            p = self.parent()
            while p:
                if hasattr(p, 'current_df') and getattr(p, 'current_df') is not None and not getattr(p, 'current_df').empty:
                    current_df = p.current_df
                    break
                p = p.parent()
            if (current_df is None or (isinstance(current_df, pd.DataFrame) and current_df.empty)) and hasattr(main_win, 'current_df'):
                current_df = getattr(main_win, 'current_df', None)

        # ── 1. 【权威数据源 (SSOT)】优先从 RAMDisk 或快照读取 bidding_session_data.json.gz ──
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
                else:
                    # 尝试寻找最新日期的 bidding_YYYYMMDD.json.gz
                    snap_pattern = os.path.join(base, "snapshots", "bidding_*.json.gz")
                    snap_files = [f for f in glob.glob(snap_pattern) if re.search(r'bidding_\d{8}\.json\.gz$', f)]
                    if snap_files:
                        path = sorted(snap_files)[-1]
            except Exception:
                pass
                
        if path and os.path.exists(path):
            session_mtime = os.path.getmtime(path)
            if (getattr(self, '_last_session_path', None) != path or 
                getattr(self, '_last_session_mtime', None) != session_mtime or 
                not hasattr(self, '_cached_raw_sector_data') or force):
                try:
                    with open(path, 'rb') as f:
                        raw_data = f.read()
                    if raw_data:
                        json_str = zlib.decompress(raw_data).decode('utf-8')
                        data = json.loads(json_str)
                        self._cached_raw_sector_data = data.get('sector_data', {})
                        self._last_session_path = path
                        self._last_session_mtime = session_mtime
                except Exception as e:
                    print(f"[SectorHeatmapWidget] Error loading bidding_session_data: {e}")
            
            raw_sector_data = getattr(self, '_cached_raw_sector_data', {})
            if raw_sector_data:
                # 🛡️ [SSOT 权威数据消费与极限性能] 100% 直接消费 TK 计算好的权威板块强度数据，绝不自创公式重新计算，杜绝卡顿与失真
                self.update_from_tk_sector_data(raw_sector_data)
                return

        # ── 2. 【备用兜底通道】仅在无 bidding_session_data 时尝试从 v_reversal_pool 读取 ──
        ram_path = None
        try:
            ram_path = cct.get_ramdisk_path("v_reversal_pool.json")
        except Exception:
            pass
            
        latest_reversal_path = None
        if ram_path and os.path.exists(ram_path):
            latest_reversal_path = ram_path
        else:
            logs_dir = os.path.join(base, "logs")
            normal_path = os.path.join(logs_dir, "v_reversal_pool.json")
            if os.path.exists(normal_path):
                latest_reversal_path = normal_path
            else:
                pattern = os.path.join(logs_dir, "v_reversal_pool_*.json.gz")
                files = sorted(glob.glob(pattern))
                if files:
                    latest_reversal_path = files[-1]
                    
        v_reversal_data = None
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
                    temp_map = {}
                    for k, v in cats.to_dict().items():
                        v_str = str(v).split(';')[0].strip()
                        if is_valid_sector_name(v_str):
                            k_str = str(k).strip()
                            temp_map[k_str] = v_str
                            k_clean = "".join(c for c in k_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in k_str) else k_str
                            temp_map[k_clean] = v_str
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
                                if not is_valid_sector_name(sec_name):
                                    continue
                                lcode = str(info.get('leader', '')).strip()
                                if lcode:
                                    self._bidding_stock_to_sector[lcode] = sec_name
                                    lclean = "".join(c for c in lcode if c.isdigit()).zfill(6) if any(c.isdigit() for c in lcode) else lcode
                                    self._bidding_stock_to_sector[lclean] = sec_name
                                for fol in info.get('followers', []):
                                    fcode = str(fol.get('code', '')).strip()
                                    if fcode:
                                        self._bidding_stock_to_sector[fcode] = sec_name
                                        fclean = "".join(c for c in fcode if c.isdigit()).zfill(6) if any(c.isdigit() for c in fcode) else fcode
                                        self._bidding_stock_to_sector[fclean] = sec_name
                        except Exception:
                            pass
                except Exception:
                    pass
            
            # Combine real-time categories and snapshot fallbacks
            for k, v in self._bidding_stock_to_sector.items():
                if is_valid_sector_name(v) and k not in stock_to_sector:
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
                code_clean = "".join(c for c in code_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in code_str) else code_str
                sec = stock_to_sector.get(code_str) or stock_to_sector.get(code_clean)
                if not sec or not is_valid_sector_name(sec):
                    continue
                    
                if sec not in self.sector_to_codes:
                    self.sector_to_codes[sec] = []
                self.sector_to_codes[sec].append(code_str)
                
                flag_info = consolidation_flags.get(code_str, {}) or consolidation_flags.get(code_clean, {})
                phase = flag_info.get('phase', 'INIT')
                weight = phase_weights.get(phase, 20.0)
                
                sector_scores[sec] = sector_scores.get(sec, 0.0) + weight
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
                
                pct_val = 0.0
                stock_name = ""
                if current_df is not None:
                    row = None
                    if hasattr(main_win, 'get_df_row_safe'):
                        row = main_win.get_df_row_safe(current_df, code_str)
                    elif code_str in current_df.index:
                        row = current_df.loc[code_str]
                    elif code_clean in current_df.index:
                        row = current_df.loc[code_clean]
                    if row is not None:
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
                if not is_valid_sector_name(sec):
                    continue
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

        # ── 3. 终极兜底 ──
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

    def render_grid(self, force=False):
        if not hasattr(self, 'sectors') or not self.sectors:
            # 🛡️ 优雅占位（保持现有样式与尺寸不变，杜绝空白或排版塌陷）
            self.sectors = [
                ("共封装光学", 96.0, "+0.00%", 1),
                ("先进封装", 95.0, "+0.00%", 1),
                ("光纤概念", 93.0, "+0.00%", 1),
                ("铜缆高速", 88.0, "+0.00%", 1),
                ("算力中心", 85.0, "+0.00%", 1),
                ("半导体", 80.0, "+0.00%", 1),
            ]

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_sectors = fav_mgr.get_favorite_sectors()

        w = self.width() if self.width() > 20 else 360
        card_target_w = 92
        cols = max(2, min(5, (w - 20) // (card_target_w + 6)))
        self._current_cols = cols

        # ⚡ [PERF 脏检查] 若 sectors 数据和列数均未变动，直接跳过物理重建
        grid_fingerprint = (cols, tuple((item[0], item[1], item[2]) for item in self.sectors[:30]), tuple(fav_sectors))
        if not force and getattr(self, '_last_rendered_fingerprint', None) == grid_fingerprint:
            return
        self._last_rendered_fingerprint = grid_fingerprint

        # ⚡ [彻底清理] 移出并彻底销毁旧的 QLayoutItem 与卡片 Widget，杜绝卡片多层重叠挤压
        while self.grid_layout.count() > 0:
            layout_item = self.grid_layout.takeAt(0)
            if layout_item:
                old_w = layout_item.widget()
                if old_w is not None:
                    old_w.deleteLater()

        display_items = [it for it in self.sectors if is_valid_sector_name(it[0])][:60]
        rows = max(1, (len(display_items) + cols - 1) // cols)
        needed_h = rows * (68 + 6) + 16
        self.grid_container.setMinimumHeight(needed_h)

        import re
        for idx, item in enumerate(display_items):
            name, score, pct, count = item[:4]
            if not is_valid_sector_name(name):
                continue
            row = idx // cols
            col = idx % cols

            clean_name = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(name)).strip()
            is_highlight = (name in fav_sectors) or (clean_name in fav_sectors)

            # Card Widget - 具有稳固高度与自适应宽度的标准卡片
            card = QPushButton()
            card.setMinimumSize(65, 68)
            card.setMaximumHeight(74)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            if is_highlight:
                bg_style = "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2205, stop:1 #1a1600);"
                border_style = "border: 1.5px solid rgba(255, 215, 0, 0.9);"
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
            card_layout.setContentsMargins(3, 3, 3, 3)
            card_layout.setSpacing(1)
            
            name_lbl = QLabel(display_name)
            name_lbl.setStyleSheet("font-weight: bold; color: #ffffff; background: transparent; font-size: 10pt;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setWordWrap(True)
            
            # 精简分数与涨幅文案 (去掉多余前缀防止横向字符溢出)
            info_lbl = QLabel(f"{score} | {pct}")
            info_lbl.setStyleSheet("color: #e2e2e5; background: transparent; font-size: 8.5pt;")
            info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            count_lbl = QLabel(f"成员: {count}")
            count_lbl.setStyleSheet("color: #aad4ff; background: transparent; font-size: 8pt; font-style: italic;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            card_layout.addWidget(name_lbl)
            card_layout.addWidget(info_lbl)
            card_layout.addWidget(count_lbl)
            
            def _on_card_clicked(checked=False, n=name):
                codes = getattr(self, 'sector_to_codes', {}).get(n, [])
                self.sector_selected.emit(n)
                self.sector_selected_with_codes.emit(n, list(codes))

            card.clicked.connect(_on_card_clicked)
            self.grid_layout.addWidget(card, row, col)

    def sort_sectors(self, index=0):
        def safe_float_pct(val_str):
            try:
                return float(str(val_str).replace("%", "").replace("+", ""))
            except:
                return 0.0

        import re
        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_sectors = fav_mgr.get_favorite_sectors()
        
        # 🛡️ 严格清洗非明确板块
        self.sectors = [s for s in self.sectors if is_valid_sector_name(s[0])]

        def get_sort_key(x):
            sec_name = x[0]
            clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sec_name)).strip()
            # 仅当板块本身在重点关注板块列表时置顶 (prim = 0)
            is_highlight = (sec_name in fav_sectors) or (clean_sec in fav_sectors)
            
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
        if hasattr(self, 'scroll') and self.scroll and self.scroll.verticalScrollBar():
            self.scroll.verticalScrollBar().setValue(0)

        # 🚀 [联动跟随龙头突击跟单榜] 发出排序变化信号并主动触发龙头突击榜刷新
        self.sort_changed.emit(index)
        
        # 💾 [自动持久化] 保存当前所选的排序模式至 window_config.json
        from ats.ui.styles import save_config_node
        try:
            save_config_node("ats_heatmap_sort_index", index)
        except Exception:
            pass

        main_win = self.window()
        p = self.parent()
        while p:
            if hasattr(p, "hot_sector_dialog"):
                main_win = p
                break
            p = p.parent()
        if hasattr(main_win, "hot_sector_dialog") and main_win.hot_sector_dialog:
            from PyQt6.sip import isdeleted
            if not isdeleted(main_win.hot_sector_dialog) and main_win.hot_sector_dialog.isVisible():
                if hasattr(main_win.hot_sector_dialog, "_force_refresh_data"):
                    main_win.hot_sector_dialog._force_refresh_data()



    def _show_sector_context_menu(self, pos, sector_name):
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        from global_favorites import GlobalFavoriteManager
        import re
        
        clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sector_name)).strip()
        fav_mgr = GlobalFavoriteManager()
        fav_sectors = fav_mgr.get_favorite_sectors()
        is_fav = (sector_name in fav_sectors) or (clean_sec in fav_sectors)
        
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
            QMenu::separator {
                height: 1px;
                background-color: #2e2e36;
                margin: 4px 8px;
            }
        """)
        
        if is_fav:
            fav_action = QAction(f"❌ 取消重点关注板块 {clean_sec}", self)
            fav_action.triggered.connect(lambda: self._toggle_favorite_sector(clean_sec))
            menu.addAction(fav_action)
        else:
            fav_action = QAction(f"⭐ 设为重点关注板块 {clean_sec}", self)
            fav_action.triggered.connect(lambda: self._toggle_favorite_sector(clean_sec))
            menu.addAction(fav_action)
            
        menu.addSeparator()

        # 查看成分股明细
        detail_action = QAction(f"🔍 打开【{clean_sec}】成分股明细", self)
        def _open_detail():
            codes = (
                getattr(self, 'sector_to_codes', {}).get(sector_name, []) or 
                getattr(self, 'sector_to_codes', {}).get(clean_sec, [])
            )
            self.sector_selected.emit(clean_sec)
            self.sector_selected_with_codes.emit(clean_sec, list(codes))
            main_win = self.window()
            p = self.parent()
            while p:
                if hasattr(p, "on_sector_clicked"):
                    main_win = p
                    break
                p = p.parent()
            if hasattr(main_win, "on_sector_clicked"):
                main_win.on_sector_clicked(clean_sec, member_codes=list(codes))
        detail_action.triggered.connect(_open_detail)
        menu.addAction(detail_action)

        # 复制板块名称
        copy_action = QAction("📋 复制板块名称", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(clean_sec))
        menu.addAction(copy_action)

        if fav_sectors:
            menu.addSeparator()
            clear_action = QAction(f"🗑️ 清空所有重点关注板块 ({len(fav_sectors)}个)", self)
            def _clear_all_favs():
                for s in list(fav_sectors):
                    fav_mgr.remove_favorite_sector(s)
                self.sort_sectors(self.sort_combo.currentIndex())
            clear_action.triggered.connect(_clear_all_favs)
            menu.addAction(clear_action)
        
        sender_card = self.sender()
        if sender_card:
            global_pos = sender_card.mapToGlobal(pos)
        else:
            global_pos = self.mapToGlobal(pos)
            
        menu.exec(global_pos)

    def _toggle_favorite_sector(self, sector_name):
        try:
            import re
            clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sector_name)).strip()
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_sectors = fav_mgr.get_favorite_sectors()
            
            if clean_sec in fav_sectors or sector_name in fav_sectors:
                fav_mgr.remove_favorite_sector(clean_sec)
                fav_mgr.remove_favorite_sector(sector_name)
            else:
                fav_mgr.add_favorite_sector(clean_sec)

            # 立即原地触发重新排序与网格刷新
            self.sort_sectors(self.sort_combo.currentIndex())
        except Exception as e:
            print(f"[SectorHeatmap] Toggle favorite sector error: {e}")

