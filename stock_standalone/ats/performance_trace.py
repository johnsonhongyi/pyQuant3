"""Opt-in, bounded asynchronous performance diagnostics for the ATS process."""
import atexit
import logging
import logging.handlers
import os
import queue
import sys

perf_logger = logging.getLogger("ats.performance_trace")
perf_logger.propagate = False
perf_logger.disabled = True
_listener = None
_queue_handler = None


class _DroppingQueueHandler(logging.handlers.QueueHandler):
    """Never wait for disk or a full queue on the UI thread."""
    def __init__(self, records):
        super().__init__(records)
        self.dropped = 0

    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1


class _BoundedQueueListener(logging.handlers.QueueListener):
    def enqueue_sentinel(self):
        try:
            self.queue.put_nowait(self._sentinel)
        except queue.Full:
            # Reserve room for shutdown without blocking the producer.
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.queue.put_nowait(self._sentinel)

    def stop(self):
        thread = self._thread
        if thread is None:
            return True
        self.enqueue_sentinel()
        thread.join(timeout=2.0)
        if thread.is_alive():
            return False
        self._thread = None
        return True


def configure_performance_trace(root, argv, environ=None):
    """Consume the ATS flag before Qt sees it, preserving unrelated arguments."""
    environ = os.environ if environ is None else environ
    enabled = "--perf-log" in argv or environ.get("FUSION_PERF_TRACE") == "1"
    argv[:] = [arg for arg in argv if arg != "--perf-log"]
    return start_performance_trace(root, enabled=enabled)


def start_performance_trace(root, enabled=False):
    """Start one writer per process; return the log path, or None on failure."""
    global _listener, _queue_handler
    if not enabled:
        return None
    if _listener is not None:
        return getattr(_listener, "performance_path", None)
    try:
        directory = os.path.join(root, "logs", "performance")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "ats_perf_{}.log".format(os.getpid()))
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8", delay=True)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        records = queue.Queue(maxsize=4096)
        handler = _DroppingQueueHandler(records)
        listener = _BoundedQueueListener(records, file_handler)
        listener.performance_path = path
        listener.start()
        _listener, _queue_handler = listener, handler
        perf_logger.handlers = [handler]
        perf_logger.setLevel(logging.DEBUG)
        perf_logger.disabled = False
        perf_logger.info("[FusionPerf] start pid=%s executable=%s", os.getpid(), sys.executable)
        atexit.register(stop_performance_trace)
        return path
    except (OSError, RuntimeError, ValueError):
        logging.getLogger(__name__).exception("Unable to start ATS performance logging")
        return None


def stop_performance_trace():
    """Flush at process shutdown; never wait on the Qt event loop during operation."""
    global _listener, _queue_handler
    listener, handler = _listener, _queue_handler
    if listener is None:
        return
    perf_logger.info("[FusionPerf] stop dropped_records=%s", handler.dropped)
    perf_logger.disabled = True
    perf_logger.handlers = []
    _listener = _queue_handler = None
    try:
        stopped = listener.stop()
    except queue.Full:
        stopped = False
    if stopped:
        for output in listener.handlers:
            output.close()
    else:
        logging.getLogger(__name__).warning("ATS performance log flush timed out; remaining records may be lost")
