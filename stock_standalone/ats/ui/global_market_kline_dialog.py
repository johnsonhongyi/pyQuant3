# -*- coding: utf-8 -*-
"""
ATS Global Market K-Line Viewer Dialog
独立极速外盘资产 (美股7巨头/存储芯片/A50/原油黄金) 近 120 日 K 线与 OHLC 走势查看器
采用 TradingView 极简 Pro 暗黑交易画板设计，支持异步无卡顿后台加载、格式化 DateAxis/VolumeAxis、
支持 🕯️ 蜡烛图 (Candlestick) 与 📊 竹节线 (OHLC) 双模式平滑切换、
MA5/MA20/MA60 动态均线、成交量 Subplot 柱状图、十字光标与磁盘 JSON 物理持久化
"""

import json
import os
from math import floor, ceil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QApplication, QSplitter,
    QListWidget, QListWidgetItem, QTextEdit, QTextBrowser, QWidget, QMenu
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QThread, pyqtSignal, QByteArray, QTimer
from PyQt6.QtGui import QColor, QPicture, QPainter, QPen, QBrush, QFont, QCursor

import pyqtgraph as pg
from JSONData.global_market_data import (
    fetch_global_kline_history, get_kline_cache_file_path,
    get_related_symbols, fetch_global_market_quotes,
    fetch_symbol_financial_news, get_proxy_info_str,
    delete_news_item_by_id, save_news_hotlist_json,
    _auto_translate_en_text_to_cn,
    log_market_msg
)
from sys_utils import get_app_root, get_conf_path
from ats.ui.styles import CONFIG_FILE_LOCK


class OnlineTranslateWorkerThread(QThread):
    """后台非阻塞极速英译中线程，确保 UI 响应极速滑顺"""
    translated_signal = pyqtSignal(str, str, str, str)  # (original_text, translated_text, mode, translated_title)

    def __init__(self, text: str, mode: str = 'full', title: str = ''):
        super().__init__()
        self.text = text
        self.mode = mode
        self.title = title

    def run(self):
        try:
            translated_text = _auto_translate_en_text_to_cn(self.text)
            translated_title = _auto_translate_en_text_to_cn(self.title) if self.title else ""
            self.translated_signal.emit(self.text, translated_text or self.text, self.mode, translated_title or "")
        except Exception as ex:
            self.translated_signal.emit(self.text, self.text, self.mode, "")


# ---------------- 全局股票实体识别与联动工具集 ----------------
_GLOBAL_STOCK_NAME_MAP_CACHE = None

def get_global_stock_name_map(parent_dialog=None) -> tuple:
    """
    智能归纳全市场股票 code -> name, name -> code 映射表及 C 引擎编译大正则
    """
    global _GLOBAL_STOCK_NAME_MAP_CACHE
    if _GLOBAL_STOCK_NAME_MAP_CACHE is not None:
        return _GLOBAL_STOCK_NAME_MAP_CACHE

    code_to_name = {}
    name_to_code = {}

    # 预置核心热门黑马/权重股映射字典
    preset_map = {
        '603259': '药明康德', '688981': '中芯国际', '601939': '建设银行', '300418': '智谱',
        '688347': '华虹公司', '1347': '华虹半导体', '9868': '小鹏汽车', '9866': '蔚来',
        '9618': '京东集团', '9988': '阿里巴巴', '0700': '腾讯控股', '3690': '美团',
        '600519': '贵州茅台', '300750': '宁德时代', '002594': '比亚迪', '600036': '招商银行',
        '601318': '中国平安', '601857': '中国石油', '600028': '中国石化', '601988': '中国银行',
        '601398': '工商银行', '601288': '农业银行', '000001': '平安银行', '000651': '格力电器',
        '000333': '美的集团', '688012': '中微公司', '688041': '海光信息', '600118': '中国卫星',
        '300936': '中英科技', '002297': '博云新材', '600893': '航发动力', '600760': '中航沈飞',
        'NVDA': '英伟达', 'TSLA': '特斯拉', 'AAPL': '苹果', 'MSFT': '微软', 'GOOGL': '谷歌',
        'AMZN': '亚马逊', 'META': 'Meta', 'AMD': 'AMD', 'OIL': '原油', 'GOLD': '黄金'
    }
    for c, n in preset_map.items():
        code_to_name[c] = n
        name_to_code[n] = c

    try:
        main_app = None
        curr = parent_dialog
        while curr:
            if hasattr(curr, 'main_app'):
                main_app = curr.main_app
                break
            if hasattr(curr, 'parent') and callable(curr.parent):
                curr = curr.parent()
            else:
                break

        if not main_app:
            from PyQt6.QtWidgets import QApplication
            for top_w in QApplication.topLevelWidgets():
                if hasattr(top_w, 'get_stock_name') or hasattr(top_w, 'current_df'):
                    main_app = top_w
                    break

        if main_app:
            for attr in ('current_df', 'df_realtime', 'df_all'):
                if hasattr(main_app, attr):
                    df = getattr(main_app, attr)
                    if df is not None and not df.empty and 'name' in df.columns:
                        for code, row in df.iterrows():
                            c_str = str(code).zfill(6)
                            n_str = str(row['name']).strip()
                            if n_str and n_str != '未知' and len(n_str) >= 2:
                                code_to_name[c_str] = n_str
                                name_to_code[n_str] = c_str
    except Exception:
        pass

    import re
    valid_names = sorted([n for n in name_to_code.keys() if len(n) >= 2], key=lambda x: len(x), reverse=True)
    compiled_regex = None
    if valid_names:
        pattern = r'|'.join([re.escape(n) for n in valid_names])
        compiled_regex = re.compile(pattern)

    _GLOBAL_STOCK_NAME_MAP_CACHE = (code_to_name, name_to_code, compiled_regex)
    return _GLOBAL_STOCK_NAME_MAP_CACHE


def extract_stock_entities_from_text(text: str, parent_dialog=None) -> list:
    """
    自动在新闻标题/正文中高效扫描匹配出现的股票名称与代码 (C 正则极速引擎)
    返回 [{'code': '603259', 'name': '药明康德'}, ...]
    """
    if not text:
        return []

    code_to_name, name_to_code, compiled_regex = get_global_stock_name_map(parent_dialog)
    matched_entities = []
    seen_codes = set()

    import re
    # 1. 匹配 6 位数字 A 股代码
    digit_codes = re.findall(r'\b\d{6}\b', text)
    for c in digit_codes:
        if c not in seen_codes:
            seen_codes.add(c)
            n = code_to_name.get(c, c)
            matched_entities.append({'code': c, 'name': n})

    # 2. 正则极速全自动匹配股票名称实体 (从 5000 次 Python 遍历优化为 1 次 C 正则扫描)
    if compiled_regex:
        found_names = compiled_regex.findall(text)
        for name in found_names:
            code = name_to_code.get(name)
            if code and code not in seen_codes:
                seen_codes.add(code)
                matched_entities.append({'code': code, 'name': name})

    return matched_entities


def highlight_stock_names_in_html(text: str, parent_dialog=None) -> str:
    """
    将文本中识别出的股票名称打上 HTML 超链接标签 (stock://CODE|NAME)
    直接在正文/标题标记位上支持鼠标点击联动，彻底解决底部按钮挤压折叠缺陷
    """
    if not text:
        return text

    entities = extract_stock_entities_from_text(text, parent_dialog)
    if not entities:
        return text

    highlighted = text
    for ent in entities:
        name = ent['name']
        code = ent['code']
        if not name or name in ['原油', '黄金']:
            continue
        if f">{name}<" in highlighted or f"href=" in highlighted or f"style=" in highlighted:
            # 避免对已被 HTML 标签修饰过的文本重复替换
            continue
        replacement = f"<a href='stock://{code}|{name}' style='color:#00ff88; text-decoration:underline; font-weight:bold; padding:0 2px;'>{name}</a>"
        highlighted = highlighted.replace(name, replacement)

    return highlighted


def trigger_stock_linkage(code: str, name: str, parent_dialog=None):
    """
    通用极速触发股票 Code 联动：
    1. 物理联动同花顺/通达信终端 (link_stock)
    2. 主界面秒级定位高亮与调起 K 线图/详情弹窗 (on_stock_clicked)
    """
    if not code:
        return

    code_clean = str(code).strip()
    from PyQt6.QtWidgets import QApplication
    main_win = None
    for top_w in QApplication.topLevelWidgets():
        if hasattr(top_w, 'link_stock') or hasattr(top_w, 'on_stock_clicked'):
            main_win = top_w
            break

    if main_win:
        if hasattr(main_win, 'link_stock'):
            try:
                main_win.link_stock(code_clean, name)
            except Exception:
                pass
        if hasattr(main_win, 'on_stock_clicked'):
            try:
                main_win.on_stock_clicked(code_clean, name)
            except Exception:
                pass
    else:
        try:
            dlg = GlobalMarketKLineDialog(symbol=code_clean, name=name, parent=parent_dialog)
            dlg.exec()
        except Exception:
            pass



class KLineWorkerThread(QThread):
    """后台非阻塞异步 K 线抓取线程，彻底解决 UI 界面调起卡顿问题"""
    finished_signal = pyqtSignal(list, str)  # klines, error_msg

    def __init__(self, symbol: str, force_refresh: bool = False, data_source: str = 'yahoo'):
        super().__init__()
        self.symbol = symbol
        self.force_refresh = force_refresh
        self.data_source = data_source

    def run(self):
        try:
            klines = fetch_global_kline_history(self.symbol, limit=120, force_refresh=self.force_refresh, data_source=self.data_source)
            self.finished_signal.emit(klines or [], "")
        except Exception as e:
            self.finished_signal.emit([], str(e))


class RelatedKLineWorkerThread(QThread):
    """后台并行抓取关联品种 K 线数据，不阻塞主 K 线渲染"""
    finished_signal = pyqtSignal(str, list)  # symbol, klines

    def __init__(self, symbol: str, data_source: str = 'yahoo'):
        super().__init__()
        self.symbol = symbol
        self.data_source = data_source

    def run(self):
        try:
            klines = fetch_global_kline_history(self.symbol, limit=120, force_refresh=False, data_source=self.data_source)
            self.finished_signal.emit(self.symbol, klines or [])
        except Exception as e:
            self.finished_signal.emit(self.symbol, [])


class NewsWorkerThread(QThread):
    """后台非阻塞异步新闻与要闻抓取线程，彻底消除主线程网络卡死(未响应) Bug"""
    finished_signal = pyqtSignal(list, str)  # (news_items, err_msg)

    def __init__(self, symbol: str, name: str, force_refresh: bool = False):
        super().__init__()
        self.symbol = symbol
        self.name = name
        self.force_refresh = force_refresh

    def run(self):
        try:
            items = fetch_symbol_financial_news(self.symbol, self.name, force_refresh=self.force_refresh)
            self.finished_signal.emit(items or [], "")
        except Exception as e:
            self.finished_signal.emit([], str(e))




