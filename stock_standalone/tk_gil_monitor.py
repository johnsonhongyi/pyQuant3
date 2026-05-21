# -*- coding: utf-8 -*-
"""
tk_gil_monitor.py  ——  Tk GIL Radar v3
=======================================
v3 新增：
  ① BlockingEdgeTracker + TraceQueue  — 追踪所有 blocking 点 enter/exit
  ② DeltaStackSampler                 — CPU time delta 判定真正 CPU-bound
  ③ GilContProxy                      — 1000-loop 探针推断 GIL 争用强度
  ④ FreezeClassifier                  — A(CPU-bound) B(IO-wait) C(deadlock)
  ⑤ CallChainBuffer                   — deque(50) 调用链追踪谁触发谁
"""

import sys, time, threading, traceback, functools, os
from collections import deque
from typing import Optional, Callable

_global_monitor: Optional["TkBreathingMonitor"] = None
def get_monitor(): return _global_monitor


# ─── 内部工具 ────────────────────────────────────────────
_last_warns = {}
_warn_lock = threading.Lock()

def _should_suppress_warn(msg: str) -> bool:
    try:
        import re
        # 1. 提取骨架指纹，将浮点数、整数、百分比等动态数值全部归一化为 [NUM]
        skeleton = re.sub(r'\d+\.\d+|\d+', '[NUM]', msg)
        skeleton = "".join(skeleton.split()) # 去除空白字符以做严格结构比对
        
        # 2. 根据警报严重程度和体量定制冷却阈值
        cooldown = 5.0 # 默认普通警报 5 秒
        if "THREAD DUMP" in msg:
            cooldown = 30.0
        elif "CALL CHAIN" in msg:
            cooldown = 30.0
        elif "DELTA_SAMPLER" in msg:
            cooldown = 15.0
        elif "TraceLock" in msg:
            cooldown = 10.0
        elif "BLOCKING THREADS" in msg:
            cooldown = 30.0
        elif "DELTA SAMPLER SUMMARY" in msg:
            cooldown = 30.0
        elif "QUEUE PRESSURE" in msg:
            cooldown = 30.0
            
        now = time.monotonic()
        with _warn_lock:
            last_t = _last_warns.get(skeleton, 0.0)
            if now - last_t < cooldown:
                return True
            _last_warns[skeleton] = now
            
            # 3. 限制指纹缓存大小，防内存膨胀
            if len(_last_warns) > 1000:
                for k, t in list(_last_warns.items()):
                    if now - t > 600.0:
                        del _last_warns[k]
    except Exception:
        pass
    return False

def _warn(msg):
    try:
        import sys
        enabled = True
        if "JohnsonUtil.commonTips" in sys.modules:
            cct = sys.modules["JohnsonUtil.commonTips"]
            if hasattr(cct, "CFG") and hasattr(cct.CFG, "gil_monitor"):
                enabled = bool(cct.CFG.gil_monitor)
        elif "stock_standalone.JohnsonUtil.commonTips" in sys.modules:
            cct = sys.modules["stock_standalone.JohnsonUtil.commonTips"]
            if hasattr(cct, "CFG") and hasattr(cct.CFG, "gil_monitor"):
                enabled = bool(cct.CFG.gil_monitor)
        else:
            try:
                from JohnsonUtil.commonTips import CFG
                if hasattr(CFG, "gil_monitor"):
                    enabled = bool(CFG.gil_monitor)
            except Exception:
                try:
                    from stock_standalone.JohnsonUtil.commonTips import CFG
                    if hasattr(CFG, "gil_monitor"):
                        enabled = bool(CFG.gil_monitor)
                except Exception:
                    pass
        if enabled:
            if _should_suppress_warn(msg):
                return
            print(msg, flush=True)
    except Exception:
        pass

def _tname(tid):
    for t in threading.enumerate():
        if t.ident == tid: return t.name
    return "unknown"

