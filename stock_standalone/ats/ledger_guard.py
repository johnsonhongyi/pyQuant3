"""Short ledger mutation/capture critical sections shared by all ATS writers."""
from functools import wraps
from contextlib import nullcontext


def ledger_guard(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        ledger = getattr(self, 'signal_ledger', self)
        lock = getattr(ledger, '_mutation_lock', None)
        with lock if lock is not None else nullcontext():
            return method(self, *args, **kwargs)
    return guarded
