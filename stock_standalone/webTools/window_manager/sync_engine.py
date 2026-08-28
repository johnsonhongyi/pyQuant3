# -*- coding: utf-8 -*-
"""
RamDisk 实时数据自动同步与备份引擎模块 (RamDisk Sync Engine)
功能：
1. 监控并定期将 RamDisk（内存盘）中的关键数据文件（.h5, .json, .pkl, .csv 等）安全同步到物理硬盘备份目录。
2. 变更指纹检测（Change Detection）：仅当数据有新增或 mtime/size 发生变化时才执行同步，杜绝无意义的磁盘 I/O。
3. 交易日与交易时段过滤：支持配置仅在交易日及交易时段（如 09:15-11:35, 13:00-15:10）执行同步，亦支持全天候模式。
4. Windows 文件锁与并发读写安全（Safe Copy）：采用共享读取、重试与临时文件原子替换（Atomic Swap），防止断电损坏备份文件。
5. 后台多线程守护：提供 RamDiskSyncWorker，支持与 PyQt6 UI 及无界面 CLI 模式无缝集成。
"""

import os
import sys
import time
import json
import fnmatch
import shutil
import uuid
import datetime
from typing import List, Dict, Tuple, Optional, Any

# 尝试导入 PyQt6 信号组件；若在非 GUI / 命令行环境下则优雅降级
try:
    from PyQt6.QtCore import QThread, pyqtSignal, QObject
    HAS_PYQT6 = True
except ImportError:
    HAS_PYQT6 = False
    QThread = object
    pyqtSignal = None
    QObject = object

from . import core


def normalize_dir_path(path_str: str) -> str:
    """
    规范化目录路径。
    特别针对 Windows 盘符（如 'G:' 或 'g:'）转换为标准根路径 'G:\\'，杜绝相对路径歧义。
    """
    if not path_str:
        return ""
    p = os.path.expanduser(os.path.expandvars(str(path_str).strip()))
    # 处理类似 "G:" 或 "g:" 的纯盘符
    if len(p) == 2 and p[1] == ":" and p[0].isalpha():
        return p.upper() + "\\"
    return os.path.abspath(p)


def detect_default_ramdisk_dir() -> str:
    """智能自动探测当前系统中的 RamDisk 物理路径"""
    # 1. 优先尝试从系统已加载的 commonTips 获取
    try:
        from JohnsonUtil import commonTips as cct
        ram_dir = cct.get_ramdisk_dir()
        if ram_dir and os.path.exists(ram_dir):
            return normalize_dir_path(ram_dir)
    except Exception:
        pass

    # 2. 常见 Windows / Linux / macOS RamDisk 候选路径探测
    candidates = [
        r"R:",
        r"R:\\",
        r"G:",
        r"G:\\",
        r"D:\Ramdisk",
        r"E:\Ramdisk",
        r"C:\Ramdisk",
        "/Volumes/RamDisk",
        "/mnt/ramdisk",
        "/dev/shm"
    ]
    for c in candidates:
        if os.path.exists(c):
            return normalize_dir_path(c)

    # 3. 环境变量探测
    env_ram = os.environ.get("RAMDISK_DIR")
    if env_ram and os.path.exists(env_ram):
        return normalize_dir_path(env_ram)

    # 4. 若均未探测到，返回推荐默认路径 D:\Ramdisk
    return r"D:\Ramdisk"


def detect_default_backup_dir() -> str:
    """智能自动探测默认物理硬盘备份目录"""
    # 优先使用物理磁盘 D:\Ramdisk_Backup
    if os.path.exists(r"D:\\"):
        return r"D:\Ramdisk_Backup"
    elif os.path.exists(r"E:\\"):
        return r"E:\Ramdisk_Backup"
    
    # 否则默认使用程序根目录下的 backup\ramdisk 文件夹
    app_root = core.get_app_root()
    return os.path.join(app_root, "backup", "ramdisk")


