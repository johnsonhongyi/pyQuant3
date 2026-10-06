#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

from concurrent.futures import FIRST_COMPLETED, wait


def bounded_results(executor, items, worker, max_pending):
    """Yield (item, result, error) while keeping only a small queue in flight."""
    source = iter(items)
    pending = {}
    limit = max(1, int(max_pending))

    def fill_queue():
        while len(pending) < limit:
            try:
                item = next(source)
            except StopIteration:
                return
            pending[executor.submit(worker, item)] = item

    fill_queue()
    while pending:
        completed, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in completed:
            item = pending.pop(future)
            try:
                result = future.result()
                error = None
            except Exception as exc:
                result = None
                error = "%s: %s" % (type(exc).__name__, exc)
            yield item, result, error
            del future
            fill_queue()
