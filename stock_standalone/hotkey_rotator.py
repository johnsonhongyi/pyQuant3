# -*- coding: utf-8 -*-
"""
独立的高性能全局热键监听与视窗轮换切换进程 (HotkeyRotatorProcess)
完全独立于 Tkinter 的 GIL，在任何时候实现零卡顿、瞬时响应。
"""
import os
import sys
import time
import json
import socket
import threading
import ctypes
from ctypes import wintypes
import win32con
import win32file
import traceback

try:
    from PyQt6 import QtWidgets, QtCore, QtGui, sip
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QLabel, QFrame, QWidget, QGridLayout, QPushButton, QApplication
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
except ImportError as e:
    print(f"[HotkeyRotator] Failed to import PyQt6: {e}")
    sys.exit(1)

# 全局异常处理器，防御 unhandled exception 导致 PyQt 闪退
def global_excepthook(exctype, value, tb):
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(f"🚨 [Rotator Unhandled Exception]: {err_msg}")
    try:
        send_to_tk_pipe({"cmd": "STATUS_MSG", "msg": f"🚨 快捷键进程发生异常: {str(value)[:60]}"})
    except:
        pass

sys.excepthook = global_excepthook

# 全局变量
_app_instance = None
_active_dialog = None
PIPE_NAME_TK = r"\\.\pipe\instock_tk_pipe"

def send_to_tk_pipe(msg_dict):
    """通过命名管道发送指令给 Tk 进程 (无阻塞，短连接)"""
    try:
        handle = win32file.CreateFile(
            PIPE_NAME_TK,
            win32file.GENERIC_WRITE,
            0, None,
            win32file.OPEN_EXISTING,
            0, None
        )
        payload = json.dumps(msg_dict).encode("utf-8")
        win32file.WriteFile(handle, payload)
        win32file.CloseHandle(handle)
        return True
    except Exception as e:
        # 忽略 Tk 暂未就绪或已关闭的情况
        return False

def force_focus_hwnd(hwnd):
    """100% 强力穿透并聚焦置顶窗口 (AttachThreadInput 底层穿透技术)"""
    if not hwnd:
        return
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    
    # 🧬 [加固] 强力判断 HWND 是否仍然是有效的窗口句柄，防止 ctypes Access Violation 底层闪退
    try:
        if not user32.IsWindow(hwnd):
            print(f"[Rotator] HWND {hwnd} is no longer a valid window.")
            return
    except Exception as e:
        print(f"[Rotator] IsWindow check failed: {e}")
        return

    fore_hwnd = user32.GetForegroundWindow()
    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
    current_thread = kernel32.GetCurrentThreadId()
    
    attached = False
    if fore_thread and fore_thread != current_thread:
        try:
            attached = bool(user32.AttachThreadInput(current_thread, fore_thread, True))
        except Exception:
            pass
        
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetFocus(hwnd)
    except Exception as e:
        print(f"[Rotator] SetFocus error for {hwnd}: {e}")
    finally:
        if attached:
            try:
                user32.AttachThreadInput(current_thread, fore_thread, False)
            except Exception:
                pass


