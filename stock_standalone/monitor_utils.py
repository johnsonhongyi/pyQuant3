# -*- coding:utf-8 -*-
import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

# Note: These should ideally be imported or passed in. 
# For now, we will expect them to be provided or we'll define them here if they are static.

def load_display_config(config_file: str, default_cols: List[str]) -> Dict[str, Any]:
    """加载显示配置"""
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {"current": default_cols, "sets": []}

def save_display_config(config_file: str, config: Dict[str, Any]) -> None:
    """保存显示配置"""
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def save_monitor_list(monitor_list_file: str, monitor_windows_dict: Dict[str, Any], logger: Any) -> None:
    """保存当前的监控股票列表到文件"""
    monitor_list = [win['stock_info'] for win in monitor_windows_dict.values()]
    mo_list = []
    if len(monitor_list) > 0:
        for m in monitor_list:
            stock_code = m[0]
            if stock_code:
                stock_code = stock_code.zfill(6)

            if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
                logger.info(f"错误请输入有效的6位股票代码:{m}")
                continue
            
            # 确保结构升级：带 create_time
            if len(m) < 4:
                create_time = datetime.now().strftime("%Y-%m-%d %H")
                m.append(create_time)
            mo_list.append(m)
            
        with open(monitor_list_file, "w", encoding="utf-8") as f:
            json.dump(mo_list, f, ensure_ascii=False, indent=2)
    else:
        logger.info('no window find')

    logger.info(f"监控列表已保存到 {monitor_list_file} : count: {len(mo_list)}")

def load_monitor_list(monitor_list_file: str) -> List[List[Any]]:
    """从文件加载监控股票列表"""
    if os.path.exists(monitor_list_file):
        with open(monitor_list_file, "r", encoding="utf-8") as f:
            try:
                loaded_list = json.load(f)
                if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
                    return [list(item) for item in loaded_list]
                return []
            except (json.JSONDecodeError, TypeError):
                return []
    return []

def list_archives(archive_dir: str, prefix: str = "search_history") -> List[str]:
    """列出所有存档文件"""
    if not os.path.exists(archive_dir):
        return []
    files = sorted(
        [f for f in os.listdir(archive_dir) if f.startswith(prefix) and f.endswith(".json")],
        reverse=True
    )
    return files

def archive_file_tools(src_file: str, prefix: str, archive_dir: str, logger: Any, max_keep: int = 15) -> None:
    """通用备份函数"""
    if not os.path.exists(src_file):
        logger.info(f"⚠ {src_file} 不存在，跳过存档")
        return

    try:
        with open(src_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取 {src_file}: {e}")
        return

    if not content or content in ("[]", "{}", ""):
        logger.info(f"⚠ {src_file} 内容为空，跳过存档")
        return

    os.makedirs(archive_dir, exist_ok=True)

    files = sorted(
        [f for f in os.listdir(archive_dir) if f.startswith(prefix + "_")],
        reverse=True
    )

    if files:
        last_file = os.path.join(archive_dir, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if content == last_content:
                logger.info(f"⚠ {src_file} 与上一次 {prefix} 存档相同，跳过存档")
                return
        except Exception as e:
            logger.info(f"⚠ 无法读取最近存档: {e}")

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{prefix}_{today}.json"
    dest = os.path.join(archive_dir, filename)

    shutil.copy2(src_file, dest)
    logger.info(f"✅ 已归档：{os.path.relpath(dest)}")

    files = sorted(
        [os.path.join(archive_dir, f) for f in os.listdir(archive_dir) if f.startswith(prefix + "_")],
        key=os.path.getmtime,
        reverse=True
    )
    for old_file in files[max_keep:]:
        try:
            os.remove(old_file)
            logger.info(f"🗑 删除旧归档: {os.path.basename(old_file)}")
        except Exception as e:
            logger.info(f"⚠ 删除失败 {old_file} -> {e}")

def archive_search_history_list(monitor_list_file: str, search_history_file: str, archive_dir: str, logger: Any) -> None:
    """归档监控文件，避免空或重复存档"""
    archive_file_tools(monitor_list_file, "monitor_category_list", archive_dir, logger)

    if not os.path.exists(search_history_file):
        logger.info(f"⚠ {search_history_file} 不存在，跳过归档")
        return

    try:
        with open(search_history_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        logger.info(f"⚠ {search_history_file} 内容为空，跳过归档")
        return

    os.makedirs(archive_dir, exist_ok=True)

    files = sorted(list_archives(archive_dir, "search_history"), reverse=True)
    if files:
        last_file = os.path.join(archive_dir, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if content == last_content:
                logger.info("⚠ 内容与上一次存档相同，跳过归档")
                return
        except Exception as e:
            logger.info(f"⚠ 无法读取最近存档: {e}")

    today = datetime.now().strftime("%Y-%m-%d-%H")
    filename = f"search_history_{today}.json"
    dest = os.path.join(archive_dir, filename)

    shutil.copy2(search_history_file, dest)
    logger.info(f"✅ 已归档监控文件: {dest}")

def ensure_parentheses_balanced(expr: str) -> str:
    """确保表达式括号平衡且外层包裹"""
    expr = expr.strip()
    left_count = expr.count("(")
    right_count = expr.count(")")

    if left_count > right_count:
        expr += ")" * (left_count - right_count)
    elif right_count > left_count:
        expr = "(" * (right_count - left_count) + expr

    if not (expr.startswith("(") and expr.endswith(")")):
        expr = f"({expr})"
    return expr
