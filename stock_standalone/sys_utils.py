# -*- coding:utf-8 -*-
import os
import sys
import json
import configparser
import threading
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.Sys")

def assert_main_thread(tag=""):
    """
    检查当前是否在主线程执行。如果不在，抛出 RuntimeError。
    用于定位可能导致 GUI 崩溃的后台线程 UI 操作。
    """
    if threading.current_thread() is not threading.main_thread():
        msg = f"[FATAL] {tag} called outside main thread: {threading.current_thread().name}"
        logger.error(msg)
        # 在开发模式下建议抛出异常以立即定位问题
        # 如果是生产环境，可以只打日志不抛异常
        raise RuntimeError(msg)

def is_packaged_env() -> bool:
    """判断当前运行环境是否为打包后的可执行程序 (PyInstaller / Nuitka)"""
    return getattr(sys, "frozen", False) or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version")

def get_app_root() -> str:
    """Nuitka / PyInstaller / dev 统一兼容的物理可执行程序所在绝对根目录 (直接返回 str 格式)"""
    # 优先从环境变量获取，确保子进程完美继承父进程定位的物理路径
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        return env_root

    import sys
    
    def _is_inside_temp_dir(path: str) -> bool:
        if not path:
            return False
        # 统一规范化为小写和标准斜杠
        path_norm = os.path.normpath(os.path.normcase(os.path.abspath(path)))
        
        # 1. 检查环境变量指向的所有可能临时目录，包含 realpath 解析以应对 C: 与 G: (RAMDISK) 映射
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
                    
        # 2. 物理规则模糊判定 (instock_Nuitka, onefile_, _meipass, \temp\)
        for pattern in ("instock_nuitka", "onefile_", "_meipass", "\\temp\\", "/temp/"):
            if pattern in path_norm:
                return True
                
        return False

    is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ
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
            if os.path.basename(path) == 'JohnsonUtil':
                path = os.path.dirname(path)
            # 如果 fallback 获取的 __file__ 路径依然被判定为临时目录，则绝不能采用它，改用 os.getcwd() 或 sys.path
            if _is_inside_temp_dir(path):
                # 尝试寻找非 temp_dir 的 sys.path 路径
                for sp in sys.path:
                    if sp and not _is_inside_temp_dir(sp):
                        calculated_root = os.path.abspath(sp)
                        break
                if not calculated_root:
                    calculated_root = os.getcwd()
            else:
                calculated_root = path
        except Exception:
            calculated_root = os.getcwd()

    # 物理锁定并写入环境变量，保障多进程完美一致
    os.environ["INSTOCK_APP_ROOT"] = calculated_root
    logger.warning(f"sys.executable={sys.executable}")
    logger.warning(f"sys.argv[0]={sys.argv[0] if sys.argv else None}")
    logger.warning(f"cwd={os.getcwd()}")
    logger.warning(f"get_app_root={calculated_root}")
    logger.warning(f"get_base_path={get_base_path()}")
    return calculated_root

def get_app_root_two() -> str:
    """返回 EXE 或脚本所在目录（不依赖 CWD）"""
    return get_app_root()

