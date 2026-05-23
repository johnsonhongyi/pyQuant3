from __future__ import annotations

import json
import os
import tempfile
import threading
import time

FLAT = "FLAT"
ARMED = "ARMED"
IN_TRADE = "IN_TRADE"
EXITING = "EXITING"
COOLDOWN = "COOLDOWN"

VALID_STATES = {FLAT, ARMED, IN_TRADE, EXITING, COOLDOWN}


class StateManager:
    """Behavior lock only: code -> state (Robust Multi-process Resilient Lock)."""

    def __init__(self):
        self._states: dict[str, str] = {}
        self._lock = threading.Lock()
        self._last_sync = 0.0
        self._throttle_interval = 0.05  # 50ms 节流读取，降低 I/O 开销
        
        # 跨进程物理共享状态与文件自愈锁
        temp_dir = tempfile.gettempdir()
        self._filepath = os.path.join(temp_dir, "trading_kernel_shared_state.json")
        self._lockpath = os.path.join(temp_dir, "trading_kernel_shared_state.lock")
        
        # 自愈清空遗留的死锁文件
        self._self_heal_stale_lock()

    def _self_heal_stale_lock(self) -> None:
        """如果锁文件由于旧进程意外崩溃而遗留，且超过 2 秒未释放，则物理自愈释放"""
        try:
            if os.path.exists(self._lockpath):
                mtime = os.path.getmtime(self._lockpath)
                if time.time() - mtime > 2.0:
                    os.remove(self._lockpath)
        except OSError:
            pass

    def _acquire_file_lock(self, timeout: float = 0.3) -> bool:
        """原子性创建 lock 文件以在 Windows/Linux 下实现强跨进程排他锁"""
        start = time.time()
        while True:
            try:
                fd = os.open(self._lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return True
            except OSError:
                if time.time() - start > timeout:
                    # 超时自愈：判定为遗留死锁并物理接管
                    self._self_heal_stale_lock()
                    try:
                        fd = os.open(self._lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.close(fd)
                        return True
                    except OSError:
                        return False
                time.sleep(0.005)

    def _release_file_lock(self) -> None:
        try:
            if os.path.exists(self._lockpath):
                os.remove(self._lockpath)
        except OSError:
            pass

    def _sync_from_file(self) -> None:
        """从共享物理文件中同步全局状态至本进程内存，并具备自愈恢复能力"""
        now = time.time()
        if now - self._last_sync < self._throttle_interval:
            return  # 节流短路，降低高频行情下的 I/O 损耗
            
        if not os.path.exists(self._filepath):
            self._last_sync = now
            return

        if self._acquire_file_lock(timeout=0.1):
            try:
                if os.path.exists(self._filepath):
                    with open(self._filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._states = {str(k): str(v) for k, v in data.items() if v in VALID_STATES}
            except (json.JSONDecodeError, OSError, ValueError):
                # 自愈恢复：若 JSON 损坏则自动进行物理初始化重设
                self._states = {}
            finally:
                self._release_file_lock()
            self._last_sync = now

    def _flush_to_file(self) -> None:
        """将当前状态原子持久化，确保其它四大金刚进程秒级对齐"""
        if self._acquire_file_lock(timeout=0.3):
            try:
                # 写入前先与磁盘做一次最新增量合并，防止覆盖其它进程瞬时变更的值
                disk_data = {}
                if os.path.exists(self._filepath):
                    try:
                        with open(self._filepath, "r", encoding="utf-8") as f:
                            disk_data = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        disk_data = {}
                
                # 合并内存和磁盘
                merged = {str(k): str(v) for k, v in disk_data.items() if v in VALID_STATES}
                merged.update(self._states)
                
                # 写入临时文件再原子 rename，规避写入中途断电导致文件损毁
                temp_filepath = self._filepath + ".tmp"
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                
                # Windows 下需先 remove 再 rename
                if os.path.exists(self._filepath):
                    os.remove(self._filepath)
                os.rename(temp_filepath, self._filepath)
            except OSError:
                pass
            finally:
                self._release_file_lock()

    def get(self, code: str) -> str:
        with self._lock:
            self._sync_from_file()
            return self._states.get(str(code), FLAT)

    def set(self, code: str, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid trade state: {state}")
        with self._lock:
            self._states[str(code)] = state
            self._flush_to_file()
            self._last_sync = time.time()

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            # 强制做一次全量物理同步
            self._last_sync = 0.0
            self._sync_from_file()
            return dict(self._states)
