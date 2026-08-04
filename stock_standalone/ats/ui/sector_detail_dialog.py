# -*- coding: utf-8 -*-
"""
ATS Sector Detail Dialog
Displays all constituent stocks of a given sector from the bidding session data.
"""

import os
import json
import zlib
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ats.ui.styles import NumericTableWidgetItem, setup_header_persistence, apply_dark_theme, CONFIG_FILE_LOCK
from sys_utils import get_app_root, get_conf_path
from JohnsonUtil import commonTips as cct

class ATSSectorDetailDialog(QDialog):
    def __init__(self, sector_name, linkage_cb=None, double_click_cb=None, member_codes=None, parent=None):
        super().__init__(None) # [🚀 独立窗口解耦] 传入 None 剥离 Win32 HWND Owner 从属关系，防止窗口在 OS 视角下被强制浮在 Parent 主窗口上方
        self._py_parent = parent
        self.sector_name = sector_name
        self.linkage_cb = linkage_cb
        self.double_click_cb = double_click_cb
        self.member_codes = member_codes or []
        
        self.setWindowTitle(f"🔥 {sector_name} 板块明细 (Real-time Sector Details)")
        self.resize(750, 480)
        
        # [🚀 经典黑金 Style] 继承统一的 ATS 暗黑 Mode QSS 风格
        apply_dark_theme(self)
        
        self.setStyleSheet(self.styleSheet() + """
            QDialog {
                background-color: #121214;
                color: #e2e2e5;
            }
            QTableWidget {
                background-color: #18181c;
                alternate-background-color: #1c1c22;
                color: #e2e2e5;
                gridline-color: #2e2e36;
                border: 1px solid #2e2e36;
                selection-background-color: #2a3a4a;
                selection-color: #00ff88;
            }
            QHeaderView::section {
                background-color: #1a1a1f;
                color: #aad4ff;
                font-weight: bold;
                border: 1px solid #2e2e36;
                padding: 3px 6px;
            }
            QTableCornerButton::section {
                background-color: #1a1a1f;
                border: 1px solid #2e2e36;
            }
        """)
        # 明确设置为独立顶层窗口类型，并防止主应用退出
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

        self._init_ui()
        self.load_data()
        self._restore_geometry()
        


    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Title block
        header = QHBoxLayout()
        self.title_lbl = QLabel(f"板块名称: {self.sector_name}")
        self.title_lbl.setStyleSheet("font-size: 13pt; font-weight: bold; color: #00ff88;")
        header.addWidget(self.title_lbl)
        header.addStretch()
        
        self.score_lbl = QLabel("强度得分: --")
        self.score_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ff9900;")
        header.addWidget(self.score_lbl)
        layout.addLayout(header)
        
        # Stats info
        self.stats_lbl = QLabel("成员数: 0 | 领涨股: --")
        self.stats_lbl.setStyleSheet("font-size: 10pt; color: #aad4ff;")
        layout.addWidget(self.stats_lbl)
        
        # Table of members
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "得分", "类型", "涨幅", "起点", "DFF", "Rank", "DFF2", "DFF3", "形态提示"
        ])
        
        # Set headers left align and vertical center
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setStretchLastSection(True)
        
        self.table.setAlternatingRowColors(True)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Connect signals
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.currentItemChanged.connect(self.on_current_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        
        # Bottom action bar
        btn_layout = QHBoxLayout()

        btn_dna = QPushButton("🧬 DNA审计")
        btn_dna.setStyleSheet("""
            QPushButton { background-color: #1b5e20; color: #a5d6a7; border: 1px solid #388e3c;
                          border-radius: 4px; padding: 4px 10px; font-weight: bold; }
            QPushButton:hover { background-color: #2e7d32; }
        """)
        btn_dna.clicked.connect(self._run_dna_audit)
        btn_layout.addWidget(btn_dna)

        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _restore_geometry(self):
        """从 window_config.json 恢复弹窗位置与大小"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                geom = data.get("ats_sector_detail_dialog_geom")
                if geom:
                    from PyQt6.QtCore import QByteArray
                    self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
        except Exception:
            pass

    def _save_geometry(self):
        """原子写盘持久化弹窗位置与大小至 window_config.json"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(cfg_path):
                    try:
                        with open(cfg_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                data["ats_sector_detail_dialog_geom"] = self.saveGeometry().toHex().data().decode('utf-8')
                tmp_path = cfg_path + ".tmp_sector"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, cfg_path)
        except Exception:
            pass

    def closeEvent(self, event):
        """关闭时自动持久化窗口大小与位置"""
        self._save_geometry()
        super().closeEvent(event)

    def accept(self):
        """OK/关闭按钮同样触发持久化"""
        self._save_geometry()
        super().accept()
        
    def _get_parent_mw(self):
        return getattr(self, '_py_parent', None) or self.parent()

    def update_data(self, df_realtime=None):
        """实盘行情更新时调起的无缝刷新接口"""
        # 每次刷新前同步标题 Label，防止窗口复用后显示旧板块名
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"板块名称: {self.sector_name}")
        try:
            self.load_data(df_realtime=df_realtime)
        except Exception:
            pass

    def load_data(self, df_realtime=None):
        # Resolve helper functions & streaming df from parent chain
        get_name_fn = None
        get_row_fn = None
        current_df = df_realtime
        p = self._get_parent_mw()
        while p:
            if hasattr(p, 'get_stock_name'):
                get_name_fn = p.get_stock_name
            if hasattr(p, 'get_df_row_safe'):
                get_row_fn = p.get_df_row_safe
            if current_df is None and hasattr(p, 'current_df'):
                current_df = p.current_df
            if get_name_fn and current_df is not None:
                break
            p = getattr(p, '_py_parent', None) or (p.parent() if hasattr(p, 'parent') and callable(p.parent) else None)

        def _get_row(df, code_str):
            """双 Key 智能查找：先用父窗口安全接口，再降级子串匹配"""
            if get_row_fn:
                return get_row_fn(df, code_str)
            if code_str in df.index:
                return df.loc[code_str]
            c_clean = ''.join(c for c in code_str if c.isdigit())
            if c_clean and c_clean in df.index:
                return df.loc[c_clean]
            return None

        SECTOR_SYNONYMS = {
            "半导体": ["半导体及部件", "半导体", "芯片", "电子元器件"],
            "存储芯片": ["半导体及部件", "存储芯片", "芯片", "电子元器件"],
            "传媒": ["传媒娱乐", "文化传媒", "传媒", "互联网"],
            "软件开发": ["软件服务", "软件开发", "IT设备", "计算机"],
            "国防军工": ["国防军工", "军工", "航天装备", "通用设备"],
            "汽车整车": ["汽车类", "汽车整车", "新能源车", "交运设备"],
            "贵金属": ["贵金属", "黄金", "珠宝首饰"],
            "石油化工": ["石油行业", "石油", "石油化工", "采掘行业", "化学原料"],
            "有色金属": ["有色金属", "有色", "小金属", "稀缺资源", "工业金属"],
            "AI/软件": ["软件服务", "人工智能", "互联网", "软件开发"],
            "金融/权重龙头": ["银行", "证券", "保险"],
            "石油化工/资源": ["石油", "煤炭开采", "化工", "化学原料"]
        }

        # 1. 结合外部传入的 member_codes 与 current_df 中按 category 动态匹配的成分股
        target_codes = set()
        if self.member_codes:
            for c in self.member_codes:
                if str(c).strip():
                    target_codes.add(str(c).strip())

        # 如果 current_df 存在且包含 category 列，自动进行板块关键词与同义词向量化匹配
        if current_df is not None and not current_df.empty and 'category' in current_df.columns:
            try:
                synonyms = [self.sector_name] + SECTOR_SYNONYMS.get(self.sector_name, [])
                pattern = '|'.join([re.escape(s) for s in synonyms if s])
                matched_series = current_df['category'].astype(str).str.contains(pattern, case=False, na=False)
                df_matched = current_df[matched_series]
                if not df_matched.empty:
                    for code_idx in df_matched.index[:60]: # 最多抓取前 60 只活跃成分股
                        target_codes.add(str(code_idx).strip())
            except Exception as e:
                print(f"[SectorDetailDialog] Error matching categories from current_df: {e}")

        # 只要存在目标股票代码或 current_df 包含匹配数据，100% 走实时 IPC 数据渲染
        if target_codes:
            self.setWindowTitle(f"📡 {self.sector_name} 板块明细 (实时IPC)")
            rows = []
            leader_code = ""
            leader_name = ""
            max_pct = -999.0
            
            for code_str in target_codes:
                name = get_name_fn(code_str) if get_name_fn else "个股"
                if not name or name == "未知":
                    name = code_str
                
                score = 60.0
                pct_val = 0.0
                dff_val = 0.0
                rank_val = 0
                dff2_val = 0.0
                dff3_val = 0.0
                pattern_hint = "反转/板块成分"
                
                if current_df is not None:
                    import pandas as pd
                    row = _get_row(current_df, code_str)
                    if row is not None:
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]
                        name_df = str(row.get('name', '')).strip()
                        if name_df and name_df != "未知":
                            name = name_df
                        try: pct_val = float(row.get('percent', 0.0))
                        except: pass
                        try: dff_val = float(row.get('dff', 0.0))
                        except: pass
                        try: rank_val = int(row.get('Rank', row.get('rank', 0)))
                        except: pass
                        try: dff2_val = float(row.get('DFF2', row.get('dff2', 0.0)))
                        except: pass
                        try: dff3_val = float(row.get('DFF3', row.get('dff3', 0.0)))
                        except: pass
                
                if pct_val > max_pct:
                    max_pct = pct_val
                    leader_code = code_str
                    leader_name = name
                    
                rows.append({
                    'code': code_str,
                    'name': name,
                    'score': score,
                    'type': '跟涨',
                    'pct': pct_val,
                    'start_pct': pct_val - dff_val,
                    'dff': dff_val,
                    'rank': rank_val,
                    'dff2': dff2_val,
                    'dff3': dff3_val,
                    'pattern': pattern_hint
                })
                
            # 标记领涨龙头
            for r in rows:
                if r['code'] == leader_code:
                    r['type'] = '👑 领涨'
                    r['score'] = 95.0
                    r['pattern'] = '领涨先锋'
                    
            rows.sort(key=lambda x: x['pct'], reverse=True)
            
            self.score_lbl.setText(f"强度得分: {min(100.0, len(rows) * 12.5):.1f}")
            self.stats_lbl.setText(f"成员数: {len(rows)} | 领涨标的: {leader_name} ({leader_code}) [{max_pct:+.2f}%]")
            
            self._render_rows(rows)
            return

        # 2. 本地快照路径：从 bidding_session_data 读取
        self.setWindowTitle(f"📁 {self.sector_name} 板块明细 (本地快照)")
        SECTOR_SYNONYMS = {
            "半导体": ["半导体及部件", "半导体", "芯片", "电子元器件"],
            "存储芯片": ["半导体及部件", "存储芯片", "芯片", "电子元器件"],
            "传媒": ["传媒娱乐", "文化传媒", "传媒", "互联网"],
            "软件开发": ["软件服务", "软件开发", "IT设备", "计算机"],
            "国防军工": ["国防军工", "军工", "航天装备", "通用设备"],
            "汽车整车": ["汽车类", "汽车整车", "新能源车", "交运设备"],
            "贵金属": ["贵金属", "黄金", "珠宝首饰"],
            "石油化工": ["石油行业", "石油", "石油化工", "采掘行业", "化学原料"],
            "有色金属": ["有色金属", "有色", "小金属", "稀缺资源", "工业金属"],
            "AI/软件": ["软件服务", "人工智能", "互联网", "软件开发"],
            "金融/权重龙头": ["银行", "证券", "保险"],
            "石油化工/资源": ["石油", "煤炭开采", "化工", "化学原料"]
        }

        FAMOUS_SECTOR_LEADERS = {
            "半导体": [("688981", "中芯国际"), ("603501", "韦尔股份"), ("002371", "北方华创"), ("688012", "华海清科"), ("688008", "澜起科技"), ("688036", "传音控股")],
            "存储芯片": [("603986", "兆易创新"), ("688981", "中芯国际"), ("002156", "通富微电"), ("688041", "普冉股份"), ("300661", "圣邦股份"), ("688008", "澜起科技")],
            "传媒": [("300058", "蓝色光标"), ("603533", "掌阅科技"), ("301171", "易点天下"), ("002624", "完美世界"), ("300413", "芒果超媒"), ("002354", "天娱数科")],
            "软件开发": [("300496", "科大讯飞"), ("600588", "用友网络"), ("300033", "指南针"), ("688111", "金山办公"), ("300229", "拓尔思"), ("600570", "恒生电子")],
            "国防军工": [("601606", "长城军工"), ("600118", "中国卫星"), ("002179", "中航光电"), ("600760", "中航沈飞"), ("000768", "中航西飞"), ("600893", "航发动力")],
            "汽车整车": [("600733", "北汽蓝谷"), ("002594", "比亚迪"), ("601633", "长城汽车"), ("601127", "赛力斯"), ("600104", "上汽集团"), ("000625", "长安汽车")],
            "贵金属": [("601899", "紫金矿业"), ("600988", "赤峰黄金"), ("600547", "山东黄金"), ("600489", "中金黄金"), ("000975", "山金国际")],
            "石油化工": [("600938", "中国海油"), ("601857", "中国石油"), ("600583", "中海油服"), ("600028", "中国石化"), ("600346", "恒力石化")],
            "有色金属": [("603993", "洛阳钼业"), ("601899", "紫金矿业"), ("600362", "江西铜业"), ("601600", "中国铝业"), ("000630", "铜陵有色")],
            "AI/软件": [("300058", "蓝色光标"), ("300496", "科大讯飞"), ("688111", "金山办公"), ("300033", "指南针"), ("603533", "掌阅科技")],
            "金融/权重龙头": [("600036", "招商银行"), ("601318", "中国平安"), ("600030", "中信证券"), ("601688", "华泰证券")],
            "石油化工/资源": [("601857", "中国石油"), ("600028", "中国石化"), ("600938", "中国海油"), ("601088", "中国神华")]
        }

        # 3. Fetch sector data from bidding_session_data
        path = None
        try:
            ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
            if ram_path and os.path.exists(ram_path):
                path = ram_path
        except Exception:
            pass
            
        if not path:
            try:
                base = get_app_root()
                fallback_path = os.path.abspath(os.path.join(base, "snapshots", "bidding_session_data.json.gz"))
                if os.path.exists(fallback_path):
                    path = fallback_path
            except Exception:
                pass

        sector_data = {}
        if path and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    raw_data = f.read()
                json_str = zlib.decompress(raw_data).decode('utf-8')
                data = json.loads(json_str)
                sector_data = data.get('sector_data', {})
            except Exception:
                pass

        # 优先精准查找
        sec_info = sector_data.get(self.sector_name)

        # 降级 1: 同义词模糊查找
        if not sec_info and sector_data:
            syns = SECTOR_SYNONYMS.get(self.sector_name, [])
            for syn in syns:
                if syn in sector_data:
                    sec_info = sector_data[syn]
                    break

        # 降级 2: 子串包络查找
        if not sec_info and sector_data:
            for s_key, s_val in sector_data.items():
                if self.sector_name in s_key or s_key in self.sector_name:
                    sec_info = s_val
                    break

        # 如果在 sector_data 中找到了板块特征
        if sec_info:
            try:
                score = sec_info.get('score', 0.0)
                self.score_lbl.setText(f"强度得分: {score:.1f}")
                
                leader_code = str(sec_info.get('leader', '')).strip()
                leader_name = sec_info.get('leader_name', '')
                if not leader_name and get_name_fn and leader_code:
                    leader_name = get_name_fn(leader_code)
                if not leader_name or leader_name == "未知":
                    leader_name = sec_info.get('leader_name') or leader_code
                    
                leader_pct = sec_info.get('leader_pct', 0.0)
                leader_dff = sec_info.get('leader_dff') or sec_info.get('leader_pct_diff') or 0.0
                leader_score = sec_info.get('leader_score', 0.0)
                
                followers = sec_info.get('followers', [])
                self.stats_lbl.setText(f"成员数: {len(followers) + (1 if leader_code else 0)} | 领涨龙头: {leader_name} ({leader_code})")
                
                leader_rank = 0
                leader_dff2 = 0.0
                leader_dff3 = 0.0
                if current_df is not None and leader_code:
                    import pandas as pd
                    l_row = _get_row(current_df, leader_code)
                    if l_row is not None:
                        if isinstance(l_row, pd.DataFrame):
                            l_row = l_row.iloc[0]
                        try: leader_rank = int(l_row.get('Rank', l_row.get('rank', 0)))
                        except: pass
                        try: leader_dff2 = float(l_row.get('DFF2', l_row.get('dff2', 0.0)))
                        except: pass
                        try: leader_dff3 = float(l_row.get('DFF3', l_row.get('dff3', 0.0)))
                        except: pass

                # Combine leader and followers into rows list
                rows = []
                if leader_code:
                    rows.append({
                        'code': leader_code,
                        'name': leader_name,
                        'score': leader_score,
                        'type': '👑 龙头',
                        'pct': leader_pct,
                        'start_pct': leader_pct - leader_dff,
                        'dff': leader_dff,
                        'rank': leader_rank,
                        'dff2': leader_dff2,
                        'dff3': leader_dff3,
                        'pattern': '领涨先锋'
                    })
                    
                for fol in followers:
                    f_code = str(fol.get('code', '')).strip()
                    if not f_code or f_code == leader_code:
                        continue
                    f_name = fol.get('name', '')
                    if not f_name and get_name_fn:
                        f_name = get_name_fn(f_code)
                    if not f_name or f_name == "未知":
                        f_name = fol.get('name') or f_code
                    f_pct = fol.get('pct', 0.0)
                    f_dff = fol.get('dff') or fol.get('pct_diff') or 0.0
                    f_rank = 0
                    f_dff2 = 0.0
                    f_dff3 = 0.0
                    if current_df is not None:
                        import pandas as pd
                        f_row = _get_row(current_df, f_code)
                        if f_row is not None:
                            if isinstance(f_row, pd.DataFrame):
                                f_row = f_row.iloc[0]
                            try: f_rank = int(f_row.get('Rank', f_row.get('rank', 0)))
                            except: pass
                            try: f_dff2 = float(f_row.get('DFF2', f_row.get('dff2', 0.0)))
                            except: pass
                            try: f_dff3 = float(f_row.get('DFF3', f_row.get('dff3', 0.0)))
                            except: pass
                        
                    rows.append({
                        'code': f_code,
                        'name': f_name,
                        'score': fol.get('score', 0.0),
                        'type': '跟涨',
                        'pct': f_pct,
                        'start_pct': f_pct - f_dff,
                        'dff': f_dff,
                        'rank': f_rank,
                        'dff2': f_dff2,
                        'dff3': f_dff3,
                        'pattern': fol.get('pattern_hint', '')
                    })
                    
                self._render_rows(rows)
                return
            except Exception as e:
                print(f"Error loading sector detail rows: {e}")
                self.stats_lbl.setText(f"❌ 加载出错: {e}")

        # 降级 3: 若仍无数据，使用国内优质知名龙头股 Fallback 兜底渲染
        famous_list = None
        for key, st_list in FAMOUS_SECTOR_LEADERS.items():
            if key == self.sector_name or key in self.sector_name or self.sector_name in key:
                famous_list = st_list
                break
        
        if famous_list:
            rows = []
            leader_code = ""
            leader_name = ""
            max_pct = -999.0
            
            for code_str, def_name in famous_list:
                name = get_name_fn(code_str) if get_name_fn else def_name
                if not name or name == "未知":
                    name = def_name
                
                score = 75.0
                pct_val = 0.0
                dff_val = 0.0
                rank_val = 0
                dff2_val = 0.0
                dff3_val = 0.0
                pattern_hint = "国内知名行业龙头"
                
                if current_df is not None and code_str in current_df.index:
                    import pandas as pd
                    row = current_df.loc[code_str]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    name_df = str(row.get('name', '')).strip()
                    if name_df and name_df != "未知":
                        name = name_df
                    try: pct_val = float(row.get('percent', 0.0))
                    except: pass
                    try: dff_val = float(row.get('dff', 0.0))
                    except: pass
                    try: rank_val = int(row.get('Rank', row.get('rank', 0)))
                    except: pass
                    try: dff2_val = float(row.get('DFF2', row.get('dff2', 0.0)))
                    except: pass
                    try: dff3_val = float(row.get('DFF3', row.get('dff3', 0.0)))
                    except: pass
                
                if pct_val > max_pct:
                    max_pct = pct_val
                    leader_code = code_str
                    leader_name = name
                    
                rows.append({
                    'code': code_str,
                    'name': name,
                    'score': score,
                    'type': '行业龙头',
                    'pct': pct_val,
                    'start_pct': pct_val - dff_val,
                    'dff': dff_val,
                    'rank': rank_val,
                    'dff2': dff2_val,
                    'dff3': dff3_val,
                    'pattern': pattern_hint
                })
                
            for r in rows:
                if r['code'] == leader_code:
                    r['type'] = '👑 领涨龙头'
                    r['score'] = 98.0
                    r['pattern'] = '板块中军龙头'
                    
            rows.sort(key=lambda x: x['pct'], reverse=True)
            
            self.score_lbl.setText(f"强度得分: {min(100.0, len(rows) * 16.0):.1f}")
            self.stats_lbl.setText(f"成员数: {len(rows)} | 领涨标的: {leader_name} ({leader_code}) [{max_pct:+.2f}%]")
            
            self._render_rows(rows)
            return

        self.stats_lbl.setText("❌ 当前板块暂无成分股明细特征")

    def _render_rows(self, rows):
        self._is_rendering = True
        self.table.blockSignals(True)
        try:
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(rows))
            
            for row_idx, r in enumerate(rows):
                # 0. Code
                code_item = QTableWidgetItem(str(r['code']))
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 0, code_item)
                
                # 1. Name
                name_item = QTableWidgetItem(str(r['name']))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 1, name_item)
                
                # 2. Score
                score_item = NumericTableWidgetItem(f"{r['score']:.1f}")
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 2, score_item)
                
                # 3. Type
                type_item = QTableWidgetItem(str(r['type']))
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if '👑' in r['type']:
                    type_item.setForeground(QColor("#ffcc00")) # gold
                self.table.setItem(row_idx, 3, type_item)
                
                # 4. Pct
                pct_val = r['pct']
                pct_str = f"{pct_val:+.2f}%"
                pct_item = NumericTableWidgetItem(pct_str)
                pct_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if pct_val > 0.001:
                    pct_item.setForeground(QColor("#ff4444"))
                elif pct_val < -0.001:
                    pct_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 4, pct_item)
                
                # 5. Start Pct
                start_val = r['start_pct']
                start_str = f"{start_val:+.2f}%"
                start_item = NumericTableWidgetItem(start_str)
                start_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if start_val > 0.001:
                    start_item.setForeground(QColor("#ff4444"))
                elif start_val < -0.001:
                    start_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 5, start_item)
                
                # 6. DFF
                dff_val = r['dff']
                dff_str = f"{dff_val:+.2f}%"
                dff_item = NumericTableWidgetItem(dff_str)
                dff_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff_val > 0.001:
                    dff_item.setForeground(QColor("#ff4444"))
                elif dff_val < -0.001:
                    dff_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 6, dff_item)
                
                # 7. Rank
                rank_item = NumericTableWidgetItem(str(r['rank']))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 7, rank_item)
                
                # 8. DFF2
                dff2_val = r['dff2']
                dff2_item = NumericTableWidgetItem(f"{dff2_val:+.2f}%")
                dff2_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff2_val > 0.001:
                    dff2_item.setForeground(QColor("#ff4444"))
                elif dff2_val < -0.001:
                    dff2_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 8, dff2_item)
                
                # 9. DFF3
                dff3_val = r['dff3']
                dff3_item = NumericTableWidgetItem(f"{dff3_val:+.2f}%")
                dff3_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff3_val > 0.001:
                    dff3_item.setForeground(QColor("#ff4444"))
                elif dff3_val < -0.001:
                    dff3_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 9, dff3_item)
                
                # 10. Pattern
                pat_item = QTableWidgetItem(str(r['pattern'] or '--'))
                pat_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 10, pat_item)
                
            self.table.setSortingEnabled(True)
            self.table.resizeColumnsToContents()
            self.table.clearSelection()
            
            # Setup columns minimum widths or interactive persistence
            setup_header_persistence(self.table, f"ats_sector_detail_table_{self.sector_name}")
        finally:
            self.table.blockSignals(False)
            self._is_rendering = False
            
    def on_item_clicked(self, item):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.linkage_cb:
            code = code_item.text().strip()
            name = name_item.text().strip()
            if getattr(self, '_last_linked_code', None) != code:
                self._last_linked_code = code
                self.linkage_cb(code, name)
            
    def on_current_item_changed(self, current, previous):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        if current and self.linkage_cb:
            row = current.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                code = code_item.text().strip()
                name = name_item.text().strip()
                if getattr(self, '_last_linked_code', None) != code:
                    self._last_linked_code = code
                    self.linkage_cb(code, name)
                
    def on_item_double_clicked(self, item):
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.double_click_cb:
            self.double_click_cb(code_item.text().strip(), name_item.text().strip())

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else ""
        if not code:
            return

        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        from ats.ui.base_table import send_to_linkage

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

        # 选中联动
        if self.linkage_cb:
            link_act = menu.addAction(f"⚡ 选中联动 ({code})")
            link_act.triggered.connect(lambda: self.linkage_cb(code, name))

        # 发送到异动联动
        pipe_act = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        pipe_act.triggered.connect(lambda: send_to_linkage(code, name, self))

        menu.addSeparator()

        copy_code_act = menu.addAction("📋 复制代码")
        copy_code_act.triggered.connect(lambda: QApplication.clipboard().setText(code))
        copy_name_act = menu.addAction("📋 复制名称")
        copy_name_act.triggered.connect(lambda: QApplication.clipboard().setText(name))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _run_dna_audit(self):
        """对板块内所有成员股（按表格顺序，最多20只）执行 DNA 审计。
        优先通过主程序 parent_app._run_dna_audit_batch，降级到本地 QtDnaAuditReportWindow。
        """
        rows = self.table.rowCount()
        if rows == 0:
            return

        # Collect all member stocks from the table (code in col 0, name in col 1)
        items = []
        for r in range(rows):
            c_it = self.table.item(r, 0)
            n_it = self.table.item(r, 1)
            if c_it and n_it:
                items.append((c_it.text().strip(), n_it.text().strip()))

        # Align with chart_widgets.py selection logic:
        #   multi-select  → all selected rows (up to 50)
        #   single-select → current row + next 19 rows (total ≤ 20)
        #   no selection  → first 20 rows of the table
        sel_rows = sorted(set(i.row() for i in self.table.selectedItems()))
        if len(sel_rows) > 1:
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip()) for r in sel_rows[:50]
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip())
                      for r in range(start, min(start + 20, rows))
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        else:
            target = items[:20]

        code_to_name = {c: n for c, n in target if c}
        if not code_to_name:
            return

        # Try main app first
        main_app = getattr(self.parent(), 'parent_app', None)
        if not main_app:
            main_app = getattr(self.window(), 'parent_app', None)
        if not main_app:
            main_app = getattr(QApplication.instance(), 'parent_app', None)

        if main_app and hasattr(main_app, '_run_dna_audit_batch'):
            if hasattr(main_app, 'tk_dispatch_queue'):
                _cn = dict(code_to_name)
                main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
            else:
                main_app._run_dna_audit_batch(code_to_name)
            return

        # ATSMainWindow or any Qt window with _run_dna_audit_batch
        win = self.window()
        if hasattr(win, '_run_dna_audit_batch'):
            win._run_dna_audit_batch(code_to_name)
            return

        # Local PyQt6 fallback (packaged env)
        try:
            from backtest_feature_auditor import audit_multiple_codes
            from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            # 尝试从 parent 链或活跃窗口中获取包含自定义列的 DataFrame
            _period_data = None
            try:
                p = self.parent() or self.window()
                while p:
                    for attr in ('_last_flat_df', 'last_result_df', 'flat_df', 'result_df', 'df_all', 'current_df', 'top_now'):
                        df_cand = getattr(p, attr, None)
                        if df_cand is not None and not df_cand.empty:
                            _period_data = df_cand
                            break
                    if _period_data is not None:
                        break
                    p = p.parent() if hasattr(p, 'parent') and callable(p.parent) else None
            except Exception:
                pass
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=None,
                code_to_name=code_to_name,
                progress_callback=None,
                resample='d',
                period_data=_period_data
            )
            if summaries:
                self._dna_audit_win = QtDnaAuditReportWindow(
                    summaries, parent=self.window(), end_date=None, resample='d'
                )
                self._dna_audit_win.show()
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "DNA 审计", "没有产生审计数据或结论。")
        except Exception as e:
            print(f"[ATSSectorDetailDialog] DNA audit local fallback failed: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def closeEvent(self, event):
        self._save_geometry()
        # Save header state of the table
        if hasattr(self.table, 'save_column_widths'):
            try:
                self.table.save_column_widths()
            except Exception:
                pass
        super().closeEvent(event)
