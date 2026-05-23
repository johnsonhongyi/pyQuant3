# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from typing import Any
from PyQt6 import QtCore, QtGui, QtWidgets
from tk_gui_modules.window_mixin import WindowMixin


class OrderConfirmationBubble(QtWidgets.QDialog, WindowMixin):
    """交易内核人工确认悬浮气泡框 (Phase 7: Human Confirmation Mode)
    
    采用 Cyberpunk Dark 暗黑科技质感风格，提供 15秒倒计时物理自毁保护，
    并内置仓位微调滑块，支持操盘手对获风控准入的 ApprovedOrder 执行 Confirm / Override / Reject 操作。
    """

    def __init__(
        self,
        order_info: dict[str, Any],
        parent: QtWidgets.QWidget | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        super().__init__(parent)
        self.order_info = order_info
        self.timeout_seconds = timeout_seconds
        self.remaining_seconds = timeout_seconds
        
        # 返回结果状态机
        self.result_data = {
            "confirmed": False,
            "size_pct_override": None,
            "override_reason": "Timeout auto rejection",
        }

        self.setWindowTitle("⚡ 交易内核委托人工确认 (Human Confirmation)")
        self.setWindowFlags(
            QtCore.Qt.WindowType.WindowStaysOnTopHint 
            | QtCore.Qt.WindowType.FramelessWindowHint 
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 初始默认尺寸
        self.resize(380, 240)
        
        self._init_ui()
        self._setup_timer()
        self._center_on_screen()

    def _init_ui(self) -> None:
        # 1. 暗黑科技感玻璃拟态外框 (Glassmorphism Frame)
        self.main_frame = QtWidgets.QFrame(self)
        self.main_frame.setObjectName("MainFrame")
        self.main_frame.setStyleSheet("""
            QFrame#MainFrame {
                background-color: rgba(20, 24, 30, 0.95);
                border: 2px solid rgba(0, 240, 255, 0.4);
                border-radius: 12px;
            }
            QLabel {
                color: #e0e6ed;
                font-family: 'Segoe UI', 'Microsoft YaHei';
            }
        """)
        
        # 给外框加精致的呼吸阴影 (Cyan Shadow)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QtGui.QColor(0, 240, 255, 100))
        shadow.setOffset(0, 0)
        self.main_frame.setGraphicsEffect(shadow)

        layout = QtWidgets.QVBoxLayout(self.main_frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 2. 顶部标题栏带 Emoji
        title_label = QtWidgets.QLabel("⚠️ 交易内核委托确认请求", self)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(title_label)

        # 分割线
        line = QtWidgets.QFrame(self)
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(0, 240, 255, 0.2);")
        layout.addWidget(line)

        # 3. 核心订单参数展示 (Emoji 高对比度着色)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)

        action = self.order_info.get("action", "BUY").upper()
        action_color = "#39ff14" if action in {"BUY", "ADD"} else "#ff073a"
        action_text = f"🟢 {action}" if action in {"BUY", "ADD"} else f"🔴 {action}"

        code_label = QtWidgets.QLabel(f"证券代码: <b>{self.order_info.get('code', '')}</b>", self)
        name_label = QtWidgets.QLabel(f"证券名称: <b>{self.order_info.get('name', '未知名')}</b>", self)
        action_val = QtWidgets.QLabel(self)
        action_val.setText(f"动作方向: <span style='color:{action_color}; font-weight:bold;'>{action_text}</span>")
        price_label = QtWidgets.QLabel(f"委托价格: <span style='color:#ffcc00; font-weight:bold;'>{self.order_info.get('price', 0.0):.2f} 元</span>", self)

        grid.addWidget(code_label, 0, 0)
        grid.addWidget(name_label, 0, 1)
        grid.addWidget(action_val, 1, 0)
        grid.addWidget(price_label, 1, 1)
        layout.addLayout(grid)

        # 4. 仓位占比微调控制滑块 (QSlider + Spinner 联动)
        slider_layout = QtWidgets.QHBoxLayout()
        slider_label = QtWidgets.QLabel("下单仓位占比:", self)
        
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self.slider.setMinimum(1)
        self.slider.setMaximum(100)
        
        # 将原始 size_pct (如 0.15) 映射为 1-100 的整数 (15)
        init_pct = int(self.order_info.get("size_pct", 0.10) * 100)
        self.slider.setValue(max(1, min(init_pct, 100)))
        
        self.value_label = QtWidgets.QLabel(f"<b>{self.slider.value()}%</b>", self)
        self.value_label.setStyleSheet("color: #00f0ff; font-size: 13px; min-width: 40px;")
        
        self.slider.valueChanged.connect(self._on_slider_changed)
        
        slider_layout.addWidget(slider_label)
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.value_label)
        layout.addLayout(slider_layout)

        # 5. 双排按钮栏：确认委托 (Confirm) & 物理拒绝 (Cancel)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_confirm = QtWidgets.QPushButton("⚡ 同意委托 (Confirm)", self)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: rgba(57, 255, 20, 0.2);
                color: #39ff14;
                border: 1px solid #39ff14;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(57, 255, 20, 0.4);
            }
        """)
        self.btn_confirm.clicked.connect(self._on_confirm)

        self.btn_cancel = QtWidgets.QPushButton("❌ 物理拒绝 (Reject)", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 7, 58, 0.2);
                color: #ff073a;
                border: 1px solid #ff073a;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 7, 58, 0.4);
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)

        # 6. 底部倒计时进度条
        timer_layout = QtWidgets.QHBoxLayout()
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setRange(0, self.timeout_seconds)
        self.progress_bar.setValue(self.timeout_seconds)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #00f0ff;
                border-radius: 2px;
            }
        """)
        
        self.countdown_label = QtWidgets.QLabel(f"⏱️ 剩余时间: {self.remaining_seconds}秒", self)
        self.countdown_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        timer_layout.addWidget(self.progress_bar)
        timer_layout.addWidget(self.countdown_label)
        layout.addLayout(timer_layout)

        # 布局自适应绑定
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_frame)

    def _setup_timer(self) -> None:
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

    def _on_tick(self) -> None:
        self.remaining_seconds -= 1
        self.progress_bar.setValue(self.remaining_seconds)
        self.countdown_label.setText(f"⏱️ 剩余时间: {self.remaining_seconds}秒")
        
        if self.remaining_seconds <= 0:
            self.timer.stop()
            self.result_data = {
                "confirmed": False,
                "size_pct_override": None,
                "override_reason": "Trader response timeout",
            }
            self.reject()

    def _on_slider_changed(self, val: int) -> None:
        self.value_label.setText(f"<b>{val}%</b>")

    def _on_confirm(self) -> None:
        self.timer.stop()
        final_pct = self.slider.value() / 100.0
        orig_pct = self.order_info.get("size_pct", 0.10)
        
        override_needed = abs(final_pct - orig_pct) > 0.001
        self.result_data = {
            "confirmed": True,
            "size_pct_override": final_pct if override_needed else None,
            "override_reason": "Trader confirmed manual approval" if not override_needed else "Trader manual size modification",
        }
        self.accept()

    def _on_cancel(self) -> None:
        self.timer.stop()
        self.result_data = {
            "confirmed": False,
            "size_pct_override": None,
            "override_reason": "Trader clicked Reject button",
        }
        self.reject()

    def _center_on_screen(self) -> None:
        # 获取当前鼠标所在的屏幕，实现完美的防跨屏分裂
        screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        if not screen:
            screen = QtGui.QGuiApplication.primaryScreen()
        
        if screen:
            geom = screen.geometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            # 偏置于中上方，吸引视线且避开操作区
            y = geom.y() + (geom.height() - self.height()) // 3
            self.move(x, y)


