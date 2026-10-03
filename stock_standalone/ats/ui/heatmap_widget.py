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
import threading
from functools import lru_cache
from typing import Dict, Any, List, Optional
import pandas as pd
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
from ats.hot_sector_engine import is_valid_sector_name

@lru_cache(maxsize=8)
def _read_sector_json(path, mtime):
    import gzip
    with open(path, 'rb') as handle:
        raw = handle.read()
    if path.endswith('.gz'):
        try:
            raw = zlib.decompress(raw)
        except Exception:
            raw = gzip.decompress(raw)
    else:
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            raw = zlib.decompress(raw)
    return json.loads(raw.decode('utf-8'))

def _read_sector_snapshot_sources():
    """Read and decode cold sector sources outside the GUI thread."""
    import glob
    import re

    base = get_app_root()
    try:
        non_trade_day = not cct.get_day_istrade_date()
    except Exception:
        non_trade_day = False

    path = None
    snapshot_dir = os.path.join(base, 'snapshots')
    if non_trade_day:
        try:
            last_trade = str(cct.get_last_trade_date()).replace('-', '')
            candidates = glob.glob(os.path.join(snapshot_dir, f'bidding_{last_trade}.json.gz'))
            path = candidates[-1] if candidates else None
        except Exception:
            pass
    else:
        try:
            ram_path = cct.get_ramdisk_path('bidding_session_data.json.gz')
            if ram_path and os.path.exists(ram_path):
                path = ram_path
        except Exception:
            pass
        if path is None:
            session_path = os.path.join(snapshot_dir, 'bidding_session_data.json.gz')
            if os.path.exists(session_path):
                path = session_path
            else:
                candidates = sorted(f for f in glob.glob(os.path.join(snapshot_dir, 'bidding_*.json.gz'))
                                    if re.search(r'bidding_\d{8}\.json\.gz$', f))
                path = candidates[-1] if candidates else None

    def read_json(path):
        return _read_sector_json(path, os.path.getmtime(path))

    sector_data = {}
    if path and os.path.exists(path):
        try:
            sector_data = read_json(path).get('sector_data', {}) or {}
        except Exception as exc:
            print(f'[SectorHeatmapWidget] Error loading bidding snapshot: {exc}')
    usable_sectors = sum(1 for name in sector_data
                         if is_valid_sector_name(name)
                         and not any(ex in name for ex in ('实时报警', '系统报警', '异动汇总', '报警标注')))
    if usable_sectors >= 3 or non_trade_day:
        return non_trade_day, sector_data, [], {}, {}

    try:
        ram_path = cct.get_ramdisk_path('v_reversal_pool.json')
    except Exception:
        ram_path = None
    logs_dir = os.path.join(base, 'logs')
    if ram_path and os.path.exists(ram_path):
        reversal_path = ram_path
    elif os.path.exists(os.path.join(logs_dir, 'v_reversal_pool.json')):
        reversal_path = os.path.join(logs_dir, 'v_reversal_pool.json')
    else:
        files = sorted(glob.glob(os.path.join(logs_dir, 'v_reversal_pool_*.json.gz')))
        reversal_path = files[-1] if files else None

    reversal_pool, flags, bidding_map = [], {}, {}
    if reversal_path:
        try:
            reversal = read_json(reversal_path)
            reversal_pool = reversal.get('v_reversal_pool', []) or []
            flags = reversal.get('consolidation_flags', {}) or {}
        except Exception as exc:
            print(f'[SectorHeatmapWidget] Error loading reversal pool: {exc}')
    if reversal_pool:
        candidates = sorted((f for f in glob.glob(os.path.join(snapshot_dir, 'bidding_*.json.gz'))
                             if re.search(r'bidding_\d{8}\.json\.gz$', f)), reverse=True)
        for snapshot_path in candidates[:3]:
            try:
                for sector_name, info in read_json(snapshot_path).get('sector_data', {}).items():
                    if (not is_valid_sector_name(sector_name)
                            or any(ex in sector_name for ex in ('实时报警', '系统报警', '异动汇总', '报警标注'))):
                        continue
                    codes = [info.get('leader', '')] + [row.get('code', '') for row in info.get('followers', [])]
                    for code in codes:
                        code = str(code).strip()
                        if code:
                            bidding_map[code] = sector_name
                            cleaned = ''.join(c for c in code if c.isdigit()).zfill(6) if any(c.isdigit() for c in code) else code
                            bidding_map[cleaned] = sector_name
            except Exception:
                pass
    return non_trade_day, sector_data, reversal_pool, flags, bidding_map


