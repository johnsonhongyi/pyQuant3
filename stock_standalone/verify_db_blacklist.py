import unittest
import os
import sqlite3
import pandas as pd
from datetime import datetime
from trading_logger import TradingLogger
from stock_live_strategy import StockLiveStrategy

class TestDatabaseBlacklist(unittest.TestCase):
    def setUp(self):
        # 使用测试数据库
        self.test_db = "test_trading_signals.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.logger = TradingLogger(db_path=self.test_db)
        # 强制策略使用测试 logger
        self.strategy = StockLiveStrategy()
        self.strategy.trading_logger = self.logger
        self.strategy._load_blacklist()

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_blacklist_crud_in_db(self):
        """测试黑名单的增删查改 (数据库级别)"""
        code = "600000.SH"
        name = "浦发银行"
        reason = "test_reason"
        
        # 1. 添加
        self.strategy.add_to_blacklist(code, name, reason)
        
        # 2. 检查数据库
        conn = sqlite3.connect(self.test_db)
        cur = conn.cursor()
        cur.execute("SELECT name, reason, hit_count FROM live_blacklist WHERE code=?", (code,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], name)
        self.assertEqual(row[1], reason)
        self.assertEqual(row[2], 0) # 初始 hit_count 为 0
        conn.close()
        
        # 3. 检查 is_blacklisted
        self.assertTrue(self.strategy.is_blacklisted(code))
        
        # 4. 移除
        self.strategy.remove_from_blacklist(code)
        self.assertFalse(self.strategy.is_blacklisted(code))
        
        # 5. 检查数据库是否真的删了
        conn = sqlite3.connect(self.test_db)
        cur = conn.cursor()
        cur.execute("SELECT * FROM live_blacklist WHERE code=?", (code,))
        self.assertIsNone(cur.fetchone())
        conn.close()

    def test_hit_count_increment(self):
        """测试触发报警时命中次数是否正确累加"""
        code = "000001.SZ"
        name = "平安银行"
        self.strategy.add_to_blacklist(code, name, "hit_test")
        
        # 预设 hit_count 应为 0
        self.assertEqual(self.strategy.get_blacklist()[code]['hit_count'], 0)
        
        # 伪造触发报警并被拦截
        self.strategy._trigger_alert(code, name, "Should be blocked")
        
        # 重新加载检查
        self.strategy._load_blacklist()
        self.assertEqual(self.strategy._blacklist_data[code]['hit_count'], 1)
        
        # 再次触发
        self.strategy._trigger_alert(code, name, "Still blocked")
        self.strategy._load_blacklist()
        self.assertEqual(self.strategy._blacklist_data[code]['hit_count'], 2)

    def test_clear_daily(self):
        """测试按日期清空"""
        self.strategy.add_to_blacklist("C1", "N1", "R1")
        # 强制修改数据库日期模拟往日数据 (手动通过 sqlite3 操作)
        conn = sqlite3.connect(self.test_db)
        conn.execute("UPDATE live_blacklist SET added_date='2020-01-01' WHERE code='C1'")
        conn.commit()
        
        self.strategy.add_to_blacklist("C2", "N2", "R2") # 今日数据
        
        # 清空今日
        self.logger.clear_daily_blacklist()
        
        self.strategy._load_blacklist()
        self.assertIn("C1", self.strategy._blacklist_data) # 往日数据不应删
        self.assertNotIn("C2", self.strategy._blacklist_data) # 今日数据应删

if __name__ == "__main__":
    unittest.main()
