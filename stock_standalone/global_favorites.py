# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import time
from typing import Set, Callable
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
        self.stock_grades = {}
        self._lock = threading.Lock()
        self._last_config_mtime = 0.0
        self._version = 0
        
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
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                grades = {}
                for key, stock in data.items():
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
            
    def _file_watcher_loop(self):
        while not self._watcher_stop.wait(1.0):
            try:
                path = self._config_path
                if path and os.path.exists(path):
                    mtime = os.path.getmtime(path)
                    with self._lock:
                        if mtime != self._last_config_mtime:
                            need_load = True
                        else:
                            need_load = False
                    
                    if need_load:
                        logger.info(f"🔄 [GlobalFavorites] Config file changed externally ({path}), reloading...")
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
            default_date = None
            try:
                from JohnsonUtil import commonTips as cct
                default_date = cct.get_lastdays_trade_date(3)
            except Exception:
                pass
            if not default_date:
                import datetime
                default_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
            
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

    def load_from_config(self, config_path: str = None):
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
            mtime = os.path.getmtime(path)
            with open(path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
            
            ui_state = full_data.get("sector_bidding_panel_persistence_ui_state")
            if not ui_state:
                ui_state = full_data
                
            changed = False
            if ui_state:
                new_sectors = set(ui_state.get('favorite_sectors', []))
                new_stocks = set(ui_state.get('favorite_stocks', []))
                new_stocks_dates = ui_state.get('favorite_stocks_dates', {})
                
                # Check compatibility/integrity: populate missing dates with 3 trading days ago for testing
                default_date = None
                try:
                    from JohnsonUtil import commonTips as cct
                    default_date = cct.get_lastdays_trade_date(3)
                except Exception:
                    pass
                if not default_date:
                    import datetime
                    default_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")

                for code in new_stocks:
                    if code not in new_stocks_dates:
                        new_stocks_dates[code] = default_date
                # Clean up orphaned keys
                for code in list(new_stocks_dates.keys()):
                    if code not in new_stocks:
                        del new_stocks_dates[code]

                with self._lock:
                    if (new_sectors != self.favorite_sectors or 
                        new_stocks != self.favorite_stocks or 
                        new_stocks_dates != self.favorite_stocks_dates):
                        changed = True
                    self.favorite_sectors = new_sectors
                    self.favorite_stocks = new_stocks
                    self.favorite_stocks_dates = new_stocks_dates
                    self._last_config_mtime = mtime
                logger.info(f"🔑 [GlobalFavorites] Loaded {len(self.favorite_sectors)} sectors and {len(self.favorite_stocks)} stocks from {path}.")
                if changed:
                    with self._lock:
                        self._version += 1
            else:
                with self._lock:
                    self._last_config_mtime = mtime
        except Exception as e:
            logger.error(f"Failed to load favorites from config: {e}")

    def save_to_config(self, config_path: str = None):
        path = FAVORITE_STOCKS_FILE
        try:
            full_data = {}
            with self._lock:
                fav_sectors = list(self.favorite_sectors)
                fav_stocks = list(self.favorite_stocks)
                fav_stocks_dates = dict(self.favorite_stocks_dates)
                
            ui_state_key = "sector_bidding_panel_persistence_ui_state"
            full_data[ui_state_key] = {
                'favorite_sectors': fav_sectors,
                'favorite_stocks': fav_stocks,
                'favorite_stocks_dates': fav_stocks_dates
            }
            # 同时在顶层放一份，更易直观读写
            full_data['favorite_sectors'] = fav_sectors
            full_data['favorite_stocks'] = fav_stocks
            full_data['favorite_stocks_dates'] = fav_stocks_dates
            
            # Write to a temp file first for atomic safety
            tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            
            if os.path.exists(path):
                os.remove(path)
            os.rename(tmp_path, path)
            with self._lock:
                self._last_config_mtime = os.path.getmtime(path)
            logger.debug(f"Saved favorites to {path}")
        except Exception as e:
            logger.error(f"Failed to save favorites to config: {e}")

    def add_favorite_sector(self, sector: str):
        with self._lock:
            self.favorite_sectors.add(sector)
            self._version += 1
        self.save_to_config()

    def remove_favorite_sector(self, sector: str):
        with self._lock:
            if sector in self.favorite_sectors:
                self.favorite_sectors.remove(sector)
                self._version += 1
        self.save_to_config()

    def toggle_favorite_sector(self, sector: str):
        with self._lock:
            if sector in self.favorite_sectors:
                self.favorite_sectors.remove(sector)
                action = "removed"
            else:
                self.favorite_sectors.add(sector)
                action = "added"
            self._version += 1
        self.save_to_config()
        return action

    def add_favorite_stock(self, code: str, add_date: str = None):
        if not add_date:
            add_date = time.strftime("%Y-%m-%d")
        with self._lock:
            self.favorite_stocks.add(code)
            self.favorite_stocks_dates[code] = add_date
            self._version += 1
        self.save_to_config()

    def remove_favorite_stock(self, code: str):
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
                self._version += 1
            if code in self.favorite_stocks_dates:
                del self.favorite_stocks_dates[code]
        self.save_to_config()

    def toggle_favorite_stock(self, code: str, add_date: str = None):
        if not add_date:
            add_date = time.strftime("%Y-%m-%d")
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
                if code in self.favorite_stocks_dates:
                    del self.favorite_stocks_dates[code]
                action = "removed"
            else:
                self.favorite_stocks.add(code)
                self.favorite_stocks_dates[code] = add_date
                action = "added"
            self._version += 1
        self.save_to_config()
        return action

    def get_favorite_stock_date(self, code: str) -> str:
        with self._lock:
            return self.favorite_stocks_dates.get(code, "")

    def get_favorite_stocks_dates(self) -> dict:
        with self._lock:
            return dict(self.favorite_stocks_dates)

    def get_favorite_sectors(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_sectors)

    def get_favorite_stocks(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_stocks)
