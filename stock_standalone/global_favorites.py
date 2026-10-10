# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import time
import contextlib
from typing import Set, Callable, Any
import sys_utils

_base_dir = sys_utils.get_app_root()
def _get_fav_config_path(filename="window_config.json"):
    path = sys_utils.get_conf_path(filename, _base_dir)
    if not path:
        path = os.path.join(_base_dir, filename)
    return str(path)
WINDOW_CONFIG_FILE = _get_fav_config_path("window_config.json")
FAVORITE_STOCKS_FILE = _get_fav_config_path("favorite_stocks.json")

logger = logging.getLogger("instock_TK.GlobalFavoriteManager")


@contextlib.contextmanager
def _favorites_file_lock(path: str, timeout: float = 8.0):
    """Serialize favorite-file updates across TK/ATS processes."""
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("favorite file lock timed out")
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _favorite_source_changes(before_sources, before_tombstones, after_sources, after_tombstones):
    changes = []
    codes = set(before_sources) | set(after_sources) | set(before_tombstones) | set(after_tombstones)
    for code in sorted(codes):
        old_tombstone = before_tombstones.get(code)
        new_tombstone = after_tombstones.get(code)
        if new_tombstone and new_tombstone != old_tombstone:
            changes.append({"code": code, "action": "remove_all", "source": "manual",
                            "operation_id": str(new_tombstone.get("operation_id", ""))})
            continue
        old = before_sources.get(code, {})
        new = after_sources.get(code, {})
        for source in sorted(set(old) | set(new)):
            if source not in old and source in new:
                changes.append({"code": code, "action": "add", "source": source})
            elif source in old and source not in new:
                changes.append({"code": code, "action": "remove_source", "source": source})
    return changes


def _normalize_local_attention_source(source):
    value = str(source or "").strip()[:96]
    if value.startswith("stock-strategy."):
        return "stock-strategy:" + value[len("stock-strategy."):]
    return value

class GlobalFavoriteManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(GlobalFavoriteManager, cls).__new__(cls, *args, **kwargs)
                    cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.favorite_sectors: Set[str] = set()
        self.favorite_stocks: Set[str] = set()
        self.favorite_stocks_dates = {}  # {code: "%Y-%m-%d"}
        self.favorite_sources = {}  # {code: {source: metadata}}
        self.favorite_tombstones = {}  # {code: last full-removal metadata}
        self.favorite_source_tombstones = {}  # {code: {source: removal metadata}}
        self._attention_revision = 0
        self._attention_favorites_revision = 0
        self.stock_grades = {}
        self._lock = threading.Lock()
        self._store_update_lock = threading.RLock()
        self._last_config_mtime = 0.0
        self._last_file_hash = ""
        self._version = 0
        self._listeners = set()
        self._linkage_operations = {}
        self._persistent_revision = 0
        
        # Default config path - now hardcoded to independent favorite_stocks.json to avoid DPI scale issues
        self._config_path = FAVORITE_STOCKS_FILE
        # Load initially from the default path
        self.load_from_config()
        self.load_grades_from_voice_alert_config()

        # Start a background file mtime watcher thread for cross-process synchronization
        self._watcher_stop = threading.Event()
        self._watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True, name="FavoritesWatcher")
        self._watcher_thread.start()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def load_grades_from_voice_alert_config(self):
        try:
            from sys_utils import get_conf_path
            path = get_conf_path("voice_alert_config.json") or "voice_alert_config.json"
            if os.path.exists(path):
                data = None
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except json.JSONDecodeError as j_err:
                    logger.warning(f"⚠️ [GlobalFavorites] {path} decode error: {j_err}. Attempting raw_decode repair...")
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                        data, _ = json.JSONDecoder().raw_decode(content)
                        tmp_file = f"{path}.tmp.{os.getpid()}"
                        with open(tmp_file, "w", encoding="utf-8") as f_out:
                            json.dump(data, f_out, ensure_ascii=False, indent=2)
                        os.replace(tmp_file, path)
                        logger.info(f"✅ [GlobalFavorites] Repaired and saved clean JSON to {path}")
                    except Exception as e_repair:
                        logger.error(f"❌ [GlobalFavorites] Failed to auto-repair {path}: {e_repair}")
                        data = {}

                if isinstance(data, dict):
                    grades = {}
                    for key, stock in data.items():
                        if isinstance(stock, dict):
                            code = stock.get('code') or key.split('_')[0]
                            grade = stock.get('grade') or stock.get('snapshot', {}).get('grade', '')
                            if grade:
                                grades[code] = grade
                    with self._lock:
                        self.stock_grades.update(grades)
                    logger.info(f"[GlobalFavorites] Loaded {len(grades)} stock grades from {path}.")
        except Exception as e:
            logger.error(f"Failed to load grades from voice alert config: {e}")

    def set_stock_grades(self, grades: dict):
        with self._lock:
            self.stock_grades.update(grades)
            
    def get_stock_grade(self, code: str) -> str:
        with self._lock:
            return self.stock_grades.get(code, "C")
            
    def set_config_path(self, path: str):
        """[DEPRECATED] 重点关注个股独立存储后，不再根据 scale_factor 或外部调用更改路径，始终使用唯一的 favorite_stocks.json"""
        pass
            
    RELOAD_COOLDOWN_SEC = 3.0  # 跨节点/跨进程同步防抖阈值 (1.0s)

    def _file_watcher_loop(self):
        import hashlib
        while not self._watcher_stop.wait(2.0):
            try:
                path = self._config_path
                if path and os.path.exists(path):
                    mtime = os.path.getmtime(path)
                    now = time.time()
                    with self._lock:
                        # 只有 mtime 发生改变 且 距离上次重载超越大周期阈值(3.0s) 时才允许进行 Hash 脏检查
                        time_changed = abs(mtime - self._last_config_mtime) > 1e-4 and (now - getattr(self, '_last_reload_timestamp', 0)) >= self.RELOAD_COOLDOWN_SEC
                    
                    if time_changed:
                        # ⚡ 严格内容指纹脏检查：内容完全相同时静默同步 mtime，杜绝多进程乒乓重载风暴
                        try:
                            with open(path, "rb") as f:
                                file_bytes = f.read()
                            file_hash = hashlib.md5(file_bytes).hexdigest()
                        except Exception:
                            file_hash = ""
                            
                        with self._lock:
                            if file_hash and file_hash == self._last_file_hash:
                                self._last_config_mtime = mtime
                                continue
                        
                        logger.info(f"🔄 [GlobalFavorites] Config file changed externally ({path}), reloading (3min cooldown OK)...")
                        self.load_from_config(path)
            except Exception as e:
                logger.error(f"Error in FavoritesWatcher loop: {e}")

    def shutdown(self):
        """
        Shuts down the file watcher thread cleanly.
        """
        self._watcher_stop.set()
        if hasattr(self, '_watcher_thread') and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=1.0)

    def _migrate_old_favorites(self):
        """
        [MIGRATION] 从历史的 window_config.json 或 scaleX_window_config.json 中
        自动合并提取出自选股与自选板块数据，保存至专用的 favorite_stocks.json。
        """
        migrated_stocks = set()
        migrated_sectors = set()
        migrated_dates = {}
        
        candidates = ["window_config.json", "scale2_window_config.json", "scale1_window_config.json", "scale3_window_config.json"]
        for fname in candidates:
            c_path = _get_fav_config_path(fname)
            if os.path.exists(c_path):
                try:
                    with open(c_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    ui_state = data.get("sector_bidding_panel_persistence_ui_state")
                    if ui_state:
                        sectors = ui_state.get("favorite_sectors", [])
                        if sectors:
                            migrated_sectors.update(sectors)
                        stocks = ui_state.get("favorite_stocks", [])
                        if stocks:
                            migrated_stocks.update(stocks)
                        dates = ui_state.get("favorite_stocks_dates", {})
                        if dates:
                            migrated_dates.update(dates)
                except Exception as e:
                    logger.warning(f"[GlobalFavorites] Failed to read migrate source {fname}: {e}")
        
        if migrated_stocks or migrated_sectors:
            logger.info(f"🚚 [GlobalFavorites] Migrating {len(migrated_stocks)} stocks and {len(migrated_sectors)} sectors to favorite_stocks.json")
            default_date = self._get_default_trade_date()
            
            for code in migrated_stocks:
                if code not in migrated_dates:
                    migrated_dates[code] = default_date
            
            for code in list(migrated_dates.keys()):
                if code not in migrated_stocks:
                    del migrated_dates[code]
            
            with self._lock:
                self.favorite_stocks = migrated_stocks
                self.favorite_sectors = migrated_sectors
                self.favorite_stocks_dates = migrated_dates
            
            self.save_to_config(FAVORITE_STOCKS_FILE)

    def _read_store(self, path):
        if not os.path.exists(path):
            return {}, {
                "sectors": set(), "stocks": set(), "dates": {},
                "sources": {}, "tombstones": {}, "source_tombstones": {}, "attention_revision": 0,
                "attention_favorites_revision": 0, "operations": {}, "revision": 0,
            }
        with open(path, "rb") as file_obj:
            payload = json.loads(file_obj.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("favorite store root must be an object")
        ui_key = "sector_bidding_panel_persistence_ui_state"
        ui_state = payload.get(ui_key)
        if not isinstance(ui_state, dict):
            ui_state = {}
        if ui_key not in payload:
            ui_state = payload
        linkage = payload.get("system_linkage")
        if not isinstance(linkage, dict):
            linkage = {}
        operations = linkage.get("applied_operations")
        if not isinstance(operations, dict):
            operations = {}
        try:
            attention_revision = max(0, int(linkage.get("attention_revision") or 0))
        except (TypeError, ValueError):
            attention_revision = 0
        try:
            attention_favorites_revision = max(0, int(linkage.get("attention_favorites_revision") or 0))
        except (TypeError, ValueError):
            attention_favorites_revision = 0
        sectors = ui_state.get("favorite_sectors", payload.get("favorite_sectors", []))
        stocks = ui_state.get("favorite_stocks", payload.get("favorite_stocks", []))
        dates = ui_state.get("favorite_stocks_dates", payload.get("favorite_stocks_dates", {}))
        try:
            revision = max(0, int(linkage.get("favorites_revision") or 0))
        except (TypeError, ValueError):
            revision = 0
        valid_stocks = set()
        if isinstance(stocks, (list, tuple, set)):
            valid_stocks = {
                str(code).strip().zfill(6) for code in stocks
                if str(code).strip().isdigit() and 1 <= len(str(code).strip()) <= 6
                and str(code).strip().zfill(6) != "000000"
            }
        if not isinstance(sectors, (list, tuple, set)):
            sectors = []
        if not isinstance(dates, dict):
            dates = {}
        raw_sources = linkage.get("favorite_sources")
        if not isinstance(raw_sources, dict):
            raw_sources = {}
        sources = {}
        for code, entries in raw_sources.items():
            normalized_code = str(code).strip().zfill(6)
            if normalized_code not in valid_stocks or not isinstance(entries, dict):
                continue
            safe_entries = {}
            for source, metadata in entries.items():
                source = str(source).strip()[:96]
                if source:
                    safe_entries[source] = dict(metadata) if isinstance(metadata, dict) else {}
            if safe_entries:
                sources[normalized_code] = safe_entries
        for code in valid_stocks:
            sources.setdefault(code, {"manual": {"legacy": True}})
        raw_tombstones = linkage.get("favorite_tombstones")
        if not isinstance(raw_tombstones, dict):
            raw_tombstones = {}
        tombstones = {str(code).strip().zfill(6): dict(value)
                      for code, value in raw_tombstones.items()
                      if isinstance(value, dict) and str(code).strip().isdigit()
                      and 1 <= len(str(code).strip()) <= 6}
        raw_source_tombstones = linkage.get("favorite_source_tombstones")
        if not isinstance(raw_source_tombstones, dict):
            raw_source_tombstones = {}
        source_tombstones = {}
        for code, entries in raw_source_tombstones.items():
            raw_code = str(code).strip()
            normalized_code = raw_code.zfill(6)
            if not raw_code.isdigit() or not 1 <= len(raw_code) <= 6 or not isinstance(entries, dict):
                continue
            safe_entries = {str(source).strip()[:96]: dict(value)
                            for source, value in entries.items()
                            if str(source).strip() and isinstance(value, dict)}
            if safe_entries:
                source_tombstones[normalized_code] = safe_entries
        return payload, {
            "sectors": set(str(sector).strip() for sector in sectors if str(sector).strip()),
            "stocks": valid_stocks,
            "dates": dict(dates),
            "sources": sources,
            "tombstones": tombstones,
            "source_tombstones": source_tombstones,
            "attention_revision": attention_revision,
            "attention_favorites_revision": attention_favorites_revision,
            "operations": dict(operations),
            "revision": revision,
        }

    @staticmethod
    def _write_store(path, payload, state):
        ui_key = "sector_bidding_panel_persistence_ui_state"
        ui_state = payload.get(ui_key)
        if not isinstance(ui_state, dict):
            ui_state = {}
        ui_state.update({
            "favorite_sectors": sorted(state["sectors"]),
            "favorite_stocks": sorted(state["stocks"]),
            "favorite_stocks_dates": dict(state["dates"]),
        })
        payload[ui_key] = ui_state
        payload.update({
            "favorite_sectors": sorted(state["sectors"]),
            "favorite_stocks": sorted(state["stocks"]),
            "favorite_stocks_dates": dict(state["dates"]),
        })
        linkage = payload.get("system_linkage")
        if not isinstance(linkage, dict):
            linkage = {}
        linkage["favorites_revision"] = int(state["revision"])
        linkage["favorite_sources"] = state["sources"]
        linkage["favorite_tombstones"] = state["tombstones"]
        linkage["favorite_source_tombstones"] = state.get("source_tombstones", {})
        linkage["attention_revision"] = int(state.get("attention_revision", 0))
        linkage["attention_favorites_revision"] = int(state.get("attention_favorites_revision", 0))
        linkage["applied_operations"] = state["operations"]
        payload["system_linkage"] = linkage

        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}"
        try:
            with open(tmp_path, "xb") as file_obj:
                file_obj.write(content)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            last_error = None
            for attempt in range(4):
                try:
                    os.replace(tmp_path, path)
                    last_error = None
                    break
                except OSError as error:
                    last_error = error
                    if attempt < 3:
                        time.sleep(0.05 * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                logger.warning("Could not remove temporary favorite file %s", tmp_path)
        return content

    def _publish_store_state(self, state, content, origin="local", source_changes=None):
        import hashlib
        sectors = set(state["sectors"])
        stocks = set(state["stocks"])
        dates = dict(state["dates"])
        sources = {code: {key: dict(value) for key, value in items.items()}
                   for code, items in state.get("sources", {}).items()}
        tombstones = {code: dict(value) for code, value in state.get("tombstones", {}).items()}
        source_tombstones = {code: {key: dict(value) for key, value in entries.items()}
                             for code, entries in state.get("source_tombstones", {}).items()}
        try:
            mtime = os.path.getmtime(self._config_path)
        except OSError:
            mtime = 0.0
        with self._lock:
            changed = (sectors != self.favorite_sectors or stocks != self.favorite_stocks
                       or dates != self.favorite_stocks_dates
                       or sources != self.favorite_sources or tombstones != self.favorite_tombstones
                       or source_tombstones != self.favorite_source_tombstones)
            prior_operations = self._linkage_operations
            operations = dict(state["operations"])
            new_operations = {key: value for key, value in operations.items() if key not in prior_operations}
            self.favorite_sectors = sectors
            self.favorite_stocks = stocks
            self.favorite_stocks_dates = dates
            self.favorite_sources = sources
            self.favorite_tombstones = tombstones
            self.favorite_source_tombstones = source_tombstones
            self._attention_revision = int(state.get("attention_revision", 0))
            self._attention_favorites_revision = int(state.get("attention_favorites_revision", 0))
            self._linkage_operations = operations
            self._persistent_revision = int(state["revision"])
            self._last_config_mtime = mtime
            self._last_file_hash = hashlib.md5(content).hexdigest()
            self._last_reload_timestamp = time.time()
            if changed:
                self._version += 1
            listeners = list(self._listeners) if changed or new_operations else []
        event = {"favorites_revision": state["revision"], "changed": changed,
                 "stocks": sorted(stocks), "sources": sources, "tombstones": tombstones,
                 "source_tombstones": source_tombstones,
                 "new_operations": new_operations, "origin": origin,
                 "source_changes": list(source_changes or [])}
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Favorite change listener failed")

    def add_change_listener(self, callback: Callable[[dict], Any]):
        with self._lock:
            self._listeners.add(callback)
        return callback

    def remove_change_listener(self, callback: Callable[[dict], Any]):
        with self._lock:
            self._listeners.discard(callback)

    def _mutate_store(self, mutate, origin="local"):
        """Read, merge and atomically persist one change under a process-wide lock."""
        with self._store_update_lock:
            path = FAVORITE_STOCKS_FILE
            with _favorites_file_lock(path):
                payload, state = self._read_store(path)
                before = (set(state["sectors"]), set(state["stocks"]), dict(state["dates"]),
                          {code: {key: dict(value) for key, value in items.items()}
                           for code, items in state["sources"].items()},
                          {code: dict(value) for code, value in state["tombstones"].items()},
                          {code: {key: dict(value) for key, value in items.items()}
                           for code, items in state["source_tombstones"].items()})
                result, force_write = mutate(state)
                source_changes = _favorite_source_changes(before[3], before[4], state["sources"], state["tombstones"])
                favorites_changed = before != (state["sectors"], state["stocks"], state["dates"],
                                                state["sources"], state["tombstones"], state["source_tombstones"])
                if favorites_changed:
                    state["revision"] += 1
                if force_write or favorites_changed or not os.path.exists(path):
                    content = self._write_store(path, payload, state)
                else:
                    with open(path, "rb") as file_obj:
                        content = file_obj.read()
            self._publish_store_state(state, content, origin, source_changes)
        return result, state["revision"]

    def get_persistent_revision(self):
        path = FAVORITE_STOCKS_FILE
        with _favorites_file_lock(path):
            _, state = self._read_store(path)
        return state["revision"]

    @property
    def persistent_revision(self):
        with self._lock:
            return self._persistent_revision

    def list_linkage_operations(self):
        with self._lock:
            operations = dict(self._linkage_operations)
        return {key: dict(value) for key, value in operations.items()
                if isinstance(value, dict)}

    def is_linkage_operation_active(self, code, operation_id):
        code = str(code or "").strip().zfill(6)
        operation_id = str(operation_id or "").strip()
        with self._lock:
            operation = self._linkage_operations.get(operation_id)
            if (not isinstance(operation, dict) or operation.get("code") != code
                    or operation.get("action", "add") != "add"):
                return False
            source = str(operation.get("source") or "")
            return bool(source and source in self.favorite_sources.get(code, {}))

    def ensure_linkage_favorite(self, code, operation_id, add_date=None, metadata=None):
        """Idempotently add one stock and atomically record the operation marker."""
        code = str(code or "").strip()
        operation_id = str(operation_id or "").strip()
        if len(code) != 6 or not code.isdigit() or code == "000000":
            raise ValueError("invalid_stock_code")
        if not operation_id or len(operation_id) > 128:
            raise ValueError("invalid_operation_id")
        if sys_utils.is_delisted_stock(code):
            raise ValueError("delisted_stock")

        def apply(state):
            safe_metadata = dict(metadata or {})
            source_name = str(safe_metadata.get("source") or "sbc").strip()[:80]
            source = _normalize_local_attention_source(source_name)
            if not source.startswith("stock-strategy:"):
                source = "stock-strategy:" + source
            previous = state["operations"].get(operation_id)
            if previous is not None:
                if (not isinstance(previous, dict) or previous.get("code") != code
                        or previous.get("action", "add") != "add"
                        or previous.get("source") not in (None, source)):
                    raise ValueError("operation_id_conflict")
                return {"status": previous.get("status", "applied"), "already_applied": True}, False
            already_present = code in state["stocks"]
            if not already_present:
                state["stocks"].add(code)
                state["dates"][code] = self._get_default_trade_date(add_date)
            state["sources"].setdefault(code, {}).setdefault(source, {
                "operation_id": operation_id,
                "local_revision": int(state["revision"]) + 1,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            state["tombstones"].pop(code, None)
            state["source_tombstones"].setdefault(code, {}).pop(source, None)
            if not state["source_tombstones"].get(code):
                state["source_tombstones"].pop(code, None)
            state["operations"][operation_id] = {
                "code": code,
                "source": source,
                "action": "add",
                "status": "already_present" if already_present else "applied",
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "metadata": safe_metadata,
            }
            return {"status": "already_present" if already_present else "applied",
                    "already_applied": False}, True

        result, revision = self._mutate_store(apply, origin="linkage_command")
        result["persisted"] = True
        result["favorites_revision"] = revision
        return result

    def apply_favorite_source_intent(self, code, source, action, operation_id, add_date=None, origin="local",
                                    expected_revision=None):
        """Apply one idempotent source add/removal or a full-removal tombstone."""
        code = str(code or "").strip()
        source = _normalize_local_attention_source(source)
        action = str(action or "").strip().lower()
        operation_id = str(operation_id or "").strip()
        if len(code) != 6 or not code.isdigit() or code == "000000":
            raise ValueError("invalid_stock_code")
        if not source or any(ord(char) < 33 for char in source):
            raise ValueError("invalid_favorite_source")
        if action not in ("add", "remove_source", "remove_all"):
            raise ValueError("invalid_favorite_action")
        if not operation_id or len(operation_id) > 128:
            raise ValueError("invalid_operation_id")
        if expected_revision is not None:
            try:
                expected_revision = max(0, int(expected_revision))
            except (TypeError, ValueError) as error:
                raise ValueError("invalid_favorites_revision") from error
        if action == "add" and sys_utils.is_delisted_stock(code):
            raise ValueError("delisted_stock")

        def apply(state):
            previous = state["operations"].get(operation_id)
            if previous is not None:
                if (not isinstance(previous, dict) or previous.get("code") != code
                        or previous.get("action") != action or previous.get("source") != source):
                    raise ValueError("operation_id_conflict")
                return {"status": previous.get("status", "applied"), "already_applied": True}, False
            if expected_revision is not None and int(state["revision"]) != expected_revision:
                raise ValueError("favorites_revision_conflict")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if action == "add":
                state["stocks"].add(code)
                state["dates"].setdefault(code, self._get_default_trade_date(add_date))
                state["sources"].setdefault(code, {})[source] = {
                    "operation_id": operation_id, "local_revision": int(state["revision"]) + 1,
                    "recorded_at": now,
                }
                state["tombstones"].pop(code, None)
                state["source_tombstones"].setdefault(code, {}).pop(source, None)
                if not state["source_tombstones"].get(code):
                    state["source_tombstones"].pop(code, None)
                status = "applied"
            elif action == "remove_source":
                state["sources"].setdefault(code, {}).pop(source, None)
                if not state["sources"].get(code):
                    state["sources"].pop(code, None)
                    state["stocks"].discard(code)
                    state["dates"].pop(code, None)
                now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                state["source_tombstones"].setdefault(code, {})[source] = {
                    "operation_id": operation_id, "local_revision": int(state["revision"]) + 1,
                    "recorded_at": now,
                }
                status = "applied"
            else:
                state["sources"].pop(code, None)
                state["stocks"].discard(code)
                state["dates"].pop(code, None)
                state["tombstones"][code] = {
                    "operation_id": operation_id, "local_revision": int(state["revision"]) + 1,
                    "recorded_at": now,
                }
                state["source_tombstones"].pop(code, None)
                status = "removed"
            state["operations"][operation_id] = {
                "code": code, "source": source, "action": action,
                "status": status, "recorded_at": now,
            }
            return {"status": status, "already_applied": False}, True

        result, revision = self._mutate_store(apply, origin=origin)
        result.update({"persisted": True, "favorites_revision": revision})
        return result

    def get_favorite_attention_state(self):
        with self._lock:
            return {
                "favorites_revision": self._persistent_revision,
                "stocks": sorted(self.favorite_stocks),
                "sources": {code: {source: dict(metadata) for source, metadata in entries.items()}
                            for code, entries in self.favorite_sources.items()},
                "tombstones": {code: dict(value) for code, value in self.favorite_tombstones.items()},
                "source_tombstones": {code: {source: dict(value) for source, value in entries.items()}
                                       for code, entries in self.favorite_source_tombstones.items()},
                "attention_revision": self._attention_revision,
                "attention_favorites_revision": self._attention_favorites_revision,
            }

    def get_persistent_favorite_attention_state(self):
        """Read the latest cross-process state while holding the favorite-file lock."""
        with _favorites_file_lock(FAVORITE_STOCKS_FILE):
            _, state = self._read_store(FAVORITE_STOCKS_FILE)
        return {
            "favorites_revision": state["revision"],
            "stocks": sorted(state["stocks"]),
            "sources": state["sources"],
            "tombstones": state["tombstones"],
            "source_tombstones": state["source_tombstones"],
            "attention_revision": state["attention_revision"],
            "attention_favorites_revision": state["attention_favorites_revision"],
        }

    def set_attention_sync_revision(self, revision, favorites_revision=None):
        revision = max(0, int(revision or 0))
        favorites_revision = None if favorites_revision is None else max(0, int(favorites_revision))

        def update(state):
            target_revision = max(int(state.get("attention_revision", 0)), revision)
            baseline = int(state["revision"]) if favorites_revision is None else max(
                int(state.get("attention_favorites_revision", 0)), favorites_revision)
            changed = (int(state.get("attention_revision", 0)) != target_revision
                       or int(state.get("attention_favorites_revision", 0)) != baseline)
            state["attention_revision"] = target_revision
            state["attention_favorites_revision"] = baseline
            return None, changed

        self._mutate_store(update, origin="remote_sync")

    def load_from_config(self, config_path: str = None):
        with self._store_update_lock:
            return self._load_from_config_locked(config_path)

    def _load_from_config_locked(self, config_path: str = None):
        # 强行限定仅读写专有的 favorite_stocks.json 配置文件
        path = FAVORITE_STOCKS_FILE
        if not os.path.exists(path):
            try:
                self._migrate_old_favorites()
            except Exception as e:
                logger.error(f"Failed to migrate old favorites: {e}")
                
        if not os.path.exists(path):
            return
        try:
            with _favorites_file_lock(path):
                payload, state = self._read_store(path)
                before = (set(state["sectors"]), set(state["stocks"]), dict(state["dates"]))
                delisted = {code for code in state["stocks"] if sys_utils.is_delisted_stock(code)}
                if delisted:
                    logger.warning("Cleaning delisted favorites from %s: %s", path, sorted(delisted))
                    state["stocks"].difference_update(delisted)
                    for code in delisted:
                        state["dates"].pop(code, None)
                        state["sources"].pop(code, None)
                        state["source_tombstones"].pop(code, None)
                        operation_id = f"local-remove-delisted-{code}-{time.time_ns()}"
                        state["tombstones"][code] = {
                            "operation_id": operation_id,
                            "local_revision": int(state["revision"]) + 1,
                            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                        state["operations"][operation_id] = {
                            "code": code, "source": "manual", "action": "remove_all",
                            "status": "removed", "recorded_at": state["tombstones"][code]["recorded_at"],
                        }
                default_date = self._get_default_trade_date()
                for code in state["stocks"]:
                    if not state["dates"].get(code):
                        state["dates"][code] = default_date
                for code in list(state["dates"]):
                    if code not in state["stocks"]:
                        del state["dates"][code]
                normalized = (before != (state["sectors"], state["stocks"], state["dates"])
                              or bool(delisted))
                if normalized:
                    state["revision"] += 1
                    content = self._write_store(path, payload, state)
                else:
                    with open(path, "rb") as file_obj:
                        content = file_obj.read()
            self._publish_store_state(state, content)
            logger.debug("Loaded %d favorite stocks from %s", len(state["stocks"]), path)
        except Exception as e:
            logger.error(f"Failed to load favorites from config: {e}")

    def backup_to_archives(self, archive_dir: str = None, logger_obj: Any = None, max_keep: int = 15):
        """
        [BACKUP] 跟随系统的标准归档：使用 monitor_utils.archive_file_tools
        自动备份 favorite_stocks.json 至 archives/ 目录，具备自动查重与 max_keep 清理功能。
        """
        try:
            from monitor_utils import archive_file_tools
            path = FAVORITE_STOCKS_FILE
            if not archive_dir:
                archive_dir = os.path.join(_base_dir, "archives")
            log_target = logger_obj or logger
            archive_file_tools(path, "favorite_stocks", archive_dir, log_target, max_keep=max_keep)
        except Exception as e:
            logger.error(f"[GlobalFavorites] Failed to backup favorite_stocks.json: {e}")

    def save_to_config(self, config_path: str = None):
        with self._store_update_lock:
            return self._save_to_config_locked(config_path)

    def _save_to_config_locked(self, config_path: str = None):
        path = FAVORITE_STOCKS_FILE
        try:
            with self._lock:
                base_revision = int(self._persistent_revision)
                memory = {
                    "sectors": set(self.favorite_sectors),
                    "stocks": set(self.favorite_stocks),
                    "dates": dict(self.favorite_stocks_dates),
                }
            stale_state = None
            with _favorites_file_lock(path):
                payload, state = self._read_store(path)
                if int(state["revision"]) != base_revision:
                    with open(path, "rb") as file_obj:
                        content = file_obj.read()
                    stale_state = (state, content)
                else:
                    before = (set(state["sectors"]), set(state["stocks"]), dict(state["dates"]))
                    before_sources = {code: {key: dict(value) for key, value in items.items()}
                                      for code, items in state["sources"].items()}
                    state["sectors"].update(memory["sectors"])
                    state["stocks"].update(memory["stocks"])
                    for code in state["stocks"]:
                        state["dates"].setdefault(code, memory["dates"].get(code) or self._get_default_trade_date())
                    for code in memory["stocks"]:
                        state["sources"].setdefault(code, {"manual": {}})
                    state["dates"].update({code: date for code, date in memory["dates"].items() if code not in before[1]})
                    for code in list(state["dates"]):
                        if code not in state["stocks"]:
                            del state["dates"][code]
                    changed = (before != (state["sectors"], state["stocks"], state["dates"])
                               or before_sources != state["sources"])
                    if changed:
                        state["revision"] += 1
                    if changed or not os.path.exists(path):
                        content = self._write_store(path, payload, state)
                    else:
                        with open(path, "rb") as file_obj:
                            content = file_obj.read()
            if stale_state is not None:
                self._publish_store_state(*stale_state, origin="stale_save_rejected")
                logger.warning("Rejected stale favorite snapshot write at revision %s; current revision is %s",
                               base_revision, stale_state[0]["revision"])
                return False
            self._publish_store_state(state, content)
            return True
        except Exception as e:
            logger.error(f"Failed to save favorites to config: {e}")
            return False

    def _get_default_trade_date(self, add_date: str = None) -> str:
        """获取规范格式的有效交易日 (%Y-%m-%d)。若传入非空 add_date 则保持并规范化，若为空则返回最新有效交易日"""
        if add_date and str(add_date).strip():
            s = str(add_date).strip()[:10].replace("/", "-")
            # 简单规范化 YYYYMMDD -> YYYY-MM-DD
            if len(s) == 8 and s.isdigit():
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            return s
        try:
            from JohnsonUtil import commonTips as cct
            dt = cct.get_last_trade_date()
            if dt:
                return str(dt).strip()[:10]
        except Exception:
            pass
        return time.strftime("%Y-%m-%d")

    def _legacy_change(self, mutate):
        try:
            result, _ = self._mutate_store(mutate)
            return result
        except Exception as error:
            logger.error("Favorite change was not persisted: %s", error)
            return None

    def add_favorite_sector(self, sector: str):
        sector = str(sector or "").strip()
        if not sector:
            return
        self._legacy_change(lambda state: (state["sectors"].add(sector) or None, False))

    def remove_favorite_sector(self, sector: str):
        sector = str(sector or "").strip()
        if not sector:
            return
        self._legacy_change(lambda state: (state["sectors"].discard(sector) or None, False))

    def toggle_favorite_sector(self, sector: str):
        sector = str(sector or "").strip()
        if not sector:
            return "error"

        def toggle(state):
            if sector in state["sectors"]:
                state["sectors"].remove(sector)
                return "removed", False
            state["sectors"].add(sector)
            return "added", False

        return self._legacy_change(toggle) or "error"

    def is_favorite_sector(self, sector: str) -> bool:
        with self._lock:
            return sector in self.favorite_sectors

    def add_favorite_stock(self, code: str, add_date: str = None):
        code = str(code or "").strip()
        if not code.isdigit() or not 1 <= len(code) <= 6:
            return
        code = code.zfill(6)
        if code == '000000' or sys_utils.is_delisted_stock(code):
            if sys_utils.is_delisted_stock(code):
                logger.warning(f"🚫 [GlobalFavorites] 拦截添加已知退市死码: {code}")
            return
            
        self._legacy_change(lambda state: self._add_favorite_source_state(
            state, code, "manual", add_date, {},
        ))

    def _add_favorite_source_state(self, state, code, source, add_date=None, metadata=None):
        state["stocks"].add(code)
        state["dates"].setdefault(code, self._get_default_trade_date(add_date))
        source_metadata = dict(metadata or {})
        source_metadata.setdefault("local_revision", int(state["revision"]) + 1)
        state["sources"].setdefault(code, {}).setdefault(source, source_metadata)
        state["tombstones"].pop(code, None)
        state["source_tombstones"].setdefault(code, {}).pop(source, None)
        if not state["source_tombstones"].get(code):
            state["source_tombstones"].pop(code, None)
        return None, False

    def add_favorites_batch(self, items, add_date: str = None):
        """批量添加重点关注，支持 code 列表"""
        if not items:
            return

        def add_batch(state):
            for item in items:
                code = None
                item_date = add_date
                if isinstance(item, str):
                    code = item.strip()
                elif isinstance(item, (tuple, list)) and len(item) >= 1:
                    code = str(item[0]).strip()
                    if len(item) >= 2 and item[1]:
                        item_date = str(item[1])

                if not code or not code.isdigit() or not 1 <= len(code) <= 6:
                    continue
                code = code.zfill(6)
                if code == '000000' or sys_utils.is_delisted_stock(code):
                    continue

                self._add_favorite_source_state(state, code, "manual", item_date, {})
            return None, False

        self._legacy_change(add_batch)

    def remove_favorite_stock(self, code: str):
        code = str(code or "").strip()
        if not code.isdigit() or not 1 <= len(code) <= 6:
            return
        code = code.zfill(6)
        def remove(state):
            state["stocks"].discard(code)
            state["dates"].pop(code, None)
            state["sources"].pop(code, None)
            state["source_tombstones"].pop(code, None)
            state["tombstones"][code] = {
                "operation_id": "local-remove-" + str(time.time_ns()),
                "local_revision": int(state["revision"]) + 1,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            return None, False

        self._legacy_change(remove)

    def remove_favorite_source(self, code: str, source: str):
        code = str(code or "").strip()
        source = str(source or "").strip()
        if not code.isdigit() or not 1 <= len(code) <= 6 or not source:
            return
        code = code.zfill(6)

        def remove(state):
            state["sources"].setdefault(code, {}).pop(source, None)
            state["source_tombstones"].setdefault(code, {})[source] = {
                "operation_id": "local-source-remove-" + str(time.time_ns()),
                "local_revision": int(state["revision"]) + 1,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if not state["sources"].get(code):
                state["sources"].pop(code, None)
                state["stocks"].discard(code)
                state["dates"].pop(code, None)
            return None, False

        self._legacy_change(remove)

    def toggle_favorite_stock(self, code: str, add_date: str = None):
        code = str(code or "").strip()
        if not code.isdigit() or not 1 <= len(code) <= 6:
            return "error"
        code = code.zfill(6)
        if code == "000000" or sys_utils.is_delisted_stock(code):
            return "error"

        def toggle(state):
            if code in state["stocks"]:
                state["stocks"].remove(code)
                state["dates"].pop(code, None)
                state["sources"].pop(code, None)
                state["source_tombstones"].pop(code, None)
                state["tombstones"][code] = {
                    "operation_id": "local-remove-" + str(time.time_ns()),
                    "local_revision": int(state["revision"]) + 1,
                    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                return "removed", False
            self._add_favorite_source_state(state, code, "manual", add_date, {})
            return "added", False

        return self._legacy_change(toggle) or "error"

    def is_favorite_stock(self, code: str) -> bool:
        code = str(code).strip().zfill(6)
        with self._lock:
            return code in self.favorite_stocks

    def get_favorite_stock_date(self, code: str) -> str:
        code = str(code).strip().zfill(6)
        with self._lock:
            date_str = self.favorite_stocks_dates.get(code, "")
            if date_str:
                return self._get_default_trade_date(date_str)
            elif code in self.favorite_stocks:
                # 内存自动补全为最近交易日保底，确保可视化联动 100% 能找到添加日期
                date_str = self._get_default_trade_date()
                self.favorite_stocks_dates[code] = date_str
                return date_str
        return date_str

    def get_favorite_stocks_dates(self) -> dict:
        with self._lock:
            default_date = self._get_default_trade_date()
            for code in self.favorite_stocks:
                cur_d = self.favorite_stocks_dates.get(code)
                norm_d = self._get_default_trade_date(cur_d) if cur_d else default_date
                if cur_d != norm_d:
                    self.favorite_stocks_dates[code] = norm_d
            return dict(self.favorite_stocks_dates)

    def get_favorite_sectors(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_sectors)

    def get_favorite_stocks(self) -> Set[str]:
        with self._lock:
            return {str(c).strip().zfill(6) for c in self.favorite_stocks if c}

