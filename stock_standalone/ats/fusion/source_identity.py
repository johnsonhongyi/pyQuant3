# -*- coding: utf-8 -*-
"""影子记录的实时与回放来源判定。"""


def is_replay_record(row):
    origin = str(row.get("writer_exe") or "").lower()
    source = str(row.get("source") or "").lower()
    return ("replay" in origin or "backfill" in origin or
            "replay" in source or "backfill" in source or row.get("writer_pid") == 0)
