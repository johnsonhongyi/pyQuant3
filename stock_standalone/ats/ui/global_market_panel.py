# -*- coding: utf-8 -*-
"""
ATS Global Market Panel ("🌐 全球外盘与热点情绪看板" 专属 Tab 页面)
实时查看美股 7 巨头 (NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA)、
存储芯片 (美光 MU)、半导体 (TSM, SOXX)、富时 A50、大宗商品与 A 股热点板块连带提权分。

核心功能:
1. 顶部宏观与热点摘要卡片 (M7、存储芯片/半导体、A50/汇率、大宗商品)。
2. 全球 15+ 核心外盘资产极速明细表 (含行情、涨跌幅、关联 A 股板块及趋势)。
3. A 股热点板块连带 Boost 提权分与专属 Signal Tag 看板。
4. 异步后台线程 (GlobalMarketWorker) 支持即时一键强制刷新与 30 分钟缓存自适应更新。
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGridLayout, QHeaderView, QTableWidgetItem, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QColor, QFont
import time
import datetime

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_WARN, COLOR_ACCENT, NumericTableWidgetItem, PinnedNumericTableWidgetItem


class GlobalMarketWorker(QThread):
    """后台异步抓取/更新外盘行情 worker"""
    finished_signal = pyqtSignal(dict, float, str, dict, dict) # quotes, score, label, sector_boosts, metadata

    def __init__(self, force_refresh: bool = False, parent=None):
        super().__init__(parent)
        self.force_refresh = force_refresh

    def run(self):
        try:
            from JSONData.global_market_data import (
                fetch_global_market_quotes,
                get_global_sentiment_score,
                get_sector_global_boost,
                get_global_market_quotes_metadata,
                fetch_symbol_financial_news
            )

            quotes = fetch_global_market_quotes(force_refresh=self.force_refresh)
            score, label = get_global_sentiment_score()
            meta = get_global_market_quotes_metadata()
            meta['force_refresh'] = self.force_refresh

            # 若强制刷新，同步预刷新自选热榜新闻
            if self.force_refresh:
                try:
                    fetch_symbol_financial_news('A50', '富时A50', force_refresh=True)
                except Exception:
                    pass

            sectors = ["存储芯片", "半导体", "传媒", "软件开发", "国防军工", "汽车整车", "贵金属", "石油化工", "有色金属"]
            boosts = {}
            for sec in sectors:
                b_val, g_tag = get_sector_global_boost(sec)
                boosts[sec] = (b_val, g_tag)

            self.finished_signal.emit(quotes, score, label, boosts, meta)
        except Exception as e:
            self.finished_signal.emit({}, 0.0, f"⚠️ 更新失败: {e}", {}, {'is_live_network': False, 'error': str(e)})


class GlobalMarketPanel(QWidget):
    """🌐 全球外盘与热点情绪看板页"""

    sector_selected = pyqtSignal(str) # 选中板块信号
    stock_selected = pyqtSignal(str, str, dict) # 选中股票详情弹窗信号
    stock_linked = pyqtSignal(str, str) # 单击个股轻量联动信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self.pinned_symbols = []
        self.pinned_sectors = []
        self._last_quotes = {}
        self._last_boosts = {}
        self._restore_pinned_symbols()
        self._restore_pinned_sectors()
        self._init_ui()
        self._start_auto_refresh_timer()

        # 连接全局代理与日志变更信号，实现跨窗口 100% 实时同步与跟持久化数据一致
        try:
            from ats.ui.proxy_dialog import GLOBAL_PROXY_EVENT_BRIDGE, GLOBAL_LOG_EVENT_BRIDGE
            GLOBAL_PROXY_EVENT_BRIDGE.proxy_changed_signal.connect(self._on_global_proxy_changed)
            GLOBAL_LOG_EVENT_BRIDGE.log_toggled_signal.connect(self._on_global_log_changed)
        except Exception as ex:
            pass

        # 初始装载数据
        self.refresh_data(force=False)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---------------- 1. 顶部 Header 与操作栏 (紧凑高性价比布局) ----------------
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #161a22; border-radius: 4px; padding: 2px; }")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 3, 6, 3)

        title = QLabel("🌐 全球外盘情绪与热点板块连带看板")
        title.setStyleSheet("font-weight: bold; color: #00e5ff; font-size: 10.5pt;")
        header_layout.addWidget(title)

        self.lbl_sentiment = QLabel("🌐 外盘整体情绪: --")
        self.lbl_sentiment.setStyleSheet("font-weight: bold; color: #ffd700; font-size: 9.5pt; margin-left: 8px;")
        header_layout.addWidget(self.lbl_sentiment)

        self.lbl_status = QLabel("状态: 磁盘缓存模式")
        self.lbl_status.setStyleSheet("color: #888888; font-size: 8.5pt; margin-left: 8px;")
        header_layout.addWidget(self.lbl_status)

        header_layout.addStretch()

        self.btn_log_config = QPushButton("📜 日志: 关")
        self.btn_log_config.clicked.connect(self._toggle_log_config)
        self._update_log_btn_style()
        header_layout.addWidget(self.btn_log_config)

        self.btn_proxy_config = QPushButton("🌐 代理: 关")
        self.btn_proxy_config.clicked.connect(self._open_proxy_dialog)
        self._update_proxy_btn_style()
        header_layout.addWidget(self.btn_proxy_config)

        self.lbl_update_time = QLabel("最后更新: --:--:--")
        self.lbl_update_time.setStyleSheet("color: #aaa; font-size: 8.5pt; margin-left: 4px; margin-right: 6px;")
        header_layout.addWidget(self.lbl_update_time)

        self.btn_refresh = QPushButton("🔄 强制实时刷新外盘")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #00e5ff; font-weight: bold;
                border: 1px solid #00e5ff; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #00e5ff; color: #000; }
            QPushButton:disabled { background-color: #2a2a33; color: #666; border: 1px solid #444; }
        """)
        self.btn_refresh.clicked.connect(lambda: self.refresh_data(force=True))
        header_layout.addWidget(self.btn_refresh)

        layout.addWidget(header_frame)


        # ---------------- 2. 上下垂直主 Splitter (v_splitter) ----------------
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setChildrenCollapsible(False)

        # ---- 上部分: 紧凑外盘 4 大摘要卡片区域 ----
        cards_widget = QWidget()
        cards_layout = QHBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(4)

        self.card_m7 = self._create_card("💻 美股7巨头 (M7/AI)", "--", "NVDA / AAPL / MSFT / GOOGL", "#00e5ff")
        self.card_semi = self._create_card("💾 存储芯片 & 半导体", "--", "美光 MU / TSM / SOXX", "#ff007f")
        self.card_macro = self._create_card("🏛️ 富时 A50 & 汇率", "--", "A50 期货 / 离岸 RMB", "#ffd700")
        self.card_commodity = self._create_card("🛢️ 美原油 & 美黄金", "--", "美原油 / 美黄金", "#00ff88")

        cards_layout.addWidget(self.card_m7['frame'])
        cards_layout.addWidget(self.card_semi['frame'])
        cards_layout.addWidget(self.card_macro['frame'])
        cards_layout.addWidget(self.card_commodity['frame'])

        self.v_splitter.addWidget(cards_widget)

        # ---- 下部分: 左右水平 Splitter (h_splitter) 包含双数据表 ----
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setChildrenCollapsible(False)

        # Left Widget: 外盘明细表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_title = QLabel("📊 全球 15 大核心外盘资产极速明细")
        left_title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 9.5pt; margin-bottom: 2px;")
        left_layout.addWidget(left_title)

        self.tbl_quotes = BaseATSTableWidget(self)
        q_headers = ["资产名称", "资产代码", "最新价格 / 点位", "涨跌幅 (%)", "关联 A 股热点", "外盘连带趋势"]
        self.tbl_quotes.setColumnCount(len(q_headers))
        self.tbl_quotes.setHorizontalHeaderLabels(q_headers)
        self.tbl_quotes.setup_persistence(
            config_key="ats_global_quotes_table_state",
            default_widths=[145, 85, 110, 110, 185, 220]
        )
        self.tbl_quotes.itemClicked.connect(self._on_quotes_table_clicked)
        self.tbl_quotes.itemDoubleClicked.connect(self._on_quotes_table_double_clicked)
        self.tbl_quotes.customContextMenuRequested.disconnect()
        self.tbl_quotes.customContextMenuRequested.connect(self._show_quotes_context_menu)
        left_layout.addWidget(self.tbl_quotes)
        self.h_splitter.addWidget(left_widget)

        # 4 大卡片点击左右半区智能识别与分立外盘 K 线走势弹窗
        self.card_m7['frame'].setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_m7['frame'].mousePressEvent = lambda e: self._open_kline_dialog(
            'QQQ' if e.pos().x() > self.card_m7['frame'].width() / 2 else 'NVDA',
            '纳斯达克100 ETF' if e.pos().x() > self.card_m7['frame'].width() / 2 else '英伟达/算力'
        )
        
        self.card_semi['frame'].setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_semi['frame'].mousePressEvent = lambda e: self._open_kline_dialog(
            'SOXX' if e.pos().x() > self.card_semi['frame'].width() / 2 else 'MU',
            '费城半导体 ETF' if e.pos().x() > self.card_semi['frame'].width() / 2 else '美光/存储'
        )

        self.card_macro['frame'].setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_macro['frame'].mousePressEvent = lambda e: self._open_kline_dialog(
            'USDCNH' if e.pos().x() > self.card_macro['frame'].width() / 2 else 'A50',
            '离岸人民币' if e.pos().x() > self.card_macro['frame'].width() / 2 else '富时 A50 期货'
        )

        self.card_commodity['frame'].setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_commodity['frame'].mousePressEvent = lambda e: self._open_kline_dialog(
            'GOLD' if e.pos().x() > self.card_commodity['frame'].width() / 2 else 'BRENT',
            'COMEX 纽约金 (黄金期货)' if e.pos().x() > self.card_commodity['frame'].width() / 2 else '布伦特原油主连 (ICE)'
        )

        # Right Widget: 板块 Boost 提权看板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_title = QLabel("🎯 A 股热点板块外盘连带 Boost 提权与 Signal Tag 看板")
        right_title.setStyleSheet("font-weight: bold; color: #ffd700; font-size: 9.5pt; margin-bottom: 2px;")
        right_layout.addWidget(right_title)

        self.tbl_boosts = BaseATSTableWidget(self)
        b_headers = ["A 股核心热点板块", "关键关联外盘标的", "连带 Boost 提权分", "专属 Signal Tag 标签", "信号提权状态与指导"]
        self.tbl_boosts.setColumnCount(len(b_headers))
        self.tbl_boosts.setHorizontalHeaderLabels(b_headers)
        self.tbl_boosts.setup_persistence(
            config_key="ats_global_boosts_table_state",
            default_widths=[145, 200, 110, 220, 280]
        )
        self.tbl_boosts.itemDoubleClicked.connect(self._on_boost_table_double_clicked)
        self.tbl_boosts.customContextMenuRequested.disconnect()
        self.tbl_boosts.customContextMenuRequested.connect(self._show_boosts_context_menu)
        right_layout.addWidget(self.tbl_boosts)
        self.h_splitter.addWidget(right_widget)

        # 将左右 h_splitter 放入上下 v_splitter 的下半部分
        self.v_splitter.addWidget(self.h_splitter)
        layout.addWidget(self.v_splitter)

        # 恢复与绑定 Splitter 拖拽持久化
        self._restore_splitter_states()
        self.v_splitter.splitterMoved.connect(self._save_splitter_states)
        self.h_splitter.splitterMoved.connect(self._save_splitter_states)

    def _save_splitter_states(self):
        """持久化落盘上下 (v_splitter) 与左右 (h_splitter) 分割线位置"""
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from ats.ui.styles import CONFIG_FILE_LOCK
            from PyQt6.QtCore import QByteArray

            cfg_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(cfg_path):
                    try:
                        with open(cfg_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                if hasattr(self, 'v_splitter'):
                    data["ats_global_market_v_splitter"] = self.v_splitter.saveState().toHex().data().decode('utf-8')
                if hasattr(self, 'h_splitter'):
                    data["ats_global_market_h_splitter"] = self.h_splitter.saveState().toHex().data().decode('utf-8')
                
                tmp_path = cfg_path + ".tmp_gpanel"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, cfg_path)
        except Exception as e:
            print(f"[GlobalMarketPanel] Save splitter states error: {e}")

    def _restore_splitter_states(self):
        """恢复上下 (v_splitter) 与左右 (h_splitter) 分割线位置"""
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from PyQt6.QtCore import QByteArray

            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                v_hex = data.get("ats_global_market_v_splitter")
                if v_hex and hasattr(self, 'v_splitter'):
                    self.v_splitter.restoreState(QByteArray.fromHex(v_hex.encode('utf-8')))
                else:
                    self.v_splitter.setSizes([85, 550]) # 默认顶部卡片紧凑 85px

                h_hex = data.get("ats_global_market_h_splitter")
                if h_hex and hasattr(self, 'h_splitter'):
                    self.h_splitter.restoreState(QByteArray.fromHex(h_hex.encode('utf-8')))
                else:
                    self.h_splitter.setSizes([480, 520])
        except Exception as e:
            print(f"[GlobalMarketPanel] Restore splitter states error: {e}")

    def _create_card(self, title: str, main_val: str, sub_val: str, theme_color: str) -> dict:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #191d26;
                border: 1px solid {theme_color};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"font-size: 9pt; color: #aaa;")
        layout.addWidget(lbl_t)

        lbl_main = QLabel(main_val)
        lbl_main.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {theme_color};")
        layout.addWidget(lbl_main)

        lbl_sub = QLabel(sub_val)
        lbl_sub.setStyleSheet("font-size: 8.5pt; color: #888;")
        layout.addWidget(lbl_sub)

        return {'frame': frame, 'main': lbl_main, 'sub': lbl_sub}

    def _start_auto_refresh_timer(self):
        """启动定时刷新 (根据统一的交易期/非交易期阈值时间自动更新界面)"""
        try:
            from JSONData.global_market_data import get_global_market_cache_ttl
            interval_sec = get_global_market_cache_ttl()
        except Exception:
            interval_sec = 60.0

        self._timer = QTimer(self)
        self._timer.setInterval(int(interval_sec * 1000))
        self._timer.timeout.connect(self._on_auto_timer_timeout)
        self._timer.start()

    def _on_auto_timer_timeout(self):
        """定时器到期回调: 重新检测并动态调整轮询间隔，并触发无感增量刷新"""
        try:
            from JSONData.global_market_data import get_global_market_cache_ttl
            interval_sec = get_global_market_cache_ttl()
            self._timer.setInterval(int(interval_sec * 1000))
        except Exception:
            pass
        self.refresh_data(force=False)

    def refresh_data(self, force: bool = False):
        """调起后台 worker 刷新数据"""
        if self._worker and self._worker.isRunning():
            return

        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("⏳ 正在更新..." if force else "🔄 刷新中...")

        self._worker = GlobalMarketWorker(force_refresh=force, parent=self)
        self._worker.finished_signal.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self, quotes: dict, score: float, label: str, boosts: dict, meta: dict = None):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 强制实时刷新外盘")

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        meta = meta or {}
        is_live = meta.get('is_live_network', False)
        is_force = meta.get('force_refresh', False)
        q_count = len(quotes)

        # 检查价格数据是否有变动
        changed_syms = []
        for sym, item in quotes.items():
            old_item = self._last_quotes.get(sym, {})
            if old_item and (old_item.get('price') != item.get('price') or old_item.get('pct') != item.get('pct')):
                changed_syms.append(sym)

        # 1. 更新顶部 Sentiment Label
        score_color = COLOR_UP if score > 10.0 else (COLOR_DOWN if score < -10.0 else COLOR_ACCENT)
        self.lbl_sentiment.setText(f"🌐 外盘整体情绪得分: {score:+.1f} ({label})")
        self.lbl_sentiment.setStyleSheet(f"font-weight: bold; color: {score_color}; font-size: 10pt; margin-left: 10px;")

        from JSONData.global_market_data import is_market_active_time
        active_time = is_market_active_time()

        if is_live:
            if changed_syms:
                status_str = f"✅ 网络在线抓取成功 ({q_count} 项, {', '.join(changed_syms[:3])} 等最新价变动)"
            elif is_force:
                status_str = f"✅ 手动强制刷新完成 (已是最新 {q_count} 项数据)"
            else:
                status_str = f"✅ 网络在线更新 ({q_count} 项数据集)"
            self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; margin-left: 8px;")
        else:
            status_str = f"⚠️ 磁盘 Cache / 静态数据 ({q_count} 项数据集)"
            self.lbl_status.setStyleSheet("color: #ffa500; font-size: 8.5pt; margin-left: 8px;")

        self.lbl_status.setText(f"状态: {status_str}")
        self.lbl_update_time.setText(f"最后更新: {now_str}")

        # 2. 更新卡片
        self._update_cards(quotes)

        # 3. 更新外盘明细表
        self._update_quotes_table(quotes)

        # 4. 更新板块 Boost 看板
        self._update_boosts_table(boosts)

    def _update_cards(self, quotes: dict):
        if not quotes:
            return

        # Card 1: M7 (英伟达/算力, 微软, 谷歌, 亚马逊, 特斯拉)
        nvda_pct = quotes.get('NVDA', {}).get('pct', 0.0)
        msft_pct = quotes.get('MSFT', {}).get('pct', 0.0)
        googl_pct = quotes.get('GOOGL', {}).get('pct', 0.0)
        amzn_pct = quotes.get('AMZN', {}).get('pct', 0.0)
        m7_avg = (nvda_pct + msft_pct + googl_pct + amzn_pct) / 4.0
        m7_str = f"M7均值 {m7_avg:+.2f}% | NVDA {nvda_pct:+.2f}%"
        self.card_m7['main'].setText(m7_str)
        self.card_m7['sub'].setText("提权: 传媒 / AI / 软件开发 / 计算机")

        # Card 2: 存储与半导体 (美光 MU, 台积电 TSM, SOXX)
        mu_pct = quotes.get('MU', {}).get('pct', 0.0)
        soxx_pct = quotes.get('SOXX', {}).get('pct', 0.0)
        semi_str = f"美光 MU {mu_pct:+.2f}% | SOXX {soxx_pct:+.2f}%"
        self.card_semi['main'].setText(semi_str)
        self.card_semi['sub'].setText("提权: 存储芯片 / 半导体 / 电子元件")

        # Card 3: 富时 A50 & 汇率
        a50_pct = quotes.get('A50', {}).get('pct', 0.0)
        cnh_price = quotes.get('USDCNH', {}).get('price', 0.0)
        macro_str = f"A50 {a50_pct:+.2f}% | CNH {cnh_price:.4f}"
        self.card_macro['main'].setText(macro_str)
        self.card_macro['sub'].setText("提权: 国防军工 / 金融 / 权重龙头")

        # Card 4: 大宗商品 (原油 / 黄金)
        oil_pct = quotes.get('OIL', {}).get('pct', 0.0)
        gold_pct = quotes.get('GOLD', {}).get('pct', 0.0)
        comm_str = f"原油 {oil_pct:+.2f}% | 黄金 {gold_pct:+.2f}%"
        self.card_commodity['main'].setText(comm_str)
        self.card_commodity['sub'].setText("提权: 有色金属 / 石油化工 / 资源")

    def _update_quotes_table(self, quotes: dict):
        self._last_quotes = quotes or {}
        self.tbl_quotes.setSortingEnabled(False)
        self.tbl_quotes.setRowCount(0)

        mapping_info = {
            'A50': ('富时 A50 期货', '国防军工 / 金融 / 权重龙头'),
            'USDCNH': ('离岸人民币', '整体北向/外资风险偏好'),
            'OIL': ('美原油', '石油化工 / 基础化工 / 能源'),
            'GOLD': ('美黄金', '贵金属 / 有色金属 / 避险板块'),
            'NVDA': ('英伟达 / 算力', 'AI算力 / 传媒 / 算力服务器'),
            'MU': ('美光 / 存储', '存储芯片 / 存储封测 / 半导体'),
            'TSM': ('台积电 / 晶圆', '半导体代工 / 电子 / 芯片制造'),
            'SOXX': ('费城半导体 ETF', '半导体 / 芯片 / 电子元件'),
            'TSLA': ('特斯拉', '汽车整车 / 汽车零部件 / 智能驾驶'),
            'AAPL': ('苹果', '消费电子 / 苹果概念 / 果链'),
            'MSFT': ('微软', '软件开发 / AI应用 / 云计算'),
            'GOOGL': ('谷歌', 'AI模型 / 互联网 / 传媒'),
            'AMZN': ('亚马逊', '跨境电商 / 云计算 / AI应用'),
            'META': ('Meta', '社交传媒 / 虚拟现实 / AI大模型'),
            'QQQ': ('纳斯达克 100 ETF', '科技股整体 / 创业板指同向')
        }

        # 优先排序逻辑: 1. 是否置顶 (0 排前面, 1 排后面); 2. 置顶 index (0 号位为最新置顶，最高优先级); 3. 涨跌幅降序 (-pct)
        def _get_sort_key(item_tuple):
            sym, info_dict = item_tuple
            if sym in self.pinned_symbols:
                rank = self.pinned_symbols.index(sym)
                return (0, rank, 0.0)
            else:
                pct_val = float(info_dict.get('pct', 0.0))
                return (1, 0, -pct_val)

        sorted_quotes = sorted(quotes.items(), key=_get_sort_key)
        self.tbl_quotes.setRowCount(len(sorted_quotes))

        for row_idx, (symbol, info) in enumerate(sorted_quotes):
            name = info.get('name', symbol)
            price = info.get('price', 0.0)
            pct = info.get('pct', 0.0)
            is_pinned = symbol in self.pinned_symbols
            pin_rank = self.pinned_symbols.index(symbol) if is_pinned else 999

            c_info = mapping_info.get(symbol, (name, '科技 / 综合板块'))
            c_name = f"📌 {c_info[0]}" if is_pinned else c_info[0]
            c_sector = c_info[1]

            trend_str = "🔥 强劲拉升共振" if pct >= 3.0 else ("📈 稳步上行" if pct > 0.0 else ("📉 走弱回调" if pct < -2.0 else "➖ 横盘整理"))

            col_values = [
                c_name, symbol, f"{price:.2f}" if isinstance(price, (int, float)) else str(price),
                f"{pct:+.2f}%", c_sector, trend_str
            ]

            for col_idx, val in enumerate(col_values):
                item = PinnedNumericTableWidgetItem(
                    val, is_pinned=is_pinned, pin_rank=pin_rank,
                    header_view=self.tbl_quotes.horizontalHeader()
                )
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx not in (0, 4) else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

                # 置顶行单元格微暗金色专属尊贵背景高亮
                if is_pinned:
                    item.setBackground(QColor("#2a2415"))

                # Color coding
                if col_idx == 0:
                    item.setForeground(QColor("#FFD700" if is_pinned else "#00E5FF"))
                    item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif col_idx == 3: # Pct
                    if pct > 0:
                        item.setForeground(QColor(COLOR_UP))
                        if pct >= 3.0 or is_pinned:
                            item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    elif pct < 0:
                        item.setForeground(QColor(COLOR_DOWN))
                        if pct <= -3.0 or is_pinned:
                            item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    else:
                        item.setForeground(QColor("#E2E2E5"))
                elif col_idx == 5: # Trend
                    if "强劲" in val or "上行" in val:
                        item.setForeground(QColor(COLOR_UP))
                    elif "走弱" in val:
                        item.setForeground(QColor(COLOR_DOWN))
                    else:
                        item.setForeground(QColor("#AAA"))

                self.tbl_quotes.setItem(row_idx, col_idx, item)

        self.tbl_quotes.setSortingEnabled(True)
        if hasattr(self.tbl_quotes, 'restore_header_state'):
            self.tbl_quotes.restore_header_state()


    def _show_quotes_context_menu(self, pos):
        """右键弹出外盘极速明细表专用菜单 (包含优先置顶、查看K线、编辑单元格、一键列宽)"""
        item = self.tbl_quotes.itemAt(pos)
        if not item:
            return
        row = item.row()
        sym_item = self.tbl_quotes.item(row, 1)
        name_item = self.tbl_quotes.item(row, 0)
        if not sym_item:
            return
        symbol = sym_item.text().strip().replace("📌 ", "")
        name = name_item.text().strip().replace("📌 ", "")

        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self.tbl_quotes)
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

        is_pinned = symbol in self.pinned_symbols
        pin_label = f"📌 取消优先置顶 ({symbol})" if is_pinned else f"📌 优先置顶 ({symbol})"
        pin_action = QAction(pin_label, self)
        pin_action.triggered.connect(lambda: self._toggle_pin_symbol(symbol))
        menu.addAction(pin_action)

        menu.addSeparator()

        kline_action = QAction(f"📈 查看 {name} ({symbol}) 120日 K线", self)
        kline_action.triggered.connect(lambda: self._open_kline_dialog(symbol, name))
        menu.addAction(kline_action)

        menu.addSeparator()

        copy_action = QAction(f"📋 复制资产代码 {symbol}", self)
        copy_action.triggered.connect(lambda: self.tbl_quotes._copy_to_clipboard(symbol))
        menu.addAction(copy_action)

        edit_action = QAction("✏️ 编辑当前单元格内容", self)
        edit_action.triggered.connect(lambda: self.tbl_quotes._edit_current_cell(item))
        menu.addAction(edit_action)

        fit_action = QAction("↔️ 一键自适应全列宽", self)
        fit_action.triggered.connect(self.tbl_quotes.auto_fit_columns)
        menu.addAction(fit_action)

        menu.exec(self.tbl_quotes.viewport().mapToGlobal(pos))

    def _toggle_pin_symbol(self, symbol: str):
        """切换资产置顶状态并落盘持久化，保证最新置顶排在最上面 (最高优先级)"""
        sym = symbol.strip().upper()
        if sym in self.pinned_symbols:
            self.pinned_symbols.remove(sym)
            print(f"[GlobalMarketPanel] 取消优先置顶: {sym}")
        else:
            self.pinned_symbols.insert(0, sym) # 最新置顶插在 0 号位，拥有最高优先级
            print(f"[GlobalMarketPanel] 设为优先置顶 (最高优先级): {sym}")
        self._save_pinned_symbols()
        if self._last_quotes:
            self._update_quotes_table(self._last_quotes)

    def _restore_pinned_symbols(self):
        """从 window_config.json 恢复优先置顶的资产列表 (保持 list 顺序)"""
        try:
            from ats.ui.styles import load_config_node
            pins = load_config_node("ats_global_market_pinned_symbols", [])
            if isinstance(pins, list):
                seen = set()
                self.pinned_symbols = [x for x in pins if not (x in seen or seen.add(x))]
        except Exception as e:
            print(f"[GlobalMarketPanel] Restore pinned symbols error: {e}")

    def _save_pinned_symbols(self):
        """将优先置顶的资产列表持久化写入 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_global_market_pinned_symbols", list(self.pinned_symbols))
        except Exception as e:
            print(f"[GlobalMarketPanel] Save pinned symbols error: {e}")


    def _update_boosts_table(self, boosts: dict):
        self._last_boosts = boosts or {}
        self.tbl_boosts.setSortingEnabled(False)
        self.tbl_boosts.setRowCount(0)

        sector_relations = {
            "存储芯片": "美光 (MU) / 费城半导体 (SOXX)",
            "半导体": "费城半导体 (SOXX) / 台积电 / 英伟达",
            "传媒": "美股7巨头 (NVDA/MSFT/AMZN) / QQQ",
            "软件开发": "微软 (MSFT) / 谷歌 / 亚马逊",
            "国防军工": "富时 A50 期货 / 离岸 RMB",
            "汽车整车": "特斯拉 (TSLA) / 富时 A50 期货",
            "贵金属": "美黄金 (GOLD / COMEX 纽约金)",
            "石油化工": "美原油 (OIL / 布伦特原油)",
            "有色金属": "大宗商品 (美原油 / 美黄金)"
        }

        # 板块置顶优先排序算法: 1. 是否置顶; 2. 板块置顶 index (最新置顶 index=0 排最前); 3. Boost 分数降序
        def _get_boost_sort_key(item_tuple):
            sec_name, info_tuple = item_tuple
            if sec_name in self.pinned_sectors:
                rank = self.pinned_sectors.index(sec_name)
                return (0, rank, 0.0)
            else:
                b_score = float(info_tuple[0])
                return (1, 0, -b_score)

        sorted_boosts = sorted(boosts.items(), key=_get_boost_sort_key)
        self.tbl_boosts.setRowCount(len(sorted_boosts))

        for row_idx, (sec_name, (b_val, g_tag)) in enumerate(sorted_boosts):
            rel_symbols = sector_relations.get(sec_name, "纳斯达克 / 标普500")
            tag_display = g_tag if g_tag else "--"
            is_pinned = sec_name in self.pinned_sectors
            pin_rank = self.pinned_sectors.index(sec_name) if is_pinned else 999
            c_sec_name = f"📌 {sec_name}" if is_pinned else sec_name

            if b_val >= 25.0:
                guide_str = "🚀 强力连带提权，优先精选置顶龙头"
            elif b_val > 0.0:
                guide_str = "📈 适度共振提权，偏正面支撑"
            elif b_val < 0.0:
                guide_str = "⚠️ 外盘走弱减分防护，谨防高开低走"
            else:
                guide_str = "➖ 外盘影响平淡，回归 A 股独立结构"

            col_values = [
                c_sec_name, rel_symbols, f"{b_val:+.1f} 分", tag_display, guide_str
            ]

            for col_idx, val in enumerate(col_values):
                item = PinnedNumericTableWidgetItem(
                    val, is_pinned=is_pinned, pin_rank=pin_rank,
                    header_view=self.tbl_boosts.horizontalHeader()
                )
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx in (0, 2) else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

                # 置顶行单元格微暗金色专属尊贵背景高亮
                if is_pinned:
                    item.setBackground(QColor("#2a2415"))

                if col_idx == 0:
                    item.setForeground(QColor("#FFD700" if is_pinned else "#00E5FF"))
                    item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif col_idx == 2: # Boost score
                    if b_val > 0:
                        item.setForeground(QColor(COLOR_UP))
                        item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    elif b_val < 0:
                        item.setForeground(QColor(COLOR_DOWN))
                        item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    else:
                        item.setForeground(QColor("#AAA"))
                elif col_idx == 3: # Tag
                    if "共振" in val or "强拉" in val:
                        item.setForeground(QColor("#00FF88"))
                        item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    elif "回调" in val or "走弱" in val:
                        item.setForeground(QColor("#FF5555"))

                self.tbl_boosts.setItem(row_idx, col_idx, item)

        self.tbl_boosts.setSortingEnabled(True)
        if hasattr(self.tbl_boosts, 'restore_header_state'):
            self.tbl_boosts.restore_header_state()


    def _show_boosts_context_menu(self, pos):
        """右键弹出 A 股热点板块提权表专用菜单 (包含优先置顶、双击查看成分股、复制名称、一键列宽)"""
        item = self.tbl_boosts.itemAt(pos)
        if not item:
            return
        row = item.row()
        sec_item = self.tbl_boosts.item(row, 0)
        if not sec_item:
            return
        sec_name = sec_item.text().strip().replace("📌 ", "")

        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self.tbl_boosts)
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

        is_pinned = sec_name in self.pinned_sectors
        pin_label = f"📌 取消优先置顶板块 ({sec_name})" if is_pinned else f"📌 优先置顶板块 ({sec_name})"
        pin_action = QAction(pin_label, self)
        pin_action.triggered.connect(lambda: self._toggle_pin_sector(sec_name))
        menu.addAction(pin_action)

        menu.addSeparator()

        detail_action = QAction(f"🔍 查看 {sec_name} 板块成分股明细", self)
        detail_action.triggered.connect(lambda: self.sector_selected.emit(sec_name))
        menu.addAction(detail_action)

        menu.addSeparator()

        copy_action = QAction(f"📋 复制板块名称 {sec_name}", self)
        copy_action.triggered.connect(lambda: self.tbl_boosts._copy_to_clipboard(sec_name))
        menu.addAction(copy_action)

        fit_action = QAction("↔️ 一键自适应全列宽", self)
        fit_action.triggered.connect(self.tbl_boosts.auto_fit_columns)
        menu.addAction(fit_action)

        menu.exec(self.tbl_boosts.viewport().mapToGlobal(pos))

    def _toggle_pin_sector(self, sector: str):
        """切换板块置顶状态并落盘持久化，保证最新置顶排在最上面 (最高优先级)"""
        sec = sector.strip()
        if sec in self.pinned_sectors:
            self.pinned_sectors.remove(sec)
            print(f"[GlobalMarketPanel] 取消优先置顶板块: {sec}")
        else:
            self.pinned_sectors.insert(0, sec)
            print(f"[GlobalMarketPanel] 设为优先置顶板块 (最高优先级): {sec}")
        self._save_pinned_sectors()
        if self._last_boosts:
            self._update_boosts_table(self._last_boosts)

    def _restore_pinned_sectors(self):
        """从 window_config.json 恢复优先置顶的板块列表 (保持 list 顺序)"""
        try:
            from ats.ui.styles import load_config_node
            pins = load_config_node("ats_global_market_pinned_sectors", [])
            if isinstance(pins, list):
                seen = set()
                self.pinned_sectors = [x for x in pins if not (x in seen or seen.add(x))]
        except Exception as e:
            print(f"[GlobalMarketPanel] Restore pinned sectors error: {e}")

    def _save_pinned_sectors(self):
        """将优先置顶的板块列表持久化写入 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_global_market_pinned_sectors", list(self.pinned_sectors))
        except Exception as e:
            print(f"[GlobalMarketPanel] Save pinned sectors error: {e}")

    def _on_quotes_table_clicked(self, item):
        """单击外盘明细表格行，若 K 线弹窗已存在，即刻无缝切标的并强力最前显示"""
        row = item.row()
        sym_item = self.tbl_quotes.item(row, 1)
        name_item = self.tbl_quotes.item(row, 0)
        if sym_item and name_item:
            symbol = sym_item.text().strip().replace("📌 ", "")
            name = name_item.text().strip().replace("📌 ", "")
            from PyQt6.sip import isdeleted
            # 若已打开 K 线弹窗，单击任一 code 行即刻无缝同步切标的并最前显示！
            if hasattr(self, "_kline_dialog") and self._kline_dialog and not isdeleted(self._kline_dialog) and self._kline_dialog.isVisible():
                self._open_kline_dialog(symbol, name)

    def _on_quotes_table_double_clicked(self, item):
        """双击外盘明细表格行，直接调起该资产 120 日 K 线图并强力最前显示"""
        row = item.row()
        sym_item = self.tbl_quotes.item(row, 1)
        name_item = self.tbl_quotes.item(row, 0)
        if sym_item and name_item:
            symbol = sym_item.text().strip().replace("📌 ", "")
            name = name_item.text().strip().replace("📌 ", "")
            self._open_kline_dialog(symbol, name)

    def _open_kline_dialog(self, symbol: str, name: str = ""):
        """打开/平滑复用外盘个股与指数 120 日 K 线走势图 (0 毫秒秒开，100% 恢复最小化并置顶激活最前显示)"""
        try:
            from ats.ui.global_market_kline_dialog import GlobalMarketKLineDialog
            from PyQt6.sip import isdeleted
            from PyQt6.QtCore import QTimer

            dlg = getattr(self, "_kline_dialog", None)
            if dlg and not isdeleted(dlg):
                try:
                    # 1. 🛡️ 若窗口被最小化收起，强力还原为正常视区尺寸
                    if dlg.isMinimized():
                        dlg.showNormal()
                    
                    # 2. 0ms 无缝更新标的与 K 线数据
                    dlg.update_symbol(symbol, name)
                    
                    # 3. ⚡ 强力最前显示 (Bring to Front) 与全方位激活
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
                    dlg.setFocus()

                    # 4. 延迟 50ms 进行二次激活强化，突破 Windows 前台抢占拦截
                    QTimer.singleShot(50, lambda: (dlg.raise_(), dlg.activateWindow()) if (dlg and not isdeleted(dlg)) else None)
                    return
                except Exception as ex:
                    print(f"[GlobalMarketPanel] Reuse KLine dialog exception: {ex}")
                    self._kline_dialog = None

            # 新建窗口并初始化最前显示
            self._kline_dialog = GlobalMarketKLineDialog(symbol, name, parent=self)
            self._kline_dialog.show()
            self._kline_dialog.raise_()
            self._kline_dialog.activateWindow()
            self._kline_dialog.setFocus()
            QTimer.singleShot(50, lambda: (self._kline_dialog.raise_(), self._kline_dialog.activateWindow()) if (hasattr(self, "_kline_dialog") and self._kline_dialog and not isdeleted(self._kline_dialog)) else None)
        except Exception as e:
            print(f"[GlobalMarketPanel] Open KLine dialog error: {e}")

    def _on_boost_table_double_clicked(self, item):
        if not item:
            return
        row = item.row()
        sec_item = self.tbl_boosts.item(row, 0)
        if sec_item:
            sec_name = sec_item.text().strip().replace("📌 ", "")
            from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
            def _link_cb(code, name):
                self.stock_linked.emit(code, name)
            def _double_click_cb(code, name):
                self.stock_selected.emit(code, name, {})
            from PyQt6.sip import isdeleted
            if hasattr(self, "_sector_detail_dialog") and self._sector_detail_dialog and not isdeleted(self._sector_detail_dialog):
                try:
                    self._sector_detail_dialog.close()
                except Exception:
                    pass
            dlg = ATSSectorDetailDialog(sec_name, linkage_cb=_link_cb, double_click_cb=_double_click_cb, parent=None)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            self._sector_detail_dialog = dlg

    def _update_proxy_btn_style(self):
        """更新 🌐 代理: 开/关 按键高亮与显示文本"""
        try:
            from JSONData.global_market_data import get_proxy_config
            cfg = get_proxy_config()
            enabled = cfg.get("enabled", False)
            p_url = cfg.get("proxy_url", "")
            port = p_url.split(":")[-1] if ":" in p_url else ""

            if enabled:
                btn_txt = f"🌐 代理: 开({port})" if port else "🌐 代理: 开"
                self.btn_proxy_config.setText(btn_txt)
                self.btn_proxy_config.setStyleSheet("""
                    QPushButton {
                        background-color: #00E5FF;
                        color: #000000;
                        font-weight: bold;
                        border: 1px solid #00E5FF;
                        border-radius: 3px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #33ebff;
                    }
                """)
            else:
                self.btn_proxy_config.setText("🌐 代理: 关")
                self.btn_proxy_config.setStyleSheet("""
                    QPushButton {
                        background-color: #1e222d;
                        color: #787b86;
                        font-weight: bold;
                        border: 1px solid #363c4e;
                        border-radius: 3px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #2a2e39;
                        color: #d1d4dc;
                    }
                """)
        except Exception as ex:
            print(f"[GlobalMarketPanel] 更新代理按键状态异常: {ex}")

    def _open_proxy_dialog(self):
        """调起网络代理设置弹窗"""
        try:
            from ats.ui.proxy_dialog import ProxySettingsDialog
            dlg = ProxySettingsDialog(parent=self)
            dlg.exec()
        except Exception as ex:
            print(f"[GlobalMarketPanel] 调起代理弹窗异常: {ex}")

    def _on_global_proxy_changed(self, cfg: dict = None):
        """响应全局代理变更广播，瞬间同步主窗口按钮状态并重载数据"""
        self._update_proxy_btn_style()
        self.refresh_data(force=True)

    def _update_log_btn_style(self):
        """动态更新日志开关按键样式与文案"""
        try:
            from JSONData.global_market_data import get_global_market_log_enabled
            enabled = get_global_market_log_enabled()
            if enabled:
                self.btn_log_config.setText("📜 日志: 开")
                self.btn_log_config.setStyleSheet("""
                    QPushButton {
                        background-color: #1a2233;
                        color: #00F0FF;
                        border: 1px solid #00F0FF;
                        border-radius: 3px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #2962ff;
                        color: #ffffff;
                    }
                """)
            else:
                self.btn_log_config.setText("📜 日志: 关")
                self.btn_log_config.setStyleSheet("""
                    QPushButton {
                        background-color: #191d26;
                        color: #787b86;
                        border: 1px solid #363c4e;
                        border-radius: 3px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #2a2e39;
                        color: #d1d4dc;
                    }
                """)
        except Exception:
            pass

    def _toggle_log_config(self):
        """手动切换外盘数据日志开关"""
        try:
            from JSONData.global_market_data import get_global_market_log_enabled, save_global_market_log_enabled
            from ats.ui.proxy_dialog import GLOBAL_LOG_EVENT_BRIDGE
            new_state = not get_global_market_log_enabled()
            save_global_market_log_enabled(new_state)
            GLOBAL_LOG_EVENT_BRIDGE.log_toggled_signal.emit(new_state)
        except Exception:
            pass

    def _on_global_log_changed(self, enabled: bool):
        """响应全局日志开关变更广播信号，秒级更新 UI 按键状态"""
        self._update_log_btn_style()

