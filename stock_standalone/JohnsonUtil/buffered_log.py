"""Bounded, deduplicated log batches on RAMDisk; local copy is closing-only."""
import copy
import hashlib
import logging
from logging.handlers import RotatingFileHandler
from collections import OrderedDict
import os
import threading


class BufferedRamLogHandler(RotatingFileHandler):
    INTERVAL = 60.0
    MAX_KEYS = 1024
    MAX_PENDING_BYTES = 2 * 1024 * 1024

    def __init__(self, filename, **kwargs):
        self._pending = OrderedDict()
        self._seen = OrderedDict()
        self._pending_bytes = 0
        self._omitted = 0
        self._closed_event = threading.Event()
        self._archive_target = os.path.abspath(filename)
        self._runtime_ready = False
        # Do not open the local file, including during logging initialization.
        kwargs['delay'] = True
        super().__init__(filename, **kwargs)
        threading.Thread(target=self._batch_loop, daemon=True, name='RamLogBatch').start()

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

    def flush(self):
        if not hasattr(self, '_pending'):
            return
        self.acquire()
        try:
            if not self._pending:
                return
            if not self._runtime_ready:
                # Deferred import avoids LoggerFactory/commonTips initialization cycles.
                from linkage_storage import runtime_file
                self.baseFilename = runtime_file(self._archive_target, max_bytes=5 * 1024 * 1024)
                # One bounded log file per logger path; no persistent rotation history.
                self.backupCount = 0
                self._runtime_ready = True
            from ats.persistence_lock import directory_write_lock
            with directory_write_lock(os.path.dirname(self.baseFilename), timeout=0.25):
                pending = list(self._pending.items())
                if self.stream is None:
                    self.stream = self._open()
                current_size = os.path.getsize(self.baseFilename)
                for key, (record, count) in pending:
                    record = copy.copy(record)
                    previous_count = self._seen.get(key, 0)
                    total_count = previous_count + count
                    original_message = record.msg
                    message_id = hashlib.sha256(repr(key).encode('utf-8')).hexdigest()[:16]
                    if previous_count:
                        record.msg = '[repeat message_id=%s count=%d added=%d]' % (message_id, total_count, count)
                        record.exc_text = None
                    else:
                        record.msg = '%s [message_id=%s repeat_count=%d]' % (record.msg, message_id, count)
                    line = self.format(record) + '\n'
                    if len(line.encode('utf-8')) > 32 * 1024:
                        line = line[:8192] + ' [truncated]\n'
                    if self.stream is None:
                        self.stream = self._open()
                    line_size = len(line.encode('utf-8'))
                    if current_size + line_size > self.maxBytes - 256:
                        self.stream.close()
                        self.stream = open(self.baseFilename, 'w', encoding='utf-8')
                        current_size = 0
                        self._seen.clear()
                        total_count = count
                        record.msg = original_message + ' [repeat_count=%d]' % count
                        line = self.format(record) + '\n'
                        line_size = len(line.encode('utf-8'))
                    self.stream.write(line)
                    self.stream.flush()
                    self._pending.pop(key, None)
                    current_size += line_size
                    self._seen[key] = total_count
                    self._seen.move_to_end(key)
                    if len(self._seen) > self.MAX_KEYS:
                        self._seen.popitem(last=False)
                if self._omitted:
                    self.stream.write('[log capacity] omitted_count=%d\n' % self._omitted)
                    self._omitted = 0
                logging.FileHandler.flush(self)
        except Exception:
            # The console handler still receives records; never fall back to SSD.
            import sys
            sys.stderr.write('RAMDisk log batch unavailable; local disk write skipped\n')
        finally:
            self._pending_bytes = sum(
                len(key[4].encode('utf-8')) + len(key[5].encode('utf-8')) + 256
                for key in self._pending)
            self.release()

    def close(self):
        self._closed_event.set()
        self.flush()
        super().close()
