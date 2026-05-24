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

def get_base_path():
    """获取程序基准路径，支持脚本和打包模式 (Nuitka/PyInstaller)"""
    is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
    # 🚀 Nuitka 专属定制局部修复：如果是由 Nuitka 打包编译，强行将 is_interpreter 设为 False，避免误入脚本模式
    if "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        is_interpreter = False
    
    if is_interpreter and not getattr(sys, "frozen", False):
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except NameError:
            pass
            
    if sys.platform.startswith('win'):
        try:
            real_path = cct._get_win32_exe_path()
            if real_path != os.path.dirname(os.path.abspath(sys.executable)):
                 return real_path
            if not is_interpreter:
                 return real_path
        except:
            pass 

    if getattr(sys, "frozen", False) or not is_interpreter:
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(sys.argv[0]))
    # base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    # # 💥 [New] 优先检查 dist 目录作为数据根目录
    # dist_path = os.path.join(base_path, 'dist')
    # if os.path.exists(dist_path) and os.path.exists(os.path.join(dist_path, 'trading_signals.db')):
    #     return dist_path
    # return base_path
    
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
    "strategy_config.json": {
        "src": "strategy_config.json",
        "dst": "strategy_config.json"
    },
    "voice_alert_config.json": {
        "src": "voice_alert_config.json",
        "dst": "voice_alert_config.json"
    },
    "macro_trends.json": {
        "src": "macro_trends.json",
        "dst": "macro_trends.json"
    },
    "display_cols.json": {
        "src": "display_cols.json",
        "dst": "display_cols.json"
    },
    "intraday_pattern_config.json": {
        "src": "intraday_pattern_config.json",
        "dst": "intraday_pattern_config.json"
    },
    "search_history.json": {
        "src": "search_history.json",
        "dst": "datacsv/search_history.json"
    },
    "minute_kline_viewer_history.json": {
        "src": "minute_kline_viewer_history.json",
        "dst": "datacsv/minute_kline_viewer_history.json"
    },
    "stock_codes.conf": {
        "src": "JSONData/stock_codes.conf",
        "dst": "stock_codes.conf"
    },
    "count.ini": {
        "src": "JSONData/count.ini",
        "dst": "count.ini"
    },
    "global.ini": {
        "src": "JohnsonUtil/global.ini",
        "dst": "global.ini"
    },
    "同花顺板块行业.xlsx": {
        "src": "JohnsonUtil/wencai/同花顺板块行业.xlsx",
        "dst": "同花顺板块行业.xlsx"
    }
}

def get_conf_path(fname, base_dir=None):
    """获取并验证配置文件路径，如果物理磁盘不存在，自动创建层级目录并从内置资源包中智能解压自愈"""
    if base_dir is None:
        base_dir = get_base_path()
        
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
            
    # 2. 查找映射字典
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

    # 💥 彻底防范并消除 `datacsv/datacsv` 重复嵌套：
    # 如果 `dst_rel` 已经包含了 `datacsv/` 或者是 `wencai/` 或者是 `JSONData/`，
    # 而传入的 `base_dir` 刚好是其对应的子目录（例如 base_dir 结尾是 `datacsv` ），
    # 我们应该自动将 `base_dir` 提升回退回根目录 `BASE_DIR`
    for folder_name in ["datacsv", "wencai", "JSONData", "JohnsonUtil"]:
        if dst_rel.startswith(f"{folder_name}/") and base_dir.replace("\\", "/").rstrip("/").endswith(folder_name):
            # 将 base_dir 回退到它的父目录
            base_dir = os.path.dirname(os.path.abspath(base_dir))

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
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller 经典的临时解压根目录
        base = sys._MEIPASS
    elif "NUITKA_ONEFILE_DIRECTORY" in os.environ:
        # Nuitka Onefile 经典的临时解压根目录
        base = os.environ["NUITKA_ONEFILE_DIRECTORY"]
    else:
        # 源码开发环境下
        base = get_base_path()
        # 如果是 JohnsonUtil 子文件夹，往上退一级作为源码根
        if os.path.basename(base) == 'JohnsonUtil':
            base = os.path.dirname(base)

    # 🚀 Nuitka/PyInstaller 多进程包内自愈：如果在子进程下环境变量丢失，导致 base 指向了外部目录而不是临时解压目录
    # （检测外部 exe 目录下既没有 JohnsonUtil/global.ini 也没有 global.ini），则利用 __file__ 物理定位包内根目录
    if not os.path.exists(os.path.join(base, "JohnsonUtil", "global.ini")) and not os.path.exists(os.path.join(base, "global.ini")):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(this_dir) == "JohnsonUtil":
            pkg_base = os.path.dirname(this_dir)
        else:
            pkg_base = this_dir
        
        # 如果通过代码定位的根目录下确实有 global.ini 模板
        if os.path.exists(os.path.join(pkg_base, "JohnsonUtil", "global.ini")) or os.path.exists(os.path.join(pkg_base, "global.ini")):
            base = pkg_base
            os.environ["NUITKA_ONEFILE_DIRECTORY"] = pkg_base
            logger.info(f"[自愈] 子进程检测到环境变量丢失，已通过物理代码路径锁定临时资源根并还原环境变量: {base}")

    # 拼接包内的源文件绝对路径
    src = os.path.join(base, src_rel)

    # 如果源文件在上述 base 目录下不存在，进行常见包内路径多重自愈探测
    if not os.path.exists(src):
        nuitka_candidates = [
            os.path.join(base, "JohnsonUtil", src_rel),
            os.path.join(base, "JSONData", src_rel),
            os.path.join(base, "JohnsonUtil", "wencai", src_rel),
            os.path.join(base, "datacsv", src_rel),
            os.path.join(base, os.path.basename(src_rel)),
            os.path.join(base, "JohnsonUtil", os.path.basename(src_rel)),
            os.path.join(base, "JSONData", os.path.basename(src_rel))
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
            logger.info(f"成功自愈释放配置文件并归位: {default_path}")
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
    logger.info("📡 正在启动核心配置文件抢占式预加载自愈释放...")
    for fname in RESOURCE_MAP:
        try:
            get_conf_path(fname)
        except Exception as e:
            logger.error(f"预加载释放 {fname} 异常: {e}")
    logger.info("✅ 抢占式预加载自愈释放完成，全物理安全屏障已建立。")
