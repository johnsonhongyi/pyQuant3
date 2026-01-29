# -*- coding: utf-8 -*-
"""
概念分析查看器 - 独立进程运行
解决 TK-Qt 混合使用时的 DPI 缩放冲突问题

通过 Socket IPC 与 TK 主程序通信：
- 接收端口: 26670 (接收数据更新)
- 回调端口: 26671 (发送交互事件给主程序)

使用方式:
    python concept_viewer.py --code 000001 --top_n 10
    或由主程序 subprocess 启动
"""

import os
import sys
import json
import socket
import struct
import threading
import argparse
import hashlib
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import numpy as np

# 设置 Qt 环境变量（必须在导入 PyQt 之前）
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'

from PyQt6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

# IPC 配置
IPC_LISTEN_PORT = 26670  # 接收数据
IPC_CALLBACK_PORT = 26671  # 发送回调到主程序


class ConceptViewerWindow(QtWidgets.QWidget):
    """概念分析图表窗口"""
    
    # 信号：用于跨线程安全更新 UI
    data_received = QtCore.pyqtSignal(dict)
    
    def __init__(self, code: str, top_n: int, initial_data: Optional[Dict] = None):
        super().__init__()
        self.code = code
        self.top_n = top_n
        self.unique_code = f"{code}_{top_n}"
        
        # 数据存储
        self.concepts: List[str] = []
        self.scores = np.array([])
        self.avg_percents = np.array([])
        self.follow_ratios = np.array([])
        self.current_idx = 0
        
        # UI 组件引用
        self.plot = None
        self.bars = None
        self.texts = []
        self.brushes = []
        
        # 历史数据（用于增量显示）
        self._init_data: Dict[str, Dict] = {}
        self._prev_data: Dict[str, Dict] = {}
        
        self._setup_ui()
        self._setup_signals()
        
        # 加载初始数据
        if initial_data:
            self._update_from_data(initial_data)
    
    def _setup_ui(self):
        """初始化 UI"""
        self.setWindowTitle(f"{self.code} 概念分析Top{self.top_n}")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window |
            QtCore.Qt.WindowType.WindowMinimizeButtonHint |
            QtCore.Qt.WindowType.WindowMaximizeButtonHint |
            QtCore.Qt.WindowType.WindowCloseButtonHint
        )
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.resize(600, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # 控制栏
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.chk_auto = QtWidgets.QCheckBox("自动更新")
        self.chk_auto.setChecked(True)
        self.spin_interval = QtWidgets.QSpinBox()
        self.spin_interval.setRange(5, 300)
        self.spin_interval.setValue(60)
        self.spin_interval.setSuffix(" 秒")
        
        ctrl_layout.addWidget(self.chk_auto)
        ctrl_layout.addWidget(self.spin_interval)
        ctrl_layout.addStretch()
        
        # 状态标签
        self.status_label = QtWidgets.QLabel("等待数据...")
        ctrl_layout.addWidget(self.status_label)
        
        layout.addLayout(ctrl_layout)
        
        # 绘图区域
        self.pg_widget = pg.GraphicsLayoutWidget()
        self.pg_widget.setContentsMargins(0, 0, 0, 0)
        self.pg_widget.ci.layout.setContentsMargins(0, 0, 0, 0)
        self.pg_widget.ci.layout.setSpacing(0)
        layout.addWidget(self.pg_widget)
        
        self.plot = self.pg_widget.addPlot()
        self.plot.setContentsMargins(0, 0, 0, 0)
        self.plot.invertY(True)
        self.plot.setLabel('bottom', '综合得分 (score)')
        self.plot.setLabel('left', '概念')
        self.plot.setMenuEnabled(False)
        
        # 绑定事件
        self.plot.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_move)
    
    def _setup_signals(self):
        """设置信号连接"""
        self.data_received.connect(self._update_from_data)
    
    def _update_from_data(self, data: Dict):
        """从数据字典更新图表"""
        try:
            self.concepts = data.get('concepts', [])
            self.scores = np.array(data.get('scores', []))
            self.avg_percents = np.array(data.get('avg_percents', []))
            self.follow_ratios = np.array(data.get('follow_ratios', []))
            
            if len(self.concepts) == 0:
                self.status_label.setText("无数据")
                return
            
            self._render_chart()
            self.status_label.setText(f"更新: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            self.status_label.setText(f"错误: {e}")
            print(f"[ConceptViewer] 更新数据失败: {e}")
    
    def _render_chart(self):
        """渲染图表"""
        # 清除旧的 BarGraphItem
        for item in self.plot.items[:]:
            if isinstance(item, pg.BarGraphItem):
                self.plot.removeItem(item)
        
        # 清除旧的 TextItem
        for text in self.texts:
            try:
                self.plot.removeItem(text)
            except:
                pass
        self.texts.clear()
        
        y = np.arange(len(self.concepts))
        max_score = max(self.scores.max(), 1) if len(self.scores) > 0 else 1
        
        # 颜色映射
        color_map = pg.colormap.get('CET-R1')
        self.brushes = [pg.mkBrush(color_map.map(s)) for s in self.scores]
        
        # 绘制主条形图
        self.bars = pg.BarGraphItem(
            x0=np.zeros(len(y)), 
            y=y, 
            height=0.6, 
            width=self.scores, 
            brushes=self.brushes
        )
        self.plot.addItem(self.bars)
        
        # 添加文字标签
        for i, (score, avg) in enumerate(zip(self.scores, self.avg_percents)):
            # 计算增量
            c_name = self.concepts[i]
            delta = 0
            if c_name in self._init_data:
                base_score = self._init_data[c_name].get('score', score)
                delta = score - base_score
            else:
                self._init_data[c_name] = {'score': score, 'avg': avg}
            
            # 增量箭头
            if delta > 0.01:
                arrow = "↑"
                color = "green"
            elif delta < -0.01:
                arrow = "↓"
                color = "red"
            else:
                arrow = "→"
                color = "gray"
            
            text = pg.TextItem(f"{arrow}{delta:.1f} score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
            text.setColor(QtGui.QColor(color))
            text.setPos(score + 0.03 * max_score, y[i])
            self.plot.addItem(text)
            self.texts.append(text)
            
            # 更新历史数据
            self._prev_data[c_name] = {'score': score, 'avg': avg}
        
        # 设置 Y 轴标签
        self.plot.getAxis('left').setTicks([list(zip(y, self.concepts))])
    
    def _highlight_bar(self, index: int):
        """高亮选中的条形"""
        if self.bars is None or not self.brushes:
            return
        if not (0 <= index < len(self.concepts)):
            return
        
        # 恢复所有颜色
        highlight_brushes = self.brushes.copy()
        highlight_brushes[index] = pg.mkBrush((255, 255, 0, 180))  # 黄色高亮
        self.bars.setOpts(brushes=highlight_brushes)
        self.plot.update()
    
    def _on_mouse_click(self, event):
        """鼠标点击事件"""
        try:
            if not self.plot.sceneBoundingRect().contains(event.scenePos()):
                return
            
            vb = self.plot.vb
            mouse_point = vb.mapSceneToView(event.scenePos())
            idx = int(round(mouse_point.y()))
            
            if 0 <= idx < len(self.concepts):
                self.current_idx = idx
                self._highlight_bar(idx)
                
                click_type = "left" if event.button() == QtCore.Qt.MouseButton.LeftButton else "right"
                
                if click_type == "right":
                    # 右键复制概念名称
                    concept_text = self.concepts[idx]
                    clipboard = QtWidgets.QApplication.clipboard()
                    clipboard.setText(concept_text)
                    QtWidgets.QToolTip.showText(
                        QtGui.QCursor.pos(), 
                        f"已复制: {concept_text}", 
                        self
                    )
                else:
                    # 左键发送点击回调
                    self._send_callback({
                        "cmd": "CONCEPT_CLICK",
                        "code": self.code,
                        "concept_name": self.concepts[idx],
                        "click_type": click_type,
                        "unique_code": self.unique_code
                    })
        except Exception as e:
            print(f"[ConceptViewer] 鼠标点击处理失败: {e}")
    
    def _on_mouse_move(self, pos):
        """鼠标移动事件 - 显示 tooltip"""
        try:
            if not self.plot.sceneBoundingRect().contains(pos):
                return
            
            vb = self.plot.vb
            mouse_point = vb.mapSceneToView(pos)
            idx = int(round(mouse_point.y()))
            
            if 0 <= idx < len(self.concepts):
                msg = (f"概念: {self.concepts[idx]}\n"
                       f"平均涨幅: {self.avg_percents[idx]:.2f}%\n"
                       f"跟随指数: {self.follow_ratios[idx]:.2f}\n"
                       f"综合得分: {self.scores[idx]:.2f}")
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), msg, self)
        except:
            pass
    
    def keyPressEvent(self, event):
        """键盘事件"""
        key = event.key()
        
        if key == QtCore.Qt.Key.Key_Up:
            self.current_idx = max(0, self.current_idx - 1)
            self._highlight_bar(self.current_idx)
            self._send_callback({
                "cmd": "CONCEPT_CLICK",
                "code": self.code,
                "concept_name": self.concepts[self.current_idx],
                "click_type": "left",
                "unique_code": self.unique_code
            })
            event.accept()
            
        elif key == QtCore.Qt.Key.Key_Down:
            self.current_idx = min(len(self.concepts) - 1, self.current_idx + 1)
            self._highlight_bar(self.current_idx)
            self._send_callback({
                "cmd": "CONCEPT_CLICK",
                "code": self.code,
                "concept_name": self.concepts[self.current_idx],
                "click_type": "left",
                "unique_code": self.unique_code
            })
            event.accept()
            
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if 0 <= self.current_idx < len(self.concepts):
                self._send_callback({
                    "cmd": "CONCEPT_CLICK",
                    "code": self.code,
                    "concept_name": self.concepts[self.current_idx],
                    "click_type": "enter",
                    "unique_code": self.unique_code
                })
            event.accept()
            
        elif key == QtCore.Qt.Key.Key_R:
            # 请求刷新
            self._send_callback({
                "cmd": "REQUEST_REFRESH",
                "code": self.code,
                "top_n": self.top_n,
                "unique_code": self.unique_code
            })
            event.accept()
            
        elif key in (QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_Escape):
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def _send_callback(self, data: Dict):
        """发送回调到主程序"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(('127.0.0.1', IPC_CALLBACK_PORT))
            
            msg = json.dumps(data, ensure_ascii=False).encode('utf-8')
            sock.send(struct.pack('>I', len(msg)) + msg)
            sock.close()
        except Exception as e:
            print(f"[ConceptViewer] 发送回调失败: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        self._send_callback({
            "cmd": "VIEWER_CLOSED",
            "code": self.code,
            "top_n": self.top_n,
            "unique_code": self.unique_code
        })
        event.accept()


class ConceptViewerIPC:
    """IPC 数据接收器"""
    
    def __init__(self, window: ConceptViewerWindow):
        self.window = window
        self.running = True
        self.server_socket = None
        self.thread = None
    
    def start(self):
        """启动 IPC 监听"""
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """停止 IPC 监听"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
    
    def _listen_loop(self):
        """IPC 监听循环"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('127.0.0.1', IPC_LISTEN_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            
            print(f"[ConceptViewer] IPC 监听启动: 127.0.0.1:{IPC_LISTEN_PORT}")
            
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                    self._handle_connection(conn)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[ConceptViewer] IPC 接收错误: {e}")
        except Exception as e:
            print(f"[ConceptViewer] IPC 启动失败: {e}")
    
    def _handle_connection(self, conn):
        """处理单个连接"""
        try:
            # 读取消息长度 (4 bytes, big-endian)
            length_data = conn.recv(4)
            if len(length_data) < 4:
                return
            
            msg_length = struct.unpack('>I', length_data)[0]
            
            # 读取消息体
            msg_data = b''
            while len(msg_data) < msg_length:
                chunk = conn.recv(min(4096, msg_length - len(msg_data)))
                if not chunk:
                    break
                msg_data += chunk
            
            data = json.loads(msg_data.decode('utf-8'))
            cmd = data.get('cmd', '')
            
            if cmd == 'UPDATE_DATA':
                # 通过信号安全更新 UI
                self.window.data_received.emit(data)
            elif cmd == 'CLOSE':
                QtCore.QTimer.singleShot(0, self.window.close)
            
        except Exception as e:
            print(f"[ConceptViewer] 处理消息失败: {e}")
        finally:
            try:
                conn.close()
            except:
                pass


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description='概念分析独立查看器')
    parser.add_argument('--code', type=str, default='总览', help='股票代码')
    parser.add_argument('--top_n', type=int, default=10, help='显示前N个概念')
    parser.add_argument('--data', type=str, default='', help='初始数据 (JSON)')
    args = parser.parse_args()
    
    # 解析初始数据
    initial_data = None
    if args.data:
        try:
            initial_data = json.loads(args.data)
        except:
            pass
    
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 创建窗口
    window = ConceptViewerWindow(args.code, args.top_n, initial_data)
    
    # 启动 IPC
    ipc = ConceptViewerIPC(window)
    ipc.start()
    
    # 显示窗口
    window.show()
    
    # 运行事件循环
    ret = app.exec()
    
    # 清理
    ipc.stop()
    sys.exit(ret)


if __name__ == '__main__':
    main()
