# -*- coding: utf-8 -*-
"""
ATS Alert Notifier
特异黄金信号弹窗与语音反馈通知组件 — 专为高胜率、买卖逻辑特异个股实施弹屏与语音播报
"""

import sys
import os
import time
import logging

logger = logging.getLogger("ats.alert_notifier")

try:
    from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QFrame, QLabel, QVBoxLayout, QApplication
    from PyQt6.QtGui import QIcon
    from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False


_active_toasts = set()

class InAppToastWidget(QFrame if HAS_PYQT else object):
    """应用内半透明高分屏自适应 Toast 卡片 (支持点击联动定位股票，100% 优雅显示)"""
    def __init__(self, title, message, code="", parent=None):
        if not HAS_PYQT:
            return
        super().__init__(None) # 使用独立 Tool 浮窗，全屏幕右下角弹出，绝不被父容器裁切或遮挡
        self.code = str(code).strip()
        self.target_parent = parent
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.code:
            self.setToolTip(f"💡 点击即可在列表中自动高亮定位 [{self.code}] 并联动分析")
        
        # 强引用注册，防止 Python 垃圾回收器 (GC) 提前销毁弹窗
        _active_toasts.add(self)

        # 动态寻找 parent (多周期/ATS主窗口) 所在的物理显示屏 (Screen)
        screen = None
        if parent and hasattr(parent, 'screen') and parent.screen():
            screen = parent.screen()
        elif parent and hasattr(parent, 'window') and parent.window() and parent.window().screen():
            screen = parent.window().screen()

        if not screen and HAS_PYQT:
            try:
                from PyQt6.QtGui import QCursor
                screen = QApplication.screenAt(QCursor.pos())
            except Exception:
                pass
        if not screen:
            screen = QApplication.primaryScreen()

        # 调整为更高、更窄的精致直立黄金比 (高一点 94px、窄一点 260px，更舒展舒服)
        card_w = 260
        card_h = 94
        title_f_size = 12
        msg_f_size = 10

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(4)
        
        lbl_t = QLabel(title, self)
        lbl_t.setStyleSheet(f"color: #ffca28; font-weight: bold; font-size: {title_f_size}px; background: transparent;")
        lbl_m = QLabel(message, self)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet(f"color: #e2e8f0; font-size: {msg_f_size}px; background: transparent; line-height: 1.35;")
        
        layout.addWidget(lbl_t)
        layout.addWidget(lbl_m)
        
        # 100% 纯不透明实色背景 + 1px 霓虹蓝精致高对比边框
        self.setStyleSheet(f"""
            InAppToastWidget {{
                background-color: #0f172a;
                border: 1px solid #00b0ff;
                border-radius: 6px;
            }}
            InAppToastWidget:hover {{
                border-color: #00e676;
                background-color: #1e293b;
            }}
        """)
        
        self.resize(card_w, card_h)
        
        # 目标窗口所在屏幕的右下角精致定位 (Target Screen Bottom-Right)，留出 Taskbar 任务栏边距
        if screen:
            try:
                s_geom = screen.availableGeometry()
                pos_x = s_geom.right() - card_w - 15
                pos_y = s_geom.bottom() - card_h - 15
                self.move(max(s_geom.left() + 10, pos_x), max(s_geom.top() + 10, pos_y))
            except Exception:
                self.move(100, 100)
        else:
            self.move(100, 100)

        self.show()
        self.raise_()
        QTimer.singleShot(8000, self.close)

    def closeEvent(self, event):
        """关闭时主动从强引用池解绑"""
        _active_toasts.discard(self)
        super().closeEvent(event)

    def mousePressEvent(self, event):
        """点击 Toast 弹窗一键自动联动定位股票"""
        super().mousePressEvent(event)
        parent = getattr(self, 'target_parent', None) or self.parent()
        if not self.code or not parent:
            self.close()
            return

        logger.info(f"🎯 [TOAST_CLICK] 点击特异 Toast 通知，尝试自动定位联动股票: {self.code}")

        # 1. 尝试使用 MultiPeriodDialog 定位 (传入 auto_popup=True 弹出诊断小窗口)
        if hasattr(parent, 'locate_stock_in_table'):
            parent.locate_stock_in_table(self.code, auto_popup=True)

        # 2. 尝试使用 ATS MainWindow 定位 (传入 auto_popup=True 弹出详情小窗口)
        if hasattr(parent, 'locate_stock_in_tree'):
            parent.locate_stock_in_tree(self.code, auto_popup=True)

        self.close()