def _dump_threads(tag="", max_frames=12):
    lines = [f"\n🔥 ===== THREAD DUMP [{tag}] ====="]
    frames = sys._current_frames()
    main_tid = threading.main_thread().ident
    for tid, frame in sorted(frames.items(), key=lambda x:(x[0]!=main_tid, x[0])):
        nm = _tname(tid)
        marker = " ← ★" if nm == _gil_holder.get()["thread"] else ""
        lines.append(f"\n--- [{nm}]{marker} ---")
        lines.append("".join(traceback.format_stack(frame)[-max_frames:]).rstrip())
    lines.append("===== END =====\n")
    _warn("\n".join(lines))


# ─── 1. LastCallTracker ──────────────────────────────────
class LastCallTracker:
    __slots__ = ("_data", "_lock")
    def __init__(self):
        self._data = {"time": 0.0, "func": None, "thread": None, "args_repr": ""}
        self._lock = threading.Lock()

    def trace(self, func):
        @functools.wraps(func)
        def w(*a, **kw):
            with self._lock:
                self._data.update({"time": time.time(), "func": func.__qualname__,
                                   "thread": threading.current_thread().name,
                                   "args_repr": repr(a[1])[:40] if len(a)>1 else ""})
            return func(*a, **kw)
        return w

    def get(self):
        with self._lock: return dict(self._data)

    def dump(self):
        d = self.get()
        if not d["func"]: return "[LastCall] (none)"
        return (f"[LastCall] func={d['func']}  thread={d['thread']}  "
                f"elapsed={time.time()-d['time']:.3f}s")

last_call = LastCallTracker()


# ─── 2. GilHolderTracker ────────────────────────────────
class GilHolderTracker:
    def __init__(self): self._t = {"func":None,"thread":None,"ts":0.0}
    def mark(self, fn):
        if not fn or fn.endswith(":end"):
            self._t.update({"func": None, "thread": None, "ts": 0.0})
        else:
            self._t.update({"func": fn, "thread": threading.current_thread().name, "ts": time.time()})
    def get(self): return dict(self._t)
    def dump(self, thr=1.0):
        d=self.get()
        if not d["func"]: return "[GilHolder] (none)"
        e=time.time()-d["ts"]
        return f"[GilHolder] {'🔥STUCK' if e>thr else 'OK'}  func={d['func']}  thread={d['thread']}  held={e:.3f}s"

_gil_holder = GilHolderTracker()

def gil_mark(fn): _gil_holder.mark(fn)


# ─── 3. CallChainBuffer ★NEW ────────────────────────────
class CallChainBuffer:
    """记录最近 50 次函数调用链，用于还原"谁触发了谁"。"""
    def __init__(self, maxlen=50):
        self._buf = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, fn: str):
        with self._lock:
            self._buf.append((time.time(), threading.current_thread().name, fn))

    def dump(self, last_n=20) -> str:
        with self._lock:
            items = list(self._buf)[-last_n:]
        if not items: return "[CallChain] (empty)"
        lines = ["📋 ===== CALL CHAIN (last {}) =====".format(len(items))]
        t0 = items[0][0]
        for ts, thr, fn in items:
            lines.append(f"  +{ts-t0:6.3f}s [{thr}] {fn}")
        return "\n".join(lines)

call_chain = CallChainBuffer()


# ─── 4. BlockingEdgeTracker + TraceQueue ★NEW ───────────
_blocking_state = {}   # thread_name -> {"point": str, "enter_ts": float}

def block_mark(name: str, action: str):
    """
    在 blocking 点前后调用：
      block_mark("queue.get", "enter")
      ...blocking call...
      block_mark("queue.get", "exit")
    """
    thr = threading.current_thread().name
    now = time.time()
    if action == "enter":
        _blocking_state[thr] = {"point": name, "enter_ts": now}
        call_chain.push(f"BLOCK_ENTER:{name}")
    elif action == "exit":
        st = _blocking_state.pop(thr, None)
        if st:
            waited = now - st["enter_ts"]
            call_chain.push(f"BLOCK_EXIT:{name}  waited={waited:.3f}s")
            if waited > 0.5:
                _warn(f"⚠️ [BLOCK_SLOW] {name}  waited={waited:.3f}s  thread={thr}")

