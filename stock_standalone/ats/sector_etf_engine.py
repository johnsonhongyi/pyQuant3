# -*- coding: utf-8 -*-
"""
ats/sector_etf_engine.py — ATS 板块 ETF 趋势结构与行业大势判定引擎 (Sector ETF Trend Engine)
职责：
1. 建立核心行业/题材赛道与通达信基准 ETF 的映射矩阵 (包含同义词模糊泛化)；
2. 通过通达信原生极速二进制接口 (get_tdx_Exp_day_to_df_lday) 离线毫秒级读取 ETF 日 K 线；
3. 量化评估板块 2 个月大级别反弹/主升趋势结构 (MA20/MA60/60日收益率/通道方向)；
4. 识别真主线趋势板块 (加权扶持回踩主升个股)，识别空头下行板块 (拦截单日"昙花一现"脉冲诱多)。
"""

import os
import sys
import time
import math
import logging
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("SectorETFEngine")

# 核心赛道与通达信基准 ETF 权威映射字典
SECTOR_TO_BENCHMARK_ETF: Dict[str, Dict[str, Any]] = {
    # 养殖业 / 水产 / 畜牧
    "养殖": {"code": "159865", "name": "养殖ETF", "keywords": ["养殖", "畜禽", "水产", "猪肉", "鸡肉", "饲料", "渔业", "生猪", "肉鸡", "禽类", "水产养殖", "兽药", "农药兽药"]},
    "农业": {"code": "159825", "name": "农业ETF", "keywords": ["农业", "种业", "农林牧渔", "粮食", "转基因", "化肥", "农药", "玉米", "大豆", "水稻", "种植", "农业种植", "种子"]},
    "黄金": {"code": "518880", "name": "黄金ETF", "keywords": ["黄金", "贵金属", "白银", "珠宝"]},
    "电力": {"code": "159611", "name": "电力ETF", "keywords": ["电力", "绿色电力", "火电", "水电", "风电", "光伏发电", "热电"]},
    "消费": {"code": "159928", "name": "消费ETF", "keywords": ["消费", "食品", "饮料", "白酒", "调味品", "包装", "轻工"]},
    "半导体": {"code": "512480", "name": "半导体ETF", "keywords": ["半导体", "芯片", "存储芯片", "光刻机", "集成电路"]},
    "通信": {"code": "515880", "name": "通信ETF", "keywords": ["通信", "5G", "CPO", "光模块", "算力", "服务器"]},
    "计算机": {"code": "512720", "name": "计算机ETF", "keywords": ["计算机", "软件", "IT设备", "人工智能", "信创", "大数据"]},
    "证券": {"code": "512880", "name": "证券ETF", "keywords": ["证券", "券商", "多元金融", "金融科技"]},
    "军工": {"code": "512660", "name": "军工ETF", "keywords": ["军工", "国防", "航天", "中航", "武器装备"]},
    "汽车": {"code": "515700", "name": "新能车ETF", "keywords": ["汽车", "新能源车", "锂电池", "整车", "汽配"]},
    "医药": {"code": "512010", "name": "医药ETF", "keywords": ["医药", "生物", "中药", "创新药", "医疗器械"]},
    "有色": {"code": "159980", "name": "有色ETF", "keywords": ["有色", "小金属", "稀土", "铜", "铝", "锂矿"]},
}


