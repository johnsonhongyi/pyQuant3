# -*- coding: utf-8 -*-
"""
ats/new_stock_fetcher.py — ATS 新股/次新股/IPO发行日历全市场多通道数据引擎
职责：
1. 自动抓取全市场（沪深主板、科创板、创业板、北交所）近期已上市、前5日(C)、首日(N)、次新股(近60日)实时行情；
2. 自动拉取最新新股发行一览与 IPO 申购/上市日历（含发行价、申购日、上市日、网上发行量、中签率等）；
3. 多通道（腾讯行情+东方财富+新浪+TDX）毫秒级补齐现价、涨跌幅、换手率、成交额、流通市值、总市值，彻底杜绝数据缺失与类型转换异常；
4. 深度对接 TDXRealtimeFetcher 与分时阶梯策略引擎。
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


class NewStockFetcher:
    """新股与次新股多通道数据获取与聚合引擎"""

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
        self._cache_ttl_seconds: float = 3.0  # 3秒轻量缓存，满足高频实时刷新

    def fetch_ipo_calendar(self, page_size: int = 100) -> Dict[str, Dict[str, Any]]:
        """
        从东方财富 IPO 日历接口拉取近期发行与上市新股列表 (含发行价、申购日、上市日、网上发行量、中签率等)
        """
        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get?"
            "reportName=RPTA_APP_IPOAPPLY&"
            "columns=SECURITY_CODE,SECURITY_NAME,TRADE_MARKET,APPLY_CODE,ISSUE_PRICE,APPLY_DATE,LISTING_DATE,ONLINE_ISSUE_NUM,BALLOT_NUM&"
            f"pageNumber=1&pageSize={page_size}&sortColumns=APPLY_DATE&sortTypes=-1&source=WEB&client=WEB"
        )
        ipo_dict = {}
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("result", {}).get("data", []) if data.get("result") else []
                for it in items:
                    c = str(it.get("SECURITY_CODE", "")).strip().zfill(6)
                    if not c:
                        continue
                    # 格式化日期
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
                self._cached_ipo_dict = ipo_dict
                logger.info(f"✅ 成功拉取东方财富 IPO 日历: 共 {len(ipo_dict)} 条记录")
        except Exception as e:
            logger.warning(f"拉取东方财富 IPO 日历异常: {e}")
            if self._cached_ipo_dict:
                return self._cached_ipo_dict
        return ipo_dict

    def fetch_recent_new_stocks_spot(self) -> Dict[str, Dict[str, Any]]:
        """
        拉取已上市新股与次新股实时行情（含沪深北全市场）
        """
        spot_dict = {}
        # 通道 1: akshare.stock_new_a_spot_em
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
                        "speed": safe_float(row.get("涨速")),
                        "pct_5min": safe_float(row.get("5分钟涨跌")),
                        "pct_60d": safe_float(row.get("60日涨跌幅")),
                        "pct_ytd": safe_float(row.get("年初至今涨跌幅")),
                    }
                return spot_dict
        except Exception as e:
            logger.debug(f"akshare 获取新股行情异常: {e}, 自动降级至 Push2")

        # 通道 2: 东方财富 Push2
        try:
            url = "http://82.push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1",
                "pz": "200",
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
            resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=6)
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
        except Exception as e:
            logger.debug(f"Push2 获取新股行情解析: {e}")

        return spot_dict

    def get_combined_new_stocks(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        获取综合新股与次新股数据表（聚合行情 + IPO日历 + 策略状态 + 极速补齐全量字段）
        """
        now = time.time()
        if not force_refresh and self._cached_stocks_df is not None and (now - self._last_fetch_time < self._cache_ttl_seconds):
            return self._cached_stocks_df

        ipo_dict = self.fetch_ipo_calendar(page_size=100)
        spot_dict = self.fetch_recent_new_stocks_spot()

        all_codes = set(ipo_dict.keys()) | set(spot_dict.keys())
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

            # 极速秒级多通道补齐全量字段（腾讯 + TDX 分批覆盖全部新股）
            df = self.enrich_with_tdx_realtime(df)

        self._cached_stocks_df = df
        self._last_fetch_time = time.time()
        return df

    def enrich_with_tdx_realtime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        利用腾讯行情 API + 本地 TDX 分批覆盖全量新股/次新股补充最新实时行情
        """
        if df.empty:
            return df

        codes_to_query = df["code"].tolist()
        quote_map = {}

        # ── 通道 1: 腾讯高频行情 API (分批全覆盖) ──
        try:
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
                    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=3.5)
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
                                p_vol = safe_float(vals[36]) # 手
                                p_amt = safe_float(vals[37]) * 10000.0 if vals[37] else 0.0 # 元
                                p_high = safe_float(vals[33], default=p_now)
                                p_low = safe_float(vals[34], default=p_now)
                                p_pct = safe_float(vals[32])
                                p_to = safe_float(vals[38])
                                p_fmv = safe_float(vals[44]) # 亿
                                p_tmv = safe_float(vals[45]) # 亿

                                quote_map[c_raw] = {
                                    "code": c_raw,
                                    "price": p_now,
                                    "last_close": p_close,
                                    "open": p_open,
                                    "high": p_high,
                                    "low": p_low,
                                    "vol": p_vol,
                                    "amount": p_amt,
                                    "pct": p_pct,
                                    "turnover": p_to,
                                    "float_mv_yi": p_fmv,
                                    "total_mv_yi": p_tmv
                                }
        except Exception as e:
            logger.debug(f"腾讯行情补齐异常: {e}")

        # ── 通道 2: TDXRealtimeFetcher 补充秒级五档与昨收价 (分批全覆盖，权威一等公民) ──
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
                        if c_clean and p > 0:
                            if c_clean not in quote_map:
                                quote_map[c_clean] = {}
                            quote_map[c_clean]["price"] = p
                            if last_c > 0:
                                quote_map[c_clean]["last_close"] = last_c
                                quote_map[c_clean]["pct"] = round((p - last_c) / last_c * 100.0, 2)
                            if safe_float(q.get("amount", 0.0)) > 0:
                                quote_map[c_clean]["amount"] = safe_float(q.get("amount"))
                            if safe_float(q.get("open", 0.0)) > 0:
                                quote_map[c_clean]["open"] = safe_float(q.get("open"))
        except Exception as e:
            logger.debug(f"TDX 补齐异常: {e}")

        # ── 3. 回填更新到 DataFrame ──
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

                    # 涨跌幅精确计算：
                    # 1. 优先使用由昨收价与现价计算的真实涨跌幅 (已上市/次新股/前5日标的)
                    if last_c > 0:
                        df.at[idx, "pct"] = round((p - last_c) / last_c * 100.0, 2)
                    elif "pct" in q and q["pct"] is not None and not math.isnan(safe_float(q["pct"])):
                        df.at[idx, "pct"] = round(safe_float(q["pct"]), 2)
                    elif is_first_day and issue_p > 0:
                        # 仅首日(N)且无昨收时，以发行价为基准计算涨幅
                        df.at[idx, "pct"] = round((p - issue_p) / issue_p * 100.0, 2)
                    else:
                        df.at[idx, "pct"] = 0.0

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
