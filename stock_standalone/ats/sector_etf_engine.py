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

# 核心赛道与通达信基准 ETF 权威映射字典 (扩充至 20 大黄金核心题材)
SECTOR_TO_BENCHMARK_ETF: Dict[str, Dict[str, Any]] = {
    # 1. 热门科技与人工智能概念
    "AI": {"code": "159819", "name": "人工智能ETF", "keywords": ["ai", "人工智能", "大模型", "aigc", "智能体", "自然语言", "nlp", "深度学习", "智算", "ai语料"]},
    "影视传媒": {"code": "512980", "name": "传媒ETF", "keywords": ["影视", "传媒", "短剧", "院线", "电影", "动画", "广告", "网文", "短视频", "出版", "知识产权", "文化传媒"]},
    "游戏": {"code": "159869", "name": "游戏ETF", "keywords": ["游戏", "电竞", "网络游戏", "二次元", "动漫", "互动娱乐", "元宇宙", "云游戏"]},
    "机器人": {"code": "562500", "name": "机器人ETF", "keywords": ["机器人", "减速器", "伺服电机", "人形机器人", "具身智能", "工业母机", "自动化", "机床", "智能制造"]},
    "云计算": {"code": "516510", "name": "云计算ETF", "keywords": ["云计算", "云服务", "数据中心", "idc", "大数据", "数据要素", "服务器", "东数西算"]},
    "通信": {"code": "515880", "name": "通信ETF", "keywords": ["通信", "5g", "cpo", "光模块", "算力", "光通信", "基站", "通信设备"]},
    "半导体": {"code": "512480", "name": "半导体ETF", "keywords": ["半导体", "芯片", "存储芯片", "光刻机", "集成电路", "封装测试", "晶圆代工"]},
    "计算机": {"code": "512720", "name": "计算机ETF", "keywords": ["计算机", "软件", "it设备", "信创", "操作系统", "网络安全", "华为鸿蒙", "基础软件"]},
    
    # 2. 农业与民生主线
    "养殖": {"code": "159865", "name": "养殖ETF", "keywords": ["养殖", "畜禽", "水产", "猪肉", "鸡肉", "饲料", "渔业", "生猪", "肉鸡", "禽类", "水产养殖", "兽药", "农药兽药"]},
    "农业": {"code": "159825", "name": "农业ETF", "keywords": ["农业", "种业", "农林牧渔", "粮食", "转基因", "化肥", "农药", "玉米", "大豆", "水稻", "种植", "农业种植", "种子", "乡村振兴"]},
    "黄金": {"code": "518880", "name": "黄金ETF", "keywords": ["黄金", "贵金属", "白银", "珠宝", "金矿"]},
    "电力": {"code": "159611", "name": "电力ETF", "keywords": ["电力", "绿色电力", "火电", "水电", "风电", "光伏发电", "热电", "核电", "电网设备", "特高压"]},
    "光伏": {"code": "515790", "name": "光伏ETF", "keywords": ["光伏", "储能", "逆变器", "太阳能", "硅片", "光伏设备", "组件", "光伏建筑"]},
    "煤炭": {"code": "515220", "name": "煤炭ETF", "keywords": ["煤炭", "焦煤", "动力煤", "煤化工", "焦炭", "传统能源"]},
    "消费": {"code": "159928", "name": "消费ETF", "keywords": ["消费", "食品", "饮料", "白酒", "调味品", "包装", "轻工", "乳制品", "零食"]},
    
    # 3. 核心支柱与先进制造
    "证券": {"code": "512880", "name": "证券ETF", "keywords": ["证券", "券商", "多元金融", "金融科技", "资本市场", "头部券商"]},
    "银行": {"code": "512800", "name": "银行ETF", "keywords": ["银行", "国有大行", "股份制银行", "城商行", "农商行", "中特估金融"]},
    "军工": {"code": "512660", "name": "军工ETF", "keywords": ["军工", "国防", "航天", "中航", "武器装备", "大飞机", "低空经济", "无人机", "航空装备"]},
    "汽车": {"code": "515700", "name": "新能车ETF", "keywords": ["汽车", "新能源车", "锂电池", "整车", "汽配", "动力电池", "充电桩", "固态电池"]},
    "医药": {"code": "512010", "name": "医药ETF", "keywords": ["医药", "生物", "中药", "创新药", "医疗器械", "cxo", "疫苗", "医药商业"]},
    "有色": {"code": "159980", "name": "有色ETF", "keywords": ["有色", "小金属", "稀土", "铜", "铝", "锂矿", "黄金有色", "工业金属"]},
}


