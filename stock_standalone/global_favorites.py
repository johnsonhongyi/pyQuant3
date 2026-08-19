# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import time
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
        while not self._watcher_stop.wait(2.0):
            try:
                path = self._config_path
                if path and os.path.exists(path):
                    mtime = os.path.getmtime(path)
                    now = time.time()
                    with self._lock:
                        # 只有 mtime 发生改变 且 距离上次重载超越大周期阈值(3.0s) 时才允许再次加载
                        if abs(mtime - self._last_config_mtime) > 1e-4 and (now - getattr(self, '_last_reload_timestamp', 0)) >= self.RELOAD_COOLDOWN_SEC:
                            need_load = True
                        else:
                            need_load = False
                    
                    if need_load:
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
            auto_filled = False
            if ui_state:
                new_sectors = set(ui_state.get('favorite_sectors', []))
                new_stocks = set(ui_state.get('favorite_stocks', []))
                new_stocks_dates = ui_state.get('favorite_stocks_dates', {})
                
                # 💥 运行时自动防卫与退市死码物理自愈清洗
                delisted_found = {c for c in new_stocks if sys_utils.is_delisted_stock(c)}
                if delisted_found:
                    logger.warning(f"🧹 [GlobalFavorites] 自动自愈清洗从 {path} 加载的已知退市死码: {delisted_found}")
                    new_stocks = {c for c in new_stocks if not sys_utils.is_delisted_stock(c)}
                    for d_code in delisted_found:
                        if d_code in new_stocks_dates:
                            del new_stocks_dates[d_code]
                    auto_filled = True

                default_date = self._get_default_trade_date()
                for code in new_stocks:
                    cur_d = new_stocks_dates.get(code)
                    if not cur_d:
                        new_stocks_dates[code] = default_date
                        auto_filled = True
                # Clean up orphaned keys
                for code in list(new_stocks_dates.keys()):
                    if code not in new_stocks:
                        del new_stocks_dates[code]
                        auto_filled = True

                with self._lock:
                    if (new_sectors != self.favorite_sectors or 
                        new_stocks != self.favorite_stocks):
                        changed = True
                    self.favorite_sectors = new_sectors
                    self.favorite_stocks = new_stocks
                    self.favorite_stocks_dates = new_stocks_dates
                    self._last_config_mtime = mtime
                    self._last_reload_timestamp = time.time()
                logger.info(f"🔑 [GlobalFavorites] Loaded {len(self.favorite_sectors)} sectors and {len(self.favorite_stocks)} stocks from {path}.")
                if changed:
                    with self._lock:
                        self._version += 1
                if auto_filled:
                    # 自动回补缺失日期后，立刻同步落盘持久化至 favorite_stocks.json
                    self.save_to_config()
            else:
                with self._lock:
                    self._last_config_mtime = mtime
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
            
            # Windows 下另一进程可能暂时占用文件，重试最多 3 次
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                    os.rename(tmp_path, path)
                    break
                except OSError as win_err:
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                    else:
                        # 所有重试均失败：tmp 文件保留，以备人工处理
                        raise win_err

            with self._lock:
                self._last_config_mtime = os.path.getmtime(path)
            logger.debug(f"Saved favorites to {path}")
        except Exception as e:
            logger.error(f"Failed to save favorites to config: {e}")

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
        code = str(code).strip().zfill(6)
        if not code or code == '000000' or sys_utils.is_delisted_stock(code):
            if sys_utils.is_delisted_stock(code):
                logger.warning(f"🚫 [GlobalFavorites] 拦截添加已知退市死码: {code}")
            return
            
        with self._lock:
            existing_date = self.favorite_stocks_dates.get(code)
            final_date = add_date if add_date else existing_date
            final_date = self._get_default_trade_date(final_date)

            self.favorite_stocks.add(code)
            self.favorite_stocks_dates[code] = final_date
            self._version += 1

        self.save_to_config()

    def add_favorites_batch(self, items, add_date: str = None):
        """批量添加重点关注，支持 code 列表"""
        if not items:
            return

        with self._lock:
            for item in items:
                code = None
                item_date = add_date
                if isinstance(item, str):
                    code = item.strip().zfill(6)
                elif isinstance(item, (tuple, list)) and len(item) >= 1:
                    code = str(item[0]).strip().zfill(6)
                    if len(item) >= 2 and item[1]:
                        item_date = str(item[1])

                if not code or code == '000000' or sys_utils.is_delisted_stock(code):
                    continue

                existing_date = self.favorite_stocks_dates.get(code)
                final_date = item_date if item_date else existing_date
                final_date = self._get_default_trade_date(final_date)

                self.favorite_stocks.add(code)
                self.favorite_stocks_dates[code] = final_date

            self._version += 1

        self.save_to_config()

    def remove_favorite_stock(self, code: str):
        code = str(code).strip().zfill(6)
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
                self._version += 1
            if code in self.favorite_stocks_dates:
                del self.favorite_stocks_dates[code]
        self.save_to_config()

    def toggle_favorite_stock(self, code: str, add_date: str = None):
        code = str(code).strip().zfill(6)
        with self._lock:
            if code in self.favorite_stocks:
                self.favorite_stocks.remove(code)
                if code in self.favorite_stocks_dates:
                    del self.favorite_stocks_dates[code]
                action = "removed"
            else:
                existing_date = self.favorite_stocks_dates.get(code)
                final_date = add_date if add_date else existing_date
                final_date = self._get_default_trade_date(final_date)

                self.favorite_stocks.add(code)
                self.favorite_stocks_dates[code] = final_date
                action = "added"
            self._version += 1

        self.save_to_config()
        return action

    def get_favorite_stock_date(self, code: str) -> str:
        code = str(code).strip().zfill(6)
        should_save = False
        with self._lock:
            date_str = self.favorite_stocks_dates.get(code, "")
            if date_str:
                norm_d = self._get_default_trade_date(date_str)
                if norm_d != date_str:
                    date_str = norm_d
                    self.favorite_stocks_dates[code] = date_str
                    should_save = True
            elif code in self.favorite_stocks:
                # 自动补全为最近交易日保底，确保可视化联动 100% 能找到添加日期
                date_str = self._get_default_trade_date()
                self.favorite_stocks_dates[code] = date_str
                should_save = True

        if should_save:
            self.save_to_config()
        return date_str

    def get_favorite_stocks_dates(self) -> dict:
        should_save = False
        with self._lock:
            default_date = self._get_default_trade_date()
            for code in self.favorite_stocks:
                cur_d = self.favorite_stocks_dates.get(code)
                norm_d = self._get_default_trade_date(cur_d) if cur_d else default_date
                if cur_d != norm_d:
                    self.favorite_stocks_dates[code] = norm_d
                    should_save = True
            res = dict(self.favorite_stocks_dates)

        if should_save:
            self.save_to_config()
        return res

    def get_favorite_sectors(self) -> Set[str]:
        with self._lock:
            return set(self.favorite_sectors)

    def get_favorite_stocks(self) -> Set[str]:
        with self._lock:
            return {str(c).strip().zfill(6) for c in self.favorite_stocks if c}

