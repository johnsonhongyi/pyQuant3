# -*- coding:utf-8 -*-
"""
sys_utils.py - 异动联动系统级路径与环境权威解析模块
全面对齐 TK / ATS 成熟打包路径体系，原生支持 Nuitka Onefile / PyInstaller / 源码开发环境。
彻底根除 Nuitka Onefile 模式下路径被劫持至临时解压目录导致配置文件与持久化数据丢失的问题。
"""
import os
import sys
import json
import shutil
from typing import Optional, Any, Dict

# 全局环境缓存，确保子进程完美继承父进程定位的物理路径
_CACHED_APP_ROOT: Optional[str] = None

RESOURCE_MAP: Dict[str, Dict[str, str]] = {
    "globalYD.ini": {
        "src": "globalYD.ini",
        "dst": "globalYD.ini"
    },
    "code_ths_other.json": {
        "src": "code_ths_other.json",
        "dst": "code_ths_other.json"
    },
    "window_config.json": {
        "src": "window_config.json",
        "dst": "window_config.json"
    },
    "query_history.json": {
        "src": "query_history.json",
        "dst": "query_history.json"
    },
    "alerts.json": {
        "src": "alerts.json",
        "dst": "alerts.json"
    },
    "monitor_list.json": {
        "src": "monitor_list.json",
        "dst": "monitor_list.json"
    },
    "custom_focus_stocks.json": {
        "src": "custom_focus_stocks.json",
        "dst": "custom_focus_stocks.json"
    },
    "filter_stock_codes.json": {
        "src": "filter_stock_codes.json",
        "dst": "filter_stock_codes.json"
    },
    "app.ico": {
        "src": "app.ico",
        "dst": "app.ico"
    }
}

def is_packaged_env() -> bool:
    """判断当前运行环境是否为打包后的可执行程序 (PyInstaller / Nuitka)"""
    if getattr(sys, "frozen", False):
        return True
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ or "NUITKA_ONEFILE_BINARY" in os.environ or "_MEIPASS" in os.environ:
        return True
    if hasattr(sys, "nuitka_version"):
        return True
    if "__compiled__" in globals():
        return True
    main_mod = sys.modules.get("__main__")
    if main_mod is not None and (hasattr(main_mod, "__compiled__") or "__compiled__" in getattr(main_mod, "__dict__", {})):
        return True
    exe_name = os.path.basename(sys.executable or "").lower()
    if exe_name.endswith(".exe") and not (exe_name.startswith("python") or "pytest" in exe_name):
        return True
    return False

def safe_resolve_path(path: Any) -> Any:
    """安全解析路径，避免在 Windows 内存盘 (RamDisk) 上因 GetFinalPathNameByHandle 抛错"""
    from pathlib import Path
    p = Path(path) if not isinstance(path, Path) else path
    try:
        return p.resolve()
    except OSError:
        return p.absolute()

def _is_inside_temp_dir(path: str) -> bool:
    """严密检测指定路径是否位于任何系统临时目录或打包临时解压目录内部"""
    if not path:
        return False
    path_norm = os.path.normpath(os.path.normcase(os.path.abspath(path)))
    
    # 1. 检查所有相关环境变量指向的临时目录
    for env_name in ("NUITKA_ONEFILE_DIRECTORY", "TEMP", "TMP", "SystemRoot"):
        env_val = os.environ.get(env_name)
        if env_val:
            try:
                env_norm = os.path.normpath(os.path.normcase(os.path.abspath(env_val)))
                if env_norm in path_norm:
                    return True
            except:
                pass
            try:
                env_real = os.path.normpath(os.path.normcase(os.path.realpath(env_val)))
                if env_real in path_norm:
                    return True
            except:
                pass

    # 2. 物理规则模糊判定 (针对 stockalerts_nuitka, onefile_, _meipass, \temp\ 等)
    for pattern in (
        "stockalerts_nuitka", "ats_nuitka", "instock_nuitka",
        "onefile_", "_meipass", "\\temp\\", "/temp/",
    ):
        if pattern in path_norm:
            return True
            
    return False

