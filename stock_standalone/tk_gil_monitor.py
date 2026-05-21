# -*- coding: utf-8 -*-
"""
tk_gil_monitor.py  ——  Tk GIL 呼吸器系统（生产级诊断工具）
=============================================================

架构说明：
    ┌────────────────────────────────┐
    │   Tk mainloop thread           │
    │   breathe() 每 200ms tick 一次  │
    └──────────────┬─────────────────┘
                   │ 更新 _ui_alive_ts
    ┌──────────────▼─────────────────┐
    │  GIL Watchdog Thread (1s loop)  │
    └──────────────┬─────────────────┘
                   │ 超过阈值时
    ┌──────────────▼─────────────────┐
    │  dump_all_threads()            │
    │  + lock_status_report()        │
    │  + queue_pressure_report()     │
    └────────────────────────────────┘

组件清单：
  1. TkBreathingMonitor   — UI 心跳 + Watchdog 主体
  2. TraceLock            — 带超时/死锁诊断的 RLock 包装器
  3. gil_yield(tag)       — GIL 时间片切割探针（可选）
  4. ui_guard(name)       — UI 函数耗时装饰器
  5. LastCallTracker      — 全局"最后活跃函数"记录器
  6. auto_stack_dump_if_stuck() — 独立卡死检测（可选，无需 Tk）

接入方式（在 StockMonitorApp.__init__ 最后或 mainloop 前调用）：
    from tk_gil_monitor import TkBreathingMonitor
    _monitor = TkBreathingMonitor(root=self, app=self)
    _monitor.breathe()          # 在 Tk 主线程启动心跳
    _monitor.start_watchdog()   # 启动后台 Watchdog 线程

作者：自动生成 (Antigravity)
日期：2026-05-21
"""

import sys
import time
import threading
import traceback
import functools
import queue as _queue
from typing import Optional, Callable, Any

# ─────────────────────────────────────────────────────────
# 全局单例引用（外部可直接 import 使用）
# ─────────────────────────────────────────────────────────
_global_monitor: Optional["TkBreathingMonitor"] = None


def get_monitor() -> Optional["TkBreathingMonitor"]:
    """获取全局 TkBreathingMonitor 单例（如果已初始化）。"""
    return _global_monitor


