"""Run favorite-store mutations off the Qt UI thread and deliver results safely."""

import threading
import weakref

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

_dispatcher = None
_dispatcher_lock = threading.Lock()


class _FavoriteWriteDispatcher(QObject):
    completed = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _is_deleted(owner):
        try:
            from PyQt6 import sip
            return sip.isdeleted(owner)
        except Exception:
            return False

    def _deliver(self, event):
        owner = event["owner"]()
        if owner is None or self._is_deleted(owner):
            return
        result, error = event["result"], event["error"]
        try:
            window = owner.window() if hasattr(owner, "window") else owner
            current = window
            status_bar = None
            refresh_target = None
            visited = set()
            while current is not None and id(current) not in visited:
                visited.add(id(current))
                if refresh_target is None and hasattr(current, "_safe_favorites_changed"):
                    refresh_target = current
                if status_bar is None and hasattr(current, "statusBar"):
                    try:
                        status_bar = current.statusBar()
                    except Exception:
                        status_bar = None
                if refresh_target is not None and status_bar is not None:
                    break
                try:
                    current = current.parentWidget() or current.parent()
                except Exception:
                    current = None
            if error is None:
                if refresh_target is not None:
                    getattr(refresh_target, "_on_favorites_changed", refresh_target._safe_favorites_changed)()
                message = event.get("success_message") or "重点关注已保存"
            else:
                message = "重点关注保存失败: " + str(error)
            if status_bar is not None:
                status_bar.showMessage(message[:180], 6000)
            elif error is not None:
                import logging
                logging.getLogger(__name__).error(message)
        except Exception:
            pass
        callback = event.get("on_complete")
        if callback is not None:
            try:
                callback(owner, result, error)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Favorite UI completion callback failed")


def _get_dispatcher():
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is None:
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("qt_application_required")
            _dispatcher = _FavoriteWriteDispatcher(app)
        return _dispatcher


def _run_manager_action(method_name, args, kwargs):
    from global_favorites import GlobalFavoriteManager

    manager = GlobalFavoriteManager()
    result = getattr(manager, method_name)(*args, **kwargs)
    if result == "error" or (isinstance(result, dict) and result.get("persisted") is False):
        raise RuntimeError("favorite_write_failed")
    return result


def submit_favorite_action(owner, method_name, *args, on_complete=None, success_message=None, **kwargs):
    """Submit a manager method and marshal completion onto the Qt application thread."""
    from global_favorites import submit_favorite_write

    dispatcher = _get_dispatcher()
    owner_ref = weakref.ref(owner)
    future = submit_favorite_write(_run_manager_action, method_name, args, kwargs)

    def dispatch(completed):
        try:
            result, error = completed.result(), None
        except Exception as caught:
            result, error = None, caught
        try:
            dispatcher.completed.emit({
                "owner": owner_ref,
                "result": result,
                "error": error,
                "on_complete": on_complete,
                "success_message": success_message,
            })
        except RuntimeError:
            pass

    future.add_done_callback(dispatch)
    return future
