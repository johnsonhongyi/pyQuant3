import json
import subprocess
import sys
import threading

import global_favorites


def _manager_at(path, monkeypatch):
    monkeypatch.setattr(global_favorites, "FAVORITE_STOCKS_FILE", str(path))
    monkeypatch.setattr(global_favorites.sys_utils, "is_delisted_stock", lambda _code: False)
    manager = object.__new__(global_favorites.GlobalFavoriteManager)
    manager.favorite_sectors = set()
    manager.favorite_stocks = set()
    manager.favorite_stocks_dates = {}
    manager.favorite_sources = {}
    manager.favorite_tombstones = {}
    manager._attention_revision = 0
    manager._attention_favorites_revision = 0
    manager._lock = threading.RLock()
    manager._store_update_lock = threading.RLock()
    manager._listeners = set()
    manager._linkage_operations = {}
    manager._persistent_revision = 0
    manager._last_config_mtime = 0
    manager._last_file_hash = ""
    manager._last_reload_timestamp = 0
    manager._version = 0
    manager._config_path = str(path)
    return manager


def test_favorite_sources_can_be_removed_independently_and_full_remove_leaves_tombstone(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)

    manager.add_favorite_stock("600000", "2026-10-10")
    added = manager.ensure_linkage_favorite("600000", "sbc-op-1", metadata={"source": "sbc"})
    assert added["persisted"] is True
    assert manager.is_favorite_stock("600000")
    assert set(manager.favorite_sources["600000"]) == {"manual", "stock-strategy:sbc"}

    manager.remove_favorite_source("600000", "stock-strategy:sbc")
    assert manager.is_favorite_stock("600000")
    assert set(manager.favorite_sources["600000"]) == {"manual"}
    assert manager.get_favorite_attention_state()["source_tombstones"]["600000"]["stock-strategy:sbc"]

    manager.remove_favorite_stock("600000")
    assert not manager.is_favorite_stock("600000")
    state = manager.get_favorite_attention_state()
    assert state["tombstones"]["600000"]["operation_id"].startswith("local-remove-")

    with open(manager._config_path, "r", encoding="utf-8") as file_obj:
        persisted = json.load(file_obj)["system_linkage"]
    assert "600000" not in persisted["favorite_sources"]
    assert persisted["favorite_tombstones"]["600000"] == state["tombstones"]["600000"]