class AlertNotifier(QObject if HAS_PYQT else object):
    """黄金特异信号桌面弹窗与语音通知器"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            if HAS_PYQT:
                cls._instance = super().__new__(cls)
                QObject.__init__(cls._instance)
            else:
                cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, *args, **kwargs):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self.tray_icon = None
        self._last_alert_ts = {}  # 单股 15 分钟内冷却
        self._last_global_ts = 0.0 # 全局 15 秒内冷却，防止批量刷屏
        self._last_notified_code = None
        self._last_parent = None
        self._init_tray()
        
    def _init_tray(self):
        if not HAS_PYQT:
            return
        try:
            self.tray_icon = QSystemTrayIcon(self)
            icon_path = os.path.join(os.path.dirname(__file__), "..", "MonitorTK32.ico")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                try:
                    app = QApplication.instance()
                    if app and hasattr(QStyle, "StandardPixmap"):
                        self.tray_icon.setIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
                except Exception:
                    pass

            if self.tray_icon.icon().isNull():
                try:
                    from PyQt6.QtGui import QPixmap, QPainter, QColor, QBrush
                    from PyQt6.QtCore import Qt
                    pixmap = QPixmap(32, 32)
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setBrush(QBrush(QColor("#00ff88")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(2, 2, 28, 28)
                    painter.end()
                    self.tray_icon.setIcon(QIcon(pixmap))
                except Exception:
                    pass

            # [KEY FIX] 绑定 Windows 系统托盘 Toast 点击事件
            self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
            self.tray_icon.show()
        except Exception as e:
            logger.warning(f"Failed to initialize QSystemTrayIcon: {e}")

    def _on_tray_message_clicked(self):
        """点击 Windows 系统托盘 Toast 消息弹窗，自动定位高亮与弹出详情小窗口"""
        if not self._last_notified_code:
            return
        code = self._last_notified_code
        logger.info(f"🎯 [TRAY_CLICK] 用户点击 Windows 托盘 Toast 弹窗，自动联动定位股票: {code}")

        if HAS_PYQT:
            try:
                target_p = self._last_parent if self._last_parent else QApplication.activeWindow()
                if target_p:
                    # 1. 在 MultiPeriodDialog 表格中定位高亮并自动打开【详情窗口】
                    if hasattr(target_p, 'locate_stock_in_table'):
                        target_p.locate_stock_in_table(code, auto_popup=True)

                    # 2. 在 ATS MainWindow 左侧树中定位高亮并自动弹出详情小窗口
                    if hasattr(target_p, 'locate_stock_in_tree'):
                        target_p.locate_stock_in_tree(code, auto_popup=True)
            except Exception as e_clk:
                logger.warning(f"Tray click response failed: {e_clk}")

    def notify(self, title, message, code="", score=90.0, level="GOLD", parent=None):
        """通用通知方法别名，无缝兼容多周期等系统调用"""
        name = str(title).strip()
        reason = str(message).strip()
        return self.notify_special_signal(code=code, name=name, reason=reason, score=score, parent=parent)

    def notify_special_signal(self, code, name, reason, score=90.0, win_rate="85.0%", parent=None):
        """推送信信号弹窗与语音
        
        Args:
            code: 股票代码
            name: 股票名称
            reason: 买卖逻辑理由 (如: 自动通道Fib50企稳|2D/3D阶梯抬升|板块大哥带队)
            score: 特异打分
            win_rate: 历史有效胜率
            parent: 主界面句柄 (传入后开启应用内右上角高亮 Toast 提示)
        """
        # 0. 特异打分门槛过滤：小于 88.0 分的微弱异动静默过滤，避免干扰用户
        if score < 88.0:
            return

        now = time.time()
        code_str = str(code).strip()

        # 1. 全局限频：15 秒内最多推送 1 条，杜绝批量刷屏
        if (now - self._last_global_ts) < 15.0:
            return

        # 2. 单股限频：同一股票 15 分钟 (900s) 内绝不重复推送
        last_ts = self._last_alert_ts.get(code_str, 0.0)
        if (now - last_ts) < 900.0:
            return

        self._last_global_ts = now
        self._last_alert_ts[code_str] = now
        self._last_notified_code = code_str
        self._last_parent = parent

        title = f"⭐ 黄金特异信号: {name} ({code_str})"
        message = f"【打分】: {score:.1f}分 | 【胜率】: {win_rate}\n【逻辑】: {reason}"
        
        logger.info(f"📢 [ALERT_NOTIFY] 触发特异黄金桌面/界面通知: {title} | {message}")
        
        # 1. 在当前屏幕/活跃窗口右上角弹出高分屏 HighDPI 自适应炫酷 Toast (100% 优雅美观且完美放大幅面)
        toast_success = False
        if HAS_PYQT:
            try:
                target_p = parent if parent else QApplication.activeWindow()
                InAppToastWidget(title, message, code=code_str, parent=target_p)
                toast_success = True
            except Exception as e_toast:
                logger.warning(f"InAppToastWidget failed: {e_toast}")

        # 2. 仅在无 GUI 界面极特殊环境下 Fallback 到系统托盘消息
        if not toast_success and self.tray_icon and HAS_PYQT:
            try:
                if not self.tray_icon.isVisible():
                    self.tray_icon.show()

                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    6000
                )
            except Exception as e:
                logger.warning(f"ShowMessage failed: {e}")
                
        # 3. 触发 TTS 语音播报 (绝对禁用 pyttsx3，基于项目标准 AlertManager 或 SAPI.SpVoice 独立 safe 子线程)
        voice_text = f"特异买点 {name}，{reason}"
        self._speak_text(voice_text)

    def _speak_text(self, text: str):
        """标准 safe 子线程语音播报：基于 AlertManager / SAPI.SpVoice，绝对不与 Tk/Qt/Vis 冲突"""
        if not text:
            return

        def _worker():
            # 1. 优先使用项目标准的 alert_manager (无缝集成队列与全系统配置)
            try:
                from alert_manager import get_alert_manager
                mgr = get_alert_manager()
                if hasattr(mgr, 'speak'):
                    mgr.speak(text)
                    return
            except Exception:
                pass

            # 2. Fallback: 独立 CoInitialize() 的 Win32 SAPI.SpVoice 线程直连 (绝不上锁、不冲突 pyttsx3)
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                speaker.Rate = 1
                speaker.Volume = 100
                speaker.Speak(str(text), 0)
                del speaker
                pythoncom.CoUninitialize()
            except Exception as e:
                logger.warning(f"Fallback SAPI.SpVoice speak error: {e}")

        import threading
        t = threading.Thread(target=_worker, name="ATSSafeVoiceThread", daemon=True)
        t.start()
