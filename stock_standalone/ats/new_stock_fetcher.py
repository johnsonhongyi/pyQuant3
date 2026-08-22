# -*- coding: utf-8 -*-
"""
ats/new_stock_fetcher.py — ATS 新股/次新股/IPO发行日历全市场多通道数据与磁盘持久化引擎
职责：
1. 自动抓取并本地磁盘持久化全市场（沪深主板、科创板、创业板、北交所）近期已上市、前5日(C)、首日(N)、次新股(近90日)基础日历与行情；
2. 彻底解决代理冲突与被 ban 痛点：使用直连 requests (trust_env=False)、6小时智能防频控、本地 JSON 磁盘持久化、网络异常 100% 无缝平滑降级；
3. 多通道（TDX直连权威股本 + 腾讯行情 + 东方财富 + IPC数据流）毫秒级补齐现价、涨跌幅、换手率、成交额、流通市值、总市值，彻底消除数据缺失与 `--` 占位符；
4. 深度对接 TDXRealtimeFetcher 与分时阶梯策略引擎，支持冷启动 0 秒展示。
"""

import sys
import os
import time
import json
import math
import logging
import datetime
import requests
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple

from sys_utils import get_app_root, get_conf_path

logger = logging.getLogger("NewStockFetcher")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "http://quote.eastmoney.com/"
}

# 本地持久化文件路径
IPO_CALENDAR_CACHE_FILE = os.path.join(get_app_root(), "config", "new_stock_ipo_calendar.json")
NEW_STOCK_DATA_CACHE_FILE = os.path.join(get_app_root(), "config", "new_stock_data_cache.json")

# 出厂预置新股清单（当本地无文件且网络离线时的终极安全兜底）
FACTORY_DEFAULT_NEW_STOCKS: List[Dict[str, Any]] = [
    {"code": "920012", "name": "创达新材", "trade_market": "北交所", "issue_price": 19.58, "apply_date": "2026-04-01", "listing_date": "2026-04-13", "status": "已上市"},
    {"code": "920078", "name": "族兴新材", "trade_market": "北交所", "issue_price": 6.98, "apply_date": "2026-03-09", "listing_date": "2026-03-18", "status": "已上市"},
    {"code": "688826", "name": "频准激光", "trade_market": "科创板", "issue_price": 186.88, "apply_date": "2026-08-07", "listing_date": "2026-08-18", "status": "前5日(C)"},
    {"code": "688836", "name": "宇树科技", "trade_market": "科创板", "issue_price": 150.80, "apply_date": "2026-08-10", "listing_date": "2026-08-19", "status": "前5日(C)"},
    {"code": "001232", "name": "嘉立创", "trade_market": "深主板", "issue_price": 84.46, "apply_date": "2026-07-24", "listing_date": "2026-08-04", "status": "次新"},
    {"code": "688808", "name": "联讯仪器", "trade_market": "科创板", "issue_price": 81.88, "apply_date": "2026-04-14", "listing_date": "2026-04-24", "status": "已上市"},
    {"code": "301683", "name": "慧谷新材", "trade_market": "创业板", "issue_price": 78.38, "apply_date": "2026-03-20", "listing_date": "2026-04-01", "status": "已上市"},
    {"code": "301682", "name": "宏明电子", "trade_market": "创业板", "issue_price": 69.66, "apply_date": "2026-03-16", "listing_date": "2026-03-25", "status": "已上市"},
    {"code": "301655", "name": "绿控传动", "trade_market": "创业板", "issue_price": 32.50, "apply_date": "2026-06-18", "listing_date": "2026-06-28", "status": "次新"},
    {"code": "920059", "name": "双英集团", "trade_market": "北交所", "issue_price": 12.80, "apply_date": "2026-07-02", "listing_date": "2026-07-12", "status": "次新"},
]


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


def _get_direct_session() -> requests.Session:
    """创建绕过系统代理的纯直连 requests Session，防止本地代理导致 ProxyError"""
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}
    return session


