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
            # 优先尝试 zstd 压缩读取
            df = pd.read_pickle(self.cache_file, compression='zstd')
            self._mem_df = df
            return df
        except Exception:
            try:
                # 兜底：尝试传统无压缩方式读取（兼容旧文件）
                df = pd.read_pickle(self.cache_file)
                self._mem_df = df
                # [Optimization] 如果是老文件，可以在此处标记下次保存会自动转为 zstd
                return df
            except Exception as e:
                if self.logger:
                    self.logger.error(f"load_df corrupted ({e}), attempting backup restore...")
                
                # 读取失败，尝试从备份恢复
                bak_file = self.cache_file + ".bak"
                if os.path.exists(bak_file):
                    try:
                        # 备份文件也优先尝试 zstd
                        try:
                            df = pd.read_pickle(bak_file, compression='zstd')
                        except:
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

    def save_df(self, df: pd.DataFrame, persist: bool = True, backup: bool = False, min_rows_factor: float = 0.5, force: bool = False) -> bool:
        if df is None or df.empty:
            if self.logger:
                self.logger.warning("save_df skipped: empty df")
            return False

        # 内存优先
        self._mem_df = df
        self._mem_ts = time.time()

        if not persist:
            return True

        if not force and os.path.exists(self.cache_file):
            try:
                # [PROTECTION] 如果新数据量远小于旧数据量，拦截覆盖
                # 仅在非强制模式下检查
                new_count = len(df)
                # 使用读取方式（可能较慢但安全）
                try:
                    old_df_meta = pd.read_pickle(self.cache_file, compression='zstd')
                except Exception:
                    old_df_meta = pd.read_pickle(self.cache_file)
                
                old_count = len(old_df_meta)
                if new_count < old_count * min_rows_factor:
                    if self.logger:
                        self.logger.error(f"🛑 [DataProtection] Save BLOCKED: New rows({new_count}) < {min_rows_factor} * Old rows({old_count}). Set force=True to overwrite.")
                    return False
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Data volume check failed (corrupted old file?), proceeding: {e}")

        temp_file = self.cache_file + f".{os.getpid()}.tmp"
        try:
            self._check_disk_space()

            # 1. atomic write to temp file
            with open(temp_file, "wb") as f:
                df.to_pickle(f, compression='zstd')
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            
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

            # 3. replace target with temp
            # os.replace is atomic and works on Windows for replacing existing files
            os.replace(temp_file, self.cache_file)
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"save_df failed: {e}")
            self._safe_remove(temp_file)
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
            temp_fp = self.fp_file + f".{os.getpid()}.tmp"
            try:
                with open(temp_fp, "w", encoding="utf-8") as f:
                    json.dump(fp, f)
                    f.flush()
                os.replace(temp_fp, self.fp_file)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"save_fp failed: {e}")
                self._safe_remove(temp_fp)

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
