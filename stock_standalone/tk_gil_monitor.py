# -*- coding: utf-8 -*-
"""
tk_gil_monitor.py  ——  Tk GIL 呼吸器系统 v2（生产级核武器）
=============================================================

v2 升级：
  ① GIL Holder Tracker   — 追踪"谁最后持有 GIL 超过 N ms"
  ② CPU Sampling Watchdog — 每 200ms 采样所有线程栈，检测"栈不变=卡死"
  ③ Breathe 增强          — 50ms 心跳 + update_idletasks() 强制事件消费
  ④ gil_yield 增强        — sleep(0) + sys._getframe() 强制调度器切换

架构：
    Tk mainloop (50ms breathe + idletasks)
         ↑ 心跳
    GIL Watchdog Thread (1s)   ← 报 FROZEN + dump
    CPU Sampler Thread (200ms) ← 采样栈 → 检测"热点/卡死线程"
    GIL Holder Tracker         ← gil_mark() 埋点 → 知道谁卡住了

组件：
  1. TkBreathingMonitor  — 主体
  2. LastCallTracker     — 最后活跃函数
  3. GilHolderTracker    — GIL 持有者追踪 ★NEW
  4. CpuSampler          — CPU 热点采样器 ★NEW
  5. TraceLock           — 死锁诊断 RLock
  6. gil_yield(tag)      — 强化版 GIL 切片
  7. gil_mark(tag)       — GIL 持有标记 ★NEW
  8. ui_guard(name)      — UI 耗时装饰器
  9. auto_stack_dump_if_stuck()
"""

import sys
import time
import threading
import traceback
import functools
import collections
from typing import Optional, Callable, Any

# ─────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────
_global_monitor: Optional["TkBreathingMonitor"] = None


def get_monitor() -> Optional["TkBreathingMonitor"]:
    return _global_monitor


