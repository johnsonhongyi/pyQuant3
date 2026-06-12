# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
from typing import Set, Callable
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE

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
        self.stock_grades = {}
        self._subscribers = []
        self._lock = threading.Lock()
        self._last_config_mtime = 0.0
        
        # Default config path — may be updated to DPI-aware path by the panel
        self._config_path = WINDOW_CONFIG_FILE
        # Load initially from the default path
        self.load_from_config()
        self.load_grades_from_voice_alert_config()

        # Start a background file mtime watcher thread for cross-process synchronization
        self._watcher_stop = threading.Event()
        self._watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True, name="FavoritesWatcher")
        self._watcher_thread.start()

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
        """更新配置文件路径（支持 DPI 缩放感知的路径）并重新加载。"""
        with self._lock:
            old_path = self._config_path
            self._config_path = path
        # 如果路径发生变化，从新路径重新加载一次，确保数据对齐
        if old_path != path and os.path.exists(path):
            logger.info(f"[GlobalFavorites] Config path updated: {old_path} → {path}, reloading...")
            self.load_from_config(path)
            
    def _file_watcher_loop(self):
        import time
        while not self._watcher_stop.is_set():
            try:
                time.sleep(1.0)
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

    def load_from_config(self, config_path: str = None):
        path = config_path or self._config_path
        if not path or not os.path.exists(path):
            return
        try:
            mtime = os.path.getmtime(path)
            with open(path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
            
            ui_state = full_data.get("sector_bidding_panel_persistence_ui_state")
            if ui_state:
                with self._lock:
                    self.favorite_sectors = set(ui_state.get('favorite_sectors', []))
                    self.favorite_stocks = set(ui_state.get('favorite_stocks', []))
                    self._last_config_mtime = mtime
                logger.info(f"🔑 [GlobalFavorites] Loaded {len(self.favorite_sectors)} sectors and {len(self.favorite_stocks)} stocks from {path}.")
                self.notify_subscribers()
        except Exception as e:
            logger.error(f"Failed to load favorites from config: {e}")

    def save_to_config(self, config_path: str = None):
        path = config_path or self._config_path
        if not path:
            return
        try:
            # Read current config to avoid overwriting other keys
            full_data = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        full_data = json.load(f)
                except Exception:
                    pass
            
            ui_state_key = "sector_bidding_panel_persistence_ui_state"
            if ui_state_key not in full_data:
                full_data[ui_state_key] = {}
            
            with self._lock:
                fav_sectors = list(self.favorite_sectors)
                fav_stocks = list(self.favorite_stocks)
                
            full_data[ui_state_key]['favorite_sectors'] = fav_sectors
            full_data[ui_state_key]['favorite_stocks'] = fav_stocks
            
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
        self.save_to_config()
        self.notify_subscribers()

    def remove_favorite_sector(self, sector: str):
        with self._lock:
            if sector in self.favorite_sectors:
                self.favorite_sectors.remove(sector)
        self.save_to_config()
        self.notify_subscribers()

    def toggle_favorite_sector(self, sector: str):
        with self._lock:
            if sector in self.favorite_sectors:
                self.favorite_sectors.remove(sector)
                action = "removed"
            else:
                self.favorite_sectors.add(sector)
                action = "added"
        self.save_to_config()
        self.notify_subscribers()
        return action

    def add_favorite_stock(self, code: str):
        with self._lock:
            self.favorite_stocks.add(code)
        self.save_to_config()
        self.notify_subscribers()

    def remove_favorite_stock(self, code: str):
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
        self.save_to_config()
        self.notify_subscribers()

    def toggle_favorite_stock(self, code: str):
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
                action = "removed"
            else:
                self.favorite_stocks.add(code)
                action = "added"
        self.save_to_config()
        self.notify_subscribers()
        return action

    def subscribe(self, callback: Callable[[], None]):
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[], None]):
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def notify_subscribers(self):
        with self._lock:
            subs = list(self._subscribers)
        for sub in subs:
            try:
                sub()
            except Exception as e:
                logger.error(f"Subscriber notification error: {e}")

    def get_favorite_sectors(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_sectors)

    def get_favorite_stocks(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_stocks)