def get_blocking_summary() -> str:
    if not _blocking_state: return "[Blocking] (none)"
    lines = ["🔒 ===== BLOCKING THREADS ====="]
    for thr, st in _blocking_state.items():
        waited = time.time() - st["enter_ts"]
        lines.append(f"  [{thr}] BLOCKED on {st['point']}  waited={waited:.3f}s")
    return "\n".join(lines)


import queue as _queue_mod

class TraceQueue(_queue_mod.Queue):
    """替换标准 Queue，自动记录 get/put 的 blocking 耗时。"""
    def __init__(self, *a, name="unnamed", **kw):
        super().__init__(*a, **kw)
        self._tq_name = name

    def get(self, *a, **kw):
        block_mark(f"TraceQueue({self._tq_name}).get", "enter")
        try:
            return super().get(*a, **kw)
        finally:
            block_mark(f"TraceQueue({self._tq_name}).get", "exit")

    def put(self, *a, **kw):
        block_mark(f"TraceQueue({self._tq_name}).put", "enter")
        try:
            return super().put(*a, **kw)
        finally:
            block_mark(f"TraceQueue({self._tq_name}).put", "exit")


# ─── 5. DeltaStackSampler ★NEW ──────────────────────────
class DeltaStackSampler:
    """
    每 200ms 采样线程栈 + process CPU time delta。
    真正的 CPU-bound 判定：同一 stack + CPU time 增长 > 阈值
    （纯"栈不变"会误判 IO-wait 线程）
    """
    def __init__(self, interval=0.2, stuck_rounds=15,
                 ignore=("TkGilWatchdog","DeltaStackSampler","AutoStackDump")):
        self.interval = interval
        self.stuck_rounds = stuck_rounds
        self.ignore = ignore
        self._running = False
        # tid -> {"key": tuple, "count": int, "cpu_t0": float}
        self._state: dict = {}
        try:
            self._proc = __import__("psutil").Process(os.getpid())
            self._has_psutil = True
        except Exception:
            self._has_psutil = False

    def start(self):
        if self._running: return
        self._running = True
        t = threading.Thread(target=self._loop, name="DeltaStackSampler", daemon=True)
        t.start()

    def stop(self): self._running = False

    def _cpu_time(self):
        try:
            if self._has_psutil:
                ct = self._proc.cpu_times()
                return ct.user + ct.system
        except Exception: pass
        return time.process_time()

    def _loop(self):
        while self._running:
            time.sleep(self.interval)
            try: self._sample()
            except Exception as e:
                try: print(f"[DeltaStackSampler] {e}", flush=True)
                except: pass

    def _sample(self):
        frames = sys._current_frames()
        cpu_now = self._cpu_time()
        for tid, frame in frames.items():
            tname = _tname(tid)
            if any(tname.startswith(ig) for ig in self.ignore): continue

            # 栈指纹：文件+函数+行号（最后4帧）
            key = tuple(
                (f.f_code.co_filename[-30:], f.f_code.co_name, f.f_lineno)
                for f in self._iter_frames(frame)
            )[-4:]

            prev = self._state.get(tid, {"key": None, "count": 0, "cpu_t0": cpu_now})

            if key == prev["key"]:
                count = prev["count"] + 1
                cpu_delta = cpu_now - prev["cpu_t0"]
                self._state[tid] = {"key": key, "count": count, "cpu_t0": prev["cpu_t0"]}

                if count == self.stuck_rounds:
                    elapsed = count * self.interval
                    # 区分 CPU-bound vs IO-wait
                    is_cpu_bound = cpu_delta > elapsed * 0.3
                    kind = "CPU-BOUND 🔥" if is_cpu_bound else "IO-WAIT ⏳"
                    full = "".join(traceback.format_stack(frame)[-8:]).rstrip()
                    _warn(
                        f"\n🔥 [DELTA_SAMPLER] Thread [{tname}] {kind} ~{elapsed:.1f}s\n"
                        f"   cpu_delta={cpu_delta:.3f}s  stack_rounds={count}\n"
                        f"{full}\n"
                        f"   {last_call.dump()}\n"
                        f"   {_gil_holder.dump()}"
                    )
            else:
                self._state[tid] = {"key": key, "count": 0, "cpu_t0": cpu_now}

    @staticmethod
    def _iter_frames(frame):
        f = frame
        while f:
            yield f
            f = f.f_back

    def summary(self) -> str:
        lines = ["📊 ===== DELTA SAMPLER SUMMARY ====="]
        for tid, st in list(self._state.items()):
            if st["count"] > 2:
                tname = _tname(tid)
                top = f"{st['key'][-1][1]}@{st['key'][-1][2]}" if st["key"] else "?"
                elapsed = st["count"] * self.interval
                lines.append(f"  [{tname}] stuck={elapsed:.1f}s  top={top}")
        lines.append("=====")
        return "\n".join(lines)

