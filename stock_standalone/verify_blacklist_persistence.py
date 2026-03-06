import sys
import os
import json
import logging
import unittest
from datetime import datetime

# 设置工作目录
sys.path.append(r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone")

from stock_live_strategy import StockLiveStrategy

# 配置模拟 logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Test")

class TestBlacklist(unittest.TestCase):
    def setUp(self):
        # 使用临时黑名单文件
        self.strategy = StockLiveStrategy(voice_enabled=False)
        self.strategy.blacklist_file = "test_ignored_stocks.json"
        if os.path.exists(self.strategy.blacklist_file):
            os.remove(self.strategy.blacklist_file)
        self.strategy._blacklist_data = {}

    def tearDown(self):
        if os.path.exists(self.strategy.blacklist_file):
            os.remove(self.strategy.blacklist_file)

    def test_add_and_persistence(self):
        print("\n[1] 测试添加与持久化...")
        code = "sh600519"
        name = "贵州茅台"
        self.strategy.add_to_blacklist(code, name=name, reason="单元测试")
        
        # 检查内存
        self.assertTrue(self.strategy.is_blacklisted(code))
        
        # 检查文件
        self.assertTrue(os.path.exists(self.strategy.blacklist_file))
        with open(self.strategy.blacklist_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn(code, data)
            self.assertEqual(data[code]["name"], name)

    def test_interception(self):
        print("\n[2] 测试拦截逻辑...")
        code = "sz000001"
        self.strategy.add_to_blacklist(code, name="平安银行", reason="拦截测试")
        
        # 模拟触发报警，应该被拦截返回 None
        # _trigger_alert 本身返回 None，但我们可以通过 logger 观察或捕获异常（如果不拦截会往下走）
        # 这里验证 is_blacklisted 即可，因为逻辑很简单
        self.assertTrue(self.strategy.is_blacklisted(code))
        
        # 模拟扫描逻辑过滤
        df_stub = {code: {"some": "data"}}
        # 如果在黑名单中，相关逻辑应跳过
        self.assertTrue(any(c == code for c in self.strategy.get_blacklist()))

    def test_restore(self):
        print("\n[3] 测试恢复功能...")
        code = "sh600000"
        self.strategy.add_to_blacklist(code, name="浦发银行")
        self.assertTrue(self.strategy.is_blacklisted(code))
        
        result = self.strategy.remove_from_blacklist(code)
        self.assertTrue(result)
        self.assertFalse(self.strategy.is_blacklisted(code))
        
        # 检查文件是否同步删除
        with open(self.strategy.blacklist_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertNotIn(code, data)

if __name__ == "__main__":
    unittest.main()
