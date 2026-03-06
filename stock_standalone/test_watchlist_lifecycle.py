# -*- coding: utf-8 -*-
"""
热股观察队列 (hot_stock_watchlist) 完整生命周期测试

测试流程: 发现 → 写入观察 → 跨日验证 → 晋升跟单 → 持仓强弱评估
使用 601869(长飞光纤)/002440(闰土股份)/603103(横店影视) 的模拟数据
"""
import os
import sys
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from trading_hub import TradingHub


class TestWatchlistLifecycle(unittest.TestCase):
    """热股观察队列完整生命周期测试"""

    def setUp(self):
        """每个测试使用独立临时数据库"""
        self.test_dir = tempfile.mkdtemp()
        self.signal_db = os.path.join(self.test_dir, "test_signal.db")
        self.trading_db = os.path.join(self.test_dir, "test_trading.db")
        self.hub = TradingHub(signal_db=self.signal_db, trading_db=self.trading_db)

    def tearDown(self):
        """清理临时文件"""
        for f in [self.signal_db, self.trading_db]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except:
                    pass

    # ===== Phase 1: 写入观察队列 =====
    def test_add_to_watchlist(self):
        """测试热股写入观察队列"""
        result = self.hub.add_to_watchlist('601869', '长飞光纤', '光通信', 28.0)
        self.assertTrue(result, "首次写入应成功")

        # 同日去重
        result2 = self.hub.add_to_watchlist('601869', '长飞光纤', '光通信', 29.0)
        self.assertFalse(result2, "同日同代码不应重复写入")

        # 不同代码应可以写入
        result3 = self.hub.add_to_watchlist('002440', '闰土股份', '化工', 15.0)
        self.assertTrue(result3, "不同代码应可写入")

    def test_add_multiple_and_query(self):
        """测试批量写入与查询"""
        stocks = [
            ('601869', '长飞光纤', '光通信', 28.0),
            ('002440', '闰土股份', '化工', 15.0),
            ('603103', '横店影视', '影视', 22.0),
        ]
        for code, name, sector, price in stocks:
            self.hub.add_to_watchlist(code, name, sector, price)

        df = self.hub.get_watchlist_df()
        self.assertEqual(len(df), 3, "应有3条记录")

        # 按状态查询
        df_watching = self.hub.get_watchlist_df(status='WATCHING')
        self.assertEqual(len(df_watching), 3, "全部应为WATCHING状态")

    # ===== Phase 2: 跨日验证 =====
    def test_validate_strong_stock(self):
        """测试强势股验证通过"""
        self.hub.add_to_watchlist('601869', '长飞光纤', '光通信', 28.0)

        # 模拟强势数据: close>MA5>MA10, 沿upper攀升, 新高, 量比>1.2
        ohlc = {
            '601869': {
                'close': 33.0, 'high': 33.5, 'low': 31.0, 'open': 31.5,
                'ma5': 30.0, 'ma10': 28.5,
                'upper': 32.0,   # close >= upper*0.98
                'high4': 32.0,   # close > high4 → 新高
                'volume_ratio': 1.5,
                'win': 3,
            }
        }
        results = self.hub.validate_watchlist(ohlc)
        # trend: +0.3(MA) +0.3(upper) +0.2(新高) +0.1(连阳) = 0.9, vol: 0.2 → total=1.1
        # consecutive_strong = 1 (初始0+1=1)
        self.assertEqual(len(results['validated']), 1, "强势股应验证通过")
        self.assertEqual(len(results['dropped']), 0)

    def test_validate_weak_stock_dropped(self):
        """测试弱势股被淘汰"""
        self.hub.add_to_watchlist('999999', '测试弱股', '测试', 20.0)

        # 模拟弱势: 跌破MA10
        ohlc = {
            '999999': {
                'close': 17.0, 'high': 18.0, 'low': 16.5, 'open': 18.0,
                'ma5': 18.5, 'ma10': 19.0,
                'upper': 20.0,
                'high4': 20.0,
                'volume_ratio': 0.8,
                'win': -2,
            }
        }
        results = self.hub.validate_watchlist(ohlc)
        self.assertEqual(len(results['dropped']), 1, "弱势股应被淘汰")
        self.assertIn('跌破', results['dropped'][0])  # 跌破MA10 或 跌破发现价

    def test_validate_price_crash_dropped(self):
        """测试跌破发现价7%淘汰"""
        self.hub.add_to_watchlist('888888', '测试崩盘', '测试', 100.0)

        ohlc = {
            '888888': {
                'close': 92.0,  # < 100*0.93=93
                'high': 93.0, 'low': 91.0, 'open': 93.0,
                'ma5': 95.0, 'ma10': 120.0,  # 也跌破MA10
                'upper': 100.0,
                'high4': 100.0,
                'volume_ratio': 0.5,
                'win': -3,
            }
        }
        results = self.hub.validate_watchlist(ohlc)
        self.assertEqual(len(results['dropped']), 1)
        self.assertIn('7%', results['dropped'][0])

    def test_validate_watching_continues(self):
        """测试中性股继续观察"""
        self.hub.add_to_watchlist('777777', '测试中性', '测试', 50.0)

        # 中性：没有跌破MA10但也没足够强
        ohlc = {
            '777777': {
                'close': 50.5, 'high': 51.0, 'low': 50.0, 'open': 50.2,
                'ma5': 50.0, 'ma10': 49.0,
                'upper': 55.0,   # close < upper*0.98
                'high4': 51.5,   # close < high4
                'volume_ratio': 0.9,
                'win': 0,
            }
        }
        results = self.hub.validate_watchlist(ohlc)
        # trend: +0.3(MA) +0(upper不够) +0(没新高) +0(没连阳) = 0.3
        # < 0.5 → 继续观察
        self.assertEqual(len(results['watching']), 1)

    # ===== Phase 3: 晋升跟单 =====
    def test_promote_to_follow_queue(self):
        """测试验证通过后晋升到跟单队列"""
        self.hub.add_to_watchlist('601869', '长飞光纤', '光通信', 28.0)

        # 先验证通过
        ohlc = {
            '601869': {
                'close': 33.0, 'high': 33.5, 'low': 31.0, 'open': 31.5,
                'ma5': 30.0, 'ma10': 28.5,
                'upper': 32.0, 'high4': 32.0,
                'volume_ratio': 1.5, 'win': 3,
            }
        }
        self.hub.validate_watchlist(ohlc)

        # 晋升
        promoted = self.hub.promote_validated_stocks()
        self.assertIn('601869', promoted)

        # 验证 follow_queue 中存在
        queue = self.hub.get_follow_queue()
        codes = [s.code for s in queue]
        self.assertIn('601869', codes)

        # 入场策略应为竞价买入
        signal = [s for s in queue if s.code == '601869'][0]
        self.assertEqual(signal.entry_strategy, '竞价买入')
        self.assertIn('热股验证', signal.source)

        # 不应重复晋升
        promoted2 = self.hub.promote_validated_stocks()
        self.assertEqual(len(promoted2), 0)

    def test_promote_with_priority(self):
        """测试晋升优先级计算"""
        self.hub.add_to_watchlist('002440', '闰土股份', '化工', 15.0)

        # 高分验证
        ohlc = {
            '002440': {
                'close': 18.0, 'high': 18.5, 'low': 17.0, 'open': 17.5,
                'ma5': 16.0, 'ma10': 15.0,
                'upper': 17.5, 'high4': 17.5,
                'volume_ratio': 2.0, 'win': 4,
            }
        }
        self.hub.validate_watchlist(ohlc)
        promoted = self.hub.promote_validated_stocks()
        self.assertEqual(len(promoted), 1)

        # 检查优先级 (score=1.1 >= 0.8 → priority=12, new_high → +2, cs insufficient for +1)
        queue = self.hub.get_follow_queue()
        signal = [s for s in queue if s.code == '002440'][0]
        self.assertGreaterEqual(signal.priority, 12, "高分股应有高优先级")

    # ===== Phase 4: 持仓强弱评估 =====
    def test_evaluate_strong_holding(self):
        """测试强势持仓评估"""
        from trading_hub import TrackedSignal
        # 先手动写入一条 ENTERED 状态的跟单
        signal = TrackedSignal(
            code='601869', name='长飞光纤', signal_type='验证通过',
            detected_date='2026-02-09', detected_price=28.0,
            entry_strategy='竞价买入', entry_price=30.0,
            status='ENTERED', priority=8
        )
        self.hub.add_to_follow_queue(signal)
        self.hub.update_follow_status('601869', 'ENTERED')

        # 强势数据
        ohlc = {
            '601869': {
                'close': 35.0, 'high': 35.5, 'low': 34.0, 'open': 34.5,
                'ma5': 33.0, 'ma10': 31.0,
                'upper': 34.5,
                'volume_ratio': 1.3,
            }
        }
        results = self.hub.evaluate_holding_strength(ohlc)
        self.assertEqual(len(results['strong']), 1)
        self.assertIn('站稳MA5', results['strong'][0])

    def test_evaluate_weak_pump_dump(self):
        """测试冲高回落判定为弱势"""
        from trading_hub import TrackedSignal
        signal = TrackedSignal(
            code='999999', name='测试冲高', signal_type='测试',
            detected_date='2026-02-09', detected_price=50.0,
            entry_strategy='竞价买入', entry_price=52.0,
            status='ENTERED', priority=5
        )
        self.hub.add_to_follow_queue(signal)
        self.hub.update_follow_status('999999', 'ENTERED')

        # 冲高回落: high涨7%但收阴
        ohlc = {
            '999999': {
                'close': 49.0,  # < open=50.0 → 收阴
                'high': 53.5,   # (53.5-50)/50*100=7% > 5%
                'low': 48.5, 'open': 50.0,
                'ma5': 51.0, 'ma10': 50.5,
                'upper': 52.0,
                'volume_ratio': 2.0,
            }
        }
        results = self.hub.evaluate_holding_strength(ohlc)
        self.assertEqual(len(results['weak']), 1)
        self.assertIn('冲高回落', results['weak'][0])

    # ===== Phase 5: 完整生命周期 =====
    def test_full_lifecycle(self):
        """完整闭环测试: 发现→观察→验证→晋升→持仓评估"""
        # 1. 发现热股
        self.hub.add_to_watchlist('601869', '长飞光纤', '光通信', 28.0)
        self.hub.add_to_watchlist('999999', '弱势股', '测试', 50.0)

        summary = self.hub.get_watchlist_summary()
        self.assertEqual(summary['total'], 2)

        # 2. 跨日验证 (D+1)
        ohlc_d1 = {
            '601869': {
                'close': 33.0, 'high': 33.5, 'low': 31.0, 'open': 31.5,
                'ma5': 30.0, 'ma10': 28.5,
                'upper': 32.0, 'high4': 32.0,
                'volume_ratio': 1.5, 'win': 3,
            },
            '999999': {
                'close': 44.0, 'high': 45.0, 'low': 43.0, 'open': 45.0,
                'ma5': 48.0, 'ma10': 50.0,  # 跌破MA10 → DROP
                'upper': 52.0, 'high4': 51.0,
                'volume_ratio': 0.5, 'win': -2,
            }
        }
        results = self.hub.validate_watchlist(ohlc_d1)
        self.assertEqual(len(results['validated']), 1, "长飞光纤应验证通过")
        self.assertEqual(len(results['dropped']), 1, "弱势股应被淘汰")

        # 3. 晋升到跟单
        promoted = self.hub.promote_validated_stocks()
        self.assertIn('601869', promoted)

        # 4. 模拟入场
        self.hub.update_follow_status('601869', 'ENTERED', notes='竞价买入@33.0')

        # 5. 持仓评估
        ohlc_d2 = {
            '601869': {
                'close': 36.0, 'high': 36.5, 'low': 35.0, 'open': 35.0,
                'ma5': 33.0, 'ma10': 31.0,
                'upper': 35.0,
                'volume_ratio': 1.2,
            }
        }
        strength = self.hub.evaluate_holding_strength(ohlc_d2)
        self.assertEqual(len(strength['strong']), 1, "长飞光纤持仓应评估为强势")

        print("\n✅ 完整生命周期测试通过: 发现→验证→晋升→持仓评估→强势确认")


if __name__ == '__main__':
    unittest.main(verbosity=2)
