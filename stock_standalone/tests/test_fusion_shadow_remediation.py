import gzip
import json
import multiprocessing
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from ats.fusion import shadow_io, shadow_writer
from ats.fusion.cross_day import build_cross_day
from ats.fusion.discovery_audit import _price_at
from ats.fusion.history_events import HistoricalEvents
from ats.fusion.paper_follow import read_shadow_days
from ats.fusion.review import load_records
from ats.fusion.shadow import FusionShadow

DAY = "2026-10-29"


def row(index=0):
    return {"code": "000001", "name": "test", "ts": datetime(2026, 10, 29, 10).timestamp() + index,
            "price": 10 + index, "fusion": {"tier": 2}, "source": "live_strategy"}


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch):
    monkeypatch.setattr(shadow_writer, "ram_directory", lambda directory: None)
    monkeypatch.setattr(shadow_io, "ram_directory", lambda directory: None)


def test_full_day_rotates_before_enforcing_next_day_limit(tmp_path):
    shadow = FusionShadow(config={"enabled": False, "max_records_per_day": 1}, root=str(tmp_path))
    try:
        shadow._append(row(), DAY)
        shadow._append(row(1), DAY)
        shadow._append(row(2), "2026-10-30")
        assert shadow._fh_day == "2026-10-30"
        assert shadow._written_today == 1
        shadow.flush()
        directory = tmp_path / "logs" / "fusion_shadow"
        assert len(shadow_io.read_paths(shadow_io.day_paths([directory], DAY))[0]) == 1
        assert len(shadow_io.read_paths(shadow_io.day_paths([directory], "2026-10-30"))[0]) == 1
    finally:
        shadow.close()


def test_writer_rejects_replay_before_opening_storage(tmp_path):
    shadow = FusionShadow(config={"enabled": False}, root=str(tmp_path))
    shadow._append({**row(), "source": "replay_archive"}, DAY)
    assert shadow._fh is None
    assert not list(tmp_path.rglob("*.jsonl"))


def test_bad_timestamps_do_not_cancel_valid_cross_day_rows():
    records = [row(), {"ts": "bad"}, {"ts": float("nan")}, {"ts": float("inf")}, None]
    assert build_cross_day({DAY: {"000001": records}}, DAY)[0]["reference"] == 10


def test_ram_close_persists_and_runtime_loss_keeps_pending_records(tmp_path, monkeypatch):
    ram = tmp_path / "ram"
    local = tmp_path / "local"
    monkeypatch.setattr(shadow_writer, "ram_directory", lambda directory: str(ram))
    writer = shadow_writer.ShadowWriter(str(local), DAY)
    writer.write(json.dumps(row()) + "\n")
    assert writer.on_ramdisk and not os.path.exists(writer.local)
    writer.checkpoint()
    writer.write(json.dumps(row(1)) + "\n")
    original = os.path.isfile
    monkeypatch.setattr(os.path, "isfile", lambda path: False if path == writer.path else original(path))
    writer.write(json.dumps(row(2)) + "\n")
    assert not writer.on_ramdisk
    writer.close()
    rows, errors = shadow_io.read_paths([writer.local])
    assert not errors and [r["price"] for r in rows] == [10, 11, 12]


def test_close_atomic_failure_keeps_old_copy_and_can_retry(tmp_path, monkeypatch):
    ram = tmp_path / "ram"
    monkeypatch.setattr(shadow_writer, "ram_directory", lambda directory: str(ram))
    writer = shadow_writer.ShadowWriter(str(tmp_path / "local"), DAY)
    writer.write(json.dumps(row()) + "\n")
    writer.checkpoint()
    original = Path(writer.local).read_bytes()
    writer.write(json.dumps(row(1)) + "\n")
    replace = os.replace
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk unavailable")))
        with pytest.raises(OSError):
            writer.close()
        assert Path(writer.local).read_bytes() == original
        assert writer._pending and not writer._closed
    writer.close()
    assert len(shadow_io.read_paths([writer.local])[0]) == 2
    assert os.replace is replace


