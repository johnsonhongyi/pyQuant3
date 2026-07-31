# -*- coding: utf-8 -*-
"""
Unit Tests for TDX Signal Watcher & Configuration Integration
验证 commonTips 配置获取/设置、通达信信号文本解析以及 SignalLedger 的自动提权联动
"""

import sys
import os
import unittest
import tempfile
import datetime

# 将项目根目录添加到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from JohnsonUtil import commonTips as cct
from ats.tdx_signal_watcher import parse_tdx_signal_line, load_ordermon_flag_map, TdxSignalWatcher
from ats.signal_ledger import SignalLedger


class TestTdxSignalWatcher(unittest.TestCase):

    def test_get_set_tdx_signal_path(self):
        """测试 commonTips 中的通达信信号路径动态配置 getter / setter"""
        default_path = cct.get_tdx_signal_path()
        self.assertIsNotNone(default_path)
        self.assertTrue(isinstance(default_path, str))

        # 测试自定义写入新路径
        test_custom_path = r"D:\TestCustomTdxSignal.txt"
        success = cct.set_tdx_signal_path(test_custom_path)
        self.assertTrue(success)

        read_back_path = cct.get_tdx_signal_path()
        self.assertEqual(read_back_path, test_custom_path)

        # 还原默认配置
        cct.set_tdx_signal_path(r"D:\TdxSignal.txt")
        self.assertEqual(cct.get_tdx_signal_path(), r"D:\TdxSignal.txt")

        # 测试 OrderMon.ini 路径配置 getter / setter
        default_ini = cct.get_ordermon_ini_path()
        self.assertIsNotNone(default_ini)
        test_custom_ini = r"D:\TestCustomOrderMon.ini"
        cct.set_ordermon_ini_path(test_custom_ini)
        self.assertEqual(cct.get_ordermon_ini_path(), test_custom_ini)
        cct.set_ordermon_ini_path(r"D:\MacTools\OrderMonitor\OrderMon.ini")
        self.assertEqual(cct.get_ordermon_ini_path(), r"D:\MacTools\OrderMonitor\OrderMon.ini")

    def test_parse_tdx_signal_line(self):
        """测试单行通达信 / OrderMon 信号解析"""
        today_ymd = datetime.date.today().strftime('%Y%m%d')
        sample_line = f"{today_ymd}|0000|600519|1|11|5|1850.50|0|0|09:35:12|"

        parsed = parse_tdx_signal_line(sample_line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['code'], '600519')
        self.assertEqual(parsed['direction'], 1)
        self.assertEqual(parsed['flag1'], '11')
        self.assertEqual(parsed['flag_label'], '5上10')
        self.assertEqual(parsed['price'], 1850.50)
        self.assertEqual(parsed['time_str'], '09:35:12')

    def test_ordermon_flag_map(self):
        """测试 OrderMon.ini 配置文件标志解析与默认回退"""
        flag_map = load_ordermon_flag_map(r"D:\MacTools\OrderMonitor\OrderMon.ini")
        self.assertIn('11', flag_map)
        self.assertEqual(flag_map['11'], '5上10')
        self.assertEqual(flag_map['1'], 'KDJ金叉')

    def test_record_tdx_signal_in_ledger(self):
        """测试来自通达信的外部信号写入 SignalLedger 并自动提权置顶"""
        ledger = SignalLedger()

        today_ymd = datetime.date.today().strftime('%Y%m%d')
        sig_dict = {
            'code': '601606',
            'name': '长城军工',
            'date_str': today_ymd,
            'direction': 1,
            'direction_cn': '买入',
            'flag1': '11',
            'flag_label': '5上10',
            'price': 12.80,
            'time_str': '09:35:00',
        }

        entry = ledger.record_tdx_signal(sig_dict)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.code, '601606')
        self.assertEqual(entry.tier, 'WATCH')  # 自动晋级为 WATCH
        self.assertEqual(entry.tdx_label, '🔔 TDX 5上10')
        self.assertEqual(entry.tdx_boost, 150.0)
        self.assertTrue(entry.priority_score > 150.0)  # 包含 +150 提权置顶分

        # 验证在池中获取时靠前置顶
        watch_pool = ledger.get_sorted_pool('WATCH')
        self.assertTrue(len(watch_pool) > 0)
        self.assertEqual(watch_pool[0].code, '601606')


if __name__ == '__main__':
    unittest.main()
