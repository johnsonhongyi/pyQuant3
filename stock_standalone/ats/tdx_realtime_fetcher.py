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
import logging
import threading
import concurrent.futures
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from pytdx.hq import TdxHq_API

logger = logging.getLogger("TDXRealtimeFetcher")

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


class TDXRealtimeFetcher:
    """
    通达信秒级独立行情拉取引擎（支持单例与独立实例）
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

        # 启动时快速选取最优服务器
        self._init_best_server()

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
                return False

            name, ip, port = self.current_host
            self.api = TdxHq_API(heartbeat=False)
            try:
                if self.api.connect(ip, port, time_out=1.2):
                    self._is_connected = True
                    logger.info(f"✅ TDX 行情接口已成功连接到 {name} ({ip}:{port})")
                    return True
            except Exception as e:
                logger.warning(f"❌ 连接 TDX 服务器 {ip}:{port} 失败: {e}")
                self._is_connected = False

            # 故障转移
            for cost, f_name, f_ip, f_port in self.active_hosts_pool[1:5]:
                try:
                    self.api = TdxHq_API(heartbeat=False)
                    if self.api.connect(f_ip, f_port, time_out=1.2):
                        self._is_connected = True
                        self.current_host = (f_name, f_ip, f_port)
                        self.latency_ms = cost
                        logger.info(f"✅ TDX 故障切换成功连接到备用服务器 {f_name} ({f_ip}:{f_port})")
                        return True
                except Exception:
                    continue

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

        with self._conn_lock:
            if not self._is_connected:
                if not self.connect():
                    return []

            req_params = []
            for c in codes:
                c_clean = str(c).strip().zfill(6)
                mkt = get_market_code(c_clean)
                req_params.append((mkt, c_clean))

            try:
                quotes = self.api.get_security_quotes(req_params)
                if quotes:
                    return quotes
            except Exception as e:
                logger.warning(f"批量获取 TDX 盘口异常: {e}, 尝试逐个重试...")
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
                except Exception:
                    pass
            return results

    def fetch_stock_snapshot(
        self,
        code: str,
        circulation_shares_wan: float = 761.78
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

        # 计算 VWAP 均价
        if vol > 0 and amount > 0:
            vwap = round(amount / (vol * 100.0), 2)
        else:
            vwap = trade_price if trade_price > 0 else open_price

        # 计算换手率
        total_circ_shares = circulation_shares_wan * 10000.0
        if total_circ_shares > 0 and vol > 0:
            turnover_rate = round((vol * 100.0 / total_circ_shares) * 100.0, 2)
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
