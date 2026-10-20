"""RAMDisk-only, cross-process minute auction samples (never minute trades)."""
from contextlib import closing
import json
import math
import sqlite3


def _path():
    from linkage_storage import configured_ramdisk_root
    return configured_ramdisk_root() / "sbc_auction.sqlite3"


def load_samples(code, day):
    path = _path()
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1)) as db:
        result = []
        for row in db.execute("SELECT payload FROM samples WHERE code=? AND day=? ORDER BY minute", (code, day)):
            sample = json.loads(row[0])
            if not isinstance(sample, dict) or sample.get("date") != day:
                continue
            try:
                valid_price = math.isfinite(float(sample.get("price", 0))) and float(sample.get("price", 0)) > 0
            except (TypeError, ValueError):
                valid_price = False
            if (valid_price and "09:15" <= str(sample.get("time_only", "")) < "09:30"
                    and sample.get("kind") in ("auction_indicative", "auction_open")):
                result.append(sample)
        return result


def save_samples(code, day, samples):
    path = _path()
    with closing(sqlite3.connect(str(path), timeout=0.1)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS samples(code TEXT,day TEXT,minute TEXT,observed TEXT,payload TEXT,PRIMARY KEY(code,day,minute))")
        for sample in samples:
            if sample.get("date") != day:
                continue
            db.execute("INSERT INTO samples VALUES(?,?,?,?,?) ON CONFLICT(code,day,minute) DO UPDATE SET observed=excluded.observed,payload=excluded.payload WHERE excluded.observed>=samples.observed",
                       (code, day, sample["time_only"], sample["observed_at"], json.dumps(sample, ensure_ascii=False)))