def _aggregate_reversal_sectors(current_df, v_reversal_pool, consolidation_flags, bidding_map):
    # Map codes to sector
    stock_to_sector = {}
    # Build quote aliases once, including prefixed indices and code columns.
    quotes = {}
    if current_df is not None and not current_df.empty:
        for idx, row in zip(current_df.index, current_df.to_dict('records')):
            keys = [str(idx).strip()]
            if row.get('code') is not None:
                keys.append(str(row['code']).strip())
            for key in keys:
                quotes.setdefault(key, row)
                digits = ''.join(c for c in key if c.isdigit())
                if digits and not (isinstance(current_df.index, pd.RangeIndex) and key == str(idx)):
                    quotes.setdefault(digits.zfill(6), row)

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

    # Combine real-time categories and snapshot fallbacks
    for k, v in bidding_map.items():
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
    sector_to_codes = {}

    for code in v_reversal_pool:
        code_str = str(code).strip()
        code_clean = "".join(c for c in code_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in code_str) else code_str
        sec = stock_to_sector.get(code_str) or stock_to_sector.get(code_clean)
        if not sec or not is_valid_sector_name(sec):
            continue

        if sec not in sector_to_codes:
            sector_to_codes[sec] = []
        sector_to_codes[sec].append(code_str)

        flag_info = consolidation_flags.get(code_str, {}) or consolidation_flags.get(code_clean, {})
        phase = flag_info.get('phase', 'INIT')
        weight = phase_weights.get(phase, 20.0)

        sector_scores[sec] = sector_scores.get(sec, 0.0) + weight
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

        pct_val = 0.0
        stock_name = ""
        if current_df is not None:
            row = quotes.get(code_str) or quotes.get(code_clean)
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

    return sectors_list, sector_to_codes

