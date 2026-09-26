"""Bounded cross-process exclusion for read/modify/replace transactions."""
from contextlib import contextmanager
import errno
import os
import time


class DirectoryBusy(TimeoutError):
    pass


@contextmanager
def directory_write_lock(directory, timeout=0.25):
    """Cooperating writers lock byte zero; the OS releases it on process exit."""
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, '.ats-write.lock'), 'a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise DirectoryBusy('ATS data directory is busy') from exc
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def replace_with_retry(source, target):
    """Retry only Windows sharing violations; all other failures stay visible."""
    for delay in (0.0, 0.01, 0.02, 0.04):
        if delay:
            time.sleep(delay)
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (32, 33) or delay == 0.04:
                raise
