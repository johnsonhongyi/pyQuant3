"""桌面桥看门狗：管理器后台周期检测桥状态，掉线/卡死时自动重启（带退避，不阻塞 UI）。"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 30.0        # 检测周期
HEARTBEAT_STALE = 180.0      # 桥运行但 agent 心跳超过该秒数视为卡死
CONFIRM_COUNT = 2            # 连续异常次数才触发，避免瞬时抖动
BACKOFF_BASE = 60.0          # 首次失败后的冷却
BACKOFF_MAX = 600.0


class BridgeWatchdog:
    """每个桥一个实例；controller 需提供 task_info/restart_bridge/autostart_enabled/runtime_path。"""

    def __init__(self, name: str, controller, log=None):
        self.name = name
        self.controller = controller
        self._log = log or (lambda msg: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bad = 0
        self._failures = 0
        self._next_allowed = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name=f"bridge-watchdog-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # 先等一个周期，让随管理器启动的流程完成
        while not self._stop.wait(CHECK_INTERVAL):
            try:
                self.check_once()
            except Exception as exc:  # 看门狗自身不可中断
                logger.warning("[%s 看门狗] 检测异常：%s", self.name, type(exc).__name__)

    def _manually_stopped(self) -> bool:
        rt = self.controller.runtime_path()
        return any((rt / rel).exists() for rel in ("stop.request", "agent/stop.request"))

    def diagnose(self) -> str:
        """返回异常原因；健康返回空串。"""
        info = self.controller.task_info()
        if not info.get("exists"):
            return ""
        if not info.get("running"):
            return "进程未运行"
        agent = info.get("agent_status") or {}
        try:
            updated = float(agent.get("updated_epoch") or 0)
        except (TypeError, ValueError):
            updated = 0.0
        if updated and time.time() - updated > HEARTBEAT_STALE:
            return f"心跳停滞 {int(time.time() - updated)}s"
        return ""

    def check_once(self) -> str:
        if not self.controller.autostart_enabled() or self._manually_stopped():
            self._bad = 0
            return "skip"
        reason = self.diagnose()
        if not reason:
            self._bad = self._failures = 0
            return "healthy"
        self._bad += 1
        if self._bad < CONFIRM_COUNT or time.time() < self._next_allowed:
            return "pending"
        self._log(f"[{self.name} 桌面桥看门狗] 检测到异常（{reason}），自动重启…")
        try:
            self.controller.restart_bridge(timeout=60.0)
        except Exception as exc:
            self._failures += 1
            delay = min(BACKOFF_MAX, BACKOFF_BASE * (2 ** (self._failures - 1)))
            self._next_allowed = time.time() + delay
            self._log(f"[{self.name} 桌面桥看门狗] 自动重启失败（{type(exc).__name__}: {str(exc)[:120]}），{int(delay)}s 后重试。")
            return "failed"
        self._bad = self._failures = 0
        self._log(f"[{self.name} 桌面桥看门狗] 自动重启成功。")
        return "restarted"
