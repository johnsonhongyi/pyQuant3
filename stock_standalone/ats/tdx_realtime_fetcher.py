# -*- coding: utf-8 -*-
"""
ats/tdx_realtime_fetcher.py — 通达信 (pytdx) 独立高频秒级行情引擎
特点：
1. 优先从用户本地通达信目录 (D:\\MacTools\\WinTools\\new_tdx2\\connect.cfg 等) 提取预设 HQHOST 服务器列表；
2. 支持并发测速与动态自动故障切换 (Failover)，确保毫秒级连接可用服务器；
3. 支持针对指定监控标的（新股/次新股/科创板/主板）进行 1~3 秒级高频独立轮询；
4. 自动解析五档盘口、实时成交、分时 VWAP 与换手率，转化为标准 DataFrame 与行情快照字典；
5. 提供后台独立 Worker 线程与 Qt Signal 异步广播机制，完全不阻塞 UI 主线程。
"""

import sys
import os
import re
import time
import threading
import concurrent.futures
import collections
import datetime
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from pytdx.hq import TdxHq_API

from logger_utils import LoggerFactory
from JohnsonUtil import commonTips as cct
from ats.sector_etf_engine import get_sector_etf_engine
from ats.reentry_tracker import get_reentry_tracker

import math

logger = LoggerFactory.getLogger("TDXRealtimeFetcher")