class WindowRotatorDialog(QDialog):
    def __init__(self, hwnds, name_map, initial_dir, hk_desc):
        super().__init__(None)
        self.hwnds = hwnds
        self.name_map = name_map
        self.hk_desc = hk_desc
        
        # 分类核心窗口和瓷贴窗口
        self.core_hwnds = []
        self.tile_hwnds = []
        for h in self.hwnds:
            raw_name = self.name_map.get(str(h), self.name_map.get(h, ""))
            if "概念前10监控" in raw_name or "MonitorWindow_" in raw_name:
                self.tile_hwnds.append(h)
            else:
                self.core_hwnds.append(h)
        
        self.last_action_time = time.time()
        self.selection_changed = False  # 是否已修改过选中项
        self.has_interacted = False     # 是否有任何鼠标或按键交互
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 高对比度极客暗黑风 QSS 样式设计
        self.setStyleSheet("""
            QDialog {
                background-color: transparent;
            }
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #1c1d30;
                color: #ffffff;
                border-radius: 6px;
                padding: 10px;
                margin-bottom: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                color: #39ff14;
                border: 1.5px solid #00f0ff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title = QLabel("🔄 交易视窗全局轮询切换器", self)
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold; margin-bottom: 8px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        self.list_widget = QListWidget(self)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.list_widget)
        
        # 灌入核心窗口
        for h in self.core_hwnds:
            name = self.name_map.get(str(h), self.name_map.get(h, "📺 K线/分时可视化监控终端 (Visualizer)"))
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, h)
            self.list_widget.addItem(item)
            
        # 灌入瓷贴小方块
        self.tiles_frame = None
        self.tile_buttons = {}  # hwnd -> QPushButton
        
        if self.tile_hwnds:
            self.tiles_frame = QFrame(self)
            self.tiles_frame.setStyleSheet("""
                QFrame {
                    background-color: #171828;
                    border: 1px solid #2d2e42;
                    border-radius: 8px;
                }
            """)
            tiles_layout = QVBoxLayout(self.tiles_frame)
            tiles_layout.setContentsMargins(8, 8, 8, 8)
            
            t_title = QLabel("🔍 概念前10放量监控 (瓷贴)", self.tiles_frame)
            t_title.setStyleSheet("color: #8b92b6; font-size: 10px; font-weight: bold; border: none; background: transparent;")
            tiles_layout.addWidget(t_title)
            
            grid_widget = QWidget(self.tiles_frame)
            grid_widget.setStyleSheet("border: none; background: transparent;")
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 4, 0, 0)
            grid_layout.setSpacing(6)
            
            for idx, h in enumerate(self.tile_hwnds):
                raw_name = self.name_map.get(str(h), self.name_map.get(h, ""))
                clean_name = raw_name.replace("🔍 概念前10监控 (", "").replace(")", "")
                if "_" in clean_name:
                    clean_name = clean_name.split("_")[0]
                if len(clean_name) > 6:
                    clean_name = clean_name[:5] + ".."
                    
                btn = QPushButton(clean_name, grid_widget)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setStyleSheet(self._get_tile_style(selected=False))
                btn.clicked.connect(lambda checked, hwnd=h: self.select_hwnd_and_close(hwnd))
                
                self.tile_buttons[h] = btn
                row = idx // 3
                col = idx % 3
                grid_layout.addWidget(btn, row, col)
                
            tiles_layout.addWidget(grid_widget)
            layout.addWidget(self.tiles_frame)
            
        # 确定初始高亮索引：当前激活窗口顺次往后切
        current_fore = ctypes.windll.user32.GetForegroundWindow()
        if current_fore in self.hwnds:
            curr_idx = self.hwnds.index(current_fore)
            self.curr_idx = (curr_idx + initial_dir) % len(self.hwnds)
        else:
            self.curr_idx = 0
            
        self.apply_highlight_to_ui()
        
        # 底部操作指南
        help_lbl = QLabel(f"💡 连按 [{self.hk_desc}] 轮选 | 回车/点击 确认切换 | 5秒无操作自动关闭", self)
        help_lbl.setStyleSheet("color: #8b92b6; font-size: 11px; font-weight: bold; margin-top: 6px;")
        help_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(help_lbl)
        
        # 屏幕居中尺寸适配
        list_height = len(self.core_hwnds) * 45
        tile_rows = (len(self.tile_hwnds) + 2) // 3
        tiles_height = 40 + tile_rows * 36 if self.tile_hwnds else 0
        self.resize(380, min(120 + list_height + tiles_height, 600))
        self.center_on_screen()
        
        # 注册全局事件过滤器
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        
        # 启动检测器: 30ms 高频轮询 Alt 键状态 + 5s 无操作超时兜底
        self.detect_timer = QTimer(self)
        self.detect_timer.timeout.connect(self.check_alt_release)
        self.detect_timer.start(30)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#111224")))
        painter.setPen(QPen(QColor("#00f0ff"), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def center_on_screen(self):
        screen = self.screen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.width()) // 2
            y = (geom.height() - self.height()) // 2
            self.move(x, y)

    def _get_tile_style(self, selected=False):
        if selected:
            return """
                QPushButton {
                    background-color: #1e3a8a;
                    color: #39ff14;
                    border: 1.5px solid #00f0ff;
                    border-radius: 4px;
                    padding: 5px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #1c1d30;
                    color: #ffffff;
                    border: 1px solid #33344a;
                    border-radius: 4px;
                    padding: 5px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """

    def select_hwnd_and_close(self, hwnd):
        if hwnd in self.hwnds:
            self.curr_idx = self.hwnds.index(hwnd)
        if hasattr(self, 'detect_timer') and self.detect_timer.isActive():
            self.detect_timer.stop()
        self.trigger_switch_and_close()

    def apply_highlight_to_ui(self):
        if not self.hwnds or self.curr_idx < 0 or self.curr_idx >= len(self.hwnds):
            return
        target_hwnd = self.hwnds[self.curr_idx]
        
        if target_hwnd in self.core_hwnds:
            self.list_widget.blockSignals(True)
            core_idx = self.core_hwnds.index(target_hwnd)
            self.list_widget.setCurrentRow(core_idx)
            self.list_widget.blockSignals(False)
            
            for btn in self.tile_buttons.values():
                btn.setStyleSheet(self._get_tile_style(selected=False))
        else:
            self.list_widget.blockSignals(True)
            self.list_widget.clearSelection()
            self.list_widget.setCurrentRow(-1)
            self.list_widget.blockSignals(False)
            
            for h, btn in self.tile_buttons.items():
                btn.setStyleSheet(self._get_tile_style(selected=(h == target_hwnd)))
            
    def rotate_highlight(self, direction, is_hotkey=False):
        if not self.hwnds:
            return
        self.last_action_time = time.time()
        self.has_interacted = True
        if is_hotkey:
            self.selection_changed = True
        self.curr_idx = (self.curr_idx + direction) % len(self.hwnds)
        self.apply_highlight_to_ui()
        
    def on_item_clicked(self, item):
        self.last_action_time = time.time()
        hwnd = item.data(Qt.ItemDataRole.UserRole)
        if hwnd and hwnd in self.hwnds:
            self.curr_idx = self.hwnds.index(hwnd)
        if hasattr(self, 'detect_timer') and self.detect_timer.isActive():
            self.detect_timer.stop()
        self.trigger_switch_and_close()

    def eventFilter(self, watched, event):
        is_our_window = False
        if watched == self:
            is_our_window = True
        elif hasattr(watched, 'window') and watched.window() == self:
            is_our_window = True
            
        if not is_our_window:
            return super().eventFilter(watched, event)
        
        evt_type = event.type()
        if hasattr(evt_type, 'value'):
            evt_type = evt_type.value
            
        if evt_type in [
            QtCore.QEvent.Type.KeyPress.value,
            QtCore.QEvent.Type.KeyRelease.value,
            QtCore.QEvent.Type.MouseButtonPress.value,
            QtCore.QEvent.Type.MouseButtonRelease.value,
            QtCore.QEvent.Type.MouseMove.value,
            QtCore.QEvent.Type.Wheel.value
        ]:
            self.last_action_time = time.time()
            self.has_interacted = True
        
        if evt_type == QtCore.QEvent.Type.KeyPress.value:
            evt_key = event.key()
            if hasattr(evt_key, 'value'):
                evt_key = evt_key.value
                
            if evt_key == Qt.Key.Key_Space.value:
                if hasattr(self, 'detect_timer') and self.detect_timer.isActive():
                    self.detect_timer.stop()
                self.trigger_switch_and_close()
                return True
            elif evt_key == Qt.Key.Key_Down.value:
                self.rotate_highlight(1, is_hotkey=False)
                return True
            elif evt_key == Qt.Key.Key_Up.value:
                self.rotate_highlight(-1, is_hotkey=False)
                return True
        
        if evt_type == QtCore.QEvent.Type.Wheel.value:
            delta = event.angleDelta().y()
            if delta > 0:
                self.rotate_highlight(-1, is_hotkey=False)
            elif delta < 0:
                self.rotate_highlight(1, is_hotkey=False)
            return True
            
        return super().eventFilter(watched, event)

    def check_alt_release(self):
        timeout_limit = 5.0 if self.has_interacted else 1.5
        if time.time() - self.last_action_time > timeout_limit:
            self.detect_timer.stop()
            self.trigger_switch_and_close()
            return
        
        state = ctypes.windll.user32.GetAsyncKeyState(0x12)  # VK_MENU
        alt_released = not (state & 0x8000)
        
        if alt_released and self.selection_changed:
            self.detect_timer.stop()
            self.trigger_switch_and_close()

    def trigger_switch_and_close(self):
        # 加上重入保护，防止多次点击或热键触发重入导致底层 C++ 状态冲突闪退
        if getattr(self, "_is_switching", False):
            return
        self._is_switching = True
        
        try:
            if self.curr_idx >= 0 and self.curr_idx < len(self.hwnds):
                target_hwnd = self.hwnds[self.curr_idx]
                target_name = self.name_map.get(str(target_hwnd), self.name_map.get(target_hwnd, "未知窗口"))
                
                # 更新本地 MRU 列表
                global _app_instance
                if _app_instance and target_hwnd in _app_instance.mru_list:
                    try:
                        _app_instance.mru_list.remove(target_hwnd)
                    except ValueError:
                        pass
                if _app_instance:
                    _app_instance.mru_list.insert(0, target_hwnd)
                    
                # 强力置顶
                force_focus_hwnd(target_hwnd)
                
                # 异步发送聚焦通知到 Tk 进程以防双保险
                send_to_tk_pipe({"cmd": "FOCUS_HWND", "hwnd": target_hwnd})
                print(f"[Rotator] Switched focus to HWND {target_hwnd} [{target_name}]")
        except Exception as e:
            print(f"[Rotator] Error in trigger_switch_and_close: {e}")
        finally:
            try:
                self.close()
            except Exception:
                pass

    def keyPressEvent(self, event):
        self.last_action_time = time.time()
        self.has_interacted = True
        if event.key() == Qt.Key.Key_Down:
            self.rotate_highlight(1, is_hotkey=False)
        elif event.key() == Qt.Key.Key_Up:
            self.rotate_highlight(-1, is_hotkey=False)
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space]:
            self.detect_timer.stop()
            self.trigger_switch_and_close()
        elif event.key() == Qt.Key.Key_Escape:
            self.detect_timer.stop()
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, 'detect_timer') and self.detect_timer.isActive():
            self.detect_timer.stop()
        
        app = QApplication.instance()
        if app:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
                
        global _active_dialog
        _active_dialog = None
        super().closeEvent(event)


class WindowSyncServer(threading.Thread):
    """TCP Socket 服务端，接收来自 Tk 进程的窗口列表同步数据"""
    def __init__(self, data_signal):
        super().__init__(name="WindowSyncServerThread", daemon=True)
        self.data_signal = data_signal
        
    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 尝试多次绑定端口，防止旧进程刚退出时操作系统尚未释放端口
        bound = False
        for attempt in range(5):
            try:
                s.bind(('127.0.0.1', 26669))
                bound = True
                break
            except OSError as e:
                if attempt == 4:
                    err_msg = f"⚠️ 轮转同步端口26669被占用 ({e})，热键进程启动受限，请重启系统！"
                    print(f"[SyncServer] Bind failed after 5 attempts: {err_msg}")
                    send_to_tk_pipe({"cmd": "STATUS_MSG", "msg": err_msg})
                    s.close()
                    return
                time.sleep(0.5)
            
        try:
            s.listen(5)
            print("[SyncServer] Listening on 127.0.0.1:26669")
            while True:
                conn, addr = s.accept()
                try:
                    data_chunks = []
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data_chunks.append(chunk)
                    payload = b"".join(data_chunks).decode("utf-8")
                    if payload:
                        obj = json.loads(payload)
                        self.data_signal.emit(obj)
                except json.JSONDecodeError as je:
                    print(f"[SyncServer] JSON Decode Error: {je}")
                except Exception as e:
                    print(f"[SyncServer] Connection handler error: {e}")
                finally:
                    conn.close()
        except Exception as e:
            print(f"[SyncServer] Server crashed: {e}")
        finally:
            s.close()



class HotkeyListener(threading.Thread):
    """全局热键监听线程 (Win32 RegisterHotKey)"""
    def __init__(self, trigger_signal, log_level):
        super().__init__(name="HotkeyListenerThread", daemon=True)
        self.trigger_signal = trigger_signal
        self.stop_event = threading.Event()
        self.hotkey_id_base = 0xBF00
        self.fallback_active = False
        
        # 完美对齐 instock_MonitorTK 中的映射表
        self.hotkey_map = {
            0: (win32con.MOD_ALT, 0x42, "Alt+B"),  # B
            1: (win32con.MOD_ALT, 0x45, "Alt+E"),  # E
            2: (win32con.MOD_ALT, 0x53, "Alt+S"),  # S
            3: (win32con.MOD_ALT, 0x4B, "Alt+K"),  # K
            4: (win32con.MOD_ALT, 0x4C, "Alt+L"),  # L
            5: (win32con.MOD_ALT, 0x48, "Alt+H"),  # H
            6: (win32con.MOD_ALT, 0x56, "Alt+V"),  # V
            7: (win32con.MOD_ALT, 0x4D, "Alt+M"),  # M
            8: (win32con.MOD_ALT, 0x54, "Alt+T"),  # T
            9: (win32con.MOD_ALT, 0x52, "Alt+R"),  # R
            10: (win32con.MOD_ALT | win32con.MOD_SHIFT, 0x52, "Alt+Shift+R"),  # Shift+R
            11: (win32con.MOD_ALT, 0x4A, "Alt+J"),  # J
        }
        self.registered_ids = []

    def run(self):
        user32 = ctypes.windll.user32
        
        # 1. 注册热键
        for offset, (mod, vk, desc) in list(self.hotkey_map.items()):
            hk_id = self.hotkey_id_base + offset
            if user32.RegisterHotKey(None, hk_id, mod, vk):
                self.registered_ids.append(hk_id)
            else:
                # 针对 Alt+R / Alt+Shift+R 触发降级保护自愈
                if offset in [9, 10]:
                    fallback_vk = 0x51  # Q 键码
                    new_desc = "Alt+Q (已降级)" if offset == 9 else "Alt+Shift+Q (已降级)"
                    self.hotkey_map[offset] = (mod, fallback_vk, new_desc)
                    if user32.RegisterHotKey(None, hk_id, mod, fallback_vk):
                        self.registered_ids.append(hk_id)
                        self.fallback_active = True
                        send_to_tk_pipe({"cmd": "STATUS_MSG", "msg": "⚠️ Alt+R被占用，已降级为 Alt+Q 轮转窗口！"})
                    
        # 2. PeekMessage 消息循环
        msg = wintypes.MSG()
        try:
            while not self.stop_event.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:  # WM_HOTKEY
                        hk_id = msg.wParam
                        offset = hk_id - self.hotkey_id_base
                        self.trigger_signal.emit(offset)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.02)
        except Exception as e:
            print(f"[HotkeyListener] Thread Error: {e}")
        finally:
            for hk_id in self.registered_ids:
                user32.UnregisterHotKey(None, hk_id)


class HotkeyRotatorApp(QtCore.QObject):
    """主控制逻辑，桥接 Socket 消息与 Win32 全局快捷键"""
    hotkey_signal = pyqtSignal(int)
    sync_signal = pyqtSignal(dict)
    
    def __init__(self, log_level):
        super().__init__()
        self.raw_hwnds = []
        self.hwnds = []
        self.name_map = {}
        self.mru_list = []
        self.fallback_active = False
        
        self.sync_signal.connect(self.on_windows_synced)
        self.hotkey_signal.connect(self.on_hotkey_triggered)
        
        # 启动 Socket 窗口同步服务
        self.sync_server = WindowSyncServer(self.sync_signal)
        self.sync_server.start()
        
        # 启动全局热键监听
        self.hotkey_listener = HotkeyListener(self.hotkey_signal, log_level)
        self.hotkey_listener.start()
        
        QTimer.singleShot(500, self.update_fallback_status)
        
    def update_fallback_status(self):
        self.fallback_active = self.hotkey_listener.fallback_active

    def on_windows_synced(self, data):
        try:
            self.raw_hwnds = data.get("hwnds", [])
            self.name_map = data.get("name_map", {})
            current_fore = data.get("current_fore", 0)
            
            # 在本地做有效可见性检查
            import ctypes
            user32 = ctypes.windll.user32
            
            self.hwnds = []
            for h in self.raw_hwnds:
                try:
                    if user32.IsWindow(h) and user32.IsWindowVisible(h):
                        self.hwnds.append(h)
                except Exception:
                    pass
                    
            # 更新物理 MRU 焦点
            global _active_dialog
            self_hwnd = 0
            if _active_dialog is not None and not sip.isdeleted(_active_dialog):
                try:
                    self_hwnd = int(_active_dialog.winId()) if _active_dialog.isVisible() else 0
                except Exception:
                    pass
            
            if current_fore and current_fore in self.hwnds and current_fore != self_hwnd:
                if current_fore in self.mru_list:
                    try:
                        self.mru_list.remove(current_fore)
                    except ValueError:
                        pass
                self.mru_list.insert(0, current_fore)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass
            
    def on_hotkey_triggered(self, offset):
        if offset in [9, 10]:
            # 窗口切换热键：本地处理，不阻塞，不进入 GIL
            core_hwnds = []
            tile_hwnds = []
            for h in self.hwnds:
                name = self.name_map.get(str(h), self.name_map.get(h, ""))
                if "概念前10监控" in name or "MonitorWindow_" in name:
                    tile_hwnds.append(h)
                else:
                    core_hwnds.append(h)
                    
            # 常规窗口按照 MRU 排序
            sorted_normal = []
            for mru in self.mru_list:
                if mru in core_hwnds:
                    sorted_normal.append(mru)
            for h in core_hwnds:
                if h not in sorted_normal:
                    sorted_normal.append(h)
                    
            final_hwnds = sorted_normal + tile_hwnds
            if not final_hwnds:
                return
                
            direction = 1 if offset == 9 else -1
            
            global _active_dialog
            if _active_dialog is not None and not sip.isdeleted(_active_dialog):
                try:
                    if _active_dialog.isVisible():
                        _active_dialog.rotate_highlight(direction, is_hotkey=True)
                        return
                    else:
                        _active_dialog.close()
                except Exception:
                    pass
            _active_dialog = None

            # 实例化 Dialog 呈现
            hk_desc = "Alt+Q" if self.fallback_active else "Alt+R"
            _active_dialog = WindowRotatorDialog(final_hwnds, self.name_map, direction, hk_desc)
            _active_dialog.show()
            _active_dialog.raise_()
            _active_dialog.activateWindow()
        else:
            # 其它功能性热键：直接投递给 Tk 进程
            send_to_tk_pipe({"cmd": "HOTKEY_TRIGGERED", "offset": offset})


def main(log_level="DEBUG"):
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # 物理根治：关闭轮选 Dialog 时防止整个 QApplication 事件循环退出闪退
        
        # 启用独立高 DPI 适配
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # PerMonitorV2
        except Exception:
            pass
            
        global _app_instance
        _app_instance = HotkeyRotatorApp(log_level)
        
        sys.exit(app.exec())
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == '__main__':
    main("DEBUG")
