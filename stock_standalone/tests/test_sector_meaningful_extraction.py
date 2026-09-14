# -*- coding: utf-8 -*-
"""
tests/test_sector_meaningful_extraction.py — 资金主线与高价值实体板块提取专项测试
=============================================================================
验证目标：
1. 泛概念/监管/金融操作标签彻底过滤（国企改革、ST板块、回购增持再贷款、深股通等）；
2. 实体产业题材与细分赛道高精保护（PCB概念、先进封装、芯片、网络安全、光伏概念等）；
3. 真实股票场景（300311任子行、600876凯盛新能、002346柘中股份、600172黄河旋风）提取准确性；
4. CapitalDragonEngine 引擎主线聚合与龙头画像所属主线实战断言（杜绝泛概念霸屏与霸榜）。
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_logic_utils import (
    is_generic_concept,
    extract_meaningful_sectors,
    get_most_valuable_sector,
    SYSTEM_SECTOR_BLACKLIST
)
from ats.capital_dragon_engine import CapitalDragonEngine


class TestSectorMeaningfulExtraction(unittest.TestCase):

    def test_generic_concepts_filtered(self):
        """测试各类无明确产业信息的泛概念 100% 被识别并拦截"""
        noise_samples = [
            "国企改革", "央企国企改革", "央企改革", "地方国企改革", "地方国资", "地方国企", "上海国企改革",
            "ST板块", "*ST板块", "ST股", "*ST股", "ST", "*ST", "摘帽", "退市整理", "风险警示",
            "回购增持再贷款", "回购增持", "股份回购", "股票回购", "回购", "增持",
            "深股通", "沪股通", "港股通", "融资融券", "转融通", "转融券",
            "微盘股", "破净股", "低价股", "中字头", "中字头股票", "同花顺中特估100", "中特估",
            "预盈预增", "半年报预增", "年报预增", "高送转", "昨日涨停"
        ]
        for name in noise_samples:
            self.assertTrue(
                is_generic_concept(name),
                f"泛概念 [{name}] 未能被识别为 generic concept！"
            )

    def test_real_industry_concepts_protected(self):
        """测试真实实体产业与具体题材板块 100% 被保护（绝不误杀）"""
        valid_samples = [
            "PCB概念", "先进封装", "芯片概念", "半导体", "人工智能", "算力芯片",
            "网络安全", "数据安全", "信创", "车联网", "智能驾驶",
            "光伏概念", "光伏玻璃", "超硬材料", "培育钻石", "柔性直流输电", "智能电网",
            "人形机器人", "低空经济", "特斯拉概念", "人造肉", "流感", "跨境电商"
        ]
        for name in valid_samples:
            self.assertFalse(
                is_generic_concept(name),
                f"实体产业题材 [{name}] 被错误识别为泛概念！"
            )

    def test_extract_meaningful_sectors_cleaning(self):
        """测试复合板块概念字符串的纯化与切分"""
        # 模拟 300311 任子行
        s_300311 = "ST板块;深股通;网络安全;信息安全;华为概念;信创"
        res_300311 = extract_meaningful_sectors(s_300311)
        self.assertNotIn("ST板块", res_300311)
        self.assertNotIn("深股通", res_300311)
        self.assertEqual(res_300311, ["网络安全", "信息安全", "华为概念", "信创"])

        # 模拟 600876 凯盛新能
        s_600876 = "国企改革;央企国企改革;光伏概念;玻璃玻纤;新材料;沪股通"
        res_600876 = extract_meaningful_sectors(s_600876)
        self.assertNotIn("国企改革", res_600876)
        self.assertNotIn("央企国企改革", res_600876)
        self.assertNotIn("沪股通", res_600876)
        self.assertEqual(res_600876, ["光伏概念", "玻璃玻纤", "新材料"])

        # 模拟 002346 柘中股份
        s_002346 = "深股通, 回购增持再贷款, 智能电网, 柔性直流输电, 成套电气设备"
        res_002346 = extract_meaningful_sectors(s_002346)
        self.assertNotIn("深股通", res_002346)
        self.assertNotIn("回购增持再贷款", res_002346)
        self.assertEqual(res_002346, ["智能电网", "柔性直流输电", "成套电气设备"])

    def test_get_most_valuable_sector_real_cases(self):
        """测试 get_most_valuable_sector 在实战标的中的智能决选"""
        # 1. 任子行 (ST板块首位 -> 智能选定网络安全)
        sec_300311 = get_most_valuable_sector(
            sec_str="ST板块;网络安全;信息安全;华为概念",
            industry="软件开发"
        )
        self.assertEqual(sec_300311, "网络安全")

        # 2. 凯盛新能 (国企改革首位 -> 智能选定光伏概念)
        sec_600876 = get_most_valuable_sector(
            sec_str="国企改革;光伏概念;玻璃玻纤;新材料",
            industry="光伏设备"
        )
        self.assertEqual(sec_600876, "光伏概念")

        # 3. 柘中股份 (回购增持再贷款首位 -> 智能选定智能电网)
        sec_002346 = get_most_valuable_sector(
            sec_str="深股通;回购增持再贷款;智能电网;柔性直流输电",
            industry="电网设备"
        )
        self.assertEqual(sec_002346, "智能电网")

        # 4. 黄河旋风 (国企改革首位 -> 智能选定超硬材料或培育钻石)
        sec_600172 = get_most_valuable_sector(
            sec_str="国企改革;超硬材料;培育钻石;光伏概念",
            industry="通用设备"
        )
        self.assertIn(sec_600172, ["超硬材料", "培育钻石", "光伏概念"])
        self.assertNotEqual(sec_600172, "国企改革")

        # 5. 核心主线共振优先测试：
        # 假设当前 Top 核心主线是 ["先进封装", "PCB概念"]，标的概念包含 "智能电网;PCB概念"
        sec_res = get_most_valuable_sector(
            sec_str="智能电网;PCB概念",
            top_sectors=["先进封装", "PCB概念"]
        )
        self.assertEqual(sec_res, "PCB概念")

        # 6. 极端全泛概念兜底行业测试
        sec_fallback = get_most_valuable_sector(
            sec_str="国企改革;深股通;融资融券",
            industry="计算机-软件开发"
        )
        self.assertEqual(sec_fallback, "软件开发")

        # 7. 指数与ETF识别
        sec_idx = get_most_valuable_sector(
            sec_str="上证指数;权重股",
            is_index=True
        )
        self.assertEqual(sec_idx, "综合指数/ETF")

    def test_capital_dragon_engine_end_to_end_cleansing(self):
        """测试 CapitalDragonEngine 端到端主线聚合与龙头所属主线，杜绝国企改革霸榜"""
        # 构建仿真数据：包含 5 只带有“国企改革”但不同行业的股票，以及 3 只集中在“PCB概念”的强势股
        mock_data = {
            # 300311 佳了行 (带 ST板块)
            "300311": {
                "name": "佳了行", "close": 6.39, "percent": 13.1, "amount": 7.6e8,
                "category": "ST板块;深股通;网络安全;信息安全", "industry": "软件开发",
                "dff": 1.2, "dff2": 5.0, "dff3": 10.0, "vol_ratio": 1.72
            },
            # 600876 凯盛新能 (带 国企改革)
            "600876": {
                "name": "凯盛新能", "close": 9.57, "percent": 10.0, "amount": 3.2e8,
                "category": "国企改革;光伏概念;玻璃玻纤", "industry": "光伏设备",
                "dff": 2.0, "dff2": 6.0, "dff3": 8.0, "vol_ratio": 2.22
            },
            # 002346 柘中股份 (带 回购增持再贷款)
            "002346": {
                "name": "柘中股份", "close": 19.82, "percent": 9.99, "amount": 2.5e8,
                "category": "深股通;回购增持再贷款;智能电网;柔性直流输电", "industry": "电网设备",
                "dff": 1.5, "dff2": 4.5, "dff3": 7.0, "vol_ratio": 1.38
            },
            # 600172 黄河旋风 (带 国企改革)
            "600172": {
                "name": "黄河旋风", "close": 16.53, "percent": 9.98, "amount": 46.2e8,
                "category": "国企改革;超硬材料;培育钻石", "industry": "非金属材料",
                "dff": 3.0, "dff2": 8.0, "dff3": 15.0, "vol_ratio": 1.18
            },
            # PCB概念强势集团：3只合力爆发
            "002669": {
                "name": "康达新材", "close": 13.75, "percent": 10.0, "amount": 3.8e8,
                "category": "PCB概念;新材料", "industry": "电子元件",
                "dff": 1.5, "dff2": 5.2, "dff3": 9.0, "vol_ratio": 1.63
            },
            "301132": {
                "name": "满坤科技", "close": 20.0, "percent": 20.0, "amount": 5.5e8,
                "category": "PCB概念;消费电子", "industry": "电子元件",
                "dff": 4.0, "dff2": 12.0, "dff3": 22.0, "vol_ratio": 1.85
            },
            "300903": {
                "name": "科翔股份", "close": 15.0, "percent": 20.0, "amount": 6.8e8,
                "category": "PCB概念;汽车电子", "industry": "电子元件",
                "dff": 3.5, "dff2": 11.0, "dff3": 18.0, "vol_ratio": 1.70
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')

        engine = CapitalDragonEngine.get_instance()
        with engine._cache_lock:
            engine._cached_report = {}
            engine._cached_time = 0.0
            engine._cached_df_len = 0
            engine._cached_df_first_code = ""

        report = engine.analyze_capital_dragon_universe(df_mock, force=True)

        # 1. 验证核心主线 Top Sectors
        top_secs = report.get("top_sectors", [])
        top_sec_names = [s["name"] for s in top_secs]

        # 严厉断言：主线中绝无“国企改革”、“ST板块”、“深股通”、“回购增持再贷款”
        self.assertNotIn("国企改革", top_sec_names)
        self.assertNotIn("ST板块", top_sec_names)
        self.assertNotIn("深股通", top_sec_names)
        self.assertNotIn("回购增持再贷款", top_sec_names)
        self.assertIn("PCB概念", top_sec_names)

        # 2. 验证龙头画像结果中的【所属主线】
        dragons = report.get("dragons", [])
        dragon_sec_map = {d["code"]: d.get("sector", "") for d in dragons}

        # 佳了行 300311：绝对不能是 ST板块，应为网络安全
        if "300311" in dragon_sec_map:
            self.assertNotEqual(dragon_sec_map["300311"], "ST板块")
            self.assertEqual(dragon_sec_map["300311"], "网络安全")

        # 凯盛新能 600876：绝对不能是 国企改革，应为光伏概念
        if "600876" in dragon_sec_map:
            self.assertNotEqual(dragon_sec_map["600876"], "国企改革")
            self.assertEqual(dragon_sec_map["600876"], "光伏概念")

        # 柘中股份 002346：绝对不能是 回购增持再贷款，应为智能电网
        if "002346" in dragon_sec_map:
            self.assertNotIn("回购", dragon_sec_map["002346"])
            self.assertEqual(dragon_sec_map["002346"], "智能电网")

        # 黄河旋风 600172：绝对不能是 国企改革，应为超硬材料或培育钻石
        if "600172" in dragon_sec_map:
            self.assertNotEqual(dragon_sec_map["600172"], "国企改革")
            self.assertIn(dragon_sec_map["600172"], ["超硬材料", "培育钻石", "光伏概念"])

    def test_condiments_and_regional_sectors_cleansing(self):
        """测试调味品行业与概念深度融合，彻底纠正爱普股份误入烟草，并拦截海峡两岸等区域泛概念"""
        from stock_logic_utils import combine_industry_and_category
        from ats.sector_rotation_pullback_miner import SectorRotationPullbackMiner

        # 1. 验证行业与概念深度融合：爱普股份调味品置顶
        comb_aipu = combine_industry_and_category("人造肉;烟草概念;新型烟草", "调味品")
        self.assertTrue(comb_aipu.startswith("调味品"), f"爱普股份首项应为调味品，实际为: {comb_aipu}")
        self.assertIn("人造肉", comb_aipu)

        # 2. 验证纯地理区域泛概念被拦截
        self.assertTrue(is_generic_concept("海峡两岸"))
        self.assertTrue(is_generic_concept("西部大开发"))
        self.assertTrue(is_generic_concept("长三角一体化"))
        self.assertTrue(is_generic_concept("一带一路"))

        # 3. 模拟全市场数据：调味品板块合力爆发 (爱普股份首板 + 莲花控股2板 + 日辰股份大涨)
        mock_df = pd.DataFrame({
            "603020": {
                "name": "爱普股份", "close": 11.17, "percent": 10.05, "pct": 10.05, "dff": 0.0, # 模拟盘中 dff 暂时为 0
                "amount": 1.69e8, "vol_ratio": 2.16, "category": "人造肉;烟草概念;新型烟草", "industry": "调味品",
                "dff2": 6.4, "dff3": 12.0
            },
            "600186": {
                "name": "莲花控股", "close": 13.18, "percent": 10.02, "pct": 10.02, "dff": 2.5,
                "amount": 3.49e8, "vol_ratio": 1.62, "category": "食品安全;预制菜", "industry": "调味品",
                "dff2": 7.0, "dff3": 15.0
            },
            "603755": {
                "name": "日辰股份", "close": 24.96, "percent": 4.17, "pct": 4.17, "dff": 1.8,
                "amount": 3.89e7, "vol_ratio": 1.35, "category": "食品安全", "industry": "调味品",
                "dff2": 3.2, "dff3": 5.0
            },
            # 顺灏股份 (单独电子烟/包装印刷)
            "002565": {
                "name": "顺灏股份", "close": 3.5, "percent": 2.0, "pct": 2.0, "dff": 1.0,
                "amount": 8.0e7, "vol_ratio": 1.1, "category": "新型烟草;包装印刷", "industry": "造纸印刷",
                "dff2": 2.0, "dff3": 3.0
            },
            # 福建水泥 (海峡两岸，但全板块只有它涨，其他在跌)
            "600802": {
                "name": "福建水泥", "close": 5.5, "percent": 10.0, "pct": 10.0, "dff": 2.0,
                "amount": 1.2e8, "vol_ratio": 1.8, "category": "海峡两岸;国企改革", "industry": "水泥建材",
                "dff2": 5.0, "dff3": 6.0
            }
        }).T

        miner = SectorRotationPullbackMiner.get_instance()
        leading_sectors = miner.identify_leading_sectors(mock_df, min_pioneers_per_sector=2)

        sec_names = [s["name"] for s in leading_sectors]

        # 核心断言一：【调味品】必须作为主线被挖掘出来！
        self.assertIn("调味品", sec_names, "调味品行业群起爆发未被成功识别为主线！")

        # 核心断言二：绝不能出现“海峡两岸”作为主线！
        self.assertNotIn("海峡两岸", sec_names, "纯地理泛概念'海峡两岸'不应进入主线！")

        # 核心断言三：调味品板块的领涨龙头应为爱普股份或莲花控股，且涨幅绝非 (+0.0%)
        cond_sec = next(s for s in leading_sectors if s["name"] == "调味品")
        self.assertIn(cond_sec["leader_name"], ["爱普股份", "莲花控股"])
        self.assertGreater(cond_sec["leader_pct"], 9.0, "领涨先锋龙头涨幅兜底失败，不应为0.0%！")


if __name__ == "__main__":
    unittest.main()
