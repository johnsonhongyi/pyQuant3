# -*- coding: utf-8 -*-
"""
MarketTempHistoryManager & MarketTempChartDialog
提供市场温度、上涨/下跌家数、放量家数的历史数据记录与高性能折线图可视化。
支持多窗口复用与跨会话自动恢复。
"""
import os
import json
import time
from datetime import datetime
import threading
from logger_utils import LoggerFactory

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QColor, QFont
import pyqtgraph as pg

from tk_gui_modules.window_mixin import WindowMixin

logger = LoggerFactory.getLogger("market_temp_chart")

class MarketTempHistoryManager:
    """市场温度和广度数据历史管理器 (单例)"""
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(MarketTempHistoryManager, cls).__new__(cls, *args, **kwargs)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.records = []
        self.last_record_time = 0
        self.last_save_time = time.time()  # 初始化上次写盘时间
        # 统一使用 get_app_root 或相对路径的 logs 目录
        from sys_utils import get_app_root
        try:
            self.filepath = os.path.join(get_app_root(), "logs", "market_temp_history.json")
        except Exception:
            self.filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "market_temp_history.json")
            
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self.load_history()

    def load_history(self):
        """加载今天的历史记录，跨天则自动清空"""
        if not os.path.exists(self.filepath):
            self.records = []
            return
            
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                date_str = data.get("date", "")
                today_str = datetime.now().strftime("%Y-%m-%d")
                if date_str == today_str:
                    self.records = data.get("records", [])
                    logger.info(f"Loaded {len(self.records)} market temp records for today.")
                else:
                    self.records = []
                    logger.info("Cleared outdated market temp records.")
            else:
                self.records = []
        except Exception as e:
            logger.error(f"Failed to load market temp history: {e}")
            self.records = []

    def save_history(self):
        """保存历史记录"""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            data = {
                "date": today_str,
                "records": self.records
            }
            tmp_file = self.filepath + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.filepath)
        except Exception as e:
            logger.error(f"Failed to save market temp history: {e}")

    def add_record(self, temp, up, down, vol_up, force=False):
        """追加一条新纪录。为了防抖，两次记录之间至少间隔 5 秒"""
        now = time.time()
        if not force and now - self.last_record_time < 5.0:
            return
        
        self.last_record_time = now
        time_str = datetime.now().strftime("%H:%M:%S")
        
        record = {
            "timestamp": now,
            "time_str": time_str,
            "temp": round(float(temp), 1) if temp is not None else 0.0,
            "up": int(up),
            "down": int(down),
            "vol_up": int(vol_up)
        }
        
        self.records.append(record)
        
        # 限制单日记录数量，避免内存泄露 (4小时交易时间，若5秒一次则共 2880 条)
        if len(self.records) > 5000:
            self.records.pop(0)
            
        # 仅在 force=True 或距离上次保存超过 60 分钟时才写盘
        if force or (now - self.last_save_time >= 3600):
            self.save_history()
            self.last_save_time = now

    def get_data(self):
        return self.records