class DateAxisItem(pg.AxisItem):
    """自定义 X 轴日期刻度格式化类 (将索引转换为 06/29 精简日期)"""

    def __init__(self, dates=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dates = dates or []

    def set_dates(self, dates):
        self.dates = dates

    def tickStrings(self, values, scale, spacing):
        strings = []
        n = len(self.dates)
        for v in values:
            idx = int(round(v))
            if 0 <= idx < n:
                dt_str = str(self.dates[idx])
                if len(dt_str) >= 10:
                    strings.append(dt_str[5:].replace('-', '/'))
                else:
                    strings.append(dt_str)
            else:
                strings.append('')
        return strings


class VolumeAxisItem(pg.AxisItem):
    """自定义 Y 轴成交量格式化类 (转换为 万/亿 简洁中文单位)"""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            abs_v = abs(v)
            if abs_v >= 1e8:
                strings.append(f"{v / 1e8:.2f}亿")
            elif abs_v >= 1e4:
                strings.append(f"{int(v / 1e4)}万")
            elif abs_v == 0:
                strings.append("0")
            else:
                strings.append(f"{int(v)}")
        return strings


class CandlestickItem(pg.GraphicsObject):
    """TradingView Pro 级 Candlestick K 线抗锯齿精准绘制组件"""

    def __init__(self, data):
        super().__init__()
        self.data = data  # list of tuples: (i, open, close, low, high)
        self.picture = QPicture()
        self.generate_picture()

    def generate_picture(self):
        p = QPainter(self.picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 国际/国内大厂高辨识度配色: 阳线 #F6465D (珊瑚红), 阴线 #089981 (青绿)
        color_up = QColor("#F6465D")
        color_down = QColor("#089981")

        pen_up = QPen(color_up, 1.0)
        pen_up.setCosmetic(True)  # 核心点：设为 cosmetic 避免屏幕放大缩小导致线宽为坐标轴 1.0 单位的肥厚块！

        pen_down = QPen(color_down, 1.0)
        pen_down.setCosmetic(True)

        brush_up = QBrush(color_up)
        brush_down = QBrush(color_down)

        w = 0.30
        for (i, open_p, close_p, low_p, high_p) in self.data:
            is_up = close_p >= open_p
            p.setPen(pen_up if is_up else pen_down)
            p.setBrush(brush_up if is_up else brush_down)

            # 1. 绘制上下影线 (1px 极细精美线条)
            p.drawLine(QPointF(i, low_p), QPointF(i, high_p))

            # 2. 绘制实体蜡烛 (标准 pyqtgraph QRectF 区域填充)
            top_p = max(open_p, close_p)
            bottom_p = min(open_p, close_p)
            h = top_p - bottom_p

            if h < 0.01:
                # 平盘/十字星: 绘制横线
                p.drawLine(QPointF(i - w, open_p), QPointF(i + w, open_p))
            else:
                p.drawRect(QRectF(i - w, bottom_p, w * 2, h))

        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        if not self.data:
            return QRectF(0, 0, 0, 0)
        if not hasattr(self, '_rect') or self._rect is None:
            x_vals = [item[0] for item in self.data]
            min_x = min(x_vals) - 0.5
            max_x = max(x_vals) + 0.5
            y_lows = [item[3] for item in self.data]
            y_highs = [item[4] for item in self.data]
            min_y = min(y_lows) if y_lows else 0
            max_y = max(y_highs) if y_highs else 1
            h = max(0.01, max_y - min_y)
            self._rect = QRectF(min_x, min_y, max_x - min_x, h)
        return self._rect


class OHLCItem(pg.GraphicsObject):
    """标准专业 OHLC (Open-High-Low-Close) 竹节线 / 美国线绘制组件"""

    def __init__(self, data):
        super().__init__()
        self.data = data  # list of tuples: (i, open, close, low, high)
        self._rect = None
        self.picture = QPicture()
        self.generate_picture()

    def generate_picture(self):
        p = QPainter(self.picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_up = QColor("#F6465D")
        color_down = QColor("#089981")

        pen_up = QPen(color_up, 1.5)
        pen_up.setCosmetic(True)

        pen_down = QPen(color_down, 1.5)
        pen_down.setCosmetic(True)

        w = 0.32
        for (i, open_p, close_p, low_p, high_p) in self.data:
            p.setPen(pen_up if close_p >= open_p else pen_down)

            # 1. 绘制 High-Low 主干竖线
            p.drawLine(QPointF(i, low_p), QPointF(i, high_p))

            # 2. 绘制左侧 Open 横线 (开盘价)
            p.drawLine(QPointF(i - w, open_p), QPointF(i, open_p))

            # 3. 绘制右侧 Close 横线 (收盘价)
            p.drawLine(QPointF(i, close_p), QPointF(i + w, close_p))

        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        if not self.data:
            return QRectF(0, 0, 0, 0)
        if not hasattr(self, '_rect') or self._rect is None:
            x_vals = [item[0] for item in self.data]
            min_x = min(x_vals) - 0.5
            max_x = max(x_vals) + 0.5
            y_lows = [item[3] for item in self.data]
            y_highs = [item[4] for item in self.data]
            min_y = min(y_lows) if y_lows else 0
            max_y = max(y_highs) if y_highs else 1
            h = max(0.01, max_y - min_y)
            self._rect = QRectF(min_x, min_y, max_x - min_x, h)
        return self._rect

class ClickableTextBrowser(QTextBrowser):
    """能够强力穿透选区阻断、在鼠标释放瞬间精确探测 anchor 并发射 link 信号的专用浏览器控件"""
    link_clicked_signal = pyqtSignal(str)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # 1. 尝试直接获取点击位置处的 anchor url (强力穿透选区与微小拖拽)
            anchor = self.anchorAt(pos)
            if anchor:
                self.link_clicked_signal.emit(anchor)
                super().mouseReleaseEvent(event)
                return

            # 2. 若未精准点中 anchor 节点，探测光标处的词汇实体
            try:
                cursor = self.cursorForPosition(pos)
                cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                w_text = cursor.selectedText().strip()
                if w_text:
                    self.link_clicked_signal.emit(f"word://{w_text}")
            except Exception:
                pass

        super().mouseReleaseEvent(event)


class GlobalMarketNewsDetailDialog(QDialog):
    """关联财经资讯与要闻解读详情弹窗 (支持自由缩放、最大化/最小化、上一条/下一条无缝切换与物理 JSON 持久化)"""

    def __init__(self, news_item: dict, parent=None, news_list: list = None, current_index: int = 0):
        super().__init__(parent)
        self.news_list = news_list if news_list else ([news_item] if news_item else [])
        if self.news_list:
            # 若传入的 current_index 不合法，根据 news_item 动态匹配
            if current_index < 0 or current_index >= len(self.news_list):
                try:
                    current_index = self.news_list.index(news_item)
                except ValueError:
                    current_index = 0
            self.current_index = max(0, min(current_index, len(self.news_list) - 1))
            self.news_item = self.news_list[self.current_index]
        else:
            self.current_index = 0
            self.news_item = news_item or {}

        # 允许自由拉伸缩放，支持标准 Windows 最小化/最大化/关闭按键
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(600, 440)
        self.resize(780, 540)
        self.setStyleSheet("""
            QDialog {
                background-color: #131722;
                color: #d1d4dc;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QLabel {
                color: #d1d4dc;
            }
        """)
        self._init_ui()
        self._refresh_content_ui()
        self._restore_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ---------------- 1. 顶部 Header 控件 ----------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)

        # 标签 + 影响分 + 来源 + 时间 行
        row1_layout = QHBoxLayout()
        self.lbl_tag = QLabel()
        self.lbl_tag.setStyleSheet("""
            background-color: #2962ff;
            color: #ffffff;
            font-size: 9pt;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 4px;
        """)
        row1_layout.addWidget(self.lbl_tag)

        self.lbl_score = QLabel()
        row1_layout.addWidget(self.lbl_score)

        row1_layout.addStretch(1)

        self.lbl_meta = QLabel()
        self.lbl_meta.setStyleSheet("color: #787b86; font-size: 9pt;")
        row1_layout.addWidget(self.lbl_meta)

        header_layout.addLayout(row1_layout)

        # 新闻大标题 (支持点击标记位股票名称直接联动)
        self.lbl_title = QLabel()
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setOpenExternalLinks(False)
        self.lbl_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.lbl_title.linkActivated.connect(self._on_link_activated)
        self.lbl_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #00F0FF; margin-top: 4px;")
        header_layout.addWidget(self.lbl_title)

        layout.addWidget(header_frame)

        # ---------------- 2. 新闻正文区域 (QTextBrowser 支持标记位高亮股票直接点击联动 & 右键智能翻译) ----------------
        self.txt_content = ClickableTextBrowser()
        self.txt_content.setReadOnly(True)
        self.txt_content.setOpenLinks(False)
        self.txt_content.link_clicked_signal.connect(self._on_link_activated)
        self.txt_content.anchorClicked.connect(self._on_anchor_clicked)
        self.txt_content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.txt_content.customContextMenuRequested.connect(self._show_context_menu)
        self.txt_content.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1e2b;
                color: #e1e4ec;
                border: 1px solid #2a2e39;
                border-radius: 6px;
                padding: 12px;
                font-size: 10.5pt;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.txt_content)

        # ---------------- 3. 底部关联标的与 翻页 / 翻译 / 关闭按键 ----------------
        bottom_layout = QHBoxLayout()
        
        # 关联标的容器
        self.rel_container = QWidget()
        self.rel_layout = QHBoxLayout(self.rel_container)
        self.rel_layout.setContentsMargins(0, 0, 0, 0)
        self.rel_layout.setSpacing(6)
        bottom_layout.addWidget(self.rel_container)

        bottom_layout.addStretch(1)

        # ⬅️ 上一条 & ➡️ 下一条 无缝切页复用按键
        self.btn_prev = QPushButton("⬅️ 上一条")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #262b3e; color: #d1d4dc; border: 1px solid #363c4e;
                border-radius: 4px; padding: 5px 12px; font-size: 9.5pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #363c4e; color: #ffffff; }
            QPushButton:disabled { background-color: #191d26; color: #434651; border-color: #262933; }
        """)
        self.btn_prev.clicked.connect(lambda: self._switch_to_index(self.current_index - 1))
        bottom_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("➡️ 下一条")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #262b3e; color: #d1d4dc; border: 1px solid #363c4e;
                border-radius: 4px; padding: 5px 12px; font-size: 9.5pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #363c4e; color: #ffffff; }
            QPushButton:disabled { background-color: #191d26; color: #434651; border-color: #262933; }
        """)
        self.btn_next.clicked.connect(lambda: self._switch_to_index(self.current_index + 1))
        bottom_layout.addWidget(self.btn_next)

        # 🌐 一键在线英译中按键
        self.btn_translate = QPushButton("🌐 在线英译中 (Translate)")
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.setStyleSheet("""
            QPushButton {
                background-color: #2962ff;
                color: #ffffff;
                border: 1px solid #3d71ff;
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 9.5pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e53e5;
            }
        """)
        self.btn_translate.clicked.connect(lambda: self._translate_text_async(self.txt_content.toPlainText(), mode='full'))
        bottom_layout.addWidget(self.btn_translate)

        btn_close = QPushButton("关闭 (Close)")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #2a2e39;
                color: #ffffff;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 5px 16px;
                font-size: 9.5pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #363c4e;
            }
        """)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    def _refresh_content_ui(self):
        """刷新新闻正文、 Header 与关联标的节点 (无缝全量更新)"""
        if not self.news_item:
            return

        # 1. 窗口标题与页码指示
        title_text = self.news_item.get('title', '财经资讯详情')
        total_count = len(self.news_list) if self.news_list else 1
        page_info = f"({self.current_index + 1}/{total_count})" if total_count > 1 else ""
        self.setWindowTitle(f"📰 {title_text} {page_info}")

        # 2. Tag & Header
        tag_str = self.news_item.get('tag', '🌐 财经要闻')
        self.lbl_tag.setText(tag_str)

        score = float(self.news_item.get('impact_score', 0.0))
        score_color = "#F6465D" if score >= 0 else "#089981"
        self.lbl_score.setText(f"影响评级: {score:+.1f} 分")
        self.lbl_score.setStyleSheet(f"""
            background-color: #1a2233;
            color: {score_color};
            font-size: 9pt;
            font-weight: bold;
            padding: 3px 8px;
            border: 1px solid {score_color};
            border-radius: 4px;
        """)

        dt_str = self.news_item.get('datetime', '')
        source_str = self.news_item.get('source', '')
        self.lbl_meta.setText(f"⏱️ {dt_str}  |  📡 来源: {source_str}")

        # 新闻大标题 (支持点击标记位股票名称直接联动)
        title_raw = self.news_item.get('title', '')
        title_html = highlight_stock_names_in_html(title_raw, self)
        if title_html != title_raw:
            self.lbl_title.setText(title_html)
        else:
            self.lbl_title.setText(title_raw)

        # 3. 正文区域
        content_text = self.news_item.get('content', '') or self.news_item.get('summary', '')
        content_html = highlight_stock_names_in_html(content_text, self)
        if content_html != content_text:
            self.txt_content.setHtml(f"<div style='font-family: sans-serif; line-height: 1.6;'>{content_html}</div>")
        else:
            self.txt_content.setPlainText(content_text)

        # 重置翻译按键状态
        self.btn_translate.setText("🌐 在线英译中 (Translate)")
        self.btn_translate.setEnabled(True)

        # 4. 动态更新关联标的
        # 清理旧节点
        while self.rel_layout.count():
            item = self.rel_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rel_symbols = self.news_item.get('related_symbols', [])
        if rel_symbols:
            lbl_rel_title = QLabel("🎯 关联影响标的:")
            lbl_rel_title.setStyleSheet("color: #787b86; font-weight: bold; font-size: 9.5pt;")
            self.rel_layout.addWidget(lbl_rel_title)
            for s in rel_symbols:
                lbl_sym = QLabel(str(s))
                lbl_sym.setStyleSheet("""
                    background-color: #262b3e;
                    color: #FFD700;
                    border: 1px solid #363c4e;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-weight: bold;
                    font-size: 9pt;
                """)
                self.rel_layout.addWidget(lbl_sym)

        # 5. 更新【⬅️ 上一条】与【➡️ 下一条】的 Enable 状态
        if self.news_list and len(self.news_list) > 1:
            self.btn_prev.setEnabled(self.current_index > 0)
            self.btn_next.setEnabled(self.current_index < len(self.news_list) - 1)
            self.btn_prev.setText(f"⬅️ 上一条")
            self.btn_next.setText(f"➡️ 下一条")
        else:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)

    def _switch_to_index(self, new_idx: int):
        """无缝切换至指定索引的新闻 (原地刷新复用)"""
        if not self.news_list or new_idx < 0 or new_idx >= len(self.news_list):
            return
        self.current_index = new_idx
        self.news_item = self.news_list[self.current_index]
        self._refresh_content_ui()

    def _on_anchor_clicked(self, url):
        url_str = url.toString() if hasattr(url, 'toString') else str(url)
        self._on_link_activated(url_str)

    def _on_link_activated(self, link_str: str):
        if not link_str:
            return
        import re
        from urllib.parse import unquote
        raw_str = unquote(str(link_str)).strip()
        
        code = ""
        name = ""
        if "stock://" in raw_str:
            stock_part = raw_str.split("stock://")[-1]
            parts = stock_part.split("|")
            code = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else code
        elif "word://" in raw_str:
            w_name = raw_str.replace("word://", "").strip()
            name_map = get_global_stock_name_map(self)
            if w_name in name_map:
                code = name_map[w_name]
                name = w_name
            else:
                m_code = re.search(r'\b\d{6}\b', w_name)
                if m_code:
                    code = m_code.group(0)
        else:
            m_code = re.search(r'\b\d{6}\b', raw_str)
            if m_code:
                code = m_code.group(0)

        if code:
            trigger_stock_linkage(code, name, self)

    def _show_context_menu(self, pos):
        """右键弹出自定义极客翻译与复制上下文菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e222d;
                color: #d1d4dc;
                border: 1px solid #2a2e39;
                padding: 4px;
                font-size: 9.5pt;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #2962ff;
                color: #ffffff;
            }
        """)

        cursor = self.txt_content.textCursor()
        sel_text = cursor.selectedText().strip()

        if sel_text:
            disp_txt = sel_text[:14] + "..." if len(sel_text) > 14 else sel_text
            act_trans_sel = menu.addAction(f"🔤 翻译选中文本: [{disp_txt}]")
            act_trans_sel.triggered.connect(lambda: self._translate_text_async(sel_text, mode='selection'))

            act_copy = menu.addAction("📋 复制选中文本")
            act_copy.triggered.connect(self.txt_content.copy)
            menu.addSeparator()

        act_trans_full = menu.addAction("🌐 全文在线英译中 (Full Translate)")
        act_trans_full.triggered.connect(lambda: self._translate_text_async(self.txt_content.toPlainText(), mode='full'))

        act_select_all = menu.addAction("全选 (Select All)")
        act_select_all.triggered.connect(self.txt_content.selectAll)

        menu.exec(self.txt_content.mapToGlobal(pos))

    def _translate_text_async(self, text: str, mode: str = 'full'):
        """非阻塞异步发起英译中网络请求"""
        if not text or not text.strip():
            return
        
        self.btn_translate.setText("⏳ 翻译中...")
        self.btn_translate.setEnabled(False)

        raw_title = self.news_item.get('title', '') if mode == 'full' else ''
        self.trans_thread = OnlineTranslateWorkerThread(text, mode=mode, title=raw_title)
        self.trans_thread.translated_signal.connect(self._on_translation_finished)
        self.trans_thread.start()

    def _on_translation_finished(self, orig_text: str, trans_text: str, mode: str, trans_title: str):
        """翻译完成后的 UI 高亮与视图更新 handler (100% 纯 UI 渲染，零同步网络请求)"""
        self.btn_translate.setText("🌐 在线英译中 (Translate)")
        self.btn_translate.setEnabled(True)

        if not trans_text:
            return

        if mode == 'selection':
            # 在选选中区域下方插入醒目的中译注解
            cursor = self.txt_content.textCursor()
            insert_html = f'<br/><span style="color:#00E676; background-color:#14291f; font-weight:bold; padding:2px 6px; border-radius:3px;">👉【中文意译】: {trans_text}</span><br/>'
            cursor.insertHtml(insert_html)
        else:
            if trans_title:
                self.lbl_title.setText(trans_title)
            self.txt_content.setPlainText(trans_text)


    def _restore_settings(self):
        """恢复物理窗口几何尺寸位置"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                geom = data.get("ats_news_detail_dialog_geom")
                if geom:
                    self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
        except Exception:
            pass

    def _save_settings(self):
        """物理落盘持久化配置至 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_news_detail_dialog_geom", self.saveGeometry().toHex().data().decode('utf-8'))
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def accept(self):
        self._save_settings()
        super().accept()


class GlobalMarketKLineDialog(QDialog):
    """外盘资产 120 日 K 线 / OHLC 走势弹窗 (TradingView 风格极简暗黑画板)"""

    def __init__(self, symbol: str, name: str = "", parent=None):
        super().__init__(None)  # ⚡ 传入 None 使其成为完全独立的顶级 Window 窗口，支持多屏独立拖拽与全屏展宽
        self.symbol = symbol.strip().upper()
        self.name = name or self.symbol
        self.klines = []
        self.worker = None
        self.chart_mode = 'candlestick'  # 'candlestick' 或 'ohlc'
        self.show_boll = True  # 布林线 BOLL 显示开关
        self.zoom_mode = 'recent_60'  # 'recent_60' 或 'full_120'
        # 关联走势: {symbol: klines}
        self.related_symbols = get_related_symbols(self.symbol)
        self._related_klines_cache = {}   # {symbol: [kline_dict, ...]}
        self._related_workers = []        # RelatedKLineWorkerThread 列表 (防GC)

        # 0ms 瞬间加载磁盘物理持久化 JSON 缓存 (消除开屏等待空框)
        try:
            from JSONData.global_market_data import load_news_hotlist_json
            cached_hotlist, deleted_ids = load_news_hotlist_json()
            if cached_hotlist:
                self.news_items = [item for item in cached_hotlist if str(item.get('id')) not in deleted_ids]
            else:
                self.news_items = []
        except Exception:
            self.news_items = []
        self._news_worker = None

        self.setWindowTitle(f"📈 [{self.symbol} · {self.name}] 近 120 日外盘 K 线走势图与关联资讯")
        # 允许自由拉伸缩放，支持标准 Windows 最小化/最大化/关闭按键
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(780, 480)
        self.resize(1120, 680)
        from ats.ui.styles import apply_dark_theme
        apply_dark_theme(self)

        self.chart_mode = "candlestick"
        self.show_boll = True
        self.zoom_mode = "recent_60"
        self.data_source = "yahoo"

        self._init_ui()
        self._restore_settings()
        # ⚡ 15ms 非阻塞延迟调度填充新闻热榜，让 K 线画板 0 毫秒极速瞬间呈现在用户面前
        QTimer.singleShot(15, self._populate_news_list)

        # 连接全局代理与日志变更信号，实现跨窗口 100% 实时同步与跟持久化数据一致
        try:
            from ats.ui.proxy_dialog import GLOBAL_PROXY_EVENT_BRIDGE, GLOBAL_LOG_EVENT_BRIDGE
            GLOBAL_PROXY_EVENT_BRIDGE.proxy_changed_signal.connect(self._on_global_proxy_changed)
            GLOBAL_LOG_EVENT_BRIDGE.log_toggled_signal.connect(self._on_global_log_changed)
        except Exception as ex:
            pass

        self._load_news_async(force_refresh=False)
        self._load_fast_cached_or_async()

    def update_symbol(self, symbol: str, name: str = ""):
        """平滑动态无缝更新展现的外盘资产 symbol 与名称 (零销毁重建、零白屏等待)"""
        new_symbol = symbol.strip().upper()
        if self.symbol == new_symbol:
            return

        self.symbol = new_symbol
        self.name = name or self.symbol
        self.klines = []
        self.related_symbols = get_related_symbols(self.symbol)
        self._related_klines_cache = {}

        self.setWindowTitle(f"📈 [{self.symbol} · {self.name}] 近 120 日外盘 K 线走势图与关联资讯")
        if hasattr(self, 'lbl_title'):
            self.lbl_title.setText(f"🌐 {self.name} ({self.symbol})")
        if hasattr(self, 'lbl_price_info'):
            self.lbl_price_info.setText("最新价: -- | 涨跌: --")

        self._refresh_related_info_label()
        self._load_fast_cached_or_async()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ---------------- 1. 顶部 Header 控件 ----------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        self.lbl_title = QLabel(f"🌐 {self.name} ({self.symbol})")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #00F0FF; font-size: 12.5pt;")
        header_layout.addWidget(self.lbl_title)

        self.lbl_price_info = QLabel("最新价: -- | 涨跌: --")
        self.lbl_price_info.setStyleSheet("font-size: 10.5pt; font-weight: bold; margin-left: 10px;")
        header_layout.addWidget(self.lbl_price_info)

        # 关联品种实时涨跌标签 (仅当有关联品种时显示)
        self.lbl_related_info = QLabel("")
        self.lbl_related_info.setStyleSheet("""
            QLabel {
                font-size: 9pt;
                color: #9db2c6;
                margin-left: 8px;
                padding: 2px 8px;
                background: #1a1f2e;
                border: 1px solid #2a2e39;
                border-radius: 3px;
            }
        """)
        if self.related_symbols:
            header_layout.addWidget(self.lbl_related_info)
        self._refresh_related_info_label()  # 先展示缓存实时报价

        header_layout.addStretch(1)

        # 数据源选择按钮组
        self.btn_src_yahoo = QPushButton("Yahoo")
        self.btn_src_yahoo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_src_yahoo.clicked.connect(lambda: self._switch_data_source("yahoo"))
        header_layout.addWidget(self.btn_src_yahoo)

        self.btn_src_sina = QPushButton("新浪")
        self.btn_src_sina.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_src_sina.clicked.connect(lambda: self._switch_data_source("sina"))
        header_layout.addWidget(self.btn_src_sina)
        self._update_data_source_btn_style()

        # BOLL 线开关按键
        self.btn_boll_toggle = QPushButton("BOLL:开")
        self.btn_boll_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_boll_toggle.setStyleSheet("""
            QPushButton {
                background-color: #262b3e;
                color: #FF2A6D;
                border: 1px solid #FF2A6D;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
                font-weight: bold;
                min-width: 65px;
            }
            QPushButton:hover {
                background-color: #363c56;
            }
        """)
        self.btn_boll_toggle.clicked.connect(self._toggle_boll)
        header_layout.addWidget(self.btn_boll_toggle)

        # K线 / OHLC 模式切换按键
        self.btn_mode_toggle = QPushButton("美国线")
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.setStyleSheet("""
            QPushButton {
                background-color: #2962ff;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
                font-weight: bold;
                min-width: 55px;
            }
            QPushButton:hover {
                background-color: #1e54b7;
            }
        """)
        self.btn_mode_toggle.clicked.connect(self._toggle_chart_mode)
        header_layout.addWidget(self.btn_mode_toggle)

        # 视区快捷控制组
        self.btn_focus_60 = QPushButton("60日")
        self.btn_focus_60.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_focus_60.setStyleSheet("""
            QPushButton {
                background-color: #2a2e39;
                color: #d1d4dc;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 9pt;
                min-width: 45px;
            }
            QPushButton:hover {
                background-color: #363c4e;
                color: #ffffff;
            }
        """)
        self.btn_focus_60.clicked.connect(self._focus_recent_60)
        header_layout.addWidget(self.btn_focus_60)

        self.btn_focus_120 = QPushButton("120日")
        self.btn_focus_120.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_focus_120.setStyleSheet("""
            QPushButton {
                background-color: #2a2e39;
                color: #d1d4dc;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 9pt;
                min-width: 45px;
            }
            QPushButton:hover {
                background-color: #363c4e;
                color: #ffffff;
            }
        """)
        # 📐 FIB 黄金分割坐标系开关按键
        self.show_fib = True
        self.btn_fib_toggle = QPushButton("FIB:开")
        self.btn_fib_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fib_toggle.setStyleSheet("""
            QPushButton {
                background-color: #2a2233;
                color: #FFD700;
                border: 1px solid #FFD700;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 9pt;
                font-weight: bold;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: #3d2f4d;
                color: #ffffff;
            }
        """)
        self.btn_fib_toggle.clicked.connect(self._toggle_fib_mode)
        header_layout.addWidget(self.btn_fib_toggle)

        # 📰 关联资讯展开/收起控制按键
        self.btn_news_toggle = QPushButton("资讯:收起")
        self.btn_news_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_news_toggle.setStyleSheet("""
            QPushButton {
                background-color: #1a2233;
                color: #00F0FF;
                border: 1px solid #00F0FF;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
                font-weight: bold;
                min-width: 65px;
            }
            QPushButton:hover {
                background-color: #2962ff;
                color: #ffffff;
            }
        """)
        self.btn_news_toggle.clicked.connect(self._toggle_news_panel)
        header_layout.addWidget(self.btn_news_toggle)

        # 📜 日志开关按键
        self.btn_log_config = QPushButton("日志:关")
        self.btn_log_config.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log_config.clicked.connect(self._toggle_log_config)
        self._update_log_btn_style()
        header_layout.addWidget(self.btn_log_config)

        # 🌐 代理设置按键
        self.btn_proxy_toggle = QPushButton("代理:关")
        self.btn_proxy_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_proxy_toggle.clicked.connect(self._open_proxy_dialog)
        self._update_proxy_btn_style()
        header_layout.addWidget(self.btn_proxy_toggle)

        layout.addWidget(header_frame)

        # ---------------- 2. 动态信息条 (Info Banner) ----------------
        self.lbl_info = QLabel("提示: 鼠标悬浮移入画板查看开高低收明细与指标数据")
        self.lbl_info.setStyleSheet("""
            QLabel {
                background-color: #181c27;
                border: 1px solid #232733;
                border-radius: 4px;
                padding: 4px 10px;
                color: #9db2c6;
                font-size: 9.5pt;
            }
        """)
        layout.addWidget(self.lbl_info)

        # ---------------- 3. 水平 QSplitter 容器 (包裹左侧 K线走势图 + 右侧关联财经资讯侧边栏) ----------------
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setHandleWidth(6)
        self.h_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #1e222d;
                border-left: 1px solid #2a2e39;
                border-right: 1px solid #2a2e39;
            }
            QSplitter::handle:hover {
                background: #00F0FF;
            }
        """)

        # 3.1 左侧垂直 QSplitter 包裹三个 GraphicsLayoutWidget
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(5)
        self.v_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #1e222d;
                border-top: 1px solid #2a2e39;
                border-bottom: 1px solid #2a2e39;
            }
            QSplitter::handle:hover {
                background: #2962ff;
                border-top: 1px solid #2962ff;
                border-bottom: 1px solid #2962ff;
            }
            QSplitter::handle:pressed {
                background: #1e54b7;
            }
        """)

        # 主 K 线图窗口
        self.gw_kline = pg.GraphicsLayoutWidget()
        self.gw_kline.setBackground('#131722')
        self.date_axis = DateAxisItem(orientation='bottom')
        self.date_axis.setPen(pg.mkPen('#363c4e'))
        self.date_axis.setTextPen(pg.mkPen('#787b86'))
        self.p_kline = self.gw_kline.addPlot(row=0, col=0, axisItems={'bottom': self.date_axis})
        self.p_kline.showGrid(x=True, y=True, alpha=0.18)
        self.p_kline.getAxis('left').setPen(pg.mkPen('#363c4e'))
        self.p_kline.getAxis('left').setTextPen(pg.mkPen('#787b86'))
        self.p_kline.hideButtons()
        # 禁用原生 Y 轴 AutoRange，由 _auto_fit_y_range 自动实时居中拉伸自适应
        self.p_kline.vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.p_kline.sigXRangeChanged.connect(lambda *args: self._auto_fit_y_range())
        self.gw_kline.setMinimumHeight(200)
        self.v_splitter.addWidget(self.gw_kline)

        # 成交量 Subplot 窗口
        self.gw_vol = pg.GraphicsLayoutWidget()
        self.gw_vol.setBackground('#131722')
        self.vol_axis = VolumeAxisItem(orientation='left')
        self.vol_axis.setPen(pg.mkPen('#363c4e'))
        self.vol_axis.setTextPen(pg.mkPen('#787b86'))
        self.p_vol = self.gw_vol.addPlot(
            row=0, col=0,
            axisItems={'left': self.vol_axis, 'bottom': DateAxisItem(orientation='bottom')}
        )
        self.p_vol.showGrid(x=True, y=True, alpha=0.18)
        self.p_vol.getAxis('bottom').setPen(pg.mkPen('#363c4e'))
        self.p_vol.getAxis('bottom').setTextPen(pg.mkPen('#787b86'))
        self.p_vol.hideButtons()
        self.p_vol.setXLink(self.p_kline)
        self.gw_vol.setMinimumHeight(60)
        self.v_splitter.addWidget(self.gw_vol)

        # 十字光标 Crosshair
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DashLine, width=1))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DashLine, width=1))
        self.p_kline.addItem(self.v_line, ignoreBounds=True)
        self.p_kline.addItem(self.h_line, ignoreBounds=True)
        self.proxy = pg.SignalProxy(self.p_kline.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

        # 关联走势对比子图窗口 (仅当有关联品种时创建)
        self.p_related = None
        self.gw_related = None
        if self.related_symbols:
            self.gw_related = pg.GraphicsLayoutWidget()
            self.gw_related.setBackground('#131722')
            rel_label = pg.AxisItem(orientation='left')
            rel_label.setPen(pg.mkPen('#363c4e'))
            rel_label.setTextPen(pg.mkPen('#787b86'))
            self.p_related = self.gw_related.addPlot(
                row=0, col=0,
                axisItems={'left': rel_label, 'bottom': DateAxisItem(orientation='bottom')}
            )
            self.p_related.showGrid(x=True, y=True, alpha=0.15)
            self.p_related.getAxis('bottom').setPen(pg.mkPen('#363c4e'))
            self.p_related.getAxis('bottom').setTextPen(pg.mkPen('#787b86'))
            self.p_related.hideButtons()
            self.p_related.setXLink(self.p_kline)
            self.gw_related.setMinimumHeight(80)
            self.v_splitter.addWidget(self.gw_related)

        if self.related_symbols:
            self.v_splitter.setSizes([360, 120, 120])
        else:
            self.v_splitter.setSizes([420, 140])

        self.v_splitter.splitterMoved.connect(self._on_splitter_moved)
        self.h_splitter.addWidget(self.v_splitter)

        # 3.2 右侧关联财经资讯/要闻侧边栏面板 (news_panel)
        self._init_news_panel()
        self.h_splitter.addWidget(self.news_panel)

        # 设置水平 Splitter 默认比例: K线图70% / 资讯侧边栏30%
        self.h_splitter.setSizes([770, 330])
        self.h_splitter.splitterMoved.connect(self._on_splitter_moved)

        layout.addWidget(self.h_splitter)

    def _init_news_panel(self):
        """构建右侧权威自选财经热榜侧边栏面板 (支持自动英译中、物理 JSON 持久化与右键删除)"""
        self.news_panel = QFrame()
        self.news_panel.setStyleSheet("""
            QFrame {
                background-color: #181c27;
                border: 1px solid #2a2e39;
                border-radius: 6px;
            }
        """)
        news_layout = QVBoxLayout(self.news_panel)
        news_layout.setContentsMargins(8, 8, 8, 8)
        news_layout.setSpacing(6)

        # Header 标题栏
        header_box = QHBoxLayout()
        self.lbl_news_hdr = QLabel(f"🔥 权威自选热榜 ({len(self.news_items)}/20)")
        self.lbl_news_hdr.setStyleSheet("font-weight: bold; color: #00F0FF; font-size: 10.0pt;")
        header_box.addWidget(self.lbl_news_hdr)
        header_box.addStretch(1)

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #1e222d;
                color: #00F0FF;
                border: 1px solid #2962ff;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #2962ff;
                color: #ffffff;
            }
        """)
        btn_refresh.clicked.connect(self._on_refresh_news_clicked)
        header_box.addWidget(btn_refresh)

        lbl_tip = QLabel("右键可删除")
        lbl_tip.setStyleSheet("color: #787b86; font-size: 8.5pt;")
        header_box.addWidget(lbl_tip)

        news_layout.addLayout(header_box)

        # 资讯列表 QListWidget
        self.lst_news = QListWidget()
        self.lst_news.setStyleSheet("""
            QListWidget {
                background-color: #131722;
                border: 1px solid #232733;
                border-radius: 4px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 4px;
                margin-bottom: 6px;
                padding: 6px;
                color: #d1d4dc;
            }
            QListWidget::item:hover {
                background-color: #262b3e;
                border-color: #00F0FF;
            }
            QListWidget::item:selected {
                background-color: #2a344a;
                border-color: #2962ff;
            }
        """)
        self.lst_news.itemDoubleClicked.connect(self._on_news_item_double_clicked)
        self.lst_news.itemClicked.connect(self._on_news_item_clicked)

        # 启用右键上下文菜单
        self.lst_news.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lst_news.customContextMenuRequested.connect(self._show_news_context_menu)

        self._populate_news_list()
        news_layout.addWidget(self.lst_news)
        self._start_auto_refresh_timer()

    def _populate_news_list(self):
        """填充资讯列表条目 (限制显示不超过 20 条)"""
        self.lst_news.clear()
        display_items = (self.news_items or [])[:20]
        self.lbl_news_hdr.setText(f"🔥 权威自选热榜 ({len(display_items)}/20)")
        if hasattr(self, 'btn_news_toggle'):
            vis_str = "收起" if (hasattr(self, 'news_panel') and self.news_panel.isVisible()) else "展开"
            self.btn_news_toggle.setText(f"资讯:{vis_str}")

        if not display_items:
            item = QListWidgetItem("暂无相关权威财经热榜")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lst_news.addItem(item)
            return

        for news in display_items:
            title = news.get('title', '')
            dt = news.get('datetime', '')
            tag = news.get('tag', '🔥 热榜')
            score = float(news.get('impact_score', 0.0))
            score_color = "#F6465D" if score >= 0 else "#089981"
            summary = news.get('summary', '')

            # 自动识别新闻中的股票名称代码实体
            entities = extract_stock_entities_from_text(title + ' ' + summary, self)
            entity_tag_html = ""
            if entities:
                ent_strs = [f"<b style='color:#00ff88; padding:0 3px;'>⚡ [{e['code']} {e['name']}]</b>" for e in entities[:3]]
                entity_tag_html = f"<div style='margin-top: 4px; font-size: 8.5pt;'>{' '.join(ent_strs)}</div>"

            # 简易多行格式化 HTML (突出自动翻译后的中文字样与识别到的股票实体)
            title_highlighted = highlight_stock_names_in_html(title, self)
            item_text = (
                f"<div style='font-size: 8.5pt; color: #787b86; margin-bottom: 3px;'>"
                f"<b style='color: #2962ff;'>[{tag}]</b> &nbsp; ⏱️ {dt} &nbsp; "
                f"<b style='color: {score_color};'>影响: {score:+.1f}</b>"
                f"</div>"
                f"<div style='font-size: 9.5pt; font-weight: bold; color: #00F0FF; line-height: 1.3;'>{title_highlighted}</div>"
                f"<div style='font-size: 8.5pt; color: #9db2c6; margin-top: 4px;'>{summary[:65]}...</div>"
                f"{entity_tag_html}"
            )

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, news)

            lbl = QLabel(item_text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background: transparent; padding: 2px;")

            item.setSizeHint(lbl.sizeHint())
            self.lst_news.addItem(item)
            self.lst_news.setItemWidget(item, lbl)

    def _on_news_item_clicked(self, item: QListWidgetItem):
        """单击列表项更新 Banner 提示"""
        news = item.data(Qt.ItemDataRole.UserRole)
        if news and isinstance(news, dict):
            self.lbl_info.setText(f"📰 双击查看要闻正文: 【{news.get('tag', '')}】{news.get('title', '')}")

    def _on_news_item_double_clicked(self, item: QListWidgetItem):
        """双击列表项瞬间弹出 GlobalMarketNewsDetailDialog 查看深度正文与评估"""
        news = item.data(Qt.ItemDataRole.UserRole)
        if news and isinstance(news, dict):
            idx = self.lst_news.row(item)
            dlg = GlobalMarketNewsDetailDialog(news, self, news_list=self.news_items, current_index=idx)
            dlg.exec()

    def _on_refresh_news_clicked(self):
        """一键强制刷新全网权威财经热榜 (后台异步极速加载，绝不卡死 UI)"""
        if hasattr(self, 'lbl_info'):
            self.lbl_info.setText("⏳ 正在后台极速刷新全网权威财经热榜...")
        self._load_news_async(force_refresh=True)

    def _load_news_async(self, force_refresh: bool = False):
        """后台异步线程加载财经要闻，确保 UI 主线程绝不卡死挂起 (未响应 0 容忍)"""
        if getattr(self, '_news_worker', None) and self._news_worker.isRunning():
            return
        
        if hasattr(self, 'lbl_news_hdr'):
            self.lbl_news_hdr.setText("🔥 权威自选热榜 (加载中...)")

        self._news_worker = NewsWorkerThread(self.symbol, self.name, force_refresh=force_refresh)
        self._news_worker.finished_signal.connect(self._on_news_loaded)
        self._news_worker.start()

    def _on_news_loaded(self, items: list, err_msg: str):
        """新闻异步加载完成后的 UI 刷新槽函数"""
        self.news_items = items or []
        if hasattr(self, 'lbl_news_hdr'):
            self.lbl_news_hdr.setText(f"🔥 权威自选热榜 ({len(self.news_items)}/20)")
        if hasattr(self, 'btn_news_toggle'):
            is_vis = self.news_panel.isVisible() if hasattr(self, 'news_panel') else True
            state_str = "收起" if is_vis else "展开"
            self.btn_news_toggle.setText(f"📰 资讯({len(self.news_items)}条): {state_str}")
        self._populate_news_list()
        if hasattr(self, 'lbl_info'):
            self.lbl_info.setText(f"✅ 已载入最新权威自选热榜资讯 ({len(self.news_items)} 条)")

    def _show_news_context_menu(self, pos):
        """右键弹出资讯上下文菜单: 支持物理删除早期无用资讯、剪贴板复制与清空操作"""
        item = self.lst_news.itemAt(pos)
        if not item:
            return

        news = item.data(Qt.ItemDataRole.UserRole)
        if not news or not isinstance(news, dict):
            return

        news_id = news.get('id', '')
        news_title = news.get('title', '')

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e222d;
                color: #d1d4dc;
                border: 1px solid #2a2e39;
            }
            QMenu::item:selected {
                background-color: #2962ff;
                color: #ffffff;
            }
        """)

        act_delete = menu.addAction(f"🗑️ 删除此条资讯 (物理持久化剔除)")
        act_prune = menu.addAction("🧹 仅保留最新 10 条 (清理早期旧资讯)")
        menu.addSeparator()
        act_copy = menu.addAction("📋 复制标题与摘要内容")
        act_detail = menu.addAction("🔍 查看深度正文解读")

        action = menu.exec(self.lst_news.mapToGlobal(pos))
        if action == act_delete:
            if news_id:
                delete_news_item_by_id(news_id)
                self.news_items = [n for n in self.news_items if n.get('id') != news_id]
                self._populate_news_list()
                self.lbl_info.setText(f"🗑️ 已成功物理删除此条资讯: 【{news_title[:20]}...】")
        elif action == act_prune:
            if len(self.news_items) > 10:
                removed_items = self.news_items[10:]
                for rm in removed_items:
                    rm_id = rm.get('id')
                    if rm_id:
                        delete_news_item_by_id(rm_id)
                self.news_items = self.news_items[:10]
                self._populate_news_list()
                self.lbl_info.setText(f"🧹 已清理早期旧资讯，成功保留最新 10 条权威热榜")
        elif action == act_copy:
            summary = news.get('summary', '')
            text_to_copy = f"{news_title}\n{summary}"
            QApplication.clipboard().setText(text_to_copy)
            self.lbl_info.setText(f"📋 已复制资讯标题与摘要至剪贴板")
        elif action == act_detail:
            idx = self.lst_news.row(item)
            dlg = GlobalMarketNewsDetailDialog(news, self, news_list=self.news_items, current_index=idx)
            dlg.exec()

    def _toggle_news_panel(self):
        """切换右侧资讯侧边栏的展开与折叠 (收起)"""
        is_vis = self.news_panel.isVisible()
        if is_vis:
            self.news_panel.hide()
            self.btn_news_toggle.setText(f"📰 资讯({len(self.news_items)}条): 展开")
            self.btn_news_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #2a2e39;
                    color: #d1d4dc;
                    border: 1px solid #363c4e;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 9pt;
                    min-width: 110px;
                }
                QPushButton:hover {
                    background-color: #363c4e;
                    color: #ffffff;
                }
            """)
        else:
            self.news_panel.show()
            self.btn_news_toggle.setText(f"📰 资讯({len(self.news_items)}条): 收起")
            self.btn_news_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #1a2233;
                    color: #00F0FF;
                    border: 1px solid #00F0FF;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 9pt;
                    font-weight: bold;
                    min-width: 110px;
                }
                QPushButton:hover {
                    background-color: #2962ff;
                    color: #ffffff;
                }
            """)
        self._on_splitter_moved(0, 0)
        self._start_auto_refresh_timer()

    def _start_auto_refresh_timer(self):
        """启动子窗口自动轮询定时器，依据统一系统更新阈值时间 (交易期 60s, 非交易期 600s) 定时同步关联行情与自选要闻"""
        try:
            from JSONData.global_market_data import get_global_market_cache_ttl
            interval_sec = get_global_market_cache_ttl()
        except Exception:
            interval_sec = 60.0

        self._news_timer = QTimer(self)
        self._news_timer.setInterval(int(interval_sec * 1000))
        self._news_timer.timeout.connect(self._on_auto_refresh_timer_timeout)
        self._news_timer.start()

    def _on_auto_refresh_timer_timeout(self):
        """定时器到期回调: 重新检测并动态调整轮询间隔，自动无感更新关联实时数据、最新K线与热榜要闻"""
        try:
            from JSONData.global_market_data import get_global_market_cache_ttl, is_market_active_time, fetch_global_market_quotes
            interval_sec = get_global_market_cache_ttl()
            self._news_timer.setInterval(int(interval_sec * 1000))

            # 在美股/外盘活跃交易期，定时触发实时行情切片刷新与 K 线动态重绘 (受到 300s/900s 梯度冷却锁保护，绝不高频刷接口)
            if is_market_active_time():
                fetch_global_market_quotes(force_refresh=True)
                self._trigger_async_load(force_refresh=False)
        except Exception:
            pass

        self._refresh_related_info_label()
        # 异步加载新闻，绝对不能在定时器触发的主线程发起同步 HTTP 网络抓取！
        self._load_news_async(force_refresh=True)



    def _update_data_source_btn_style(self):
        """根据当前的 data_source 动态更新数据源按键高亮样式"""
        src = (self.data_source or 'yahoo').lower()
        active_style = """
            QPushButton {
                background-color: #2962ff;
                color: #ffffff;
                border: 1px solid #00F0FF;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
                font-weight: bold;
                min-width: 90px;
            }
        """
        normal_style = """
            QPushButton {
                background-color: #1e222d;
                color: #787b86;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #2a2e39;
                color: #d1d4dc;
            }
        """
        if src == 'yahoo':
            self.btn_src_yahoo.setStyleSheet(active_style)
            self.btn_src_sina.setStyleSheet(normal_style)
        else:
            self.btn_src_yahoo.setStyleSheet(normal_style)
            self.btn_src_sina.setStyleSheet(active_style)

    def _switch_data_source(self, new_source: str):
        """用户点击数据源按键，实时切换数据源并持久化"""
        if self.data_source == new_source and self.klines:
            return
        self.data_source = new_source
        self._update_data_source_btn_style()
        self._save_settings()
        self.klines = []
        self.lbl_info.setText(f"🌐 已切换至数据源: {'🇺🇸 Yahoo Finance (权威连续)' if new_source == 'yahoo' else '📡 新浪财经'}，正在刷新...")
        self._load_fast_cached_or_async()

    def _toggle_boll(self):
        """切换 BOLL 布林线显示状态"""
        self.show_boll = not self.show_boll
        if self.show_boll:
            self.btn_boll_toggle.setText("BOLL:开")
            self.btn_boll_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #262b3e;
                    color: #FF2A6D;
                    border: 1px solid #FF2A6D;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 9pt;
                    font-weight: bold;
                    min-width: 65px;
                }
                QPushButton:hover {
                    background-color: #363c56;
                }
            """)
        else:
            self.btn_boll_toggle.setText("BOLL:关")
            self.btn_boll_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #1e222d;
                    color: #787b86;
                    border: 1px solid #363c4e;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 9pt;
                    min-width: 65px;
                }
                QPushButton:hover {
                    background-color: #2a2e39;
                    color: #d1d4dc;
                }
            """)
        self._draw_chart()

    def _toggle_chart_mode(self):
        """切换 🕯️ 蜡烛图 (Candlestick) 与 📊 竹节线 (OHLC)"""
        if self.chart_mode == 'candlestick':
            self.chart_mode = 'ohlc'
            self.btn_mode_toggle.setText("蜡烛图")
        else:
            self.chart_mode = 'candlestick'
            self.btn_mode_toggle.setText("美国线")
        self._draw_chart()

    def _load_fast_cached_or_async(self):
        """0 毫秒极速读取本地 JSON 缓存；若无缓存则触发后台异步线程"""
        src_key = (self.data_source or 'yahoo').lower()
        cache_path = get_kline_cache_file_path().replace(".json", f"_{src_key}.json")
        log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} 检查 [{src_key}] 外盘 K线物理持久化文件路径: {cache_path}")
        cached_klines = []
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                    cached_klines = all_data.get(self.symbol, [])
            except Exception as ex:
                log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} 读取本地 K线缓存文件异常: {ex}")
                cached_klines = []

        if cached_klines and len(cached_klines) >= 5:
            # 本地有缓存，瞬间秒载渲染，无任何卡顿！
            log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} 0ms 瞬间秒载 [{src_key}] 本地 K线缓存 ({len(cached_klines)} 条) -> {self.symbol}")
            self.klines = cached_klines
            self._draw_chart()
            self._apply_zoom_mode()
            # 异步加载关联品种 K 线
            self._trigger_related_loads()

            # 非外盘交易窗口 (如周末/休市)，已有缓存直接锁定，绝对不触发异步网络请求！
            from JSONData.global_market_data import is_market_active_time
            if not is_market_active_time():
                log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} 当前处于外盘休市/非交易时间，已命中本地物理 JSON 缓存，停止网络抓取 -> {self.symbol}")
                return

        # 后台异步抓取最新或静默刷新
        from JSONData.global_market_data import is_market_active_time
        force_flag = True if is_market_active_time() else (False if (cached_klines and len(cached_klines) >= 5) else True)
        self._trigger_async_load(force_refresh=force_flag)

    def _trigger_async_load(self, force_refresh: bool = False):
        if self.worker and self.worker.isRunning():
            return

        if not self.klines and hasattr(self, 'lbl_info'):
            self.lbl_info.setText(f"🌐 正在后台异步加载 [{self.data_source}] 最新外盘 K 线数据...")

        self.worker = KLineWorkerThread(self.symbol, force_refresh=force_refresh, data_source=self.data_source)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, klines: list, err_msg: str):
        cache_path = get_kline_cache_file_path()
        if klines and len(klines) >= 5:
            self.klines = klines
            log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} K线数据加载完成 ({len(klines)} 条)，物理文件: {cache_path}")
            self._draw_chart()
            self._apply_zoom_mode()
            # 主 K 线数据就绪后再触发关联品种加载
            self._trigger_related_loads()
            last_date = klines[-1].get('date', '') if klines else ''
            last_close = float(klines[-1].get('close', 0.0)) if klines else 0.0
            last_pct = float(klines[-1].get('pct', 0.0)) if klines else 0.0
            if hasattr(self, 'lbl_info'):
                self.lbl_info.setText(f"✅ [{self.data_source.upper()}源] K 线数据加载成功: {len(klines)} 条日K线 (最新切片: {last_date}, 点位: {last_close:.2f}, {last_pct:+.2f}%)")
        elif not self.klines:
            log_market_msg(f"[GlobalMarketKLineDialog] {get_proxy_info_str()} K线数据加载失败: {err_msg} | 持久化路径: {cache_path}")
            if hasattr(self, 'lbl_info'):
                self.lbl_info.setText(f"❌ K 线数据加载失败: {err_msg or '网络或解析异常'}")

    def _refresh_related_info_label(self):
        """刷新 Header 关联品种实时涨跌标签"""
        if not self.related_symbols:
            return
        try:
            from JSONData.global_market_data import _global_cache
            quotes = _global_cache.get('quotes', {})
            parts = []
            for rel in self.related_symbols:
                sym = rel['symbol']
                name = rel['name']
                q = quotes.get(sym, {})
                if q and 'pct' in q:
                    pct = float(q['pct'])
                    color_tag = 'red' if pct >= 0 else 'green'
                    parts.append(f"<font color='{color_tag}'>{name} {pct:+.2f}%</font>")
                else:
                    parts.append(f"{name} --")
            if parts:
                self.lbl_related_info.setText(' | '.join(parts))
        except Exception:
            pass

    def _trigger_related_loads(self):
        """后台异步加载各关联品种 K 线，不阻塞主图渲染"""
        if not self.related_symbols or self.p_related is None:
            return
        # 先尝试从本地缓存块速加载
        cache_path = get_kline_cache_file_path()
        all_data = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
            except Exception:
                pass

        for rel in self.related_symbols:
            sym = rel['symbol']
            cached = all_data.get(sym, [])
            if cached and len(cached) >= 10:
                # 本地缓存存在，直接更新缓存并绘图
                self._related_klines_cache[sym] = cached
            else:
                # 启动后台线程加载
                w = RelatedKLineWorkerThread(sym)
                w.finished_signal.connect(self._on_related_klines_loaded)
                w.start()
                self._related_workers.append(w)  # 防止被 GC

        # 尝试即刻绘制已有缓存的关联走势
        if self._related_klines_cache:
            self._draw_related_chart()

    def _on_related_klines_loaded(self, symbol: str, klines: list):
        """关联品种 K 线后台成功回调"""
        if klines and len(klines) >= 5:
            self._related_klines_cache[symbol] = klines
            self._draw_related_chart()

    def _draw_related_chart(self):
        """绘制关联走势对比子图 - 合并对齐日期后按特定起点归一化为百分比变化曲线"""
        if not self.p_related or not self.klines:
            return

        self.p_related.clear()
        n_main = len(self.klines)
        main_dates = [item['date'] for item in self.klines]

        # 主品种归一化基准线 (0% 基准线)
        zero_line = pg.InfiniteLine(
            angle=0, pos=0.0, movable=False,
            pen=pg.mkPen('#363c4e', width=1, style=Qt.PenStyle.DashLine)
        )
        self.p_related.addItem(zero_line)

        # 主品种归一化曲线
        main_closes = [float(x['close']) for x in self.klines]
        base0 = main_closes[0] if main_closes[0] != 0 else 1.0
        main_pct = [(c / base0 - 1.0) * 100.0 for c in main_closes]
        self.p_related.plot(
            list(range(n_main)), main_pct,
            pen=pg.mkPen('#00F0FF', width=2.0),
            name=self.name
        )

        # 各关联品种归一化曲线
        for rel in self.related_symbols:
            sym = rel['symbol']
            color = rel['color']
            name = rel['name']
            is_inverse = rel.get('inverse', False)

            rel_klines = self._related_klines_cache.get(sym, [])
            if not rel_klines:
                continue

            # 日期对齐: 找到与主 K 线对齐的起始日期
            rel_dates = [item['date'] for item in rel_klines]
            rel_closes_map = {item['date']: float(item['close']) for item in rel_klines}

            # 按主 K 线日期对齐抗取关联品种收盘价
            aligned_closes = []
            aligned_x = []
            for i, d in enumerate(main_dates):
                c = rel_closes_map.get(d)
                if c is not None and c > 0:
                    aligned_closes.append(c)
                    aligned_x.append(i)

            if len(aligned_closes) < 5:
                continue

            base_c = aligned_closes[0]
            if base_c == 0:
                continue
            rel_pct = [(c / base_c - 1.0) * 100.0 for c in aligned_closes]
            if is_inverse:
                rel_pct = [-v for v in rel_pct]

            pen = pg.mkPen(color, width=1.5)
            self.p_related.plot(aligned_x, rel_pct, pen=pen, name=f"{name}{'(反)' if is_inverse else ''}")

            # 小标签显示最新百分比偷
            if aligned_x and rel_pct:
                last_x = aligned_x[-1]
                last_y = rel_pct[-1]
                inv_note = '[反相关]' if is_inverse else ''
                label = pg.TextItem(
                    text=f"{name}{inv_note} {last_y:+.1f}%",
                    color=color,
                    anchor=(0, 0.5)
                )
                self.p_related.addItem(label)
                label.setPos(last_x + 0.5, last_y)

        # 主品种标签
        if main_pct:
            main_label = pg.TextItem(
                text=f"{self.name} {main_pct[-1]:+.1f}%",
                color='#00F0FF',
                anchor=(0, 0.5)
            )
            self.p_related.addItem(main_label)
            main_label.setPos(n_main - 1 + 0.5, main_pct[-1])



    def _draw_chart(self):
        self.p_kline.clear()
        self.p_vol.clear()

        # 重新置入 Crosshair
        self.p_kline.addItem(self.v_line, ignoreBounds=True)
        self.p_kline.addItem(self.h_line, ignoreBounds=True)

        n = len(self.klines)
        if n == 0:
            return

        dates = [item['date'] for item in self.klines]
        opens = [float(item['open']) for item in self.klines]
        closes = [float(item['close']) for item in self.klines]
        lows = [float(item['low']) for item in self.klines]
        highs = [float(item['high']) for item in self.klines]
        vols = [float(item.get('volume', 0)) for item in self.klines]

        # 刷新日期 Axis
        self.date_axis.set_dates(dates)

        # 最新价与涨跌幅 Header 控件更新
        last_item = self.klines[-1]
        last_c = float(last_item['close'])
        last_pct = float(last_item['pct'])
        color_str = "#F6465D" if last_pct >= 0 else "#089981"
        self.lbl_price_info.setText(
            f"最新价: <font color='{color_str}'>{last_c:.2f}</font> | "
            f"涨跌: <font color='{color_str}'>{last_pct:+.2f}%</font>"
        )

        # 1. 绘制 Pro 级 蜡烛图 (Candlestick) 或 竹节线 (OHLC)
        candle_data = [(i, opens[i], closes[i], lows[i], highs[i]) for i in range(n)]
        if self.chart_mode == 'ohlc':
            chart_item = OHLCItem(candle_data)
        else:
            chart_item = CandlestickItem(candle_data)
        self.p_kline.addItem(chart_item)

        # 2. 计算均线 MA5 / MA20 / MA60 与 BOLL 布林线
        def calc_ma(period):
            ma = []
            for i in range(n):
                if i < period - 1:
                    ma.append(None)
                else:
                    sub = closes[i - period + 1: i + 1]
                    ma.append(sum(sub) / len(sub))
            return ma

        def calc_std(period, ma_list):
            std_list = []
            for i in range(n):
                if i < period - 1 or ma_list[i] is None:
                    std_list.append(None)
                else:
                    sub = closes[i - period + 1: i + 1]
                    m = ma_list[i]
                    variance = sum((x - m) ** 2 for x in sub) / len(sub)
                    std_list.append(variance ** 0.5)
            return std_list

        self.ma5 = calc_ma(5)
        self.ma20 = calc_ma(20)
        self.ma60 = calc_ma(60)

        # 计算 BOLL 布林线 (20, 2)
        std20 = calc_std(20, self.ma20)
        self.boll_upper = [self.ma20[i] + 2 * std20[i] if (self.ma20[i] is not None and std20[i] is not None) else None for i in range(n)]
        self.boll_lower = [self.ma20[i] - 2 * std20[i] if (self.ma20[i] is not None and std20[i] is not None) else None for i in range(n)]

        x_indices = list(range(n))

        # 绘制均线
        valid_ma5_x = [x_indices[i] for i in range(n) if self.ma5[i] is not None]
        valid_ma5_y = [self.ma5[i] for i in range(n) if self.ma5[i] is not None]
        self.p_kline.plot(valid_ma5_x, valid_ma5_y, pen=pg.mkPen('#f0b90b', width=1.5), name="MA5")

        valid_ma20_x = [x_indices[i] for i in range(n) if self.ma20[i] is not None]
        valid_ma20_y = [self.ma20[i] for i in range(n) if self.ma20[i] is not None]
        self.p_kline.plot(valid_ma20_x, valid_ma20_y, pen=pg.mkPen('#00F0FF', width=1.5), name="MA20")

        valid_ma60_x = [x_indices[i] for i in range(n) if self.ma60[i] is not None]
        valid_ma60_y = [self.ma60[i] for i in range(n) if self.ma60[i] is not None]
        self.p_kline.plot(valid_ma60_x, valid_ma60_y, pen=pg.mkPen('#e040fb', width=1.5), name="MA60")

        # 绘制 BOLL 布林线上轨与下轨
        if self.show_boll:
            valid_up_x = [x_indices[i] for i in range(n) if self.boll_upper[i] is not None]
            valid_up_y = [self.boll_upper[i] for i in range(n) if self.boll_upper[i] is not None]
            self.p_kline.plot(valid_up_x, valid_up_y, pen=pg.mkPen('#FF2A6D', width=1.4, style=Qt.PenStyle.DashLine), name="BOLL_UPPER")

            valid_dn_x = [x_indices[i] for i in range(n) if self.boll_lower[i] is not None]
            valid_dn_y = [self.boll_lower[i] for i in range(n) if self.boll_lower[i] is not None]
            self.p_kline.plot(valid_dn_x, valid_dn_y, pen=pg.mkPen('#00E5FF', width=1.4, style=Qt.PenStyle.DashLine), name="BOLL_LOWER")

        # 3. 绘制成交量柱状图
        vol_bars_up_x, vol_bars_up_y = [], []
        vol_bars_down_x, vol_bars_down_y = [], []

        for i in range(n):
            if closes[i] >= opens[i]:
                vol_bars_up_x.append(i)
                vol_bars_up_y.append(vols[i])
            else:
                vol_bars_down_x.append(i)
                vol_bars_down_y.append(vols[i])

        bg_up = pg.BarGraphItem(x=vol_bars_up_x, height=vol_bars_up_y, width=0.65, brush='#F6465D', pen='#F6465D')
        bg_down = pg.BarGraphItem(x=vol_bars_down_x, height=vol_bars_down_y, width=0.65, brush='#089981', pen='#089981')
        self.p_vol.addItem(bg_up)
        self.p_vol.addItem(bg_down)

        # 4. 绘制黄金分割 (Fibonacci Ratios) 动态支撑阻力坐标系
        if getattr(self, 'show_fib', True):
            self._draw_fibonacci_levels(lows, highs, n)

        self._update_info_banner(n - 1)
        self._auto_fit_y_range()

    def _draw_fibonacci_levels(self, lows, highs, n):
        """
        在 K 线主画板背景上高精度绘制 0%, 23.6%, 38.2%, 50.0%, 61.8%, 80.9%, 100% 
        黄金分割 (Fibonacci Ratios) 比例坐标系水平线与右侧动态价格标签
        """
        if not lows or not highs or n <= 0:
            return

        min_p = min(lows)
        max_p = max(highs)
        diff = max_p - min_p
        if diff <= 0:
            return

        # 7 大黄金分割核心比率位
        fib_ratios = [
            (1.000, "100.0% (顶峰)", "#F6465D", Qt.PenStyle.DashLine),
            (0.809, "80.9% (强阻)", "#FF7700", Qt.PenStyle.DotLine),
            (0.618, "61.8% (黄金位)", "#FFD700", Qt.PenStyle.DashLine),
            (0.500, "50.0% (中枢)", "#00E5FF", Qt.PenStyle.SolidLine),
            (0.382, "38.2% (黄金位)", "#FFD700", Qt.PenStyle.DashLine),
            (0.236, "23.6% (强撑)", "#00FF88", Qt.PenStyle.DotLine),
            (0.000, "0.0% (谷底)", "#089981", Qt.PenStyle.DashLine)
        ]

        for ratio, ratio_label, color_hex, line_style in fib_ratios:
            price_val = min_p + diff * ratio
            
            # 半透明专业交易水平网格线
            pen = pg.mkPen(color_hex, width=1.0, style=line_style)
            line = pg.InfiniteLine(
                pos=price_val,
                angle=0,
                pen=pen,
                movable=False
            )
            self.p_kline.addItem(line)

            # 右侧边端悬浮黄金分割比例 + 价格标签
            txt_item = pg.TextItem(
                text=f" Fib {ratio_label}: {price_val:.2f}",
                color=color_hex,
                anchor=(1.0, 0.5) # 紧靠视区右侧对齐
            )
            font = QFont("Consolas", 8, QFont.Weight.Bold)
            txt_item.setFont(font)
            self.p_kline.addItem(txt_item)
            txt_item.setPos(n - 0.5, price_val)

    def _toggle_fib_mode(self):
        """切换 FIB 黄金分割比例坐标系的显隐显示"""
        self.show_fib = not getattr(self, 'show_fib', True)
        if self.show_fib:
            self.btn_fib_toggle.setText("FIB:开")
            self.btn_fib_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #2a2233;
                    color: #FFD700;
                    border: 1px solid #FFD700;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 9pt;
                    font-weight: bold;
                    min-width: 50px;
                }
                QPushButton:hover {
                    background-color: #3d2f4d;
                    color: #ffffff;
                }
            """)
        else:
            self.btn_fib_toggle.setText("FIB:关")
            self.btn_fib_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #1e222d;
                    color: #787b86;
                    border: 1px solid #363c4e;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 9pt;
                    font-weight: bold;
                    min-width: 50px;
                }
                QPushButton:hover {
                    background-color: #2a2e39;
                    color: #d1d4dc;
                }
            """)
        self._draw_chart()
        self._save_settings()

    def _auto_fit_y_range(self):
        """
        根据当前 X 轴可见视区自动算齐最低价与最高价，
        做 5% 黄金比例上下扩展 Padding，实现 100% 自动垂直居中自适应！
        """
        n = len(self.klines)
        if n == 0 or not hasattr(self, 'p_kline'):
            return

        try:
            view_range = self.p_kline.viewRange()
            x_min, x_max = view_range[0]

            # 视区索引边界精准提取
            start_idx = max(0, min(n - 1, int(floor(x_min))))
            end_idx = max(0, min(n - 1, int(ceil(x_max))))

            if start_idx > end_idx:
                start_idx, end_idx = 0, n - 1

            visible_klines = self.klines[start_idx: end_idx + 1]
            if not visible_klines:
                visible_klines = self.klines

            lows = [float(item['low']) for item in visible_klines if ('low' in item and float(item['low']) > 0)]
            highs = [float(item['high']) for item in visible_klines if ('high' in item and float(item['high']) > 0)]

            if not lows or not highs:
                lows = [float(item['close']) for item in visible_klines if 'close' in item]
                highs = [float(item['close']) for item in visible_klines if 'close' in item]

            if not lows or not highs:
                return

            min_y = min(lows)
            max_y = max(highs)

            # 如果显示了 BOLL 或 均线，把 visible 范围内的 BOLL 计算在内
            if getattr(self, 'show_boll', False) and hasattr(self, 'boll_upper'):
                boll_up_sub = [self.boll_upper[i] for i in range(start_idx, min(n, end_idx + 1)) if (i < len(self.boll_upper) and self.boll_upper[i] is not None)]
                boll_dn_sub = [self.boll_lower[i] for i in range(start_idx, min(n, end_idx + 1)) if (i < len(self.boll_lower) and self.boll_lower[i] is not None)]
                if boll_up_sub:
                    max_y = max(max_y, max(boll_up_sub))
                if boll_dn_sub:
                    min_y = min(min_y, min(boll_dn_sub))

            h = max(0.5, max_y - min_y)
            # 5% 上下黄金比例 padding 留白，防止顶格或塌陷为细线
            padded_min_y = min_y - h * 0.05
            padded_max_y = max_y + h * 0.05

            self.p_kline.vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            self.p_kline.setYRange(padded_min_y, padded_max_y, padding=0)
        except Exception as ex:
            print(f"[GlobalMarketKLineDialog] 自动 Y 轴居中适配异常: {ex}")

    def _apply_zoom_mode(self):
        """根据 self.zoom_mode 自动应用视区并更新按键高亮"""
        mode = getattr(self, 'zoom_mode', 'recent_60')
        if mode == 'full_120':
            self._focus_full_120(save=False)
        else:
            self._focus_recent_60(save=False)

    def _focus_recent_60(self, save: bool = True):
        """缩放聚焦至最右侧最新 60 日"""
        self.zoom_mode = 'recent_60'
        n = len(self.klines)
        if n > 0:
            start_x = max(0, n - 60)
            self.p_kline.setXRange(start_x, n, padding=0.02)
        self._auto_fit_y_range()
        self._update_zoom_btn_style()
        if save:
            self._save_settings()

    def _focus_full_120(self, save: bool = True):
        """全览近 120 日完整 K 线"""
        self.zoom_mode = 'full_120'
        n = len(self.klines)
        if n > 0:
            self.p_kline.setXRange(0, n, padding=0.02)
        self._auto_fit_y_range()
        self._update_zoom_btn_style()
        if save:
            self._save_settings()

    def _update_zoom_btn_style(self):
        """更新 60日 / 120日全览 按键的高亮对比状态"""
        active_style = """
            QPushButton {
                background-color: #2962ff; color: #ffffff; font-weight: bold;
                border: 1px solid #2962ff; border-radius: 4px; padding: 4px 10px; font-size: 8.5pt;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #2a2e39; color: #d1d4dc;
                border: 1px solid #363c4e; border-radius: 4px; padding: 4px 10px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #363c4e; color: #fff; }
        """
        if getattr(self, 'zoom_mode', 'recent_60') == 'full_120':
            self.btn_focus_60.setStyleSheet(inactive_style)
            self.btn_focus_120.setStyleSheet(active_style)
        else:
            self.btn_focus_60.setStyleSheet(active_style)
            self.btn_focus_120.setStyleSheet(inactive_style)

    def _update_info_banner(self, idx: int):
        """更新顶部动态数据信息条"""
        if not self.klines or not (0 <= idx < len(self.klines)):
            return

        item = self.klines[idx]
        dt = item['date']
        o = float(item['open'])
        h = float(item['high'])
        l = float(item['low'])
        c = float(item['close'])
        pct = float(item['pct'])
        v = float(item.get('volume', 0))

        c_color = "#F6465D" if pct >= 0 else "#089981"
        v_str = f"{v/1e8:.2f}亿" if v >= 1e8 else (f"{v/1e4:.1f}万" if v >= 1e4 else f"{int(v)}")

        ma5_str = f"{self.ma5[idx]:.2f}" if hasattr(self, 'ma5') and self.ma5[idx] else "--"
        ma20_str = f"{self.ma20[idx]:.2f}" if hasattr(self, 'ma20') and self.ma20[idx] else "--"
        ma60_str = f"{self.ma60[idx]:.2f}" if hasattr(self, 'ma60') and self.ma60[idx] else "--"

        boll_up_str = f"{self.boll_upper[idx]:.2f}" if hasattr(self, 'boll_upper') and self.boll_upper[idx] else "--"
        boll_dn_str = f"{self.boll_lower[idx]:.2f}" if hasattr(self, 'boll_lower') and self.boll_lower[idx] else "--"

        mode_name = "📊 OHLC美国线" if self.chart_mode == 'ohlc' else "🕯️ K线蜡烛图"
        boll_info = f" | <font color='#FF2A6D'>BOLL上轨 {boll_up_str}</font> · <font color='#00E5FF'>下轨 {boll_dn_str}</font>" if self.show_boll else ""

        self.lbl_info.setText(
            f"模式: <b>{mode_name}</b> | 日期: <b>{dt}</b> | 开: {o:.2f} | 高: {h:.2f} | 低: {l:.2f} | "
            f"收: <font color='{c_color}'><b>{c:.2f}</b></font> ({pct:+.2f}%) | 量: {v_str} | "
            f"均线: <font color='#f0b90b'>MA5 {ma5_str}</font> · <font color='#00F0FF'>MA20 {ma20_str}</font> · <font color='#e040fb'>MA60 {ma60_str}</font>"
            f"{boll_info}"
        )

    def _on_mouse_moved(self, evt):
        """鼠标悬浮十字光标穿透交互"""
        pos = evt[0]
        if self.p_kline.sceneBoundingRect().contains(pos):
            mouse_point = self.p_kline.vb.mapSceneToView(pos)
            x_idx = int(round(mouse_point.x()))
            if 0 <= x_idx < len(self.klines):
                self.v_line.setPos(mouse_point.x())
                self.h_line.setPos(mouse_point.y())
                self._update_info_banner(x_idx)

    def _restore_settings(self):
        """恢复物理窗口几何尺寸、模式、BOLL状态、视区、h_splitter 水平比例及资讯面板显隐"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                geom = data.get("ats_global_kline_dialog_geom")
                if geom:
                    from PyQt6.QtCore import QByteArray
                    self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
                mode = data.get("ats_global_kline_dialog_mode")
                if mode in ['candlestick', 'ohlc']:
                    self.chart_mode = mode
                    if mode == 'ohlc':
                        self.btn_mode_toggle.setText("🕯️ 切换 蜡烛图(K线)")
                    else:
                        self.btn_mode_toggle.setText("📊 切换 OHLC(美国线)")
                boll = data.get("ats_global_kline_dialog_boll")
                if boll is not None:
                    self.show_boll = bool(boll)
                    if not self.show_boll:
                        self.btn_boll_toggle.setText("📈 BOLL(20,2): 关")
                        self.btn_boll_toggle.setStyleSheet("""
                            QPushButton {
                                background-color: #1e222d;
                                color: #787b86;
                                border: 1px solid #363c4e;
                                border-radius: 4px;
                                padding: 4px 10px;
                                font-size: 9pt;
                                font-weight: bold;
                                min-width: 105px;
                            }
                            QPushButton:hover {
                                background-color: #2a2e39;
                                color: #d1d4dc;
                            }
                        """)
                src = data.get("ats_global_kline_default_source")
                if src in ['yahoo', 'sina']:
                    self.data_source = src
                    self._update_data_source_btn_style()
                zoom = data.get("ats_global_kline_dialog_zoom")
                if zoom in ['recent_60', 'full_120']:
                    self.zoom_mode = zoom
                    self._update_zoom_btn_style()
                # 恢复资讯侧边栏显隐状态
                news_vis = data.get("ats_global_kline_news_visible")
                if news_vis is False and hasattr(self, 'news_panel'):
                    self.news_panel.hide()
                    self.btn_news_toggle.setText(f"📰 资讯({len(self.news_items)}条): 展开")
                    self.btn_news_toggle.setStyleSheet("""
                        QPushButton {
                            background-color: #2a2e39;
                            color: #d1d4dc;
                            border: 1px solid #363c4e;
                            border-radius: 4px;
                            padding: 4px 10px;
                            font-size: 9pt;
                            min-width: 110px;
                        }
                        QPushButton:hover {
                            background-color: #363c4e;
                            color: #ffffff;
                        }
                    """)
                # 恢复 Splitter 分割比例 (延迟到 Layout 展示完成后)
                splitter_sizes = data.get("ats_global_kline_splitter_sizes")
                if splitter_sizes and isinstance(splitter_sizes, list) and len(splitter_sizes) >= 2:
                    QTimer.singleShot(60, lambda s=list(splitter_sizes): hasattr(self, 'v_splitter') and self.v_splitter.setSizes(s))
                h_splitter_sizes = data.get("ats_global_kline_h_splitter_sizes")
                if h_splitter_sizes and isinstance(h_splitter_sizes, list) and len(h_splitter_sizes) >= 2:
                    QTimer.singleShot(70, lambda s=list(h_splitter_sizes): hasattr(self, 'h_splitter') and self.h_splitter.setSizes(s))
        except Exception:
            pass

    def _save_settings(self):
        """物理落盘持久化配置 (窗口几何、模式、BOLL、缩放状态、数据源、Splitter 分割比例与资讯面板显隐)"""
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_global_kline_dialog_geom", self.saveGeometry().toHex().data().decode('utf-8'))
            save_config_node("ats_global_kline_dialog_mode", self.chart_mode)
            save_config_node("ats_global_kline_dialog_boll", self.show_boll)
            save_config_node("ats_global_kline_dialog_zoom", self.zoom_mode)
            save_config_node("ats_global_kline_default_source", self.data_source)
            if hasattr(self, 'news_panel'):
                save_config_node("ats_global_kline_news_visible", self.news_panel.isVisible())
            # 保存 Splitter 分割比例
            if hasattr(self, 'v_splitter'):
                sizes = self.v_splitter.sizes()
                if sizes and any(s > 0 for s in sizes):
                    save_config_node("ats_global_kline_splitter_sizes", list(sizes))
            if hasattr(self, 'h_splitter'):
                h_sizes = self.h_splitter.sizes()
                if h_sizes and any(s > 0 for s in h_sizes):
                    save_config_node("ats_global_kline_h_splitter_sizes", list(h_sizes))
        except Exception as ex:
            print(f"[GlobalMarketKLineDialog] Save settings error: {ex}")


    def _on_splitter_moved(self, pos: int, index: int):
        """Splitter 拖动时延迟 300ms 防抖后持久化分割比例。
        splitterMoved 在拖动过程中高频触发，防抖避免频繁写盘。
        """
        if not hasattr(self, '_splitter_save_timer'):
            self._splitter_save_timer = QTimer(self)
            self._splitter_save_timer.setSingleShot(True)
            self._splitter_save_timer.timeout.connect(self._save_settings)
        self._splitter_save_timer.start(300)

    def showEvent(self, event):
        """窗口打开/显示事件：强制执行 100% 自动 Reset 与 Y 轴垂直居中适配"""
        super().showEvent(event)
        QTimer.singleShot(30, self._apply_zoom_mode)
        QTimer.singleShot(80, self._auto_fit_y_range)

    def closeEvent(self, event):
        """关闭事件，自动持久化配置与尺寸"""
        self._save_settings()
        super().closeEvent(event)

    def _update_proxy_btn_style(self):
        """更新 🌐 代理: 开/关 按键高亮与显示文本"""
        try:
            from JSONData.global_market_data import get_proxy_config
            cfg = get_proxy_config()
            enabled = cfg.get("enabled", False)
            p_url = cfg.get("proxy_url", "")
            port = p_url.split(":")[-1] if ":" in p_url else ""

            if hasattr(self, 'btn_proxy_toggle'):
                if enabled:
                    btn_txt = f"代理:{port}" if port else "代理:开"
                    self.btn_proxy_toggle.setText(btn_txt)
                    self.btn_proxy_toggle.setStyleSheet("""
                        QPushButton {
                            background-color: #00E5FF;
                            color: #000000;
                            font-weight: bold;
                            border: 1px solid #00E5FF;
                            border-radius: 4px;
                            padding: 4px 8px;
                            font-size: 9pt;
                            min-width: 60px;
                        }
                        QPushButton:hover {
                            background-color: #33ebff;
                        }
                    """)
                else:
                    self.btn_proxy_toggle.setText("代理:关")
                    self.btn_proxy_toggle.setStyleSheet("""
                        QPushButton {
                            background-color: #1e222d;
                            color: #787b86;
                            border: 1px solid #363c4e;
                            border-radius: 4px;
                            padding: 4px 8px;
                            font-size: 9pt;
                            font-weight: bold;
                            min-width: 55px;
                        }
                        QPushButton:hover {
                            background-color: #2a2e39;
                            color: #d1d4dc;
                        }
                    """)
        except Exception as ex:
            print(f"[GlobalMarketKLineDialog] 更新代理按键状态异常: {ex}")

    def _open_proxy_dialog(self):
        """调起网络代理设置弹窗"""
        try:
            from ats.ui.proxy_dialog import ProxySettingsDialog
            dlg = ProxySettingsDialog(parent=self)
            dlg.exec()
        except Exception as ex:
            print(f"[GlobalMarketKLineDialog] 调起代理弹窗异常: {ex}")

    def _on_global_proxy_changed(self, cfg: dict = None):
        """响应全局代理变更广播，瞬间同步子窗口按钮状态并重载数据"""
        self._update_proxy_btn_style()
        self._load_fast_cached_or_async()

    def _update_log_btn_style(self):
        """动态更新日志开关按键样式与文案"""
        try:
            from JSONData.global_market_data import get_global_market_log_enabled
            enabled = get_global_market_log_enabled()
            if enabled:
                self.btn_log_config.setText("日志:开")
                self.btn_log_config.setStyleSheet("""
                    QPushButton {
                        background-color: #1a2233;
                        color: #00F0FF;
                        border: 1px solid #00F0FF;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 9pt;
                        font-weight: bold;
                        min-width: 55px;
                    }
                    QPushButton:hover {
                        background-color: #2962ff;
                        color: #ffffff;
                    }
                """)
            else:
                self.btn_log_config.setText("日志:关")
                self.btn_log_config.setStyleSheet("""
                    QPushButton {
                        background-color: #191d26;
                        color: #787b86;
                        border: 1px solid #363c4e;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 9pt;
                        min-width: 55px;
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


