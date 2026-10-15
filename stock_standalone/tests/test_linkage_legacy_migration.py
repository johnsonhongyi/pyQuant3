import os
import sqlite3
import subprocess
import sys
import types
from contextlib import closing
from pathlib import Path

import pytest

import linkage_storage as storage


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows file sharing guard')


def prepare_runtime(tmp_path, monkeypatch):
    local = tmp_path / 'legacy.sqlite3'
    runtime = tmp_path / 'ram' / local.name
    runtime.parent.mkdir()
    monkeypatch.setattr(storage, '_runtime_location', lambda path: (runtime, local))
    monkeypatch.setattr(storage, '_start_archive', lambda *args: None)
    return local, runtime


def test_crashed_wal_commits_are_migrated(tmp_path, monkeypatch):
    local, runtime = prepare_runtime(tmp_path, monkeypatch)
    script = """import sqlite3, os, sys
db = sqlite3.connect(sys.argv[1])
db.execute('PRAGMA journal_mode=WAL')
db.execute('CREATE TABLE sample (value TEXT)')
db.execute("INSERT INTO sample VALUES ('committed-in-wal')")
db.commit()
db.execute("INSERT INTO sample VALUES ('uncommitted')")
os._exit(0)
"""
    subprocess.run([sys.executable, '-c', script, str(local)], check=True)
    wal = Path(str(local) + '-wal')
    assert wal.exists()
    before = {path: path.read_bytes() for path in (local, wal)}
    assert storage.runtime_database(str(local)) == str(runtime)
    with closing(sqlite3.connect(runtime)) as db:
        assert db.execute('SELECT * FROM sample').fetchall() == [('committed-in-wal',)]
        assert db.execute('PRAGMA quick_check').fetchone() == ('ok',)
    assert all(path.read_bytes() == content for path, content in before.items())
    backups = list(tmp_path.glob('*.migration-backup-*.sqlite3'))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute('SELECT * FROM sample').fetchall() == [('committed-in-wal',)]


@pytest.mark.parametrize('journal', ['WAL', 'DELETE'])
def test_open_legacy_connection_blocks_migration(tmp_path, monkeypatch, journal):
    local, runtime = prepare_runtime(tmp_path, monkeypatch)
    with closing(sqlite3.connect(local)) as db:
        db.execute('PRAGMA journal_mode=' + journal)
        db.execute('CREATE TABLE sample (value TEXT)')
        db.commit()
        with pytest.raises(RuntimeError, match='legacy_writer_active'):
            storage.runtime_database(str(local))
        assert not runtime.exists()
        assert not list(tmp_path.glob('*.migration-backup-*.sqlite3'))
        db.execute("INSERT INTO sample VALUES ('still-writable')")
        db.commit()
    storage.runtime_database(str(local))
    with closing(sqlite3.connect(runtime)) as db:
        assert db.execute('SELECT * FROM sample').fetchall() == [('still-writable',)]


@pytest.mark.parametrize('packaged', [False, True])
def test_database_environment_paths(tmp_path, monkeypatch, packaged):
    local = tmp_path / 'system_linkage.sqlite3'
    expected = local if packaged else tmp_path / '.development' / local.name
    runtime = tmp_path / 'ram' / ('packaged' if packaged else 'development') / local.name
    runtime.parent.mkdir(parents=True)
    received = []

    def location(path):
        received.append(Path(path))
        return runtime, Path(path)

    monkeypatch.setitem(sys.modules, 'sys_utils', types.SimpleNamespace(is_packaged_env=lambda: packaged))
    monkeypatch.setattr(storage, '_runtime_location', location)
    monkeypatch.setattr(storage, '_start_archive', lambda *args: None)
    storage.runtime_database(str(local))
    assert received == [expected]
    assert runtime.exists()