class TimeStrAxisItem(pg.AxisItem):
    """自定义时间轴，将数组索引映射为对应的时间字符串"""
    def __init__(self, time_strs, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_strs = time_strs

    def tickStrings(self, values, scale, spacing):
        ticks = []
        for v in values:
            idx = int(round(v))
            if 0 <= idx < len(self.time_strs):
                ticks.append(self.time_strs[idx])
            else:
                ticks.append("")
        return ticks


class MarketTempChartDialog(QDialog, WindowMixin):
    """市场温度与广度指标趋势弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌡️ 市场温度与多维指标今日走势")
        self.setMinimumSize(850, 600)
        
        # 加载窗口位置与大小
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        self.load_window_position_qt(self, "market_temp_chart_dialog", default_width=900, default_height=650)
        
        self._init_ui()
        self.update_chart()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        
        # 1. 顶部状态简报
        self.setStyleSheet("background-color: #0d121f; color: #abb2bf;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.info_label = QLabel("正在加载今日温度历史走势...")
        self.info_label.setFont(QFont("Microsoft YaHei", 10))
        self.info_label.setStyleSheet("""
            QLabel {
                background-color: #161b2d;
                color: #e0e6ed;
                border: 1px solid #232d4b;
                border-radius: 6px;
                padding: 8px 12px;
            }
        """)
        lay.addWidget(self.info_label)
        
        # 2. 创建 pyqtgraph 绘图视口
        self.graph_layout = pg.GraphicsLayoutWidget()
        self.graph_layout.setBackground('#0d121f')
        lay.addWidget(self.graph_layout)
        
        # 2b. 初始化图表子图与数据曲线（仅创建一次，防止 clear 触发 disconnect 报错）
        self.time_strs = []
        
        # Subplot 1: 🌡️ 市场温度 (0-100)
        self.axis1 = TimeStrAxisItem(self.time_strs, orientation='bottom')
        self.p1 = self.graph_layout.addPlot(
            title="🌡️ 市场温度历史走势 (%)",
            axisItems={'bottom': self.axis1}
        )
        self.p1.showGrid(x=True, y=True, alpha=0.3)
        self.p1.setYRange(0, 100)
        self.p1.setLabel('left', '温度', units='%')
        
        # 绘制温度折线
        self.temp_curve = self.p1.plot(pen=pg.mkPen('#5bc0de', width=2.5), name="市场温度")
        
        # 添加 80% (火热) 和 20% (冰点) 辅助水平参考线
        self.h_line_hot = pg.InfiniteLine(pos=80, angle=0, pen=pg.mkPen('#ff3333', width=1, style=Qt.PenStyle.DashLine))
        self.h_line_cold = pg.InfiniteLine(pos=20, angle=0, pen=pg.mkPen('#33ccff', width=1, style=Qt.PenStyle.DashLine))
        self.p1.addItem(self.h_line_hot)
        self.p1.addItem(self.h_line_cold)
        
        # Subplot 2: 🚀 盘中放量个股数量
        self.graph_layout.nextRow()
        self.axis2 = TimeStrAxisItem(self.time_strs, orientation='bottom')
        self.p2 = self.graph_layout.addPlot(
            title="🚀 盘中放量暴增个股数量",
            axisItems={'bottom': self.axis2}
        )
        self.p2.showGrid(x=True, y=True, alpha=0.3)
        self.p2.setLabel('left', '家数')
        self.vol_curve = self.p2.plot(pen=pg.mkPen('#ffa502', width=2), name="放量个股")
        self.p2.setXLink(self.p1) # X轴与温度图联动
        
        # Subplot 3: 📊 上涨 vs 下跌家数对比
        self.graph_layout.nextRow()
        self.axis3 = TimeStrAxisItem(self.time_strs, orientation='bottom')
        self.p3 = self.graph_layout.addPlot(
            title="📊 上涨(红) vs 下跌(绿)家数对比",
            axisItems={'bottom': self.axis3}
        )
        self.p3.showGrid(x=True, y=True, alpha=0.3)
        self.p3.setLabel('left', '家数')
        
        # 绘制上涨家数 (红) 与下跌家数 (绿)
        self.up_curve = self.p3.plot(pen=pg.mkPen('#ff4444', width=2), name="上涨")
        self.down_curve = self.p3.plot(pen=pg.mkPen('#2ed573', width=2), name="下跌")
        self.p3.setXLink(self.p1) # X轴与温度图联动
        
        # 3. 底部操作栏
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a1c2c;
                color: #ddd;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a2d42;
                color: #fff;
                border-color: #444;
            }
        """)
        refresh_btn.clicked.connect(self.update_chart)
        btn_lay.addWidget(refresh_btn)
        lay.addLayout(btn_lay)
    def update_chart(self):
        # 1. 获取最新数据
        records = MarketTempHistoryManager().get_data()
        
        if not records:
            self.info_label.setText("<span style='color: #ff5252; font-weight: bold;'>⚠️ 今日暂无记录的温度指标数据</span> <span style='color: #a0aec0;'>(需盘中开启行情心跳触发)</span>")
            return
            
        # 2. 解析指标数据
        times = list(range(len(records)))
        time_strs = [r['time_str'] for r in records]
        temps = [r['temp'] for r in records]
        ups = [r['up'] for r in records]
        downs = [r['down'] for r in records]
        vol_ups = [r['vol_up'] for r in records]
        
        # 3. 更新顶部文字说明
        last_rec = records[-1]
        self.info_label.setText(
            f"🕒 <span style='color: #a0aec0;'>数据截止:</span> <span style='color: #38bdf8; font-weight: bold;'>{last_rec['time_str']}</span> <span style='color: #4a5568;'>|</span> "
            f"🌡️ <span style='color: #a0aec0;'>最新温度:</span> <span style='color: #ff9f43; font-weight: bold;'>{last_rec['temp']:.1f}°C</span> <span style='color: #4a5568;'>|</span> "
            f"📈 <span style='color: #a0aec0;'>上涨:</span> <span style='color: #ff5252; font-weight: bold;'>{last_rec['up']}</span> <span style='color: #4a5568;'>|</span> "
            f"📉 <span style='color: #a0aec0;'>下跌:</span> <span style='color: #2ed573; font-weight: bold;'>{last_rec['down']}</span> <span style='color: #4a5568;'>|</span> "
            f"🚀 <span style='color: #a0aec0;'>放量:</span> <span style='color: #ffa502; font-weight: bold;'>{last_rec['vol_up']}</span>"
        )
        
        # 4. 更新时间轴的底层列表数据，供 TimeStrAxisItem 映射使用
        self.time_strs.clear()
        self.time_strs.extend(time_strs)
        
        # 5. 更新折线图数据与笔刷颜色 (温度大于 60 用红色，否则用淡蓝色)
        temp_color = '#ff4444' if temps[-1] >= 60 else '#5bc0de'
        self.temp_curve.setPen(pg.mkPen(temp_color, width=2.5))
        self.temp_curve.setData(times, temps)
        
        self.vol_curve.setData(times, vol_ups)
        self.up_curve.setData(times, ups)
        self.down_curve.setData(times, downs)
        
        # 6. 通知子图表重新计算坐标和刻度
        self.p1.getAxis('bottom').picture = None
        self.p1.getAxis('bottom').update()
        self.p2.getAxis('bottom').picture = None
        self.p2.getAxis('bottom').update()
        self.p3.getAxis('bottom').picture = None
        self.p3.getAxis('bottom').update()

    def closeEvent(self, event):
        """关闭窗口时自动保存位置"""
        try:
            self.save_window_position_qt(self, "market_temp_chart_dialog")
        except: pass
        super().closeEvent(event)