class RamDiskSyncConfig:
    """RamDisk 自动同步配置管理器"""
    
    DEFAULT_CONFIG_FILE = "ramdisk_sync_config.json"
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = core.get_conf_path(self.DEFAULT_CONFIG_FILE)
        self.config_path = config_path
        
        # 配置属性与默认值
        self.enabled: bool = True
        self.sync_interval_sec: int = 30
        self.only_trading_hours: bool = True
        self.trading_hours: List[List[str]] = [
            ["09:15", "11:35"],
            ["13:00", "15:10"]
        ]
        self.only_workdays: bool = True
        self.source_dir: str = ""
        self.target_dir: str = ""
        self.sync_scope: str = "specific_files"  # "specific_files" (仅同步多选指定的具体文件) | "all_directory" (同步源目录下匹配通配符的所有文件)
        self.specific_files: List[str] = []
        self.file_patterns: List[str] = ["*.h5", "*.json", "*.pkl", "*.csv", "*.txt", "*.db", "*.parquet"]
        self.backup_mode: str = "mirror"  # "mirror" (镜像覆盖) | "date_folder" (每日日期归档) | "diff_snapshot" (差异快照版本归档)
        self.keep_backup_days: int = 7  # 历史日期归档与差异快照保留天数 (0 表示永久保留，默认 7 天)
        self.max_snapshots_per_file: int = 10  # diff_snapshot 模式下单文件同日最大保留版本数
        self.safe_copy_retry: int = 3
        self.safe_copy_retry_delay: float = 0.2
        self.atomic_swap: bool = True
        self.log_enabled: bool = False  # 日志开关：开启时输出每次巡检详细调试日志，默认关闭以避免刷屏
        
        self.load()

    def load(self):
        """从 JSON 配置文件加载"""
        loaded_data = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
            except Exception as e:
                print(f"[RamDiskSyncConfig] 读取配置失败: {e}", file=sys.stderr)
        
        # 赋值并填充默认值
        self.enabled = bool(loaded_data.get("enabled", True))
        self.sync_interval_sec = max(5, int(loaded_data.get("sync_interval_sec", 30)))
        self.only_trading_hours = bool(loaded_data.get("only_trading_hours", True))
        
        th = loaded_data.get("trading_hours")
        if isinstance(th, list) and len(th) > 0:
            self.trading_hours = th
        else:
            self.trading_hours = [["09:15", "11:35"], ["13:00", "15:10"]]
            
        self.only_workdays = bool(loaded_data.get("only_workdays", True))
        
        src = loaded_data.get("source_dir", "")
        self.source_dir = normalize_dir_path(src) if src else detect_default_ramdisk_dir()
        
        tgt = loaded_data.get("target_dir", "")
        self.target_dir = normalize_dir_path(tgt) if tgt else detect_default_backup_dir()
        
        self.sync_scope = loaded_data.get("sync_scope", "specific_files")
        self.specific_files = loaded_data.get("specific_files", [])
        
        fp = loaded_data.get("file_patterns")
        if isinstance(fp, list) and len(fp) > 0:
            self.file_patterns = fp
        else:
            self.file_patterns = ["*.h5", "*.json", "*.pkl", "*.csv", "*.txt", "*.db", "*.parquet"]
            
        self.backup_mode = loaded_data.get("backup_mode", "mirror")
        self.keep_backup_days = max(0, int(loaded_data.get("keep_backup_days", 7)))
        self.max_snapshots_per_file = max(1, int(loaded_data.get("max_snapshots_per_file", 10)))
        self.safe_copy_retry = int(loaded_data.get("safe_copy_retry", 3))
        self.safe_copy_retry_delay = float(loaded_data.get("safe_copy_retry_delay", 0.2))
        self.atomic_swap = bool(loaded_data.get("atomic_swap", True))
        self.log_enabled = bool(loaded_data.get("log_enabled", False))

    def save(self) -> bool:
        """持久化配置到 JSON 文件"""
        data = self.to_dict()
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[RamDiskSyncConfig] 保存配置失败: {e}", file=sys.stderr)
            return False

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "sync_interval_sec": self.sync_interval_sec,
            "only_trading_hours": self.only_trading_hours,
            "trading_hours": self.trading_hours,
            "only_workdays": self.only_workdays,
            "source_dir": self.source_dir,
            "target_dir": self.target_dir,
            "sync_scope": self.sync_scope,
            "specific_files": self.specific_files,
            "file_patterns": self.file_patterns,
            "backup_mode": self.backup_mode,
            "keep_backup_days": self.keep_backup_days,
            "max_snapshots_per_file": self.max_snapshots_per_file,
            "safe_copy_retry": self.safe_copy_retry,
            "safe_copy_retry_delay": self.safe_copy_retry_delay,
            "atomic_swap": self.atomic_swap,
            "log_enabled": self.log_enabled
        }

    def from_dict(self, data: dict):
        if not isinstance(data, dict):
            return
        if "enabled" in data:
            self.enabled = bool(data["enabled"])
        if "sync_interval_sec" in data:
            self.sync_interval_sec = max(5, int(data["sync_interval_sec"]))
        if "only_trading_hours" in data:
            self.only_trading_hours = bool(data["only_trading_hours"])
        if "trading_hours" in data and isinstance(data["trading_hours"], list):
            self.trading_hours = data["trading_hours"]
        if "only_workdays" in data:
            self.only_workdays = bool(data["only_workdays"])
        if "source_dir" in data:
            self.source_dir = normalize_dir_path(str(data["source_dir"]))
        if "target_dir" in data:
            self.target_dir = normalize_dir_path(str(data["target_dir"]))
        if "sync_scope" in data:
            self.sync_scope = str(data["sync_scope"])
        if "specific_files" in data and isinstance(data["specific_files"], list):
            self.specific_files = data["specific_files"]
        if "file_patterns" in data and isinstance(data["file_patterns"], list):
            self.file_patterns = data["file_patterns"]
        if "backup_mode" in data:
            self.backup_mode = str(data["backup_mode"])
        if "keep_backup_days" in data:
            self.keep_backup_days = max(0, int(data["keep_backup_days"]))
        if "max_snapshots_per_file" in data:
            self.max_snapshots_per_file = max(1, int(data["max_snapshots_per_file"]))
        if "safe_copy_retry" in data:
            self.safe_copy_retry = int(data["safe_copy_retry"])
        if "safe_copy_retry_delay" in data:
            self.safe_copy_retry_delay = float(data["safe_copy_retry_delay"])
        if "atomic_swap" in data:
            self.atomic_swap = bool(data["atomic_swap"])
        if "log_enabled" in data:
            self.log_enabled = bool(data["log_enabled"])


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小为易读字符串（如 140.5MB, 50.9KB）"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"


