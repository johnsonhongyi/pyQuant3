import os
import time
import json
import shutil
import hashlib
import pandas as pd
from typing import Optional, Iterable

def df_fingerprint(
    df: pd.DataFrame,
    cols: Iterable[str],
    sort_by: Optional[str] = None,
    limit: Optional[int] = None,
    encoding: str = "utf-8",
) -> str:
    """
    通用 DataFrame 指纹生成器
    """

    if df is None or df.empty:
        return ""

    _df = df.loc[:, [c for c in cols if c in df.columns]].copy()

    if sort_by and sort_by in _df.columns:
        _df = _df.sort_values(sort_by)
    elif "code" in _df.columns:
        _df = _df.sort_values("code")

    if limit:
        _df = _df.head(limit)

    raw = _df.to_csv(index=False)
    return hashlib.md5(raw.encode(encoding)).hexdigest()



class DataFrameCacheSlot:
    """
    进程内 + 磁盘 双层缓存
    """

    def __init__(
        self,
        cache_file: str,
        fp_file: Optional[str] = None,
        min_disk_free_mb: int = 50,
        logger=None,
    ):
        self.cache_file = cache_file
        self.fp_file = fp_file
        self.min_disk_free_mb = min_disk_free_mb
        self.logger = logger

        self._mem_df: Optional[pd.DataFrame] = None
        self._mem_fp: Optional[dict] = None
        self._mem_ts: float = 0.0

    # =========================
    # DataFrame Cache
    # =========================

    def load_df(self) -> pd.DataFrame:
        if self._mem_df is not None and not self._mem_df.empty:
            return self._mem_df

        # 主文件不存在，尝试加载备份
        if not os.path.exists(self.cache_file):
            bak_file = self.cache_file + ".bak"
            if os.path.exists(bak_file):
                try:
                    if self.logger: self.logger.warning(f"Primary cache missing, restoring from backup: {bak_file}")
                    shutil.copy2(bak_file, self.cache_file)
                except Exception:
                    pass
            else:
                return pd.DataFrame()

        try:
            # 尝试读取主文件
            df = pd.read_pickle(self.cache_file)
            self._mem_df = df
            return df
        except Exception as e:
            if self.logger:
                self.logger.error(f"load_df corrupted ({e}), attempting backup restore...")
            
            # 读取失败，尝试从备份恢复
            bak_file = self.cache_file + ".bak"
            if os.path.exists(bak_file):
                try:
                    df = pd.read_pickle(bak_file)
                    self._mem_df = df
                    if self.logger: self.logger.info("✅ Cache restored from backup successfully.")
                    # 恢复后立即覆盖主文件（修复坏文件）
                    shutil.copy2(bak_file, self.cache_file)
                    return df
                except Exception as bak_e:
                    if self.logger: self.logger.error(f"Backup also corrupted: {bak_e}")
            
            # 都失败了，删除坏文件
            self._safe_remove(self.cache_file)
            return pd.DataFrame()

    def save_df(self, df: pd.DataFrame, persist: bool = True, backup: bool = False) -> bool:
        if df is None or df.empty:
            if self.logger:
                self.logger.warning("save_df skipped: empty df")
            return False

        # 内存优先
        self._mem_df = df
        self._mem_ts = time.time()

        if not persist:
            return True

        try:
            self._check_disk_space()

            # 1. atomic write to temp file
            temp_file = self.cache_file + ".tmp"
            with open(temp_file, "wb") as f:
                df.to_pickle(f)
                f.flush()
                # os.fsync(f.fileno()) # Windows slow, optional
            
            # 2. create backup if exists (Only if backup=True)
            if backup and os.path.exists(self.cache_file):
                bak_file = self.cache_file + ".bak"
                try:
                    # Windows atomic rename restriction workaround
                    if os.path.exists(bak_file):
                        os.remove(bak_file)
                    os.rename(self.cache_file, bak_file)
                except Exception:
                    pass
            elif not backup and os.path.exists(self.cache_file):
                # If no backup needed, just remove the old file before rename
                 try:
                    os.remove(self.cache_file)
                 except Exception:
                    pass

            # 3. rename temp to target
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            os.rename(temp_file, self.cache_file)

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"save_df failed: {e}")
            self._safe_remove(self.cache_file)
            return False

    # =========================
    # Fingerprint Cache
    # =========================

    def load_fp(self) -> dict:
        if self._mem_fp is not None:
            return self._mem_fp

        if self.fp_file and os.path.exists(self.fp_file):
            try:
                with open(self.fp_file, "r", encoding="utf-8") as f:
                    self._mem_fp = json.load(f)
                    return self._mem_fp
            except Exception as e:
                if self.logger:
                    self.logger.error(f"load_fp failed: {e}")

        self._mem_fp = {}
        return self._mem_fp

    def save_fp(self, fp: dict, persist: bool = True):
        if not isinstance(fp, dict):
            return

        self._mem_fp = fp

        if persist and self.fp_file:
            try:
                with open(self.fp_file, "w", encoding="utf-8") as f:
                    json.dump(fp, f)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"save_fp failed: {e}")

    # =========================
    # Utils
    # =========================

    def _check_disk_space(self):
        disk = shutil.disk_usage(os.path.dirname(self.cache_file) or ".")
        if disk.free < self.min_disk_free_mb * 1024 * 1024:
            raise OSError("Disk space insufficient")

    @staticmethod
    def _safe_remove(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
