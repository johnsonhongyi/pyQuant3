"""Background persistence drain with a single shared shutdown deadline."""
import multiprocessing
import os
import threading
import time


class ShutdownDrain:
    def __init__(self, tasks, deadline):
        self.deadline = deadline
        self.done = threading.Event()
        self.errors = []
        self._thread = threading.Thread(target=self._run, args=(tasks,),
                                        name='ATS-ShutdownDrain', daemon=True)
        self._thread.start()

    def _run(self, tasks):
        try:
            for name, task in tasks:
                if time.monotonic() >= self.deadline:
                    self.errors.append(name + ': deadline exceeded')
                    break
                try:
                    if task() is False:
                        self.errors.append(name + ': drain failed')
                except Exception as exc:
                    self.errors.append(name + ': ' + str(exc))
        finally:
            self.done.set()


def wait_for_threads(threads, deadline):
    """Join owned cleanup workers within one deadline, before interpreter shutdown."""
    for thread in threads:
        if thread is None:
            continue
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if thread.is_alive():
            return False
    return True


def reap_multiprocessing_children(deadline):
    """Retire this ATS process's remaining workers and their descendant process trees."""
    try:
        import psutil
    except ImportError:
        psutil = None

    children = multiprocessing.active_children()
    descendants = []
    if psutil is not None:
        for child in children:
            try:
                if child.is_alive():
                    p = psutil.Process(child.pid)
                    descendants.extend(p.children(recursive=True))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # 1. 先递归终止所有孙子孤儿后代进程 (例如 Nuitka Onefile bootstrap 派生的 worker payload)
        for desc in descendants:
            try:
                desc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    # 2. 终止直属 daemon 子进程
    for child in children:
        if child.daemon and child.is_alive():
            child.terminate()

    # 3. 有界等待直属子进程
    for child in children:
        child.join(timeout=max(0.0, deadline - time.monotonic()))
        if child.is_alive():
            try:
                child.kill()
                child.join(timeout=0.2)
            except Exception:
                pass
            if child.is_alive():
                return False

    # 4. 确保后代进程彻底退场
    if psutil is not None:
        for desc in descendants:
            try:
                desc.wait(timeout=max(0.0, min(0.5, deadline - time.monotonic())))
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                try:
                    desc.kill()
                    desc.wait(timeout=max(0.0, deadline - time.monotonic()))
                except psutil.NoSuchProcess:
                    pass
                except (psutil.TimeoutExpired, psutil.AccessDenied):
                    return False

    return True


def start_exit_watchdog(timeout_seconds=1.5, exit_code=0):
    """Bound packaged interpreter teardown; call only after durable cleanup succeeds."""
    def force_exit():
        threading.Event().wait(max(0.0, timeout_seconds))
        # Logging and executor atexit hooks may themselves be the blocked resource.
        # Do not write to those resources from the watchdog.
        os._exit(exit_code)

    worker = threading.Thread(target=force_exit, name='ATS-ExitWatchdog', daemon=True)
    worker.start()
    return worker
