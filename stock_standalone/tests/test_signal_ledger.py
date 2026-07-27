# -*- coding: utf-8 -*-
"""
ATS Signal Ledger & Volume Profiler Unit Tests
验证增量账本写入、优先级评分、时段识别以及连续缩量逻辑的正确性。
"""

import sys
import os
import unittest
import time
import datetime
import pandas as pd

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.signal_ledger import SignalLedger, _detect_phase, _compute_time_score
from ats.volume_profiler import VolumeProfiler, MarketVolumeContext


class TestSignalLedger(unittest.TestCase):
    
    def setUp(self):
        self.ledger = SignalLedger()
        self.profiler = VolumeProfiler()
        
    def test_detect_phase(self):
        """测试交易时段识别"""
        # 测试集合竞价 09:20
        dt_auction = datetime.datetime.now().replace(hour=9, minute=20, second=0)
        ts_auction = time.mktime(dt_auction.timetuple())
        self.assertEqual(_detect_phase(ts_auction), 'AUCTION')
        
        # 测试黄金早盘 09:45
        dt_golden = datetime.datetime.now().replace(hour=9, minute=45, second=0)
        ts_golden = time.mktime(dt_golden.timetuple())
        self.assertEqual(_detect_phase(ts_golden), 'GOLDEN')
        
        # 测试下午盘中 13:30
        dt_afternoon = datetime.datetime.now().replace(hour=13, minute=30, second=0)
        ts_afternoon = time.mktime(dt_afternoon.timetuple())
        self.assertEqual(_detect_phase(ts_afternoon), 'AFTERNOON')
        
    def test_compute_time_score(self):
        """测试时间基础分数衰减"""
        # 竞价时段固定 100 分
        self.assertEqual(_compute_time_score('AUCTION'), 100.0)
        
        # 黄金早盘开盘瞬间高分，随后衰减
        dt_start = datetime.datetime.now().replace(hour=9, minute=30, second=0)
        ts_start = time.mktime(dt_start.timetuple())
        score_start = _compute_time_score('GOLDEN', ts_start)
        
        dt_later = datetime.datetime.now().replace(hour=9, minute=50, second=0)
        ts_later = time.mktime(dt_later.timetuple())
        score_later = _compute_time_score('GOLDEN', ts_later)
        
        self.assertTrue(score_start > score_later)
        
    def test_record_signal_and_lock(self):
        """测试信号增量写入与时间戳锁定"""
        code = "601606"  # 长城军工
        name = "长城军工"
        
        # 首次录入信号 (偏离度 0.5%)
        entry1 = self.ledger.record_signal(code, name, 12.50, 1.5, 0.5)
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.first_seen_price, 12.50)
        first_seen_ts = entry1.first_seen_ts
        
        # 模拟 3 秒后再次推送行情，股价拉升 (偏离度上升到 3.5%)
        time.sleep(0.1)  # 短暂休眠模拟延迟
        entry2 = self.ledger.record_signal(code, name, 12.80, 3.8, 3.5)
        
        # 验证: 首次发现价格与时间戳保持不变
        self.assertEqual(entry2.first_seen_price, 12.50)
        self.assertEqual(entry2.first_seen_ts, first_seen_ts)
        # 验证: 最新价格得到更新
        self.assertEqual(entry2.latest_price, 12.80)
        
    def test_consecutive_shrink_days(self):
        """测试个股连续缩量逻辑"""
        # 模拟昨日成交量 100w < 前日 150w < 大前日 200w (连续缩量 2 天)
        row = {
            'lastv1d': 1000000,
            'lastv2d': 1500000,
            'lastv3d': 2000000,
            'lastv4d': 1800000, # 没连续缩量了
        }
        
        shrink_days = self.profiler._calc_consecutive_shrink_days(row)
        self.assertEqual(shrink_days, 2)
        
    def test_market_rebound_from_shrink(self):
        """测试大盘连续缩量后放量反弹感知"""
        # 模拟大盘连续缩量 3 天
        # sh000001 的 lastv1d (100) < lastv2d (150) < lastv3d (200) < lastv4d (250)
        df_market = pd.DataFrame({
            'lastv1d': [100.0],
            'lastv2d': [150.0],
            'lastv3d': [200.0],
            'lastv4d': [250.0],
            'lastv5d': [300.0],
            'vol_ratio': [1.3], # 放量反弹
            'percent': [1.8]
        }, index=['sh000001'])
        
        context = MarketVolumeContext()
        context.update(df_market)
        
        self.assertEqual(context.consecutive_market_shrink_days, 4)
        self.assertTrue(context.is_rebound_from_shrink)
        self.assertTrue(context.rebound_quality > 50.0)

    def test_recent_up_days_and_consecutive_up(self):
        """测试连阳连涨形态计算 (长城军工 3连阳/6天连阳)"""
        # 模拟 3 连阳: lastp1d (12.5) > lastp2d (12.2) > lastp3d (12.0) > lastp4d (11.9)
        # 今日当前 close (13.0) 相比昨日继续上涨
        row = {
            'close': 13.0,
            'lastp1d': 12.5,
            'lastp2d': 12.2,
            'lastp3d': 12.0,
            'lastp4d': 11.9,
            'lastp5d': 11.5,
            'lastp6d': 11.2,
            'lastp7d': 11.3, # 连阳在此中断
        }
        
        recent_up_3d = self.profiler._calc_recent_up_days_3d(row)
        consecutive_up = self.profiler._calc_consecutive_up_days(row)
        
        # 验证: 前3日均收阳 (收涨)
        self.assertEqual(recent_up_3d, 3)
        # 验证: 加上今日 13.0，连续收阳天数为 6 天 (从 lastp6d 的 11.2 连续涨到今日 13.0)
        self.assertEqual(consecutive_up, 6)

    def test_sector_resonance_leader_follower(self):
        """测试板块联动：龙头带队(长城军工)与小弟跟风(北方长龙)共振评分"""
        # 模拟长城军工 (09:20 竞价即启动放量，主所属: 国防军工)
        now_ts = time.time()
        row_ccjg = {
            'name': '长城军工',
            'category': '国防军工;地面兵装;军工概念',
            'vol_ratio': 3.5,
            'lastp1d': 12.0, 'lastp2d': 11.8, 'lastp3d': 11.6, 'lastp4d': 11.5,
        }
        
        # 模拟北方长龙 (09:35 黄金早盘启动放量，所属同一板块)
        row_bfcl = {
            'name': '北方长龙',
            'category': '国防军工;地面兵装;军工概念',
            'vol_ratio': 2.5,
            'lastp1d': 90.0, 'lastp2d': 90.5, 'lastp3d': 89.0, 'lastp4d': 90.0,
        }
        
        # 1. 模拟行情先更新长城军工 (竞价时段)
        self.profiler.update_profile("601606", row_ccjg)
        profile_ccjg = self.profiler.get_profile("601606")
        profile_ccjg.first_surge_ts = now_ts - 900  # 假设比北方长龙早 15 分钟启动
        
        # 2. 模拟行情更新北方长龙 (黄金早盘)
        self.profiler.update_profile("301357", row_bfcl)
        profile_bfcl = self.profiler.get_profile("301357")
        profile_bfcl.first_surge_ts = now_ts
        
        # 3. 运行板块共振与联动分析
        self.profiler.analyze_sector_resonance(active_codes=["601606", "301357"])
        
        # 4. 验证板块领涨识别
        self.assertTrue(profile_ccjg.is_sector_leader)
        self.assertFalse(profile_ccjg.is_sector_follower)
        
        # 5. 验证跟风小弟识别
        self.assertFalse(profile_bfcl.is_sector_leader)
        self.assertTrue(profile_bfcl.is_sector_follower)
        self.assertEqual(profile_bfcl.sector_leader_code, "601606")
        
        # 6. 验证跟风分提权 (北方长龙获得 +8.0 板块联动加分)
        # 初始评分若排除板块共振，应该较低；加分后，其 vol_score 显著拉升，有助于在池中排前
        self.assertTrue(profile_bfcl.volume_score > 25.0)

    def test_cross_day_signal_restoration(self):
        """测试跨日信号恢复 (load_previous_signals)"""
        # 模拟昨日快照字典
        prev_snapshot = {
            '601606': {
                'code': '601606',
                'name': '长城军工',
                'latest_price': 12.8,
                'latest_pct': 3.5,
                'latest_deviation': 1.2,
                'tier': 'WATCH'
            },
            '001254': {
                'code': '001254',
                'name': '立新能源',
                'latest_price': 5.60,
                'latest_pct': 2.1,
                'latest_deviation': 0.8,
                'tier': 'TRADE'
            }
        }
        
        # 载入昨日快照
        self.ledger.load_previous_signals(prev_snapshot)
        
        # 验证: 账本恢复了 2 只信号
        self.assertEqual(len(self.ledger.entries), 2)
        self.assertIn('601606', self.ledger.entries)
        self.assertIn('001254', self.ledger.entries)
        
        # 验证: 恢复的信号层级重置为 RADAR，时间段重置为 PREMARKET (盘前)
        entry_601606 = self.ledger.entries['601606']
        self.assertEqual(entry_601606.tier, 'RADAR')
        self.assertEqual(entry_601606.first_seen_phase, 'PREMARKET')
        
        # 验证: 恢复信号后若今日出现放量异动，依然可以被正常更新并自动晋级
        self.ledger.record_signal('601606', '长城军工', 13.5, 5.2, 2.1, row={'vol_ratio': 1.8})
        self.assertEqual(entry_601606.tier, 'WATCH')  # 再次自动晋级为 WATCH


if __name__ == '__main__':
    unittest.main()