# ─────────────────────────────────────────────────────────
# 1. LastCallTracker —— 最后活跃函数记录
# ─────────────────────────────────────────────────────────
class LastCallTracker:
    """
    轻量函数进入记录器。
    使用 @tracker.trace 装饰目标函数后，任意时刻调用
    tracker.get() 即可得到最近一次被调用的函数名、线程名和时间戳。

    示例::

        _last_call = LastCallTracker()

        @_last_call.trace
        def update_scores(...): ...
    """
    __slots__ = ("_data", "_lock")

    def __init__(self):
        self._data = {"time": 0.0, "func": None, "thread": None, "args_repr": ""}
        self._lock = threading.Lock()

    def trace(self, func: Callable) -> Callable:
        """装饰器：记录函数调用。"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self._lock:
                self._data["time"] = time.time()
                self._data["func"] = func.__qualname__
                self._data["thread"] = threading.current_thread().name
                # 只记录第一个非 self 的参数，避免大对象序列化开销
                try:
                    extra = repr(args[1])[:40] if len(args) > 1 else ""
                    self._data["args_repr"] = extra
                except Exception:
                    pass
            return func(*args, **kwargs)
        return wrapper

    def get(self) -> dict:
        """返回最后一次调用记录（只读副本）。"""
        with self._lock:
            return dict(self._data)

    def dump(self) -> str:
        d = self.get()
        if not d["func"]:
            return "[LastCall] (none)"
        delta = time.time() - d["time"]
        return (
            f"[LastCall] func={d['func']}  "
            f"thread={d['thread']}  "
            f"elapsed={delta:.3f}s  "
            f"args={d['args_repr']}"
        )


# 全局实例
last_call = LastCallTracker()


# ─────────────────────────────────────────────────────────
# 2. TraceLock —— 带死锁诊断的 RLock 包装器
# ─────────────────────────────────────────────────────────
class TraceLock:
    """
    带死锁诊断的 threading.RLock 包装器。

    当 acquire() 超过 timeout 秒未拿到锁时：
      1. 打印 DEADLOCK DETECTED 告警
      2. dump 所有线程栈（找出持有者）

    用法::

        _score_lock = TraceLock("score_lock")

        with _score_lock:          # 支持 with 语法
            ...

    或::

        _lock = TraceLock("main_lock", timeout=3.0, verbose=False)
    """

    def __init__(self, name: str, timeout: float = 5.0, verbose: bool = True):
        self.name = name
        self.timeout = timeout
        self.verbose = verbose
        self._lock = threading.RLock()
        self._owner_name: Optional[str] = None
        self._acquire_ts: float = 0.0

    # ── with 协议 ─────────────────────────────────────────
    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()

    # ── 核心 API ──────────────────────────────────────────
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        t = timeout if timeout is not None else self.timeout
        t0 = time.monotonic()
        ok = self._lock.acquire(blocking=blocking, timeout=t if blocking else -1)
        elapsed = time.monotonic() - t0

        if not ok:
            _warn(
                f"🚨 [TraceLock][DEADLOCK] '{self.name}' acquire TIMEOUT "
                f"after {elapsed:.2f}s  "
                f"owner_was={self._owner_name}  "
                f"caller_thread={threading.current_thread().name}"
            )
            _dump_all_threads()
            return False

        if self.verbose and elapsed > 0.1:
            _warn(
                f"⚠️ [TraceLock][SLOW] '{self.name}' acquired in {elapsed:.3f}s  "
                f"thread={threading.current_thread().name}"
            )

        self._owner_name = threading.current_thread().name
        self._acquire_ts = time.monotonic()
        return True

    def release(self):
        held_for = time.monotonic() - self._acquire_ts if self._acquire_ts else 0.0
        if self.verbose and held_for > 0.5:
            _warn(
                f"⚠️ [TraceLock][LONG_HOLD] '{self.name}' held {held_for:.3f}s  "
                f"thread={self._owner_name}"
            )
        self._owner_name = None
        self._lock.release()

    # ── 兼容原生 threading.Lock 调用方式 ──────────────────
    def locked(self) -> bool:
        acquired = self._lock.acquire(blocking=False)
        if acquired:
            self._lock.release()
            return False
        return True


# ─────────────────────────────────────────────────────────
# 3. gil_yield —— GIL 时间片切割探针
# ─────────────────────────────────────────────────────────
def gil_yield(tag: str = "", threshold_ms: float = 5.0):
    """
    在 Worker loop 关键位置调用，强制 time.sleep(0) 释放 GIL。
    如果等待 GIL 超过 threshold_ms，打印告警。

    示例::

        detector.update_scores(...)
        gil_yield("update_scores")
    """
    t0 = time.perf_counter()
    time.sleep(0)
    cost_ms = (time.perf_counter() - t0) * 1000.0
    if cost_ms > threshold_ms:
        _warn(f"⚠️ [GIL_STALL] tag={tag!r}  wait={cost_ms:.2f}ms  "
              f"thread={threading.current_thread().name}")


# ─────────────────────────────────────────────────────────
# 4. ui_guard —— UI 函数耗时装饰器
# ─────────────────────────────────────────────────────────
def ui_guard(name: str, threshold_ms: float = 50.0):
    """
    装饰器工厂：检测 UI 函数超时并打印告警。

    示例::

        @ui_guard("_refresh_sector_list", threshold_ms=50)
        def _refresh_sector_list(self): ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            if dt_ms > threshold_ms:
                _warn(f"⚠️ [UI_SLOW] {name}  cost={dt_ms:.1f}ms  "
                      f"thread={threading.current_thread().name}")
                # 同时更新最后调用记录
                last_call._data.update({
                    "time": time.time(),
                    "func": name,
                    "thread": threading.current_thread().name,
                })
            return result
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────
# 5. TkBreathingMonitor —— 主体
# ─────────────────────────────────────────────────────────
class TkBreathingMonitor:
    """
    Tk GIL 呼吸器系统主体。

    参数
    ----
    root          : Tk 根窗口（任何拥有 .after() 方法的对象）
    app           : StockMonitorApp 实例（用于访问 queue / detector）
    warn_threshold: UI 无响应警告阈值（秒），默认 1.0s
    freeze_threshold: UI 冻结阈值（秒），默认 3.0s
    heartbeat_ms  : 心跳间隔（毫秒），默认 200ms
    watchdog_interval: Watchdog 检查间隔（秒），默认 1.0s
    enabled       : False 时完全禁用所有诊断（生产安静模式）
    """

    def __init__(
        self,
        root,
        app=None,
        warn_threshold: float = 1.0,
        freeze_threshold: float = 3.0,
        heartbeat_ms: int = 200,
        watchdog_interval: float = 1.0,
        enabled: bool = True,
    ):
        global _global_monitor
        _global_monitor = self

        self.root = root
        self.app = app
        self.warn_threshold = warn_threshold
        self.freeze_threshold = freeze_threshold
        self.heartbeat_ms = heartbeat_ms
        self.watchdog_interval = watchdog_interval
        self.enabled = enabled

        self._ui_alive_ts: float = time.time()
        self._watchdog_running: bool = False

        # 可选：要追踪的 queue 对象（由外部注入）
        self._tracked_queues: dict[str, Any] = {}

        # 连续冻结次数（避免刷屏）
        self._freeze_count: int = 0
        self._last_dump_ts: float = 0.0
        self._dump_cooldown: float = 5.0   # 最短 5s 才再次 dump

        # 注入 last_call tracker 引用（供外部查询）
        self.last_call = last_call

    # ── 心跳（必须在 Tk 主线程调用）────────────────────────
    def breathe(self):
        """
        在 Tk 主线程中持续心跳。
        调用一次后通过 root.after() 自循环，无需外部驱动。
        """
        if not self.enabled:
            return
        self._ui_alive_ts = time.time()
        try:
            self.root.after(self.heartbeat_ms, self.breathe)
        except Exception:
            pass  # Tk 已销毁时静默退出

    # ── Watchdog（后台守护线程）─────────────────────────────
    def start_watchdog(self):
        """启动 Watchdog 后台守护线程。"""
        if not self.enabled or self._watchdog_running:
            return
        self._watchdog_running = True
        t = threading.Thread(
            target=self._watchdog_loop,
            name="TkGilWatchdog",
            daemon=True,
        )
        t.start()

    def _watchdog_loop(self):
        while self._watchdog_running:
            time.sleep(self.watchdog_interval)
            if not self.enabled:
                continue
            try:
                lag = time.time() - self._ui_alive_ts

                if lag > self.freeze_threshold:
                    self._freeze_count += 1
                    # 防刷屏：冷却期内仅打印简短提示
                    now = time.time()
                    if now - self._last_dump_ts >= self._dump_cooldown:
                        self._last_dump_ts = now
                        _warn(
                            f"\n🚨 [GIL BREATHING ALERT] UI THREAD FROZEN!\n"
                            f"   lag={lag:.2f}s  freeze_count={self._freeze_count}\n"
                            f"   {last_call.dump()}"
                        )
                        self._dump_all_threads()
                        self._dump_queue_pressure()
                    else:
                        _warn(
                            f"🚨 [FREEZE] lag={lag:.2f}s (cooldown, skip dump)  "
                            f"{last_call.dump()}"
                        )

                elif lag > self.warn_threshold:
                    _warn(
                        f"⚠️ [GIL PRESSURE] UI lag={lag:.2f}s  "
                        f"{last_call.dump()}"
                    )
                    self._freeze_count = 0

                else:
                    self._freeze_count = 0

            except Exception as exc:
                # Watchdog 自身不能崩溃
                try:
                    print(f"[TkGilWatchdog] internal error: {exc}")
                except Exception:
                    pass

    # ── 线程栈快照 ──────────────────────────────────────────
    def _dump_all_threads(self):
        try:
            lines = ["\n🔥 ===== THREAD STACK SNAPSHOT ====="]
            frames = sys._current_frames()
            # 将主线程放在最前面
            main_tid = threading.main_thread().ident
            sorted_items = sorted(
                frames.items(),
                key=lambda kv: (0 if kv[0] == main_tid else 1, kv[0])
            )
            for tid, frame in sorted_items:
                t_name = _thread_name(tid)
                lines.append(f"\n--- THREAD {tid} [{t_name}] ---")
                stack_lines = traceback.format_stack(frame)
                # 只取最后 15 帧（最关键的调用链）
                lines.append("".join(stack_lines[-15:]).rstrip())
            lines.append("\n===== END SNAPSHOT =====\n")
            _warn("\n".join(lines))
        except Exception as exc:
            _warn(f"[dump_all_threads] error: {exc}")

    # ── Queue 压力报告 ────────────────────────────────────
    def _dump_queue_pressure(self):
        if not self._tracked_queues:
            return
        try:
            lines = ["📦 ===== QUEUE PRESSURE ====="]
            for name, q in self._tracked_queues.items():
                try:
                    size = q.qsize() if hasattr(q, "qsize") else "?"
                    lines.append(f"  {name}: qsize={size}")
                except Exception:
                    lines.append(f"  {name}: (error)")
            lines.append("=====")
            _warn("\n".join(lines))
        except Exception as exc:
            _warn(f"[queue_pressure] error: {exc}")

    # ── 公共 API ──────────────────────────────────────────
    def register_queue(self, name: str, q):
        """注册一个队列对象，供 Watchdog 汇报压力。"""
        self._tracked_queues[name] = q

    def get_lag(self) -> float:
        """返回当前 UI 线程响应延迟（秒）。"""
        return time.time() - self._ui_alive_ts

    def is_frozen(self) -> bool:
        """当前 UI 线程是否处于冻结状态。"""
        return self.get_lag() > self.freeze_threshold

    def stop(self):
        """停止 Watchdog（退出时调用）。"""
        self._watchdog_running = False
        self.enabled = False


