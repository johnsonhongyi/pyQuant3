#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
非交易时段信号清理工具
用于清理数据库中所有非交易时段(9:30-11:30, 13:00-15:00)的信号记录
"""
import sqlite3
import logging
import argparse
from datetime import datetime
from typing import Tuple, List
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def is_trading_time(timestamp_str: str) -> bool:
    """
    判断给定的时间戳是否在交易时段内
    
    Args:
        timestamp_str: 时间戳字符串,格式: "YYYY-MM-DD HH:MM:SS" 或 "HH:MM:SS"
    
    Returns:
        bool: True表示在交易时段内,False表示不在
    """
    try:
        # 提取时间部分
        if ' ' in timestamp_str:
            time_part = timestamp_str.split(' ')[1]
        else:
            time_part = timestamp_str
        
        # 转换为整数格式 HHMM
        time_obj = datetime.strptime(time_part, '%H:%M:%S')
        time_int = time_obj.hour * 100 + time_obj.minute
        
        # 交易时段: 09:30-11:30 (930-1130) 和 13:00-15:00 (1300-1500)
        # 注意: 09:30:05 开始到 11:30:00, 13:00:00 到 15:00:00
        is_morning = 930 <= time_int <= 1130
        is_afternoon = 1300 <= time_int <= 1500
        
        return is_morning or is_afternoon
    except Exception as e:
        logger.warning(f"解析时间戳失败: {timestamp_str}, 错误: {e}")
        return False


def clean_live_signal_history(db_path: str, dry_run: bool = False) -> Tuple[int, int]:
    """
    清理 live_signal_history 表中的非交易时段信号
    
    Args:
        db_path: 数据库文件路径
        dry_run: 是否为试运行模式(只统计不删除)
    
    Returns:
        Tuple[int, int]: (总记录数, 删除记录数)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        # 获取所有记录
        cur.execute("SELECT id, timestamp FROM live_signal_history")
        all_records = cur.fetchall()
        total_count = len(all_records)
        
        # 筛选出非交易时段的记录
        non_trading_ids = []
        for record_id, timestamp in all_records:
            if not is_trading_time(timestamp):
                non_trading_ids.append(record_id)
        
        delete_count = len(non_trading_ids)
        
        if delete_count > 0:
            logger.info(f"[live_signal_history] 总记录: {total_count}, 非交易时段记录: {delete_count}")
            
            if not dry_run:
                # 批量删除
                placeholders = ','.join(['?' for _ in non_trading_ids])
                cur.execute(f"DELETE FROM live_signal_history WHERE id IN ({placeholders})", non_trading_ids)
                conn.commit()
                logger.info(f"[live_signal_history] 已删除 {delete_count} 条非交易时段记录")
            else:
                logger.info(f"[live_signal_history] [试运行] 将删除 {delete_count} 条记录")
        else:
            logger.info(f"[live_signal_history] 无需清理,所有记录均在交易时段内")
        
        return total_count, delete_count
    
    finally:
        cur.close()
        conn.close()


def clean_signal_message(db_path: str, dry_run: bool = False) -> Tuple[int, int]:
    """
    清理 signal_message 表中的非交易时段信号
    
    Args:
        db_path: 数据库文件路径
        dry_run: 是否为试运行模式(只统计不删除)
    
    Returns:
        Tuple[int, int]: (总记录数, 删除记录数)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        # 获取所有记录
        cur.execute("SELECT id, timestamp FROM signal_message")
        all_records = cur.fetchall()
        total_count = len(all_records)
        
        # 筛选出非交易时段的记录
        non_trading_ids = []
        for record_id, timestamp in all_records:
            if not is_trading_time(timestamp):
                non_trading_ids.append(record_id)
        
        delete_count = len(non_trading_ids)
        
        if delete_count > 0:
            logger.info(f"[signal_message] 总记录: {total_count}, 非交易时段记录: {delete_count}")
            
            if not dry_run:
                # 批量删除
                placeholders = ','.join(['?' for _ in non_trading_ids])
                cur.execute(f"DELETE FROM signal_message WHERE id IN ({placeholders})", non_trading_ids)
                conn.commit()
                logger.info(f"[signal_message] 已删除 {delete_count} 条非交易时段记录")
            else:
                logger.info(f"[signal_message] [试运行] 将删除 {delete_count} 条记录")
        else:
            logger.info(f"[signal_message] 无需清理,所有记录均在交易时段内")
        
        return total_count, delete_count
    
    finally:
        cur.close()
        conn.close()


def backup_database(db_path: str) -> str:
    """
    备份数据库文件
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        str: 备份文件路径
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.backup_{timestamp}"
    
    import shutil
    shutil.copy2(db_path, backup_path)
    logger.info(f"数据库已备份至: {backup_path}")
    
    return backup_path


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='清理数据库中非交易时段的信号记录',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 试运行模式(只统计不删除)
  python cleanup_non_trading_signals.py --dry-run
  
  # 清理 trading_signals.db
  python cleanup_non_trading_signals.py --db trading_signals.db
  
  # 清理 signal_strategy.db
  python cleanup_non_trading_signals.py --db signal_strategy.db
  
  # 清理所有数据库
  python cleanup_non_trading_signals.py --all
  
  # 清理时不备份
  python cleanup_non_trading_signals.py --all --no-backup
        """
    )
    
    parser.add_argument(
        '--db',
        type=str,
        help='指定要清理的数据库文件路径'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='清理所有相关数据库(trading_signals.db 和 signal_strategy.db)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='试运行模式,只统计不删除'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='不备份数据库(默认会先备份)'
    )
    
    args = parser.parse_args()
    
    # 确定要处理的数据库列表
    db_files: List[str] = []
    
    if args.all:
        db_files = ['trading_signals.db', 'signal_strategy.db']
    elif args.db:
        db_files = [args.db]
    else:
        # 默认处理两个主要数据库
        db_files = ['trading_signals.db', 'signal_strategy.db']
    
    # 处理每个数据库
    total_deleted = 0
    
    for db_file in db_files:
        db_path = Path(db_file)
        
        if not db_path.exists():
            logger.warning(f"数据库文件不存在,跳过: {db_file}")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"开始处理数据库: {db_file}")
        logger.info(f"{'='*60}")
        
        # 备份数据库
        if not args.dry_run and not args.no_backup:
            backup_database(str(db_path))
        
        # 清理 live_signal_history 表 (在 trading_signals.db 中)
        if 'trading_signals' in db_file:
            try:
                total, deleted = clean_live_signal_history(str(db_path), args.dry_run)
                total_deleted += deleted
            except Exception as e:
                logger.error(f"清理 live_signal_history 失败: {e}")
        
        # 清理 signal_message 表 (在 signal_strategy.db 中)
        if 'signal_strategy' in db_file:
            try:
                total, deleted = clean_signal_message(str(db_path), args.dry_run)
                total_deleted += deleted
            except Exception as e:
                logger.error(f"清理 signal_message 失败: {e}")
    
    # 总结
    logger.info(f"\n{'='*60}")
    if args.dry_run:
        logger.info(f"[试运行完成] 共发现 {total_deleted} 条非交易时段记录")
        logger.info("提示: 去掉 --dry-run 参数可执行实际删除操作")
    else:
        logger.info(f"[清理完成] 共删除 {total_deleted} 条非交易时段记录")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