class RamDiskSyncEngine:
    """RamDisk 自动同步核心引擎"""
    
    def __init__(self, config: Optional[RamDiskSyncConfig] = None):
        self.config = config or RamDiskSyncConfig()
        # 内存中维护的已同步文件指纹: { relative_path: (mtime, size) }
        self._synced_fingerprints: Dict[str, Tuple[float, int]] = {}
        self._last_sync_time: float = 0.0
        self._last_sync_result: Dict[str, Any] = {}

    def get_effective_target_dir(self, dt: Optional[datetime.datetime] = None) -> str:
        """
        获取当前备份模式下实际生效的目标目录绝对路径。
        例如：
        - mirror: D:\\Ramdisk_Backup
        - date_folder / diff_snapshot: D:\\Ramdisk_Backup\\20260828
        """
        if dt is None:
            dt = datetime.datetime.now()
        target_root = normalize_dir_path(self.config.target_dir) or detect_default_backup_dir()
        if self.config.backup_mode in ["date_folder", "diff_snapshot"]:
            today_str = dt.strftime("%Y%m%d")
            return os.path.join(target_root, today_str)
        return target_root

    def is_in_trading_time(self, dt: Optional[datetime.datetime] = None) -> Tuple[bool, str]:
        """
        判断指定时间是否符合交易日与交易时段约束。
        返回: (is_valid: bool, reason: str)
        """
        if dt is None:
            dt = datetime.datetime.now()

        # 1. 判断是否仅在工作日/交易日执行
        if self.config.only_workdays:
            # 0=周一, 6=周日
            if dt.weekday() >= 5:
                return False, f"非工作日 (周{['一','二','三','四','五','六','日'][dt.weekday()]})"
            
            # 尝试通过 commonTips 检查法定节假日
            try:
                from JohnsonUtil import commonTips as cct
                if hasattr(cct, "is_trade_date") and not cct.is_trade_date(dt.date()):
                    return False, "非交易日 (法定节假日/休市)"
            except Exception:
                pass

        # 2. 判断是否仅在交易时段执行
        if self.config.only_trading_hours:
            current_time_str = dt.strftime("%H:%M")
            in_slot = False
            for slot in self.config.trading_hours:
                if len(slot) == 2:
                    start_str, end_str = slot[0], slot[1]
                    if start_str <= current_time_str <= end_str:
                        in_slot = True
                        break
            if not in_slot:
                return False, f"非交易时段 ({current_time_str})"

        return True, "在交易时段内"

    def scan_source_files(self) -> List[str]:
        """
        扫描或获取待同步的文件列表（相对于源目录的相对路径）。
        支持多选指定文件模式 (specific_files) 与全目录扫描模式 (all_directory)。
        """
        src_root = normalize_dir_path(self.config.source_dir)
        if not src_root or not os.path.exists(src_root):
            return []

        matched_files = set()

        # 模式 1：如果配置为 specific_files（多选指定文件），严格只处理用户多选选定的文件
        if self.config.sync_scope == "specific_files":
            for spec_f in self.config.specific_files:
                if not spec_f:
                    continue
                if os.path.isabs(spec_f):
                    abs_p = spec_f
                else:
                    abs_p = os.path.join(src_root, spec_f)
                
                if os.path.exists(abs_p) and os.path.isfile(abs_p):
                    try:
                        rel_p = os.path.relpath(abs_p, src_root)
                        # 若相对路径跳出源目录根层级（如 .. 开头），退化为 basename 避免目录穿越
                        if rel_p.startswith("..") or os.path.isabs(rel_p):
                            rel_p = os.path.basename(abs_p)
                        matched_files.add(rel_p)
                    except Exception:
                        matched_files.add(os.path.basename(abs_p))
            return sorted(list(matched_files))

        # 模式 2：全目录通配符扫描
        patterns = self.config.file_patterns or ["*"]
        try:
            for root, dirs, files in os.walk(src_root):
                # 排除临时文件和回收站目录
                dirs[:] = [d for d in dirs if not d.startswith("$") and d.lower() not in ["temp", "tmp", ".git"]]
                for f in files:
                    if f.startswith("~$") or f.endswith(".tmp") or f.endswith(".lock"):
                        continue
                    # 匹配通配符
                    if any(fnmatch.fnmatch(f, pat) for pat in patterns):
                        abs_p = os.path.join(root, f)
                        rel_p = os.path.relpath(abs_p, src_root)
                        matched_files.add(rel_p)
        except Exception as e:
            print(f"[RamDiskSyncEngine] 扫描源目录异常: {e}", file=sys.stderr)

        return sorted(list(matched_files))

    def is_file_changed(self, rel_path: str, target_base_dir: str) -> Tuple[bool, str]:
        """
        判断单个文件是否有变动需要同步。
        返回: (has_changed: bool, reason: str)
        """
        src_root = normalize_dir_path(self.config.source_dir)
        src_path = os.path.join(src_root, rel_path)
        dst_path = os.path.join(target_base_dir, rel_path)

        if not os.path.exists(src_path):
            return False, "源文件不存在"

        try:
            src_stat = os.stat(src_path)
            src_mtime = src_stat.st_mtime
            src_size = src_stat.st_size
        except Exception as e:
            return False, f"获取源文件状态失败: {e}"

        # 目标文件不存在 -> 新文件
        if not os.path.exists(dst_path):
            return True, "目标文件不存在 (新增)"

        try:
            dst_stat = os.stat(dst_path)
            dst_mtime = dst_stat.st_mtime
            dst_size = dst_stat.st_size
        except Exception as e:
            return True, f"获取目标文件状态失败，强制同步: {e}"

        # 大小发生变化
        if src_size != dst_size:
            return True, f"文件大小变化 ({format_file_size(dst_size)} -> {format_file_size(src_size)})"

        # 源文件修改时间显著晚于目标文件（允许 0.9s 跨文件系统/FAT/NTFS 精度误差）
        if src_mtime - dst_mtime > 0.9:
            return True, f"源文件更新 (src:{time.ctime(src_mtime)} > dst:{time.ctime(dst_mtime)})"

        # 内存指纹比对
        last_fp = self._synced_fingerprints.get(rel_path)
        if last_fp and (abs(src_mtime - last_fp[0]) > 0.9 or src_size != last_fp[1]):
            return True, "内存指纹变动"

        return False, "无变化 (指纹完全一致)"

    def clean_expired_backup_folders(self, target_base_dir: Optional[str] = None) -> List[str]:
        """
        根据 keep_backup_days 配置清理过期的历史日期归档目录（如 20260815）。
        仅在 backup_mode 为 'date_folder' 或 'diff_snapshot' 且 keep_backup_days > 0 时执行。
        返回被清理的目录名称列表。
        """
        if self.config.backup_mode not in ["date_folder", "diff_snapshot"]:
            return []
        
        keep_days = getattr(self.config, "keep_backup_days", 7)
        if keep_days <= 0:
            return []

        target_root = normalize_dir_path(target_base_dir or self.config.target_dir) or detect_default_backup_dir()
        if not target_root or not os.path.exists(target_root):
            return []

        today = datetime.date.today()
        cleaned_dirs = []

        try:
            for item in os.listdir(target_root):
                item_path = os.path.join(target_root, item)
                if not os.path.isdir(item_path):
                    continue
                # 判断是否为 8 位纯数字日期目录 YYYYMMDD
                if len(item) == 8 and item.isdigit():
                    try:
                        folder_year = int(item[0:4])
                        folder_month = int(item[4:6])
                        folder_day = int(item[6:8])
                        folder_date = datetime.date(folder_year, folder_month, folder_day)
                        days_diff = (today - folder_date).days
                        if days_diff > keep_days:
                            shutil.rmtree(item_path, ignore_errors=True)
                            cleaned_dirs.append(item)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[RamDiskSyncEngine] 清理过期备份目录异常: {e}", file=sys.stderr)

        return cleaned_dirs

    def _rotate_diff_snapshots(self, target_base_dir: str, rel_path: str, max_keep: int = 10):
        """
        清理超出最大保留数量的历史差异快照。
        """
        if max_keep <= 0:
            return
        dst_full = os.path.join(target_base_dir, rel_path)
        dst_dir = os.path.dirname(dst_full)
        stem, ext = os.path.splitext(os.path.basename(rel_path))
        prefix = f"{stem}_"

        try:
            if not os.path.exists(dst_dir):
                return
            snapshot_files = []
            for f in os.listdir(dst_dir):
                if f.startswith(prefix) and f.endswith(ext) and f != os.path.basename(rel_path):
                    p = os.path.join(dst_dir, f)
                    if os.path.isfile(p):
                        try:
                            snapshot_files.append((p, os.path.getmtime(p)))
                        except Exception:
                            pass

            # 按修改时间从新到旧排序
            snapshot_files.sort(key=lambda x: x[1], reverse=True)
            # 超出上限的旧快照予以删除
            if len(snapshot_files) > max_keep:
                for old_p, _ in snapshot_files[max_keep:]:
                    try:
                        os.remove(old_p)
                    except Exception:
                        pass
        except Exception:
            pass

    def safe_copy_file(self, src_path: str, dst_path: str) -> Tuple[bool, str]:
        """
        Windows 文件锁安全原子写入与复制：
        1. 使用只读共享模式打开，防范被其他进程正在写入时的文件锁报错。
        2. 指数退避重试（针对偶发冲突）。
        3. 先复制到目标目录下的临时文件 .tmp.<uuid>，完整性核验后 os.replace 原子替换。
        4. 保留源文件时间戳与属性 (shutil.copystat)。
        """
        retries = max(1, self.config.safe_copy_retry)
        delay = max(0.05, self.config.safe_copy_retry_delay)
        last_err = ""

        dst_dir = os.path.dirname(dst_path)
        os.makedirs(dst_dir, exist_ok=True)

        for attempt in range(retries):
            tmp_dst = None
            try:
                if self.config.atomic_swap:
                    tmp_filename = f".sync_{uuid.uuid4().hex[:8]}_{os.path.basename(dst_path)}.tmp"
                    tmp_dst = os.path.join(dst_dir, tmp_filename)
                else:
                    tmp_dst = dst_path

                # 分块安全读写（4MB 缓冲区）
                with open(src_path, "rb") as f_src:
                    with open(tmp_dst, "wb") as f_dst:
                        shutil.copyfileobj(f_src, f_dst, length=4 * 1024 * 1024)

                # 同步元数据（时间戳与属性）
                try:
                    shutil.copystat(src_path, tmp_dst)
                except Exception:
                    pass

                # 原子替换目标文件
                if self.config.atomic_swap and tmp_dst != dst_path:
                    os.replace(tmp_dst, dst_path)

                # 确保替换后的目标文件 mtime 严格与源文件一致
                try:
                    shutil.copystat(src_path, dst_path)
                except Exception:
                    pass

                return True, "OK"

            except (PermissionError, OSError) as e:
                last_err = f"IO/锁定错误: {e}"
                if tmp_dst and os.path.exists(tmp_dst) and tmp_dst != dst_path:
                    try:
                        os.remove(tmp_dst)
                    except Exception:
                        pass
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
            except Exception as e:
                last_err = f"未预期异常: {e}"
                if tmp_dst and os.path.exists(tmp_dst) and tmp_dst != dst_path:
                    try:
                        os.remove(tmp_dst)
                    except Exception:
                        pass
                break

        return False, last_err

    def sync_once(self, force: bool = False, ignore_time_filter: bool = False) -> Dict[str, Any]:
        """
        执行一次同步巡检与文件备份。
        
        :param force: 是否强制全量同步（忽略指纹比对）
        :param ignore_time_filter: 是否忽略交易时段/工作日限制（用于手动立即同步按钮）
        :return: 结构化结果字典
        """
        start_time = time.time()
        now_dt = datetime.datetime.now()
        timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        result = {
            "status": "ok",
            "timestamp": timestamp_str,
            "effective_target": "",
            "synced_files": [],               # 纯相对路径列表，如 ["sina_MultiIndex_data.h5"]
            "synced_files_display": [],       # 包含文件名与大小，如 ["sina_MultiIndex_data.h5 (140.5MB)"]
            "synced_file_names": [],          # 纯文件名列表，如 ["sina_MultiIndex_data.h5"]
            "skipped_files": [],              # 跳过文件名列表，如 ["tdx_last_df.h5 (无变动)"]
            "skipped_count": 0,
            "failed_files": [],
            "message": "",
            "duration_ms": 0.0
        }

        # 1. 检查开关
        if not self.config.enabled and not force:
            result["status"] = "skipped"
            result["message"] = "自动同步已停用"
            self._last_sync_result = result
            return result

        # 2. 检查交易时段限制
        if not ignore_time_filter:
            in_trading, reason = self.is_in_trading_time(now_dt)
            if not in_trading:
                result["status"] = "skipped"
                th_desc = ", ".join([f"{s[0]}-{s[1]}" for s in self.config.trading_hours]) if self.config.trading_hours else "未配置"
                result["message"] = f"巡检待命跳过: {reason} (交易时段: {th_desc})"
                self._last_sync_result = result
                return result

        # 3. 检查源目录是否存在
        src_root = normalize_dir_path(self.config.source_dir)
        if not src_root or not os.path.exists(src_root):
            result["status"] = "error"
            result["message"] = f"源目录不存在: {src_root}"
            self._last_sync_result = result
            return result

        # 4. 确定实际生效的目标目录
        effective_target = self.get_effective_target_dir(now_dt)
        result["effective_target"] = effective_target
        os.makedirs(effective_target, exist_ok=True)

        # 5. 扫描源文件并逐一比对指纹
        matched_files = self.scan_source_files()
        if not matched_files:
            result["message"] = f"源目录 ({src_root}) 下无匹配的待同步文件"
            result["duration_ms"] = round((time.time() - start_time) * 1000, 2)
            self._last_sync_result = result
            return result

        for rel_p in matched_files:
            src_full = os.path.join(src_root, rel_p)
            dst_full = os.path.join(effective_target, rel_p)

            # 获取源文件大小描述
            try:
                stat_tmp = os.stat(src_full)
                sz_str = format_file_size(stat_tmp.st_size)
            except Exception:
                sz_str = ""

            # 判断是否有变动
            if force:
                changed = True
                change_reason = "强制全量同步"
            else:
                changed, change_reason = self.is_file_changed(rel_p, effective_target)

            if not changed:
                result["skipped_count"] += 1
                result["skipped_files"].append(f"{os.path.basename(rel_p)} ({change_reason})")
                continue

            # 执行主目标文件安全原子复制
            success, err_msg = self.safe_copy_file(src_full, dst_full)
            if success:
                try:
                    stat = os.stat(src_full)
                    self._synced_fingerprints[rel_p] = (stat.st_mtime, stat.st_size)
                except Exception:
                    pass

                # 若启用 diff_snapshot 差异快照版本归档模式，同时保留一份带时间戳的历史快照
                if self.config.backup_mode == "diff_snapshot":
                    stem, ext = os.path.splitext(rel_p)
                    time_tag = now_dt.strftime("%H%M%S")
                    snap_rel = f"{stem}_{time_tag}{ext}"
                    snap_dst = os.path.join(effective_target, snap_rel)
                    self.safe_copy_file(src_full, snap_dst)
                    # 轮转清理超额旧快照
                    self._rotate_diff_snapshots(effective_target, rel_p, max_keep=self.config.max_snapshots_per_file)

                display_desc = f"{os.path.basename(rel_p)} ({sz_str})" if sz_str else os.path.basename(rel_p)
                result["synced_files"].append(rel_p)
                result["synced_files_display"].append(display_desc)
                result["synced_file_names"].append(os.path.basename(rel_p))
            else:
                result["failed_files"].append((os.path.basename(rel_p), err_msg))

        # 6. 整理清晰透明的汇总日志并清理超期历史日期归档
        duration = round((time.time() - start_time) * 1000, 2)
        result["duration_ms"] = duration
        self._last_sync_time = time.time()

        # 触发超期历史归档文件夹清理
        cleaned_dirs = self.clean_expired_backup_folders()
        result["cleaned_expired_dirs"] = cleaned_dirs

        synced_desc = ", ".join(result["synced_files_display"])
        skipped_names = [f.split()[0] for f in result["skipped_files"]]
        skipped_desc = ", ".join(skipped_names)
        clean_msg = f" (已清理 {len(cleaned_dirs)} 个超期历史归档: {', '.join(cleaned_dirs)})" if cleaned_dirs else ""

        if result["failed_files"]:
            result["status"] = "error" if not result["synced_files"] else "partial"
            result["message"] = (
                f"同步完成 (耗时 {duration}ms): 成功 {len(result['synced_files'])} 个 [{synced_desc}] -> {effective_target}，"
                f"失败 {len(result['failed_files'])} 个，未变动跳过 {result['skipped_count']} 个{clean_msg}。"
            )
        elif result["synced_files"]:
            result["status"] = "ok"
            msg_tail = f"，未变动跳过 {result['skipped_count']} 个 [{skipped_desc}]" if skipped_names else ""
            result["message"] = (
                f"同步成功 (耗时 {duration}ms): 更新 {len(result['synced_files'])} 个 [{synced_desc}] -> {effective_target}{msg_tail}{clean_msg}。"
            )
        else:
            result["status"] = "ok"
            result["message"] = f"巡检完成 (耗时 {duration}ms): 所有 {result['skipped_count']} 个文件 [{skipped_desc}] 均无变化，已跳过 I/O{clean_msg}。"

        self._last_sync_result = result
        return result

    def check_and_sync_startup_baseline(self) -> Dict[str, Any]:
        """
        程序启动时的初检与基线初始化同步。
        特点：不受交易时间限制 (ignore_time_filter=True)。
        检查目标备份位置中是否存在缺失文件或不一致数据，若存在则自动执行同步补齐底包。
        """
        if not self.config.enabled:
            return {
                "status": "disabled",
                "message": "RamDisk 自动同步未启用",
                "synced_files": [],
                "synced_file_names": [],
                "skipped_files": [],
                "skipped_count": 0,
                "failed_files": []
            }
        
        # 执行不受交易时间限制的增量同步
        result = self.sync_once(force=False, ignore_time_filter=True)
        if result.get("synced_files"):
            result["message"] = f"启动初检初始化完成: 发现并同步补全了 {len(result['synced_files'])} 个目标缺失/变动文件 [{', '.join(result['synced_files'])}] -> {result.get('effective_target', '')}。"
        elif result.get("status") == "ok":
            result["message"] = f"启动初检完成: 目标备份位置数据完整且与源目录一致 (共核验 {result.get('skipped_count', 0)} 个文件)。"
        return result