# ─────────────────────────────────────────────────────────
# 6. auto_stack_dump_if_stuck —— 独立卡死检测（无需 Tk）
# ─────────────────────────────────────────────────────────
def auto_stack_dump_if_stuck(seconds: float = 3.0) -> Callable:
    """
    独立版卡死检测器。不依赖 Tk，可在任意函数/循环中使用。
    返回一个 tick 函数，调用者需定期调用它来"证明自己还活着"。

    示例::

        tick = auto_stack_dump_if_stuck(seconds=3)

        def my_loop():
            while True:
                do_work()
                tick()    # 定期调用

    当 tick 超过 seconds 秒未被调用时，自动 dump 所有线程栈。
    """
    state = {"last_tick": time.time()}

    def _watchdog():
        while True:
            time.sleep(1.0)
            elapsed = time.time() - state["last_tick"]
            if elapsed > seconds:
                _warn(
                    f"\n🚨 [auto_stack_dump] STUCK DETECTED "
                    f"(no tick for {elapsed:.1f}s)\n"
                    f"{last_call.dump()}"
                )
                _dump_all_threads()

    threading.Thread(target=_watchdog, name="AutoStackDump", daemon=True).start()

    def tick():
        state["last_tick"] = time.time()

    return tick


# ─────────────────────────────────────────────────────────
# 内部工具函数（私有）
# ─────────────────────────────────────────────────────────
def _warn(msg: str):
    """统一输出到 stdout，兼容 Nuitka/PyInstaller 无 stderr 场景。"""
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _thread_name(tid: int) -> str:
    """通过 tid 查线程名，找不到则返回 'unknown'。"""
    for t in threading.enumerate():
        if t.ident == tid:
            return t.name
    return "unknown"


