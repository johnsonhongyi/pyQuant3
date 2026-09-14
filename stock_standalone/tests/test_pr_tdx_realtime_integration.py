# -*- encoding: utf-8 -*-
"""
tests/test_pr_tdx_realtime_integration.py
验证人气综合排行榜全面接入 TDX API 实时行情更新链路的正确性、接口兼容性与容灾回退能力。
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from popularity_resonance_service import fetch_realtime_quotes, clean_stock_code


class TestPRTDXRealtimeIntegration(unittest.TestCase):
    def test_clean_stock_code(self):
        self.assertEqual(clean_stock_code("sh600127"), "600127")
        self.assertEqual(clean_stock_code("SZ000978"), "000978")
        self.assertEqual(clean_stock_code("688826"), "688826")

    @patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance")
    def test_fetch_realtime_quotes_via_tdx(self, mock_get_instance):
        mock_fetcher = MagicMock()
        mock_get_instance.return_value = mock_fetcher
        
        mock_fetcher.get_security_quotes_safe.return_value = [
            {
                "code": "000978",
                "price": 10.50,
                "last_close": 10.00,
                "open": 10.10,
                "high": 10.60,
                "low": 9.95,
                "vol": 10000.0,
                "amount": 10500000.0,
                "bid1": 10.49,
                "ask1": 10.50,
            },
            {
                "code": "600127",
                "price": 13.00,
                "last_close": 13.50,
                "open": 13.40,
                "high": 13.60,
                "low": 12.90,
                "vol": 20000.0,
                "amount": 26000000.0,
                "bid1": 12.99,
                "ask1": 13.00,
            }
        ]
        
        quotes = fetch_realtime_quotes(["000978", "600127"])
        self.assertIn("000978", quotes)
        self.assertIn("600127", quotes)
        
        q1 = quotes["000978"]
        self.assertEqual(q1["price"], 10.50)
        self.assertEqual(q1["last_close"], 10.00)
        self.assertEqual(q1["percent"], 5.0)
        self.assertEqual(q1["open"], 10.10)
        self.assertEqual(q1["high"], 10.60)
        self.assertEqual(q1["low"], 9.95)
        self.assertEqual(q1["vol"], 10000.0)
        self.assertEqual(q1["amount"], 10500000.0)
        
        q2 = quotes["600127"]
        self.assertEqual(q2["price"], 13.00)
        self.assertEqual(q2["last_close"], 13.50)
        self.assertEqual(q2["percent"], -3.7)

    @patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance")
    def test_pr_gui_refresh_realtime_from_tdx_mock(self, mock_get_instance):
        from popularity_resonance_gui import PRServiceGUI
        
        mock_root = MagicMock()
        mock_root.winfo_exists.return_value = True
        
        with patch.object(PRServiceGUI, '__init__', lambda s, r: None):
            gui = PRServiceGUI(mock_root)
            gui.root = mock_root
            gui.current_date = time.strftime("%Y-%m-%d")
            gui.df_lock = MagicMock()
            gui.df_lock.__enter__ = MagicMock()
            gui.df_lock.__exit__ = MagicMock()
            gui.current_df = None
            gui.resonance_codes = ["000978", "600127"]
            
            # mock 表格
            mock_tree = MagicMock()
            mock_tree.winfo_exists.return_value = True
            mock_tree.get_children.return_value = ["item1", "item2"]
            mock_tree.item.side_effect = lambda iid, attr=None: {
                "item1": ("1", "000978", "桂林旅游", "4.66", "10.33", "0.0%", "0.0%", "4.7", "9.3", "7"),
                "item2": ("2", "600127", "金健米业", "-3.17", "13.12", "0.0%", "0.0%", "-0.4", "154.3", "653")
            }.get(iid, ())
            
            gui.tree_res = mock_tree
            gui.tree_em = MagicMock(winfo_exists=lambda: False)
            gui.tree_ths = MagicMock(winfo_exists=lambda: False)
            gui.tree_lh = MagicMock(winfo_exists=lambda: False)
            gui.tree_tgb = MagicMock(winfo_exists=lambda: False)
            
            # 验证 get_all_displayed_codes
            codes = gui.get_all_displayed_codes()
            self.assertEqual(codes, ["000978", "600127"])
            
            # mock TDX fetcher
            mock_fetcher = MagicMock()
            mock_get_instance.return_value = mock_fetcher
            mock_fetcher.get_security_quotes_safe.return_value = [
                {"code": "000978", "price": 10.80, "last_close": 10.00, "open": 10.20, "high": 10.85, "low": 10.10, "vol": 15000.0, "amount": 16000000.0},
                {"code": "600127", "price": 13.50, "last_close": 13.00, "open": 13.10, "high": 13.60, "low": 12.95, "vol": 25000.0, "amount": 33000000.0}
            ]
            
            tdx_df = pd.DataFrame([
                {"code": "000978", "trade": 10.80, "price": 10.80, "close": 10.80, "open": 10.20, "high": 10.85, "low": 10.10, "last_close": 10.00, "percent": 8.0, "volume": 15000.0, "vol": 15000.0, "amount": 16000000.0, "vwap": 10.67, "bid1": 10.79, "ask1": 10.80},
                {"code": "600127", "trade": 13.50, "price": 13.50, "close": 13.50, "open": 13.10, "high": 13.60, "low": 12.95, "last_close": 13.00, "percent": 3.85, "volume": 25000.0, "vol": 25000.0, "amount": 33000000.0, "vwap": 13.20, "bid1": 13.49, "ask1": 13.50},
            ])
            tdx_df.set_index("code", drop=False, inplace=True)
            mock_fetcher.convert_quotes_to_df.return_value = tdx_df
            
            gui.get_current_df = lambda: gui.current_df
            gui.refresh_realtime_fields = MagicMock()
            
            gui.refresh_realtime_from_tdx()
            
            # 校验 current_df 成功更新
            self.assertIsNotNone(gui.current_df)
            self.assertIn("000978", gui.current_df.index)
            self.assertEqual(gui.current_df.loc["000978", "price"], 10.80)
            self.assertEqual(gui.current_df.loc["000978", "percent"], 8.0)
            
            # 校验调度了 refresh_realtime_fields
            mock_root.after.assert_called()

    @patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance")
    def test_refresh_realtime_fields_with_tdx_quotes(self, mock_get_instance):
        from popularity_resonance_gui import PRServiceGUI

        mock_root = MagicMock()
        with patch.object(PRServiceGUI, '__init__', lambda s, r: None):
            gui = PRServiceGUI(mock_root)
            gui.root = mock_root
            gui.current_date = time.strftime("%Y-%m-%d")
            gui.df_lock = MagicMock()
            gui.df_lock.__enter__ = MagicMock()
            gui.df_lock.__exit__ = MagicMock()
            gui.current_df = None
            gui._BASE_FIXED_COLS = ("idx", "code", "name", "val", "price", "velocity", "vwap_dev", "dff2", "dff3", "rank")
            gui._get_all_cols = lambda: (None, None, [])
            gui.segment_mode = '60m'
            gui.update_concept_ranking = MagicMock()

            # mock tree
            items_store = {
                "item1": {"values": ("1", "000978", "桂林旅游", "4.66", "10.33", "0.0%", "0.0%", "4.7", "9.3", "7"), "tags": ("up",)},
                "item2": {"values": ("2", "600127", "金健米业", "-3.17", "13.12", "0.0%", "0.0%", "-0.4", "154.3", "653"), "tags": ("down", "favorite")}
            }
            mock_tree = MagicMock()
            mock_tree.winfo_exists.return_value = True
            mock_tree.cget.return_value = gui._BASE_FIXED_COLS
            mock_tree.get_children.return_value = ["item1", "item2"]

            def mock_item(iid, *args, **kwargs):
                if not args and not kwargs:
                    return items_store[iid]
                if "values" in kwargs:
                    items_store[iid]["values"] = kwargs["values"]
                if "tags" in kwargs:
                    items_store[iid]["tags"] = kwargs["tags"]
                if args and args[0] == "values":
                    return items_store[iid]["values"]
                if args and args[0] == "tags":
                    return items_store[iid]["tags"]
                return items_store[iid]

            mock_tree.item.side_effect = mock_item

            gui.tree_res = mock_tree
            gui.tree_em = MagicMock(winfo_exists=lambda: False)
            gui.tree_ths = MagicMock(winfo_exists=lambda: False)
            gui.tree_lh = MagicMock(winfo_exists=lambda: False)
            gui.tree_tgb = MagicMock(winfo_exists=lambda: False)

            # mock tdx_fetcher
            mock_fetcher = MagicMock()
            mock_get_instance.return_value = mock_fetcher
            mock_fetcher.calculate_segmented_velocity.return_value = {"velocity_pct": 2.5}

            # 传入 tdx_quotes 且 df 为空（模拟无 IPC 时的 TDX 直拉更新）
            tdx_quotes = {
                "000978": {"code": "000978", "price": 11.20, "last_close": 10.00, "open": 10.50, "high": 11.30, "low": 10.40, "vol": 30000.0, "amount": 33000000.0},
                "600127": {"code": "600127", "price": 12.80, "last_close": 13.50, "open": 13.00, "high": 13.10, "low": 12.70, "vol": 40000.0, "amount": 51000000.0}
            }

            gui.refresh_realtime_fields(df=None, tdx_quotes=tdx_quotes)

            # 验证 item1 (000978) 的价格被更新为 11.20，涨幅为 12.00%，涨速为 🚀+2.5%
            val1 = items_store["item1"]["values"]
            self.assertEqual(val1[3], "12.00")
            self.assertEqual(val1[4], "11.20")
            self.assertIn("🚀+2.5%", val1[5])
            # 校验原有量化指标 dff2, dff3, rank 依然完好保留，没有被冲刷成空
            self.assertEqual(val1[7], "4.7")
            self.assertEqual(val1[8], "9.3")
            self.assertEqual(val1[9], "7")
            self.assertEqual(items_store["item1"]["tags"], ("up",))

            # 验证 item2 (600127) 的价格被更新为 12.80，涨幅为 -5.19%，且保留 favorite tag
            val2 = items_store["item2"]["values"]
            self.assertEqual(val2[3], "-5.19")
            self.assertEqual(val2[4], "12.80")
            self.assertEqual(val2[7], "-0.4")
            self.assertEqual(val2[8], "154.3")
            self.assertEqual(val2[9], "653")
            self.assertIn("favorite", items_store["item2"]["tags"])
            self.assertIn("down", items_store["item2"]["tags"])


if __name__ == "__main__":
    unittest.main()