# ─────────────────────────────────────────────────────────
# 1. LastCallTracker
# ─────────────────────────────────────────────────────────
class LastCallTracker:
    """记录最后一次被调用的函数（线程安全，超低开销）。"""
    __slots__ = ("_data", "_lock")

    def __init__(self):
        self._data = {"time": 0.0, "func": None, "thread": None, "args_repr": ""}
        self._lock = threading.Lock()

    def trace(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self._lock:
                self._data["time"] = time.time()
                self._data["func"] = func.__qualname__
                self._data["thread"] = threading.current_thread().name
                try:
                    self._data["args_repr"] = repr(args[1])[:40] if len(args) > 1 else ""
                except Exception:
                    pass
            return func(*args, **kwargs)
        return wrapper

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def dump(self) -> str:
        d = self.get()
        if not d["func"]:
            return "[LastCall] (none)"
        delta = time.time() - d["time"]
        return (f"[LastCall] func={d['func']}  thread={d['thread']}  "
                f"elapsed={delta:.3f}s  args={d['args_repr']}")


last_call = LastCallTracker()


# ─────────────────────────────────────────────────────────
# 2. GilHolderTracker ★NEW
#    在核心函数入口/出口调用 gil_mark(tag)
#    Watchdog 检测"最后标记超过 N ms 未更新 = GIL 被占"
# ─────────────────────────────────────────────────────────
class GilHolderTracker:
    """
    追踪"谁最后持有 GIL 并停留了多久"。

    用法::

        from tk_gil_monitor import gil_mark

        gil_mark("update_scores:start")
        self.detector.update_scores(...)
        gil_mark("update_scores:end")

    Watchdog 会自动检测 last_ts 超过阈值 → 报 GIL_STUCK。
    """
    __slots__ = ("_trace",)

    def __init__(self):
        # 无锁设计：dict 赋值在 CPython 中是原子的
        self._trace = {
            "func": None,
            "thread": None,
            "ts": 0.0,
        }

    def mark(self, func_name: str):
        """在关键函数入口/出口调用，标记当前 GIL 持有状态。"""
        self._trace["func"] = func_name
        self._trace["thread"] = threading.current_thread().name
        self._trace["ts"] = time.time()

    def get(self) -> dict:
        return dict(self._trace)

    def dump(self, threshold_s: float = 1.0) -> str:
        d = self.get()
        if not d["func"]:
            return "[GilHolder] (none)"
        elapsed = time.time() - d["ts"]
        flag = "🔥 STUCK" if elapsed > threshold_s else "OK"
        return (f"[GilHolder] {flag}  func={d['func']}  "
                f"thread={d['thread']}  held={elapsed:.3f}s")


gil_holder = GilHolderTracker()


def gil_mark(func_name: str):
    """在关键函数入口/出口调用。外部一行接入：gil_mark('update_scores:start')"""
    gil_holder.mark(func_name)


# ─────────────────────────────────────────────────────────
# 3. CpuSampler ★NEW
#    每 200ms 采样所有线程栈 → 检测"栈 N 次不变 = CPU loop 卡死"
# ─────────────────────────────────────────────────────────
class CpuSampler:
    """
    CPU 热点采样器。

    每 sample_interval 秒采样一次所有线程的调用栈（最后3帧）。
    若某线程的栈连续 stuck_count 次未变化，判定为 CPU-bound 卡死，
    打印 🔥 [CPU_HOTSPOT] 报告。

    这是定位"C/Python loop 独占 GIL"的核武器，传统 freeze dump 看不到。
    """

    def __init__(
        self,
        sample_interval: float = 0.2,
        stuck_count: int = 15,       # 15 × 0.2s = 3s 不变则报警
        ignore_threads: tuple = (),  # 线程名前缀黑名单
    ):
        self.sample_interval = sample_interval
        self.stuck_count = stuck_count
        self.ignore_threads = ignore_threads or ("TkGilWatchdog", "CpuSampler", "AutoStackDump")

        self._running = False
        self._last_stacks: dict = {}      # tid -> (stack_tuple, repeat_count)
        self._hotspot_report: list = []   # 最近热点记录

    def start(self):
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._loop, name="CpuSampler", daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(self.sample_interval)
            try:
                self._sample()
            except Exception as exc:
                try:
                    print(f"[CpuSampler] error: {exc}", flush=True)
                except Exception:
                    pass

    def _sample(self):
        frames = sys._current_frames()
        now = time.time()

        for tid, frame in frames.items():
            t_name = _thread_name(tid)

            # 跳过采样器自身和黑名单线程
            if any(t_name.startswith(ig) for ig in self.ignore_threads):
                continue

            # 取最后 3 帧作为"栈指纹"
            stack_key = tuple(
                (f.f_code.co_filename, f.f_code.co_name, f.f_lineno)
                for f in _iter_frames(frame)
            )[-3:]

            prev_key, prev_count = self._last_stacks.get(tid, (None, 0))

            if stack_key == prev_key:
                count = prev_count + 1
                self._last_stacks[tid] = (stack_key, count)

                if count == self.stuck_count:
                    # 刚刚达到阈值 → 报一次
                    elapsed_s = count * self.sample_interval
                    lines = [
                        f"\n🔥 [CPU_HOTSPOT] Thread [{t_name}] STUCK for ~{elapsed_s:.1f}s",
                        f"   Stack fingerprint (last 3 frames):",
                    ]
                    full_stack = "".join(traceback.format_stack(frame)[-8:]).rstrip()
                    lines.append(full_stack)
                    lines.append(f"   {last_call.dump()}")
                    lines.append(f"   {gil_holder.dump()}")
                    _warn("\n".join(lines))

            else:
                self._last_stacks[tid] = (stack_key, 0)

    def get_hotspot_summary(self) -> str:
        """返回当前所有线程的栈重复次数摘要（供 Watchdog dump 附加）。"""
        lines = ["📊 ===== CPU SAMPLER SUMMARY ====="]
        for tid, (stack, count) in list(self._last_stacks.items()):
            if count > 0:
                t_name = _thread_name(tid)
                elapsed = count * self.sample_interval
                top = f"{stack[-1][1]}@{stack[-1][2]}" if stack else "?"
                lines.append(f"  [{t_name}] stuck={elapsed:.1f}s  top={top}")
        lines.append("=====")
        return "\n".join(lines)


# 全局实例
cpu_sampler = CpuSampler()


# ─────────────────────────────────────────────────────────
# 4. TraceLock
# ─────────────────────────────────────────────────────────
class TraceLock:
    """带超时死锁诊断的 threading.RLock 包装器。"""

    def __init__(self, name: str, timeout: float = 5.0, verbose: bool = True):
        self.name = name
        self.timeout = timeout
        self.verbose = verbose
        self._lock = threading.RLock()
        self._owner_name: Optional[str] = None
        self._acquire_ts: float = 0.0

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        t = timeout if timeout is not None else self.timeout
        t0 = time.monotonic()
        ok = self._lock.acquire(blocking=blocking, timeout=t if blocking else -1)
        elapsed = time.monotonic() - t0

        if not ok:
            _warn(
                f"🚨 [TraceLock][DEADLOCK] '{self.name}' TIMEOUT after {elapsed:.2f}s  "
                f"owner={self._owner_name}  caller={threading.current_thread().name}"
            )
            _dump_all_threads()
            return False

        if self.verbose and elapsed > 0.1:
            _warn(f"⚠️ [TraceLock][SLOW] '{self.name}' acquired in {elapsed:.3f}s  "
                  f"thread={threading.current_thread().name}")

        self._owner_name = threading.current_thread().name
        self._acquire_ts = time.monotonic()
        return True

    def release(self):
        held = time.monotonic() - self._acquire_ts if self._acquire_ts else 0.0
        if self.verbose and held > 0.5:
            _warn(f"⚠️ [TraceLock][LONG_HOLD] '{self.name}' held {held:.3f}s  "
                  f"thread={self._owner_name}")
        self._owner_name = None
        self._lock.release()

    def locked(self) -> bool:
        acquired = self._lock.acquire(blocking=False)
        if acquired:
            self._lock.release()
            return False
        return True


# ─────────────────────────────────────────────────────────
# 5. gil_yield 增强版 ★UPGRADED
#    sleep(0) + sys._getframe() → 强制调度器切换
# ─────────────────────────────────────────────────────────
def gil_yield(tag: str = "", threshold_ms: float = 5.0):
    """
    强化版 GIL 时间片释放探针。

    对比旧版：
      旧: time.sleep(0)
      新: time.sleep(0) + sys._getframe()  ← 强制触发调度器

    在大循环的 chunk 边界调用::

        for i in range(0, len(codes), 200):
            process_batch(codes[i:i+200])
            gil_yield(f"chunk-{i}")
    """
    t0 = time.perf_counter()
    time.sleep(0)
    # sys._getframe() 强制触发 Python 字节码边界，让调度器有机会切换
    sys._getframe()
    cost_ms = (time.perf_counter() - t0) * 1000.0
    if cost_ms > threshold_ms:
        _warn(f"⚠️ [GIL_STALL] tag={tag!r}  wait={cost_ms:.2f}ms  "
              f"thread={threading.current_thread().name}")


# ─────────────────────────────────────────────────────────
# 6. ui_guard
# ─────────────────────────────────────────────────────────
def ui_guard(name: str, threshold_ms: float = 50.0):
    """UI 函数耗时装饰器，超阈值自动报警。"""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            if dt_ms > threshold_ms:
                _warn(f"⚠️ [UI_SLOW] {name}  cost={dt_ms:.1f}ms  "
                      f"thread={threading.current_thread().name}")
                last_call._data.update({
                    "time": time.time(),
                    "func": name,
                    "thread": threading.current_thread().name,
                })
            return result
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────
# 7. TkBreathingMonitor 增强版 ★UPGRADED
# ─────────────────────────────────────────────────────────
class TkBreathingMonitor:
    """
    Tk GIL 呼吸器系统 v2 主体。

    v2 升级点：
    - breathe() 心跳从 200ms → 50ms，加 update_idletasks()
    - Watchdog dump 时附加 CpuSampler 热点摘要 + GilHolder 状态
    - 集成 CpuSampler 自动启停
    """

    def __init__(
        self,
        root,
        app=None,
        warn_threshold: float = 1.0,
        freeze_threshold: float = 3.0,
        heartbeat_ms: int = 50,          # v2: 50ms（旧 200ms）
        watchdog_interval: float = 1.0,
        enabled: bool = True,
        cpu_sampling: bool = True,       # v2: CPU 采样开关
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
        self.cpu_sampling = cpu_sampling

        self._ui_alive_ts: float = time.time()
        self._watchdog_running: bool = False
        self._tracked_queues: dict = {}
        self._freeze_count: int = 0
        self._last_dump_ts: float = 0.0
        self._dump_cooldown: float = 5.0

        self.last_call = last_call
        self.gil_holder = gil_holder
        self.cpu_sampler = cpu_sampler

    # ── 心跳（Tk 主线程）★UPGRADED ────────────────────────
    def breathe(self):
        """
        50ms 心跳 + update_idletasks()。

        update_idletasks() 强制 Tk 处理积压的 idle 事件，
        防止因 GIL 压力导致的 Tk 内部事件队列积压。
        """
        if not self.enabled:
            return
        self._ui_alive_ts = time.time()
        try:
            # ★ 关键升级：强制消费 Tk idle 事件
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self.root.after(self.heartbeat_ms, self.breathe)
        except Exception:
            pass

    # ── Watchdog ──────────────────────────────────────────
    def start_watchdog(self):
        """启动 Watchdog + CpuSampler。"""
        if not self.enabled or self._watchdog_running:
            return
        self._watchdog_running = True

        t = threading.Thread(target=self._watchdog_loop, name="TkGilWatchdog", daemon=True)
        t.start()

        if self.cpu_sampling:
            cpu_sampler.start()

    def _watchdog_loop(self):
        while self._watchdog_running:
            time.sleep(self.watchdog_interval)
            if not self.enabled:
                continue
            try:
                lag = time.time() - self._ui_alive_ts

                if lag > self.freeze_threshold:
                    self._freeze_count += 1
                    now = time.time()
                    if now - self._last_dump_ts >= self._dump_cooldown:
                        self._last_dump_ts = now
                        _warn(
                            f"\n🚨 [GIL BREATHING ALERT] UI FROZEN!\n"
                            f"   lag={lag:.2f}s  freeze_count={self._freeze_count}\n"
                            f"   {last_call.dump()}\n"
                            f"   {gil_holder.dump(threshold_s=self.freeze_threshold)}"
                        )
                        self._dump_all_threads()
                        self._dump_queue_pressure()
                        # ★ v2: 附加 CPU 采样摘要
                        _warn(cpu_sampler.get_hotspot_summary())
                    else:
                        _warn(f"🚨 [FREEZE] lag={lag:.2f}s (cooldown)  "
                              f"{last_call.dump()}")

                elif lag > self.warn_threshold:
                    _warn(f"⚠️ [GIL PRESSURE] lag={lag:.2f}s  {last_call.dump()}  "
                          f"{gil_holder.dump()}")
                    self._freeze_count = 0
                else:
                    self._freeze_count = 0

                # ★ v2: 独立检测 GIL Holder 超时（不依赖 UI 心跳）
                gh = gil_holder.get()
                if gh["func"] and (time.time() - gh["ts"]) > self.freeze_threshold:
                    elapsed = time.time() - gh["ts"]
                    _warn(
                        f"🔥 [GIL_STUCK_HOLDER] func={gh['func']}  "
                        f"thread={gh['thread']}  held={elapsed:.2f}s"
                    )

            except Exception as exc:
                try:
                    print(f"[TkGilWatchdog] error: {exc}", flush=True)
                except Exception:
                    pass

    # ── 线程栈快照 ────────────────────────────────────────
    def _dump_all_threads(self):
        try:
            lines = ["\n🔥 ===== THREAD STACK SNAPSHOT ====="]
            frames = sys._current_frames()
            main_tid = threading.main_thread().ident
            sorted_items = sorted(
                frames.items(),
                key=lambda kv: (0 if kv[0] == main_tid else 1, kv[0])
            )
            for tid, frame in sorted_items:
                t_name = _thread_name(tid)
                # ★ v2: 标注"可能 GIL 持有者"
                gh = gil_holder.get()
                marker = " ← ★GIL HOLDER★" if gh["thread"] == t_name else ""
                lines.append(f"\n--- THREAD {tid} [{t_name}]{marker} ---")
                lines.append("".join(traceback.format_stack(frame)[-15:]).rstrip())
            lines.append("\n===== END SNAPSHOT =====\n")
            _warn("\n".join(lines))
        except Exception as exc:
            _warn(f"[dump_all_threads] error: {exc}")

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
        self._tracked_queues[name] = q

    def get_lag(self) -> float:
        return time.time() - self._ui_alive_ts

    def is_frozen(self) -> bool:
        return self.get_lag() > self.freeze_threshold

    def stop(self):
        self._watchdog_running = False
        self.enabled = False
        cpu_sampler.stop()


# ─────────────────────────────────────────────────────────
# 8. auto_stack_dump_if_stuck
# ─────────────────────────────────────────────────────────
def auto_stack_dump_if_stuck(seconds: float = 3.0) -> Callable:
    """独立版卡死检测，返回 tick 函数，调用者定期调用证明存活。"""
    state = {"last_tick": time.time()}

    def _watchdog():
        while True:
            time.sleep(1.0)
            elapsed = time.time() - state["last_tick"]
            if elapsed > seconds:
                _warn(f"\n🚨 [auto_stack_dump] STUCK {elapsed:.1f}s\n{last_call.dump()}")
                _dump_all_threads()

    threading.Thread(target=_watchdog, name="AutoStackDump", daemon=True).start()

    def tick():
        state["last_tick"] = time.time()

    return tick


# ─────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────
def _warn(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _thread_name(tid: int) -> str:
    for t in threading.enumerate():
        if t.ident == tid:
            return t.name
    return "unknown"


def _iter_frames(frame):
    """从当前帧向上迭代所有帧。"""
    f = frame
    while f is not None:
        yield f
        f = f.f_back


def _dump_all_threads():
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
# 快捷接入
# ─────────────────────────────────────────────────────────
def install(
    root,
    app=None,
    freeze_threshold: float = 3.0,
    enabled: bool = True,
    cpu_sampling: bool = True,
) -> "TkBreathingMonitor":
    """
    一行集成工厂。在 StockMonitorApp.__init__ 末尾::

        from tk_gil_monitor import install
        self._gil_monitor = install(root=self, app=self)
    """
    monitor = TkBreathingMonitor(
        root=root,
        app=app,
        freeze_threshold=freeze_threshold,
        enabled=enabled,
        heartbeat_ms=50,          # 50ms 心跳
        cpu_sampling=cpu_sampling,
    )
    monitor.breathe()
    monitor.start_watchdog()
    return monitor
