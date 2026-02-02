# -*- coding: utf-8 -*-
"""
Signal Testing Suite - 分时信号测试工具
用于手动触发并验证各类主升、诱多、破位信号。
"""
import sys
import os
import time
import pandas as pd
from datetime import datetime, time as dt_time, timedelta
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QPushButton, QLabel, 
                             QTextEdit, QCheckBox, QGroupBox, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QTimer
import socket
import json

# 导入核心组件
from intraday_pattern_detector import IntradayPatternDetector, PatternEvent
from signal_bus import get_signal_bus, publish_pattern, SignalBus

class SignalTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pyQuant3 - 分时信号功能测试工具")
        self.resize(800, 600)
        
        self.detector = IntradayPatternDetector(cooldown=2) # 缩短冷却时间便于测试
        self.bus = get_signal_bus()
        
        self._init_ui()
        self.log("测试工具就绪。支持 9:25 时间过滤模拟。")

    def _send_signal_to_visualizer_ipc(self, data: dict):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2) 
            # Visualizer 监听端口 26668
            s.connect(('127.0.0.1', 26668))
            
            json_str = json.dumps(data)
            # CommandListenerThread 协议: b"CODE" (4 字节) + 内容
            # Visualizer 端会将接收到的内容拼接为: prefix (CODE) + remaining
            # 因此这里只需发送 b"CODE" + b"|SIGNAL|{json}"，对方收到就是 "CODE|SIGNAL|{json}"
            msg = f"|SIGNAL|{json_str}"
            s.send(b"CODE")
            s.send(msg.encode('utf-8'))
            s.close()
        except Exception as e:
            # 推送失败可能是 Visualizer 没开，忽略即可
            self.log(f"IPC Error: Connection failed - {e}")

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- 左侧：形态列表 ---
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("<b>形态列表 (可多选)</b>"))
        
        self.pattern_list = QListWidget()
        for p in IntradayPatternDetector.PATTERNS:
            self.pattern_list.addItem(p)
        left_panel.addWidget(self.pattern_list)
        
        self.btn_run_logic = QPushButton("1. 执行逻辑模拟 (触发检测)")
        self.btn_run_logic.clicked.connect(self.run_logic_test)
        self.btn_run_logic.setStyleSheet("background-color: #d1ecf1; height: 40px;")
        left_panel.addWidget(self.btn_run_logic)

        self.btn_direct_inject = QPushButton("2. 直接注入总线 (测试日志/播报)")
        self.btn_direct_inject.clicked.connect(self.direct_inject_test)
        self.btn_direct_inject.setStyleSheet("background-color: #f8d7da; height: 40px;")
        left_panel.addWidget(self.btn_direct_inject)

        main_layout.addLayout(left_panel, 1)

        # --- 右侧：配置与日志 ---
        right_panel = QVBoxLayout()
        
        # 参数配置
        config_group = QGroupBox("参数配置")
        config_layout = QVBoxLayout()
        
        self.cb_mock_925 = QCheckBox("模拟 9:25 之后 (跳过时间限制)")
        self.cb_mock_925.setChecked(True)
        config_layout.addWidget(self.cb_mock_925)

        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel("昨日 TrendS:"))
        self.spin_trends = QDoubleSpinBox()
        self.spin_trends.setRange(0, 100)
        self.spin_trends.setValue(75)
        h_layout1.addWidget(self.spin_trends)
        config_layout.addLayout(h_layout1)

        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel("昨日 Win 计数:"))
        self.spin_win = QDoubleSpinBox()
        self.spin_win.setRange(0, 10)
        self.spin_win.setDecimals(0)
        self.spin_win.setValue(1)
        h_layout2.addWidget(self.spin_win)
        config_layout.addLayout(h_layout2)

        config_group.setLayout(config_layout)
        right_panel.addWidget(config_group)

        # 日志输出
        right_panel.addWidget(QLabel("<b>测试日志输出</b>"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        right_panel.addWidget(self.log_output)
        
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.log_output.clear)
        right_panel.addWidget(btn_clear)

        main_layout.addLayout(right_panel, 2)

    def log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{ts}] {text}")

    def get_mock_day_row(self, pattern):
        """构造能够触发特定模式的 mock data"""
        base = {
            'open': 10.0, 'high': 10.0, 'low': 10.0, 'close': 10.0, 
            'trade': 10.0, 'amount': 1000000.0, 'volume': 100000.0,
            'TrendS': self.spin_trends.value(),
            'win': int(self.spin_win.value())
        }
        prev_close = 10.0
        
        if pattern == 'master_momentum':
            # 强势结构：高开 + Open=Low + 大于均线
            base['open'] = 10.2
            base['low'] = 10.2
            base['close'] = 10.5
            base['trade'] = 10.5
            base['amount'] = 1050000.0
            base['volume'] = 100000.0 # VWAP = 10.5, curr=10.5
        elif pattern == 'bull_trap_exit':
            # 诱多：曾经涨幅 > 3% 且现在破位
            base['open'] = 10.0
            base['high'] = 10.4 # +4%
            base['close'] = 9.9
            base['trade'] = 9.9
            base['amount'] = 1010000.0
            base['volume'] = 100000.0 # VWAP = 10.1, curr=9.9
        elif pattern == 'open_low_retest':
            base['open'] = 10.0
            base['low'] = 10.0
            base['close'] = 10.2
            base['trade'] = 10.2
        elif pattern == 'high_sideways_break':
            base['open'] = 10.0
            base['high'] = 10.6
            base['close'] = 10.55
            base['trade'] = 10.55
            base['amount'] = 1020000.0
            base['volume'] = 100000.0 # VWAP = 10.2
        elif pattern == 'open_is_low_volume':
            # 开盘最低带量: Open=Low, 且 volume > 1.0 或 ratio > 2.5
            base['open'] = 10.0
            base['low'] = 10.0
            base['close'] = 10.2
            base['trade'] = 10.2
            base['volume'] = 1.5 # 量比 > 1.0
            base['amount'] = 1020000.0 # VWAP = 10.2, curr=10.2
        elif pattern == 'nlow_is_low_volume':
            # 日低反转带量: 当前从日低反弹 1%+, 且带量
            base['open'] = 10.1
            base['low'] = 9.9
            base['close'] = 10.05 # rebound from 9.9
            base['trade'] = 10.05
            base['volume'] = 1.2
            base['amount'] = 1000000.0 # VWAP ≈ 10.0
        elif pattern == 'low_open_breakout':
            # 低开突破: 已触发过 base，现在突破昨日高点
            self.detector._cache[f"MOCK_low_open_state"] = {'base_triggered': True, 'open_price': 9.5}
            base['open'] = 9.5
            base['close'] = 10.5
            base['trade'] = 10.5
            base['lasth1d'] = 10.0 # 昨高
            base['max5'] = 10.4 # 5日高
        elif pattern == 'strong_auction_open':
            # 强力竞价: 高开 3% + Open=Low + TrendS > 60
            base['open'] = 10.3
            base['low'] = 10.3
            base['close'] = 10.4
            base['trade'] = 10.4
            base['TrendS'] = 75
        elif pattern == 'momentum_failure':
             # 先构造 master_momentum 状态
             self.detector._cache["MOCK_master_momentum_state"] = {'ever_broken': False, 'failure_signaled': False}
             base['close'] = 9.5
             base['amount'] = 1000000.0
             base['volume'] = 100000.0 # VWAP = 10.0
             
        return pd.Series(base), prev_close

    def run_logic_test(self):
        try:
            items = self.pattern_list.selectedItems()
            if not items:
                self.log("请先在列表中选择要测试的形态。")
                return
                
            for item in items:
                pattern = item.text()
                self.log(f"--- 启动逻辑模拟: {pattern} ---")
                
                day_row, prev_close = self.get_mock_day_row(pattern)
                raw_code = "000001" # 使用真实感的代码
                name = "平安测试"   # 使用真实感的名称
                detected = [] # Initialize detected list
                
                # 绕过检测器内部时间限制：
                # 如果勾选了 mock_925，则传入 09:30 作为当前时间
                # 否则传入 09:00 (这会被逻辑拦截，仅用于测试拦截功能)
                if self.cb_mock_925.isChecked():
                    mock_time = dt_time(9, 30) if pattern != 'auction_high_open' else dt_time(9, 26)
                else:
                    mock_time = dt_time(9, 0)

                # Simulate time progression for more robust testing
                for i in range(1, 21): # Simulate 20 minutes after 9:30
                    t = (datetime.combine(datetime.today(), dt_time(9, 30)) + timedelta(minutes=i)).time()
                    
                    # [DEBUG] 打印调用参数，排查崩溃点
                    # print(f"DEBUG: Calling update with {t}")
                    
                    events = self.detector.update(raw_code, name, None, day_row, prev_close, current_time=t)
                    
                    if events:
                        for ev in events:
                            # 获取事件描述 (兼容原始 PatternEvent 和新的 StandardSignal)
                            if hasattr(ev, 'signal') and ev.signal:
                                sig = ev.signal
                                # 确保 signal 对象有 type/subtype 属性
                                s_type = getattr(sig, 'type', 'unknown')
                                s_subtype = getattr(sig, 'subtype', 'unknown')
                                s_price = getattr(sig, 'price', 0.0)
                                desc = f"{s_type}:{s_subtype} @ {s_price}"
                            else:
                                # 兼容模式
                                desc = f"{getattr(ev, 'type', 'unknown')}:{getattr(ev, 'subtype', 'unknown')}"
                                
                            self.log(f"  [Detected] {t} -> {desc}")
                            detected.append(ev)
                            
                            # 模拟发布 StandardSignal (如果是测试环境，可能需要直接调用 publish_standard_signal)
                            if hasattr(ev, 'signal') and ev.signal:
                                # 假设 publish_standard_signal 已定义，或者安全调用
                                try:
                                    from signal_bus import publish_standard_signal
                                    publish_standard_signal(ev.signal)
                                except ImportError:
                                    pass
                            else:
                                from signal_bus import publish_pattern
                                publish_pattern(source="Test", code=raw_code, name=name, 
                                                pattern=getattr(ev, 'subtype', 'unknown'), 
                                                price=getattr(ev, 'price', 0.0))
                            
                            # 将模拟信号推送到 Visualizer
                            ipc_data = {
                                "code": ev.code if hasattr(ev, 'code') else raw_code,
                                "name": ev.name if hasattr(ev, 'name') else name,
                                "pattern": getattr(ev, 'subtype', 'unknown'),
                                "price": getattr(ev, 'price', 0.0),
                                "detail": getattr(ev, 'detail', ''),
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "source": "SIMULATOR"
                            }
                            # 如果 StandardSignal 存在，优先使用其数据
                            if hasattr(ev, 'signal') and ev.signal:
                                sig = ev.signal
                                ipc_data.update(sig.to_dict())

                            self._send_signal_to_visualizer_ipc(ipc_data)
                            self.log(f"📡 已通过 IPC 将信号推送到 Visualizer (Port: 26668)")

                            if getattr(ev, 'subtype', '') == 'strong_auction_open':
                                self.log("提示: 系统在检查该标的 Follow Queue 时将强制要求命中此形态。")
                            if getattr(ev, 'subtype', '') in ('bull_trap_exit', 'momentum_failure'):
                                self.log("提示: 对于 auto_followed 标的，此信号将触发“跑路”通报。")

                if not detected:
                    self.log(f"结果: 未触发 {pattern}。请检查 Mock 数据生成逻辑。")

        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print(err_msg) # 打印到控制台以防 UI 更新失败
            self.log(f"CRITICAL ERROR: {e}")
            self.log(err_msg)

    def direct_inject_test(self):
        items = self.pattern_list.selectedItems()
        if not items:
            self.log("请先选择形态。")
            return
            
        for item in items:
            pattern = item.text()
            self.log(f"--- 直接注入总线: {pattern} ---")
            
            # 使用便捷函数发布
            publish_pattern(
                source="ManualTestTool",
                code="000001",
                name="测试注入",
                pattern=pattern,
                price=10.0,
                detail=f"[手动测试] 模拟触发 {pattern}"
            )
            self.log(f"已发布 {pattern} 到 SignalBus。请观察主程序界面。")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SignalTestWindow()
    window.show()
    sys.exit(app.exec())
