# -*- coding: utf-8 -*-
"""
ats/new_stock_fetcher.py — ATS 新股/次新股/IPO发行日历全市场多通道数据与磁盘持久化引擎
职责：
1. 【已上市个股免重复请求与自动持久化】：已缓存过且已上市的新股基础发行日历永久固化在本地 config/new_stock_ipo_calendar.json，东方财富 API 仅在后台增量补充最新未上市/新发行标的；
2. 【TDX API 绝对最高优先级】：现价、昨收、涨跌幅、成交额、成交量、开盘价、最高价、最低价全由 TDX 直连驱动；
3. 【权威股本换手率与市值推演】：通过 TDX get_batch_finance_shares 批量获取真实流通股本与总股本，精准计算流通市值(亿)、总市值(亿)与换手率(%)，彻底根治数据遗失与 `--` 占位符；
4. 【冷启动 0 秒展示与网络异常 100% 无缝降级】：无论网络/代理是否波动，启动瞬间 100% 呈现完整新股数据，绝无 0 标的。
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
from typing import Dict, List, Any, Optional, Tuple, Set

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
    {"code": "688828", "name": "国仪公司", "trade_market": "科创板", "issue_price": 21.22, "apply_date": "2026-07-31", "listing_date": "2026-08-11", "status": "次新"},
    {"code": "301717", "name": "超纯应材", "trade_market": "创业板", "issue_price": 65.99, "apply_date": "2026-07-31", "listing_date": "2026-08-11", "status": "次新"},
    {"code": "688635", "name": "长进光子", "trade_market": "科创板", "issue_price": 40.98, "apply_date": "2026-05-18", "listing_date": "2026-05-27", "status": "次新"},
    {"code": "688808", "name": "联讯仪器", "trade_market": "科创板", "issue_price": 81.88, "apply_date": "2026-04-14", "listing_date": "2026-04-24", "status": "已上市"},
    {"code": "920093", "name": "信胜科技", "trade_market": "北交所", "issue_price": 14.35, "apply_date": "2026-08-12", "listing_date": "2026-08-21", "status": "前5日(C)"},
    {"code": "301655", "name": "绿控传动", "trade_market": "创业板", "issue_price": 8.50, "apply_date": "2026-08-10", "listing_date": "2026-08-20", "status": "前5日(C)"},
    {"code": "688836", "name": "宇树科技", "trade_market": "科创板", "issue_price": 150.80, "apply_date": "2026-08-10", "listing_date": "2026-08-19", "status": "前5日(C)"},
    {"code": "920059", "name": "双英集团", "trade_market": "北交所", "issue_price": 11.13, "apply_date": "2026-08-10", "listing_date": "2026-08-19", "status": "前5日(C)"},
    {"code": "688826", "name": "频准激光", "trade_market": "科创板", "issue_price": 186.88, "apply_date": "2026-08-07", "listing_date": "2026-08-18", "status": "前5日(C)"},
    {"code": "920107", "name": "恒兴股份", "trade_market": "北交所", "issue_price": 16.02, "apply_date": "2026-08-05", "listing_date": "2026-08-17", "status": "前5日(C)"},
    {"code": "920138", "name": "杰理科技", "trade_market": "北交所", "issue_price": 18.86, "apply_date": "2026-08-03", "listing_date": "2026-08-12", "status": "次新"},
    {"code": "920012", "name": "创达新材", "trade_market": "北交所", "issue_price": 19.58, "apply_date": "2026-04-01", "listing_date": "2026-04-13", "status": "已上市"},
    {"code": "920078", "name": "族兴新材", "trade_market": "北交所", "issue_price": 6.98, "apply_date": "2026-03-09", "listing_date": "2026-03-18", "status": "已上市"},
    {"code": "001232", "name": "嘉立创", "trade_market": "深主板", "issue_price": 84.46, "apply_date": "2026-07-24", "listing_date": "2026-08-04", "status": "次新"},
    {"code": "301683", "name": "慧谷新材", "trade_market": "创业板", "issue_price": 78.38, "apply_date": "2026-03-20", "listing_date": "2026-04-01", "status": "已上市"},
    {"code": "301682", "name": "宏明电子", "trade_market": "创业板", "issue_price": 69.66, "apply_date": "2026-03-16", "listing_date": "2026-03-25", "status": "已上市"},
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
        self._cache_ttl_seconds: float = 2.0  # 2秒内存缓存，满足高频实时刷新

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
                        items = data.get("items", {})
                        if isinstance(items, dict) and items:
                            self._cached_ipo_dict = items
                            self._last_calendar_fetch_time = float(data.get("updated_at", 0.0))
                            logger.info(f"✅ 成功从磁盘恢复 IPO 日历: 共 {len(self._cached_ipo_dict)} 条记录")
            except Exception as e:
                logger.debug(f"加载 IPO 日历持久化文件异常: {e}")

        # 若无磁盘日历或数据不全，注入出厂预置数据
        for item in FACTORY_DEFAULT_NEW_STOCKS:
            c = item["code"]
            if c not in self._cached_ipo_dict:
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
        从东方财富 IPO 日历接口增量拉取最新发行与上市新股列表:
        - 【增量合并原则】：对于已在本地缓存且已上市的个股信息永久保留、不再重复请求；
        - 仅拉取与增量更新待上市/最新申购的新标的；
        - 网络异常时 100% 自动降级使用本地持久化日历。
        """
        now = time.time()
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        # 6 小时防频控：非强制刷新且本地缓存已有数据时直接复用，杜绝高频请求被封 IP
        if not force and self._cached_ipo_dict and (now - self._last_calendar_fetch_time < 6 * 3600):
            return self._cached_ipo_dict

        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            "reportName=RPTA_APP_IPOAPPLY&"
            "columns=SECURITY_CODE,SECURITY_NAME,TRADE_MARKET,APPLY_CODE,ISSUE_PRICE,APPLY_DATE,LISTING_DATE,ONLINE_ISSUE_NUM,BALLOT_NUM&"
            f"pageNumber=1&pageSize={page_size}&sortColumns=APPLY_DATE&sortTypes=-1&source=WEB&client=WEB"
        )
        try:
            session = _get_direct_session()
            resp = session.get(url, headers=DEFAULT_HEADERS, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("result", {}).get("data", []) if data.get("result") else []
                new_added_count = 0
                for it in items:
                    c = str(it.get("SECURITY_CODE", "")).strip().zfill(6)
                    if not c:
                        continue
                    
                    # 💡 若本地已有该股票且该股票已确认上市，绝不覆盖已有正确基础信息
                    if c in self._cached_ipo_dict:
                        existing = self._cached_ipo_dict[c]
                        ex_ld = existing.get("listing_date", "")
                        if ex_ld and ex_ld != "-" and ex_ld <= today_str and existing.get("issue_price"):
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

                    self._cached_ipo_dict[c] = {
                        "code": c,
                        "name": str(it.get("SECURITY_NAME", "")).strip(),
                        "trade_market": str(it.get("TRADE_MARKET", "")).strip(),
                        "apply_code": str(it.get("APPLY_CODE", "")).strip(),
                        "issue_price": issue_price_val if issue_price_val > 0 else (self._cached_ipo_dict.get(c, {}).get("issue_price") or 0.0),
                        "apply_date": apply_d or self._cached_ipo_dict.get(c, {}).get("apply_date", ""),
                        "listing_date": listing_d or self._cached_ipo_dict.get(c, {}).get("listing_date", ""),
                        "online_issue_num": online_num_val if online_num_val > 0 else None,
                        "ballot_num": ballot_num,
                    }
                    new_added_count += 1

                self._last_calendar_fetch_time = time.time()
                self._save_persisted_ipo_calendar()
                logger.info(f"✅ 东方财富增量 IPO 日历同步完成: 现存共 {len(self._cached_ipo_dict)} 条记录 (新增/更新: {new_added_count})")
                return self._cached_ipo_dict
        except Exception as e:
            logger.debug(f"直连拉取东方财富增量 IPO 日历异常: {e}，自动平滑降级至本地持久化日历")

        # 降级：返回内存或磁盘已持久化的日历
        if not self._cached_ipo_dict:
            self._load_persisted_data()
        return self._cached_ipo_dict

    def get_combined_new_stocks(self, force_refresh: bool = False, segment_mode: str = "30m") -> pd.DataFrame:
        """
        获取综合新股与次新股数据表:
        - 基础日历来自本地增量持久化日历；
        - 所有实时行情（现价、昨收、涨跌幅、成交额、成交量、换手率、流通市值、总市值、分段涨速、VWAP偏离）100% 由 TDX API 权威直连计算赋予；
        - 计算完成后自动原子落盘保存至 config/new_stock_data_cache.json。
        """
        now = time.time()
        # ⚡ [0 毫秒冷启动即显与高频实时刷新] 非强制刷新时，在 TTL 有效期内直接复用内存缓存；超过 TTL 时自动拉取最新行情
        if not force_refresh and self._cached_stocks_df is not None and not self._cached_stocks_df.empty and (now - self._last_fetch_time < self._cache_ttl_seconds):
            return self._cached_stocks_df

        if self._cached_stocks_df is None or self._cached_stocks_df.empty:
            self._load_persisted_data()

        ipo_dict = self.fetch_ipo_calendar(page_size=100, force=force_refresh)

        all_codes = set(ipo_dict.keys())
        if not all_codes:
            if self._cached_stocks_df is not None and not self._cached_stocks_df.empty:
                return self._cached_stocks_df
            self._load_persisted_data()
            all_codes = set(self._cached_ipo_dict.keys())

        rows = []
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        for c in all_codes:
            ipo_info = ipo_dict.get(c, {})

            name = ipo_info.get("name") or c
            listing_date = ipo_info.get("listing_date") or ""
            apply_date = ipo_info.get("apply_date") or ""
            issue_price = safe_float(ipo_info.get("issue_price", 0.0))

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

            # 策略配置状态检测
            has_strategy = self._check_strategy_exists(c)

            rows.append({
                "code": c,
                "name": name,
                "status": status,
                "listing_date": listing_date if listing_date else "-",
                "apply_date": apply_date if apply_date else "-",
                "issue_price": issue_price if issue_price > 0 else 0.0,
                "price": 0.0,
                "pct": 0.0,
                "turnover": 0.0,
                "float_mv_yi": 0.0,
                "total_mv_yi": 0.0,
                "amount_yi": 0.0,
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

            # ⚡ 权威极速赋能：由 TDX API 直连赋予全部实时行情、真实股本、换手率与总/流通市值、分段涨速与VWAP
            df = self.enrich_with_tdx_realtime(df, force=force_refresh, segment_mode=segment_mode)

            # 写入磁盘持久化
            self._save_persisted_stocks_df(df)

        self._cached_stocks_df = df
        self._last_fetch_time = time.time()
        return df

    def enrich_with_tdx_realtime(self, df: pd.DataFrame, force: bool = False, segment_mode: str = "30m") -> pd.DataFrame:
        """
        利用 TDX API 权威行情 + 真实流通股本/总股本批量推算全量新股数据 (最高绝对优先级)
        计算 15分/30分/60分分段涨速及日内均线 VWAP 与 VWAP 偏离度。
        带【历史有效数据无损继承】：只要历史成功获取过有效现价与市值，绝不因临时网络波动清零为 `--`！
        """
        if df.empty:
            return df

        # 建立历史有效数据字典
        history_map: Dict[str, Dict[str, Any]] = {}
        if self._cached_stocks_df is not None and not self._cached_stocks_df.empty:
            for _, r in self._cached_stocks_df.iterrows():
                c_k = str(r.get("code", "")).strip().zfill(6)
                if c_k and safe_float(r.get("price", 0.0)) > 0:
                    history_map[c_k] = r.to_dict()

        codes_to_query = df["code"].tolist()
        quote_map: Dict[str, Dict[str, Any]] = {}

        now_ts = time.time()
        # ── 通道 1: TDXRealtimeFetcher 权威直连 (现价、昨收、成交量、成交额、流通市值、总市值、换手率、分段涨速、VWAP) ──
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            tdx_fetcher = TDXRealtimeFetcher.get_instance()
            
            # 1. 批量快速获取全部标的的真实流通股本与总股本
            shares_dict = tdx_fetcher.get_batch_finance_shares(codes_to_query)

            chunk_size = 40
            for i in range(0, len(codes_to_query), chunk_size):
                chunk = codes_to_query[i:i + chunk_size]
                quotes = tdx_fetcher.get_security_quotes_safe(chunk, force=force)
                if quotes:
                    for q in quotes:
                        c_clean = str(q.get("code", "")).strip().zfill(6)
                        if not c_clean:
                            continue

                        # ⚡ 提取价格与盘口数据 (全面支持 09:15~09:25 集合竞价试撮合阶段)
                        p = safe_float(q.get("price", 0.0))
                        last_c = safe_float(q.get("last_close", 0.0))
                        amt = safe_float(q.get("amount", 0.0))
                        vol = safe_float(q.get("vol", 0.0))  # 手
                        op_p = safe_float(q.get("open", 0.0))
                        hi_p = safe_float(q.get("high", 0.0))
                        lo_p = safe_float(q.get("low", 0.0))
                        bid1_p = safe_float(q.get("bid1", 0.0))
                        ask1_p = safe_float(q.get("ask1", 0.0))
                        bid1_v = safe_float(q.get("bid_vol1", 0.0))
                        ask1_v = safe_float(q.get("ask_vol1", 0.0))

                        # ⚡ 集合竞价 (09:15~09:25) 及连续交易有效参考价与委托量推导
                        effective_p = p if p > 0 else (bid1_p if bid1_p > 0 else (ask1_p if ask1_p > 0 else (op_p if op_p > 0 else 0.0)))
                        effective_vol = vol if vol > 0 else (bid1_v if bid1_v > 0 else ask1_v)
                        effective_amt = amt if amt > 0 else (round(effective_p * effective_vol * 100.0, 2) if (effective_p > 0 and effective_vol > 0) else 0.0)

                        bid_vol_sum = 0.0
                        ask_vol_sum = 0.0
                        for d_i in range(1, 6):
                            bid_vol_sum += safe_float(q.get(f"bid_vol{d_i}", 0.0))
                            ask_vol_sum += safe_float(q.get(f"ask_vol{d_i}", 0.0))
                        total_d = bid_vol_sum + ask_vol_sum
                        bid_p = round((bid_vol_sum / total_d) * 100.0, 1) if total_d > 0 else 50.0

                        # 竞价单量与金额 (万元)
                        b_vol = vol if vol > 0 else (bid1_v if bid1_v > 0 else ask1_v)
                        b_amt = b_vol * 100.0 * effective_p if (b_vol > 0 and effective_p > 0) else 0.0
                        b_amt_wan = round(b_amt / 10000.0, 1)

                        # ⚡ 交易时段分段（默认30分/支持60分等）价格/量能记忆与区间涨速引擎
                        seg_res = tdx_fetcher.calculate_segmented_velocity(
                            code=c_clean,
                            price=effective_p,
                            open_price=op_p if op_p > 0 else effective_p,
                            last_close=last_c if last_c > 0 else effective_p,
                            vol=effective_vol,
                            amount=effective_amt,
                            now_ts=now_ts,
                            segment_mode=segment_mode
                        )

                        # ⚡ 日内分时均价 VWAP (元) 与 VWAP 偏离度 (%)
                        if effective_vol > 0 and effective_amt > 0:
                            calc_vwap = effective_amt / (effective_vol * 100.0)
                            if effective_p > 0 and (effective_p * 0.7 <= calc_vwap <= effective_p * 1.3):
                                vwap = round(calc_vwap, 2)
                            else:
                                vwap = round((op_p + hi_p + lo_p + effective_p) / 4.0, 2) if op_p > 0 else effective_p
                        else:
                            vwap = effective_p if effective_p > 0 else (op_p if op_p > 0 else 0.0)

                        vwap_dev_pct = round((effective_p - vwap) / vwap * 100.0, 2) if vwap > 0 else 0.0

                        if c_clean and (effective_p > 0 or last_c > 0):
                            if c_clean not in quote_map:
                                quote_map[c_clean] = {}
                            if effective_p > 0:
                                quote_map[c_clean]["price"] = effective_p
                            if last_c > 0:
                                quote_map[c_clean]["last_close"] = last_c
                            if effective_p > 0 and last_c > 0:
                                quote_map[c_clean]["pct"] = round((effective_p - last_c) / last_c * 100.0, 2)
                            if effective_amt > 0:
                                quote_map[c_clean]["amount"] = effective_amt
                            if op_p > 0:
                                quote_map[c_clean]["open"] = op_p
                            if hi_p > 0:
                                quote_map[c_clean]["high"] = hi_p
                            if lo_p > 0:
                                quote_map[c_clean]["low"] = lo_p

                            quote_map[c_clean]["bid_pressure"] = bid_p
                            quote_map[c_clean]["bidding_amt_wan"] = b_amt_wan
                            quote_map[c_clean]["bidding_vol"] = b_vol

                            # 分段涨速与 VWAP 写入 quote_map
                            quote_map[c_clean]["velocity_pct"] = seg_res.get("velocity_pct", 0.0)
                            quote_map[c_clean]["velocity_tag"] = seg_res.get("velocity_tag", "⏱️ 窄幅横盘")
                            quote_map[c_clean]["segment_label"] = seg_res.get("segment_label", "⏱️ 30分分段")
                            quote_map[c_clean]["segment_base_price"] = seg_res.get("segment_base_price", effective_p)
                            quote_map[c_clean]["segment_vol_increment"] = seg_res.get("segment_vol_increment", 0.0)
                            quote_map[c_clean]["segment_amount_wan"] = seg_res.get("segment_amount_wan", 0.0)
                            quote_map[c_clean]["is_midway_init"] = seg_res.get("is_midway_init", False)
                            quote_map[c_clean]["vwap"] = vwap
                            quote_map[c_clean]["vwap_dev_pct"] = vwap_dev_pct

                            # 💡 权威推算流通市值、总市值与换手率 (支持集合竞价)
                            lt_shares, zg_shares = shares_dict.get(c_clean, (0.0, 0.0))
                            if effective_p > 0:
                                if lt_shares > 0:
                                    fmv = round(effective_p * lt_shares / 1e8, 2)
                                    quote_map[c_clean]["float_mv_yi"] = fmv
                                    if effective_vol > 0:
                                        to_rate = round((effective_vol * 100.0) / lt_shares * 100.0, 2)
                                        quote_map[c_clean]["turnover"] = to_rate
                                if zg_shares > 0:
                                    tmv = round(effective_p * zg_shares / 1e8, 2)
                                    quote_map[c_clean]["total_mv_yi"] = tmv
        except Exception as e:
            logger.debug(f"TDX 权威补齐行情异常: {e}")

        # ── 通道 2: 腾讯行情 API 备用兜底 (若 TDX 实在未命中时补充) ──
        try:
            missing_codes = [c for c in codes_to_query if c not in quote_map or quote_map[c].get("price", 0) <= 0]
            if missing_codes:
                session = _get_direct_session()
                chunk_size = 80
                for i in range(0, len(missing_codes), chunk_size):
                    chunk = missing_codes[i:i + chunk_size]
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
                        r = session.get(url, headers=DEFAULT_HEADERS, timeout=2.0)
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
                                    p_amt = safe_float(vals[37]) * 10000.0 if vals[37] else 0.0
                                    p_pct = safe_float(vals[32])
                                    p_to = safe_float(vals[38])
                                    p_fmv = safe_float(vals[44])
                                    p_tmv = safe_float(vals[45])
                                    p_bid1 = safe_float(vals[9]) if len(vals) > 9 else 0.0
                                    p_ask1 = safe_float(vals[19]) if len(vals) > 19 else 0.0

                                    eff_p_tx = p_now if p_now > 0 else (p_bid1 if p_bid1 > 0 else (p_ask1 if p_ask1 > 0 else p_open))

                                    if c_raw not in quote_map:
                                        quote_map[c_raw] = {}
                                    if "price" not in quote_map[c_raw] and eff_p_tx > 0:
                                        quote_map[c_raw]["price"] = eff_p_tx
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
                                    if "vwap" not in quote_map[c_raw] and eff_p_tx > 0:
                                        quote_map[c_raw]["vwap"] = eff_p_tx
                                        quote_map[c_raw]["vwap_dev_pct"] = 0.0
                                        quote_map[c_raw]["velocity_pct"] = 0.0
        except Exception as e:
            logger.debug(f"腾讯行情备用补齐异常: {e}")

        # ── 3. 权威回填更新到 DataFrame (带历史有效无损继承) ──
        for idx, row in df.iterrows():
            c = str(row["code"]).zfill(6)
            st = str(row.get("status", ""))
            nm = str(row.get("name", ""))
            today_s = datetime.date.today().strftime("%Y-%m-%d")
            list_d = str(row.get("listing_date", "")).strip()[:10]
            # 严格首日判定：状态为首日/今日上市，或上市日为今日，或名称以 N 开头且无早于今日的历史上市日；严禁按 920 盲目全量判定！
            is_first_day = ("首日" in st) or (st == "今日上市") or (list_d == today_s) or (nm.startswith("N") and list_d in ("", today_s, "-"))
            issue_p = safe_float(row.get("issue_price", 0.0))

            # 优先从本轮获取字典中取
            q = quote_map.get(c, {})
            p = safe_float(q.get("price", 0.0))
            last_c = safe_float(q.get("last_close", 0.0))

            # 🛡️ 历史有效数据无损继承 (若本轮未拉取到价格，继承历史已有的有效现价)
            if p <= 0 and c in history_map:
                h = history_map[c]
                h_p = safe_float(h.get("price", 0.0))
                if h_p > 0:
                    p = h_p
                    last_c = safe_float(h.get("last_close", 0.0))
                    if "turnover" not in q: q["turnover"] = safe_float(h.get("turnover", 0.0))
                    if "float_mv_yi" not in q: q["float_mv_yi"] = safe_float(h.get("float_mv_yi", 0.0))
                    if "total_mv_yi" not in q: q["total_mv_yi"] = safe_float(h.get("total_mv_yi", 0.0))
                    if "amount_yi" not in q: q["amount_yi"] = safe_float(h.get("amount_yi", 0.0))
                    if "pct" not in q: q["pct"] = safe_float(h.get("pct", 0.0))
                    if "velocity_pct" not in q: q["velocity_pct"] = safe_float(h.get("velocity_pct", 0.0))
                    if "velocity_tag" not in q: q["velocity_tag"] = h.get("velocity_tag", "⏱️ 窄幅横盘")
                    if "segment_label" not in q: q["segment_label"] = h.get("segment_label", "⏱️ 30分分段")
                    if "segment_base_price" not in q: q["segment_base_price"] = safe_float(h.get("segment_base_price", p))
                    if "segment_amount_wan" not in q: q["segment_amount_wan"] = safe_float(h.get("segment_amount_wan", 0.0))
                    if "is_midway_init" not in q: q["is_midway_init"] = bool(h.get("is_midway_init", False))
                    if "vwap" not in q: q["vwap"] = safe_float(h.get("vwap", p))
                    if "vwap_dev_pct" not in q: q["vwap_dev_pct"] = safe_float(h.get("vwap_dev_pct", 0.0))

            if p > 0:
                df.at[idx, "price"] = p

                # 涨跌幅精确计算
                if last_c > 0:
                    df.at[idx, "pct"] = round((p - last_c) / last_c * 100.0, 2)
                elif "pct" in q and q["pct"] is not None and not math.isnan(safe_float(q["pct"])):
                    df.at[idx, "pct"] = round(safe_float(q["pct"]), 2)
                elif is_first_day and issue_p > 0:
                    df.at[idx, "pct"] = round((p - issue_p) / issue_p * 100.0, 2)

            # 成交额
            amt = safe_float(q.get("amount", 0.0))
            if amt > 10000:
                df.at[idx, "amount_yi"] = round(amt / 1e8, 2)
            elif amt > 0:
                df.at[idx, "amount_yi"] = round(amt, 2)
            elif "amount_yi" in q and safe_float(q["amount_yi"]) > 0:
                df.at[idx, "amount_yi"] = safe_float(q["amount_yi"])

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

            # ⚡ 分段涨速与 VWAP 赋值
            df.at[idx, "velocity_pct"] = safe_float(q.get("velocity_pct", 0.0))
            df.at[idx, "velocity_tag"] = q.get("velocity_tag", "⏱️ 窄幅横盘")
            df.at[idx, "segment_label"] = q.get("segment_label", "⏱️ 30分分段")
            df.at[idx, "segment_base_price"] = safe_float(q.get("segment_base_price", p if p > 0 else issue_p))
            df.at[idx, "segment_amount_wan"] = safe_float(q.get("segment_amount_wan", 0.0))
            df.at[idx, "is_midway_init"] = bool(q.get("is_midway_init", False))

            vwap_val = safe_float(q.get("vwap", 0.0))
            if vwap_val <= 0:
                vwap_val = p if p > 0 else issue_p
            df.at[idx, "vwap"] = vwap_val

            vwap_dev_val = safe_float(q.get("vwap_dev_pct", 0.0))
            if vwap_dev_val == 0.0 and p > 0 and vwap_val > 0 and abs(p - vwap_val) > 1e-4:
                vwap_dev_val = round((p - vwap_val) / vwap_val * 100.0, 2)
            df.at[idx, "vwap_dev_pct"] = vwap_dev_val

            # 💡 集合竞价策略信号判定与关键信息同步
            b_amt_wan = safe_float(q.get("bidding_amt_wan", 0.0))
            bid_p = safe_float(q.get("bid_pressure", 50.0))
            pct_curr = safe_float(df.at[idx, "pct"]) if "pct" in df.columns else 0.0

            # 首日估值健康度
            is_healthy_ipo = True
            if is_first_day and issue_p > 0 and p > 0:
                ipo_pct = round((p - issue_p) / issue_p * 100.0, 1)
                is_healthy_ipo = (ipo_pct <= 220.0)

            if is_first_day and (b_amt_wan >= 500.0 or b_amt_wan >= 80.0) and is_healthy_ipo:
                bidding_tag = "💎 首日真金抢筹"
                bidding_advice = "09:25黄金上车点 (防开盘极速脉冲)"
            elif pct_curr >= 9.5 and (bid_p >= 75.0 or b_amt_wan >= 2000.0):
                bidding_tag = "👑 竞价一字顶格"
                bidding_advice = "集合竞价一字顶格，主力顶格锁仓"
            elif (pct_curr >= 4.0) and (b_amt_wan >= 1500.0 or bid_p >= 75.0):
                bidding_tag = "💎 竞价爆量突破"
                bidding_advice = "竞价大单爆量跳空突破，极速主升先锋"
            elif (pct_curr >= 3.0) and (b_amt_wan >= 500.0 or bid_p >= 65.0):
                bidding_tag = "🚀 竞价极速抢筹"
                bidding_advice = "不可撤单高开抢筹，先手观察点"
            elif pct_curr >= 3.0 and (b_amt_wan < 100.0 or bid_p <= 40.0):
                bidding_tag = "⚠️ 竞价缩量诱多"
                bidding_advice = "缩量假高开，卖盘压制防砸"
            else:
                bidding_tag = "⏱️ 常规博弈" if (p > 0 and b_amt_wan > 0) else "--"
                bidding_advice = "常规博弈观望"

            df.at[idx, "bidding_tag"] = bidding_tag
            df.at[idx, "bidding_advice"] = bidding_advice
            df.at[idx, "bidding_amt_wan"] = b_amt_wan

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
