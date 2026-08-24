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

LOCAL_TDX_CONFIG_PATHS = [
    r"D:\MacTools\WinTools\new_tdx2\connect.cfg",
    r"D:\MacTools\WinTools\new_tdx2\connect-ShowTab.cfg",
    r"D:\MacTools\WinTools\new_tdx\connect.cfg",
    r"D:\MacTools\WinTool\zd_cczq\connect.cfg",
    r"D:\JohnsonProgram\联动精灵\connect.cfg",
    r"D:\MacTools\WinTools\tc_pazq\connect.cfg",
    r"D:\MacTools\WinTools\zd_dxzq\connect.cfg"
]


def extract_hosts_from_tdx_cfg(cfg_path: str) -> List[Tuple[str, str, int]]:
    """从通达信 connect.cfg 配置文件中解析 [HQHOST] 服务器列表"""
    hosts = []
    if not os.path.exists(cfg_path):
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
    """获取所有可用 TDX 服务器（本地预设优先，Fallback 兜底，去重）"""
    all_hosts = []
    seen = set()

    for path in LOCAL_TDX_CONFIG_PATHS:
        parsed = extract_hosts_from_tdx_cfg(path)
        for name, ip, port in parsed:
            if (ip, port) not in seen:
                seen.add((ip, port))
                all_hosts.append((name, ip, port))

    for name, ip, port in FALLBACK_TDX_HOSTS:
        if (ip, port) not in seen:
            seen.add((ip, port))
            all_hosts.append((name, ip, port))

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

        # 瞬时上涨涨速历史追踪缓存 {code: (last_price, last_timestamp)}
        self._velocity_history: Dict[str, Tuple[float, float]] = {}

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

        # 1. 尝试从本地阶梯规格获取
        try:
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            spec = IntradayStrategyEngine.get_instance().get_stock_ladder_spec(c_clean)
            float_shares_wan = float(spec.get("float_shares_wan", 0.0) or 0.0)
            if float_shares_wan > 0:
                self._finance_shares_cache[c_clean] = float_shares_wan * 10000.0
                return self._finance_shares_cache[c_clean]
        except Exception:
            pass

        # 2. 尝试从 TDX 财务数据接口拉取 (单次拉取永久有效)
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
        cooldown_sec = 30.0 if is_trading else 60.0

        # 若强制刷新或进入交易时段，清空非交易时段定盘与静默状态
        if force or is_trading:
            if self._off_hours_settled_codes:
                self._off_hours_settled_codes.clear()
                self._off_hours_success_counts.clear()
            if force:
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
                        for q in quotes:
                            c_clean = str(q.get("code", "")).strip().zfill(6)
                            if not c_clean:
                                continue
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
                        self.add_log(f"⚡ [TDX] 成功获取批次 {len(quotes)} 只标的行情 (耗时: {cost_ms:.1f}ms, 主站: {host_info})", level="INFO")
                    else:
                        self.add_log(f"⚠️ [TDX] 批次 [{codes_str[:30]}...] 未返回盘口数据，尝试单只补拉", level="WARN")
                        for mkt, c_clean in req_params:
                            try:
                                single_q = self.api.get_security_quotes([(mkt, c_clean)])
                                if single_q:
                                    all_fetched_quotes.extend(single_q)
                                    self._off_hours_cached_quotes[c_clean] = single_q[0]
                            except Exception:
                                pass
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

    def get_circulation_shares(self, code: str) -> float:
        """
        获取股票流通股本 (单位：股)。优先从 IntradayStrategyEngine 的 stock_spec 中获取，
        回退使用 15 亿元 / 昨收估算流通股本，保底 1000 万股。
        """
        c_clean = str(code).strip().zfill(6)
        try:
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            spec = IntradayStrategyEngine.get_instance().get_stock_ladder_spec(c_clean)
            sh_wan = float(spec.get("float_shares_wan", 0.0))
            if sh_wan > 0:
                return sh_wan * 10000.0

            mv_yi = float(spec.get("float_mv_yi", 15.0))
            issue_p = float(spec.get("issue_price", 10.0))
            if mv_yi > 0 and issue_p > 0:
                return (mv_yi * 1e8) / issue_p
        except Exception:
            pass
        return 10000000.0 # 默认保底 1000 万股

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
        cat_map = {
            "5m": 0,
            "15m": 1,
            "30m": 2,
            "60m": 3,
            "day": 4,
            "week": 5,
            "month": 6
        }
        cat_code = cat_map.get(category, 0)

        try:
            mkt = get_market_code(c_clean)
            bars = None
            with self._conn_lock:
                if not self._is_connected or self.api is None:
                    if not self.connect():
                        return pd.DataFrame()
                try:
                    bars = self.api.get_security_bars(cat_code, mkt, c_clean, 0, count)
                except Exception as e_k:
                    logger.debug(f"TDX get_security_bars {cat_code} 异常: {e_k}")
                    bars = None

                # 💡 若连接闲置超时被服务端切断或拉取为空，自动标记断开并立即重连重试！
                if not bars or len(bars) == 0:
                    self._is_connected = False
                    if self.connect():
                        try:
                            bars = self.api.get_security_bars(cat_code, mkt, c_clean, 0, count)
                        except Exception:
                            bars = None

            if not bars:
                return pd.DataFrame()

            df = pd.DataFrame(bars)
            if df.empty:
                return pd.DataFrame()

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

                if last_row_date == today_str and len(df_daily) >= 2:
                    y_row = df_daily.iloc[-2]
                elif last_row_date != today_str and len(df_daily) >= 1:
                    y_row = df_daily.iloc[-1]
                else:
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

    def fetch_multi_stock_alpha_quotes(
        self,
        codes: List[str],
        sector_map: Optional[Dict[str, str]] = None,
        multi_period_cache: Optional[Dict[str, Any]] = None,
        name_map: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        批量拉取多只股票的 TDX 高频盘口数据，并计算量比爆发力、分时 VWAP 偏离、
        买卖盘口承接力、分时进攻斜率以及【三维买点定位】(领涨龙头/先锋突破/VWAP回踩/跟风)。

        :param codes: 股票代码列表，例如 ['300570', '688167', '603083']
        :param sector_map: 代码到所属强势板块的映射 {code: sector_name}
        :param multi_period_cache: 底层多日底蕴特征 {code: {dff, dff2, dff3, rank, perc3d...}}
        :param name_map: 代码到名称的映射 {code: name}
        :return: 包含完整 Alpha 动量与买点指引的字典列表，按 alpha_score 降序排列
        """
        if not codes:
            return []

        quotes = self.get_security_quotes_safe(codes)
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

            price = float(q.get("price", 0.0))
            open_p = float(q.get("open", price))
            high_p = float(q.get("high", price))
            low_p = float(q.get("low", price))
            if low_p <= 1.0 or (price > 5.0 and low_p < price * 0.1):
                low_p = price if price > 0 else (open_p if open_p > 0 else 10.0)
            last_close = float(q.get("last_close", price))
            vol = float(q.get("vol", 0.0))       # 手
            amount = float(q.get("amount", 0.0)) # 元
            cur_vol = float(q.get("cur_vol", 0.0))
            b_vol = float(q.get("b_vol", 0.0))
            s_vol = float(q.get("s_vol", 0.0))

            # 涨幅 %
            pct = round((price - last_close) / last_close * 100.0, 2) if last_close > 0 else 0.0

            # 1. 瞬时/动态上涨涨速 (%/分)
            velocity_pct = 0.0
            if hasattr(self, '_velocity_history') and code_str in self._velocity_history:
                old_p, old_t = self._velocity_history[code_str]
                dt = now_ts - old_t
                if 1.0 <= dt <= 30.0 and last_close > 0:
                    velocity_pct = round((price - old_p) / last_close * 100.0 * (60.0 / dt), 1)
            self._velocity_history[code_str] = (price, now_ts)

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

            # 盘口主力行为分析
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
                "turnover": turnover_val,
                "vol_ratio": vol_ratio_val,
                "slope_score": slope_score,
                "dff": dff,
                "dff2": dff2,
                "dff3": dff3,
                "rank": rank_val,
                "perc3d": perc3d,
                "extra_vals": mp_info.get("extra_vals", {}),
            })

        # 2. 板块内领涨与多维买点统一智能分拣
        # 按板块分组统计最高涨幅与领跑者
        sector_max_pct = {}
        sector_leader_code = {}
        for it in parsed_items:
            sec = it["sector"]
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
            turnover = it["turnover"]
            sec = it["sector"]
            max_sec_p = sector_max_pct.get(sec, pct)
            is_sec_leader = (code == sector_leader_code.get(sec, ""))

            # 是否多日多头底座扎实 (2D/3D 加速)
            has_base = (dff2 > 0.0 or dff3 > 0.0)

            # ── 💡 统一多模块智能阿尔法分拣决策 ──
            if (pct >= 9.5 and ("涨停" in order_intent or bid_p >= 75.0)) or (is_sec_leader and pct >= 5.0 and vwap_dev >= 0.0):
                # 👑 领涨龙头：封死涨停或板块绝对领涨第一名
                buy_type = "👑 领涨龙头"
                buy_tag = "LEADER"
                buy_zone = f"{vwap:.2f} ~ {price:.2f}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"板块领涨灵魂标的 (板块第一), 站稳VWAP(+{vwap_dev:.1f}%), 主力强势统治"
                type_priority = 100

            elif pct >= 7.0 and (bid_p >= 70.0 or "扫买" in order_intent or "托底" in order_intent):
                # ⚡ 扫盘冲板：大阳拉升，主力主动扫买，冲击涨停临界点 (如三元基因)
                buy_type = "⚡ 扫盘冲板"
                buy_tag = "SURGE"
                buy_zone = f"{price:.2f} ~ {round(price * 1.01, 2)}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"主力主动扫买冲击涨停 (买盘压强{bid_p:.0f}%), 站稳均线(+{vwap_dev:.1f}%), 临界抢跑点"
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

            # 重点关注标的专属加权与置顶提权
            is_focus = (sec == "重点关注" or it.get("is_focus", False))
            if is_focus:
                type_priority += 8
                reason = "⭐[重点关注] " + reason

            # 综合 Alpha 进攻得分 (0 ~ 100)
            alpha_score = (
                type_priority * 0.35 +
                min(30.0, max(0.0, pct * 2.5)) +
                min(15.0, slope * 0.15) +
                min(10.0, bid_p * 0.1) +
                (10.0 if has_base else 0.0) +
                (6.0 if is_focus else 0.0)
            )
            alpha_score = round(min(100.0, max(0.0, alpha_score)), 1)

            it["buy_type"] = buy_type
            it["buy_tag"] = buy_tag
            it["buy_zone"] = buy_zone
            it["stop_loss"] = stop_loss
            it["reason"] = reason
            it["alpha_score"] = alpha_score
            results.append(it)

        # 按 Alpha 得分降序排列
        results.sort(key=lambda x: x["alpha_score"], reverse=True)
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

