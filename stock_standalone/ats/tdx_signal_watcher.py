# -*- coding: utf-8 -*-
"""
ATS TdxSignalWatcher
通达信 / OrderMon 信号文件实时监听器

核心功能:
1. 从 cct.get_tdx_signal_path() 读取动态配置的信号文本路径 (默认 D:\\TdxSignal.txt)
2. 解析 OrderMon.ini 中的 [FlagConfig] 信号映射 (如 11: 5上10, 1: Kdj金叉等)
3. 采用增量文件指针 (Seek) 极速轮询监听最新追加的信号行
4. 联动 ATS SignalLedger (信号账本置顶加权) 与 多周期策略引擎 (共振二次诊断)
"""

import os
import sys
import time
import datetime
import logging
from configobj import ConfigObj

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from JohnsonUtil import commonTips as cct

logger = logging.getLogger("ATS.TdxSignalWatcher")

# 默认信号代码标签映射字典
DEFAULT_FLAG_MAP = {
    '1': 'KDJ金叉',
    '2': 'KDJ死叉',
    '3': 'RSI金叉',
    '4': 'RSI死叉',
    '5': 'KDJ底反转',
    '6': 'KDJ顶反转',
    '7': 'RSI底反转',
    '8': 'RSI顶反转',
    '11': '5上10',
    '12': '10下5',
    '99': '设定信号',
}

TDX_PERIOD_MAP = {
    '0': '分时',
    '1': '1分钟',
    '2': '5分钟',
    '3': '15分钟',
    '4': '30分钟',
    '5': '60分钟',
    '6': '日线',
    '7': '周线',
    '8': '月线',
    '9': '多日线',
    '10': '季线',
    '11': '年线'
}


def load_ordermon_flag_map(ini_path=None) -> dict:
    """从 OrderMon.ini 读取 [FlagConfig] 信号代码与中文描述映射 (支持多编码与容错降级)"""
    flag_map = DEFAULT_FLAG_MAP.copy()
    if ini_path is None:
        ini_path = cct.get_ordermon_ini_path()

    if not os.path.exists(ini_path):
        return flag_map

    parsed_ok = False
    for enc in ['GBK', 'utf-8-sig', 'utf-8', 'ansi']:
        try:
            config = ConfigObj(ini_path, encoding=enc, raise_errors=False)
            flag_cfg = config.get('FlagConfig', {})
            for key, val in flag_cfg.items():
                if str(key).startswith('Flag') and isinstance(val, str):
                    parts = val.split('|')
                    for part in parts:
                        if '-' in part:
                            code_str, label_str = part.split('-', 1)
                            c_clean = code_str.strip()
                            l_clean = label_str.strip()
                            if c_clean and l_clean:
                                flag_map[c_clean] = l_clean
            if len(flag_map) > len(DEFAULT_FLAG_MAP):
                parsed_ok = True
                break
        except Exception:
            continue

    if not parsed_ok:
        for enc in ['gbk', 'utf-8-sig', 'utf-8', 'ansi']:
            try:
                with open(ini_path, 'r', encoding=enc, errors='ignore') as f:
                    for line in f:
                        line_s = line.strip()
                        if '-' in line_s and ('|' in line_s or 'Flag' in line_s or '=' in line_s):
                            val_part = line_s.split('=', 1)[-1] if '=' in line_s else line_s
                            for part in val_part.split('|'):
                                if '-' in part:
                                    c_str, l_str = part.split('-', 1)
                                    c_clean = c_str.strip()
                                    l_clean = l_str.strip()
                                    if c_clean.isdigit() and l_clean:
                                        flag_map[c_clean] = l_clean
                break
            except Exception:
                continue

    return flag_map