def test_restart_recovers_existing_ram_suffix_and_local_is_not_duplicated(tmp_path, monkeypatch):
    ram = tmp_path / "ram"
    local = tmp_path / "local"
    ram.mkdir()
    local.mkdir()
    name = "{}_{}.jsonl".format(DAY, os.getpid())
    first = (json.dumps(row()) + "\n").encode()
    second = (json.dumps(row(1)) + "\n").encode()
    (local / name).write_bytes(first)
    (ram / name).write_bytes(first + second)
    monkeypatch.setattr(shadow_writer, "ram_directory", lambda directory: str(ram))
    writer = shadow_writer.ShadowWriter(str(local), DAY)
    writer.write(json.dumps(row(2)) + "\n")
    writer.close()
    assert [r["price"] for r in shadow_io.read_paths([local / name])[0]] == [10, 11, 12]


def test_same_process_observers_share_one_writer(tmp_path):
    first = shadow_writer.open_writer(str(tmp_path), DAY)
    second = shadow_writer.open_writer(str(tmp_path), DAY)
    assert first is second
    first.write(json.dumps(row()) + "\n")
    first.close()
    second.write(json.dumps(row(1)) + "\n")
    second.close()
    assert len(shadow_io.read_paths([second.local])[0]) == 2


def _process_write(directory, ready):
    from ats.fusion import shadow_writer as module
    module.ram_directory = lambda directory: None
    writer = module.ShadowWriter(directory, DAY)
    ready.wait(10)
    for index in range(80):
        writer.write(json.dumps({**row(index), "writer_pid": os.getpid()}) + "\n")
    writer.close()