_delta_sampler = DeltaStackSampler()


# ─── 6. GilContProxy ★NEW ───────────────────────────────
class GilContProxy:
    """
    GIL 争用强度探针。
    在后台线程每 500ms 执行一次 1000-loop，
    若耗时突增 → 推断 GIL 被长期占用。
    """
    def __init__(self, interval=0.5, baseline_ms=0.1, alert_ratio=5.0):
        self.interval = interval
        self.baseline_ms = baseline_ms   # 正常情况下 1000-loop 约 0.05ms
        self.alert_ratio = alert_ratio   # 超过 baseline * ratio 报警
        self._running = False
        self._latency_ms: float = 0.0

    def start(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._loop, name="GilContProxy", daemon=True).start()

    def stop(self): self._running = False

    def _probe(self) -> float:
        t0 = time.perf_counter()
        for _ in range(1000): pass
        return (time.perf_counter() - t0) * 1000.0

    def _loop(self):
        # 先测几次基线
        samples = [self._probe() for _ in range(5)]
        self.baseline_ms = max(0.01, sum(samples) / len(samples))
        while self._running:
            time.sleep(self.interval)
            try:
                ms = self._probe()
                self._latency_ms = ms
                if ms > self.baseline_ms * self.alert_ratio:
                    _warn(f"🌡️ [GIL_CONT] probe={ms:.3f}ms  "
                          f"baseline={self.baseline_ms:.3f}ms  "
                          f"ratio={ms/self.baseline_ms:.1f}x  "
                          f"→ GIL contention HIGH  {_gil_holder.dump()}")
            except Exception: pass

    @property
    def contention_ratio(self) -> float:
        if self.baseline_ms <= 0: return 1.0
        return self._latency_ms / self.baseline_ms

_gil_cont = GilContProxy()


# ─── 7. FreezeClassifier ★NEW ───────────────────────────
class FreezeClassifier:
    """
    UI Freeze 三分类：
      A — CPU-bound (GIL starvation)
      B — IO/queue wait
      C — deadlock (lock cycle)
    """
    @staticmethod
    def classify(ui_lag: float) -> tuple:
        """
        返回 (class_str, confidence, reason)
        """
        cont_ratio = _gil_cont.contention_ratio
        blocking = _blocking_state

        # C: deadlock — blocking 持续 > ui_lag 的 80%
        if blocking:
            max_wait = max(time.time()-v["enter_ts"] for v in blocking.values())
            if max_wait > ui_lag * 0.8:
                return ("C-DEADLOCK", 0.85,
                        f"thread blocked {max_wait:.1f}s on {next(iter(blocking.values()))['point']}")

        # A: CPU-bound — GIL contention 探针超高 + sampler 检测到 CPU stuck
        if cont_ratio > 4.0:
            return ("A-CPU_BOUND", min(0.95, cont_ratio/10),
                    f"GIL probe ratio={cont_ratio:.1f}x")

        # B: IO-wait — blocking 有记录但不是 deadlock
        if blocking:
            return ("B-IO_WAIT", 0.7,
                    f"{len(blocking)} thread(s) in blocking call")

        # Fallback
        return ("A-CPU_BOUND", 0.5, "default (no blocking detected)")