def get_app_root() -> str:
    """
    Nuitka / PyInstaller / dev 统一兼容的物理可执行程序所在绝对根目录。
    100% 保证指向用户物理磁盘上真实保存配置与持久化数据的目录，绝不落入 Temp 临时解压目录！
    """
    global _CACHED_APP_ROOT
    if _CACHED_APP_ROOT and os.path.exists(_CACHED_APP_ROOT):
        return _CACHED_APP_ROOT

    # 优先从环境变量获取，确保子进程完美继承父进程定位的物理路径
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        _CACHED_APP_ROOT = env_root
        return env_root

    # 0. Nuitka Onefile 模式官方权威环境变量：NUITKA_ONEFILE_BINARY
    onefile_bin = os.environ.get("NUITKA_ONEFILE_BINARY")
    if onefile_bin:
        calculated_root = os.path.dirname(os.path.abspath(onefile_bin))
        if os.path.exists(calculated_root):
            _CACHED_APP_ROOT = calculated_root
            os.environ["INSTOCK_APP_ROOT"] = calculated_root
            return calculated_root

    is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ or "NUITKA_ONEFILE_BINARY" in os.environ or hasattr(sys, "nuitka_version")
    calculated_root = None

    # 1. Nuitka Onefile 模式下，从 sys.argv[0] 获取真实物理 launcher 路径，排除解释器与临时目录
    if is_nuitka:
        if sys.argv and sys.argv[0]:
            argv0_abspath = os.path.abspath(sys.argv[0])
            if os.path.basename(argv0_abspath).lower() not in ('python.exe', 'pythonw.exe', 'python', 'pythonw'):
                if not _is_inside_temp_dir(argv0_abspath):
                    calculated_root = os.path.dirname(argv0_abspath)

    # 2. PyInstaller 或 Nuitka Standalone 模式，使用 sys.executable 的父目录，排除临时目录
    if not calculated_root:
        if getattr(sys, "frozen", False) or is_nuitka:
            exe_abspath = os.path.abspath(sys.executable)
            if not _is_inside_temp_dir(exe_abspath):
                calculated_root = os.path.dirname(exe_abspath)

    # 3. 源码开发环境 fallback
    if not calculated_root:
        try:
            path = os.path.dirname(os.path.abspath(__file__))
            if _is_inside_temp_dir(path):
                for sp in sys.path:
                    if sp and not _is_inside_temp_dir(sp):
                        calculated_root = os.path.abspath(sp)
                        break
                if not calculated_root:
                    calculated_root = os.getcwd()
            else:
                calculated_root = path
        except:
            calculated_root = os.getcwd()

    if calculated_root:
        calculated_root = os.path.abspath(calculated_root)
        _CACHED_APP_ROOT = calculated_root
        os.environ["INSTOCK_APP_ROOT"] = calculated_root
        return calculated_root

    fallback_root = os.path.abspath(os.getcwd())
    _CACHED_APP_ROOT = fallback_root
    os.environ["INSTOCK_APP_ROOT"] = fallback_root
    return fallback_root

def get_base_path() -> str:
    """与 get_app_root 统一对齐，获取应用权威根目录"""
    return get_app_root()

def get_conf_path(fname: str, base_dir: Optional[str] = None, is_user_save: bool = False) -> str:
    """
    获取并验证配置文件路径。
    核心逻辑：
      1. 物理磁盘（base_dir）已存在且有效 -> 直接返回该真实物理路径；
      2. 物理磁盘不存在，但处于打包环境（Nuitka Onefile/PyInstaller）且包内带有种子文件 -> 自动自愈释放一份至物理磁盘，并返回物理路径；
      3. 若为写入/持久化操作 -> 确保物理父目录存在，绝对返回物理磁盘路径！
    """
    if base_dir is None:
        base_dir = get_app_root()

    key = os.path.basename(fname)
    default_path = os.path.join(base_dir, fname)

    # 1. 物理文件已存在且非空，直接使用
    if os.path.exists(default_path) and os.path.getsize(default_path) > 0:
        return default_path

    # 2. 判定包内资源目录 (Nuitka Onefile 临时解压目录 或 PyInstaller _MEIPASS)
    bundle_dir = None
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        bundle_dir = os.environ["NUITKA_ONEFILE_DIRECTORY"]
    elif getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = sys._MEIPASS
    else:
        try:
            bundle_dir = os.path.dirname(os.path.abspath(__file__))
        except:
            pass

    # 3. 尝试从包内种子资源自愈释放到物理磁盘
    if bundle_dir and os.path.exists(bundle_dir):
        # 寻找包内候选文件
        src_candidates = [
            os.path.join(bundle_dir, fname),
            os.path.join(bundle_dir, key),
        ]
        if key in RESOURCE_MAP:
            src_candidates.insert(0, os.path.join(bundle_dir, RESOURCE_MAP[key]["src"]))

        for src in src_candidates:
            if os.path.exists(src) and os.path.getsize(src) > 0:
                try:
                    os.makedirs(os.path.dirname(default_path), exist_ok=True)
                    shutil.copy2(src, default_path)
                    return default_path
                except Exception:
                    # 无法写入物理磁盘（例如权限限制），只读降级返回包内路径
                    return src

    # 4. 确保物理目录存在，保证持久化保存不报错
    try:
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
    except:
        pass

    return default_path