def parse_tdx_signal_line(line: str, flag_map: dict = None) -> dict:
    """解析单行通达信信号文本
    
    标准格式: 20260731|0000|600519|1|11|5|19.55|0|0|09:35:12|
    
    Returns:
        dict 或 None
    """
    if not line or not isinstance(line, str):
        return None

    line = line.strip()
    if not line or line.startswith('#') or line.startswith(';'):
        return None

    parts = [p.strip() for p in line.split('|') if p.strip() != '']
    if len(parts) < 7:
        return None

    # 提取关键字段
    date_str = parts[0]       # 20260731
    src_id = parts[1]         # 0000
    raw_code = parts[2]       # 600519
    buy_sell = parts[3]       # 1 (买入) / -1 (卖出)
    flag1 = parts[4]          # 11 (信号代码)
    flag2 = parts[5] if len(parts) > 5 else '0'
    price_str = parts[6] if len(parts) > 6 else '0.0'
    time_str = parts[9] if len(parts) > 9 else (parts[8] if len(parts) > 8 else '00:00:00')

    # 规范化股票代码 (6位)
    code = str(raw_code).zfill(6)

    # 方向解析
    direction = 1
    try:
        direction = int(buy_sell)
    except (ValueError, TypeError):
        direction = 1

    # 价格解析
    price = 0.0
    try:
        price = float(price_str)
    except (ValueError, TypeError):
        price = 0.0

    # 信号标签
    if flag_map is None:
        flag_map = DEFAULT_FLAG_MAP
    flag_label = flag_map.get(str(flag1), f"TDX-{flag1}")
    
    period_cn = TDX_PERIOD_MAP.get(str(flag2), '')

    # 获取股票名称 (使用内存高速缓存，绝不发起同步网络阻塞)
    name = code
    try:
        from sys_utils import _resolved_name_cache
        c_clean = str(code).zfill(6)
        if c_clean in _resolved_name_cache:
            name = _resolved_name_cache[c_clean]
    except Exception:
        pass

    return {
        'code': code,
        'name': name,
        'date_str': date_str,
        'direction': direction,
        'direction_cn': '买入' if direction == 1 else '卖出',
        'flag1': flag1,
        'flag2': flag2,
        'flag_label': flag_label,
        'period_cn': period_cn,
        'price': price,
        'time_str': time_str,
        'raw_line': line,
    }


class TdxSignalWatcher(QThread):
    """通达信 / OrderMon 信号文件后台轮询监听线程"""

    signal_detected = pyqtSignal(dict)  # 当捕获到新信号时触发

    def __init__(self, interval_sec: float = 2.0, parent=None):
        super().__init__(parent)
        self.interval_sec = interval_sec
        self.running = True
        self.processed_hashes = set()
        self.flag_map = load_ordermon_flag_map()
        self._last_file_path = None
        self._file_offset = 0
        self._is_initial_load = True

    def stop(self):
        """停止轮询监听 (安全等待线程退出，避免 QThread: Destroyed while still running)"""
        self.running = False
        self.requestInterruption()
        if not self.wait(3000):  # 最多等 3 秒 (超过 interval_sec=2s，保证 sleep 能结束)
            logger.warning("[TdxSignalWatcher] stop() wait timeout, forcing termination.")
            self.terminate()
            self.wait(1000)

    def run(self):
        """线程轮询主循环"""
        logger.info("[TdxSignalWatcher] 后台信号监听线程已启动")
        today_ymd = datetime.date.today().strftime('%Y%m%d')

        while self.running:
            try:
                sig_path = cct.get_tdx_signal_path()
                
                # 若监听路径变动，重置 offset 与 initial_load 标记
                if sig_path != self._last_file_path:
                    self._last_file_path = sig_path
                    self._file_offset = 0
                    self._is_initial_load = True
                    self.processed_hashes.clear()
                    self.flag_map = load_ordermon_flag_map()

                if sig_path and os.path.exists(sig_path):
                    file_size = os.path.getsize(sig_path)

                    # 如果文件被重置截断，Offset 复位
                    if file_size < self._file_offset:
                        self._file_offset = 0
                        self._is_initial_load = True

                    if file_size > self._file_offset:
                        with open(sig_path, 'r', encoding='gbk', errors='ignore') as f:
                            f.seek(self._file_offset)
                            new_lines = f.readlines()
                            self._file_offset = f.tell()

                        is_init = self._is_initial_load
                        for line in new_lines:
                            line_str = line.strip()
                            if not line_str:
                                continue

                            line_hash = hash(line_str)
                            if line_hash in self.processed_hashes:
                                continue
                            self.processed_hashes.add(line_hash)

                            sig_dict = parse_tdx_signal_line(line_str, self.flag_map)
                            if sig_dict:
                                sig_dict['is_initial_load'] = is_init
                                # 校验是否为今日信号（盘中实时消费）
                                sig_date = sig_dict.get('date_str', '')
                                if sig_date == today_ymd or not sig_date:
                                    if not is_init:
                                        logger.info(
                                            f"[TdxSignalWatcher] 捕获通达信信号: {sig_dict['code']} {sig_dict['name']} "
                                            f"[{sig_dict['flag_label']}] {sig_dict['direction_cn']} 价格:{sig_dict['price']} 时刻:{sig_dict['time_str']}"
                                        )
                                    self.signal_detected.emit(sig_dict)

                        if is_init:
                            self._is_initial_load = False

            except Exception as e:
                logger.error(f"[TdxSignalWatcher] 轮询异常: {e}")

            time.sleep(self.interval_sec)

        logger.info("[TdxSignalWatcher] 后台信号监听线程已退出")