# ─── 8. TraceLock ────────────────────────────────────────
class TraceLock:
    def __init__(self, name, timeout=5.0, verbose=True):
        self.name=name; self.timeout=timeout; self.verbose=verbose
        self._lock=threading.RLock(); self._owner=None; self._ts=0.0

    def __enter__(self): self.acquire(); return self
    def __exit__(self,*_): self.release()

    def acquire(self, blocking=True, timeout=None):
        t=timeout if timeout is not None else self.timeout
        t0=time.monotonic()
        ok=self._lock.acquire(blocking=blocking, timeout=t if blocking else -1)
        elapsed=time.monotonic()-t0
        if not ok:
            _warn(f"🚨 [TraceLock][DEADLOCK] '{self.name}' TIMEOUT {elapsed:.2f}s  owner={self._owner}")
            _dump_threads("DEADLOCK")
            return False
        if self.verbose and elapsed>0.1:
            _warn(f"⚠️ [TraceLock][SLOW] '{self.name}' {elapsed:.3f}s")
        self._owner=threading.current_thread().name; self._ts=time.monotonic()
        return True

    def release(self):
        held=time.monotonic()-self._ts if self._ts else 0
        if self.verbose and held>0.5:
            _warn(f"⚠️ [TraceLock][LONG] '{self.name}' held {held:.3f}s")
        self._owner=None; self._lock.release()


# ─── 9. gil_yield 增强 ──────────────────────────────────
def gil_yield(tag="", threshold_ms=5.0):
    """sleep(0) + sys._getframe() 双重强制调度触发。"""
    t0=time.perf_counter()
    time.sleep(0); sys._getframe()
    cost=(time.perf_counter()-t0)*1000
    if cost>threshold_ms:
        _warn(f"⚠️ [GIL_STALL] tag={tag!r}  wait={cost:.2f}ms")

def ui_guard(name, threshold_ms=50.0):
    def dec(fn):
        @functools.wraps(fn)
        def w(*a,**kw):
            t0=time.perf_counter(); r=fn(*a,**kw)
            dt=(time.perf_counter()-t0)*1000
            if dt>threshold_ms:
                _warn(f"⚠️ [UI_SLOW] {name}  {dt:.1f}ms")
            return r
        return w
    return dec

def auto_stack_dump_if_stuck(seconds=3.0):
    state={"ts":time.time()}
    def _wd():
        while True:
            time.sleep(1)
            if time.time()-state["ts"]>seconds:
                _warn(f"🚨 [auto_dump] stuck {time.time()-state['ts']:.1f}s")
                _dump_threads("auto")
    threading.Thread(target=_wd,name="AutoStackDump",daemon=True).start()
    def tick(): state["ts"]=time.time()
    return tick