def safe_float(val: Any, default: float = 0.0) -> float:
    """健壮的浮点数安全转换函数，杜绝 '-', '--', 'None', NaN, Inf 抛出异常"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default

# 默认预备通达信 HQ 服务器 (防本地配置文件不存在时的 Fallback)
FALLBACK_TDX_HOSTS = [
    ("通达信移动主站1", "111.15.15.43", 7709),
    ("通达信北京主站", "202.108.254.67", 7709),
    ("通达信华东主站", "117.149.2.68", 7709),
    ("通达信杭州主站", "120.199.2.122", 7709),
    ("通达信江苏主站", "223.112.100.140", 7709),
    ("招商证券深圳", "119.147.212.81", 7709),
    ("华泰证券南京", "221.231.141.60", 7709),
    ("国泰君安上海", "218.75.126.9", 7709),
    ("通达信官方2", "60.12.136.250", 7709),
    ("中信证券北京", "115.238.56.198", 7709)
]

def get_trading_segment_info(now_ts: float, segment_mode: str = "30m") -> Tuple[str, str, float, float]:
    """
    根据当前时间戳与分段模式（30m/15m/60m/day_open/60s），计算当前所属交易分段信息。
    :return: (segment_key, segment_label, start_epoch, end_epoch)
    """
    dt = datetime.fromtimestamp(now_ts) if now_ts > 0 else datetime.now()
    hm = dt.strftime("%H:%M")

    def make_epoch(h, m):
        return datetime(dt.year, dt.month, dt.day, h, m, 0).timestamp()

    if segment_mode == "day_open":
        return "09:30~15:00", "⏱️ 全天开盘累计", make_epoch(9, 30), make_epoch(15, 0)
    elif segment_mode == "60s":
        return "60s_rolling", "⏱️ 60秒滑动窗口", now_ts - 60.0, now_ts
    elif segment_mode == "15m":
        slots_15m = [
            ("09:15", "09:30", "09:15~09:30", "⏱️ 09:15~09:30 竞价"),
            ("09:30", "09:45", "09:30~09:45", "⏱️ 09:30~09:45 冲刺"),
            ("09:45", "10:00", "09:45~10:00", "⏱️ 09:45~10:00 定龙"),
            ("10:00", "10:15", "10:00~10:15", "⏱️ 10:00~10:15 换手"),
            ("10:15", "10:30", "10:15~10:30", "⏱️ 10:15~10:30 分歧"),
            ("10:30", "10:45", "10:30~10:45", "⏱️ 10:30~10:45 震荡"),
            ("10:45", "11:00", "10:45~11:00", "⏱️ 10:45~11:00 整理"),
            ("11:00", "11:15", "11:00~11:15", "⏱️ 11:00~11:15 收敛"),
            ("11:15", "11:30", "11:15~11:30", "⏱️ 11:15~11:30 午结"),
            ("11:30", "13:00", "11:30~13:00", "⏱️ 11:30~13:00 午休"),
            ("13:00", "13:15", "13:00~13:15", "⏱️ 13:00~13:15 午启"),
            ("13:15", "13:30", "13:15~13:30", "⏱️ 13:15~13:30 助攻"),
            ("13:30", "13:45", "13:30~13:45", "⏱️ 13:30~13:45 发酵"),
            ("13:45", "14:00", "13:45~14:00", "⏱️ 13:45~14:00 扩散"),
            ("14:00", "14:15", "14:00~14:15", "⏱️ 14:00~14:15 试盘"),
            ("14:15", "14:30", "14:15~14:30", "⏱️ 14:15~14:30 抢跑"),
            ("14:30", "14:45", "14:30~14:45", "⏱️ 14:30~14:45 定盘"),
            ("14:45", "15:00", "14:45~15:00", "⏱️ 14:45~15:00 封死"),
        ]
        for s_hm, e_hm, k, lab in slots_15m:
            if s_hm <= hm < e_hm:
                sh, sm = map(int, s_hm.split(":"))
                eh, em = map(int, e_hm.split(":"))
                return k, lab, make_epoch(sh, sm), make_epoch(eh, em)
        return "15:00+", "⏱️ 15:00+ 盘后总结", make_epoch(15, 0), make_epoch(15, 30)

    elif segment_mode == "60m":
        slots_60m = [
            ("09:15", "09:30", "09:15~09:30", "⏱️ 09:15~09:30 竞价"),
            ("09:30", "10:30", "09:30~10:30", "⏱️ 09:30~10:30 早盘一小时"),
            ("10:30", "11:30", "10:30~11:30", "⏱️ 10:30~11:30 午前一小时"),
            ("11:30", "13:00", "11:30~13:00", "⏱️ 11:30~13:00 午间休市"),
            ("13:00", "14:00", "13:00~14:00", "⏱️ 13:00~14:00 午后一小时"),
            ("14:00", "15:00", "14:00~15:00", "⏱️ 14:00~15:00 尾盘一小时"),
        ]
        for s_hm, e_hm, k, lab in slots_60m:
            if s_hm <= hm < e_hm:
                sh, sm = map(int, s_hm.split(":"))
                eh, em = map(int, e_hm.split(":"))
                return k, lab, make_epoch(sh, sm), make_epoch(eh, em)
        return "15:00+", "⏱️ 15:00+ 盘后总结", make_epoch(15, 0), make_epoch(15, 30)

    else:
        # 默认 30m 黄金分段体系
        slots_30m = [
            ("09:15", "09:30", "09:15~09:30", "⏱️ 09:15~09:30 竞价试盘"),
            ("09:30", "10:00", "09:30~10:00", "👑 09:30~10:00 早盘冲刺定龙"),
            ("10:00", "10:30", "10:00~10:30", "💎 10:00~10:30 分歧换手确认"),
            ("10:30", "11:00", "10:30~11:00", "⚡ 10:30~11:00 午前震荡分化"),
            ("11:00", "11:30", "11:00~11:30", "⏱️ 11:00~11:30 午前收敛防守"),
            ("11:30", "13:00", "11:30~13:00", "⏱️ 11:30~13:00 午间休市"),
            ("13:00", "13:30", "13:00~13:30", "🚀 13:00~13:30 午后开盘助攻"),
            ("13:30", "14:00", "13:30~14:00", "🔥 13:30~14:00 题材二次发酵"),
            ("14:00", "14:30", "14:00~14:30", "⚠️ 14:00~14:30 尾盘博弈试盘"),
            ("14:30", "15:00", "14:30~15:00", "🔒 14:30~15:00 尾盘定龙定盘"),
        ]
        for s_hm, e_hm, k, lab in slots_30m:
            if s_hm <= hm < e_hm:
                sh, sm = map(int, s_hm.split(":"))
                eh, em = map(int, e_hm.split(":"))
                return k, lab, make_epoch(sh, sm), make_epoch(eh, em)
        return "15:00+", "⏱️ 15:00+ 盘后总结", make_epoch(15, 0), make_epoch(15, 30)


def get_local_tdx_config_paths() -> List[str]:
    """
    动态自适应获取当前系统及 global.ini 中配置的所有有效通达信配置文件 (connect.cfg 等)
    彻底告别静态硬编码，支持跨设备与多环境自适应发现
    """
    try:
        if hasattr(cct, "get_tdx_config_paths"):
            paths = cct.get_tdx_config_paths()
            if paths:
                return paths
    except Exception as e:
        logger.error(f"cct.get_tdx_config_paths 探测异常: {e}")

    # 兜底：如果 cct 异常，自适应从 cct.get_tdx_dir() 动态探测
    fallback_paths = []
    try:
        main_dir = cct.get_tdx_dir() if hasattr(cct, "get_tdx_dir") else ""
        if main_dir and os.path.exists(main_dir):
            for sub in ["connect.cfg", "connect-ShowTab.cfg", "embconnect.cfg", os.path.join("T0002", "connect.cfg")]:
                p = os.path.join(main_dir, sub)
                if os.path.isfile(p):
                    fallback_paths.append(os.path.normpath(p))
    except Exception:
        pass

    return fallback_paths


# 兼容性别名：动态获取本地有效配置路径
LOCAL_TDX_CONFIG_PATHS = get_local_tdx_config_paths()


def extract_hosts_from_tdx_cfg(cfg_path: str) -> List[Tuple[str, str, int]]:
    """从通达信 connect.cfg 配置文件中解析 [HQHOST] 服务器列表"""
    hosts = []
    if not cfg_path or not os.path.exists(cfg_path):
        return hosts
    try:
        with open(cfg_path, "r", encoding="gbk", errors="ignore") as f:
            content = f.read()

        hq_match = re.search(r"\[HQHOST\](.*?)(\[\w+\]|$)", content, re.DOTALL | re.IGNORECASE)
        if hq_match:
            hq_block = hq_match.group(1)
            items = re.findall(
                r"HostName\d*=(.*?)\n.*?IPAddress\d*=(.*?)\n.*?Port\d*=(\d+)",
                hq_block,
                re.DOTALL | re.IGNORECASE
            )
            for name, ip, port in items:
                ip_clean = ip.strip()
                if ip_clean and not ip_clean.startswith("127.") and not ip_clean.startswith("192.168."):
                    hosts.append((name.strip(), ip_clean, int(port.strip())))

        if not hosts:
            ips = re.findall(r"IPAddress\d*=([0-9\.]+)\s+Port\d*=(\d+)", content, re.IGNORECASE)
            for ip, port in ips:
                ip_clean = ip.strip()
                if ip_clean and not ip_clean.startswith("127.") and not ip_clean.startswith("192.168."):
                    hosts.append(("TDX_HQ", ip_clean, int(port.strip())))
    except Exception as e:
        logger.warning(f"解析 TDX 配置 {cfg_path} 异常: {e}")
    return hosts


def get_all_tdx_hosts() -> List[Tuple[str, str, int]]:
    """获取所有可用 TDX 服务器（动态探测本地预设优先，Fallback 兜底，去重）"""
    all_hosts = []
    seen = set()

    cfg_paths = get_local_tdx_config_paths()
    for path in cfg_paths:
        parsed = extract_hosts_from_tdx_cfg(path)
        for name, ip, port in parsed:
            if (ip, port) not in seen:
                seen.add((ip, port))
                all_hosts.append((name, ip, port))

    local_count = len(all_hosts)
    for name, ip, port in FALLBACK_TDX_HOSTS:
        if (ip, port) not in seen:
            seen.add((ip, port))
            all_hosts.append((name, ip, port))

    logger.info(
        f"⚡ [TDX自适应] 探测到 {len(cfg_paths)} 个有效配置文件，提取 {local_count} 个本地 HQHOST 节点 (总池: {len(all_hosts)} 个)"
    )
    return all_hosts


def get_market_code(stock_code: str) -> int:
    """
    根据股票代码判断通达信市场代码：
    0 -> 深圳市场 (000, 001, 002, 003, 300, 301, 302, 159, 123, 127, 128, 200 等)
    1 -> 上海市场 (600, 601, 603, 605, 688, 689, 110, 113, 118, 510, 588, 900, 999 等)
    2 -> 北京市场 (920, 83, 87, 88, 43, 82 等)
    """
    c = str(stock_code).strip().zfill(6)
    if c.startswith(("920", "83", "87", "88", "43", "82")):
        return 2
    elif c.startswith(("60", "68", "99", "11", "51", "58", "90")):
        return 1
    return 0


def is_trading_time(now_dt=None) -> Tuple[bool, str]:
    """
    优先使用 JohnsonUtil.commonTips (cct) 原生实盘时段与交易日状态判定
    返回 (is_trading, status_text)
    """
    t_str = time.strftime("%H:%M:%S")
    try:
        is_work_day = cct.get_work_day_status()
        if not is_work_day:
            return False, f"周末/假日休市 ({t_str})"

        is_work_time = cct.get_work_time()
        now_int = cct.get_now_time_int()

        if is_work_time:
            if now_int < 930:
                return True, f"早盘集合竞价 ({t_str})"
            elif now_int >= 1500:
                return True, f"尾盘收盘集合竞价 ({t_str})"
            return True, f"实盘交易中 ({t_str})"
        else:
            if 1130 <= now_int < 1300:
                return False, f"午间休市休眠 ({t_str})"
            return False, f"收盘休市休眠 ({t_str})"
    except Exception as e:
        logger.debug(f"cct.get_work_time 异常降级: {e}")

    # 本地备用降级逻辑
    now = now_dt or datetime.datetime.now()
    if now.weekday() >= 5:
        return False, f"周末休市 ({t_str})"
    t = now.time()
    if datetime.time(9, 15, 0) <= t <= datetime.time(11, 30, 30) or datetime.time(12, 59, 30) <= t <= datetime.time(15, 5, 0):
        return True, f"实盘交易中 ({t_str})"
    return False, f"休市休眠中 ({t_str})"


# 兼容性别名
is_trade_time_now = is_trading_time


class TDXRealtimeFetcher:
    """
    通达信行情高频并发拉取单例引擎
    """
    _instance: Optional['TDXRealtimeFetcher'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'TDXRealtimeFetcher':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.api: Optional[TdxHq_API] = None
        self.current_host: Optional[Tuple[str, str, int]] = None
        self.latency_ms: float = 9999.0
        self.active_hosts_pool: List[Tuple[float, str, str, int]] = []
        self._is_connected = False
        self._conn_lock = threading.RLock()
        
        # 内存日志缓冲队列 (最大保留 500 条最新日志)
        self._log_buffer = collections.deque(maxlen=500)
        self._log_lock = threading.Lock()
        
        # 标的尝试获取计数与未上市/休市静默保护字典 (尝试 3 次无成交则标记并进入冷却)
        self._no_quote_counts: Dict[str, int] = collections.defaultdict(int)
        self._no_quote_last_attempt: Dict[str, float] = collections.defaultdict(float)
        self._unlisted_or_dormant_codes: Set[str] = set()

        # 非交易时段定盘缓存与尝试计数 (非交易时段成功获取 3 次即定盘休眠，复用盘后缓存，不再重复发送网络请求)
        self._off_hours_cached_quotes: Dict[str, Dict[str, Any]] = {}
        self._off_hours_success_counts: Dict[str, int] = collections.defaultdict(int)
        self._off_hours_settled_codes: Set[str] = set()

        # 自适应防限流与动态间隔退避控制器 (基准 3.0s，限流时自动延展至 15.0s)
        self.base_interval_sec: float = 3.0
        self.current_interval_sec: float = 3.0
        self.max_backoff_interval: float = 15.0
        self._consecutive_slow_or_errors: int = 0
        self._consecutive_healthy: int = 0

        # 工业级 1 分钟滑动窗口价格时序队列 {code: deque([(t, price), ...], maxlen=60)}
        self._price_timeline_history: Dict[str, collections.deque] = {}
        # 标的历史平滑涨速缓存与状态 {code: float}, {code: str}
        self._smoothed_velocity: Dict[str, float] = {}
        self._velocity_tags: Dict[str, str] = {}

        # ⏱️ 交易时段分段基准缓存 {code: {segment_key: {'base_price': float, 'base_vol': float, 'base_amount': float, 'first_seen_time': float, 'date': str}}}
        self._segment_stock_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # 标的真实流通股本与总股本永久缓存 (股数)
        self._finance_shares_cache: Dict[str, float] = {}
        self._total_shares_cache: Dict[str, float] = {}

        self.add_log("🚀 TDX 高频行情引擎初始化完成，准备测速与连接最优主站 (基准周期: 3.0s)", level="INFO")

        # 启动时快速选取最优服务器
        self._init_best_server()

    def get_circulation_shares(self, code: str) -> float:
        """获取标的真实流通股本 (股)，带内存永久缓存与按需懒拉取，实现 100% 精准换手率与流通市值"""
        c_clean = str(code).strip().zfill(6)
        if c_clean in self._finance_shares_cache and self._finance_shares_cache[c_clean] > 0:
            return self._finance_shares_cache[c_clean]

        # 1. 尝试从 NewStockFetcher 权威 IPO 日历/缓存中获取新股流通股本
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            ns_fetcher = NewStockFetcher.get_instance()
            if hasattr(ns_fetcher, "_cached_ipo_dict") and c_clean in ns_fetcher._cached_ipo_dict:
                ipo_info = ns_fetcher._cached_ipo_dict[c_clean]
                online_num = float(ipo_info.get("online_issue_num", 0.0) or 0.0)
                issue_num = float(ipo_info.get("issue_num", 0.0) or 0.0)
                if online_num > 0:
                    self._finance_shares_cache[c_clean] = online_num
                    return online_num
                elif issue_num > 0:
                    self._finance_shares_cache[c_clean] = issue_num
                    return issue_num
        except Exception:
            pass

        # 2. 尝试从本地阶梯规格获取
        try:
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            spec = IntradayStrategyEngine.get_instance().get_stock_ladder_spec(c_clean)
            float_shares_wan = float(spec.get("float_shares_wan", 0.0) or 0.0)
            if float_shares_wan > 0:
                self._finance_shares_cache[c_clean] = float_shares_wan * 10000.0
                return self._finance_shares_cache[c_clean]
        except Exception:
            pass

        # 3. 尝试从 TDX 财务数据接口拉取 (单次拉取永久有效)
        with self._conn_lock:
            try:
                if not self._is_connected:
                    self.connect()
                if self._is_connected and self.api:
                    mkt = get_market_code(c_clean)
                    fin = self.api.get_finance_info(mkt, c_clean)
                    if fin and "liutongguben" in fin:
                        shares = float(fin["liutongguben"] or 0.0)
                        if shares > 0:
                            self._finance_shares_cache[c_clean] = shares
                        if "zongguben" in fin and float(fin["zongguben"] or 0.0) > 0:
                            self._total_shares_cache[c_clean] = float(fin["zongguben"])
                        if shares > 0:
                            return shares
            except Exception:
                pass

        # 4. 尝试从本地股票基础数据表获取
        try:
            import JohnsonUtil.commonTips as cct
            df_basics = cct.get_tushare_stock_basics()
            if df_basics is not None and not df_basics.empty:
                if c_clean in df_basics.index:
                    row = df_basics.loc[c_clean]
                    # totals 为万股
                    outstanding = float(row.get("outstanding", 0.0) or 0.0)
                    totals = float(row.get("totals", 0.0) or 0.0)
                    if outstanding > 0:
                        self._finance_shares_cache[c_clean] = outstanding * 10000.0
                        return self._finance_shares_cache[c_clean]
                    elif totals > 0:
                        self._finance_shares_cache[c_clean] = totals * 10000.0
                        return self._finance_shares_cache[c_clean]
        except Exception:
            pass

        return 150000000.0

    def get_total_shares(self, code: str) -> float:
        """获取标的真实总股本 (股)，用于精准推算总市值"""
        c_clean = str(code).strip().zfill(6)
        if c_clean in self._total_shares_cache and self._total_shares_cache[c_clean] > 0:
            return self._total_shares_cache[c_clean]

        with self._conn_lock:
            try:
                if not self._is_connected:
                    self.connect()
                if self._is_connected and self.api:
                    mkt = get_market_code(c_clean)
                    fin = self.api.get_finance_info(mkt, c_clean)
                    if fin and "zongguben" in fin:
                        zg = float(fin["zongguben"] or 0.0)
                        if zg > 0:
                            self._total_shares_cache[c_clean] = zg
                        if "liutongguben" in fin and float(fin["liutongguben"] or 0.0) > 0:
                            self._finance_shares_cache[c_clean] = float(fin["liutongguben"])
                        if zg > 0:
                            return zg
            except Exception:
                pass

        # 降级：若无总股本，回退为流通股本
        return self.get_circulation_shares(c_clean)

    def get_batch_finance_shares(self, codes: List[str]) -> Dict[str, Tuple[float, float]]:
        """
        批量并发/按需快速拉取标的流通股本与总股本字典 {code: (liutong_shares, total_shares)}
        """
        res: Dict[str, Tuple[float, float]] = {}
        if not codes:
            return res

        missing = []
        for c in codes:
            c_clean = str(c).strip().zfill(6)
            lt = self._finance_shares_cache.get(c_clean, 0.0)
            zg = self._total_shares_cache.get(c_clean, 0.0)
            if lt > 0 and zg > 0:
                res[c_clean] = (lt, zg)
            else:
                missing.append(c_clean)

        if missing:
            with self._conn_lock:
                if not self._is_connected:
                    self.connect()
                if self._is_connected and self.api:
                    for c_clean in missing:
                        try:
                            mkt = get_market_code(c_clean)
                            fin = self.api.get_finance_info(mkt, c_clean)
                            lt = float(fin.get("liutongguben") or 0.0) if fin else 0.0
                            zg = float(fin.get("zongguben") or 0.0) if fin else 0.0
                            if lt > 0:
                                self._finance_shares_cache[c_clean] = lt
                            if zg > 0:
                                self._total_shares_cache[c_clean] = zg
                            if lt > 0 or zg > 0:
                                res[c_clean] = (lt if lt > 0 else zg, zg if zg > 0 else lt)
                        except Exception:
                            pass

        # 针对仍未命中的赋予安全降级值
        for c in codes:
            c_clean = str(c).strip().zfill(6)
            if c_clean not in res:
                lt = self._finance_shares_cache.get(c_clean, 150000000.0)
                zg = self._total_shares_cache.get(c_clean, lt)
                res[c_clean] = (lt, zg)

        return res

    def get_market_code(self, code: str) -> int:
        """获取通达信市场代码 (0: 深市/创业板, 1: 沪市/科创板, 2: 北交所)"""
        return get_market_code(code)

    def _record_request_feedback(self, cost_ms: float, is_error: bool = False):
        """
        根据单次网络通信的耗时与健康状况，自适应调整拉取间隔（防封禁与退避保护）：
        - 耗时 >= 600ms 或通信异常 -> 触发退避延长间隔 (3.0s -> 4.5s -> 6.8s -> 10.0s -> 15.0s)
        - 耗时 < 250ms 且正常通信 -> 连续 2 次后平滑恢复至 3.0s
        """
        if is_error or cost_ms >= 600.0:
            self._consecutive_slow_or_errors += 1
            self._consecutive_healthy = 0
            if self._consecutive_slow_or_errors >= 2:
                new_interval = min(self.max_backoff_interval, round(self.base_interval_sec * (1.5 ** min(self._consecutive_slow_or_errors, 4)), 1))
                if new_interval > self.current_interval_sec:
                    self.current_interval_sec = new_interval
                    reason = "通信异常" if is_error else f"响应缓慢 ({cost_ms:.0f}ms)"
                    self.add_log(f"⚠️ [WARN] 捕捉到 TDX {reason} 疑似被限流，自适应延长获取间隔至 {self.current_interval_sec:.1f}s 避免封禁", level="WARN")
        else:
            self._consecutive_slow_or_errors = 0
            if self.current_interval_sec > self.base_interval_sec:
                self._consecutive_healthy += 1
                if self._consecutive_healthy >= 2:
                    self.current_interval_sec = self.base_interval_sec
                    self._consecutive_healthy = 0
                    self.add_log(f"✅ [INFO] TDX 通信恢复极速稳定 ({cost_ms:.0f}ms)，获取间隔自动恢复为 {self.base_interval_sec:.1f}s", level="INFO")

    def get_recommended_interval_ms(self) -> int:
        """获取当前推荐的 UI 定时器毫秒数 (默认 3000ms)"""
        return int(self.current_interval_sec * 1000)

    def get_current_interval_sec(self) -> float:
        """获取当前推荐的轮询秒数 (默认 3.0s)"""
        return self.current_interval_sec

    def reset_code_dormancy(self, code: Optional[str] = None):
        """重置某标的或全量标的的无行情尝试计数与静默状态（供用户切换标的或手动刷新时调用）"""
        with self._conn_lock:
            if code:
                c_clean = str(code).strip().zfill(6)
                self._no_quote_counts.pop(c_clean, None)
                self._no_quote_last_attempt.pop(c_clean, None)
                self._unlisted_or_dormant_codes.discard(c_clean)
                self._off_hours_success_counts.pop(c_clean, None)
                self._off_hours_settled_codes.discard(c_clean)
            else:
                self._no_quote_counts.clear()
                self._no_quote_last_attempt.clear()
                self._unlisted_or_dormant_codes.clear()
                self._off_hours_success_counts.clear()
                self._off_hours_settled_codes.clear()

    def add_log(self, msg: str, level: str = "INFO"):
        """向内存循环队列记录结构化日志"""
        ts = time.strftime("%H:%M:%S")
        prefix = {
            "INFO": "✅ [INFO]",
            "WARN": "⚠️ [WARN]",
            "ERROR": "❌ [ERROR]",
            "SLEEP": "💤 [SLEEP]",
            "SPEED": "⚡ [SPEED]"
        }.get(level, "🔹 [LOG]")
        log_line = f"[{ts}] {prefix} {msg}"
        with self._log_lock:
            self._log_buffer.append(log_line)
        if level in ("ERROR", "WARN"):
            logger.warning(log_line)
        else:
            logger.debug(log_line)

    def get_logs(self, limit: int = 300) -> List[str]:
        """获取最近的结构化日志列表"""
        with self._log_lock:
            logs = list(self._log_buffer)
            return logs[-limit:] if limit > 0 else logs

    def clear_logs(self):
        """清空日志缓存"""
        with self._log_lock:
            self._log_buffer.clear()
            self._log_buffer.append(f"[{time.strftime('%H:%M:%S')}] 🧹 [INFO] 日志缓存已清空")

    def _ping_single_host(self, host_item: Tuple[str, str, int]) -> Optional[Tuple[float, str, str, int]]:
        name, ip, port = host_item
        test_api = TdxHq_API(heartbeat=False)
        t0 = time.time()
        try:
            if test_api.connect(ip, port, time_out=0.6):
                # 必须验证能成功拉取真实行情
                quotes = test_api.get_security_quotes([(1, "600519")])
                cost = (time.time() - t0) * 1000
                test_api.disconnect()
                if quotes and len(quotes) >= 1 and quotes[0].get("price") is not None:
                    return (cost, name, ip, port)
        except Exception:
            pass
        return None

    def _init_best_server(self, max_test_count: int = 40):
        """并发测速并连接最优服务器"""
        hosts = get_all_tdx_hosts()
        if not hosts:
            hosts = FALLBACK_TDX_HOSTS

        test_targets = hosts[:max_test_count]
        valid_results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(self._ping_single_host, h) for h in test_targets]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    valid_results.append(res)

        if valid_results:
            valid_results.sort(key=lambda x: x[0])
            self.active_hosts_pool = valid_results
            best = valid_results[0]
            self.latency_ms = best[0]
            self.current_host = (best[1], best[2], best[3])
            logger.info(f"🏆 TDX 极速服务器选定: {best[1]} ({best[2]}:{best[3]}), 延迟: {best[0]:.1f}ms")
        else:
            fb = FALLBACK_TDX_HOSTS[0]
            self.current_host = (fb[0], fb[1], fb[2])
            self.latency_ms = 150.0

    def connect(self) -> bool:
        """建立或确保连接"""
        with self._conn_lock:
            if self._is_connected and self.api is not None:
                return True

            if not self.current_host:
                self._init_best_server()

            if not self.current_host:
                self.add_log("❌ 无可用 TDX 服务器列表，连接失败", level="ERROR")
                return False

            name, ip, port = self.current_host
            self.api = TdxHq_API(heartbeat=False)
            try:
                if self.api.connect(ip, port, time_out=1.2):
                    self._is_connected = True
                    self.add_log(f"已成功连接到主站 [{name}] ({ip}:{port})", level="INFO")
                    return True
            except Exception as e:
                self.add_log(f"连接主站 [{name}] ({ip}:{port}) 失败: {e}", level="WARN")
                self._is_connected = False

            # 故障转移
            for cost, f_name, f_ip, f_port in self.active_hosts_pool[1:5]:
                try:
                    self.api = TdxHq_API(heartbeat=False)
                    if self.api.connect(f_ip, f_port, time_out=1.2):
                        self._is_connected = True
                        self.current_host = (f_name, f_ip, f_port)
                        self.latency_ms = cost
                        self.add_log(f"故障切换成功连接到备用服务器 [{f_name}] ({f_ip}:{f_port}), 延迟: {cost:.1f}ms", level="INFO")
                        return True
                except Exception as e_failover:
                    self.add_log(f"尝试备用服务器 [{f_name}] ({f_ip}:{f_port}) 失败: {e_failover}", level="WARN")
                    continue

            self.add_log("所有备用 TDX HQ 服务器连接均失败，网络或 IP 可能受限", level="ERROR")
            return False

    def disconnect(self):
        with self._conn_lock:
            if self.api:
                try:
                    self.api.disconnect()
                except Exception:
                    pass
            self.api = None
            self._is_connected = False

    def get_security_quotes_safe(self, codes: List[str], force: bool = False) -> List[Dict[str, Any]]:
        """
        安全批量获取股票最新五档盘口行情（支持 force=True 强制透传全量穿透）
        :param codes: 股票代码列表，例如 ['688826', '600519']
        :param force: 是否强制无视定盘与静默冷却，全量向服务器发起拉取
        :return: 盘口字典列表
        """
        if not codes:
            return []

        # ⚡ 拦截并过滤退市股票
        codes = cct.filter_delisted_stocks(codes)
        if not codes:
            return []

        now_t = time.time()
        is_trading, _ = is_trading_time()
        cooldown_sec = 60.0 if is_trading else 180.0

        # 若强制刷新，清空非交易时段定盘与静默状态
        if force:
            if self._off_hours_settled_codes:
                self._off_hours_settled_codes.clear()
                self._off_hours_success_counts.clear()
            self._unlisted_or_dormant_codes.clear()
            self._no_quote_counts.clear()
            self._no_quote_last_attempt.clear()

        cached_results = []
        active_codes = []
        for c in codes:
            c_clean = str(c).strip().zfill(6)
            # 非交易时段定盘保护：若已完成 3 次拉取定盘且非强制，直接复用盘后缓存
            if not force and not is_trading and c_clean in self._off_hours_settled_codes and c_clean in self._off_hours_cached_quotes:
                cached_results.append(self._off_hours_cached_quotes[c_clean])
                continue

            if not force and c_clean in self._unlisted_or_dormant_codes:
                last_try = self._no_quote_last_attempt.get(c_clean, 0.0)
                if now_t - last_try < cooldown_sec:
                    if c_clean in self._off_hours_cached_quotes:
                        cached_results.append(self._off_hours_cached_quotes[c_clean])
                    continue
            active_codes.append(c_clean)

        if not active_codes:
            return cached_results

        all_fetched_quotes = []
        chunk_size = 40  # 符合 TDXHQ 协议的安全批次大小

        with self._conn_lock:
            if not self._is_connected:
                if not self.connect():
                    self.add_log(f"无法建立 TDX 连接，跳过获取 {len(active_codes)} 只标的行情", level="ERROR")
                    return cached_results

            for i in range(0, len(active_codes), chunk_size):
                chunk = active_codes[i:i + chunk_size]
                req_params = [(get_market_code(c_c), c_c) for c_c in chunk]
                codes_str = ",".join(c for _, c in req_params)
                t_start = time.time()
                try:
                    quotes = self.api.get_security_quotes(req_params)
                    cost_ms = (time.time() - t_start) * 1000.0
                    host_info = f"{self.current_host[0]}" if self.current_host else "TDX"
                    if quotes:
                        self._record_request_feedback(cost_ms, is_error=False)
                        returned_codes = set()
                        for q in quotes:
                            c_clean = str(q.get("code", "")).strip().zfill(6)
                            if not c_clean:
                                continue
                            returned_codes.add(c_clean)
                            p = safe_float(q.get("price", 0.0))
                            last_c = safe_float(q.get("last_close", 0.0))
                            if p > 0 or last_c > 0:
                                if c_clean in self._unlisted_or_dormant_codes:
                                    self._unlisted_or_dormant_codes.discard(c_clean)
                                self._no_quote_counts[c_clean] = 0

                                # 记录有效定盘快照
                                self._off_hours_cached_quotes[c_clean] = q
                                if not is_trading:
                                    self._off_hours_success_counts[c_clean] += 1
                                    if self._off_hours_success_counts[c_clean] >= 3:
                                        self._off_hours_settled_codes.add(c_clean)
                        all_fetched_quotes.extend(quotes)

                        # 处理该批次中个别未返回行情的标的（自动记录并冷却）
                        missing_in_chunk = [c_c for _, c_c in req_params if c_c not in returned_codes]
                        for c_m in missing_in_chunk:
                            self._no_quote_counts[c_m] = self._no_quote_counts.get(c_m, 0) + 1
                            self._no_quote_last_attempt[c_m] = now_t
                            if self._no_quote_counts[c_m] >= 2:
                                self._unlisted_or_dormant_codes.add(c_m)

                        self.add_log(f"⚡ [TDX] 成功获取批次 {len(quotes)} 只标的行情 (耗时: {cost_ms:.1f}ms, 主站: {host_info})", level="INFO")
                    else:
                        # 批次未返回盘口数据（整批包含较多未上市代码或主站拒绝）：带 60s 日志防刷频
                        if not hasattr(self, "_last_batch_warn_time"):
                            self._last_batch_warn_time = {}
                        batch_key = codes_str[:25]
                        last_warn_t = self._last_batch_warn_time.get(batch_key, 0.0)
                        if now_t - last_warn_t > 60.0:
                            self._last_batch_warn_time[batch_key] = now_t
                            self.add_log(f"⚠️ [TDX] 批次 [{codes_str[:30]}...] 未返回盘口数据，尝试单只补拉并自动冷却", level="WARN")

                        for mkt, c_clean in req_params:
                            try:
                                single_q = self.api.get_security_quotes([(mkt, c_clean)])
                                if single_q and len(single_q) > 0:
                                    sq = single_q[0]
                                    sp = safe_float(sq.get("price", 0.0))
                                    slast = safe_float(sq.get("last_close", 0.0))
                                    if sp > 0 or slast > 0:
                                        all_fetched_quotes.extend(single_q)
                                        self._off_hours_cached_quotes[c_clean] = sq
                                        self._no_quote_counts[c_clean] = 0
                                        self._unlisted_or_dormant_codes.discard(c_clean)
                                        continue
                            except Exception:
                                pass
                            
                            # 单只拉取依然无行情/未上市：立即进入冷却，绝不重复轰炸
                            self._no_quote_counts[c_clean] = self._no_quote_counts.get(c_clean, 0) + 1
                            self._no_quote_last_attempt[c_clean] = now_t
                            if self._no_quote_counts[c_clean] >= 2:
                                self._unlisted_or_dormant_codes.add(c_clean)
                except Exception as e:
                    cost_ms = (time.time() - t_start) * 1000.0
                    self._record_request_feedback(cost_ms, is_error=True)
                    self.add_log(f"标的批次 [{codes_str[:30]}...] 行情获取异常: {e}", level="WARN")

        return cached_results + all_fetched_quotes

    def clear_stock_cache(self, code: str):
        """【🧹 彻底清理单股 TDX 行情缓存】清除 1 分钟 K 线内存缓存与盘后快照缓存"""
        c_clean = str(code).strip().zfill(6)
        with self._conn_lock:
            self._intraday_bars_cache.pop(c_clean, None)
            self._off_hours_cached_quotes.pop(c_clean, None)
            self._off_hours_settled_codes.discard(c_clean)
            self._no_quote_last_attempt.pop(c_clean, None)
            self._no_quote_counts.pop(c_clean, None)
            self._unlisted_or_dormant_codes.discard(c_clean)
        self.add_log(f"🧹 已强力清除标的 [{c_clean}] 的 TDX 内存 K 线与快照缓存！", level="INFO")



    def fetch_stock_snapshot(
        self,
        code: str,
        circulation_shares_wan: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        拉取单只股票的高精度秒级快照字典（包含开高低收、五档盘口、换手率、成交额、VWAP）
        """
        c_clean = str(code).strip().zfill(6)
        quotes = self.get_security_quotes_safe([c_clean])
        if not quotes:
            return {}

        q = quotes[0]
        trade_price = float(q.get("price", 0.0))
        open_price = float(q.get("open", trade_price))
        high_price = float(q.get("high", trade_price))
        low_price = float(q.get("low", trade_price))
        if low_price <= 1.0 or (trade_price > 5.0 and low_price < trade_price * 0.1):
            low_price = trade_price if trade_price > 0 else (open_price if open_price > 0 else 10.0)
        last_close = float(q.get("last_close", trade_price))
        vol = float(q.get("vol", 0.0))       # 单位：手 (100股)
        amount = float(q.get("amount", 0.0)) # 单位：元
        bid1_p = float(q.get("bid1", trade_price))
        bid1_v = float(q.get("bid_vol1", 0.0))
        ask1_p = float(q.get("ask1", trade_price))
        ask1_v = float(q.get("ask_vol1", 0.0))

        # 计算与修正 VWAP 均价 (元)
        if vol > 0 and amount > 0:
            calc_vwap = amount / (vol * 100.0)
            if trade_price > 0 and (trade_price * 0.7 <= calc_vwap <= trade_price * 1.3):
                vwap = round(calc_vwap, 2)
            else:
                vwap = round((open_price + high_price + low_price + trade_price) / 4.0, 2) if open_price > 0 else trade_price
        else:
            vwap = trade_price if trade_price > 0 else open_price

        # 动态获取该标的真实流通盘并计算换手率 (%)
        if circulation_shares_wan and circulation_shares_wan > 0:
            total_circ_shares = circulation_shares_wan * 10000.0
        else:
            total_circ_shares = self.get_circulation_shares(c_clean)

        if total_circ_shares > 0 and vol > 0:
            turnover_rate = round((vol * 100.0 / total_circ_shares) * 100.0, 2)
            turnover_rate = min(100.0, max(0.0, turnover_rate))
        else:
            turnover_rate = 0.0

        return {
            "code": c_clean,
            "open_price": open_price,
            "price": trade_price,
            "trade": trade_price,
            "high_price": high_price,
            "low_price": low_price,
            "last_close": last_close,
            "vwap": vwap,
            "volume": vol,
            "vol": vol,
            "amount": amount,
            "turnover_rate": turnover_rate,
            "turnover": turnover_rate,
            "bid1_price": bid1_p,
            "bid1": bid1_p,
            "bid1_vol": bid1_v,
            "ask1_price": ask1_p,
            "ask1": ask1_p,
            "ask1_vol": ask1_v,
            "server_time": time.strftime("%H:%M:%S")
        }

    def fetch_intraday_bars(self, code: str) -> pd.DataFrame:
        """
        从 TDX 极速拉取当日 1 分钟 K 线与分时走势全量数据 (包含 09:25 集合竞价、早盘全量分钟 Tick 走势、开高低收与换手率)
        """
        c_clean = str(code).strip().zfill(6)
        mkt = get_market_code(c_clean)
        t_start = time.time()

        # 1. 优先使用内存中已缓存的全量 240 条分时 K 线 (带时间戳与交易日校验，避免陈旧跨日数据)
        if not hasattr(self, '_intraday_bars_cache'):
            self._intraday_bars_cache = {}
        
        today_date_str = datetime.now().strftime("%Y-%m-%d")
        cached_entry = self._intraday_bars_cache.get(c_clean)
        if cached_entry is not None:
            if isinstance(cached_entry, tuple) and len(cached_entry) >= 2:
                cached_df, cache_ts, cache_day = cached_entry[0], cached_entry[1], cached_entry[2]
                # 在交易时段内缓存 2.5 秒，非交易时段且同一交易日内可长效复用
                is_fresh = (cache_day == today_date_str) and ((time.time() - cache_ts < 2.5) or (len(cached_df) >= 240))
                if is_fresh and cached_df is not None and not cached_df.empty and len(cached_df) >= 30:
                    return cached_df
            elif isinstance(cached_entry, pd.DataFrame) and not cached_entry.empty and len(cached_entry) >= 30:
                cached_df = cached_entry
            else:
                cached_df = None
        else:
            cached_df = None

        try:
            with self._conn_lock:
                if not self._is_connected or self.api is None:
                    if not self.connect():
                        return cached_df if cached_df is not None else pd.DataFrame()

                bars = None
                try:
                    bars = self.api.get_security_bars(7, mkt, c_clean, 0, 240)
                    if not bars or len(bars) < 30:
                        bars_8 = self.api.get_security_bars(8, mkt, c_clean, 0, 240)
                        if bars_8 and len(bars_8) > (len(bars) if bars else 0):
                            bars = bars_8
                except Exception:
                    bars = None

                if not bars or len(bars) < 30:
                    self._is_connected = False
                    if self.connect():
                        try:
                            bars = self.api.get_security_bars(7, mkt, c_clean, 0, 240)
                        except Exception:
                            bars = None

                # 若 K 线引擎拉取条数不足，触发 PyTDX 官方分时走势全量引擎 (get_minute_time_data / get_history_minute_time_data) 补齐 240 分钟全量走势
                if (not bars or len(bars) < 30) and self._is_connected and self.api is not None:
                    try:
                        min_data = self.api.get_minute_time_data(mkt, c_clean)
                        if not min_data or len(min_data) < 30:
                            today_int = int(datetime.now().strftime("%Y%m%d"))
                            min_data = self.api.get_history_minute_time_data(mkt, c_clean, today_int)
                        
                        if min_data and len(min_data) >= 30:
                            bars = []
                            today_prefix = datetime.now().strftime("%Y-%m-%d")
                            base_time = datetime.strptime(f"{today_prefix} 09:30", "%Y-%m-%d %H:%M")
                            for idx_m, md in enumerate(min_data):
                                p_val = float(md.get("price", 0.0))
                                v_val = float(md.get("vol", 0.0))
                                if p_val <= 0:
                                    continue
                                if idx_m < 120:
                                    t_curr = base_time + pd.Timedelta(minutes=idx_m+1)
                                else:
                                    t_curr = datetime.strptime(f"{today_prefix} 13:00", "%Y-%m-%d %H:%M") + pd.Timedelta(minutes=idx_m-120+1)
                                bars.append({
                                    "datetime": t_curr.strftime("%Y-%m-%d %H:%M"),
                                    "open": p_val,
                                    "close": p_val,
                                    "high": p_val,
                                    "low": p_val,
                                    "vol": v_val * 100.0, # 转换为股
                                    "amount": p_val * v_val * 100.0
                                })
                    except Exception as e_min:
                        self.add_log(f"TDX 分时全量引擎回补异常: {e_min}", level="WARN")

                if not bars:
                    return cached_df if cached_df is not None else pd.DataFrame()

                df = pd.DataFrame(bars)
                if df.empty:
                    return cached_df if cached_df is not None else pd.DataFrame()

                # 严格过滤只保留单个交易日的真实 K 线 (优先今日；若非交易日/盘后，严格只取最新单日数据，绝不串联多日)
                today_str = datetime.now().strftime("%Y-%m-%d")
                if "datetime" in df.columns:
                    df["date_str"] = df["datetime"].astype(str).str[:10]
                    df_today = df[df["date_str"] == today_str]
                    if df_today.empty:
                        # 严格只截取最新单日，杜绝多日 240 根混杂累加
                        latest_day = str(df["date_str"].iloc[-1])
                        df_today = df[df["date_str"] == latest_day]
                else:
                    df_today = df

                # 整理标准字段
                res_rows = []
                tot_circ_shares = self.get_circulation_shares(c_clean)
                cum_vol_shares = 0.0
                cum_amt = 0.0
                for _, r in df_today.iterrows():
                    dt = str(r.get("datetime", r.get("time", "")))
                    t_str = dt[-5:] if len(dt) >= 5 else dt
                    p = float(r.get("close", 0.0))
                    op = float(r.get("open", p))
                    hp = float(r.get("high", p))
                    lp = float(r.get("low", p))
                    if lp <= 1.0 or (p > 5.0 and lp < p * 0.1):
                        lp = p

                    vol_shares = float(r.get("vol", 0.0))
                    cum_vol_shares += vol_shares
                    amt = float(r.get("amount", 0.0))
                    cum_amt += amt

                    to_rate = 0.0
                    if tot_circ_shares > 0:
                        to_rate = round((cum_vol_shares / tot_circ_shares) * 100.0, 2)
                        to_rate = min(100.0, max(0.0, to_rate))

                    # 计算截止到当前分钟的全天真实累计 VWAP 均价与累计成交金额
                    if cum_vol_shares > 0 and cum_amt > 0:
                        vw = round(cum_amt / cum_vol_shares, 2)
                    else:
                        vw = p

                    res_rows.append({
                        "time": t_str,
                        "open": op,
                        "close": p,
                        "trade": p,
                        "price": p,
                        "high": hp,
                        "low": lp,
                        "vwap": vw,
                        "volume": cum_vol_shares / 100.0,
                        "vol": cum_vol_shares / 100.0,
                        "amount": cum_amt,
                        "turnover": to_rate,
                        "turnover_rate": to_rate
                    })

                df_res = pd.DataFrame(res_rows)
                if not df_res.empty:
                    df_res.set_index("time", inplace=True)
                    self._intraday_bars_cache[c_clean] = (df_res, time.time(), today_str) # 缓存到内存
                    cost_ms = (time.time() - t_start) * 1000.0
                    srv_name = self.best_server.get("name", "TDX行情") if hasattr(self, "best_server") and self.best_server else "TDX"
                    op_first = df_res.iloc[0].get("open", 0.0)
                    cl_last = df_res.iloc[-1].get("close", 0.0)
                    self.add_log(f"✅ 标的 [{c_clean}] 行情获取成功: 全量补齐 {len(df_res)} 条分时 K线/Tick (含 09:25 竞价今开: {op_first:.2f}元, 现价: {cl_last:.2f}元) (耗时: {cost_ms:.1f}ms, 服务器: {srv_name})", level="INFO")
                return df_res
        except Exception as e:
            logger.debug(f"TDX 获取 {c_clean} 分时 K 线异常: {e}")
            return pd.DataFrame()

    def fetch_multi_day_intraday_bars(self, code: str, days: int = 2) -> pd.DataFrame:
        """
        拉取最近 N 个交易日的全量分时 K 线数据 (包含 1日, 2日, 3日, 5日分时图)，按交易日拼接并计算每日 VWAP 均线与换手率
        """
        c_clean = str(code).zfill(6)
        try:
            mkt = get_market_code(c_clean)
            bars = None
            with self._conn_lock:
                if not self._is_connected or self.api is None:
                    if not self.connect():
                        return pd.DataFrame()
                try:
                    bars = self.api.get_security_bars(8, mkt, c_clean, 0, 800) or []
                    if days >= 4:
                        # 5 日分时需要约 1200 根 1 分钟 K 线，分两批获取并拼接
                        bars_prev = self.api.get_security_bars(8, mkt, c_clean, 800, 800) or []
                        if bars_prev:
                            bars = bars_prev + bars
                except Exception as e_b:
                    logger.debug(f"TDX get_security_bars 8 异常: {e_b}")
                    bars = None

                # 💡 若连接闲置超时被服务端切断或拉取为空，自动标记断开并立即重连重试！
                if not bars or len(bars) == 0:
                    self._is_connected = False
                    if self.connect():
                        try:
                            bars = self.api.get_security_bars(8, mkt, c_clean, 0, 800) or []
                            if days >= 4:
                                bars_prev = self.api.get_security_bars(8, mkt, c_clean, 800, 800) or []
                                if bars_prev:
                                    bars = bars_prev + bars
                        except Exception:
                            bars = None

            if not bars:
                return pd.DataFrame()

            df = pd.DataFrame(bars)
            if df.empty or "datetime" not in df.columns:
                return pd.DataFrame()

            df["date_str"] = df["datetime"].astype(str).str[:10]
            df["time_str"] = df["datetime"].astype(str).str[11:16]

            unique_dates = sorted(df["date_str"].unique())
            target_dates = unique_dates[-days:] if len(unique_dates) >= days else unique_dates

            df_filtered = df[df["date_str"].isin(target_dates)].copy()
            if df_filtered.empty:
                return pd.DataFrame()

            res_rows = []
            tot_circ_shares = self.get_circulation_shares(c_clean)
            cum_vol_shares = 0.0
            cum_amt = 0.0

            for d_str, group in df_filtered.groupby("date_str"):
                date_short = d_str[5:] # MM-DD

                for _, r in group.iterrows():
                    t_str = str(r.get("time_str", ""))
                    time_label = f"{date_short} {t_str}"
                    p = float(r.get("close", 0.0))
                    op = float(r.get("open", p))
                    hp = float(r.get("high", p))
                    lp = float(r.get("low", p))
                    if lp <= 1.0 or (p > 5.0 and lp < p * 0.1):
                        lp = p

                    vol_shares = float(r.get("vol", 0.0))
                    cum_vol_shares += vol_shares
                    amt = float(r.get("amount", 0.0))
                    cum_amt += amt

                    to_rate = 0.0
                    if tot_circ_shares > 0:
                        to_rate = round((cum_vol_shares / tot_circ_shares) * 100.0, 2)
                        to_rate = min(100.0, max(0.0, to_rate))

                    vw = round(cum_amt / cum_vol_shares, 2) if (cum_vol_shares > 0 and cum_amt > 0) else p

                    res_rows.append({
                        "time": time_label,
                        "date": d_str,
                        "time_only": t_str,
                        "open": op,
                        "close": p,
                        "trade": p,
                        "price": p,
                        "high": hp,
                        "low": lp,
                        "vwap": vw,
                        "volume": cum_vol_shares / 100.0,
                        "vol": cum_vol_shares / 100.0,
                        "amount": cum_amt,
                        "turnover": to_rate,
                        "turnover_rate": to_rate
                    })

            df_res = pd.DataFrame(res_rows)
            if not df_res.empty:
                df_res.set_index("time", inplace=True)
            return df_res
        except Exception as e:
            logger.debug(f"拉取 {c_clean} 多日分时数据异常: {e}")
            return pd.DataFrame()

    def fetch_kline_bars(self, code: str, category: str = "5m", count: int = 150) -> pd.DataFrame:
        """
        拉取不同周期的 K 线数据 (5m, 30m, 60m, day)，并计算 MA5, MA20, MA60, Bollinger 通道 (GG 通道) 与 Volume
        """
        c_clean = str(code).zfill(6)
        cat_str = str(category).lower().strip()
        is_120m = cat_str in ("120m", "120f", "120min", "2h", "120")
        if is_120m:
            cat_code = 3  # 从 60m 拉取两倍数量后聚合
            fetch_count = min(800, max(count * 2, 60))
        else:
            fetch_count = count
            cat_map = {
                "5m": 0, "5f": 0, "5min": 0,
                "15m": 1, "15f": 1, "15min": 1,
                "30m": 2, "30f": 2, "30min": 2,
                "60m": 3, "60f": 3, "60min": 3, "1h": 3,
                "day": 4, "d": 4, "日线": 4, "日k": 4, "日": 4,
                "week": 5, "w": 5, "周线": 5, "周k": 5, "周": 5,
                "month": 6, "m": 6, "月线": 6, "月k": 6, "月": 6,
                "1m": 8, "1f": 8, "1min": 8
            }
            cat_code = cat_map.get(cat_str, 3 if "60" in cat_str else 0)

        try:
            mkt = get_market_code(c_clean)
            bars = None
            with self._conn_lock:
                if not self._is_connected or self.api is None:
                    if not self.connect():
                        return pd.DataFrame()
                try:
                    bars = self.api.get_security_bars(cat_code, mkt, c_clean, 0, fetch_count)
                except Exception as e_k:
                    logger.debug(f"TDX get_security_bars {cat_code} 异常: {e_k}")
                    bars = None

                # 💡 若连接闲置超时被服务端切断或拉取为空，自动标记断开并立即重连重试！
                if not bars or len(bars) == 0:
                    self._is_connected = False
                    if self.connect():
                        try:
                            bars = self.api.get_security_bars(cat_code, mkt, c_clean, 0, fetch_count)
                        except Exception:
                            bars = None

            if not bars:
                return pd.DataFrame()

            df = pd.DataFrame(bars)
            if df.empty:
                return pd.DataFrame()

            # 若为 120m 周期，将每相邻两根 60m K 线精确聚合为一根标准 120m K 线
            if is_120m and len(df) >= 2:
                rows_120 = []
                offset = len(df) % 2
                for i in range(offset, len(df), 2):
                    b1 = df.iloc[i]
                    b2 = df.iloc[i + 1]
                    t_val = str(b2.get("datetime", b2.get("time", "")))
                    op_v = float(b1.get("open", 0.0))
                    hp_v = max(float(b1.get("high", 0.0)), float(b2.get("high", 0.0)))
                    lp_v = min(float(b1.get("low", 0.0)), float(b2.get("low", 0.0)))
                    cl_v = float(b2.get("close", 0.0))
                    vol_v = float(b1.get("vol", 0.0)) + float(b2.get("vol", 0.0))
                    amt_v = float(b1.get("amount", 0.0)) + float(b2.get("amount", 0.0))
                    rows_120.append({
                        "datetime": t_val,
                        "time": t_val,
                        "open": op_v,
                        "high": hp_v,
                        "low": lp_v,
                        "close": cl_v,
                        "vol": vol_v,
                        "amount": amt_v
                    })
                if rows_120:
                    df = pd.DataFrame(rows_120)

            if "datetime" in df.columns:
                df["time"] = df["datetime"].astype(str)
            elif "time" not in df.columns:
                df["time"] = [str(i) for i in range(len(df))]

            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)
            df["vol"] = df["vol"].astype(float)
            df["amount"] = df.get("amount", df["close"] * df["vol"] * 100.0).astype(float)

            # 技术指标计算: MA5, MA20, MA60, 布林通道 (Upper, Mid, Lower)
            df["ma5"] = df["close"].rolling(5, min_periods=1).mean()
            df["ma20"] = df["close"].rolling(20, min_periods=1).mean()
            df["ma60"] = df["close"].rolling(60, min_periods=1).mean()

            std20 = df["close"].rolling(20, min_periods=1).std().fillna(0)
            df["boll_mid"] = df["ma20"]
            df["boll_upper"] = df["boll_mid"] + 2.0 * std20
            df["boll_lower"] = df["boll_mid"] - 2.0 * std20

            # ⚡ 接入通达信自动通道 (Trend Channel) + 上涨支撑线 + 翻转线 + Fibonacci + 拐点启动信号
            try:
                from JSONData.tdx_data_Day import calc_trend_channel
                df = calc_trend_channel(df)
            except Exception as e_tc:
                logger.debug(f"calc_trend_channel 向量化通道计算异常: {e_tc}")

            # ⚡ 数据处理后单独调用内置神奇九转处理，不影响原有通道基础预处理逻辑
            try:
                from JSONData.tdx_data_Day import td_sequential_fast
                df = td_sequential_fast(df, lookback=4)
            except Exception as e_td:
                logger.debug(f"td_sequential_fast 神奇九转计算异常: {e_td}")

            df.set_index("time", inplace=True)
            return df
        except Exception as e:
            logger.debug(f"拉取 {c_clean} [{category}] K 线数据异常: {e}")
            return pd.DataFrame()

    def get_yesterday_ohlc(self, code: str) -> Dict[str, float]:
        """
        获取标的昨日日 K 线的真实 OHLC (昨开 open, 昨高 high, 昨低 low, 昨收 close)
        带 10s 内存缓存，毫秒级返回
        """
        c_clean = str(code).zfill(6)
        now_ts = time.time()

        if not hasattr(self, "_yesterday_ohlc_cache"):
            self._yesterday_ohlc_cache = {}

        cached = self._yesterday_ohlc_cache.get(c_clean)
        if cached and (now_ts - cached[1] < 10.0):
            return cached[0]

        res = {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
        try:
            df_daily = self.fetch_kline_bars(c_clean, category="day", count=5)
            if df_daily is not None and not df_daily.empty:
                today_str = datetime.now().strftime("%Y-%m-%d")
                last_row_date = str(df_daily.iloc[-1].get("datetime", df_daily.iloc[-1].get("time", "")))[:10]

                if last_row_date == today_str:
                    if len(df_daily) >= 2:
                        y_row = df_daily.iloc[-2]
                        res = {
                            "open": round(float(y_row.get("open", 0.0)), 2),
                            "high": round(float(y_row.get("high", 0.0)), 2),
                            "low": round(float(y_row.get("low", 0.0)), 2),
                            "close": round(float(y_row.get("close", 0.0)), 2),
                        }
                    else:
                        # 上市首日仅有今天 1 根日 K 线，无昨日真实 OHLC
                        res = {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
                elif len(df_daily) >= 1:
                    # 最后一根日 K 不是今天，说明今日 K 线尚未收盘落盘，取最后一根作为昨日日 K
                    y_row = df_daily.iloc[-1]
                    res = {
                        "open": round(float(y_row.get("open", 0.0)), 2),
                        "high": round(float(y_row.get("high", 0.0)), 2),
                        "low": round(float(y_row.get("low", 0.0)), 2),
                        "close": round(float(y_row.get("close", 0.0)), 2),
                    }
        except Exception as e:
            logger.debug(f"get_yesterday_ohlc 异常: {e}")

        self._yesterday_ohlc_cache[c_clean] = (res, now_ts)
        return res

    def calculate_rolling_velocity(self, code: str, price: float, last_close: float, now_ts: float) -> Tuple[float, str]:
        """
        【📈 工业级 1 分钟/3 分钟真实滑动窗口涨速引擎 & 状态机判定】
        彻底根治秒级单点差分乘以 60 造成的低价股/盘整股巨大噪声跳变（如苏宁环球 -10.2% 乱跳）。

        算法机制：
        1. 维护最近 180 秒的时序队列 deque([(t, price), ...], maxlen=60)；
        2. 清除 >180s 的过期采样点，并追加当前最新采样；
        3. 寻找与当前时间间隔最接近 60s (45s~90s) 的历史基准价格 P_base；
        4. 依据真实时间跨度计算标准 1 分钟净涨幅，不足 45s 时使用时间标准化带 20s 软阻尼防抖；
        5. 对低流动性买卖一档微小跳动应用 0.15% 物理死区过滤与 EMA (0.45) 平滑；
        6. 输出标准真实涨速 % 与具备实战周期的状态机标签 (🚀 极速拉升 / 🔥 强势推升 / ⚡ 稳步攀升 / ⏱️ 窄幅整理 / 🔻 震荡回踩 / ⚠️ 快速下挫 / ❄️ 极速跳水)。
        """
        c_clean = str(code).strip().zfill(6)
        if price <= 0 or last_close <= 0 or now_ts <= 0:
            return 0.0, "⏱️ 窄幅整理"

        if not hasattr(self, '_price_timeline_history'):
            self._price_timeline_history = {}
        if not hasattr(self, '_smoothed_velocity'):
            self._smoothed_velocity = {}
        if not hasattr(self, '_velocity_tags'):
            self._velocity_tags = {}

        if c_clean not in self._price_timeline_history:
            self._price_timeline_history[c_clean] = collections.deque(maxlen=60)

        history = self._price_timeline_history[c_clean]

        # 1. 淘汰超过 180 秒的历史旧点
        while history and (now_ts - history[0][0] > 180.0):
            history.popleft()

        # 2. 如果历史有点且时间戳异常（时间倒退或重复），重置
        if history and now_ts < history[-1][0]:
            history.clear()

        # 3. 将当前价格加入队列
        history.append((now_ts, price))

        # 4. 如果数据点不足 2 个或总跨度小于 5 秒，返回平稳 0.0%
        if len(history) < 2:
            tag = self._velocity_tags.get(c_clean, "⏱️ 窄幅整理")
            return self._smoothed_velocity.get(c_clean, 0.0), tag

        span = now_ts - history[0][0]
        if span < 5.0:
            tag = self._velocity_tags.get(c_clean, "⏱️ 窄幅整理")
            return self._smoothed_velocity.get(c_clean, 0.0), tag

        # 5. 寻找距今最接近 60 秒的基准点
        target_t = now_ts - 60.0
        best_p = history[0][1]
        best_dt = span

        min_diff = 9999.0
        for pt_t, pt_p in history:
            diff = abs(pt_t - target_t)
            if diff < min_diff:
                min_diff = diff
                best_p = pt_p
                best_dt = now_ts - pt_t

        # 6. 计算未经滤波的真实窗口涨速
        if best_dt >= 45.0:
            raw_vel = (price - best_p) / last_close * 100.0
        else:
            raw_vel = ((price - best_p) / last_close * 100.0) * (60.0 / max(best_dt, 20.0))

        # 7. 物理涨跌幅极值钳位 (主板 10%，创业板/科创板 20%，北交所 30%)
        if c_clean.startswith(('300', '301', '688')):
            max_limit = 20.0
        elif c_clean.startswith(('8', '4', '920')):
            max_limit = 30.0
        else:
            max_limit = 10.0
        raw_vel = max(-max_limit, min(max_limit, raw_vel))

        # 8. 死区过滤：价格微动绝对值小于 0.15% 视为买一卖一跳价噪声，归零
        if abs(raw_vel) < 0.15:
            raw_vel = 0.0

        # 9. EMA 指数平滑滤波 (α = 0.45)
        last_vel = self._smoothed_velocity.get(c_clean, raw_vel)
        smoothed_vel = 0.45 * raw_vel + 0.55 * last_vel
        if abs(smoothed_vel) < 0.15:
            smoothed_vel = 0.0

        final_vel = round(smoothed_vel, 1)
        self._smoothed_velocity[c_clean] = final_vel

        # 10. 周期状态机判定
        if final_vel >= 2.0:
            tag = "🚀 极速拉升"
        elif final_vel >= 0.8:
            tag = "🔥 强势推升"
        elif final_vel >= 0.3:
            tag = "⚡ 稳步攀升"
        elif final_vel <= -1.5:
            tag = "❄️ 极速跳水"
        elif final_vel <= -0.8:
            tag = "⚠️ 快速下挫"
        elif final_vel <= -0.3:
            tag = "🔻 震荡回踩"
        else:
            tag = "⏱️ 窄幅整理"

        self._velocity_tags[c_clean] = tag
        return final_vel, tag

    def calculate_segmented_velocity(
        self,
        code: str,
        price: float,
        open_price: float,
        last_close: float,
        vol: float,
        amount: float,
        now_ts: float,
        segment_mode: str = "30m"
    ) -> Dict[str, Any]:
        """
        【📈 交易时段分段（默认30分钟）价格/量能记忆与区间涨速引擎】

        特性：
        1. 自动根据当前时钟/行情时间划分 4 小时交易时段 (如 09:30~10:00, 10:00~10:30 等)；
        2. 自动记忆每个时段每个标的的第一笔数据 (base_price, base_vol, base_amount, first_seen_time)；
        3. 无论 09:30 正常开盘还是盘中中途启动 (如 10:15 启动)，自动匹配并锁定该时段的第一笔有效数据作为基准；
        4. 计算该时段内的真实净拉升幅度 (%) 与时段增量成交量 (手) / 成交额 (万元)；
        5. 输出标准化时段涨速、时段增量量能与实战状态标签，绝不因 1 分钱跳价发生噪音翻转！
        """
        c_clean = str(code).strip().zfill(6)
        if price <= 0 or last_close <= 0 or now_ts <= 0:
            return {
                "velocity_pct": 0.0,
                "velocity_tag": "⏱️ 窄幅横盘",
                "segment_key": "09:30~10:00",
                "segment_label": "👑 09:30~10:00 早盘冲刺定龙",
                "segment_base_price": price,
                "segment_vol_increment": 0.0,
                "segment_amount_wan": 0.0,
                "is_midway_init": False,
            }

        # 如果选择的是 60 秒滑动模式，直接回退调用 60 秒滑动算法
        if segment_mode == "60s":
            vel, tag = self.calculate_rolling_velocity(c_clean, price, last_close, now_ts)
            return {
                "velocity_pct": vel,
                "velocity_tag": tag,
                "segment_key": "60s_rolling",
                "segment_label": "⏱️ 60秒滑动窗口",
                "segment_base_price": price,
                "segment_vol_increment": 0.0,
                "segment_amount_wan": 0.0,
                "is_midway_init": False,
            }

        if not hasattr(self, '_segment_stock_cache'):
            self._segment_stock_cache = {}

        today_str = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d") if now_ts > 0 else datetime.now().strftime("%Y-%m-%d")
        seg_key, seg_label, seg_s_epoch, seg_e_epoch = get_trading_segment_info(now_ts, segment_mode)

        if c_clean not in self._segment_stock_cache:
            self._segment_stock_cache[c_clean] = {}

        code_cache = self._segment_stock_cache[c_clean]

        # 检查并清理非今日的过期缓存
        for k in list(code_cache.keys()):
            if code_cache[k].get("date") != today_str:
                del code_cache[k]

        # 确定本时段的基准数据 (第一笔有效数据)
        if seg_key not in code_cache:
            if (seg_key.startswith("09:30") or segment_mode == "day_open") and open_price > 0:
                base_p = open_price
            else:
                base_p = price

            base_v = vol if vol > 0 else 0.0
            base_amt = amount if amount > 0 else 0.0

            code_cache[seg_key] = {
                "base_price": base_p,
                "base_vol": base_v,
                "base_amount": base_amt,
                "first_seen_time": now_ts,
                "date": today_str,
                "is_midway_init": (now_ts - seg_s_epoch > 60.0) if seg_s_epoch > 0 else False
            }

        seg_base = code_cache[seg_key]
        base_price = float(seg_base["base_price"])
        base_vol = float(seg_base["base_vol"])
        base_amt = float(seg_base["base_amount"])

        # 计算时段内的真实净拉升幅度 (%)
        if last_close > 0 and base_price > 0:
            seg_vel_raw = (price - base_price) / last_close * 100.0
        else:
            seg_vel_raw = 0.0

        # 物理钳位 (主板 10%，双创 20%，北交所 30%)
        if c_clean.startswith(('300', '301', '688')):
            max_limit = 20.0
        elif c_clean.startswith(('8', '4', '920')):
            max_limit = 30.0
        else:
            max_limit = 10.0
        seg_vel = max(-max_limit, min(max_limit, seg_vel_raw))

        # 微小死区过滤 (绝对值 < 0.15% 视为震荡横盘)
        if abs(seg_vel) < 0.15:
            seg_vel = 0.0

        final_vel = round(seg_vel, 1)

        # 计算时段内的增量成交量 (手) 与增量成交额 (万元)
        vol_inc = max(0.0, vol - base_vol) if vol >= base_vol else 0.0
        amt_inc_wan = round(max(0.0, amount - base_amt) / 10000.0, 1) if amount >= base_amt else 0.0

        # 状态机判定
        if final_vel >= 2.0:
            tag = "🚀 极速拉升"
        elif final_vel >= 0.8:
            tag = "🔥 强势推升"
        elif final_vel >= 0.3:
            tag = "⚡ 稳步走高"
        elif final_vel <= -1.5:
            tag = "❄️ 深度跳水"
        elif final_vel <= -0.8:
            tag = "⚠️ 明显走弱"
        elif final_vel <= -0.3:
            tag = "🔻 震荡回踩"
        else:
            tag = "⏱️ 窄幅横盘"

        return {
            "velocity_pct": final_vel,
            "velocity_tag": tag,
            "segment_key": seg_key,
            "segment_label": seg_label,
            "segment_base_price": base_price,
            "segment_vol_increment": vol_inc,
            "segment_amount_wan": amt_inc_wan,
            "is_midway_init": seg_base.get("is_midway_init", False),
        }

    def fetch_multi_stock_alpha_quotes(
        self,
        codes: List[str],
        sector_map: Optional[Dict[str, str]] = None,
        multi_period_cache: Optional[Dict[str, Any]] = None,
        name_map: Optional[Dict[str, str]] = None,
        segment_mode: str = "30m",
        raw_quotes: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        批量拉取多只股票的 TDX 高频盘口数据，并计算量比爆发力、分时 VWAP 偏离、
        买卖盘口承接力、分时进攻斜率以及【三维买点定位】(领涨龙头/先锋突破/VWAP回踩/跟风)。

        :param codes: 股票代码列表，例如 ['300570', '688167', '603083']
        :param sector_map: 代码到所属强势板块的映射 {code: sector_name}
        :param multi_period_cache: 底层多日底蕴特征 {code: {dff, dff2, dff3, rank, perc3d...}}
        :param name_map: 代码到名称的映射 {code: name}
        :param segment_mode: 交易时段分段模式 ('30m', '15m', '60m', 'day_open', '60s')
        :param raw_quotes: 可选的预提取原始盘口列表，若提供则跳过网络获取
        :return: 包含完整 Alpha 动量与买点指引的字典列表，按 alpha_score 降序排列
        """
        if not codes:
            return []

        quotes = raw_quotes if raw_quotes is not None else self.get_security_quotes_safe(codes)
        if not quotes:
            return []

        sector_map = sector_map or {}
        multi_period_cache = multi_period_cache or {}
        name_map = name_map or {}

        now_ts = time.time()
        # 1. 整理盘口并计算基础分时指标
        parsed_items = []
        for q in quotes:
            code_str = str(q.get("code", "")).strip().zfill(6)
            if not code_str:
                continue

            price_raw = float(q.get("price", 0.0) or 0.0)
            bid1_p = float(q.get("bid1", 0.0) or 0.0)
            ask1_p = float(q.get("ask1", 0.0) or 0.0)
            open_p_raw = float(q.get("open", 0.0) or 0.0)
            price = price_raw if price_raw > 0 else (bid1_p if bid1_p > 0 else (open_p_raw if open_p_raw > 0 else ask1_p))
            open_p = open_p_raw if open_p_raw > 0 else price
            high_p = float(q.get("high", price) or price)
            low_p = float(q.get("low", price) or price)
            if low_p <= 1.0 or (price > 5.0 and low_p < price * 0.1):
                low_p = price if price > 0 else (open_p if open_p > 0 else 10.0)
            last_close = float(q.get("last_close", price) or price)
            vol = float(q.get("vol", 0.0))       # 手
            amount = float(q.get("amount", 0.0)) # 元
            cur_vol = float(q.get("cur_vol", 0.0))
            b_vol = float(q.get("b_vol", 0.0))
            s_vol = float(q.get("s_vol", 0.0))

            # 涨幅 %
            pct = round((price - last_close) / last_close * 100.0, 2) if last_close > 0 else 0.0

            # 1. 交易时段分段（默认30分钟）价格/量能记忆与区间涨速引擎
            seg_res = self.calculate_segmented_velocity(
                code=code_str,
                price=price,
                open_price=open_p,
                last_close=last_close,
                vol=vol,
                amount=amount,
                now_ts=now_ts,
                segment_mode=segment_mode
            )
            velocity_pct = seg_res["velocity_pct"]
            velocity_tag = seg_res["velocity_tag"]
            segment_key = seg_res["segment_key"]
            segment_label = seg_res["segment_label"]
            segment_base_price = seg_res["segment_base_price"]
            segment_vol_inc = seg_res["segment_vol_increment"]
            segment_amt_wan = seg_res["segment_amount_wan"]

            # 日内 VWAP (元)
            if vol > 0 and amount > 0:
                calc_vwap = amount / (vol * 100.0)
                if price > 0 and (price * 0.7 <= calc_vwap <= price * 1.3):
                    vwap = round(calc_vwap, 2)
                else:
                    vwap = round((open_p + high_p + low_p + price) / 4.0, 2) if open_p > 0 else price
            else:
                vwap = price if price > 0 else open_p

            # VWAP 偏离度 % (现价相对日内均价的偏离，正表示在均线上方强势)
            vwap_dev_pct = round((price - vwap) / vwap * 100.0, 2) if vwap > 0 else 0.0

            # 2. 五档买卖盘量能深度与主力追买/追卖意图判定
            bid_vol_sum = 0.0
            ask_vol_sum = 0.0
            for i in range(1, 6):
                bid_vol_sum += float(q.get(f"bid_vol{i}", 0.0) or 0.0)
                ask_vol_sum += float(q.get(f"ask_vol{i}", 0.0) or 0.0)

            total_depth = bid_vol_sum + ask_vol_sum
            bid_pressure = round((bid_vol_sum / total_depth) * 100.0, 1) if total_depth > 0 else 50.0
            taker_buy_ratio = round((b_vol / (b_vol + s_vol)) * 100.0, 1) if (b_vol + s_vol > 0) else 50.0

            # 💡 竞价单量拟合与真金白银测算 (09:15~09:30)
            bid1_v = float(q.get("bid_vol1", 0.0) or 0.0)
            ask1_v = float(q.get("ask_vol1", 0.0) or 0.0)
            bidding_vol = vol if vol > 0 else (bid1_v if bid1_v > 0 else ask1_v)
            bidding_amt = bidding_vol * 100.0 * price if (bidding_vol > 0 and price > 0) else 0.0
            bidding_amt_wan = round(bidding_amt / 10000.0, 1)
            bidding_amt_yi = round(bidding_amt / 1e8, 3)

            # 流通股本与基准日均量 (以流通盘 2% 估算基准全天量)
            circ_shares = self.get_circulation_shares(code_str)
            benchmark_daily_vol = (circ_shares / 100.0) * 0.02 if circ_shares > 0 else 50000.0
            # 竞价单量相对日均量拟合比 (0.15 表示仅竞价单量就达到全天日均量的 15%+)
            bidding_fit_ratio = round(bidding_vol / benchmark_daily_vol, 2) if benchmark_daily_vol > 0 else 0.0

            # 多日特征与多日突破判断 (支持 lasth1d / lasth2d / lasth3d / high4 / max5，新股保护 issue_price 发行价)
            mp_info = multi_period_cache.get(code_str, {})
            name_curr = name_map.get(code_str, q.get("name", code_str))
            # 权威判断是否为首日新股（对接 IntradayStrategyEngine 权威 SSOT，杜绝按 920 或模糊 N 误判）
            is_first_day = False
            try:
                from ats.intraday_strategy_engine import IntradayStrategyEngine
                is_first_day = bool(IntradayStrategyEngine.get_instance().is_stock_first_listing_day(code_str))
            except Exception:
                pass
            if not is_first_day:
                mp_st = str(mp_info.get("status", "")).strip()
                nm_str = str(name_curr).strip()
                if ("首日" in mp_st) or (mp_st == "今日上市") or (nm_str.startswith("N") and mp_st in ("", "首日", "今日上市", "首日(N)", "首日上市")):
                    is_first_day = True
            issue_p = float(mp_info.get("issue_price", 0.0) or q.get("issue_price", 0.0) or 0.0)

            lasth1d = float(mp_info.get("lasth1d", mp_info.get("last_high", 0.0)) or 0.0)
            lasth2d = float(mp_info.get("lasth2d", 0.0) or 0.0)
            lasth3d = float(mp_info.get("lasth3d", 0.0) or 0.0)
            high4 = float(mp_info.get("high4", 0.0) or 0.0)
            max5 = float(mp_info.get("max5", mp_info.get("hmax", mp_info.get("lasth5d", mp_info.get("high5", 0.0)))) or 0.0)

            # 💡 精确获取最近 2 日、最近 3 日与 5 日平台高点 (排除 <=0 异常值)
            valid_2d = [v for v in (lasth1d, lasth2d) if v > 0]
            max_2d = max(valid_2d) if valid_2d else 0.0

            valid_3d = [v for v in (lasth1d, lasth2d, lasth3d) if v > 0]
            max_3d = max(valid_3d) if valid_3d else 0.0

            valid_5d = [v for v in (lasth1d, lasth2d, lasth3d, high4, max5) if v > 0]
            max_5d = max(valid_5d) if valid_5d else 0.0

            # 多日有效阻力高点平台 (依次取 max_5d -> max_3d -> max_2d)
            benchmark_high = max_5d if max_5d > 0 else (max_3d if max_3d > 0 else max_2d)

            dff = float(mp_info.get("dff", 0.0) or 0.0)
            dff2 = float(mp_info.get("dff2", 0.0) or 0.0)
            dff3 = float(mp_info.get("dff3", 0.0) or 0.0)
            rank_val = int(mp_info.get("rank", mp_info.get("Rank", 999)) or 999)
            perc3d = float(mp_info.get("perc3d", 0.0) or 0.0)
            per1d = float(mp_info.get("per1d", 0.0) or 0.0)
            per2d = float(mp_info.get("per2d", 0.0) or 0.0)
            ma20_val = float(mp_info.get("ma20d", mp_info.get("ma20", 0.0)) or 0.0)
            ch_supp_val = float(mp_info.get("ch_supp", mp_info.get("ch_lower", 0.0)) or 0.0)

            is_bidding_breakout = False
            breakout_level = ""
            if not is_first_day:
                if price > 0 and max_5d > 0 and price >= max_5d - 0.01:
                    is_bidding_breakout = True
                    breakout_level = "5日高点"
                elif price > 0 and max_3d > 0 and price >= max_3d - 0.01:
                    is_bidding_breakout = True
                    breakout_level = "3日高点"
                elif price > 0 and max_2d > 0 and price >= max_2d - 0.01:
                    is_bidding_breakout = True
                    breakout_level = "2日高点"
                elif pct >= 3.0 and (dff2 >= 8.0 or dff3 >= 15.0):
                    is_bidding_breakout = True
                    breakout_level = "多头加速"

            # ── 💡 开盘即最低 (极小下影) 与跳空缺口加速结构量化计算 ──
            yesterday_high = lasth1d if lasth1d > 0 else last_close

            # 1. 开盘价即最低价 / 极小下影加速 (Open is Low)
            low_diff_pct = round((open_p - low_p) / open_p * 100.0, 3) if open_p > 0 else 999.0
            # 开盘即最低或差异极其微小 (下影 <= 1.5分钱 或 <= 0.15% 差异率，且非大幅低开)
            is_open_low_accel = bool(open_p > 0 and low_p > 0 and (low_p >= open_p - 0.015 or low_diff_pct <= 0.15) and (open_p >= last_close * 0.98))

            # 2. 跳空高开且留有跳空缺口加速 (Gap-Up Acceleration)
            # 条件：跳空高开 (高开 >= 0.8%) 且日内最低价始终运行在昨收与昨日最高之上 (未回补缺口)
            open_jump_pct = round((open_p - last_close) / last_close * 100.0, 2) if last_close > 0 else 0.0
            is_gap_accel = bool(open_jump_pct >= 0.8 and low_p > last_close and (yesterday_high <= 0 or low_p >= yesterday_high - 0.015))

            # 3. 双加速结构 (Dual Acceleration: 跳空高开 + 开盘即最低)
            is_dual_accel = bool(is_open_low_accel and is_gap_accel)

            accel_tag = ""
            if is_dual_accel:
                accel_tag = "👑双加速"
            elif is_open_low_accel:
                accel_tag = "⚡光脚加速"
            elif is_gap_accel:
                accel_tag = "🚀缺口加速"

            # 新股相对发行价溢价评估 (保护发行价，估值未透支判定)
            ipo_premium_pct = round((price - issue_p) / issue_p * 100.0, 1) if (is_first_day and issue_p > 0 and price > 0) else pct
            is_ipo_valuation_healthy = (ipo_premium_pct <= 220.0) if is_first_day else True

            # 盘口主力行为与集合竞价意图深度分析 (自适应识别竞价时态与严苛真龙过滤)
            now_hhmm = time.strftime("%H:%M")
            is_clock_bidding = ("09:15" <= now_hhmm < "09:30")
            is_data_bidding = (price_raw <= 0.0 or (vol <= 0.0 and amount <= 0.0))
            is_bidding_session = is_clock_bidding or is_data_bidding

            is_bidding_0915_0920 = ("09:15" <= now_hhmm < "09:20")
            is_bidding_0920_0925 = ("09:20" <= now_hhmm <= "09:25") or (is_data_bidding and not is_clock_bidding)
            is_bidding_0925_0930 = ("09:25" < now_hhmm < "09:30")

            if is_bidding_session:
                if is_bidding_0915_0920:
                    # ── A. 09:15~09:20 试撮合可撤单阶段 ──
                    if pct >= 9.5 and bid_pressure >= 85.0:
                        order_intent = "👑 竞价试盘一字"
                        intent_score = 90
                    elif pct >= 4.0 and (bid_pressure >= 75.0 or bidding_amt_yi >= 0.15):
                        order_intent = "⚡ 试撮合抢筹"
                        intent_score = 80
                    elif pct >= 3.0 and (bid_pressure <= 45.0 or bidding_amt_wan < 100.0):
                        order_intent = "⚠️ 虚挂测盘"
                        intent_score = 25
                    elif pct <= -3.0:
                        order_intent = "🧱 竞价低开试盘"
                        intent_score = 20
                    else:
                        order_intent = "⏱️ 竞价常规博弈"
                        intent_score = 50

                elif is_bidding_0920_0925 or (is_data_bidding and not is_clock_bidding):
                    # ── B. 09:20~09:25 不可撤单真实申报阶段 (黄金定龙/大普微爆量突破/N华大首日真金抢筹强过滤) ──
                    if is_first_day and (bidding_amt_wan >= 800.0 or bidding_amt_yi >= 0.08) and is_ipo_valuation_healthy:
                        # 💎 N华大模式：首日新股不可撤单阶段真金白银千万级抢筹，发行价估值保护未透支，09:25最佳上车点
                        order_intent = "💎 新股首日真金抢筹"
                        intent_score = 100
                    elif is_bidding_breakout and (bidding_amt_yi >= 0.3 or bidding_fit_ratio >= 0.20) and pct >= 4.0 and bid_pressure >= 75.0:
                        # 💎 大普微模式：不可撤单重金爆量突破多日高点(max5/high4/lasth2d/lasth1d)，全市场每早仅极少数
                        order_intent = "💎 竞价爆量突破"
                        intent_score = 100
                    elif pct >= 9.5 and (ask_vol_sum == 0 or bid_pressure >= 80.0 or bidding_amt_yi >= 0.3):
                        order_intent = "👑 竞价一字顶格"
                        intent_score = 98
                    elif (4.0 <= pct < 9.5) and (bidding_amt_yi >= 0.15 and bid_pressure >= 78.0):
                        order_intent = "🚀 竞价真金抢筹"
                        intent_score = 94
                    elif (pct >= 3.5) and (perc3d <= 1.0 or dff2 >= 6.0) and (bidding_amt_yi >= 0.1 or bid_pressure >= 70.0):
                        order_intent = "🔥 弱转强超预期"
                        intent_score = 90
                    elif pct >= 3.0 and (bidding_amt_wan < 150.0 or bid_pressure <= 45.0):
                        order_intent = "⚠️ 竞价缩量诱多"
                        intent_score = 15
                    elif pct <= -3.0 and bid_pressure <= 35.0:
                        order_intent = "🧱 竞价大幅低开"
                        intent_score = 15
                    else:
                        order_intent = "⏱️ 竞价常规博弈"
                        intent_score = 50

                else:
                    # ── C. 09:25~09:30 定盘静默阶段 ──
                    if is_first_day and (bidding_amt_wan >= 800.0 or bidding_amt_yi >= 0.08) and (pct <= 220.0):
                        order_intent = "💎 新股定盘真金抢筹"
                        intent_score = 100
                    elif is_bidding_breakout and (bidding_amt_yi >= 0.3 or bidding_fit_ratio >= 0.20) and pct >= 4.0:
                        order_intent = "💎 定盘爆量突破"
                        intent_score = 100
                    elif pct >= 9.5 and (bidding_amt_yi >= 0.2 or bid_pressure >= 80.0):
                        order_intent = "🔒 竞价一字定盘"
                        intent_score = 98
                    elif pct >= 4.0 and (bidding_amt_yi >= 0.15 or bid_pressure >= 75.0):
                        order_intent = "🔒 定盘真金抢筹"
                        intent_score = 92
                    elif pct >= 3.0 and (bidding_amt_wan < 150.0 or bid_pressure <= 45.0):
                        order_intent = "⚠️ 定盘缩量诱多"
                        intent_score = 15
                    else:
                        order_intent = "⏱️ 竞价常规博弈"
                        intent_score = 50
            else:
                # ── D. 连续撮合交易时段 (09:30~15:00) ──
                if pct >= 9.8 and (ask_vol_sum == 0 or bid_pressure > 85.0):
                    order_intent = "🔒 封板抢筹"
                    intent_score = 95
                elif taker_buy_ratio >= 58.0 or (price >= high_p - 0.02 and bid_pressure >= 55.0):
                    order_intent = "🔥 主动扫买"
                    intent_score = 85
                elif taker_buy_ratio <= 42.0 and bid_pressure <= 45.0:
                    order_intent = "⚠️ 主动砸盘"
                    intent_score = 30
                elif bid_pressure >= 65.0:
                    order_intent = "🛡️ 大单托底"
                    intent_score = 75
                elif bid_pressure <= 35.0:
                    order_intent = "🧱 大单压盘"
                    intent_score = 40
                else:
                    order_intent = "⚖️ 均衡博弈"
                    intent_score = 50

            # 3. 换手率计算 (100% 对齐通达信流通盘换手，自动过滤成交额异常大数)
            mp_info = multi_period_cache.get(code_str, {})
            turnover_val = float(mp_info.get("turnover", 0.0) or 0.0)
            if (turnover_val <= 0 or turnover_val > 100.0) and vol > 0:
                circ_shares = self.get_circulation_shares(code_str)
                if circ_shares > 0:
                    turnover_val = round((vol * 100.0 / circ_shares) * 100.0, 2)
            turnover_val = min(100.0, max(0.0, turnover_val))

            # 4. 真实量比计算 (若外部传入真实量比优先使用，否则结合开盘分钟与成交量计算)
            raw_vr = mp_info.get("vol_ratio", 0.0)
            if raw_vr and float(raw_vr) > 0 and float(raw_vr) != 1.8:
                vol_ratio_val = round(float(raw_vr), 2)
            elif vol > 0:
                # 依据当日总成交手与基准均量计算量比 (以流通盘0.5%为1倍量基准)
                circ_s = self.get_circulation_shares(code_str)
                benchmark_daily_vol = (circ_s / 100.0) * 0.02 # 2% 基准换手
                if benchmark_daily_vol > 0:
                    vol_ratio_val = round(max(0.2, min(30.0, vol / benchmark_daily_vol)), 2)
                else:
                    vol_ratio_val = 1.0
            else:
                vol_ratio_val = 1.0

            # 多日特征
            dff = float(mp_info.get("dff", 0.0) or 0.0)
            dff2 = float(mp_info.get("dff2", 0.0) or 0.0)
            dff3 = float(mp_info.get("dff3", 0.0) or 0.0)
            rank_val = int(mp_info.get("rank", mp_info.get("Rank", 999)) or 999)
            perc3d = float(mp_info.get("perc3d", 0.0) or 0.0)

            # 分时拉升攻角评分 (0 ~ 100)
            pos_in_day = (price - low_p) / (high_p - low_p) if (high_p > low_p) else 0.5
            slope_score = 40.0
            if vwap_dev_pct > 0:
                slope_score += min(25.0, vwap_dev_pct * 8.0)
            if pos_in_day > 0.8:
                slope_score += 15.0
            if bid_pressure > 60.0:
                slope_score += min(15.0, (bid_pressure - 50.0) * 0.4)
            if pct > 3.0:
                slope_score += min(15.0, pct * 1.5)
            slope_score = round(min(100.0, max(10.0, slope_score)), 1)

            parsed_items.append({
                "code": code_str,
                "name": name_map.get(code_str, q.get("name", code_str)),
                "sector": sector_map.get(code_str, "重点关注"),
                "price": price,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "last_close": last_close,
                "pct": pct,
                "velocity_pct": velocity_pct,
                "velocity_tag": velocity_tag,
                "segment_key": segment_key,
                "segment_label": segment_label,
                "segment_base_price": segment_base_price,
                "segment_vol_inc": segment_vol_inc,
                "segment_amt_wan": segment_amt_wan,
                "vwap": vwap,
                "vwap_dev_pct": vwap_dev_pct,
                "vol": vol,
                "amount": amount,
                "bid1": float(q.get("bid1", price)),
                "ask1": float(q.get("ask1", price)),
                "bid_vol_sum": bid_vol_sum,
                "ask_vol_sum": ask_vol_sum,
                "bid_pressure": bid_pressure,
                "order_intent": order_intent,
                "bidding_vol": bidding_vol,
                "bidding_amt_wan": bidding_amt_wan,
                "bidding_amt_yi": bidding_amt_yi,
                "bidding_fit_ratio": bidding_fit_ratio,
                "is_bidding_breakout": is_bidding_breakout,
                "breakout_level": breakout_level,
                "turnover": turnover_val,
                "vol_ratio": vol_ratio_val,
                "slope_score": slope_score,
                "dff": dff,
                "dff2": dff2,
                "dff3": dff3,
                "rank": rank_val,
                "perc3d": perc3d,
                "per1d": per1d,
                "per2d": per2d,
                "ma20": ma20_val,
                "ch_supp": ch_supp_val,
                "max_2d": max_2d,
                "max_3d": max_3d,
                "max_5d": max_5d,
                "is_open_low_accel": is_open_low_accel,
                "is_gap_accel": is_gap_accel,
                "is_dual_accel": is_dual_accel,
                "low_diff_pct": low_diff_pct,
                "open_jump_pct": open_jump_pct,
                "accel_tag": accel_tag,
                "extra_vals": mp_info.get("extra_vals", {}),
            })

        # 2. 板块内领涨与多维买点统一智能分拣
        # 按板块分组统计最高涨幅、领跑者与板块共振红盘家数
        sector_max_pct = {}
        sector_leader_code = {}
        sector_positive_count = {}
        sector_total_count = {}
        for it in parsed_items:
            sec = it["sector"]
            sector_total_count[sec] = sector_total_count.get(sec, 0) + 1
            if it["pct"] > 0:
                sector_positive_count[sec] = sector_positive_count.get(sec, 0) + 1
            if sec not in sector_max_pct or it["pct"] > sector_max_pct[sec]:
                sector_max_pct[sec] = it["pct"]
                sector_leader_code[sec] = it["code"]

        results = []
        for it in parsed_items:
            code = it["code"]
            pct = it["pct"]
            vwap = it["vwap"]
            vwap_dev = it["vwap_dev_pct"]
            price = it["price"]
            vol_r = it["vol_ratio"]
            dff = it["dff"]
            dff2 = it["dff2"]
            dff3 = it["dff3"]
            slope = it["slope_score"]
            bid_p = it["bid_pressure"]
            order_intent = it["order_intent"]
            b_amt_yi = it.get("bidding_amt_yi", 0.0)
            b_amt_wan = it.get("bidding_amt_wan", 0.0)
            b_fit_r = it.get("bidding_fit_ratio", 0.0)
            is_breakout = it.get("is_bidding_breakout", False)
            b_level = it.get("breakout_level", "")
            turnover = it["turnover"]
            sec = it["sector"]
            max_sec_p = sector_max_pct.get(sec, pct)
            is_sec_leader = (code == sector_leader_code.get(sec, ""))

            # 是否多日多头底座扎实 (2D/3D 加速)
            has_base = (dff2 > 0.0 or dff3 > 0.0)

            per1d = it.get("per1d", 0.0)
            per2d = it.get("per2d", 0.0)
            ma20_val = it.get("ma20", 0.0)
            ch_supp_val = it.get("ch_supp", 0.0)
            max_2d = it.get("max_2d", 0.0)
            max_5d = it.get("max_5d", 0.0)

            # 💡 1. 计算弱转强反差动能 (Reversal Differential)
            reversal_diff = round(pct - per1d, 2)
            it["reversal_diff"] = reversal_diff

            # 💡 2. 获取该板块对应的基准 ETF 趋势结构与共振分析
            etf_engine = get_sector_etf_engine()
            etf_trend_info = etf_engine.get_stock_sector_etf_trend(code, sec)
            is_etf_up = etf_trend_info.get("is_trend_up", False)
            is_etf_down = etf_trend_info.get("is_down_trend", False)
            etf_bonus = float(etf_trend_info.get("trend_score_bonus", 0.0))
            etf_name = str(etf_trend_info.get("etf_name", ""))
            etf_gain = float(etf_trend_info.get("gain_60d", 0.0))
            etf_supp_p = float(etf_trend_info.get("supp_p", 0.0))
            etf_reversal_p = float(etf_trend_info.get("reversal_p", 0.0))
            etf_channel_score = float(etf_trend_info.get("channel_score", 50.0))
            etf_gain_5d = float(etf_trend_info.get("gain_5d", 0.0))
            sec_res_count = sector_positive_count.get(sec, 0)

            it["etf_name"] = etf_name
            it["etf_gain"] = etf_gain
            it["etf_trend"] = etf_trend_info.get("trend_grade", "")
            it["etf_supp_p"] = etf_supp_p
            it["etf_reversal_p"] = etf_reversal_p
            it["etf_channel_score"] = etf_channel_score
            it["etf_gain_5d"] = etf_gain_5d

            # 💡 3. 检查是否属于割肉/止损标的主升确认回补
            reentry_tracker = get_reentry_tracker()
            reentry_info = reentry_tracker.check_reentry_signal(
                code=code,
                current_price=price,
                ma20=ma20_val,
                ch_supp=ch_supp_val,
                high_2d=max_2d,
                pct=pct,
                is_bidding=is_bidding_session
            )
            is_reentry = reentry_info.get("is_reentry", False)

            # ── 💡 统一多模块智能阿尔法分拣决策 (集合竞价高开竞速与盘中连续撮合买点) ──
            if is_bidding_session:
                if "新股" in order_intent and "抢筹" in order_intent:
                    # 💎 新股首日真金抢筹：N华大模式 (首日新股千万级抢筹 + 溢价合理 + 09:25黄金上车点)
                    buy_type = "💎 首日真金抢筹"
                    buy_tag = "IPO_BID_SURGE"
                    buy_zone = f"{price:.2f}"
                    stop_loss = round(price * 0.94, 2)
                    reason = f"首日新股真金白银巨资抢筹 (竞价{b_amt_wan:.0f}万/现价{price:.2f}), 估值合理未透支, 09:25黄金上车点 (防开盘极速脉冲)"
                    type_priority = 99
                elif "爆量突破" in order_intent or (is_breakout and b_amt_yi >= 0.2):
                    # 💎 竞价爆量突破龙：大普微模式 (不可撤单重金爆量 + 跳空跨过 2D/3D/5D 高点)
                    buy_type = "💎 爆量突破"
                    buy_tag = "BID_BREAKOUT"
                    buy_zone = f"{price:.2f}"
                    stop_loss = round(price * 0.96, 2)
                    reason = f"不可撤单阶段重金爆量抢筹 (竞价{b_amt_yi:.2f}亿/拟合比{b_fit_r:.1f}x), 跨越{b_level or '多日高点'}, 顶级龙头起爆"
                    type_priority = 99
                elif (price > last_close and max_2d > 0 and price >= max_2d - 0.015 and (pct >= 2.0 or b_amt_wan >= 1000.0)):
                    # 👑 竞价破顶：易点天下/四方精创模式 (连续回调后，竞价直接跳空破前高红线，09:25挂单锁死成本底座防诱多回落)
                    buy_type = "👑 竞价破顶"
                    buy_tag = "BID_BREAKOUT"
                    buy_zone = f"{price:.2f} (09:25前直接挂单)"
                    stop_loss = round(max(max_2d * 0.985, last_close), 2)
                    reason = f"连续回调后竞价高开破前高红线({max_2d:.2f}元), 跨越洗盘高点, 09:25前挂单锁死成本底座(防冲高诱多回落)"
                    type_priority = 100
                elif "一字" in order_intent or (pct >= 9.5 and bid_p >= 75.0):
                    buy_type = "👑 竞价一字"
                    buy_tag = "BID_LIMIT"
                    buy_zone = f"{price:.2f}"
                    stop_loss = round(price * 0.95, 2)
                    reason = f"集合竞价一字顶格封板 (竞价金额{b_amt_yi:.2f}亿, 买盘压强{bid_p:.0f}%), {order_intent}"
                    type_priority = 100
                elif is_reentry:
                    # 💎 割肉反转回补：建仓早割肉后，回踩企稳确认主升结构，09:25直接挂单补回
                    buy_type = reentry_info["buy_type"]
                    buy_tag = "RE_ENTRY_BUY"
                    buy_zone = f"{price:.2f} (09:25前挂单锁定成本底座)"
                    stop_loss = reentry_info["stop_loss"]
                    reason = reentry_info["reason"]
                    if is_etf_up:
                        reason += f" | {etf_name}大级别趋势主升(+{etf_gain:.1f}%)"
                    type_priority = 98
                elif (per1d <= -1.0 and pct >= -0.5 and reversal_diff >= 2.5 and (perc3d >= 8.0 or dff2 >= 4.0 or dff3 >= 8.0 or max_5d > 0 or has_base or bid_p >= 50.0 or reversal_diff >= 4.0)):
                    # 👑 弱转强起爆：柏星龙/恒盛能源模式 (前期强势异动洗盘后，早竞价平开/高开弱转强起爆，09:25前挂单锁死成本底座)
                    buy_type = "👑 弱转强起爆"
                    buy_tag = "BID_REVERSAL_LAUNCH"
                    buy_zone = f"{price:.2f} (09:25前直接挂单锁底座)"
                    stop_loss = round(price * 0.96, 2)
                    reason = f"前期强势回调后早竞价弱转强起爆 (昨日{per1d:+.1f}%,今日竞价{pct:+.1f}%,反差+{reversal_diff:.1f}%), 09:25前挂单锁死成本底座(防极速脉冲拉升)"
                    if is_etf_up:
                        reason += f" | {etf_name}大级别趋势主升(+{etf_gain:.1f}%)"
                    type_priority = 98
                elif (is_etf_down or etf_channel_score < 35.0) and sec_res_count <= 1 and (pct >= 2.0 or "诱多" in order_intent):
                    # ⚠️ 诱多脉冲(板块破位)：所属板块 ETF 处于空头破位下行通道(评分<35/破支撑)，且无板块共振，警惕诱多
                    buy_type = "⚠️ 诱多脉冲(板块破位)"
                    buy_tag = "TRAP"
                    buy_zone = "-- (严禁追高/板块破位诱多)"
                    stop_loss = round(price * 0.95, 2)
                    reason = f"所属{sec}板块对应{etf_name}通道空头破位(评分{etf_channel_score:.0f}/跌破支撑{etf_supp_p:.2f}元), 且无板块共振, 异动冲高多为诱多拉高出货, 严禁追高防被套"
                    type_priority = 10
                elif "抢筹" in order_intent:
                    buy_type = "🚀 竞价抢筹"
                    buy_tag = "BID_SURGE"
                    buy_zone = f"{round(price * 0.99, 2)} ~ {price:.2f}"
                    stop_loss = round(price * 0.97, 2)
                    reason = f"不可撤单阶段真金白银高开抢筹 (+{pct:.1f}%, 竞价金额{b_amt_wan:.0f}万, 买盘压强{bid_p:.0f}%), 极速先手点"
                    type_priority = 96
                elif "弱转强" in order_intent:
                    buy_type = "🔥 弱转强"
                    buy_tag = "BID_REVERSAL"
                    buy_zone = f"{round(price * 0.99, 2)} ~ {price:.2f}"
                    stop_loss = round(price * 0.97, 2)
                    reason = f"竞价大幅弱转强超预期 (+{pct:.1f}%, 多头底座DFF2={dff2:.1f}), 黄金反转抢手"
                    type_priority = 94
                elif "诱多" in order_intent:
                    buy_type = "⚠️ 缩量诱多"
                    buy_tag = "TRAP"
                    buy_zone = "--"
                    stop_loss = round(price * 0.95, 2)
                    reason = f"竞价虚假高开但单量不足 (竞价金额仅{b_amt_wan:.0f}万, 压强{bid_p:.0f}%), 卖盘重压防砸"
                    type_priority = 10
                elif pct >= 4.5 and is_sec_leader:
                    buy_type = "👑 竞价领涨"
                    buy_tag = "LEADER"
                    buy_zone = f"{price:.2f}"
                    stop_loss = round(price * 0.97, 2)
                    reason = f"板块竞价领涨第一名 (+{pct:.1f}%, 买盘压强{bid_p:.0f}%)"
                    type_priority = 92
                else:
                    buy_type = "⏱️ 竞价观望"
                    buy_tag = "WATCH"
                    buy_zone = "--"
                    stop_loss = round(price * 0.95, 2)
                    reason = f"竞价阶段常规博弈 (+{pct:.1f}%, 买盘压强{bid_p:.0f}%)"
                    type_priority = 50

            # 💡 计算 VWAP 脱离成本区幅度 (成本线相对开盘价拉升的百分比)
            open_p_val = float(it.get("open", 0.0) or 0.0)
            vwap_escape_pct = ((vwap - open_p_val) / open_p_val * 100.0) if (open_p_val > 0 and vwap > 0) else 0.0
            it["vwap_escape_pct"] = round(vwap_escape_pct, 2)

            if (pct >= 9.5 and ("涨停" in order_intent or bid_p >= 75.0)) or (is_sec_leader and pct >= 4.5 and vwap_dev >= 0.0):
                # 👑 领涨龙头：封死涨停或板块绝对领涨第一名
                buy_type = "👑 领涨龙头"
                buy_tag = "LEADER"
                buy_zone = f"{vwap:.2f} ~ {price:.2f}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"板块领涨龙头 (买盘压强{bid_p:.0f}%), 站稳均线(+{vwap_dev:.1f}%), {order_intent}"
                type_priority = 100

            elif (open_p_val > 0 and max_2d > 0 and open_p_val >= max_2d - 0.015 and price >= max_2d and pct >= 2.5):
                # 👑 破红线高开高走：易点天下/四方精创模式 (高开越过连续回调阻力红线，高开高走起爆主升浪)
                buy_type = "👑 破红线高开高走"
                buy_tag = "LEADER"
                type_priority = 99
                buy_zone = f"{round(max(open_p_val, max_2d), 2)} ~ {price:.2f}"
                stop_loss = round(max(max_2d * 0.985, open_p_val * 0.985), 2)
                reason = f"连续回调后高开突破前高红线({max_2d:.2f}元)并持续高走, 彻底解放洗盘筹码, 黄金主升浪"

            elif is_reentry:
                # 💎 割肉反转回补：天马科技模式 (建仓早割肉后，回踩MA20/通道企稳并突破反转位，主升确立立即回补)
                buy_type = "💎 割肉反转回补"
                buy_tag = "RE_ENTRY_BUY"
                type_priority = 98
                buy_zone = reentry_info.get("buy_zone", f"{price:.2f}")
                stop_loss = reentry_info.get("stop_loss", round(price * 0.96, 2))
                reason = reentry_info.get("reason", "前期止损标的回踩企稳确认主升结构,触发反转回补")
                if is_etf_up:
                    reason += f" | {etf_name}趋势主升助推(+{etf_gain:.1f}%)"

            elif (per1d <= -1.0 and reversal_diff >= 3.0 and vwap_dev >= 0.0 and pct >= 1.0):
                # 👑 弱转强起爆延续：昨日回调洗盘后今日弱转强起爆 (柏星龙模式盘中主升浪)
                buy_type = "👑 弱转强起爆"
                buy_tag = "LEADER"
                type_priority = 98
                buy_zone = f"{vwap:.2f} ~ {price:.2f}"
                stop_loss = round(vwap * 0.98, 2)
                reason = f"昨日回调洗盘({per1d:+.1f}%)后今日弱转强起爆(+{pct:+.1f}%,反差+{reversal_diff:.1f}%), 站稳分时均线(+{vwap_dev:.1f}%), 黄金主升确认"
                if is_etf_up:
                    reason += f" | {etf_name}大级别趋势主升(+{etf_gain:.1f}%)"

            elif (vwap_escape_pct >= 1.5 and 0.5 <= vwap_dev <= 3.8 and 2.5 <= pct <= 9.0 and (vol_r >= 1.2 or slope >= 50.0)):
                # ⚡ 脱离成本狙击：开盘资金爆量向上扫单，VWAP 强斜率向上快速拉离成本区，未封板前可直接买入参与的黄金狙击点！
                buy_type = "⚡ 脱离成本狙击"
                buy_tag = "LEADER" if is_sec_leader else "SURGE"
                type_priority = 98 if is_sec_leader else 94
                buy_zone = f"{price*0.995:.2f} ~ {round(price * 1.008, 2)}"
                stop_loss = round(max(vwap * 0.988, open_p_val), 2)
                reason = f"VWAP快速拉离成本(+{vwap_escape_pct:.1f}%), 均线护城河(+{vwap_dev:.1f}%), 攻角{slope:.0f}°, 黄金狙击买入点"

            elif (is_etf_down or etf_channel_score < 35.0) and sec_res_count <= 1 and pct >= 1.5 and pct < 9.5 and not is_sec_leader:
                # ⚠️ 诱多脉冲(板块破位)：所属板块 ETF 处于空头破位下行通道(通道评分<35/跌破支撑)，且无板块共振，个股冲高孤狼拉升多为拉高诱多砸盘，坚决拦截！
                buy_type = "⚠️ 诱多脉冲(板块破位)"
                buy_tag = "TRAP"
                type_priority = 10
                buy_zone = "-- (严禁追高/板块破位诱多)"
                stop_loss = round(vwap * 0.97, 2)
                reason = f"板块{etf_name}通道空头破位(评分{etf_channel_score:.0f}/跌破支撑{etf_supp_p:.2f}元), 无板块共振, 异动冲高多为拉高诱多砸盘, 严禁追高防被套"

            elif "扫买" in order_intent and vwap_dev >= -0.2 and pct >= 1.5:
                # 🔥 主动扫买点火抢筹：主力大单主动吃进外盘，盘中起涨先手黄金点 (盘中不等涨停即可第一时间发现并报警！)
                if pct >= 6.5:
                    buy_type = "⚡ 扫盘冲板"
                    buy_tag = "SURGE"
                    type_priority = 96
                    reason = f"主力主动扫买冲击涨停 (买盘压强{bid_p:.0f}%), 站稳均线(+{vwap_dev:.1f}%), 极速抢跑点"
                else:
                    buy_type = "🔥 主动扫买"
                    buy_tag = "SURGE"
                    type_priority = 92
                    reason = f"主力外盘主动大单扫买 (量比{vol_r:.1f}), 买盘压强{bid_p:.0f}%, 均线支撑(+{vwap_dev:.1f}%), 盘中起涨先手点"
                buy_zone = f"{vwap:.2f} ~ {price:.2f}"
                stop_loss = round(vwap * 0.985, 2)

            elif pct >= 7.0 and (bid_p >= 70.0 or "托底" in order_intent):
                # ⚡ 扫盘冲板：大阳拉升，冲击涨停临界点
                buy_type = "⚡ 扫盘冲板"
                buy_tag = "SURGE"
                buy_zone = f"{price:.2f} ~ {round(price * 1.01, 2)}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"大阳拉升冲击涨停 (买盘压强{bid_p:.0f}%), 站稳均线(+{vwap_dev:.1f}%), 临界抢跑点"
                type_priority = 95

            elif (3.0 <= pct <= 7.0) and (vwap_dev >= 0.2) and (vol_r >= 1.1 or bid_p >= 60.0 or dff2 >= 8.0):
                # 🚀 先锋突破：放量起爆，突破日内高点，主升确认 (如长盈通、新开源)
                buy_type = "🚀 先锋突破"
                buy_tag = "BREAKOUT"
                buy_zone = f"{price:.2f} ~ {round(price * 1.008, 2)}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"主升先锋放量突破 (量比{vol_r:.1f}), 站稳均线(+{vwap_dev:.1f}%), 盈亏比极佳"
                type_priority = 90

            elif (vol_r >= 1.25 or dff2 >= 5.0) and (-0.3 <= vwap_dev <= 2.5) and (1.0 <= pct <= 5.0) and (has_base or turnover <= 5.5):
                # 💎 地量地价多日震荡起爆：多日筑底震荡，地量转放量起爆点
                buy_type = "💎 地量起爆"
                buy_tag = "PULLBACK"
                buy_zone = f"{vwap:.2f} ~ {round(vwap * 1.008, 2)}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"地量地价多日震荡筑底 (底座DFF2={dff2:.1f}), 今日放量起爆(量比{vol_r:.1f}), 均线支撑扎实, 黄金起爆点"
                type_priority = 88

            elif (-0.5 <= vwap_dev <= 1.8) and (0.8 <= pct <= 4.5) and (has_base or dff2 > 5.0 or slope >= 40):
                # 🎯 冰点反身低吸 / VWAP回踩：回踩分时均线不破，绝佳潜伏点 (如ST八菱、源杰科技)
                buy_type = "💎 反身低吸"
                buy_tag = "PULLBACK"
                buy_zone = f"{vwap:.2f} ~ {round(vwap * 1.005, 2)}"
                stop_loss = round(min(it['low'], vwap * 0.98), 2)
                reason = f"回踩分时均线({vwap:.2f})企稳不破, 支撑极强, 冰点黄金潜伏上车点"
                type_priority = 85

            elif vwap_dev < -0.8 or pct < -2.0 or (it.get('high', price) > 0 and it.get('last_close', 0) > 0 and (it.get('high', price) - it.get('last_close', price)) / it.get('last_close', price) * 100.0 >= 4.5 and vwap_dev < -0.3):
                # ⚠️ 破位转弱 / 冲高回落诱多被砸 (防猎避坑保护机制)
                high_pct = round((it.get('high', price) - it.get('last_close', price)) / max(0.01, it.get('last_close', price)) * 100.0, 1) if it.get('last_close', 0) > 0 else pct
                if high_pct >= 4.5 and vwap_dev < -0.3:
                    buy_type = "⚠️ 诱多破位"
                    buy_tag = "WEAK"
                    buy_zone = "-- (严禁抄底)"
                    stop_loss = round(vwap * 0.98, 2)
                    reason = f"曾冲高(+{high_pct:.1f}%)后回落跌破均线({vwap_dev:+.1f}%), 主力诱多出货, 严禁盲目接飞刀防被猎"
                    type_priority = 15
                else:
                    buy_type = "⚠️ 破位转弱"
                    buy_tag = "WEAK"
                    buy_zone = "-- (防守观望)"
                    stop_loss = round(vwap * 0.97, 2)
                    reason = f"跌破分时均线({vwap_dev:.1f}%), 承接动能不足, 严格执行止损防守"
                    type_priority = 20

            else:
                # 📋 蓄势观察 / 趋势蓄力
                buy_type = "📋 蓄势观察"
                buy_tag = "WATCH"
                buy_zone = f"{vwap:.2f} 附近"
                stop_loss = round(vwap * 0.98, 2)
                reason = f"在均线附近窄幅震荡, 等待放量突破或回踩信号"
                type_priority = 50

            # ── 💡 开盘即最低与跳空缺口加速能力赋能与提权 ──
            is_open_low = it.get("is_open_low_accel", False)
            is_gap = it.get("is_gap_accel", False)
            is_dual = it.get("is_dual_accel", False)
            low_diff = it.get("low_diff_pct", 999.0)
            accel_t = it.get("accel_tag", "")

            accel_bonus = 0.0
            if is_dual:
                type_priority += 12
                accel_bonus = 10.0
                reason = f"【👑双加速(光脚+缺口)】{reason}"
            elif is_open_low:
                type_priority += 6
                accel_bonus = 5.0
                reason = f"【⚡光脚加速(开盘即最低)】{reason}"
            elif is_gap:
                type_priority += 6
                accel_bonus = 5.0
                reason = f"【🚀缺口加速(跳空未补)】{reason}"

            # 重点关注标的专属加权与置顶提权
            is_focus = (sec == "重点关注" or it.get("is_focus", False))
            if is_focus:
                type_priority += 8
                reason = "⭐[重点关注] " + reason

            # 综合 Alpha 进攻得分 (0 ~ 100)
            if is_bidding_session:
                if "爆量突破" in order_intent or (is_breakout and b_amt_yi >= 0.2):
                    alpha_score = 99.0 + (1.0 if b_amt_yi >= 1.0 else 0.0)
                elif "一字" in order_intent:
                    alpha_score = 98.0 + (2.0 if b_amt_yi >= 1.0 else 0.0)
                elif buy_type == "👑 弱转强起爆":
                    alpha_score = round(min(99.0, 96.0 + min(3.0, reversal_diff * 0.5)), 1)
                elif buy_type == "💎 割肉反转回补":
                    alpha_score = 96.0
                elif buy_type == "⚠️ 昙花一现脉冲":
                    alpha_score = 15.0
                elif "抢筹" in order_intent:
                    alpha_score = round(min(97.0, 92.0 + min(5.0, b_amt_wan / 1000.0)), 1)
                elif "弱转强" in order_intent:
                    alpha_score = 91.0
                elif "诱多" in order_intent or "测盘" in order_intent:
                    alpha_score = 15.0
                else:
                    alpha_score = 50.0
                if is_dual:
                    alpha_score = min(100.0, alpha_score + 2.0)
                if is_etf_up:
                    alpha_score = min(100.0, alpha_score + 3.0)
            else:
                # 基础分为买点类型权重 (占比 55%)，动量与盘口扫买加成 (占比 45%)，叠加加速结构加成
                base_score = type_priority * 0.55
                momentum_bonus = min(18.0, max(0.0, pct * 2.0))
                intent_bonus = 10.0 if ("扫买" in order_intent or "封板" in order_intent) else (5.0 if "托底" in order_intent else 0.0)
                slope_bonus = min(10.0, slope * 0.10)
                base_bonus = 7.0 if has_base else 0.0
                focus_bonus = 6.0 if is_focus else 0.0

                # 💡 融入多日强势底蕴与启动加速梯度加权 (Multi-Day Momentum & Launch Acceleration)
                multiday_bonus = 0.0
                if dff2 >= 8.0:
                    multiday_bonus += 3.0
                if dff3 >= 15.0:
                    multiday_bonus += 3.0
                if is_breakout:
                    multiday_bonus += 4.0
                    reason = f"【突破多日平台】{reason}"
                elif has_base and (is_dual or is_gap or is_open_low):
                    multiday_bonus += 3.5
                    reason = f"【多日蓄势启动加速】{reason}"

                # 💡 板块 ETF 大级别趋势结构赋能与共振加权
                sec_bonus = 0.0
                if is_etf_up:
                    sec_bonus += etf_bonus  # +6.0
                elif is_etf_down and sec_res_count <= 1:
                    sec_bonus += etf_bonus  # -8.0
                if sec_res_count >= 2:
                    sec_bonus += 2.5  # 板块高开/红盘共振奖励

                alpha_score = base_score + momentum_bonus + intent_bonus + slope_bonus + base_bonus + focus_bonus + accel_bonus + multiday_bonus + sec_bonus
                if "弱转强起爆" in buy_type:
                    alpha_score = max(alpha_score, 95.0)
                elif "割肉反转回补" in buy_type:
                    alpha_score = max(alpha_score, 94.0)
                alpha_score = round(min(100.0, max(0.0, alpha_score)), 1)

            disp_buy_type = f"{accel_t}·{buy_type}" if (accel_t and "⚠️" not in buy_type) else buy_type
            it["buy_type"] = disp_buy_type
            it["buy_tag"] = buy_tag
            it["buy_zone"] = buy_zone
            it["stop_loss"] = stop_loss
            it["reason"] = reason
            it["type_priority"] = type_priority
            it["alpha_score"] = alpha_score
            it["accel_tag"] = accel_t
            it["is_open_low_accel"] = is_open_low
            it["is_gap_accel"] = is_gap
            it["is_dual_accel"] = is_dual
            it["low_diff_pct"] = low_diff
            
            # ── 💡 买点类型综合排序权值 (Buy Type Sort Score, 降序时最强绝对置顶) ──
            # 严格对齐 SSOT：统一由 compute_buy_type_sort_score 精准计算带头大哥动能权值
            from ats.ui.hot_sector_leaderboard import compute_buy_type_sort_score
            it["buy_type_sort_score"] = compute_buy_type_sort_score(it)
            results.append(it)

        # 按买点类型梯队分层，同类型内对比 Alpha 得分与盘口：双加速/缺口加速领涨龙头绝对优先置顶！
        def _alpha_sort_key(x):
            return (
                -float(x.get("buy_type_sort_score", 0.0)),
                -float(x.get("alpha_score", 0.0)),
                float(x.get("low_diff_pct", 999.0))
            )

        results.sort(key=_alpha_sort_key)
        return results

    def convert_quotes_to_df(self, quotes: List[Dict[str, Any]]) -> pd.DataFrame:
        """将 TDX 盘口列表转化为量化系统标准 DataFrame"""
        if not quotes:
            return pd.DataFrame()

        rows = []
        for q in quotes:
            c = str(q.get("code", "")).zfill(6)
            p = float(q.get("price", 0.0))
            op = float(q.get("open", p))
            hp = float(q.get("high", p))
            lp = float(q.get("low", p))
            lc = float(q.get("last_close", p))
            vol = float(q.get("vol", 0.0))
            amt = float(q.get("amount", 0.0))
            b1 = float(q.get("bid1", p))
            a1 = float(q.get("ask1", p))
            vw = round(amt / (vol * 100.0), 2) if (vol > 0 and amt > 0) else p
            
            # 涨跌幅
            pct = round((p - lc) / lc * 100.0, 2) if lc > 0 else 0.0

            rows.append({
                "code": c,
                "trade": p,
                "price": p,
                "close": p,
                "open": op,
                "high": hp,
                "low": lp,
                "last_close": lc,
                "change_pct": pct,
                "volume": vol,
                "vol": vol,
                "amount": amt,
                "vwap": vw,
                "buy": b1,
                "bid1": b1,
                "sell": a1,
                "ask1": a1
            })

        df = pd.DataFrame(rows)
        df.set_index("code", drop=False, inplace=True)
        return df


class TDXRealtimePollingWorker(threading.Thread):
    """
    后台 TDX 轮询 Worker 线程 (基准 3.0s，支持自适应动态退避)
    """
    def __init__(
        self,
        codes: List[str],
        interval_seconds: float = 3.0,
        on_data_callback: Optional[Callable[[pd.DataFrame, Dict[str, Any]], None]] = None
    ):
        super().__init__(daemon=True, name="TDXPollingWorker")
        self.codes = [str(c).zfill(6) for c in codes]
        self.interval = max(1.0, float(interval_seconds))
        self.callback = on_data_callback
        self.fetcher = TDXRealtimeFetcher.get_instance()
        self._running = False

    def update_target_codes(self, new_codes: List[str]):
        self.codes = [str(c).zfill(6) for c in new_codes]

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        logger.info(f"🚀 TDX 轮询 Worker 线程启动: 监控标的 {self.codes}, 基准刷新间隔 {self.interval}s")

        while self._running:
            try:
                if self.codes:
                    quotes = self.fetcher.get_security_quotes_safe(self.codes)
                    if quotes:
                        df = self.fetcher.convert_quotes_to_df(quotes)
                        snap_dict = {}
                        for c in self.codes:
                            snap = self.fetcher.fetch_stock_snapshot(c)
                            if snap:
                                snap_dict[c] = snap

                        if self.callback:
                            self.callback(df, snap_dict)
            except Exception as e:
                logger.warning(f"TDX 轮询执行异常: {e}")

            # 动态使用自适应间隔进行休眠
            current_sleep = max(self.interval, self.fetcher.get_current_interval_sec())
            time.sleep(current_sleep)

        logger.info("🛑 TDX 高频轮询 Worker 线程已安全停止")

