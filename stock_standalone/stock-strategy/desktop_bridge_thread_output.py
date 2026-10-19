"""Thread-safe stdout/stderr routing shared by in-process desktop bridges."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager


class _RoutedTextOutput:
    def __init__(self, router, stream_name: str):
        self.router = router
        self.stream_name = stream_name

    @property
    def encoding(self):
        return getattr(self.router.base_stream(self.stream_name), "encoding", None) or "utf-8"

    @property
    def errors(self):
        return getattr(self.router.base_stream(self.stream_name), "errors", None) or "replace"

    def write(self, value):
        if not isinstance(value, str):
            value = str(value)
        return self.router.write(self.stream_name, value)

    def flush(self):
        self.router.flush(self.stream_name)

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


class _ThreadOutputRouter:
    def __init__(self):
        self._lock = threading.RLock()
        self._routes = []
        self._base_stdout = None
        self._base_stderr = None
        self._stdout_proxy = _RoutedTextOutput(self, "stdout")
        self._stderr_proxy = _RoutedTextOutput(self, "stderr")

    def base_stream(self, stream_name: str):
        with self._lock:
            return self._base_stdout if stream_name == "stdout" else self._base_stderr

    def register(self, stream, thread_prefixes: tuple[str, ...]):
        with self._lock:
            if not self._routes:
                self._base_stdout, self._base_stderr = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = self._stdout_proxy, self._stderr_proxy
            route = {
                "owner_thread": threading.get_ident(),
                "thread_prefixes": tuple(thread_prefixes),
                "stream": stream,
            }
            self._routes.append(route)
            return route

    def unregister(self, route):
        with self._lock:
            if route in self._routes:
                self._routes.remove(route)
            self._restore_if_idle()

    def _restore_if_idle(self):
        if self._routes:
            return
        if sys.stdout is self._stdout_proxy:
            sys.stdout = self._base_stdout
        if sys.stderr is self._stderr_proxy:
            sys.stderr = self._base_stderr
        self._base_stdout = self._base_stderr = None

    def _route_for_current_thread(self):
        thread = threading.current_thread()
        thread_id = thread.ident
        for route in reversed(self._routes):
            if route["owner_thread"] == thread_id:
                return route
        for route in reversed(self._routes):
            if any(thread.name.startswith(prefix) for prefix in route["thread_prefixes"]):
                return route
        return None

    @staticmethod
    def _write_route(route, value: str):
        route["stream"].write(value.encode("utf-8", errors="replace"))
        return len(value)

    def write(self, stream_name: str, value: str):
        with self._lock:
            fallback = self._base_stdout if stream_name == "stdout" else self._base_stderr
            route = self._route_for_current_thread()
            if route is not None:
                try:
                    return self._write_route(route, value)
                except (OSError, ValueError):
                    self._routes.remove(route)
                    self._restore_if_idle()
            if fallback is None:
                return len(value)
            try:
                return fallback.write(value)
            except (OSError, ValueError):
                return len(value)

    def flush(self, stream_name: str):
        with self._lock:
            fallback = self._base_stdout if stream_name == "stdout" else self._base_stderr
            route = self._route_for_current_thread()
            if route is not None:
                try:
                    route["stream"].flush()
                    return
                except (OSError, ValueError):
                    self._routes.remove(route)
                    self._restore_if_idle()
            if fallback is not None:
                try:
                    fallback.flush()
                except (OSError, ValueError):
                    pass


_ROUTER = _ThreadOutputRouter()


@contextmanager
def routed_thread_output(stream, *thread_prefixes: str):
    """Route only this bridge's threads to its log without stacking global proxies."""
    route = _ROUTER.register(stream, tuple(thread_prefixes))
    try:
        yield
    finally:
        _ROUTER.unregister(route)