def test_spawned_process_shards_merge_without_losing_records(tmp_path):
    directory = str(tmp_path / "logs" / "fusion_shadow")
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    processes = [context.Process(target=_process_write, args=(directory, ready)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        ready.set()
        for process in processes:
            process.join(20)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
    paths = shadow_io.day_paths([directory], DAY)
    assert len(paths) == 2
    assert len(load_records(DAY, str(tmp_path))) == 160
    assert HistoricalEvents(str(tmp_path), DAY).stats["gradient"] == 160
    series, errors = read_shadow_days(str(tmp_path), DAY)
    assert errors == 0 and len(series[DAY]["000001"]) == 160


def test_shard_copies_and_gzip_are_not_double_counted(tmp_path):
    local, ram = tmp_path / "local", tmp_path / "ram"
    local.mkdir()
    ram.mkdir()
    name = DAY + "_123.jsonl"
    first = (json.dumps(row()) + "\n").encode()
    (local / name).write_bytes(first)
    (local / (name + ".gz")).write_bytes(gzip.compress(first))
    (ram / name).write_bytes(first + (json.dumps(row(1)) + "\n").encode())
    paths = shadow_io.day_paths([local, ram], DAY)
    assert len(paths) == 1 and len(shadow_io.read_paths(paths)[0]) == 2


def test_three_minute_prices_require_next_bar_and_drop_unconfirmed_tail():
    start = datetime(2026, 10, 29).timestamp()
    bars = np.array([(start + 9 * 3600 + 33 * 60, 10),
                     (start + 9 * 3600 + 36 * 60, 99)], dtype=[("time", "i8"), ("close", "f8")])
    assert _price_at({"000001": bars}, "000001", DAY, 9, 34) is None
    assert _price_at({"000001": bars}, "000001", DAY, 9, 37) == 10
    assert _price_at({"000001": bars}, "000001", DAY, 9, 40) == 10


def test_ui_merges_pid_fragments_and_refreshes_on_other_fragment_changes(tmp_path, monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    first, second = directory / (DAY + "_11.jsonl"), directory / (DAY + "_22.jsonl.gz")
    first.write_text(json.dumps(row()) + "\n", encoding="utf-8")
    second.write_bytes(gzip.compress((json.dumps(row(1)) + "\n").encode()))
    monkeypatch.setattr(ui, "load_config_node", lambda *args: str(tmp_path))
    series = ui.load_live_series(DAY, allow_fallback=False)
    assert len(series["000001"]) == 2
    assert ui.load_live_rows(DAY, allow_fallback=False)[0]["price"] == 11
    first.write_text(json.dumps(row(2)) + "\n", encoding="utf-8")
    assert ui.load_live_rows(DAY, allow_fallback=False)[0]["price"] == 12


def test_weekly_audit_reads_compressed_pid_production(tmp_path, monkeypatch):
    import pandas as pd
    from tools import audit_weekly_outcomes as weekly
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    event = {**row(), "pct": 1, "writer_pid": 11, "trade_date": DAY}
    (directory / (DAY + "_11.jsonl.gz")).write_bytes(gzip.compress((json.dumps(event) + "\n").encode()))
    replay = tmp_path / "replay.json.gz"
    replay.write_bytes(gzip.compress(json.dumps({"result": {"records": [], "meta": {}}}).encode()))
    monkeypatch.setattr(weekly, "read_replay_follow", lambda *args: {
        "status": "ready", "independent": True, "sources": {DAY: str(replay)}, "run_dir": "isolated"})
    start = "2026-10-28"
    daily = pd.DataFrame({"close": [9, 11]}, index=pd.MultiIndex.from_tuples([
        ("000001", pd.Timestamp(start)), ("000001", pd.Timestamp(DAY))]))
    result = weekly.audit({"entries": [{"code": "000001", "pct": 22.22}],
                           "start_date": start, "end_date": DAY, "label_source": "test"},
                          daily, {}, str(tmp_path), "isolated")
    assert result["rows"][0]["production"]["price"] == 10


def test_corrupt_pid_archive_does_not_discard_other_complete_shards(tmp_path):
    good = tmp_path / (DAY + "_11.jsonl.gz")
    bad = tmp_path / (DAY + "_22.jsonl.gz")
    data = (json.dumps(row()) + "\n").encode()
    good.write_bytes(gzip.compress(data))
    bad.write_bytes(gzip.compress(data)[:-4])
    records, errors = shadow_io.read_paths(shadow_io.day_paths([tmp_path], DAY))
    assert len(records) == 1 and errors


def test_shadow_io_unified_interface_and_corrupt_line_handling(tmp_path):
    directory = tmp_path / "shadow"
    directory.mkdir()
    # 1. 旧格式带有一行损坏数据
    legacy = directory / (DAY + ".jsonl")
    legacy.write_text(json.dumps(row(0)) + "\n{invalid_json}\n" + json.dumps(row(1)) + "\n", encoding="utf-8")
    # 2. PID分片
    shard = directory / (DAY + "_9999.jsonl")
    shard.write_text(json.dumps(row(2)) + "\n", encoding="utf-8")

    assert shadow_io.day_has_records(str(directory), DAY)
    assert not shadow_io.day_has_records(str(directory), "2026-01-01")

    files = shadow_io.list_day_files(str(directory), DAY)
    assert len(files) == 2

    records = list(shadow_io.iter_day_records(str(directory), DAY))
    # 验证跳过了无效json行，正确获取了3条有效记录
    assert len(records) == 3
    assert [r["price"] for r in records] == [10, 11, 12]


def test_sync_orphan_shards_harvests_crashed_process_shards(tmp_path, monkeypatch):
    monkeypatch.setattr("ats.fusion.shadow_archive._pid_alive", lambda pid: False)
    from ats.fusion.shadow_archive import _sync_orphan_shards
    ram = tmp_path / "ram"
    persist = tmp_path / "persist"
    ram.mkdir()
    persist.mkdir()

    now = 10000.0
    own_pid = 1234
    crashed_pid = 5678
    active_pid = 9999

    # 1. 模拟本进程 PID 分片（正常退出走 close()，收割时应跳过）
    own_file = ram / f"{DAY}_{own_pid}.jsonl"
    own_file.write_text(json.dumps(row(0)) + "\n", encoding="utf-8")
    os.utime(own_file, (now - 300, now - 300))

    # 2. 模拟崩溃进程的孤儿分片（mtime 300s 前，超过 settle 120s）
    crashed_file = ram / f"{DAY}_{crashed_pid}.jsonl"
    crashed_file.write_text(json.dumps(row(1)) + "\n", encoding="utf-8")
    os.utime(crashed_file, (now - 300, now - 300))

    # 3. 模拟活跃写入中分片（mtime 10s 前，未 settle）
    active_file = ram / f"{DAY}_{active_pid}.jsonl"
    active_file.write_text(json.dumps(row(2)) + "\n", encoding="utf-8")
    os.utime(active_file, (now - 10, now - 10))

    result = _sync_orphan_shards(str(ram), str(persist), own_pid=own_pid, settle_seconds=120, now=now)

    # 只有 crashed_pid 分片被收割
    assert result["synced"] == [f"{DAY}_{crashed_pid}.jsonl"]
    assert not result["errors"]

    # 检查 persist 目录已原子发布孤儿分片
    persisted_crashed = persist / f"{DAY}_{crashed_pid}.jsonl"
    assert persisted_crashed.exists()
    assert (persist / f"{DAY}_{active_pid}.jsonl").exists() is False
    assert (persist / f"{DAY}_{own_pid}.jsonl").exists() is False

    # 再次运行收割，已同步且未变化的分片不会重复写入
    result2 = _sync_orphan_shards(str(ram), str(persist), own_pid=own_pid, settle_seconds=120, now=now)
    assert result2["synced"] == []



def test_stream_iterator_does_not_publish_corrupt_gzip_prefix(tmp_path):
    archive = tmp_path / (DAY + "_123.jsonl.gz")
    archive.write_bytes(gzip.compress((json.dumps(row()) + "\n").encode())[:-4])
    iterator = shadow_io.iter_day_records(str(tmp_path), DAY)
    with pytest.raises(ValueError, match="不完整"):
        next(iterator)


def test_cleanup_requires_verified_archive_and_dead_pid(tmp_path, monkeypatch):
    from ats.fusion import shadow_archive as archive
    old = "2026-10-01_123.jsonl"
    source = tmp_path / old
    source.write_bytes(b"valid\n")
    archive.archive_day(str(source), DAY)
    monkeypatch.setattr(archive, "_pid_alive", lambda pid: True)
    assert not archive.cleanup_verified_shards(str(tmp_path), DAY)["removed"]
    monkeypatch.setattr(archive, "_pid_alive", lambda pid: False)
    (tmp_path / (old + ".gz")).write_bytes(gzip.compress(b"other\n"))
    assert archive.cleanup_verified_shards(str(tmp_path), DAY)["errors"]
    assert source.exists()
    (tmp_path / (old + ".gz")).write_bytes(gzip.compress(b"valid\n"))
    assert archive.cleanup_verified_shards(str(tmp_path), DAY)["removed"] == [str(source)]
    assert (tmp_path / (old + ".gz")).exists()


def test_pending_capacity_falls_back_without_dropping_record(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_writer, "ram_directory", lambda directory: str(tmp_path / "ram"))
    monkeypatch.setattr(shadow_writer, "MAX_PENDING_BYTES", 1)
    writer = shadow_writer.ShadowWriter(str(tmp_path / "local"), DAY)
    writer.write(json.dumps(row()) + "\n")
    assert not writer.on_ramdisk
    writer.close()
    assert len(shadow_io.read_paths([writer.local])[0]) == 1


def test_orphan_harvest_never_copies_live_idle_process(tmp_path, monkeypatch):
    from ats.fusion import shadow_archive as archive
    ram = tmp_path / "ram"
    ram.mkdir()
    source = ram / (DAY + "_123.jsonl")
    source.write_bytes(b"test\n")
    os.utime(source, (1, 1))
    monkeypatch.setattr(archive, "_pid_alive", lambda pid: True)
    result = archive._sync_orphan_shards(str(ram), str(tmp_path / "local"), now=1000)
    assert result == {"synced": [], "errors": []}


def test_ram_cleanup_requires_verified_physical_archive(tmp_path, monkeypatch):
    from ats.fusion import shadow_archive as archive
    ram, disk = tmp_path / "ram", tmp_path / "disk"
    ram.mkdir()
    disk.mkdir()
    source = ram / "2026-10-01_123.jsonl"
    source.write_bytes(b"test\n")
    archive.archive_day(str(source), DAY, str(disk))
    monkeypatch.setattr(archive, "_pid_alive", lambda pid: False)
    result = archive.cleanup_verified_shards(str(ram), DAY, archive_directory=str(disk))
    assert result["removed"] == [str(source)]
    assert (disk / (source.name + ".gz")).exists()


def test_live_ui_excludes_legacy_replay_records(tmp_path, monkeypatch):
    from ats.ui import fusion_ladder_dialog as ui
    directory = tmp_path / "logs" / "fusion_shadow"
    directory.mkdir(parents=True)
    records = [row(), {**row(1), "source": "replay_backfill", "writer_pid": 0}]
    (directory / (DAY + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    monkeypatch.setattr(ui, "load_config_node", lambda *args: str(tmp_path))
    assert ui.load_live_rows(DAY, allow_fallback=False)[0]["price"] == 10
    assert len(ui.load_live_series(DAY, allow_fallback=False)["000001"]) == 1
