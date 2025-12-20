# -*- coding:utf-8 -*-
import os
import sys
import json
import configparser
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.Sys")

def get_base_path():
    """获取程序基准路径，支持脚本和打包模式 (Nuitka/PyInstaller)"""
    is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
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

def get_conf_path(fname, base_dir=None):
    """获取并验证配置文件路径，如果不存在则释放资源"""
    if base_dir is None:
        # 这是一个循环依赖问题，如果 sys_utils 需要 get_base_path
        # 我们可以在调用处传入 BASE_DIR
        return None
        
    default_path = os.path.join(base_dir, fname)

    if os.path.exists(default_path):
        if os.path.getsize(default_path) > 0:
            return default_path
        else:
            logger.warning(f"配置文件 {fname} 存在但为空，将尝试重新释放")

    cfg_file = cct.get_resource_file(
        rel_path=f"{fname}",
        out_name=fname,
        BASE_DIR=base_dir
    )

    if not cfg_file or not os.path.exists(cfg_file) or os.path.getsize(cfg_file) == 0:
        logger.error(f"获取 {fname} 失败")
        return None

    return cfg_file

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