class SectorETFEngine:
    """板块 ETF 趋势结构引擎 (单例架构)"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SectorETFEngine, cls).__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        self._etf_cache: Dict[str, Dict[str, Any]] = {}
        self._last_refresh_time: float = 0.0
        self._cache_ttl: float = 300.0  # 5分钟缓存有效期
        self._keyword_index_built: bool = False
        self._keyword_to_category: Dict[str, str] = {}
        self._build_keyword_index()

    def _build_keyword_index(self):
        """构建关键字反向倒排索引，加速毫秒级板块匹配"""
        for cat_key, info in SECTOR_TO_BENCHMARK_ETF.items():
            for kw in info["keywords"]:
                self._keyword_to_category[kw.lower()] = cat_key
        self._keyword_index_built = True

    def find_benchmark_etf_for_sector(self, sector_name: str) -> Optional[Dict[str, Any]]:
        """根据个股的行业题材字符串，模糊匹配最相关的基准 ETF"""
        if not sector_name or not isinstance(sector_name, str):
            return None
        
        sec_lower = sector_name.lower().strip()
        
        # 1. 精确全词匹配
        for cat_key, info in SECTOR_TO_BENCHMARK_ETF.items():
            if cat_key in sec_lower:
                return info
                
        # 2. 倒排关键词匹配
        for kw, cat_key in self._keyword_to_category.items():
            if kw in sec_lower:
                return SECTOR_TO_BENCHMARK_ETF[cat_key]
                
        return None

    def get_etf_trend_structure(self, etf_code: str) -> Dict[str, Any]:
        """
        极速读取并计算单只 ETF 的 2 个月大级别趋势结构
        """
        now = time.time()
        cached = self._etf_cache.get(etf_code)
        if cached and (now - cached.get("cached_time", 0) < self._cache_ttl):
            return cached["data"]

        # 兜底默认结构
        default_res = {
            "code": etf_code,
            "name": "ETF",
            "trend_grade": "🟡 震荡筑底",
            "is_trend_up": False,
            "is_down_trend": False,
            "gain_60d": 0.0,
            "curr_p": 0.0,
            "ma20": 0.0,
            "ma60": 0.0,
            "trend_score_bonus": 0.0,
            "summary": "ETF数据中性"
        }

        try:
            from JSONData import tdx_data_Day as tdd
            df = tdd.get_tdx_Exp_day_to_df_lday(etf_code, dl=60, resample='d')
            if df is None or df.empty or len(df) < 15:
                self._etf_cache[etf_code] = {"cached_time": now, "data": default_res}
                return default_res

            c = df['close']
            n = len(c)
            curr_p = float(c.iloc[-1])
            ma20 = float(c.rolling(min(n, 20)).mean().iloc[-1])
            ma60 = float(c.rolling(min(n, 60)).mean().iloc[-1])
            
            p_start = float(c.iloc[0])
            gain_60d = round((curr_p - p_start) / (p_start if p_start > 0 else 1.0) * 100, 2)
            
            # 趋势结构量化评级
            # A. 🟢 趋势主升 (2个月反弹/慢牛走势: 站上MA20且MA20>=MA60或近2月收益显著为正)
            is_trend_up = (curr_p >= ma20 * 0.99) and (ma20 >= ma60 * 0.985) and (gain_60d >= 2.0 or curr_p > ma20)
            
            # B. 🔴 空头破位 (长期受均线压制, 破位下行)
            is_down_trend = (curr_p < ma60 * 0.96) and (ma20 < ma60) and (gain_60d <= -8.0)
            
            if is_trend_up:
                trend_grade = "🟢 趋势主升"
                trend_score_bonus = 6.0  # 给予板块内优质个股正向主升赋能
                summary = f"ETF近2月震荡攀升(+{gain_60d}%), 均线多头MA20({ma20:.2f})>MA60({ma60:.2f})"
            elif is_down_trend:
                trend_grade = "🔴 空头破位"
                trend_score_bonus = -8.0  # 严厉惩治空头板块中个股的昙花一现脉冲
                summary = f"ETF处于下行通道({gain_60d}%), 均线空头压制, 警惕昙花一现脉冲"
            else:
                trend_grade = "🟡 震荡筑底"
                trend_score_bonus = 1.0
                summary = f"ETF箱体震荡筑底中, 振幅可控"

            res = {
                "code": etf_code,
                "name": default_res["name"],
                "trend_grade": trend_grade,
                "is_trend_up": is_trend_up,
                "is_down_trend": is_down_trend,
                "gain_60d": gain_60d,
                "curr_p": round(curr_p, 3),
                "ma20": round(ma20, 3),
                "ma60": round(ma60, 3),
                "trend_score_bonus": trend_score_bonus,
                "summary": summary
            }
            self._etf_cache[etf_code] = {"cached_time": now, "data": res}
            return res

        except Exception as ex:
            logger.warning(f"Failed to evaluate ETF trend for {etf_code}: {ex}")
            self._etf_cache[etf_code] = {"cached_time": now, "data": default_res}
            return default_res

    def evaluate_sector_trend_for_stock(self, sector_name: str) -> Dict[str, Any]:
        """输入个股所属行业或题材，直接返回其宏观板块 ETF 的趋势评级与 Alpha 加成"""
        etf_info = self.find_benchmark_etf_for_sector(sector_name)
        if not etf_info:
            return {
                "has_etf": False,
                "etf_code": "",
                "etf_name": "",
                "trend_grade": "⚪ 独立赛道",
                "is_trend_up": False,
                "is_down_trend": False,
                "trend_score_bonus": 0.0,
                "summary": "未映射到专属基准ETF"
            }
            
        trend_res = self.get_etf_trend_structure(etf_info["code"])
        trend_res["has_etf"] = True
        trend_res["etf_code"] = etf_info["code"]
        trend_res["etf_name"] = etf_info["name"]
        return trend_res

    def get_stock_sector_etf_trend(self, stock_code: str, sector_name: str) -> Dict[str, Any]:
        """别名兼容接口：根据个股代码与行业名称返回板块 ETF 趋势结构"""
        return self.evaluate_sector_trend_for_stock(sector_name)

    def get_all_sector_etfs_summary(self) -> List[Dict[str, Any]]:
        """
        获取全市场 13 大基准行业/题材 ETF 的大级别趋势量化透视表
        按 2 个月收益率降序排列，提供宏观大势把握与持续性判断
        """
        records = []
        for cat_key, info in SECTOR_TO_BENCHMARK_ETF.items():
            code = info["code"]
            name = info["name"]
            trend_data = self.get_etf_trend_structure(code)
            rec = {
                "cat_name": cat_key,
                "code": code,
                "name": name,
                "trend_grade": trend_data.get("trend_grade", "🟡 震荡筑底"),
                "is_trend_up": trend_data.get("is_trend_up", False),
                "is_down_trend": trend_data.get("is_down_trend", False),
                "gain_60d": trend_data.get("gain_60d", 0.0),
                "curr_p": trend_data.get("curr_p", 0.0),
                "ma20": trend_data.get("ma20", 0.0),
                "ma60": trend_data.get("ma60", 0.0),
                "summary": trend_data.get("summary", ""),
                "keywords": " / ".join(info.get("keywords", [])[:6]),
            }
            records.append(rec)

        # 按近 2 个月收益率降序排序，强势主升板块优先置顶
        records.sort(key=lambda x: x["gain_60d"], reverse=True)
        return records


_GLOBAL_SECTOR_ETF_ENGINE = None

def get_sector_etf_engine() -> SectorETFEngine:
    """全局获取板块 ETF 趋势结构引擎实例"""
    global _GLOBAL_SECTOR_ETF_ENGINE
    if _GLOBAL_SECTOR_ETF_ENGINE is None:
        _GLOBAL_SECTOR_ETF_ENGINE = SectorETFEngine()
    return _GLOBAL_SECTOR_ETF_ENGINE