def get_base_path() -> str:
    """获取包内静态只读资源解压目录 (PACKAGE_DIR)，用于读取内置资源。
    In Onefile mode, it is the Nuitka/PyInstaller temp directory; in source/dev mode, it fallback to the app root directory.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        val = os.environ["NUITKA_ONEFILE_DIRECTORY"]
        app_root = get_app_root()
        if os.path.normpath(os.path.abspath(val)).lower() != os.path.normpath(os.path.abspath(app_root)).lower():
            return val
        
    # 🚀 Nuitka 子进程自愈：如果 Nuitka 编译下环境变量丢失，通过物理模块 __file__ 路径直接锁定解压临时根目录
    is_nuitka = "__compiled__" in globals() or hasattr(sys, "nuitka_version")
    if is_nuitka:
        try:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            # 如果 sys_utils.py 存放在子目录里（通常在根目录，但以防万一）
            if os.path.basename(this_dir) in ("JohnsonUtil", "JSONData"):
                this_dir = os.path.dirname(this_dir)
            app_root = get_app_root()
            if os.path.normpath(os.path.abspath(this_dir)).lower() != os.path.normpath(os.path.abspath(app_root)).lower():
                # 还原环境变量，保障后续或其它子进程获取一致
                os.environ["NUITKA_ONEFILE_DIRECTORY"] = this_dir
                logger.debug(f"[get_base_path] Nuitka子进程通过 __file__ 自愈还原临时释放目录: {this_dir}")
                return this_dir
        except Exception as e:
            logger.error(f"[get_base_path] Nuitka子进程通过 __file__ 还原路径失败: {e}")

    return get_app_root()

# "window_layout_config.json": {
#     "src": "webTools/window_manager/window_layout_config.json",
#     "dst": "window_layout_config.json"
# },
    
RESOURCE_MAP = {
    "MonitorTK.ico": {
        "src": "MonitorTK.ico",
        "dst": "MonitorTK.ico"
    },

    "window_config.json": {
        "src": "window_config.json",
        "dst": "window_config.json"
    },
    "scale2_window_config.json": {
        "src": "scale2_window_config.json",
        "dst": "scale2_window_config.json"
    },
    "monitor_category_list.json": {
        "src": "monitor_category_list.json",
        "dst": "monitor_category_list.json"
    },
    "visualizer_layout.json": {
        "src": "visualizer_layout.json",
        "dst": "visualizer_layout.json"
    },
    "global.ini": {
        "src": "JohnsonUtil/global.ini",
        "dst": "global.ini"
    },
    "stock_codes.conf": {
        "src": "JSONData/stock_codes.conf",
        "dst": "stock_codes.conf"
    },
    "voice_alert_config.json": {
        "src": "voice_alert_config.json",
        "dst": "voice_alert_config.json"
    },
    "macro_trends.json": {
        "src": "macro_trends.json",
        "dst": "macro_trends.json"
    },
    "intraday_pattern_config.json": {
        "src": "intraday_pattern_config.json",
        "dst": "intraday_pattern_config.json"
    },
    "strategy_config.json": {
        "src": "strategy_config.json",
        "dst": "strategy_config.json"
    },
    "display_cols.json": {
        "src": "display_cols.json",
        "dst": "display_cols.json"
    },
    "search_history.json": {
        "src": "search_history.json",
        "dst": "datacsv/search_history.json"
    },
    "minute_kline_viewer_history.json": {
        "src": "minute_kline_viewer_history.json",
        "dst": "datacsv/minute_kline_viewer_history.json"
    },
    "count.ini": {
        "src": "JSONData/count.ini",
        "dst": "count.ini"
    },
    "同花顺板块行业.xlsx": {
        "src": "JohnsonUtil/wencai/同花顺板块行业.xlsx",
        "dst": "同花顺板块行业.xlsx"
    }
}

def get_conf_path(fname, base_dir=None):
    """获取并验证配置文件路径，如果物理磁盘不存在，自动创建层级目录并从内置资源包中智能解压自愈"""
    get_base_path() # 提前触发自愈以防 is_onefile 判定被绕过
    if base_dir is None:
        base_dir = get_app_root()
        
    key = os.path.basename(fname)
    
    # 1. 判定是否为 Onefile 物理独立打包模式
    is_onefile = False
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        # Nuitka Onefile 打包模式
        is_onefile = (os.environ["NUITKA_ONEFILE_DIRECTORY"] != base_dir)
    elif getattr(sys, "frozen", False):
        # PyInstaller Onefile 打包模式
        if hasattr(sys, "_MEIPASS"):
            is_onefile = (sys._MEIPASS != base_dir)
            
    # 2. 查找映射字典与路径防嵌套预处理
    mapping = RESOURCE_MAP.get(key)
    if mapping:
        src_rel = mapping["src"]
        # Onefile 模式下平铺在根目录（dst）；Onedir 或开发环境下维持在默认子目录（src）
        if is_onefile:
            dst_rel = mapping["dst"]
        else:
            dst_rel = mapping["src"]
    else:
        src_rel = fname
        dst_rel = fname

    # 💥 彻底防范并消除 `datacsv/datacsv` 等重复嵌套：
    # 如果传入的 `base_dir` 刚好是其对应的子目录（例如 base_dir 结尾是 `datacsv` ），
    # 且映射 dst 路径也以该子目录开头，说明发生了重复嵌套。
    # 我们应该自动将 `base_dir` 提升回退回根目录 `BASE_DIR`，并强制将 `dst_rel` 设为 `mapping["dst"]` 以保证能够正确拼出完整路径
    if mapping:
        for folder_name in ["datacsv", "wencai", "JSONData", "JohnsonUtil"]:
            dst_path_norm = mapping["dst"].replace("\\", "/")
            if dst_path_norm.startswith(f"{folder_name}/") and base_dir.replace("\\", "/").rstrip("/").endswith(folder_name):
                # 将 base_dir 回退到它的父目录
                base_dir = os.path.dirname(os.path.abspath(base_dir))
                # 既然 base_dir 已经提升，dst_rel 必须包含完整的相对路径以保证能够定位到子目录中
                dst_rel = mapping["dst"]
                break

    # 3. 🛡️ 优先探测物理根目录（dst）下的现有配置文件，避免在已有用户配置时通过备份文件（src）进行不必要的自愈/恢复或路径分流
    # 💥 这里必须使用已经经过防嵌套安全纠正后的 base_dir 重新计算 root_path，从源头上根除 Double Nesting
    if mapping:
        root_path = os.path.join(base_dir, mapping["dst"])
        if os.path.exists(root_path) and os.path.getsize(root_path) > 0:
            return root_path

    # 我们最终期待的物理磁盘目标路径
    default_path = os.path.join(base_dir, dst_rel)

    # 识别用户动态存盘文件
    user_data_keywords = ["window_config", "ui_state", "history", "monitor_category_list", "display_cols", "layout", "voice_alert", "macro_trends", "strategy"]
    is_user_save = any(k in fname.lower() for k in user_data_keywords)

    # --- 1. 直接存在且有效 -> 直接返回 ---
    if os.path.exists(default_path):
        if os.path.getsize(default_path) > 0:
            return default_path
        elif is_user_save:
            return default_path
        else:
            logger.warning(f"配置文件 {default_path} 存在但为空，尝试从资源包恢复...")

    # --- 2. 物理不存在，执行自愈释放 ---
    # 先确定内置解包临时根目录 (base)
    is_packaged = is_packaged_env()
    if is_packaged:
        # 打包模式下，由 get_base_path() 统一提供并负责环境变量丢失的逆向自愈
        base = get_base_path()
    else:
        # 源码开发环境下
        base = get_base_path()
        # 如果是 JohnsonUtil 子文件夹，往上退一级作为源码根
        if os.path.basename(base) == 'JohnsonUtil':
            base = os.path.dirname(base)

    # 拼接包内的源文件绝对路径
    src = os.path.join(base, src_rel)

    # 如果源文件在上述 base 目录下不存在，进行常见包内路径多重自愈探测
    if not os.path.exists(src):
        # 💥 多维自愈探测候选：兼容 Nuitka 在不同环境下可能发生平铺释放或路径斜杠错位的极端情况
        nuitka_candidates = [
            os.path.join(base, "JohnsonUtil", src_rel),
            os.path.join(base, "JSONData", src_rel),
            os.path.join(base, "JohnsonUtil", "wencai", src_rel),
            os.path.join(base, "datacsv", src_rel),
            os.path.join(base, os.path.basename(src_rel)),
            os.path.join(base, "JohnsonUtil", os.path.basename(src_rel)),
            os.path.join(base, "JSONData", os.path.basename(src_rel)),
            # 兼容 Windows/Unix 斜杠/反斜杠互换及平铺路径 (如 base\"JSONData\stock_codes.conf")
            os.path.join(base, src_rel.replace('/', '\\')),
            os.path.join(base, src_rel.replace('\\', '/')),
            os.path.join(base, os.path.dirname(src_rel).replace('/', '\\'), os.path.basename(src_rel)),
            os.path.join(base, os.path.dirname(src_rel).replace('\\', '/'), os.path.basename(src_rel))
        ]
        for cand in nuitka_candidates:
            if os.path.exists(cand) and os.path.getsize(cand) > 0:
                src = cand
                break

    # 如果包内确实有这个资源，执行流式复制与物理自愈释放！
    if os.path.exists(src) and os.path.getsize(src) > 0:
        try:
            # 💥 核心自愈：自动创建物理释放路径的父文件夹
            target_dir = os.path.dirname(default_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                
            # 执行物理复制
            import shutil
            shutil.copy(src, default_path)
            logger.warning(f"成功自愈释放配置文件并归位: {default_path}")
            return default_path
        except Exception as e:
            logger.exception(f"自愈释放配置文件失败: {e}")

    # 如果是非核心的、用户存盘类的 .json 且包内确实没有内置模板，直接返回 default_path 由应用自发保存
    if is_user_save or fname.lower().endswith(".json"):
        try:
            target_dir = os.path.dirname(default_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
        except:
            pass
        return default_path

    # 核心资源彻底丢失且无法解压，打印致命日志
    if "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version"):
        try:
            onefile_dir = os.environ.get("NUITKA_ONEFILE_DIRECTORY", "N/A")
            exists_base = os.path.exists(base)
            files_in_base = []
            if exists_base:
                files_in_base = os.listdir(base)[:30]
            logger.error(f"[Nuitka-Diag] base_dir={base} (exists={exists_base}), NUITKA_ONEFILE_DIRECTORY={onefile_dir}")
            logger.error(f"[Nuitka-Diag] Files in base: {files_in_base}")
            logger.error(f"[Nuitka-Diag] Expected src={src}, default_path={default_path}")
        except Exception as ex:
            logger.error(f"[Nuitka-Diag] 诊断信息收集失败: {ex}")

    logger.error(f"⚠️ [Config] 核心资源 {fname} 丢失且无法从包内释放")
    return default_path

def load_display_config_ini(config_file, stock_data, code, name, close, boll, signal_icon, breakthrough, strength):
    """根据自定义 ini 文件生成显示行和颜色"""
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    lines = []
    colors = []

    placeholders = {
        'code': code,
        'name': name,
        'close': close,
        'ratio': stock_data.get('ratio', 'N/A'),
        'volume': stock_data.get('volume', 'N/A'),
        'red': stock_data.get('red', 'N/A'),
        'boll': boll,
        'signal_icon': signal_icon,
        'upper': stock_data.get('upper', 'N/A'),
        'lower': stock_data.get('lower', 'N/A'),
        'breakthrough': breakthrough,
        'strength': strength
    }

    if 'lines' in config:
        for key in sorted(config['lines'], key=lambda x: int(x.replace('line','')) if x.replace('line','').isdigit() else 0):
            line_template = config['lines'][key]
            try:
                line_text = line_template.format(**placeholders)
            except KeyError as e:
                line_text = line_template # 容错
                logger.warning(f"Format key missing: {e}")
            
            color_value = config['colors'].get(key, 'black') if 'colors' in config else 'black'
            lines.append(line_text)
            colors.append(color_value)

    return lines, colors

def load_display_config(config_file, default_cols):
    """加载显示列配置 JSON"""
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"current": default_cols, "sets": []}

def save_display_config(config_file, config):
    """保存显示列配置 JSON"""
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

def ensure_all_configs_released():
    """在主程序最早期抢占式预加载并释放所有注册的核心配置文件，建立全物理自愈安全屏障"""
    # 💥 彻底根治并自动清理历史遗留的 `datacsv/datacsv` 重复嵌套目录，迁移旧数据
    try:
        app_root = get_app_root()
        nested_dir = os.path.join(app_root, "datacsv", "datacsv")
        correct_dir = os.path.join(app_root, "datacsv")
        if os.path.exists(nested_dir) and os.path.isdir(nested_dir):
            logger.warning(f"发现历史遗留双层嵌套目录: {nested_dir}，正在启动自动数据合并与物理自愈...")
            for item in os.listdir(nested_dir):
                src_file = os.path.join(nested_dir, item)
                dst_file = os.path.join(correct_dir, item)
                if os.path.isfile(src_file):
                    # 如果目标文件不存在，或者源文件更大/更新，执行覆盖式物理迁移
                    should_move = True
                    if os.path.exists(dst_file):
                        if os.path.getsize(dst_file) >= os.path.getsize(src_file):
                            should_move = False
                    
                    if should_move:
                        import shutil
                        shutil.copy2(src_file, dst_file)
                        logger.info(f"[自愈迁移] 成功将数据由 {src_file} 迁移至 {dst_file}")
                    
                    try:
                        os.remove(src_file)
                    except Exception as ex:
                        logger.error(f"删除冗余源文件 {src_file} 失败: {ex}")
            
            try:
                os.rmdir(nested_dir)
                logger.info(f"✅ 成功物理清除冗余的双层嵌套目录: {nested_dir}")
            except Exception as ex:
                logger.error(f"清理双层嵌套目录 {nested_dir} 失败: {ex}")
    except Exception as e:
        logger.error(f"自愈合并双层嵌套目录异常: {e}")

    logger.info("📡 正在启动核心配置文件抢占式预加载自愈释放...")
    for fname in RESOURCE_MAP:
        try:
            get_conf_path(fname)
        except Exception as e:
            logger.error(f"预加载释放 {fname} 异常: {e}")
    logger.info("✅ 抢占式预加载自愈释放完成，全物理安全屏障已建立。")

_resolved_name_cache = {}
_name_cache_lock = threading.Lock()
_SINA_ENGINE = None

def _load_name_cache():
    global _resolved_name_cache
    try:
        path = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        v_str = str(v).strip()
                        k_str = str(k).strip().zfill(6)
                        if v_str and not v_str.startswith("个股_") and not v_str.isdigit() and v_str != k_str:
                            _resolved_name_cache[k_str] = v_str
    except Exception as e:
        logger.error(f"Failed to load stock name cache: {e}")

    # 2. 如果发现缓存量过小（比如小于 4500 只，通常 A 股有 5000+），说明需要一次性灌入补齐，实现“一次干活终身受益”
    if len(_resolved_name_cache) < 4500:
        logger.info(f"⚡ [NameCache Bootstrap] Current cache size ({len(_resolved_name_cache)}) is small. Initiating full stock name bootstrap...")
        boostrap_success = False
        
        # 尝试通过 Sina Engine 一次性读取并提取全量代码名字
        try:
            from JSONData import sina_data
            engine = sina_data.Sina(readonly=True)
            df = engine.all
            if df is not None and not df.empty and 'name' in df.columns:
                name_map = df['name'].to_dict()
                added_count = 0
                for k, v in name_map.items():
                    k_clean = str(k).strip().zfill(6)
                    v_clean = str(v).strip()
                    if v_clean and not v_clean.startswith("个股_") and not v_clean.isdigit() and v_clean != k_clean:
                        if k_clean not in _resolved_name_cache:
                            _resolved_name_cache[k_clean] = v_clean
                            added_count += 1
                logger.info(f"✅ [NameCache Bootstrap] Successfully bootstrapped {added_count} names from Sina Engine (all). Total cached: {len(_resolved_name_cache)}")
                boostrap_success = True
        except Exception as e:
            logger.warning(f"⚠ [NameCache Bootstrap] Sina Engine bootstrap failed: {e}")
            
        # 如果 Sina Engine 失败了，尝试通过 top_all.h5 数据库一次性提取
        if not boostrap_success:
            try:
                base_dir = get_app_root()
                import pandas as pd
                for path in [r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(os.getcwd(), 'top_all.h5')]:
                    if os.path.exists(path):
                        df_top = pd.read_hdf(path, 'top_all')
                        if not df_top.empty and 'name' in df_top.columns:
                            name_map = {}
                            if df_top.index.name == 'code':
                                name_map = df_top['name'].to_dict()
                            elif 'code' in df_top.columns:
                                name_map = dict(zip(df_top['code'].astype(str).str.zfill(6), df_top['name']))
                            else:
                                name_map = dict(zip(df_top.index.astype(str).str.zfill(6), df_top['name']))
                            
                            added_count = 0
                            for k, v in name_map.items():
                                k_clean = str(k).strip().zfill(6)
                                v_clean = str(v).strip()
                                if v_clean and not v_clean.startswith("个股_") and not v_clean.isdigit() and v_clean != k_clean:
                                    if k_clean not in _resolved_name_cache:
                                        _resolved_name_cache[k_clean] = v_clean
                                        added_count += 1
                            logger.info(f"✅ [NameCache Bootstrap] Successfully bootstrapped {added_count} names from top_all.h5 ({path}). Total cached: {len(_resolved_name_cache)}")
                            boostrap_success = True
                            break
            except Exception as e:
                logger.warning(f"⚠ [NameCache Bootstrap] top_all.h5 bootstrap failed: {e}")
                
        # 3. 如果成功灌入了新名字，一次性把全部名字持久化写入 stock_name_cache.json
        if boostrap_success:
            try:
                path = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(_resolved_name_cache, f, ensure_ascii=False, indent=2)
                logger.info(f"💾 [NameCache Bootstrap] Saved complete stock name database ({len(_resolved_name_cache)} entries) to {path}")
            except Exception as e:
                logger.error(f"Failed to save bootstrapped cache: {e}")

def _save_to_name_cache(code: str, name: str):
    global _resolved_name_cache
    # 提取纯 6 位数字代码以保证缓存 key 的规范性
    import re
    code_clean = str(code).strip()
    code_match = re.search(r'(\d{6})', code_clean)
    if code_match:
        code_clean = code_match.group(1)
    else:
        code_clean = code_clean.zfill(6)
        
    name_clean = str(name).strip()
    if not name_clean or name_clean.startswith("个股_") or name_clean.isdigit() or name_clean == code_clean:
        return
    
    with _name_cache_lock:
        if _resolved_name_cache.get(code_clean) == name_clean:
            return
        _resolved_name_cache[code_clean] = name_clean
        try:
            path = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            disk_data = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        disk_data = json.load(f)
                except:
                    pass
            disk_data[code_clean] = name_clean
            with open(path, "w", encoding="utf-8") as f:
                json.dump(disk_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stock name cache: {e}")

# 执行初始化加载
_load_name_cache()

def resolve_stock_name(code_clean: str) -> str:
    """
    高精度、多通道、带内存与磁盘高速持久化缓存的个股名字解析器。
    专门根治“个股_XXXXXX”或代码数字做名字等 placeholder 占位符问题。
    首次解析成功后写入磁盘，绝对防止二次重复解析和多余的网络 API 请求。
    """
    original_input = str(code_clean).strip()
    code_clean = original_input
    # 剥离表情
    for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠', '👑']:
        code_clean = code_clean.replace(icon, '').strip()

    # 💥 关键修复：从输入中通过正则表达式提取 6 位纯数字股票代码，彻底治愈“个股_XXXXXX”等占位符
    import re
    code_match = re.search(r'(\d{6})', code_clean)
    if code_match:
        code_clean = code_match.group(1)
    else:
        # 如果确实不包含 6 位数字，说明可能是单纯的中文字符串名字，直接返回
        if code_clean and not code_clean.startswith("个股_") and not code_clean.isdigit():
            logger.debug(f"[resolve_stock_name] Input {original_input!r} has no 6-digit code. Returning as is: {code_clean!r}")
            return code_clean
        code_clean = code_clean.zfill(6)

    # 0. 内存/磁盘高速缓存首位拦截，极速 O(1) 返回，避免无谓 of I/O 和网络请求
    global _resolved_name_cache
    if code_clean in _resolved_name_cache:
        cached_name = _resolved_name_cache[code_clean]
        if cached_name and not cached_name.startswith("个股_") and not cached_name.isdigit() and cached_name != code_clean:
            return cached_name

    logger.info(f"[resolve_stock_name] Start multi-channel resolution for code: {code_clean} (original: {original_input!r})")

    # 0.5 优先使用本地内置 of sina_data 行情引擎极速解析
    try:
        global _SINA_ENGINE
        if _SINA_ENGINE is None:
            from JSONData import sina_data
            _SINA_ENGINE = sina_data.Sina(readonly=True)
        local_name = _SINA_ENGINE.get_code_cname(code_clean)
        if local_name and not local_name.startswith("个股_") and not local_name.isdigit() and local_name != code_clean:
            logger.info(f"[resolve_stock_name] Channel 0.5 (Sina Engine) resolved {code_clean} -> {local_name}")
            _save_to_name_cache(code_clean, local_name)
            return local_name
    except Exception as e:
        logger.warning(f"[resolve_stock_name] Sina local engine failed: {e}", exc_info=True)

    # 1. 优先从 top_all.h5 里面解析
    base_dir = get_app_root()
    import pandas as pd
    for path in [r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(os.getcwd(), 'top_all.h5')]:
        if os.path.exists(path):
            try:
                df_top = pd.read_hdf(path, 'top_all')
                if not df_top.empty:
                    if 'name' in df_top.columns:
                        if df_top.index.name == 'code':
                            name_map = df_top['name'].to_dict()
                        elif 'code' in df_top.columns:
                            name_map = dict(zip(df_top['code'].astype(str).str.zfill(6), df_top['name']))
                        else:
                            name_map = dict(zip(df_top.index.astype(str).str.zfill(6), df_top['name']))
                        name = name_map.get(code_clean)
                        if name and not str(name).startswith("个股_") and not str(name).isdigit() and name != code_clean:
                            res_name = str(name).strip()
                            logger.info(f"[resolve_stock_name] Channel 1 (top_all.h5) resolved {code_clean} -> {res_name}")
                            _save_to_name_cache(code_clean, res_name)
                            return res_name
            except Exception as e:
                logger.warning(f"[resolve_stock_name] top_all.h5 reading failed ({path}): {e}", exc_info=True)

    # 2. 其次从最新的竞价赛马快照中提取
    try:
        snapshots_dir = os.path.join(base_dir, "snapshots")
        if os.path.exists(snapshots_dir):
            files = [f for f in os.listdir(snapshots_dir) if f.startswith("racing_") and f.endswith(".json")]
            if files:
                files.sort(reverse=True)
                for file in files[:3]:
                    filepath = os.path.join(snapshots_dir, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            snap_data = json.load(f)
                            rows = []
                            if isinstance(snap_data, list):
                                rows = snap_data
                            elif isinstance(snap_data, dict):
                                for key in ["current_df", "data", "records"]:
                                    if key in snap_data and isinstance(snap_data[key], list):
                                        rows = snap_data[key]
                                        break
                            for r in rows:
                                if isinstance(r, dict):
                                    c = str(r.get("code") or "").strip().zfill(6)
                                    n = str(r.get("name") or "").strip()
                                    if c == code_clean and n and not n.startswith("个股_") and not n.isdigit() and n != code_clean:
                                        logger.info(f"[resolve_stock_name] Channel 2 (racing snapshot) resolved {code_clean} -> {n}")
                                        _save_to_name_cache(code_clean, n)
                                        return n
                    except Exception as e:
                        logger.warning(f"[resolve_stock_name] racing json failed ({file}): {e}", exc_info=True)
    except Exception as e:
        logger.warning(f"[resolve_stock_name] snapshots check failed: {e}", exc_info=True)

    # 3. 再其次从 logs/premarket_diagnose.json 中的历史记录中查找
    diagnose_file = os.path.join(base_dir, "logs", "premarket_diagnose.json")
    if os.path.exists(diagnose_file):
        try:
            with open(diagnose_file, "r", encoding="utf-8") as f:
                old_diagnoses = json.load(f)
                if isinstance(old_diagnoses, list):
                    for item in old_diagnoses:
                        h_code = item.get("code")
                        h_name = item.get("name")
                        if h_code and h_name:
                            h_code_clean = str(h_code).strip().zfill(6)
                            h_name_clean = str(h_name).strip()
                            for icon in ['🔴', '🟢', '📊', '⚠️', '🚀', '🟡', '🛡', '🛡️', '🚨', '⚠', '👑']:
                                h_name_clean = h_name_clean.replace(icon, '').strip()
                            if h_name_clean.startswith("回测_"):
                                h_name_clean = h_name_clean[3:].strip()
                            if h_code_clean == code_clean and h_name_clean and not h_name_clean.startswith("个股_") and not h_name_clean.isdigit():
                                logger.info(f"[resolve_stock_name] Channel 3 (premarket_diagnose.json) resolved {code_clean} -> {h_name_clean}")
                                _save_to_name_cache(code_clean, h_name_clean)
                                return h_name_clean
        except Exception as e:
            logger.warning(f"[resolve_stock_name] premarket_diagnose failed: {e}", exc_info=True)

    # 4. 终极网络兜底：通过新浪 API 联网拉取 (仅限 6 位纯数字代码)
    if code_clean.isdigit() and len(code_clean) == 6:
        import urllib.request
        import re
        # 格式化 code 加上 sh/sz/bj 前缀
        prefix = "sh" if code_clean.startswith("6") else ("bj" if code_clean.startswith(("8", "4", "9")) else "sz")
        url = f"http://hq.sinajs.cn/list={prefix}{code_clean}"
        try:
            req = urllib.request.Request(
                url, 
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36',
                    'Referer': 'http://finance.sina.com.cn'
                }
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                html = response.read().decode('gbk', errors='ignore')
                # 格式：var hq_str_sh600000="浦发银行,..."
                match = re.search(r'="([^,"]+)', html)
                if match:
                    name = match.group(1).strip()
                    if name and not name.startswith("个股_") and not name.isdigit():
                        logger.warning(f"🌐 [NETWORK-RESOLVE] Successfully fetched stock name for {code_clean} from Sina API: {name}")
                        _save_to_name_cache(code_clean, name)
                        return name
        except Exception as e:
            logger.error(f"[resolve_stock_name] Failed to fetch name from Sina for {code_clean}: {e}")

    logger.warning(f"[resolve_stock_name] All channels failed to resolve name for {code_clean}. Fallback to placeholder.")
    return f"个股_{code_clean}"


def is_active_trading_hours(bypass: bool = False) -> bool:
    """
    统一的交易时间判定接口。
    判定当前是否在标准的 A 股连续竞价交易活跃时段（上午 09:30-11:30，下午 13:00-15:00）。
    
    参数:
        bypass: 若为 True，则直接豁免校验，返回 True。
        
    说明:
        如果检测到是自动化测试环境（如 pytest 或命令行参数含有 test），会自动豁免并返回 True。
    """
    if bypass:
        return True
        
    import sys
    is_test = 'pytest' in sys.modules or any('test' in arg.lower() for arg in sys.argv)
    if is_test:
        return True
        
    try:
        from JohnsonUtil import commonTips as cct
        is_trade_day = cct.get_trade_date_status()
        now_time = cct.get_now_time_int()
        return is_trade_day and ((930 <= now_time <= 1130) or (1300 <= now_time <= 1500))
    except Exception as e:
        logger.error(f"[sys_utils] Error checking trading hours: {e}")
        return True


def ensure_backend_tk_running():
    """
    检查主 Tk 后台数据推送进程是否已在运行。
    若未运行，则在后台以静默（隐藏窗口）方式拉起它。
    """
    import os
    import sys
    import subprocess
    
    # 1. 尝试使用 Windows 全局互斥量 (Mutex) 检测主 Tk 是否已经运行
    is_running = False
    if sys.platform == 'win32':
        try:
            import win32event
            import win32api
            import winerror
            # 尝试打开现有的 Mutex
            handle = win32event.OpenMutex(win32event.MUTEX_ALL_ACCESS, False, "Global\\StockMonitorAppMutex")
            if handle:
                win32api.CloseHandle(handle)
                is_running = True
                logger.info("[ATS] Detected existing instock_MonitorTK via Windows Mutex.")
        except Exception:
            pass
            
    # 2. Fallback: 使用 psutil 检测进程
    if not is_running:
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmd = proc.info.get('cmdline') or []
                    cmd_str = " ".join(cmd).lower()
                    if 'instock_monitortk' in cmd_str:
                        is_running = True
                        logger.info("[ATS] Detected existing instock_MonitorTK via psutil process scanning.")
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception:
            # 如果没有 psutil，使用 tasklist 保底
            if sys.platform == 'win32':
                try:
                    out = subprocess.check_output('tasklist /FI "IMAGENAME eq instock_MonitorTK.exe"', shell=True)
                    if b'instock_MonitorTK.exe' in out:
                        is_running = True
                        logger.info("[ATS] Detected existing instock_MonitorTK.exe via tasklist.")
                except Exception:
                    pass

    # 3. 如果未运行，后台静默拉起
    if not is_running:
        app_root = get_app_root()
        
        if is_packaged_env():
            # 打包态下，寻找同目录的 instock_MonitorTK.exe
            exe_dir = os.path.dirname(sys.executable)
            backend_exe = os.path.join(exe_dir, "instock_MonitorTK.exe")
            if not os.path.exists(backend_exe):
                backend_exe = os.path.join(app_root, "instock_MonitorTK.exe")
                
            if os.path.exists(backend_exe):
                cmd = [backend_exe, "-background"]
                logger.info(f"[ATS] Spawning packaged backend: {cmd}")
            else:
                logger.warning("[ATS] Warning: instock_MonitorTK.exe not found in release directory.")
                return
        else:
            # 开发态下，使用当前 Python 解释器运行 instock_MonitorTK.py
            backend_py = os.path.join(app_root, "instock_MonitorTK.py")
            python_exe = sys.executable
            if python_exe.endswith("python.exe"):
                pyw = python_exe.replace("python.exe", "pythonw.exe")
                if os.path.exists(pyw):
                    python_exe = pyw
            cmd = [python_exe, backend_py, "-background"]
            logger.info(f"[ATS] Spawning dev backend: {cmd}")

        try:
            # 在 Windows 下隐藏子进程的命令行控制台窗口
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW
                
            # 后台非阻塞式拉起
            subprocess.Popen(
                cmd,
                cwd=app_root,
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            logger.info("[ATS] Background backend started successfully.")
        except Exception as e:
            logger.error(f"[ATS] Failed to auto-start backend: {e}")


# ----------------------------------------------------
# 本地微型 HTTP 服务，专门为油猴油猴网页联动脚本提供股票名字和代码映射
# ----------------------------------------------------
_link_callback = None

def register_link_callback(callback):
    global _link_callback
    _link_callback = callback

_stock_names_cache_data = None
_stock_names_cache_mtime = 0

def get_cached_stock_names():
    global _stock_names_cache_data, _stock_names_cache_mtime
    import os
    path = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
    try:
        if not os.path.exists(path):
            return b"{}"
        mtime = os.path.getmtime(path)
        if _stock_names_cache_data is not None and mtime == _stock_names_cache_mtime:
            return _stock_names_cache_data
        
        # 缓存失效或首次加载：执行文件读取
        with open(path, 'rb') as f:
            data = f.read()
        _stock_names_cache_data = data
        _stock_names_cache_mtime = mtime
        return data
    except Exception:
        return b"{}"

_server_started = False
_server_lock = threading.Lock()

def start_stock_name_server():
    global _server_started
    with _server_lock:
        if _server_started:
            return
        _server_started = True

    from http.server import BaseHTTPRequestHandler, HTTPServer
    import json
    import os
    
    class StockNameHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/stock_names':
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type')
                self.end_headers()
                self.wfile.write(get_cached_stock_names())
            elif self.path.startswith('/link'):
                from urllib.parse import urlparse, parse_qs
                query = urlparse(self.path).query
                params = parse_qs(query)
                code_list = params.get('code')
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type')
                self.end_headers()
                
                if code_list and len(code_list[0]) == 6:
                    code = code_list[0]
                    global _link_callback
                    if _link_callback is not None:
                        try:
                            _link_callback(code)
                            self.wfile.write(b'{"status": "ok", "message": "linked"}')
                        except Exception as e:
                            self.wfile.write(f'{{"status": "error", "message": "{str(e)}"}}'.encode('utf-8'))
                    else:
                        self.wfile.write(b'{"status": "error", "message": "no callback registered"}')
                else:
                    self.wfile.write(b'{"status": "error", "message": "invalid code"}')
            else:
                self.send_error(404)
                
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type')
            self.end_headers()
                
        def log_message(self, format, *args):
            pass

    def run_server():
        try:
            server = HTTPServer(('127.0.0.1', 26672), StockNameHandler)
            try:
                server.socket.set_inheritable(False)
            except Exception:
                pass
            server.serve_forever()
        except Exception:
            pass
            
    import threading
    t = threading.Thread(target=run_server, daemon=True, name="StockNameHTTP")
    t.start()





