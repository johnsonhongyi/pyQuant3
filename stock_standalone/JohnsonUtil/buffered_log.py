"""Bounded, deduplicated log batches on RAMDisk; local copy is closing-only."""
import copy
import hashlib
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from collections import OrderedDict


class BufferedRamLogHandler(RotatingFileHandler):
    """RAMDisk 批量日志处理器。

    设计目标（2026-10 修复版）：
      1. 去重时必须保留消息正文，只追加计数，禁止用计数器覆盖原文；
      2. 同一消息在抑制窗口内反复出现时，累计计数延后输出，而不是每轮写一行；
      3. 滚动使用真正的文件轮转（.1/.2/.3），不再原地截断抹掉历史；
      4. 刷盘间隔缩短到秒级，写入锁超时放宽，失败时保留待写数据；
      5. 容量上限触发时写入带时间戳的告警行，不再静默丢弃。
    """

    # ── 可调参数 ──────────────────────────────────────────────────────────
    INTERVAL = 5.0                 # 批量刷盘间隔（秒），原 60s 导致日志延迟近 1 分钟
    MAX_KEYS = 8192                # 待写队列容量，原 1024 在日志种类多时频繁淘汰
    MAX_PENDING_BYTES = 8 * 1024 * 1024
    SEEN_TTL = 1800.0              # 去重记忆保留时长（秒）
    REPEAT_SUPPRESS = 300.0        # 同一消息重复时的抑制窗口（秒），窗口内只累计不落盘
    LOCK_TIMEOUT = 2.0             # 目录写锁超时（秒），原 0.25s 极易整批丢弃
    BACKUP_COUNT = 3               # 轮转保留份数，原 0 表示直接原地截断

    def __init__(self, filename, **kwargs):
        self._pending = OrderedDict()     # key -> [record, count]  当前窗口内新增
        self._deferred = OrderedDict()    # key -> [record, count]  被抑制、待补写
        self._seen = OrderedDict()        # key -> [total_count, last_emit_ts]
        self._pending_bytes = 0
        self._omitted = 0
        self._closed_event = threading.Event()
        self._archive_target = os.path.abspath(filename)
        self._runtime_ready = False
        # Do not open the local file, including during logging initialization.
        kwargs['delay'] = True
        super().__init__(filename, **kwargs)
        threading.Thread(target=self._batch_loop, daemon=True, name='RamLogBatch').start()

    # ── 记录采集 ──────────────────────────────────────────────────────────
    def emit(self, record):
        try:
            message = record.getMessage()[:8192]
            exception_text = record.exc_text or (
                logging.Formatter().formatException(record.exc_info) if record.exc_info else '')
            exception_text = str(exception_text)[:8192]
            key = (record.name, record.levelno, record.pathname, record.lineno, message, exception_text)
            if key in self._pending:
                self._pending[key][1] += 1
                return
            size = len(message.encode('utf-8')) + len(key[-1].encode('utf-8')) + 256
            if len(self._pending) >= self.MAX_KEYS or self._pending_bytes + size > self.MAX_PENDING_BYTES:
                # 容量触顶：记账后丢弃，稍后在 flush 时写一条带时间戳的告警行
                self._omitted += 1
                return
            retained = copy.copy(record)
            retained.msg, retained.args = message, ()
            retained.exc_text = exception_text or None
            retained.exc_info = None
            self._pending[key] = [retained, 1]
            self._pending_bytes += size
        except Exception:
            self.handleError(record)

    def _batch_loop(self):
        while not self._closed_event.wait(self.INTERVAL):
            self.flush()

    # ── 内部工具 ──────────────────────────────────────────────────────────
    def _rotate_files(self):
        """真正的文件轮转：base -> .1 -> .2 ...，保留 backupCount 份历史。

        注意：Windows 下必须先关闭句柄再改名，否则 os.replace 会因文件占用失败。
        """
        base = self.baseFilename
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        backups = max(0, int(self.backupCount or 0))
        if backups > 0:
            for index in range(backups - 1, 0, -1):
                src = '%s.%d' % (base, index)
                dst = '%s.%d' % (base, index + 1)
                if os.path.exists(src):
                    try:
                        if os.path.exists(dst):
                            os.remove(dst)
                        os.replace(src, dst)
                    except OSError:
                        pass
            if os.path.exists(base):
                try:
                    target = base + '.1'
                    if os.path.exists(target):
                        os.remove(target)
                    os.replace(base, target)
                except OSError:
                    pass
        self.stream = self._open()

    def _write_capacity_notice(self):
        """容量告警必须带时间戳，否则无法定位丢弃发生在哪一刻。"""
        try:
            notice = logging.LogRecord(
                name='log.capacity', level=logging.WARNING, pathname=__file__, lineno=0,
                msg='[log capacity] pending queue full, omitted_count=%d '
                    '(records dropped before write; raise MAX_PENDING_BYTES/MAX_KEYS if frequent)',
                args=(self._omitted,), exc_info=None,
            )
            self.stream.write(self.format(notice) + '\n')
        except Exception:
            pass
        finally:
            self._omitted = 0

    # ── 批量落盘 ──────────────────────────────────────────────────────────
    def flush(self):
        if not hasattr(self, '_pending'):
            return
        self.acquire()
        try:
            # 把上一轮被抑制的记录并回待写队列，使其在抑制窗口结束后能补写
            if self._deferred:
                for key, item in self._deferred.items():
                    if key in self._pending:
                        self._pending[key][1] += item[1]
                    else:
                        self._pending[key] = item
                self._deferred.clear()

            if not self._pending:
                if self._omitted and self._runtime_ready and self.stream is not None:
                    self._write_capacity_notice()
                return

            if not self._runtime_ready:
                # Deferred import avoids LoggerFactory/commonTips initialization cycles.
                from linkage_storage import runtime_file
                self.baseFilename = runtime_file(self._archive_target, max_bytes=5 * 1024 * 1024)
                # 保留有限份历史，避免事故现场被原地截断抹掉
                self.backupCount = self.BACKUP_COUNT
                self._runtime_ready = True

            from ats.persistence_lock import directory_write_lock
            with directory_write_lock(os.path.dirname(self.baseFilename), timeout=self.LOCK_TIMEOUT):
                now = time.monotonic()
                if self.stream is None:
                    self.stream = self._open()
                try:
                    current_size = os.path.getsize(self.baseFilename)
                except OSError:
                    current_size = 0

                # 清理过期的去重记忆，避免长期运行后无限增长。
                # 仍在待写队列中的 key 不参与淘汰，否则会把刚攒好的计数一起丢掉。
                expired = [
                    k for k, v in self._seen.items()
                    if (now - v[1]) > self.SEEN_TTL and k not in self._pending and k not in self._deferred
                ]
                for k in expired:
                    self._seen.pop(k, None)

                for key in list(self._pending.keys()):
                    record, count = self._pending[key]
                    previous_total, last_emit = self._seen.get(key, (0, 0.0))
                    total_count = previous_total + count

                    # 抑制窗口内不落盘，只累计；等窗口结束后一次性补写完整正文 + 总数
                    # 注意：这里不能同时更新 _seen 的计数，否则 deferred 合并回来会重复累加
                    if last_emit and (now - last_emit) < self.REPEAT_SUPPRESS:
                        self._deferred[key] = [record, count]
                        self._pending.pop(key, None)
                        continue

                    message_id = hashlib.sha256(repr(key).encode('utf-8')).hexdigest()[:16]
                    body = record.msg
                    if previous_total:
                        # [FIX] 保留正文，只在尾部追加计数，绝不用计数器覆盖原文
                        record.msg = '%s [message_id=%s repeat_count=%d added=%d]' % (
                            body, message_id, total_count, count)
                    else:
                        record.msg = '%s [message_id=%s repeat_count=%d]' % (body, message_id, count)
                    line = self.format(record) + '\n'
                    if len(line.encode('utf-8')) > 32 * 1024:
                        line = line[:8192] + ' [truncated]\n'
                    line_size = len(line.encode('utf-8'))

                    if current_size + line_size > self.maxBytes - 256:
                        self._rotate_files()
                        current_size = 0

                    self.stream.write(line)
                    self.stream.flush()
                    self._pending.pop(key, None)
                    current_size += line_size
                    self._seen[key] = [total_count, now]
                    self._seen.move_to_end(key)

                if self._omitted:
                    self._write_capacity_notice()
                logging.FileHandler.flush(self)
        except Exception:
            # 保留 _pending / _deferred，下一轮继续尝试；绝不静默丢弃整批
            import sys
            sys.stderr.write('RAMDisk log batch unavailable; batch retained for retry\n')
        finally:
            self._pending_bytes = sum(
                len(key[4].encode('utf-8')) + len(key[5].encode('utf-8')) + 256
                for key in list(self._pending.keys()) + list(self._deferred.keys()))
            self.release()

    def close(self):
        self._closed_event.set()
        # 关闭前把被抑制的记录强制输出，避免丢失最后的计数
        try:
            self.acquire()
            try:
                for key, item in list(self._deferred.items()):
                    if key in self._pending:
                        self._pending[key][1] += item[1]
                    else:
                        self._pending[key] = item
                self._deferred.clear()
                # 让所有抑制窗口立即过期（用真实时间戳回退，而不是 0，避免被 TTL 当成陈旧条目淘汰）
                expire_ts = time.monotonic() - self.REPEAT_SUPPRESS - 1.0
                for key in list(self._seen.keys()):
                    self._seen[key] = [self._seen[key][0], expire_ts]
            finally:
                self.release()
        except Exception:
            pass
        self.flush()
        super().close()