class SectorHeatmapWidget(QWidget):
    sector_selected = pyqtSignal(str) # sector name
    sector_selected_with_codes = pyqtSignal(str, list) # sector name, member codes list
    hot_leaders_clicked = pyqtSignal() # 龙头突击榜点击
    sort_changed = pyqtSignal(int) # 排序维度切换 (0: 强度得分, 1: 涨跌幅, 2: 活跃成员数)
    _snapshot_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshot_ready.connect(self._on_snapshot_ready)
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
        new_sector_to_codes = {}
        for sec_name, info in sector_data.items():
            clean_sec = str(sec_name).strip()
            # 🛡️ 严格过滤 '--', '0', 'nan', '未知' 等非明确板块以及虚拟系统聚合池 (如 "实时报警" / "🔔 实时报警")
            if not is_valid_sector_name(clean_sec):
                continue
            if any(ex in clean_sec for ex in ("实时报警", "系统报警", "异动汇总", "报警标注")):
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
            new_sector_to_codes[clean_sec] = list(codes_set)
            sectors_list.append(
                (clean_sec, round(score, 1), change_pct_str, count, leader_code, leader_name)
            )

        # 🛡️ [防残缺覆盖保护]
        # 只有提取出 >= 3 个真实有效板块时，才视为全量权威更新；
        # 若 < 3 个（例如冷启动尚未生成板块强度，或仅有系统报警空包），坚决不覆盖已有的大盘板块快照！
        if len(sectors_list) >= 3:
            self._has_live_ipc_data = True
            self.sector_to_codes = new_sector_to_codes
            self.sectors = sectors_list
            self._cached_session_sectors = list(sectors_list)
            self.sort_sectors(self.sort_combo.currentIndex())
        elif (not getattr(self, '_snapshot_applying', False)
              and (not getattr(self, 'sectors', None) or len(self.sectors) < 3)):
            self.load_live_sectors(force=True)

    def load_live_sectors(self, force=False, current_df=None):
        if not self.isVisible() and not force:
            return
        if (getattr(self, '_has_live_ipc_data', False)
                and getattr(self, 'sectors', None) and len(self.sectors) >= 3):
            return

        import time
        now = time.time()
        if not force and now - getattr(self, '_last_load_time', 0.0) < 5.0:
            return
        if getattr(self, '_snapshot_busy', False):
            return
        self._last_load_time = now
        if not isinstance(current_df, pd.DataFrame) or current_df.empty:
            parent = self.parent()
            while parent is not None:
                candidate = getattr(parent, 'current_df', None)
                if isinstance(candidate, pd.DataFrame) and not candidate.empty:
                    current_df = candidate
                    break
                parent = parent.parent()
            if not isinstance(current_df, pd.DataFrame) or current_df.empty:
                current_df = getattr(self.window(), 'current_df', None)
        self._snapshot_busy = True

        def worker():
            try:
                result = _read_sector_snapshot_sources()
                aggregate = None
                if result is not None:
                    nontrade, raw, pool, flags, bidding = result
                    if not nontrade and pool:
                        aggregate = _aggregate_reversal_sectors(current_df, pool, flags, bidding)
            except Exception as exc:
                print(f'[SectorHeatmapWidget] Snapshot read failed: {exc}')
                result = None
                aggregate = None
            try:
                self._snapshot_ready.emit((result, aggregate))
            except RuntimeError:
                pass

        try:
            threading.Thread(target=worker, daemon=True, name='ATS-SectorSnapshot').start()
        except Exception as exc:
            self._snapshot_busy = False
            self._last_load_time = 0.0
            print(f'[SectorHeatmapWidget] Cannot start snapshot worker: {exc}')

    def _on_snapshot_ready(self, payload):
        self._snapshot_busy = False
        result, aggregate = payload
        if result is None or (getattr(self, '_has_live_ipc_data', False)
                              and getattr(self, 'sectors', None) and len(self.sectors) >= 3):
            return
        non_trade_day, raw_sector_data, reversal_pool, flags, bidding_map = result
        if bidding_map or not hasattr(self, '_bidding_stock_to_sector'):
            self._bidding_stock_to_sector = bidding_map
        if raw_sector_data:
            self._snapshot_applying = True
            had_live_ipc_data = getattr(self, '_has_live_ipc_data', False)
            previous_session = getattr(self, '_cached_session_sectors', None)
            try:
                self.update_from_tk_sector_data(raw_sector_data)
            finally:
                self._has_live_ipc_data = had_live_ipc_data
                self._snapshot_applying = False
            if getattr(self, '_cached_session_sectors', None) is not previous_session:
                return
        if non_trade_day:
            self._non_trade_snapshot_missing = True
            self._cached_raw_sector_data = {}
            self.sectors = []
            self.sector_to_codes = {}
            self.render_grid(force=True)
            return
        self._non_trade_snapshot_missing = False
        if reversal_pool:
            self._cached_v_reversal_pool = reversal_pool
            self._cached_consolidation_flags = flags
            if aggregate and aggregate[0]:
                self.sectors, self.sector_to_codes = aggregate
                self.sort_sectors(self.sort_combo.currentIndex())
            elif not getattr(self, 'sectors', None):
                self.sector_to_codes = {}
                self.load_mock_sectors()
            return
        if not getattr(self, 'sectors', None):
            self.sector_to_codes = {}
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
        if (not hasattr(self, 'sectors') or not self.sectors) and not getattr(self, '_non_trade_snapshot_missing', False):
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

        display_items = [it for it in self.sectors if is_valid_sector_name(it[0])][:60]
        grid_fingerprint = (cols, tuple(tuple(item[:4]) for item in display_items), tuple(sorted(fav_sectors)))
        if not force and getattr(self, '_last_rendered_fingerprint', None) == grid_fingerprint:
            return
        structure = (cols, tuple(item[0] for item in display_items))
        reuse = getattr(self, '_grid_structure', None) == structure
        if not reuse:
            while self.grid_layout.count() > 0:
                layout_item = self.grid_layout.takeAt(0)
                if layout_item and layout_item.widget() is not None:
                    layout_item.widget().deleteLater()
            self._grid_cards = []

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

            card_state = (tuple(item[:4]), is_highlight)
            if reuse:
                card, name_lbl, info_lbl, count_lbl = self._grid_cards[idx]
                if getattr(card, '_sector_render_state', None) == card_state:
                    continue
                name_lbl.setText(f"⭐ {name}" if is_highlight else str(name))
                info_lbl.setText(f"{score} | {pct}")
                count_lbl.setText(f"成员: {count}")
            else:
                card = None

            # Card Widget - 具有稳固高度与自适应宽度的标准卡片
            if card is None:
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
            
            card._sector_render_state = card_state
            if reuse:
                continue

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
            self._grid_cards.append((card, name_lbl, info_lbl, count_lbl))

        self._grid_structure = structure
        self._last_rendered_fingerprint = grid_fingerprint

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

