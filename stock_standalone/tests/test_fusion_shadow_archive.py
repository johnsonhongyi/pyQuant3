import gzip
import json
from datetime import datetime

import pytest

from ats.fusion.history_events import HistoricalEvents
from ats.fusion.shadow_archive import (
    archive_day,
    cleanup_candidates,
    archive_finished_days,
    cleanup_expired_archives,
)
from ats.fusion.paper_follow import read_shadow_days
from ats.fusion.review import load_records


def test_archive_preserves_source_and_history_can_read_compressed(tmp_path):
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    source = directory / "2026-10-29.jsonl"
    row = {"ts": datetime(2026, 10, 29, 10, 0).timestamp(), "code": "000995",
           "trade_date": "2026-10-29", "fusion": {"tier": 2, "rar": 50}}
    payload = (json.dumps(row) + "\n").encode()
    source.write_bytes(payload)
    result = archive_day(str(source), "2026-10-30")
    assert source.read_bytes() == payload
    with gzip.open(result["archive"], "rb") as stream:
        assert stream.read() == payload
    assert cleanup_candidates(str(directory), "2026-10-30")[0]["requires_revalidation"]
    source.unlink()  # 仅隔离测试数据，模拟已迁移的历史文件
    events = HistoricalEvents(str(tmp_path), "2026-10-29")
    assert events.stats["gradient_file_present"]
    assert events.stats["gradient"] == 1


def test_archive_rejects_current_day_and_existing_archive(tmp_path):
    source = tmp_path / "2026-10-30.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        archive_day(str(source), "2026-10-30")
    archive_day(str(source), "2026-10-31")
    with pytest.raises(FileExistsError):
        archive_day(str(source), "2026-10-31")
    assert source.exists()


def test_corrupt_archive_is_reported(tmp_path):
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    (directory / "2026-10-29.jsonl.gz").write_bytes(b"not a gzip file")
    events = HistoricalEvents(str(tmp_path), "2026-10-29")
    assert events.stats["errors"]
    assert events.stats["gradient"] == 0


def test_truncated_archive_does_not_leak_partial_events(tmp_path):
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    archive = directory / "2026-10-29.jsonl.gz"
    row = {"ts": datetime(2026, 10, 29, 10, 0).timestamp(), "code": "000995", "fusion": {"tier": 2}}
    archive.write_bytes(gzip.compress((json.dumps(row) + "\n").encode())[:-4])
    events = HistoricalEvents(str(tmp_path), "2026-10-29")
    assert events.stats["errors"] and not events.events
    assert events.stats["gradient"] == 0


def test_archive_directly_to_separate_storage(tmp_path):
    runtime = tmp_path / "runtime"
    persistent = tmp_path / "persistent"
    runtime.mkdir()
    persistent.mkdir()
    source = runtime / "2026-10-29.jsonl"
    source.write_bytes(b"example\n" * 5000)
    result = archive_day(str(source), "2026-10-30", str(persistent))
    assert result["archive"] == str(persistent / "2026-10-29.jsonl.gz")
    assert source.is_file()
    assert not (persistent / source.name).exists()
    assert result["archive_bytes"] < result["source_bytes"]


def test_cross_day_and_review_read_archive_without_duplicate(tmp_path):
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    source = directory / "2026-10-29.jsonl"
    source.write_text(json.dumps({"code": "000995", "ts": 1}) + "\n", encoding="utf-8")
    archive_day(str(source), "2026-10-30")
    series, errors = read_shadow_days(str(tmp_path), "2026-10-30")
    assert errors == 0 and len(series["2026-10-29"]["000995"]) == 1
    source.unlink()
    series, errors = read_shadow_days(str(tmp_path), "2026-10-30")
    assert errors == 0 and len(series["2026-10-29"]["000995"]) == 1
    assert len(load_records("2026-10-29", str(tmp_path))) == 1