# ─── 10. TkBreathingMonitor v3 ──────────────────────────
class TkBreathingMonitor:
    """Tk GIL Radar v3 主体。"""

    def __init__(self, root, app=None, warn_threshold=1.0,
                 freeze_threshold=3.0, heartbeat_ms=50,
                 watchdog_interval=1.0, enabled=True, cpu_sampling=True):
        global _global_monitor; _global_monitor=self
        self.root=root; self.app=app
        self.warn_threshold=warn_threshold
        self.freeze_threshold=freeze_threshold
        self.heartbeat_ms=heartbeat_ms
        self.watchdog_interval=watchdog_interval
        self.enabled=enabled; self.cpu_sampling=cpu_sampling
        self._ui_alive_ts=time.time()
        self._watchdog_running=False
        self._tracked_queues={}
        self._freeze_count=0; self._last_dump_ts=0.0
        self._dump_cooldown=5.0
        self.last_call=last_call; self.call_chain=call_chain

    def breathe(self):
        """50ms 心跳 + update_idletasks()。"""
        if not self.enabled: return
        self._ui_alive_ts=time.time()
        try: self.root.update_idletasks()
        except Exception: pass
        try: self.root.after(self.heartbeat_ms, self.breathe)
        except Exception: pass

    def start_watchdog(self):
        if not self.enabled or self._watchdog_running: return
        self._watchdog_running=True
        
        def _delayed_start():
            # 🛡️ [SHIELD-FIX] 延迟 3 秒启动后台监测，避开冷启动期间大量 C/C++ 模块载入的内存敏感期
            time.sleep(3.0)
            if not self._watchdog_running: return
            
            threading.Thread(target=self._loop, name="TkGilWatchdog", daemon=True).start()
            if self.cpu_sampling:
                _delta_sampler.start()
                _gil_cont.start()
                
        threading.Thread(target=_delayed_start, name="TkGilWatchdogDelayed", daemon=True).start()

    def _loop(self):
        while self._watchdog_running:
            time.sleep(self.watchdog_interval)
            if not self.enabled: continue
            try:
                lag=time.time()-self._ui_alive_ts
                if lag>self.freeze_threshold:
                    self._freeze_count+=1
                    now=time.time()
                    if now-self._last_dump_ts>=self._dump_cooldown:
                        self._last_dump_ts=now
                        cls,conf,reason=FreezeClassifier.classify(lag)
                        _warn(
                            f"\n🚨 [GIL RADAR v3] UI FROZEN!\n"
                            f"   lag={lag:.2f}s  class={cls}  conf={conf:.0%}\n"
                            f"   reason={reason}\n"
                            f"   {last_call.dump()}\n"
                            f"   {_gil_holder.dump(self.freeze_threshold)}\n"
                            f"   GIL-probe-ratio={_gil_cont.contention_ratio:.1f}x"
                        )
                        _dump_threads("FROZEN")
                        _warn(get_blocking_summary())
                        _warn(_delta_sampler.summary())
                        _warn(call_chain.dump())
                        self._dump_queue_pressure()
                    else:
                        _warn(f"🚨 [FREEZE] lag={lag:.2f}s (cooldown)")
                elif lag>self.warn_threshold:
                    _warn(f"⚠️ [GIL PRESSURE] lag={lag:.2f}s  {last_call.dump()}")
                    self._freeze_count=0
                else:
                    self._freeze_count=0

                # GilHolder 独立超时检测
                gh=_gil_holder.get()
                if gh["func"] and (time.time()-gh["ts"])>self.freeze_threshold:
                    _warn(f"🔥 [GIL_STUCK] func={gh['func']}  "
                          f"thread={gh['thread']}  held={time.time()-gh['ts']:.2f}s")
            except Exception as e:
                try: print(f"[Watchdog] {e}", flush=True)
                except: pass

    def _dump_queue_pressure(self):
        if not self._tracked_queues: return
        lines=["📦 QUEUE PRESSURE"]
        for nm,q in self._tracked_queues.items():
            try: lines.append(f"  {nm}: {q.qsize()}")
            except: lines.append(f"  {nm}: err")
        _warn("\n".join(lines))

    def register_queue(self, name, q): self._tracked_queues[name]=q
    def get_lag(self): return time.time()-self._ui_alive_ts
    def is_frozen(self): return self.get_lag()>self.freeze_threshold

    def stop(self):
        self._watchdog_running=False; self.enabled=False
        _delta_sampler.stop(); _gil_cont.stop()


def install(root, app=None, freeze_threshold=3.0, enabled=True, cpu_sampling=True):
    """一行集成：self._gil_monitor = install(root=self, app=self)"""
    m=TkBreathingMonitor(root=root, app=app, freeze_threshold=freeze_threshold,
                         enabled=enabled, heartbeat_ms=50, cpu_sampling=cpu_sampling)
    m.breathe(); m.start_watchdog(); return m
