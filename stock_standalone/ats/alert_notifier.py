# -*- coding: utf-8 -*-
"""
ATS Alert Notifier
特异黄金信号弹窗与语音反馈通知组件 — 专为高胜率、买卖逻辑特异个股实施弹屏与语音播报
"""

import sys
import os
import time
import json
import threading
import logging
from typing import Optional, Tuple, Dict, List, Any

logger = logging.getLogger("ats.alert_notifier")

try:
    from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QFrame, QLabel, QVBoxLayout, QApplication
    from PyQt6.QtGui import QIcon, QCursor
    from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer, QPoint
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False


_active_toasts = set()
ALERT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "alert_notifier_layout.json")
_ALERT_CONFIG_LOCK = threading.Lock()
_has_loaded_screen_config = False

# 全局内存开关缓存
_GLOBAL_VOICE_ENABLED = True
_GLOBAL_TOAST_ENABLED = True

def get_screen_dpi_scale(screen: Optional[Any] = None) -> float:
    """获取指定显示器的真实 DPI 缩放比例 (以标准 96 DPI 为基准 1.0)"""
    if not HAS_PYQT:
        return 1.0
    if not screen:
        screen = QApplication.primaryScreen()
    if not screen:
        return 1.0
    try:
        dpi = screen.logicalDotsPerInch()
        scale = max(0.8, min(3.0, dpi / 96.0))
        return scale
    except Exception:
        return 1.0


def load_toast_screen_config():
    """从本地配置文件安全加载 Toast 显示器、坐标配置与语音/弹窗全局开关，并执行多屏幕物理级自修复与自愈校验"""
    global _has_loaded_screen_config, _GLOBAL_VOICE_ENABLED, _GLOBAL_TOAST_ENABLED
    _has_loaded_screen_config = True
    if not HAS_PYQT:
        return
    custom_pos = None
    target_screen_index = None
    try:
        if os.path.exists(ALERT_CONFIG_FILE):
            with _ALERT_CONFIG_LOCK:
                with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    target_screen_index = data.get("target_screen_index", None)
                    pos_data = data.get("custom_pos", None)
                    if isinstance(pos_data, (list, tuple)) and len(pos_data) == 2:
                        custom_pos = (int(pos_data[0]), int(pos_data[1]))
                    _GLOBAL_VOICE_ENABLED = bool(data.get("voice_enabled", True))
                    _GLOBAL_TOAST_ENABLED = bool(data.get("toast_enabled", True))
    except Exception as e:
        logger.debug(f"Load toast config exception: {e}")

    # ── 物理级多屏幕自修复 (Self-Healing Fallback) ──
    try:
        screens = QApplication.screens() if HAS_PYQT and QApplication.instance() else []
        if screens:
            # 1. 屏幕索引失效自修复 (如拔掉副屏后)
            if target_screen_index is not None:
                if not (0 <= target_screen_index < len(screens)):
                    logger.warning(f"⚠️ [ALERT_SCREEN_HEAL] 检测到保存的显示器索引 [{target_screen_index}] 已失效(当前仅有 {len(screens)} 块物理屏幕)，自动自愈复位至主屏幕!")
                    target_screen_index = None
                    save_toast_screen_config(target_screen_index=None, custom_pos=None)

            # 2. 坐标越界与盲区自修复 (如副屏断开或分辨率缩小变异)
            if custom_pos is not None:
                pt = QPoint(custom_pos[0], custom_pos[1])
                is_valid_point = False
                for scr in screens:
                    # 检查点是否在任何一个物理屏幕的可视几何区域内 (给予 30px 外围容错)
                    if scr.geometry().adjusted(-30, -30, 30, 30).contains(pt):
                        is_valid_point = True
                        break
                if not is_valid_point:
                    logger.warning(f"⚠️ [ALERT_SCREEN_HEAL] 检测到持久化坐标 {custom_pos} 落在无效/已断开的屏幕盲区中，自动自愈复位到当前屏幕可视区域!")
                    custom_pos = None
                    save_toast_screen_config(target_screen_index=target_screen_index, custom_pos=None)
    except Exception as e_heal:
        logger.debug(f"Toast screen self-healing check error: {e_heal}")

    InAppToastWidget._target_screen_index = target_screen_index
    InAppToastWidget._custom_pos = custom_pos