def test_removing_last_source_does_not_promote_it_to_global_removal(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    manager.add_favorite_stock("600000", "2026-10-10")

    manager.remove_favorite_source("600000", "manual")

    state = manager.get_persistent_favorite_attention_state()
    assert "600000" not in state["stocks"]
    assert "600000" not in state["tombstones"]
    assert state["source_tombstones"]["600000"]["manual"]["operation_id"].startswith("local-source-remove-")


def test_linkage_add_operation_is_idempotent_and_conflicts_on_reuse(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    first = manager.ensure_linkage_favorite("000001", "sbc-op-2", metadata={"source": "sbc"})
    replay = manager.ensure_linkage_favorite("000001", "sbc-op-2", metadata={"source": "sbc"})
    assert first["persisted"] is True
    assert replay["already_applied"] is True
    try:
        manager.ensure_linkage_favorite("000002", "sbc-op-2", metadata={"source": "sbc"})
    except ValueError as error:
        assert str(error) == "operation_id_conflict"
    else:
        raise AssertionError("reused operation id for another stock was accepted")


def test_sbc_source_is_normalized_and_removed_queued_operation_is_inactive(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    manager.ensure_linkage_favorite(
        "000001", "sbc-op-source", metadata={"source": "stock-strategy.sbc"}
    )

    assert manager.favorite_sources["000001"]["stock-strategy:sbc"]["operation_id"] == "sbc-op-source"
    assert manager.is_linkage_operation_active("000001", "sbc-op-source")

    manager.remove_favorite_source("000001", "stock-strategy:sbc")

    assert not manager.is_linkage_operation_active("000001", "sbc-op-source")


def test_remote_attention_projection_rejects_a_stale_local_revision(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    manager.add_favorite_stock("600000")
    stale_revision = manager.get_persistent_favorite_attention_state()["favorites_revision"]
    manager.add_favorite_stock("600001")

    try:
        manager.apply_favorite_source_intent(
            "600002", "stock-strategy:sbc", "add", "remote-intent-1",
            origin="remote_sync", expected_revision=stale_revision,
        )
    except ValueError as error:
        assert str(error) == "favorites_revision_conflict"
    else:
        raise AssertionError("stale remote projection overwrote a newer local favorite change")

    state = manager.get_persistent_favorite_attention_state()
    assert "600002" not in state["stocks"]
    assert "600000" in state["stocks"] and "600001" in state["stocks"]


def test_legacy_save_rejects_a_stale_snapshot_instead_of_resurrecting_a_removed_favorite(tmp_path, monkeypatch):
    favorite_path = tmp_path / "favorites.json"
    current = _manager_at(favorite_path, monkeypatch)
    current.ensure_linkage_favorite("600000", "seed-op", metadata={"source": "sbc"})

    stale = _manager_at(favorite_path, monkeypatch)
    stale.load_from_config()
    assert stale.is_favorite_stock("600000")

    current.remove_favorite_stock("600000")
    assert stale.save_to_config() is False

    persisted = current.get_persistent_favorite_attention_state()
    assert "600000" not in persisted["stocks"]
    assert persisted["tombstones"]["600000"]
    assert not stale.is_favorite_stock("600000")


def test_startup_delisted_repair_writes_a_source_aware_removal_tombstone(tmp_path, monkeypatch):
    favorite_path = tmp_path / "favorite_stocks.json"
    payload = {
        "favorite_stocks": ["600000"],
        "favorite_stocks_dates": {"600000": "2026-10-10"},
        "sector_bidding_panel_persistence_ui_state": {
            "favorite_stocks": ["600000"],
            "favorite_stocks_dates": {"600000": "2026-10-10"},
        },
        "system_linkage": {
            "favorites_revision": 4,
            "favorite_sources": {"600000": {"stock-strategy:sbc": {"operation_id": "sbc-op"}}},
        },
    }
    favorite_path.write_text(json.dumps(payload), encoding="utf-8")
    sys_utils = global_favorites.sys_utils
    monkeypatch.setattr(sys_utils, "get_app_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        sys_utils, "get_conf_path",
        lambda filename, *_args: str(favorite_path) if filename == "favorite_stocks.json" else str(tmp_path / filename),
    )
    monkeypatch.setattr(sys_utils, "is_delisted_stock", lambda code: str(code).strip().zfill(6) == "600000")

    sys_utils.repair_system_configurations_and_delisted_stocks()

    repaired = json.loads(favorite_path.read_text(encoding="utf-8"))
    linkage = repaired["system_linkage"]
    assert repaired["favorite_stocks"] == []
    assert linkage["favorites_revision"] == 5
    assert "600000" not in linkage["favorite_sources"]
    assert linkage["favorite_tombstones"]["600000"]["operation_id"].startswith("self-heal-delisted-")


def test_favorites_manager_delisted_cleanup_removes_sources_and_persists_tombstone(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    manager.ensure_linkage_favorite("600000", "sbc-op", metadata={"source": "sbc"})
    monkeypatch.setattr(global_favorites.sys_utils, "is_delisted_stock", lambda code: str(code) == "600000")

    manager.load_from_config()

    persisted = manager.get_persistent_favorite_attention_state()
    assert "600000" not in persisted["stocks"]
    assert "600000" not in persisted["sources"]
    assert persisted["tombstones"]["600000"]["operation_id"].startswith("local-remove-delisted-")


def test_concurrent_process_additions_and_removal_merge_without_lost_updates(tmp_path, monkeypatch):
    favorite_path = tmp_path / "favorites.json"
    initial_manager = _manager_at(favorite_path, monkeypatch)
    initial_manager.add_favorite_stock("600002", "2026-10-10")
    child_script = r"""
import sys
import threading
import global_favorites

path, action, code, operation_id, source = sys.argv[1:]
global_favorites.FAVORITE_STOCKS_FILE = path
global_favorites.sys_utils.is_delisted_stock = lambda _code: False
manager = object.__new__(global_favorites.GlobalFavoriteManager)
manager.favorite_sectors = set()
manager.favorite_stocks = set()
manager.favorite_stocks_dates = {}
manager.favorite_sources = {}
manager.favorite_tombstones = {}
manager.favorite_source_tombstones = {}
manager._attention_revision = 0
manager._attention_favorites_revision = 0
manager._lock = threading.RLock()
manager._store_update_lock = threading.RLock()
manager._listeners = set()
manager._linkage_operations = {}
manager._persistent_revision = 0
manager._last_config_mtime = 0
manager._last_file_hash = ""
manager._last_reload_timestamp = 0
manager._version = 0
manager._config_path = path
if action == "remove":
    manager.remove_favorite_stock(code)
else:
    result = manager.ensure_linkage_favorite(
        code, operation_id, add_date="2026-10-10", metadata={"source": source}
    )
    assert result["persisted"] is True
"""
    writers = [
        ("add", "600000", "op-sbc", "sbc"),
        ("add", "000001", "op-ats", "ats"),
        ("add", "600000", "op-tk", "tk"),
        ("remove", "600002", "op-remove", ""),
    ]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", child_script, str(favorite_path), action, code, operation_id, source],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for action, code, operation_id, source in writers
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, f"child failed: {stdout}\n{stderr}"

    with favorite_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    linkage = payload["system_linkage"]
    assert set(payload["favorite_stocks"]) == {"000001", "600000"}
    assert set(linkage["favorite_sources"]["600000"]) == {
        "stock-strategy:sbc", "stock-strategy:tk",
    }
    assert linkage["favorites_revision"] == 5
    assert set(linkage["applied_operations"]) == {"op-sbc", "op-ats", "op-tk"}
    assert linkage["favorite_tombstones"]["600002"]["operation_id"].startswith("local-remove-")


def test_same_process_concurrent_writers_publish_state_in_revision_order(tmp_path, monkeypatch):
    manager = _manager_at(tmp_path / "favorites.json", monkeypatch)
    original_publish = manager._publish_store_state
    first_publish_entered = threading.Event()
    second_mutation_finished = threading.Event()
    second_thread_started = threading.Event()
    errors = []

    def delayed_publish(state, content, origin="local", source_changes=None):
        if state["revision"] == 1:
            first_publish_entered.set()
            second_mutation_finished.wait(timeout=0.25)
        original_publish(state, content, origin, source_changes)

    manager._publish_store_state = delayed_publish

    def add_first():
        try:
            manager.ensure_linkage_favorite("600000", "thread-op-1", metadata={"source": "sbc"})
        except Exception as error:
            errors.append(error)

    def add_second():
        second_thread_started.set()
        try:
            manager.ensure_linkage_favorite("600001", "thread-op-2", metadata={"source": "ats"})
            second_mutation_finished.set()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=add_first)
    second = threading.Thread(target=add_second)
    first.start()
    assert first_publish_entered.wait(timeout=2)
    second.start()
    assert second_thread_started.wait(timeout=2)
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert manager.persistent_revision == 2
    assert manager.favorite_stocks == {"600000", "600001"}
    assert set(manager.list_linkage_operations()) == {"thread-op-1", "thread-op-2"}
