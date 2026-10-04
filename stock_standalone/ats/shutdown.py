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
    """Retire this ATS process's remaining workers before a packaged hard exit."""
    children = multiprocessing.active_children()
    # Match multiprocessing's normal exit policy for daemon children. Perform
    # it before the watchdog can bypass the interpreter's atexit cleanup.
    for child in children:
        if child.daemon and child.is_alive():
            child.terminate()
    for child in children:
        child.join(timeout=max(0.0, deadline - time.monotonic()))
        if child.is_alive():
            return False
    return True


def start_exit_watchdog(timeout_seconds=5.0, exit_code=0):
    """Bound packaged interpreter teardown; call only after durable cleanup succeeds."""
    def force_exit():
        threading.Event().wait(max(0.0, timeout_seconds))
        # Logging and executor atexit hooks may themselves be the blocked resource.
        # Do not write to those resources from the watchdog.
        os._exit(exit_code)

    worker = threading.Thread(target=force_exit, name='ATS-ExitWatchdog', daemon=True)
    worker.start()
    return worker
