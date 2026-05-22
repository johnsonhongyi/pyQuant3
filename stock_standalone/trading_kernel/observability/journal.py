from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


class JsonlJournal:
    def __init__(self, path: str = "logs/trading_kernel_trace.jsonl"):
        self.path = path
        self._lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("journal_ts", datetime.now().isoformat(timespec="seconds"))
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(_to_plain(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value

