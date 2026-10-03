"""Bounded priority admission for a single transport owner."""
import threading
import time
import copy
import os
from contextlib import contextmanager


def send_bytes_deadline(connection, payload, deadline):
    """Cancel the actual Windows overlapped write, including a non-reading child."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('transport_send_timeout')
    if os.name != 'nt':
        connection.send_bytes(payload)
        return
    import _winapi
    operation, error = _winapi.WriteFile(connection.fileno(), payload, overlapped=True)
    timed_out = False
    try:
        if error == _winapi.ERROR_IO_PENDING:
            wait = _winapi.WaitForMultipleObjects([operation.event], False,
                max(0, int((deadline - time.monotonic()) * 1000)))
            if wait == _winapi.WAIT_TIMEOUT:
                timed_out = True
                operation.cancel()
    except BaseException:
        operation.cancel()
        raise
    finally:
        written, error = operation.GetOverlappedResult(True)
    if timed_out:
        raise TimeoutError('transport_send_timeout')
    if error or written != len(payload):
        raise OSError(error, 'incomplete transport write')


def recv_bytes_deadline(connection, deadline, max_bytes=16 * 1024 * 1024):
    if os.name != 'nt':
        return connection.recv_bytes(maxlength=max_bytes)
    import _winapi
    chunks, size, read_size = [], 0, 128
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError('transport_receive_timeout')
        operation, error = _winapi.ReadFile(connection.fileno(), read_size, overlapped=True)
        timed_out = False
        try:
            if error == _winapi.ERROR_IO_PENDING:
                wait = _winapi.WaitForMultipleObjects([operation.event], False,
                    max(0, int((deadline - time.monotonic()) * 1000)))
                if wait == _winapi.WAIT_TIMEOUT:
                    timed_out = True
                    operation.cancel()
        except BaseException:
            operation.cancel()
            raise
        finally:
            count, error = operation.GetOverlappedResult(True)
        if timed_out:
            raise TimeoutError('transport_receive_timeout')
        if error not in (0, _winapi.ERROR_MORE_DATA):
            raise OSError(error, 'transport read failed')
        chunks.append(bytes(operation.getbuffer()))
        size += count
        if size > max_bytes:
            raise ValueError('transport response too large')
        if error == 0:
            return b''.join(chunks)
        read_size = _winapi.PeekNamedPipe(connection.fileno())[1]
        if read_size <= 0 or size + read_size > max_bytes:
            raise ValueError('invalid transport message length')


@contextmanager
def deadline_lock(lock, deadline):
    if not lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise TimeoutError('connection_lock_timeout')
    try:
        yield
    finally:
        lock.release()


class RequestGate:
    def __init__(self, capacity=8, ack_capacity=8):
        self._condition = threading.Condition()
        self._waiting = []
        self._active = False
        self._sequence = 0
        self.capacity, self.ack_capacity = capacity, ack_capacity

    @contextmanager
    def enter(self, deadline, priority=1):
        with self._condition:
            if len(self._waiting) >= self.capacity + (self.ack_capacity if priority == 0 else 0):
                raise RuntimeError("request_queue_full")
            self._sequence += 1
            ticket = (priority, self._sequence)
            self._waiting.append(ticket)
            try:
                while self._active or ticket != min(self._waiting):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("request_queue_timeout")
                    self._condition.wait(remaining)
                if time.monotonic() >= deadline:
                    raise TimeoutError("request_queue_timeout")
                self._waiting.remove(ticket)
                self._active = True
            except BaseException:
                self._waiting.remove(ticket)
                self._condition.notify_all()
                raise
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


class SingleFlight:
    """Share only currently running identical calls; never cache a future quote."""
    def __init__(self, capacity=8):
        self._lock = threading.Lock()
        self._calls = {}
        self.capacity = capacity

    def run(self, key, call, timeout=30.0):
        with self._lock:
            state = self._calls.get(key)
            owner = state is None
            if owner:
                if len(self._calls) >= self.capacity:
                    raise RuntimeError('inflight_capacity_exceeded')
                state = {'ready': threading.Event()}
                self._calls[key] = state
        if owner:
            try:
                state['result'] = call()
            except BaseException as exc:
                state['error'] = exc
            finally:
                with self._lock:
                    self._calls.pop(key, None)
                    state['ready'].set()
        elif not state['ready'].wait(timeout):
            raise TimeoutError('inflight_wait_timeout')
        if 'error' in state:
            raise state['error']
        return copy.deepcopy(state['result'])