def _dump_all_threads():
    """模块级线程栈快照（可独立调用）。"""
    try:
        lines = ["\n🔥 ===== THREAD STACK (standalone) ====="]
        frames = sys._current_frames()
        for tid, frame in frames.items():
            t_name = _thread_name(tid)
            lines.append(f"\n--- THREAD {tid} [{t_name}] ---")
            lines.append("".join(traceback.format_stack(frame)[-12:]).rstrip())
        lines.append("\n===== END =====\n")
        _warn("\n".join(lines))
    except Exception as exc:
        _warn(f"[_dump_all_threads] error: {exc}")


# ─────────────────────────────────────────────────────────
# 快捷接入：一行集成到 StockMonitorApp
# ─────────────────────────────────────────────────────────
def install(root, app=None, freeze_threshold: float = 3.0, enabled: bool = True) -> "TkBreathingMonitor":
    """
    便捷工厂函数，在 StockMonitorApp.__init__ 末尾调用即可完成全部接入：

        from tk_gil_monitor import install
        self._gil_monitor = install(root=self, app=self)
    """
    monitor = TkBreathingMonitor(
        root=root,
        app=app,
        freeze_threshold=freeze_threshold,
        enabled=enabled,
    )
    monitor.breathe()
    monitor.start_watchdog()
    return monitor