class ConfirmDispatcher(QtCore.QObject):
    """跨线程 Qt 确认弹窗调度器"""
    request_confirm = QtCore.pyqtSignal(dict, dict, object)  # (order_info, result_container, threading_event)

    def __init__(self) -> None:
        super().__init__()
        self.request_confirm.connect(self._handle_request)

    def _handle_request(self, order_info: dict[str, Any], container: dict[str, Any], event: Any) -> None:
        try:
            bubble = OrderConfirmationBubble(order_info)
            bubble.exec()
            container.update(bubble.result_data)
        except Exception as e:
            container["confirmed"] = False
            container["override_reason"] = f"DISPATCHER_EXCEPTION: {str(e)}"
        finally:
            event.set()


_DISPATCHER: ConfirmDispatcher | None = None


def init_confirm_dispatcher() -> None:
    """在 Qt 主线程初始化调度器"""
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = ConfirmDispatcher()


def show_confirmation_bubble_sync(order_info: dict[str, Any], parent: QtWidgets.QWidget | None = None) -> dict[str, Any]:
    """线程安全地物理拉起阻塞式人工确认弹窗并同步返回应答字典"""
    import threading
    
    # 检查是否在 Qt 主线程
    app = QtWidgets.QApplication.instance()
    if not app:
        # 如果 Qt app 尚未创建，先初始化 (通常仅在测试阶段或独立脚本中发生)
        argv = sys.argv if hasattr(sys, 'argv') and sys.argv else ['']
        app = QtWidgets.QApplication(argv)
        
    is_main_thread = (QtCore.QThread.currentThread() == app.thread())
    
    if is_main_thread:
        # 主线程直接实例化运行
        bubble = OrderConfirmationBubble(order_info, parent=parent)
        bubble.exec()
        return bubble.result_data
    else:
        # 非主线程，利用信号槽把弹窗委派给 Qt 主线程执行，并阻塞等待应答
        global _DISPATCHER
        if _DISPATCHER is None:
            # 安全防空：如果在非主线程首次调用且 dispatcher 还没初始化
            # 应尽可能在主线程完成初始化，这里做一次 fallback
            return {
                "confirmed": False,
                "size_pct_override": None,
                "override_reason": "ConfirmDispatcher not initialized on main thread",
            }
            
        result_container: dict[str, Any] = {}
        event = threading.Event()
        
        # 委派至主线程
        _DISPATCHER.request_confirm.emit(order_info, result_container, event)
        
        # 阻塞当前后台线程，等待主线程物理弹窗完毕并 set event
        event.wait()
        return result_container

