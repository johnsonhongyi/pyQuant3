"""Isolated shutdown persistence and read-only inspector contracts."""
import hashlib
import sqlite3
from contextlib import closing

import linkage_storage as storage
from runtime_data_viewer import inventory, preview


def test_forced_file_archive_bypasses_recent_marker(tmp_path):
    runtime = tmp_path / 'ram' / 'favorite_stocks.json'
    runtime.parent.mkdir()
    runtime.write_text('{"favorite_stocks":["600000"]}', encoding='utf-8')
    local = tmp_path / 'app' / runtime.name
    marker = runtime.with_name(runtime.name + '.archived_day')
    marker.write_text('old', encoding='utf-8')
    storage._archive_one(runtime, local, 4096)
    assert not local.exists()
    storage._archive_one(runtime, local, 4096, force=True)
    assert local.read_bytes() == runtime.read_bytes()
    assert marker.read_text(encoding='utf-8') != 'old'


def test_database_archive_preserves_source(tmp_path):
    runtime, local = tmp_path / 'runtime.sqlite3', tmp_path / 'local.sqlite3'
    with closing(sqlite3.connect(runtime)) as db:
        db.execute('CREATE TABLE linkage_operations (operation_id TEXT)')
        db.execute("INSERT INTO linkage_operations VALUES ('done-1')")
        db.commit()
    before = runtime.read_bytes()
    storage._archive_one(runtime, local, force=True)
    assert runtime.read_bytes() == before
    with closing(sqlite3.connect(local)) as db:
        assert db.execute('SELECT * FROM linkage_operations').fetchall() == [('done-1',)]
        assert db.execute('PRAGMA quick_check').fetchone() == ('ok',)


def test_failed_store_does_not_prevent_other_archives(tmp_path, monkeypatch):
    good = tmp_path / 'good.json'
    good.write_text('{}', encoding='utf-8')
    missing = tmp_path / 'missing.json'
    targets = {str(good): (good, tmp_path / 'saved.json', 1024),
               str(missing): (missing, tmp_path / 'missing-local.json', 1024)}
    monkeypatch.setattr(storage, '_archive_targets', targets)
    result = storage.persist_registered_runtime()
    assert result['saved'] == [str(tmp_path / 'saved.json')]
    assert str(tmp_path / 'missing-local.json') in result['failed']


def test_legacy_wal_does_not_replace_local_database(tmp_path):
    import pytest
    runtime, local = tmp_path / 'runtime.sqlite3', tmp_path / 'local.sqlite3'
    with closing(sqlite3.connect(runtime)) as db:
        db.execute('CREATE TABLE sample (value TEXT)')
        db.commit()
    local.write_bytes(b'original')
    local.with_name(local.name + '-wal').write_bytes(b'active')
    with pytest.raises(RuntimeError, match='legacy_writer'):
        storage._archive_one(runtime, local, force=True)
    assert local.read_bytes() == b'original'


def test_inspector_maps_selected_app_and_reads_bounded_tables(tmp_path):
    root, app = tmp_path / 'custom-ram' / 'instock_runtime', tmp_path / 'custom-app'
    name = 'system_linkage.sqlite3'
    identity = hashlib.sha256(str(app / name).casefold().encode()).hexdigest()[:16]
    directory = root / identity
    directory.mkdir(parents=True)
    runtime = directory / name
    with closing(sqlite3.connect(runtime)) as db:
        db.execute('CREATE TABLE sample (value TEXT)')
        db.executemany('INSERT INTO sample VALUES (?)', [(str(i),) for i in range(150)])
        db.commit()
    before = runtime.read_bytes()
    rows = inventory(root, app)
    assert rows[0]['local'] == str(app / name)
    assert preview(runtime)[1] == ['sample']
    content, _ = preview(runtime, 'sample')
    assert '仅展示前 100 行' in content
    assert runtime.read_bytes() == before


def test_log_preview_is_bounded(tmp_path):
    path = tmp_path / 'sample.log'
    path.write_bytes(b'a' * 200_000 + b'END')
    content, tables = preview(path)
    assert content.endswith('END')
    assert len(content) < 132_000
    assert tables == []


def test_database_preview_works_without_driver_realpath_support(tmp_path, monkeypatch):
    from pathlib import Path
    runtime = tmp_path / 'runtime.sqlite3'
    with closing(sqlite3.connect(runtime)) as db:
        db.execute('CREATE TABLE sample (value TEXT)')
        db.execute("INSERT INTO sample VALUES ('visible-data')")
        db.commit()
    def unsupported_resolve(*args, **kwargs):
        raise OSError(1, 'RAMDisk realpath unsupported')
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'resolve', unsupported_resolve)
        content, tables = preview(runtime)
    assert tables == ['sample']
    assert 'visible-data' in content
    assert '表：sample' in content


def test_viewer_window_starts_with_configured_paths(tmp_path, monkeypatch):
    import tkinter as tk
    from types import SimpleNamespace
    import JohnsonUtil
    from runtime_data_viewer import open_viewer
    monkeypatch.setattr(storage, 'configured_ramdisk_root', lambda: tmp_path)
    monkeypatch.setattr(JohnsonUtil, 'commonTips', SimpleNamespace(get_app_root=lambda: str(tmp_path)), raising=False)
    root = tk.Tk()
    root.withdraw()
    try:
        window = open_viewer(root)
        window.withdraw()
        root.update()
        assert window.title() == '运行数据查看器（只读）'
        window.destroy()
    finally:
        root.destroy()