class RamDiskSyncWorker(QThread if HAS_PYQT6 else object):
    """
    后台自动同步守护线程。
    在 PyQt6 环境下支持 pyqtSignal 信号通知，在标准控制台环境下支持回调函数机制。
    """
    if HAS_PYQT6 and pyqtSignal:
        sync_completed = pyqtSignal(dict)  # 每次同步完成派发结果字典
        status_updated = pyqtSignal(str)   # 状态简报文字

    def __init__(self, engine: Optional[RamDiskSyncEngine] = None, parent=None):
        if HAS_PYQT6 and QThread != object:
            super().__init__(parent)
        self.engine = engine or RamDiskSyncEngine()
        self._running = False
        self._trigger_event = False
        self._status_callback = None
        self._result_callback = None

    def set_callbacks(self, on_status=None, on_result=None):
        """设置纯 Python 模式下的回调函数"""
        self._status_callback = on_status
        self._result_callback = on_result

    def run(self):
        """线程主执行循环"""
        self._running = True
        self._emit_status("RamDisk 自动同步守护已启动")

        # 1. 启动后先执行不受交易时间限制的初检与基线初始化同步（确保非交易时段目标位置缺失时也能建好底包）
        try:
            init_res = self.engine.check_and_sync_startup_baseline()
            self._emit_result(init_res)
        except Exception as e:
            self._emit_status(f"启动初检异常: {e}")

        while self._running:
            # 依据配置的间隔秒数进行休眠
            interval = max(5, self.engine.config.sync_interval_sec)
            
            # 分步精准休眠并监听手动触发或停止事件
            for _ in range(interval * 2):
                if not self._running:
                    break
                if self._trigger_event:
                    self._trigger_event = False
                    break
                time.sleep(0.5)

            if not self._running:
                break

            # 执行周期性同步
            try:
                res = self.engine.sync_once(force=False)
                self._emit_result(res)
            except Exception as e:
                self._emit_status(f"同步执行异常: {e}")

        self._emit_status("RamDisk 自动同步守护已停止")

    def trigger_sync_now(self, force: bool = False):
        """外部主动触发一次立即同步（无需等待间隔倒计时）"""
        self._trigger_event = True
        try:
            res = self.engine.sync_once(force=force, ignore_time_filter=True)
            self._emit_result(res)
            return res
        except Exception as e:
            err_res = {
                "status": "error",
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "synced_files": [],
                "skipped_count": 0,
                "failed_files": [],
                "message": f"手动同步失败: {e}",
                "duration_ms": 0.0
            }
            self._emit_result(err_res)
            return err_res

    def stop(self):
        """安全停止后台线程"""
        self._running = False
        self._trigger_event = True
        if HAS_PYQT6 and hasattr(self, "wait") and callable(self.wait):
            self.wait(1500)

    def _emit_status(self, text: str):
        if HAS_PYQT6 and hasattr(self, "status_updated") and self.status_updated:
            try:
                self.status_updated.emit(text)
            except Exception:
                pass
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass

    def _emit_result(self, res: dict):
        if HAS_PYQT6 and hasattr(self, "sync_completed") and self.sync_completed:
            try:
                self.sync_completed.emit(res)
            except Exception:
                pass
        if self._result_callback:
            try:
                self._result_callback(res)
            except Exception:
                pass
