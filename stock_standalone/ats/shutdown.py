"""Background persistence drain with a single shared shutdown deadline."""
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