class NewStockFetcher:
    """新股与次新股多通道数据获取、聚合与磁盘持久化引擎"""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._cached_stocks_df: Optional[pd.DataFrame] = None
        self._cached_ipo_dict: Dict[str, Dict[str, Any]] = {}
        self._last_fetch_time: float = 0.0
        self._last_calendar_fetch_time: float = 0.0
        self._cache_ttl_seconds: float = 2.5  # 2.5秒内存缓存，满足高频实时刷新

        # 启动时自动从本地磁盘持久化文件加载恢复
        self._load_persisted_data()

    def _load_persisted_data(self):
        """【💾 磁盘持久化加载】冷启动瞬间恢复本地已有的 IPO 日历与全量新股表"""
        # 1. 恢复 IPO 日历
        if os.path.exists(IPO_CALENDAR_CACHE_FILE):
            try:
                with open(IPO_CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cached_ipo_dict = data.get("items", {})
                        self._last_calendar_fetch_time = float(data.get("updated_at", 0.0))
                        logger.info(f"✅ 成功从磁盘恢复 IPO 日历: 共 {len(self._cached_ipo_dict)} 条记录")
            except Exception as e:
                logger.debug(f"加载 IPO 日历持久化文件异常: {e}")

        # 若无磁盘日历，注入出厂预置数据
        if not self._cached_ipo_dict:
            for item in FACTORY_DEFAULT_NEW_STOCKS:
                c = item["code"]
                self._cached_ipo_dict[c] = dict(item)

        # 2. 恢复新股汇总 DataFrame
        if os.path.exists(NEW_STOCK_DATA_CACHE_FILE):
            try:
                with open(NEW_STOCK_DATA_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and data:
                        df_loaded = pd.DataFrame(data)
                        if not df_loaded.empty and "code" in df_loaded.columns:
                            self._cached_stocks_df = df_loaded
                            logger.info(f"✅ 成功从磁盘恢复新股数据表: 共 {len(df_loaded)} 条记录")
            except Exception as e:
                logger.debug(f"加载新股数据表持久化文件异常: {e}")

    def _save_persisted_ipo_calendar(self):
        """【💾 磁盘持久化保存】将 IPO 日历原子落盘保存至 config/new_stock_ipo_calendar.json"""
        if not self._cached_ipo_dict:
            return
        try:
            os.makedirs(os.path.dirname(IPO_CALENDAR_CACHE_FILE), exist_ok=True)
            payload = {
                "updated_at": time.time(),
                "count": len(self._cached_ipo_dict),
                "items": self._cached_ipo_dict
            }
            tmp_file = f"{IPO_CALENDAR_CACHE_FILE}.tmp_{os.getpid()}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            if os.path.exists(IPO_CALENDAR_CACHE_FILE):
                os.replace(tmp_file, IPO_CALENDAR_CACHE_FILE)
            else:
                os.rename(tmp_file, IPO_CALENDAR_CACHE_FILE)
        except Exception as e:
            logger.debug(f"持久化保存 IPO 日历异常: {e}")

    def _save_persisted_stocks_df(self, df: pd.DataFrame):
        """【💾 磁盘持久化保存】将新股数据表原子落盘保存至 config/new_stock_data_cache.json"""
        if df is None or df.empty:
            return
        try:
            os.makedirs(os.path.dirname(NEW_STOCK_DATA_CACHE_FILE), exist_ok=True)
            records = df.to_dict(orient="records")
            tmp_file = f"{NEW_STOCK_DATA_CACHE_FILE}.tmp_{os.getpid()}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            if os.path.exists(NEW_STOCK_DATA_CACHE_FILE):
                os.replace(tmp_file, NEW_STOCK_DATA_CACHE_FILE)
            else:
                os.rename(tmp_file, NEW_STOCK_DATA_CACHE_FILE)
        except Exception as e:
            logger.debug(f"持久化保存新股数据表异常: {e}")

    def fetch_ipo_calendar(self, page_size: int = 100, force: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        从东方财富 IPO 日历接口拉取近期发行与上市新股列表 (带 6 小时防频控与 100% 磁盘缓存降级兜底)
        """
        now = time.time()
        # 6 小时防频控：非强制刷新且本地缓存已有数据时直接复用，杜绝高频请求被封 IP
        if not force and self._cached_ipo_dict and (now - self._last_calendar_fetch_time < 6 * 3600):
            return self._cached_ipo_dict

        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            "reportName=RPTA_APP_IPOAPPLY&"
            "columns=SECURITY_CODE,SECURITY_NAME,TRADE_MARKET,APPLY_CODE,ISSUE_PRICE,APPLY_DATE,LISTING_DATE,ONLINE_ISSUE_NUM,BALLOT_NUM&"
            f"pageNumber=1&pageSize={page_size}&sortColumns=APPLY_DATE&sortTypes=-1&source=WEB&client=WEB"
        )
        ipo_dict = {}
        try:
            session = _get_direct_session()
            resp = session.get(url, headers=DEFAULT_HEADERS, timeout=3.5)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("result", {}).get("data", []) if data.get("result") else []
                for it in items:
                    c = str(it.get("SECURITY_CODE", "")).strip().zfill(6)
                    if not c:
                        continue
                    listing_d = str(it.get("LISTING_DATE", "") or "").split(" ")[0].strip()
                    apply_d = str(it.get("APPLY_DATE", "") or "").split(" ")[0].strip()
                    if listing_d in ("None", "null", ""):
                        listing_d = ""
                    if apply_d in ("None", "null", ""):
                        apply_d = ""

                    issue_price_val = safe_float(it.get("ISSUE_PRICE"), default=0.0)
                    online_num_val = safe_float(it.get("ONLINE_ISSUE_NUM"), default=0.0)
                    ballot_num = it.get("BALLOT_NUM")

                    ipo_dict[c] = {
                        "code": c,
                        "name": str(it.get("SECURITY_NAME", "")).strip(),
                        "trade_market": str(it.get("TRADE_MARKET", "")).strip(),
                        "apply_code": str(it.get("APPLY_CODE", "")).strip(),
                        "issue_price": issue_price_val if issue_price_val > 0 else None,
                        "apply_date": apply_d,
                        "listing_date": listing_d,
                        "online_issue_num": online_num_val if online_num_val > 0 else None,
                        "ballot_num": ballot_num,
                    }
                if ipo_dict:
                    self._cached_ipo_dict = ipo_dict
                    self._last_calendar_fetch_time = time.time()
                    self._save_persisted_ipo_calendar()
                    logger.info(f"✅ 成功联网拉取东方财富 IPO 日历: 共 {len(ipo_dict)} 条记录 (已持久化落盘)")
                    return ipo_dict
        except Exception as e:
            logger.debug(f"直连拉取东方财富 IPO 日历异常: {e}，自动降级至本地持久化日历")

        # 降级：返回内存或磁盘已持久化的日历
        if not self._cached_ipo_dict:
            self._load_persisted_data()
        return self._cached_ipo_dict

    def fetch_recent_new_stocks_spot(self) -> Dict[str, Dict[str, Any]]:
        """
        拉取已上市新股与次新股实时行情（直连多通道）
        """
        spot_dict = {}

        # 通道 1: 东方财富 Push2 直连
        try:
            session = _get_direct_session()
            url = "http://82.push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1",
                "pz": "150",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "wbp2u": "|0|0|0|web",
                "fid": "f26",
                "fs": "m:0 f:8,m:1 f:8,m:0 t:81 s:2048",
                "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f22,f23,f24,f25,f26,f11",
            }
            resp = session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                for it in items:
                    c = str(it.get("f12", "")).strip().zfill(6)
                    if not c:
                        continue
                    f26_val = str(it.get("f26", "") or "").strip()
                    if len(f26_val) == 8:
                        listing_d = f"{f26_val[:4]}-{f26_val[4:6]}-{f26_val[6:]}"
                    else:
                        listing_d = f26_val

                    spot_dict[c] = {
                        "code": c,
                        "name": str(it.get("f14", "")).strip(),
                        "price": safe_float(it.get("f2")),
                        "pct": safe_float(it.get("f3")),
                        "change_val": safe_float(it.get("f4")),
                        "vol": safe_float(it.get("f5")),
                        "amount": safe_float(it.get("f6")),
                        "amplitude": safe_float(it.get("f7")),
                        "high": safe_float(it.get("f15")),
                        "low": safe_float(it.get("f16")),
                        "open": safe_float(it.get("f17")),
                        "last_close": safe_float(it.get("f18")),
                        "turnover": safe_float(it.get("f8")),
                        "pe_dynamic": safe_float(it.get("f9")),
                        "pb": safe_float(it.get("f23")),
                        "listing_date": listing_d,
                        "total_mv": safe_float(it.get("f20")),
                        "float_mv": safe_float(it.get("f21")),
                    }
                if spot_dict:
                    return spot_dict
        except Exception as e:
            logger.debug(f"Push2 获取新股行情异常: {e}")

        # 通道 2: akshare 备用
        try:
            import akshare as ak
            df_spot = ak.stock_new_a_spot_em()
            if df_spot is not None and not df_spot.empty:
                for _, row in df_spot.iterrows():
                    c = str(row.get("代码", "")).strip().zfill(6)
                    if not c:
                        continue
                    spot_dict[c] = {
                        "code": c,
                        "name": str(row.get("名称", "")).strip(),
                        "price": safe_float(row.get("最新价")),
                        "pct": safe_float(row.get("涨跌幅")),
                        "change_val": safe_float(row.get("涨跌额")),
                        "vol": safe_float(row.get("成交量")),
                        "amount": safe_float(row.get("成交额")),
                        "amplitude": safe_float(row.get("振幅")),
                        "high": safe_float(row.get("最高")),
                        "low": safe_float(row.get("最低")),
                        "open": safe_float(row.get("今开")),
                        "last_close": safe_float(row.get("昨收")),
                        "turnover": safe_float(row.get("换手率")),
                        "pe_dynamic": safe_float(row.get("市盈率-动态")),
                        "pb": safe_float(row.get("市净率")),
                        "listing_date": str(row.get("上市日期", "") or "").split(" ")[0].strip(),
                        "total_mv": safe_float(row.get("总市值")),
                        "float_mv": safe_float(row.get("流通市值")),
                    }
                return spot_dict
        except Exception as e:
            logger.debug(f"akshare 获取新股行情异常: {e}")

        return spot_dict

    def get_combined_new_stocks(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        获取综合新股与次新股数据表（聚合行情 + IPO日历 + 策略状态 + 极速补齐全量字段 + 磁盘持久化）
        """
        now = time.time()
        if not force_refresh and self._cached_stocks_df is not None and not self._cached_stocks_df.empty and (now - self._last_fetch_time < self._cache_ttl_seconds):
            return self._cached_stocks_df

        ipo_dict = self.fetch_ipo_calendar(page_size=100, force=force_refresh)
        spot_dict = self.fetch_recent_new_stocks_spot()

        all_codes = set(ipo_dict.keys()) | set(spot_dict.keys())
        
        # 若网络接口全部受阻，确保使用本地持久化日历
        if not all_codes:
            if self._cached_stocks_df is not None and not self._cached_stocks_df.empty:
                return self._cached_stocks_df
            self._load_persisted_data()
            all_codes = set(self._cached_ipo_dict.keys())

        rows = []
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        for c in all_codes:
            ipo_info = ipo_dict.get(c, {})
            spot_info = spot_dict.get(c, {})

            name = spot_info.get("name") or ipo_info.get("name") or c
            listing_date = spot_info.get("listing_date") or ipo_info.get("listing_date") or ""
            apply_date = ipo_info.get("apply_date") or ""
            issue_price = ipo_info.get("issue_price")

            # 状态推断
            status = "次新"
            if not listing_date or listing_date > today_str:
                status = "待上市"
            elif listing_date == today_str:
                status = "首日(N)"
            else:
                try:
                    ld = datetime.datetime.strptime(listing_date, "%Y-%m-%d").date()
                    delta_days = (datetime.date.today() - ld).days
                    if delta_days <= 7:
                        status = "前5日(C)"
                    elif delta_days <= 90:
                        status = "次新"
                    else:
                        status = "已上市"
                except Exception:
                    status = "次新"

            price = safe_float(spot_info.get("price", 0.0))
            turnover = safe_float(spot_info.get("turnover", 0.0))
            float_mv = safe_float(spot_info.get("float_mv", 0.0))
            total_mv = safe_float(spot_info.get("total_mv", 0.0))
            amount = safe_float(spot_info.get("amount", 0.0))

            is_first_day = ("首日" in status) or ("N" in status)
            if is_first_day:
                pct = safe_float(spot_info.get("pct", 0.0))
            else:
                last_c = safe_float(spot_info.get("last_close", 0.0))
                if last_c > 0 and price > 0:
                    pct = round((price - last_c) / last_c * 100.0, 2)
                else:
                    pct = 0.0

            float_mv_yi = round(float_mv / 1e8, 2) if float_mv > 1e4 else (float_mv if float_mv > 0 else 0.0)
            total_mv_yi = round(total_mv / 1e8, 2) if total_mv > 1e4 else (total_mv if total_mv > 0 else 0.0)
            amount_yi = round(amount / 1e8, 2) if amount > 1e4 else (amount if amount > 0 else 0.0)

            # 策略配置状态检测
            has_strategy = self._check_strategy_exists(c)

            rows.append({
                "code": c,
                "name": name,
                "status": status,
                "listing_date": listing_date if listing_date else "-",
                "apply_date": apply_date if apply_date else "-",
                "issue_price": issue_price if issue_price is not None else 0.0,
                "price": price,
                "pct": pct,
                "turnover": turnover,
                "float_mv_yi": float_mv_yi,
                "total_mv_yi": total_mv_yi,
                "amount_yi": amount_yi,
                "has_strategy": has_strategy,
                "trade_market": ipo_info.get("trade_market", ""),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df.drop_duplicates(subset=["code"], keep="first", inplace=True)
            # 排序：首日/前5日 > 待上市 > 次新股，同类按上市日期倒序
            def _sort_weight(row):
                st = row["status"]
                ld = row["listing_date"]
                w = 4
                if "首日" in st: w = 1
                elif "前5日" in st: w = 2
                elif "待上市" in st: w = 3
                elif "次新" in st: w = 4
                return (w, ld if ld != "-" else "1970-01-01")

            df["_sort"] = df.apply(_sort_weight, axis=1)
            df.sort_values(by=["_sort"], ascending=[True], inplace=True)
            df.drop(columns=["_sort"], inplace=True)
            df.reset_index(drop=True, inplace=True)

            # 极速秒级多通道补齐全量字段（TDX 权威直连 + 腾讯行情 + 股本计算）
            df = self.enrich_with_tdx_realtime(df)

            # 写入磁盘持久化
            self._save_persisted_stocks_df(df)

        self._cached_stocks_df = df
        self._last_fetch_time = time.time()
        return df

    def enrich_with_tdx_realtime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        利用 TDX API 权威行情 + 真实流通股本换手率计算 + 腾讯行情覆盖全量新股/次新股补齐全量数据
        """
        if df.empty:
            return df

        codes_to_query = df["code"].tolist()
        quote_map: Dict[str, Dict[str, Any]] = {}

        # ── 通道 1: TDXRealtimeFetcher 权威直连 (现价、昨收、成交量、成交额、流通市值、换手率) ──
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            tdx_fetcher = TDXRealtimeFetcher.get_instance()
            chunk_size = 50
            for i in range(0, len(codes_to_query), chunk_size):
                chunk = codes_to_query[i:i + chunk_size]
                quotes = tdx_fetcher.get_security_quotes_safe(chunk)
                if quotes:
                    for q in quotes:
                        c_clean = str(q.get("code", "")).strip().zfill(6)
                        p = safe_float(q.get("price", 0.0))
                        last_c = safe_float(q.get("last_close", 0.0))
                        amt = safe_float(q.get("amount", 0.0))
                        vol = safe_float(q.get("vol", 0.0)) # 手
                        op_p = safe_float(q.get("open", 0.0))

                        if c_clean and (p > 0 or last_c > 0):
                            if c_clean not in quote_map:
                                quote_map[c_clean] = {}
                            if p > 0:
                                quote_map[c_clean]["price"] = p
                            if last_c > 0:
                                quote_map[c_clean]["last_close"] = last_c
                            if p > 0 and last_c > 0:
                                quote_map[c_clean]["pct"] = round((p - last_c) / last_c * 100.0, 2)
                            if amt > 0:
                                quote_map[c_clean]["amount"] = amt
                            if op_p > 0:
                                quote_map[c_clean]["open"] = op_p

                            # 💡 从 TDX 获取真实流通股本计算流通市值与换手率
                            if p > 0:
                                shares = tdx_fetcher.get_circulation_shares(c_clean)
                                if shares > 0:
                                    fmv = round(p * shares / 1e8, 2)
                                    quote_map[c_clean]["float_mv_yi"] = fmv
                                    if vol > 0:
                                        # vol 单位是手 (1手=100股)
                                        to_rate = round((vol * 100.0) / shares * 100.0, 2)
                                        quote_map[c_clean]["turnover"] = to_rate
        except Exception as e:
            logger.debug(f"TDX 补齐行情异常: {e}")

        # ── 通道 2: 腾讯行情 API 直连 (分批覆盖未有换手率/总市值的标的) ──
        try:
            session = _get_direct_session()
            chunk_size = 80
            for i in range(0, len(codes_to_query), chunk_size):
                chunk = codes_to_query[i:i + chunk_size]
                formatted_list = []
                for c in chunk:
                    c_str = str(c).zfill(6)
                    if c_str.startswith(("60", "68")):
                        formatted_list.append(f"sh{c_str}")
                    elif c_str.startswith(("920", "83", "87", "88", "43")):
                        formatted_list.append(f"bj{c_str}")
                    else:
                        formatted_list.append(f"sz{c_str}")

                if formatted_list:
                    url = f"http://qt.gtimg.cn/q={','.join(formatted_list)}"
                    r = session.get(url, headers=DEFAULT_HEADERS, timeout=2.5)
                    if r.status_code == 200:
                        for line in r.text.split(";"):
                            line = line.strip()
                            if not line or "=" not in line:
                                continue
                            parts = line.split("=")
                            vals = parts[1].strip('"').split("~")
                            if len(vals) > 45:
                                c_raw = str(vals[2]).strip().zfill(6)
                                p_now = safe_float(vals[3])
                                p_close = safe_float(vals[4])
                                p_open = safe_float(vals[5])
                                p_vol = safe_float(vals[36])
                                p_amt = safe_float(vals[37]) * 10000.0 if vals[37] else 0.0
                                p_pct = safe_float(vals[32])
                                p_to = safe_float(vals[38])
                                p_fmv = safe_float(vals[44])
                                p_tmv = safe_float(vals[45])

                                if c_raw not in quote_map:
                                    quote_map[c_raw] = {}
                                
                                if "price" not in quote_map[c_raw] and p_now > 0:
                                    quote_map[c_raw]["price"] = p_now
                                if "last_close" not in quote_map[c_raw] and p_close > 0:
                                    quote_map[c_raw]["last_close"] = p_close
                                if "pct" not in quote_map[c_raw]:
                                    quote_map[c_raw]["pct"] = p_pct
                                if "amount" not in quote_map[c_raw] and p_amt > 0:
                                    quote_map[c_raw]["amount"] = p_amt
                                if "turnover" not in quote_map[c_raw] and p_to > 0:
                                    quote_map[c_raw]["turnover"] = p_to
                                if "float_mv_yi" not in quote_map[c_raw] and p_fmv > 0:
                                    quote_map[c_raw]["float_mv_yi"] = p_fmv
                                if "total_mv_yi" not in quote_map[c_raw] and p_tmv > 0:
                                    quote_map[c_raw]["total_mv_yi"] = p_tmv
        except Exception as e:
            logger.debug(f"腾讯行情补齐异常: {e}")

        # ── 3. 权威回填更新到 DataFrame ──
        for idx, row in df.iterrows():
            c = str(row["code"]).zfill(6)
            st = str(row.get("status", ""))
            is_first_day = ("首日" in st) or ("N" in st)
            issue_p = safe_float(row.get("issue_price", 0.0))

            if c in quote_map:
                q = quote_map[c]
                p = safe_float(q.get("price", 0.0))
                last_c = safe_float(q.get("last_close", 0.0))

                if p > 0:
                    df.at[idx, "price"] = p

                    # 涨跌幅计算
                    if last_c > 0:
                        df.at[idx, "pct"] = round((p - last_c) / last_c * 100.0, 2)
                    elif "pct" in q and q["pct"] is not None and not math.isnan(safe_float(q["pct"])):
                        df.at[idx, "pct"] = round(safe_float(q["pct"]), 2)
                    elif is_first_day and issue_p > 0:
                        df.at[idx, "pct"] = round((p - issue_p) / issue_p * 100.0, 2)

                # 成交额
                amt = safe_float(q.get("amount", 0.0))
                if amt > 0:
                    df.at[idx, "amount_yi"] = round(amt / 1e8, 2)

                # 换手率
                to_val = safe_float(q.get("turnover", 0.0))
                if to_val > 0:
                    df.at[idx, "turnover"] = to_val

                # 流通市值
                fmv = safe_float(q.get("float_mv_yi", 0.0))
                if fmv > 0:
                    df.at[idx, "float_mv_yi"] = fmv

                # 总市值
                tmv = safe_float(q.get("total_mv_yi", 0.0))
                if tmv > 0:
                    df.at[idx, "total_mv_yi"] = tmv

        return df

    def _check_strategy_exists(self, code: str) -> bool:
        """检查指定股票代码是否已有分时阶梯策略配置"""
        cfg_path = os.path.join(get_app_root(), "config", "intraday_newstock_strategies.json")
        if not os.path.exists(cfg_path):
            return False
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                strategies = data.get("strategies", {})
                return any(str(st.get("code", "")).zfill(6) == code for st in strategies.values())
        except Exception:
            return False
