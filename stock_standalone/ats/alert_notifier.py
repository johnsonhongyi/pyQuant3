# -*- coding: utf-8 -*-
"""
ATS Alert Notifier
特异黄金信号弹窗与语音反馈通知组件 — 专为高胜率、买卖逻辑特异个股实施弹屏与语音播报
"""

import sys
import os
import time
import logging
from typing import Optional, Tuple, Dict, List, Any

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
    """应用内半透明高分屏自适应 Toast 卡片 (支持自由拖拽到副屏/任意屏幕、点击联动定位股票，100% 优雅显示)"""
    _custom_pos: Optional[Tuple[int, int]] = None  # 跨屏幕自定义持久化坐标 (全局记忆)

    def __init__(self, title, message, code="", parent=None):
        if not HAS_PYQT:
            return
        super().__init__(None) # 使用独立 Tool 浮窗，全屏幕弹出，支持自由跨屏拖动
        self.code = str(code).strip()
        self.target_parent = parent
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 拖拽状态
        self._drag_pos = None
        self._press_pos = None
        self._is_dragging = False

        tip_str = "💡 点击即可在列表中高亮定位并联动分析\n🖱️ 按住鼠标左键可自由拖动至副屏/任意屏幕记忆通知位置"
        if self.code:
            tip_str = f"💡 点击即可在列表中自动高亮定位 [{self.code}] 并联动分析\n🖱️ 按住鼠标左键可自由拖动至副屏/任意屏幕记忆通知位置"
        self.setToolTip(tip_str)
        
        # 强引用注册，防止 Python 垃圾回收器 (GC) 提前销毁弹窗
        _active_toasts.add(self)

        # 调整为精致直立黄金比
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
        
        # ── 智能多屏位置决定 ──
        # 1. 优先使用用户手动拖动过的多屏自定义坐标
        has_positioned = False
        if InAppToastWidget._custom_pos is not None:
            cx, cy = InAppToastWidget._custom_pos
            from PyQt6.QtCore import QPoint
            scr = QApplication.screenAt(QPoint(cx, cy))
            if scr:
                self.move(cx, cy)
                has_positioned = True

        # 2. 默认定位在目标窗口所在屏幕或用户通过右键菜单指定的显示器右下角
        if not has_positioned:
            screen = None
            if getattr(InAppToastWidget, '_target_screen_index', None) is not None:
                screens = QApplication.screens()
                tgt_idx = InAppToastWidget._target_screen_index
                if 0 <= tgt_idx < len(screens):
                    screen = screens[tgt_idx]

            if not screen and parent and hasattr(parent, 'screen') and parent.screen():
                screen = parent.screen()
            elif not screen and parent and hasattr(parent, 'window') and parent.window() and parent.window().screen():
                screen = parent.window().screen()

            if not screen and HAS_PYQT:
                try:
                    from PyQt6.QtGui import QCursor
                    screen = QApplication.screenAt(QCursor.pos())
                except Exception:
                    pass
            if not screen:
                screen = QApplication.primaryScreen()

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

    def closeEvent(self, event):
        """关闭时主动从强引用池解绑"""
        _active_toasts.discard(self)
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos:
            curr_pos = event.globalPosition().toPoint()
            if self._press_pos and (curr_pos - self._press_pos).manhattanLength() > 4:
                self._is_dragging = True
                self.move(curr_pos - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                # 用户完成了跨屏幕拖拽：记录自定义坐标，后续所有通知均在此时拖动的新屏幕位置弹出！
                InAppToastWidget._custom_pos = (self.x(), self.y())
                logger.info(f"📍 [TOAST_DRAG] 用户已将通知窗口拖动至新屏幕坐标: {InAppToastWidget._custom_pos}，后续通知将在此屏幕展示")
                self._is_dragging = False
                self._drag_pos = None
                self._press_pos = None
                return
            
            # 纯单击触发股票联动定位
            self._is_dragging = False
            self._drag_pos = None
            self._press_pos = None

            parent = getattr(self, 'target_parent', None) or self.parent()
            if not self.code or not parent:
                self.close()
                return

            logger.info(f"🎯 [TOAST_CLICK] 点击特异 Toast 通知，尝试自动定位联动股票: {self.code}")

            # 1. 尝试使用 MultiPeriodDialog 定位
            if hasattr(parent, 'locate_stock_in_table'):
                parent.locate_stock_in_table(self.code, auto_popup=True)

            # 2. 尝试使用 ATS MainWindow 定位
            if hasattr(parent, 'locate_stock_in_tree'):
                parent.locate_stock_in_tree(self.code, auto_popup=True)

            self.close()
        super().mouseReleaseEvent(event)


class AlertNotifier(QObject if HAS_PYQT else object):
    """黄金特异信号桌面弹窗与语音通知器 (支持串行轮播队列)"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'AlertNotifier':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

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
        self._last_alert_ts = {}  # 单股冷却
        self._last_global_ts = 0.0 # 全局冷却
        self._last_notified_code = None
        self._last_parent = None
        
        # 串行轮播通知队列
        import collections
        self._notify_queue = collections.deque()
        self._is_busy = False
        self._current_toast = None
        self._init_tray()

    def shutdown(self):
        """关闭并销毁系统托盘图标与浮动 Toast 弹窗，确保主进程退出"""
        try:
            if self.tray_icon:
                self.tray_icon.hide()
                self.tray_icon.deleteLater()
                self.tray_icon = None
        except Exception as e:
            logger.debug(f"Error hiding tray_icon: {e}")
        try:
            if self._current_toast:
                self._current_toast.close()
                self._current_toast = None
        except Exception:
            pass
        self._notify_queue.clear()
        
    def _init_tray(self):
        if not HAS_PYQT:
            return
        if not QApplication.instance():
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

            # [🖥️ 任务栏右键菜单] 构建高颜值暗黑风格托盘上下文菜单
            self._init_tray_context_menu()

            # [KEY FIX] 绑定 Windows 系统托盘 Toast 点击事件
            self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
            self.tray_icon.show()
        except Exception as e:
            logger.warning(f"Failed to initialize QSystemTrayIcon: {e}")

    def _init_tray_context_menu(self):
        """构建托盘图标右键菜单 (支持多显示器切换、位置复位、测试通知等)"""
        if not HAS_PYQT or not self.tray_icon:
            return
        
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #13161c;
                color: #e2e8f0;
                border: 1px solid #2d3748;
                border-radius: 6px;
                padding: 5px;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 9.5pt;
            }
            QMenu::item {
                padding: 6px 22px 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1e3a8a;
                color: #00ffaa;
            }
            QMenu::item:checked {
                color: #00ffaa;
                font-weight: bold;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d3748;
                margin: 4px 6px;
            }
        """)

        # 1. 显示器设置子菜单
        self.menu_displays = self.tray_menu.addMenu("🖥️ 预警通知显示器设置")
        self.tray_menu.aboutToShow.connect(self._refresh_displays_menu)

        # 2. 重置弹窗位置
        act_reset_pos = self.tray_menu.addAction("🎯 重置通知位置 (默认右下角)")
        act_reset_pos.triggered.connect(self._reset_toast_position)

        self.tray_menu.addSeparator()

        # 3. 发送测试预警通知
        act_test_notify = self.tray_menu.addAction("📢 发送测试特异预警通知")
        act_test_notify.triggered.connect(self._send_test_notification)

        self.tray_menu.addSeparator()

        # 4. 退出程序
        act_quit = self.tray_menu.addAction("🚪 退出系统")
        act_quit.triggered.connect(self._on_tray_quit_clicked)

        self.tray_icon.setContextMenu(self.tray_menu)

    def _refresh_displays_menu(self):
        """动态枚举当前所有屏幕并更新勾选状态"""
        if not HAS_PYQT or not hasattr(self, 'menu_displays'):
            return
        self.menu_displays.clear()
        screens = QApplication.screens()
        target_idx = getattr(InAppToastWidget, '_target_screen_index', None)

        for idx, scr in enumerate(screens):
            geom = scr.geometry()
            is_primary = (scr == QApplication.primaryScreen())
            tag = " (主屏幕)" if is_primary else f" (副屏 {idx})"
            title = f"显示器 {idx + 1}{tag} [{geom.width()}x{geom.height()}]"
            
            act = self.menu_displays.addAction(title)
            act.setCheckable(True)
            
            is_checked = (target_idx == idx) if target_idx is not None else is_primary
            act.setChecked(is_checked)
            act.triggered.connect(lambda checked, i=idx: self._select_target_screen(i))

    def _select_target_screen(self, screen_index: int):
        """用户通过托盘右键菜单选择目标显示器"""
        screens = QApplication.screens()
        if 0 <= screen_index < len(screens):
            InAppToastWidget._target_screen_index = screen_index
            InAppToastWidget._custom_pos = None # 清除手动坐标，复位到所选屏幕默认右下角
            scr = screens[screen_index]
            geom = scr.geometry()
            logger.info(f"🖥️ [TRAY_MENU] 用户已通过任务栏右键菜单切换预警通知显示器为: 显示器 {screen_index + 1} ({geom.width()}x{geom.height()})")
            
            # 立即弹出一个轻量 Toast 确认切换
            try:
                InAppToastWidget(
                    "🖥️ 显示器设置已生效", 
                    f"预警通知与特异买点将固定在【显示器 {screen_index + 1}】({geom.width()}x{geom.height()}) 弹出展示",
                    code="",
                    parent=None
                )
            except Exception as e:
                logger.debug(f"Confirm toast failed: {e}")

    def _reset_toast_position(self):
        """重置弹窗坐标到当前屏幕默认右下角"""
        InAppToastWidget._custom_pos = None
        logger.info("🎯 [TRAY_MENU] 已重置通知弹窗位置为默认右下角")
        try:
            InAppToastWidget(
                "🎯 通知位置已复位", 
                "已重置为默认右下角位置。\n(后续可随时按住鼠标左键拖拽至任意屏幕)",
                code="",
                parent=None
            )
        except Exception:
            pass

    def _send_test_notification(self):
        """发送测试特异预警通知"""
        self.notify_special_signal(
            code="688356", 
            name="键凯科技", 
            reason="【实盘演示】空间高度龙，站稳VWAP均线，买盘压强88%，黄金定龙点火", 
            score=94.0
        )

    def _on_tray_quit_clicked(self):
        """托盘菜单退出"""
        app = QApplication.instance()
        if app:
            app.quit()

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

    def notify_special_signal(self, code, name, reason, score=90.0, win_rate="85.0%", parent=None, is_force=False):
        """推送信信号弹窗与语音
        
        Args:
            code: 股票代码
            name: 股票名称
            reason: 买卖逻辑理由 (如: 自动通道Fib50企稳|2D/3D阶梯抬升|板块大哥带队)
            score: 特异打分
            win_rate: 历史有效胜率
            parent: 主界面句柄 (传入后开启应用内右上角高亮 Toast 提示)
            is_force: 是否强制弹窗/测试 (跳过限频和去重)
        """
        now = time.time()
        code_str = str(code).strip().zfill(6)
        reason_str = str(reason).strip()
        is_priority_signal = is_force or ("通达信" in reason_str) or ("精选" in reason_str) or ("重点关注" in reason_str) or ("实盘演示" in reason_str) or (score >= 88.0)

        # 0. 特异打分门槛过滤：小于 78.0 分且非重点/精选的微弱异动静默过滤
        if score < 78.0 and not is_priority_signal:
            return

        # 0.1 通过共享 SignalLedger 校验是否今天已提示过相同的信号提示，防止 ATS 与多周期重复播报 (强制模式跳过)
        if not is_force:
            try:
                from ats.signal_ledger import get_signal_ledger
                ledger = get_signal_ledger()
                if ledger.is_notified_today(code_str, reason_str):
                    logger.info(f"🔇 [ALERT_NOTIFY] 该信号 [{code_str} | {reason_str}] 今日已播报提醒，自动去重跳过重复提示")
                    return
            except Exception as e_check:
                logger.warning(f"[AlertNotifier] Deduplication check failed: {e_check}")

        # 仅对普通微弱信号进行时间抽样拦截；重点/精选/实盘信号免除全局丢弃，保证 100% 依次弹窗+语音轮播
        if not is_priority_signal and not is_force:
            # 1. 普通信号全局限频：15 秒内最多推送 1 条
            if (now - self._last_global_ts) < 10.0:
                return

            # 2. 普通信号单股限频：同一股票 15 分钟 (900s) 内不重复推送
            last_ts = self._last_alert_ts.get(code_str, 0.0)
            if (now - last_ts) < 900.0:
                return

        # 标记为今日已播报提醒 (去重写入 SignalLedger)
        try:
            from ats.signal_ledger import get_signal_ledger
            get_signal_ledger().mark_notified_today(code_str, reason)
        except Exception:
            pass

        self._last_global_ts = now
        self._last_alert_ts[code_str] = now

        item = {
            'code': code_str,
            'name': name,
            'reason': reason,
            'score': score,
            'win_rate': win_rate,
            'parent': parent,
            'ts': now
        }
        self._notify_queue.append(item)
        self._process_queue()

    def _process_queue(self):
        """串行轮播队列处理：前一个信号弹窗+语音播报完毕后再弹出下一个"""
        if self._is_busy:
            return
        if not self._notify_queue:
            self._is_busy = False
            return

        self._is_busy = True
        item = self._notify_queue.popleft()

        code_str = item['code']
        name = item['name']
        reason = item['reason']
        score = item['score']
        win_rate = item['win_rate']
        parent = item['parent']

        self._last_notified_code = code_str
        self._last_parent = parent

        title = f"⭐ 黄金特异信号: {name} ({code_str})"
        message = f"【打分】: {score:.1f}分 | 【胜率】: {win_rate}\n【逻辑】: {reason}"

        logger.info(f"📢 [ALERT_NOTIFY] 串行轮播弹出信号 [{name} | {code_str}]: {reason}")

        # 1. 弹出右下角 Toast 卡片 (完全还原原始样式与固定位置)
        toast_success = False
        if HAS_PYQT and QApplication.instance():
            try:
                target_p = parent if parent else QApplication.activeWindow()
                self._current_toast = InAppToastWidget(title, message, code=code_str, parent=target_p)
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

        # 3. 触发语音播报
        voice_text = f"特异买点 {name}，{reason}"
        self._speak_text(voice_text)

        # 4. 根据语音与内容自适应展示时长 (最小 4.5s，随文本长度平滑顺延)
        display_sec = max(4.5, min(8.5, len(voice_text) * 0.32 + 1.2))
        display_ms = int(display_sec * 1000)

        if HAS_PYQT and QApplication.instance():
            QTimer.singleShot(display_ms, self._on_current_item_finished)
        else:
            import threading
            threading.Timer(display_sec, self._on_current_item_finished).start()

    def _on_current_item_finished(self):
        """当前信号展示与播报完成，关闭当前 Toast，并秒级切入下一个信号"""
        if self._current_toast:
            try:
                self._current_toast.close()
            except Exception:
                pass
            self._current_toast = None

        self._is_busy = False

        # 延迟 300ms 顺畅弹出下一个轮播信号
        if HAS_PYQT and QApplication.instance():
            QTimer.singleShot(300, self._process_queue)
        else:
            self._process_queue()

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
