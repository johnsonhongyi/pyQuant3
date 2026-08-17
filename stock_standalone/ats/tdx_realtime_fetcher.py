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
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from pytdx.hq import TdxHq_API

from logger_utils import LoggerFactory
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger("TDXRealtimeFetcher")

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
    0 -> 深圳市场 (000, 001, 002, 003, 300, 301)
    1 -> 上海市场 (600, 601, 603, 605, 688, 689)
    """
    c = str(stock_code).strip().zfill(6)
    if c.startswith(("600", "601", "603", "605", "688", "689", "110", "113", "510")):
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
        self.add_log("🚀 TDX 高频行情引擎初始化完成，准备测速与连接最优主站", level="INFO")

        # 启动时快速选取最优服务器
        self._init_best_server()

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

    def get_security_quotes_safe(self, codes: List[str]) -> List[Dict[str, Any]]:
        """
        安全批量获取股票最新五档盘口行情
        :param codes: 股票代码列表，例如 ['688826', '600519']
        :return: 盘口字典列表
        """
        if not codes:
            return []

        t_start = time.time()
        with self._conn_lock:
            if not self._is_connected:
                if not self.connect():
                    self.add_log(f"无法建立 TDX 连接，跳过获取 {len(codes)} 只标的行情", level="ERROR")
                    return []

            req_params = []
            for c in codes:
                c_clean = str(c).strip().zfill(6)
                mkt = get_market_code(c_clean)
                req_params.append((mkt, c_clean))

            try:
                quotes = self.api.get_security_quotes(req_params)
                if quotes:
                    cost_ms = (time.time() - t_start) * 1000.0
                    host_info = f"{self.current_host[0]}" if self.current_host else "TDX"
                    self.add_log(f"批量拉取 {len(codes)} 只标的成功 (耗时: {cost_ms:.1f}ms, 服务器: {host_info})", level="INFO")
                    return quotes
            except Exception as e:
                self.add_log(f"批量获取 {len(codes)} 只标的行情异常: {e}, 正在切换连接重试...", level="WARN")
                self._is_connected = False

            # 若批量出错，尝试重新连接后逐个安全获取
            if not self.connect():
                return []

            results = []
            for mkt, c_clean in req_params:
                try:
                    q_single = self.api.get_security_quotes([(mkt, c_clean)])
                    if q_single and len(q_single) > 0:
                        results.append(q_single[0])
                except Exception as e_s:
                    self.add_log(f"单股 {c_clean} 行情拉取异常: {e_s}", level="WARN")
            cost_ms = (time.time() - t_start) * 1000.0
            self.add_log(f"逐个降级拉取完成: 成功 {len(results)}/{len(codes)} 只 (耗时: {cost_ms:.1f}ms)", level="INFO")
            return results

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

        # 动态获取该标的真实流通盘 (万股)
        circ_wan = circulation_shares_wan
        if circ_wan is None or circ_wan <= 0:
            try:
                from ats.intraday_strategy_engine import IntradayStrategyEngine
                spec = IntradayStrategyEngine.get_instance().get_stock_ladder_spec(c_clean)
                float_mv_yi = float(spec.get("float_mv_yi", 0.0))
                if float_mv_yi > 0 and trade_price > 0:
                    circ_wan = (float_mv_yi * 1e8 / trade_price) / 10000.0
                elif c_clean == "688826":
                    circ_wan = 761.78
            except Exception:
                circ_wan = 761.78 if c_clean == "688826" else None

        # 计算换手率 (%)
        if circ_wan and circ_wan > 0 and vol > 0:
            total_circ_shares = circ_wan * 10000.0
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
            last_close = float(q.get("last_close", price))
            vol = float(q.get("vol", 0.0))       # 手
            amount = float(q.get("amount", 0.0)) # 元

            # 涨幅 %
            pct = round((price - last_close) / last_close * 100.0, 2) if last_close > 0 else 0.0

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

            # 五档买卖盘量能统计与买压比 (%)
            bid_vol_sum = 0.0
            ask_vol_sum = 0.0
            for i in range(1, 6):
                bid_vol_sum += float(q.get(f"bid_vol{i}", 0.0) or 0.0)
                ask_vol_sum += float(q.get(f"ask_vol{i}", 0.0) or 0.0)

            total_depth = bid_vol_sum + ask_vol_sum
            bid_pressure = round((bid_vol_sum / total_depth) * 100.0, 1) if total_depth > 0 else 50.0

            # 多日特征
            mp_info = multi_period_cache.get(code_str, {})
            dff = float(mp_info.get("dff", 0.0) or 0.0)
            dff2 = float(mp_info.get("dff2", 0.0) or 0.0)
            dff3 = float(mp_info.get("dff3", 0.0) or 0.0)
            rank_val = int(mp_info.get("rank", mp_info.get("Rank", 999)) or 999)
            perc3d = float(mp_info.get("perc3d", 0.0) or 0.0)
            vol_ratio_base = float(mp_info.get("vol_ratio", mp_info.get("vol_rati", 1.0)) or 1.0)

            # 动态量比预估 (结合多日量比与盘中换手强度)
            vol_ratio = round(vol_ratio_base, 2) if vol_ratio_base > 0 else 1.0

            # 分时拉升攻角评分 (0 ~ 100)
            # 依据: 现价高于VWAP、处于日内高位区、涨幅、五档买压
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
                "vwap": vwap,
                "vwap_dev_pct": vwap_dev_pct,
                "vol": vol,
                "amount": amount,
                "bid1": float(q.get("bid1", price)),
                "ask1": float(q.get("ask1", price)),
                "bid_vol_sum": bid_vol_sum,
                "ask_vol_sum": ask_vol_sum,
                "bid_pressure": bid_pressure,
                "vol_ratio": vol_ratio,
                "slope_score": slope_score,
                "dff": dff,
                "dff2": dff2,
                "dff3": dff3,
                "rank": rank_val,
                "perc3d": perc3d,
                "extra_vals": mp_info.get("extra_vals", {}),
            })

        # 2. 板块内领涨与三维买点智能判决
        # 按板块分组统计最高涨幅与领跑者
        sector_max_pct = {}
        for it in parsed_items:
            sec = it["sector"]
            if sec not in sector_max_pct or it["pct"] > sector_max_pct[sec]:
                sector_max_pct[sec] = it["pct"]

        results = []
        for it in parsed_items:
            pct = it["pct"]
            vwap = it["vwap"]
            vwap_dev = it["vwap_dev_pct"]
            price = it["price"]
            vol_r = it["vol_ratio"]
            dff2 = it["dff2"]
            dff3 = it["dff3"]
            slope = it["slope_score"]
            bid_p = it["bid_pressure"]
            sec = it["sector"]
            max_sec_p = sector_max_pct.get(sec, pct)

            # 是否多日多头底座扎实 (2D/3D 加速)
            has_base = (dff2 > 0.0 or dff3 > 0.0)

            # 三维买点判定
            if pct >= 5.0 and (pct >= max_sec_p - 0.5) and vwap_dev >= 0.0:
                buy_type = "👑 领涨龙头"
                buy_tag = "LEADER"
                buy_zone = f"{vwap:.2f} ~ {price:.2f}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"板块领涨先锋(同板块涨幅最高), 站稳VWAP(+{vwap_dev:.1f}%), 主攻波形"
                type_priority = 100
            elif (1.5 <= pct <= 6.5) and vwap_dev >= 0.2 and vol_r >= 1.2 and has_base:
                buy_type = "🚀 先锋突破"
                buy_tag = "BREAKOUT"
                buy_zone = f"{price:.2f} ~ {round(price * 1.008, 2)}"
                stop_loss = round(vwap * 0.985, 2)
                reason = f"起爆先锋突破, 放量(量比{vol_r:.1f}), 站稳均线(+{vwap_dev:.1f}%), 性价比极高"
                type_priority = 90
            elif (-0.5 <= vwap_dev <= 0.8) and pct > 0.5 and has_base and slope >= 45:
                buy_type = "🎯 VWAP回踩"
                buy_tag = "PULLBACK"
                buy_zone = f"{vwap:.2f} ~ {round(vwap * 1.005, 2)}"
                stop_loss = round(min(it['low'], vwap * 0.98), 2)
                reason = f"回踩分时均线({vwap:.2f})企稳不破, 支撑极强, 风险收益比极佳"
                type_priority = 80
            elif vwap_dev < -1.0 or pct < -2.0:
                buy_type = "⚠️ 破位转弱"
                buy_tag = "WEAK"
                buy_zone = "--"
                stop_loss = round(vwap * 0.97, 2)
                reason = f"跌破分时均线({vwap_dev:.1f}%), 动能不足"
                type_priority = 20
            else:
                buy_type = "📋 蓄势观察"
                buy_tag = "WATCH"
                buy_zone = f"{vwap:.2f} 附近"
                stop_loss = round(vwap * 0.98, 2)
                reason = f"在均线附近窄幅震荡, 等待放量信号"
                type_priority = 50

            # 综合 Alpha 进攻得分 (0 ~ 100)
            alpha_score = (
                type_priority * 0.35 +
                min(30.0, max(0.0, pct * 2.5)) +
                min(15.0, slope * 0.15) +
                min(10.0, bid_p * 0.1) +
                (10.0 if has_base else 0.0)
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
    后台高频秒级 TDX 轮询 Worker 线程
    """
    def __init__(
        self,
        codes: List[str],
        interval_seconds: float = 1.0,
        on_data_callback: Optional[Callable[[pd.DataFrame, Dict[str, Any]], None]] = None
    ):
        super().__init__(daemon=True, name="TDXPollingWorker")
        self.codes = [str(c).zfill(6) for c in codes]
        self.interval = max(0.5, float(interval_seconds))
        self.callback = on_data_callback
        self.fetcher = TDXRealtimeFetcher.get_instance()
        self._running = False

    def update_target_codes(self, new_codes: List[str]):
        self.codes = [str(c).zfill(6) for c in new_codes]

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        logger.info(f"🚀 TDX 高频轮询 Worker 线程启动: 监控标的 {self.codes}, 刷新间隔 {self.interval}s")

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

            time.sleep(self.interval)

        logger.info("🛑 TDX 高频轮询 Worker 线程已安全停止")