class SectorETFEngine:
    """板块 ETF 趋势通道与支撑结构引擎 (单例架构)"""
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
            if cat_key.lower() in sec_lower:
                return info
                
        # 2. 倒排关键词匹配 (按关键词长度倒序，优先匹配长词/专有名词)
        sorted_kws = sorted(self._keyword_to_category.keys(), key=lambda x: len(x), reverse=True)
        for kw in sorted_kws:
            if kw in sec_lower:
                cat_key = self._keyword_to_category[kw]
                return SECTOR_TO_BENCHMARK_ETF[cat_key]
                
        return None

    def get_etf_trend_structure(self, etf_code: str, realtime_quote: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        跟个股一样：通过通达信自动通道引擎 (calc_trend_channel) 极速计算通道支撑、反转位与多维动能，
        并融合今日实时盘口动态合成最新 K 线，彻底摆脱单一2个月总收益率的滞后缺陷！
        同时多指标实战拟合：启动动能评分 (launch_score) 与 预埋单上车建议 (entry_advice)。
        """
        now = time.time()
        # 若外部显式传入 realtime_quote，则优先动态实时计算不走过期历史缓存
        cached = self._etf_cache.get(etf_code)
        if cached and not realtime_quote and (now - cached.get("cached_time", 0) < self._cache_ttl):
            return cached["data"]

        # 兜底默认结构
        default_res = {
            "code": etf_code,
            "name": "ETF",
            "trend_grade": "🟡 箱体震荡",
            "is_trend_up": False,
            "is_down_trend": False,
            "curr_p": 0.0,
            "pct_today": 0.0,
            "launch_score": 50.0,
            "launch_stars": "⭐⭐",
            "entry_advice": "观察中",
            "supp_p": 0.0,
            "reversal_p": 0.0,
            "ch_upper": 0.0,
            "ch_mid": 0.0,
            "ch_lower": 0.0,
            "ch_slope_deg": 0.0,
            "ch_pos": 50.0,
            "channel_score": 50.0,
            "gain_5d": 0.0,
            "gain_20d": 0.0,
            "gain_60d": 0.0,
            "trend_score_bonus": 0.0,
            "summary": "通道指标初始化中"
        }

        try:
            from JSONData import tdx_data_Day as tdd
            df = tdd.get_tdx_Exp_day_to_df_lday(etf_code, dl=60, resample='d')
            if df is None or df.empty or len(df) < 15:
                self._etf_cache[etf_code] = {"cached_time": now, "data": default_res}
                return default_res

            # 0. 尝试提取实时行情快照 (支持外部传入或单例获取)
            if realtime_quote is None:
                try:
                    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                    fetcher = TDXRealtimeFetcher.get_instance()
                    qs = fetcher.get_security_quotes_safe([etf_code])
                    if qs:
                        realtime_quote = qs[0]
                except Exception:
                    pass

            rt_p = 0.0
            rt_last_c = 0.0
            rt_open = 0.0
            rt_high = 0.0
            rt_low = 0.0
            pct_today = 0.0
            is_low_open_surge = False

            if realtime_quote:
                try:
                    rt_p = float(realtime_quote.get("price") or 0.0)
                    rt_last_c = float(realtime_quote.get("last_close") or 0.0)
                    rt_open = float(realtime_quote.get("open") or 0.0)
                    rt_high = float(realtime_quote.get("high") or 0.0)
                    rt_low = float(realtime_quote.get("low") or 0.0)
                    if rt_p > 0 and rt_last_c > 0:
                        pct_today = round((rt_p - rt_last_c) / rt_last_c * 100.0, 2)
                        # 低开高走或探底反弹大涨特征
                        if (rt_open <= rt_last_c * 1.005 or rt_low <= rt_last_c * 1.002) and rt_p > rt_open and pct_today >= 1.0:
                            is_low_open_surge = True
                except Exception:
                    pass

            # 动态将今日实时 K 线融合到 df 末尾
            if rt_p > 0 and rt_open > 0:
                today_str = time.strftime("%Y-%m-%d")
                last_idx_str = str(df.index[-1])[:10]
                if last_idx_str == today_str:
                    df.iloc[-1, df.columns.get_loc('close')] = rt_p
                    df.iloc[-1, df.columns.get_loc('high')] = max(float(df.iloc[-1]['high']), rt_high, rt_p)
                    df.iloc[-1, df.columns.get_loc('low')] = min(float(df.iloc[-1]['low']), rt_low, rt_p) if float(df.iloc[-1]['low']) > 0 else rt_p
                else:
                    rt_row = pd.DataFrame([{
                        'open': rt_open,
                        'high': max(rt_high, rt_p),
                        'low': min(rt_low, rt_p) if rt_low > 0 else rt_p,
                        'close': rt_p,
                        'amount': float(realtime_quote.get('amount') or 0.0),
                        'vol': float(realtime_quote.get('vol') or 0.0)
                    }], index=[today_str])
                    df = pd.concat([df, rt_row])

            # 1. 运行通达信原生自动通道引擎
            df_ch = tdd.calc_trend_channel(df)
            last = df_ch.iloc[-1]
            n = len(df_ch)

            curr_p = float(last['close'])
            if pct_today == 0.0 and n >= 2:
                prev_c = float(df_ch.iloc[-2]['close'])
                if prev_c > 0:
                    pct_today = round((curr_p - prev_c) / prev_c * 100.0, 2)

            ch_upper = float(last.get('ch_upper', curr_p * 1.05))
            ch_mid = float(last.get('ch_mid', curr_p))
            ch_lower = float(last.get('ch_lower', curr_p * 0.95))
            ch_slope_deg = float(last.get('ch_slope_deg', 0.0))
            ch_pos = float(last.get('ch_pos', 50.0))
            ch_dir = int(last.get('ch_dir', 0))

            # 通达信指标上升支撑线 (DRAWLINE) 与反转确认线 (EMA/MA反转线)
            supp_p = float(last.get('ch_supp_price', ch_lower))
            reversal_p = float(last.get('reversal_line', last.get('fib_50', ch_mid)))

            # 2. 多周期动能量化 (5日短期异动, 20日波段动能, 60日长期底座)
            c_series = df_ch['close']
            p_5d = float(c_series.iloc[-min(5, n)])
            p_20d = float(c_series.iloc[-min(20, n)])
            p_60d = float(c_series.iloc[0])

            gain_5d = round((curr_p - p_5d) / (p_5d if p_5d > 0 else 1.0) * 100.0, 2)
            gain_20d = round((curr_p - p_20d) / (p_20d if p_20d > 0 else 1.0) * 100.0, 2)
            gain_60d = round((curr_p - p_60d) / (p_60d if p_60d > 0 else 1.0) * 100.0, 2)

            # 3. 通道与关键价位关系判定
            is_on_support = bool(curr_p >= supp_p * 0.992)
            is_on_mid = bool(curr_p >= ch_mid * 0.992)
            is_on_reversal = bool(curr_p >= reversal_p * 0.992)

            # 前 1~3 日是否有回踩中轨/支撑后企稳动作
            has_pullback_support = False
            if n >= 3:
                recent_lows = df_ch['low'].iloc[-4:-1]
                if any((low_v <= ch_mid * 1.01 and low_v >= supp_p * 0.98) for low_v in recent_lows):
                    has_pullback_support = True

            # 4. 多指标实战拟合：通道趋势评级、启动动能评分 (0~100) 与 预埋单上车建议
            # A. 🚀 回踩起爆 (最佳上车点：如养殖ETF前两日回踩今日大阳拔起突破反转位)
            if (has_pullback_support or is_low_open_surge or (ch_pos <= 60.0 and pct_today >= 1.5)) and (curr_p >= reversal_p * 0.99 or is_on_reversal) and pct_today >= 1.2 and is_on_support:
                trend_grade = "🚀 回踩起爆"
                trend_score_bonus = 10.0
                launch_score = round(min(99.0, 92.0 + pct_today * 1.2 + max(0.0, ch_slope_deg * 0.3)), 1)
                launch_stars = "⭐⭐⭐⭐⭐"
                entry_advice = f"🎯 现价追入 / 回踩{supp_p:.3f}预埋"
                summary = f"前两日回踩支撑({supp_p:.3f})企稳, 今日大涨{pct_today:+.2f}%突破反转位({reversal_p:.3f}), 顶级起爆"

            # B. 👑 突破加速: 位于上轨区域且短线加速主升
            elif (ch_pos >= 80.0 and (gain_5d > 0.3 or curr_p >= ch_upper * 0.99) and pct_today >= 0.8) or (ch_pos >= 85.0 and is_on_mid):
                trend_grade = "👑 突破加速"
                trend_score_bonus = 8.0
                launch_score = round(min(94.0, 86.0 + pct_today * 1.0 + max(0.0, ch_slope_deg * 0.4)), 1)
                launch_stars = "⭐⭐⭐⭐"
                entry_advice = f"🚀 顺势持股 / 回踩中轨{ch_mid:.3f}预埋"
                summary = f"突破通道上轨({ch_upper:.2f})加速浪, 5日动能{gain_5d:+.1f}%, pos={ch_pos:.0f}%"

            # C. 💎 支撑企稳: 回踩通道下轨/支撑线企稳筑底，反转确认 (如黄金9.18元、证券1.10元)
            elif ((ch_pos <= 40.0 and curr_p >= ch_lower * 0.985) or (is_on_support and curr_p <= supp_p * 1.035)) and (gain_5d >= -1.0 or is_on_reversal) and pct_today >= -0.8:
                trend_grade = "💎 支撑企稳"
                trend_score_bonus = 6.0
                launch_score = round(min(85.0, 78.0 + max(0.0, pct_today * 2.0) + (1.0 if is_on_reversal else 0.0) * 3.0), 1)
                launch_stars = "⭐⭐⭐"
                entry_advice = f"💎 支撑位{supp_p:.3f}挂单预埋"
                summary = f"回踩通道支撑({supp_p:.2f}元)确认企稳, 反转位({reversal_p:.2f}元), 黄金低吸区"

            # D. 🟢 上升通道: 通道向上且站稳通道中轨与支撑线上方
            elif (ch_slope_deg >= 1.5 or ch_dir == 1) and is_on_mid and is_on_support:
                trend_grade = "🟢 上升通道"
                trend_score_bonus = 5.0
                launch_score = round(min(88.0, 75.0 + max(0.0, pct_today * 1.5) + ch_slope_deg * 0.5), 1)
                launch_stars = "⭐⭐⭐"
                entry_advice = f"🟢 沿中轨{ch_mid:.3f}逢低做多"
                summary = f"上升通道(倾角+{ch_slope_deg:.1f}°), 稳居支撑({supp_p:.2f}元)与中轨上方"

            # E. 🔴 空头破位: 通道下倾且跌破中轨与支撑线
            elif (ch_slope_deg <= -3.0 or ch_dir == -1) and (not is_on_mid) and (curr_p < supp_p * 0.985 or ch_pos < 25.0):
                trend_grade = "🔴 空头破位"
                trend_score_bonus = -8.0
                launch_score = round(max(10.0, min(35.0, 25.0 + pct_today)), 1)
                launch_stars = "⛔"
                entry_advice = "⛔ 严禁上车(板块破位风险)"
                summary = f"下降通道(倾角{ch_slope_deg:.1f}°), 跌破支撑({supp_p:.2f}元), 严防诱多"

            # F. 🟡 箱体震荡: 中轨与下轨之间整理
            else:
                trend_grade = "🟡 箱体震荡"
                trend_score_bonus = 1.0
                launch_score = round(min(70.0, max(45.0, 55.0 + pct_today * 2.0)), 1)
                launch_stars = "⭐⭐"
                entry_advice = f"🟡 支撑{supp_p:.3f}吸 / 阻力{ch_upper:.3f}抛"
                summary = f"箱体通道整理(pos={ch_pos:.0f}%), 支撑{supp_p:.2f}元, 阻力{ch_upper:.2f}元"

            is_trend_up = trend_grade in ("🚀 回踩起爆", "👑 突破加速", "🟢 上升通道", "💎 支撑企稳")
            is_down_trend = (trend_grade == "🔴 空头破位")

            # 通道量化评分
            score_base = 50.0
            score_slope = min(20.0, max(-20.0, ch_slope_deg * 1.5))
            score_supp = (15.0 if is_on_support else -15.0) + (10.0 if is_on_mid else -10.0)
            score_mom = min(15.0, max(-15.0, gain_5d * 1.5 + gain_20d * 0.5 + pct_today * 0.8))
            channel_score = round(min(100.0, max(0.0, score_base + score_slope + score_supp + score_mom)), 1)

            res = {
                "code": etf_code,
                "name": default_res["name"],
                "trend_grade": trend_grade,
                "is_trend_up": is_trend_up,
                "is_down_trend": is_down_trend,
                "curr_p": round(curr_p, 3),
                "pct_today": pct_today,
                "launch_score": launch_score,
                "launch_stars": launch_stars,
                "entry_advice": entry_advice,
                "supp_p": round(supp_p, 3),
                "reversal_p": round(reversal_p, 3),
                "ch_upper": round(ch_upper, 3),
                "ch_mid": round(ch_mid, 3),
                "ch_lower": round(ch_lower, 3),
                "ch_slope_deg": round(ch_slope_deg, 1),
                "ch_pos": round(ch_pos, 1),
                "channel_score": channel_score,
                "gain_5d": gain_5d,
                "gain_20d": gain_20d,
                "gain_60d": gain_60d,
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
                "supp_p": 0.0,
                "reversal_p": 0.0,
                "ch_pos": 50.0,
                "ch_slope_deg": 0.0,
                "channel_score": 50.0,
                "trend_score_bonus": 0.0,
                "summary": "未映射到专属基准ETF"
            }
            
        trend_res = dict(self.get_etf_trend_structure(etf_info["code"]))
        trend_res["has_etf"] = True
        trend_res["etf_code"] = etf_info["code"]
        trend_res["etf_name"] = etf_info["name"]
        return trend_res

    def get_stock_sector_etf_trend(self, stock_code: str, sector_name: str) -> Dict[str, Any]:
        """别名兼容接口：根据个股代码与行业名称返回板块 ETF 趋势结构"""
        return self.evaluate_sector_trend_for_stock(sector_name)

    def get_all_sector_etfs_summary(self) -> List[Dict[str, Any]]:
        """
        获取全市场 20 大基准行业/题材 ETF 的通道支撑与动能透视表
        批量拉取实时盘口，按【启动动能评分 (launch_score)】与【今日涨跌%】降序排列，
        直观拟合：到底哪些板块在爆发启动动能、预埋单该在什么价位上车！
        """
        all_codes = [info["code"] for info in SECTOR_TO_BENCHMARK_ETF.values()]
        realtime_map: Dict[str, Dict[str, Any]] = {}
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            fetcher = TDXRealtimeFetcher.get_instance()
            quotes = fetcher.get_security_quotes_safe(all_codes)
            if quotes:
                for q in quotes:
                    c = str(q.get("code", "")).strip().zfill(6)
                    if c:
                        realtime_map[c] = q
        except Exception as ex:
            logger.debug(f"Fetch realtime quotes in get_all_sector_etfs_summary failed: {ex}")

        records = []
        for cat_key, info in SECTOR_TO_BENCHMARK_ETF.items():
            code = info["code"]
            name = info["name"]
            rt_q = realtime_map.get(code)
            trend_data = self.get_etf_trend_structure(code, realtime_quote=rt_q)
            rec = {
                "cat_name": cat_key,
                "code": code,
                "name": name,
                "trend_grade": trend_data.get("trend_grade", "🟡 箱体震荡"),
                "is_trend_up": trend_data.get("is_trend_up", False),
                "is_down_trend": trend_data.get("is_down_trend", False),
                "curr_p": trend_data.get("curr_p", 0.0),
                "pct_today": trend_data.get("pct_today", 0.0),
                "launch_score": trend_data.get("launch_score", 50.0),
                "launch_stars": trend_data.get("launch_stars", "⭐⭐"),
                "entry_advice": trend_data.get("entry_advice", "观察中"),
                "channel_score": trend_data.get("channel_score", 50.0),
                "supp_p": trend_data.get("supp_p", 0.0),
                "reversal_p": trend_data.get("reversal_p", 0.0),
                "ch_upper": trend_data.get("ch_upper", 0.0),
                "ch_mid": trend_data.get("ch_mid", 0.0),
                "ch_lower": trend_data.get("ch_lower", 0.0),
                "ch_pos": trend_data.get("ch_pos", 50.0),
                "ch_slope_deg": trend_data.get("ch_slope_deg", 0.0),
                "gain_5d": trend_data.get("gain_5d", 0.0),
                "gain_20d": trend_data.get("gain_20d", 0.0),
                "gain_60d": trend_data.get("gain_60d", 0.0),
                "summary": trend_data.get("summary", ""),
                "keywords": " / ".join(info.get("keywords", [])[:6]),
            }
            records.append(rec)

        # 核心排序：优先按【启动动能评分 (launch_score)】降序，同分按【今日涨跌%】降序，启动起爆板块最强置顶
        records.sort(key=lambda x: (x["launch_score"], x["pct_today"], x["channel_score"]), reverse=True)
        return records


_GLOBAL_SECTOR_ETF_ENGINE = None

def get_sector_etf_engine() -> SectorETFEngine:
    """全局获取板块 ETF 趋势结构引擎实例"""
    global _GLOBAL_SECTOR_ETF_ENGINE
    if _GLOBAL_SECTOR_ETF_ENGINE is None:
        _GLOBAL_SECTOR_ETF_ENGINE = SectorETFEngine()
    return _GLOBAL_SECTOR_ETF_ENGINE