_UNSET_VAL = object()

def save_toast_screen_config(target_screen_index: Any = _UNSET_VAL, custom_pos: Any = _UNSET_VAL,
                            voice_enabled: Optional[bool] = None, toast_enabled: Optional[bool] = None):
    """原子写盘持久化保存 Toast 显示器偏好、自定义拖拽坐标与全局语音/弹窗开关到 JSON 文件"""
    global _GLOBAL_VOICE_ENABLED, _GLOBAL_TOAST_ENABLED
    try:
        os.makedirs(os.path.dirname(ALERT_CONFIG_FILE), exist_ok=True)
        # 先读取已有配置保持合并
        existing = {}
        if os.path.exists(ALERT_CONFIG_FILE):
            try:
                with _ALERT_CONFIG_LOCK:
                    with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f)
            except Exception:
                existing = {}

        if target_screen_index is not _UNSET_VAL:
            existing["target_screen_index"] = target_screen_index
        elif "target_screen_index" not in existing:
            existing["target_screen_index"] = None

        if custom_pos is not _UNSET_VAL:
            existing["custom_pos"] = list(custom_pos) if custom_pos else None
        elif "custom_pos" not in existing:
            existing["custom_pos"] = None

        if voice_enabled is not None:
            existing["voice_enabled"] = bool(voice_enabled)
            _GLOBAL_VOICE_ENABLED = bool(voice_enabled)
        elif "voice_enabled" not in existing:
            existing["voice_enabled"] = _GLOBAL_VOICE_ENABLED

        if toast_enabled is not None:
            existing["toast_enabled"] = bool(toast_enabled)
            _GLOBAL_TOAST_ENABLED = bool(toast_enabled)
        elif "toast_enabled" not in existing:
            existing["toast_enabled"] = _GLOBAL_TOAST_ENABLED

        existing["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        with _ALERT_CONFIG_LOCK:
            with open(ALERT_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 [TOAST_CONFIG] 通知屏幕与开关配置已原子持久化落盘: 显示器索引={existing.get('target_screen_index')}, 语音={existing.get('voice_enabled')}, 弹窗={existing.get('toast_enabled')}")
    except Exception as e:
        logger.warning(f"Save toast config failed: {e}")


def activate_and_locate_target_window(parent: Optional[Any], code: str = "", reason: str = ""):
    """物理级唤醒、还原、展开并置顶目标通知窗口，并在其中高亮定位股票标的并触发联动"""
    if not HAS_PYQT:
        return
    
    app = QApplication.instance()
    target_p = parent

    # 1. 如果没有 parent 或已被 C++ 销毁，尝试在活跃顶层窗口中寻找
    if target_p is not None:
        try:
            from PyQt6.sip import isdeleted
            if isdeleted(target_p):
                target_p = None
        except Exception:
            pass

    if target_p is None and app:
        active_w = app.activeWindow()
        if active_w and getattr(active_w, '__class__', None).__name__ != "InAppToastWidget":
            target_p = active_w
        else:
            for w in app.topLevelWidgets():
                if w.isVisible() and getattr(w, '__class__', None).__name__ in ("DailyLimitUpDialog", "HotSectorLeaderboard", "MultiPeriodDialog", "ATSMainWindow"):
                    target_p = w
                    break

    # 2. 物理级唤醒与置顶展示
    if target_p is not None:
        try:
            # 最小化还原
            if hasattr(target_p, 'isMinimized') and target_p.isMinimized():
                target_p.showNormal()
            
            # 隐藏恢复
            if hasattr(target_p, 'isHidden') and target_p.isHidden():
                target_p.show()
            elif hasattr(target_p, 'isVisible') and not target_p.isVisible():
                target_p.show()

            # 边缘磁吸收起 (Magnetic Snap Auto Hide) 展开
            if getattr(target_p, 'is_hidden_state', False):
                if hasattr(target_p, '_expand_window'):
                    target_p._expand_window()
                elif hasattr(target_p, '_expand_from_snap'):
                    target_p._expand_from_snap()
                else:
                    target_p.showNormal()

            target_p.show()
            target_p.raise_()
            target_p.activateWindow()
        except Exception as e_w:
            logger.debug(f"Activate target window error: {e_w}")

    # 3. 股票联动与定位
    if code:
        code_str = str(code).strip().zfill(6)
        p_name = getattr(target_p, '__class__', None).__name__ if target_p else "None"
        logger.info(f"🎯 [TOAST_LINK] 直达唤醒来源窗口 [{p_name}] 并高亮定位标的: {code_str}")

        if target_p is not None:
            # 优先 locate_stock_in_table (DailyLimitUpDialog, HotSectorLeaderboard, MultiPeriodDialog)
            if hasattr(target_p, 'locate_stock_in_table'):
                try:
                    target_p.locate_stock_in_table(code_str, auto_popup=True, reason=reason)
                except TypeError:
                    try:
                        target_p.locate_stock_in_table(code_str, auto_popup=True)
                    except Exception as e_loc:
                        logger.warning(f"locate_stock_in_table error: {e_loc}")
                except Exception as e_loc:
                    logger.warning(f"locate_stock_in_table error: {e_loc}")

            # ATS 主窗口使用 locate_stock_in_tree
            elif hasattr(target_p, 'locate_stock_in_tree'):
                try:
                    target_p.locate_stock_in_tree(code_str, auto_popup=True)
                except Exception as e_loc:
                    logger.warning(f"locate_stock_in_tree error: {e_loc}")

            # 兜底广播联动
            elif hasattr(target_p, 'link_stock'):
                try:
                    target_p.link_stock(code_str)
                except Exception:
                    pass


class InAppToastWidget(QFrame if HAS_PYQT else object):
    """应用内半透明高分屏自适应 Toast 卡片 (支持不同 DPI/分辨率自适应、自由跨屏拖拽与点击联动)"""
    _custom_pos: Optional[Tuple[int, int]] = None  # 跨屏幕自定义持久化坐标 (全局记忆)
    _target_screen_index: Optional[int] = None

    def __init__(self, title, message, code="", parent=None):
        if not HAS_PYQT:
            return
        super().__init__(None) # 使用独立 Tool 浮窗，全屏幕弹出，支持自由跨屏拖动
        
        # 确保首次弹窗时已加载持久化配置与完成自愈检查
        global _has_loaded_screen_config
        if not _has_loaded_screen_config:
            load_toast_screen_config()
        self.code = str(code).strip()
        self.target_parent = parent
        self.title_text = title
        self.message_text = message
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 拖拽状态与当前屏幕
        self._drag_pos = None
        self._press_pos = None
        self._is_dragging = False
        self._current_screen = None

        tip_str = "💡 点击即可在列表中高亮定位并联动分析\n🖱️ 按住鼠标左键可自由拖动至副屏/任意屏幕记忆通知位置"
        if self.code:
            tip_str = f"💡 点击即可在列表中自动高亮定位 [{self.code}] 并联动分析\n🖱️ 按住鼠标左键可自由拖动至副屏/任意屏幕记忆通知位置"
        self.setToolTip(tip_str)
        
        # 强引用注册，防止 Python 垃圾回收器 (GC) 提前销毁弹窗
        _active_toasts.add(self)

        # ── 1. 确定目标显示器 ──
        target_screen = None
        # 1.1 检查用户是否自定义了拖拽坐标所在屏幕
        if InAppToastWidget._custom_pos is not None:
            cx, cy = InAppToastWidget._custom_pos
            from PyQt6.QtCore import QPoint
            scr = QApplication.screenAt(QPoint(cx, cy))
            if scr:
                target_screen = scr

        # 1.2 检查托盘右键菜单指定的显示器
        if not target_screen and getattr(InAppToastWidget, '_target_screen_index', None) is not None:
            screens = QApplication.screens()
            tgt_idx = InAppToastWidget._target_screen_index
            if 0 <= tgt_idx < len(screens):
                target_screen = screens[tgt_idx]

        # 1.3 检查父窗口所在屏幕
        if not target_screen:
            if parent and hasattr(parent, 'screen') and parent.screen():
                target_screen = parent.screen()
            elif parent and hasattr(parent, 'window') and parent.window() and parent.window().screen():
                target_screen = parent.window().screen()

        if not target_screen and HAS_PYQT:
            try:
                from PyQt6.QtGui import QCursor
                target_screen = QApplication.screenAt(QCursor.pos())
            except Exception:
                pass

        if not target_screen:
            target_screen = QApplication.primaryScreen()

        self._current_screen = target_screen

        # ── 2. 根据目标显示器的 DPI 与分辨率动态自适应尺寸与字号 ──
        scale = get_screen_dpi_scale(target_screen)
        self._current_scale = scale

        base_w = 260
        base_h = 94
        self.card_w = int(base_w * scale)
        self.card_h = int(base_h * scale)
        title_f_size = max(11, int(12 * scale))
        msg_f_size = max(9, int(10 * scale))
        pad_lr = max(8, int(11 * scale))
        pad_tb = max(6, int(9 * scale))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(pad_lr, pad_tb, pad_lr, pad_tb)
        self.layout.setSpacing(max(3, int(4 * scale)))
        
        self.lbl_t = QLabel(title, self)
        self.lbl_t.setStyleSheet(f"color: #ffca28; font-weight: bold; font-size: {title_f_size}px; background: transparent;")
        self.lbl_m = QLabel(message, self)
        self.lbl_m.setWordWrap(True)
        self.lbl_m.setStyleSheet(f"color: #e2e8f0; font-size: {msg_f_size}px; background: transparent; line-height: 1.35;")
        
        self.layout.addWidget(self.lbl_t)
        self.layout.addWidget(self.lbl_m)
        
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
        
        self.resize(self.card_w, self.card_h)
        
        # ── 3. 初始位置计算 ──
        if InAppToastWidget._custom_pos is not None:
            cx, cy = InAppToastWidget._custom_pos
            self.move(cx, cy)
        else:
            if target_screen:
                try:
                    s_geom = target_screen.availableGeometry()
                    pos_x = s_geom.right() - self.card_w - int(15 * scale)
                    pos_y = s_geom.bottom() - self.card_h - int(15 * scale)
                    self.move(max(s_geom.left() + 10, pos_x), max(s_geom.top() + 10, pos_y))
                except Exception:
                    self.move(100, 100)
            else:
                self.move(100, 100)

        self.show()
        self.raise_()

    def _adapt_to_screen_dpi(self, new_screen):
        """跨屏幕拖拽时动态根据新屏幕 DPI 自适应调整尺寸与字号"""
        if not new_screen or new_screen == self._current_screen:
            return
        self._current_screen = new_screen
        scale = get_screen_dpi_scale(new_screen)
        if abs(scale - self._current_scale) < 0.05:
            return
        
        self._current_scale = scale
        base_w = 260
        base_h = 94
        self.card_w = int(base_w * scale)
        self.card_h = int(base_h * scale)
        title_f_size = max(11, int(12 * scale))
        msg_f_size = max(9, int(10 * scale))
        pad_lr = max(8, int(11 * scale))
        pad_tb = max(6, int(9 * scale))

        self.layout.setContentsMargins(pad_lr, pad_tb, pad_lr, pad_tb)
        self.layout.setSpacing(max(3, int(4 * scale)))
        self.lbl_t.setStyleSheet(f"color: #ffca28; font-weight: bold; font-size: {title_f_size}px; background: transparent;")
        self.lbl_m.setStyleSheet(f"color: #e2e8f0; font-size: {msg_f_size}px; background: transparent; line-height: 1.35;")
        self.resize(self.card_w, self.card_h)

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
                
                # 动态检测跨屏 DPI 适配
                try:
                    scr = QApplication.screenAt(curr_pos)
                    if scr:
                        self._adapt_to_screen_dpi(scr)
                except Exception:
                    pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                # 用户完成了跨屏幕拖拽：记录自定义坐标并原子落盘持久化，后续所有通知均在此时拖动的新屏幕位置弹出！
                InAppToastWidget._custom_pos = (self.x(), self.y())
                save_toast_screen_config(InAppToastWidget._target_screen_index, InAppToastWidget._custom_pos)
                logger.info(f"📍 [TOAST_DRAG] 用户已将通知窗口拖动至新屏幕坐标: {InAppToastWidget._custom_pos} (已持久化)，后续通知将在此屏幕展示")
                self._is_dragging = False
                self._drag_pos = None
                self._press_pos = None
                return
            
            # 纯单击触发直达唤醒并定位来源窗口与股票
            self._is_dragging = False
            self._drag_pos = None
            self._press_pos = None

            parent = getattr(self, 'target_parent', None) or self.parent()
            activate_and_locate_target_window(parent, self.code, getattr(self, 'message_text', ''))
            self.close()
        super().mouseReleaseEvent(event)


class AlertNotifier(QObject if HAS_PYQT else object):
    """黄金特异信号桌面弹窗与语音通知器 (支持跨线程安全投递、串行轮播队列与全局开关)"""
    
    _instance = None
    if HAS_PYQT:
        sig_notify_request = pyqtSignal(dict)
    
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
        load_toast_screen_config()
        
        # 跨线程安全投递绑定
        if HAS_PYQT:
            try:
                self.sig_notify_request.connect(self._enqueue_notification_item)
            except Exception as e_sig:
                logger.debug(f"Signal connect error: {e_sig}")

        self._init_tray()

    def is_voice_enabled(self) -> bool:
        """获取当前全局语音播报开关状态"""
        global _GLOBAL_VOICE_ENABLED
        return _GLOBAL_VOICE_ENABLED

    def set_voice_enabled(self, enabled: bool):
        """设置并原子持久化全局语音播报开关"""
        global _GLOBAL_VOICE_ENABLED
        _GLOBAL_VOICE_ENABLED = bool(enabled)
        save_toast_screen_config(voice_enabled=bool(enabled))
        logger.info(f"🔊 [ALERT_NOTIFIER] 全局语音播报已{'开启' if enabled else '关闭并静音'}")

    def is_toast_enabled(self) -> bool:
        """获取当前全局桌面弹窗开关状态"""
        global _GLOBAL_TOAST_ENABLED
        return _GLOBAL_TOAST_ENABLED

    def set_toast_enabled(self, enabled: bool):
        """设置并原子持久化全局桌面弹窗开关"""
        global _GLOBAL_TOAST_ENABLED
        _GLOBAL_TOAST_ENABLED = bool(enabled)
        save_toast_screen_config(toast_enabled=bool(enabled))
        logger.info(f"💬 [ALERT_NOTIFIER] 全局桌面弹窗通知已{'开启' if enabled else '关闭'}")

    def clear_queue(self):
        """立即一键静音并清空所有排队积压的通知与当前弹窗"""
        self._notify_queue.clear()
        if self._current_toast:
            try:
                self._current_toast.close()
            except Exception:
                pass
            self._current_toast = None
        self._is_busy = False
        logger.info("🛑 [ALERT_NOTIFIER] 已一键清空全部待播报通知队列与当前弹窗")

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
        """构建托盘图标右键菜单 (支持语音开关、弹窗开关、一键静音、多显示器切换、位置复位、测试通知等)"""
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

        # 1. 语音播报总开关 (勾选状态与持久化同步)
        self.act_voice_toggle = self.tray_menu.addAction("🔊 开启语音播报")
        self.act_voice_toggle.setCheckable(True)
        self.act_voice_toggle.setChecked(self.is_voice_enabled())
        self.act_voice_toggle.triggered.connect(lambda checked: self.set_voice_enabled(checked))

        # 2. 桌面弹窗总开关 (勾选状态与持久化同步)
        self.act_toast_toggle = self.tray_menu.addAction("💬 开启桌面弹窗通知")
        self.act_toast_toggle.setCheckable(True)
        self.act_toast_toggle.setChecked(self.is_toast_enabled())
        self.act_toast_toggle.triggered.connect(lambda checked: self.set_toast_enabled(checked))

        # 3. 立即静音并清空队列
        act_clear_queue = self.tray_menu.addAction("🛑 立即静音并清空播报队列")
        act_clear_queue.triggered.connect(self.clear_queue)

        self.tray_menu.addSeparator()

        # 4. 显示器设置子菜单
        self.menu_displays = self.tray_menu.addMenu("🖥️ 预警通知显示器设置")
        self.tray_menu.aboutToShow.connect(self._refresh_tray_menu_state)

        # 5. 重置弹窗位置
        act_reset_pos = self.tray_menu.addAction("🎯 重置通知位置 (默认右下角)")
        act_reset_pos.triggered.connect(self._reset_toast_position)

        self.tray_menu.addSeparator()

        # 6. 发送测试预警通知
        act_test_notify = self.tray_menu.addAction("📢 发送测试特异预警通知")
        act_test_notify.triggered.connect(self._send_test_notification)

        self.tray_menu.addSeparator()

        # 7. 退出程序
        act_quit = self.tray_menu.addAction("🚪 退出系统")
        act_quit.triggered.connect(self._on_tray_quit_clicked)

        self.tray_icon.setContextMenu(self.tray_menu)

    def _refresh_tray_menu_state(self):
        """托盘菜单即将弹出时，动态刷新勾选状态与显示器列表"""
        if hasattr(self, 'act_voice_toggle'):
            self.act_voice_toggle.setChecked(self.is_voice_enabled())
        if hasattr(self, 'act_toast_toggle'):
            self.act_toast_toggle.setChecked(self.is_toast_enabled())
        self._refresh_displays_menu()

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
            save_toast_screen_config(screen_index, None)
            scr = screens[screen_index]
            geom = scr.geometry()
            logger.info(f"🖥️ [TRAY_MENU] 用户已通过任务栏右键菜单切换预警通知显示器为: 显示器 {screen_index + 1} ({geom.width()}x{geom.height()}) [已持久化]")
            
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
        save_toast_screen_config(InAppToastWidget._target_screen_index, None)
        logger.info("🎯 [TRAY_MENU] 已重置通知弹窗位置为默认右下角 [已持久化]")
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
            score=94.0,
            is_force=True
        )

    def _on_tray_quit_clicked(self):
        """托盘菜单退出"""
        app = QApplication.instance()
        if app:
            app.quit()

    def _on_tray_message_clicked(self):
        """点击 Windows 系统托盘 Toast 消息弹窗，自动直达唤醒来源窗口并高亮联动标的"""
        if not self._last_notified_code:
            return
        code = self._last_notified_code
        logger.info(f"🎯 [TRAY_CLICK] 用户点击 Windows 托盘 Toast 弹窗，直达唤醒并定位股票: {code}")
        activate_and_locate_target_window(self._last_parent, code, "")

    def notify(self, title, message, code="", score=90.0, level="GOLD", parent=None):
        """通用通知方法别名，无缝兼容多周期等系统调用"""
        name = str(title).strip()
        reason = str(message).strip()
        return self.notify_special_signal(code=code, name=name, reason=reason, score=score, parent=parent)

    def notify_special_signal(self, code, name, reason, score=90.0, win_rate="85.0%", parent=None, is_force=False):
        """推送信信号弹窗与语音 (具备跨线程投递、全自动限频与去重保护)
        
        Args:
            code: 股票代码
            name: 股票名称
            reason: 买卖逻辑理由 (如: 自动通道Fib50企稳|2D/3D阶梯抬升|板块大哥带队)
            score: 特异打分
            win_rate: 历史有效胜率
            parent: 主界面句柄 (传入后开启应用内高亮 Toast 提示并支持点击直达唤醒)
            is_force: 是否强制弹窗/测试 (跳过限频和去重)
        """
        now = time.time()
        code_str = str(code).strip().zfill(6)
        reason_str = str(reason).strip()
        # 真正的高优先级信号豁免 (👑双加速顶级信号/通达信实盘信号/实盘演示/强制测试/评分>=95.0)
        is_priority_signal = is_force or ("双加速" in reason_str) or ("通达信" in reason_str) or ("实盘演示" in reason_str) or (score >= 95.0)

        # 0. 特异打分门槛过滤：小于 78.0 分且非强制/通达信信号的微弱异动静默过滤
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

        # 限频保护：非强制/通达信实盘信号执行严格的 10 秒全局限频与 300 秒(5分钟)单股冷却
        if not is_priority_signal and not is_force:
            # 1. 普通信号全局限频：10 秒内最多推送 1 条
            if (now - self._last_global_ts) < 10.0:
                return

            # 2. 普通信号单股限频：同一股票 5 分钟 (300s) 内不重复推送
            last_ts = self._last_alert_ts.get(code_str, 0.0)
            if (now - last_ts) < 300.0:
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

        # 跨线程安全检测：如果在 Qt 子工作线程中，安全投递至主事件循环处理
        if HAS_PYQT and QApplication.instance():
            app = QApplication.instance()
            from PyQt6.QtCore import QThread
            if QThread.currentThread() != app.thread():
                self.sig_notify_request.emit(item)
                return

        self._enqueue_notification_item(item)

    def _enqueue_notification_item(self, item: dict):
        """在 Qt 主线程中安全压入通知队列并启动串行轮播处理"""
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

        # 1. 弹出右下角 Toast 卡片 (受 is_toast_enabled 控制)
        toast_success = False
        if self.is_toast_enabled() and HAS_PYQT and QApplication.instance():
            try:
                target_p = parent if parent else QApplication.activeWindow()
                self._current_toast = InAppToastWidget(title, message, code=code_str, parent=target_p)
                toast_success = True
            except Exception as e_toast:
                logger.warning(f"InAppToastWidget failed: {e_toast}")

        # 2. 仅在无 GUI 界面极特殊环境下 Fallback 到系统托盘消息
        if self.is_toast_enabled() and not toast_success and self.tray_icon and HAS_PYQT:
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

        # 3. 触发语音播报 (受 is_voice_enabled 控制)
        if "双加速" in reason:
            voice_text = f"双加速买点，{name}，跳空光脚加速"
        elif "光脚加速" in reason:
            voice_text = f"光脚加速买点，{name}，开盘即最低"
        elif "缺口加速" in reason:
            voice_text = f"缺口加速买点，{name}，跳空高开未补缺"
        else:
            voice_text = f"特异买点 {name}，{reason}"
        if self.is_voice_enabled():
            self._speak_text(voice_text)
        else:
            logger.debug(f"🔇 [ALERT_NOTIFY] 全局语音已关闭，跳过发声: {voice_text}")

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
        if not text or not self.is_voice_enabled():
            return

        def _worker():
            if not self.is_voice_enabled():
                return
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

