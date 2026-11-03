"""每进程影子分片：RAMDisk 追加、原子检查点及运行中降级。"""
import atexit
import logging
import os
import shutil
import tempfile
import threading
import weakref

from ats.fusion.shadow_io import ram_directory

logger = logging.getLogger(__name__)
_writers = set()
_registry_lock = threading.RLock()
_by_path = weakref.WeakValueDictionary()
_started = False
MAX_PENDING_BYTES = 64 * 1024 * 1024


def _checkpoint_all(close=False):
    with _registry_lock:
        writers = list(_writers)
    for writer in writers:
        try:
            writer.close(force=True) if close else writer.checkpoint()
        except (OSError, RuntimeError):
            logger.exception("影子检查点失败，未落盘记录保留于内存/RAMDisk")


def _register(writer):
    global _started
    with _registry_lock:
        _writers.add(writer)
        if _started:
            return
        _started = True
    def run():
        from ats.archive_policy import archive_window
        while True:
            threading.Event().wait(30)
            try:
                window, _ = archive_window()
                if window == "close":
                    _checkpoint_all()
            except Exception:
                logger.exception("影子收盘检查点调度失败")
    threading.Thread(target=run, name="FusionShadowCheckpoint", daemon=True).start()
    atexit.register(_checkpoint_all, True)


def open_writer(directory, day):
    key = (os.path.normcase(os.path.abspath(directory)), day, os.getpid())
    with _registry_lock:
        writer = _by_path.get(key)
        if writer is not None:
            with writer._lock:
                if not writer._closed:
                    writer._users += 1
                    return writer
        writer = ShadowWriter(directory, day)
        _by_path[key] = writer
        return writer


class ShadowWriter:
    def __init__(self, directory, day):
        self._lock = threading.RLock()
        self._pending = []
        self._pending_bytes = 0
        self._closed = False
        self._users = 1
        self._fh = None
        os.makedirs(directory, exist_ok=True)
        name = "{}_{}.jsonl".format(day, os.getpid())
        self.local = os.path.join(directory, name)
        self.path = self.local
        self.on_ramdisk = False
        ram = ram_directory(directory)
        if ram:
            try:
                os.makedirs(ram, exist_ok=True)
                self.path = os.path.join(ram, name)
                self._restore()
                self._fh = open(self.path, "ab", buffering=0)
                self.on_ramdisk = True
            except (OSError, RuntimeError):
                logger.warning("影子 RAMDisk 初始化失败，降级本地", exc_info=True)
                self.path = self.local
        if self._fh is None:
            self._fh = open(self.local, "ab", buffering=0)
        _register(self)

    def _restore(self):
        """同 PID 重启时恢复未落盘后缀；不得以较旧 RAM 副本覆盖本地。"""
        local_size = os.path.getsize(self.local) if os.path.exists(self.local) else 0
        ram_size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        if ram_size > local_size:
            with open(self.path, "rb") as source:
                if local_size:
                    with open(self.local, "rb") as local:
                        for chunk in iter(lambda: local.read(1024 * 1024), b""):
                            if source.read(len(chunk)) != chunk:
                                raise RuntimeError("RAMDisk 与本地影子前缀不一致，拒绝覆盖")
                self._pending = [source.read()]
                self._pending_bytes = len(self._pending[0])
            self._checkpoint_pending()
        elif local_size:
            shutil.copyfile(self.local, self.path)

    def _checkpoint_pending(self):
        if not self._pending:
            return
        os.makedirs(os.path.dirname(self.local), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".shadow-sync-", dir=os.path.dirname(self.local))
        try:
            with os.fdopen(fd, "wb") as target:
                if os.path.exists(self.local):
                    with open(self.local, "rb") as source:
                        shutil.copyfileobj(source, target)
                for data in self._pending:
                    target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.local)
            self._pending.clear()
            self._pending_bytes = 0
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _fallback(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self._checkpoint_pending()
        self.path = self.local
        self.on_ramdisk = False
        self._fh = open(self.local, "ab", buffering=0)
        logger.warning("影子 RAMDisk 运行中不可用，已降级本地: %s", self.local)

    def write(self, text):
        data = text.encode("utf-8")
        with self._lock:
            if self._closed:
                raise ValueError("shadow writer is closed")
            if self.on_ramdisk:
                self._pending.append(data)
                self._pending_bytes += len(data)
                try:
                    if self._pending_bytes >= MAX_PENDING_BYTES:
                        raise OSError("影子待落盘缓冲达到容量上限")
                    if not os.path.isfile(self.path):
                        raise OSError("RAMDisk 分片已消失")
                    if self._fh.write(data) != len(data):
                        raise OSError("RAMDisk 写入不完整")
                except OSError:
                    self._fallback()
            else:
                # 本地失败时回滚残行，避免下一次追加到半条 JSON 后面。
                start = self._fh.tell()
                try:
                    if self._fh.write(data) != len(data):
                        raise OSError("影子写入不完整")
                except OSError:
                    self._fh.truncate(start)
                    raise

    def flush(self):
        with self._lock:
            if self._fh is not None:
                self._fh.flush()

    def checkpoint(self):
        with self._lock:
            if self._closed:
                return
            if self.on_ramdisk:
                self._checkpoint_pending()
            elif self._fh is not None:
                self._fh.flush()
                os.fsync(self._fh.fileno())

    def close(self, force=False):
        with self._lock:
            if self._closed:
                return
            self.checkpoint()
            if not force and self._users > 1:
                self._users -= 1
                return
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            self._closed = True
        with _registry_lock:
            _writers.discard(self)