def test_ui_loads_compressed_day(tmp_path, monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    source = directory / "2026-10-29.jsonl"
    source.write_text(json.dumps({"code": "000995", "name": "test", "ts": datetime(2026, 10, 29, 10).timestamp(),
                                  "fusion": {"tier": 2, "rar": 50}}) + "\n", encoding="utf-8")
    archive_day(str(source), "2026-10-30")
    source.unlink()
    monkeypatch.setattr(ui, "load_config_node", lambda *args: str(tmp_path))
    assert ui._resolve_day_file("2026-10-29").endswith(".jsonl.gz")
    assert ui.load_live_rows("2026-10-29", allow_fallback=False)[0]["code"] == "000995"
    assert len(ui.load_live_series("2026-10-29", allow_fallback=False)["000995"]) == 1


def test_replay_records_cannot_enter_live_storage(monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    monkeypatch.setattr(ui, "_shadow_storage_paths", lambda *a: (_ for _ in ()).throw(AssertionError("must not write")))
    assert ui.persist_shadow_records([{"code": "000995", "source": "backfill"}], "2026-10-29") == 0


def test_background_batch_archives_only_settled_prior_days(tmp_path):
    import os
    old = tmp_path / "2026-10-28.jsonl"
    recent = tmp_path / "2026-10-29.jsonl"
    current = tmp_path / "2026-10-30.jsonl"
    for path in (old, recent, current):
        path.write_text('{}\n', encoding='utf-8')
    os.utime(old, (100, 100))
    os.utime(recent, (950, 950))
    os.utime(current, (100, 100))
    result = archive_finished_days(str(tmp_path), "2026-10-30", now=1000, settle_seconds=120)
    assert len(result["archived"]) == 1 and not result["errors"]
    assert (tmp_path / "2026-10-28.jsonl.gz").exists()
    assert not (tmp_path / "2026-10-29.jsonl.gz").exists()
    assert not (tmp_path / "2026-10-30.jsonl.gz").exists()
    assert old.exists()


def test_cleanup_expired_archives_60_days_and_300mb_cap(tmp_path):
    # 1. 超过 60 天的 .jsonl.gz 自动删除
    old_gz = tmp_path / "2026-08-01_1001.jsonl.gz"
    recent_gz = tmp_path / "2026-10-01_1002.jsonl.gz"
    sibling_gz = tmp_path / "2026-07-15_1003.jsonl.gz"
    sibling_raw = tmp_path / "2026-07-15_1003.jsonl"

    old_gz.write_bytes(b"x" * 1024)
    recent_gz.write_bytes(b"y" * 1024)
    sibling_gz.write_bytes(b"z" * 1024)
    sibling_raw.write_bytes(b"{}\n")

    res = cleanup_expired_archives(
        str(tmp_path), "2026-11-03", keep_archive_days=60, max_archive_mb=300.0
    )
    assert str(old_gz) in res["removed"]
    assert not old_gz.exists()
    # 60天内的归档保留
    assert recent_gz.exists()
    # 尚有同名未清理 .jsonl 源文件的归档受保护不删
    assert sibling_gz.exists()
    sibling_raw.unlink()

    # 2. 总容量上限淘汰最老归档（模拟小上限 3000 bytes），同时保护近 15 天归档
    mid_old_1 = tmp_path / "2026-09-10_2001.jsonl.gz"  # 距 11-03 超过 15 天，但不足 60 天
    mid_old_2 = tmp_path / "2026-09-20_2002.jsonl.gz"  # 距 11-03 超过 15 天，但不足 60 天
    protected_recent = tmp_path / "2026-10-28_2003.jsonl.gz"  # 距 11-03 不足 15 天（受保护）

    mid_old_1.write_bytes(b"a" * 1500)
    mid_old_2.write_bytes(b"b" * 1500)
    protected_recent.write_bytes(b"c" * 1500)

    res2 = cleanup_expired_archives(
        str(tmp_path),
        "2026-11-03",
        keep_archive_days=60,
        max_archive_mb=3000 / (1024.0 * 1024.0),
        min_keep_days=15,
    )
    assert not sibling_gz.exists()
    assert not mid_old_1.exists()
    assert protected_recent.exists()
    assert res2["total_bytes_after"] <= 3000
    assert not res2["errors"]
