"""Route console Ctrl+C through the ATS Qt shutdown path."""
import multiprocessing
import os
import signal
import threading
import time

from PyQt6.QtCore import QTimer


class QtKeyboardInterruptGuard:
    """Turn Ctrl+C into a queued window close, with TK-compatible escalation."""

    def __init__(self, app, window):
        self.app = app
        self.window = window
        self._pending = threading.Event()
        self._state = {'count': 0, 'last': 0.0, 'serial': 0}
        self._handled_serial = 0
        self._previous_handler = signal.getsignal(signal.SIGINT)
        self._handler = self._on_interrupt
        signal.signal(signal.SIGINT, self._handler)

        self._timer = QTimer(app)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._dispatch)
        self._timer.start()
        app.aboutToQuit.connect(self.restore)

    def _on_interrupt(self, _signum, _frame):
        now = time.monotonic()
        if now - self._state['last'] > 3.0:
            self._state['count'] = 0
        self._state['count'] += 1
        self._state['last'] = now
        self._state['serial'] += 1
        self._pending.set()

    def _dispatch(self):
        if not self._pending.is_set():
            return
        self._pending.clear()
        serial = self._state['serial']
        if serial == self._handled_serial:
            return
        self._handled_serial = serial
        count = self._state['count']
        if count >= 3:
            self._emergency_exit()
            return

        print(f"\n[ATS] KeyboardInterrupt ({count}/3)，正在请求有序关闭；" \
              "若退出排空失败，可在 3 秒内累计按到 3 次 Ctrl+C 触发紧急回收。", flush=True)
        try:
            self.window.close()
        except Exception as exc:
            print(f"[ATS] Ctrl+C 关闭请求失败: {exc}", flush=True)

    @staticmethod
    def _terminate_active_children():
        for process in multiprocessing.active_children():
            try:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=0.2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.2)
            except (OSError, ValueError):
                pass

    def _emergency_exit(self):
        print("\n[ATS] 连续 3 次 Ctrl+C，开始紧急回收子进程并强制退出。", flush=True)
        try:
            service = getattr(self.window, '_next_day_watch_process', None)
            if service is not None:
                service.close()
        except Exception as exc:
            print(f"[ATS] Next-day worker 回收失败: {exc}", flush=True)
        try:
            from ats.ui.sbc_launcher import SBCProcessManager
            SBCProcessManager.get_instance()._close_at_exit()
        except Exception as exc:
            print(f"[ATS] SBC 子进程回收失败: {exc}", flush=True)
        try:
            from ats.ui.ipo_detector_ipc import close_ipo_detector_process
            close_ipo_detector_process(timeout=0.5)
        except Exception as exc:
            print(f"[ATS] IPO detector 回收失败: {exc}", flush=True)
        self._terminate_active_children()
        time.sleep(0.3)
        os._exit(130)

    def restore(self):
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        try:
            if signal.getsignal(signal.SIGINT) == self._handler:
                signal.signal(signal.SIGINT, self._previous_handler)
        except (ValueError, OSError):
            pass


def install_qt_keyboard_interrupt_handler(app, window):
    """Install and return the process-wide ATS console interrupt guard."""
    return QtKeyboardInterruptGuard(app, window)
