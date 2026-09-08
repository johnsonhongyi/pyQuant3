# -*- coding: utf-8 -*-
"""
tests/test_capital_dragon_panel_integration.py — CapitalDragonPanel 界面与数据全链路集成测试
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.ui.capital_dragon_panel import CapitalDragonPanel
from ats.capital_dragon_engine import CapitalDragonEngine


class TestCapitalDragonPanelIntegration(unittest.TestCase):

    def setUp(self):
        engine = CapitalDragonEngine.get_instance()
        with engine._cache_lock:
            engine._cached_report = {}
            engine._cached_time = 0.0
            engine._cached_df_len = 0
            engine._cached_df_first_code = ""
        self.panel = CapitalDragonPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_panel_initial_state(self):
        """测试初始状态与组件布局完整性"""
        self.assertEqual(len(self.panel.sector_card_widgets), 3)
        self.assertEqual(self.panel.table.columnCount(), len(self.panel.headers))
        self.assertIn("代码", self.panel.headers)
        self.assertIn("龙头角色", self.panel.headers)
        self.assertIn("虚拟量比", self.panel.headers)
        self.assertIn("成交额(亿)", self.panel.headers)

    def test_update_payload_and_rendering(self):
        """测试数据注入后 3 大主线卡片与真龙表格的渲染"""
        mock_data = {
            # 1. 空间龙
            "600108": {
                "name": "亚盛集团", "close": 3.85, "percent": 10.0, "amount": 9.5e8,
                "category": "农业种植;西部大开发", "dff": 2.5, "dff2": 6.8, "dff3": 12.0, "ma20d": 3.2
            },
            # 2. 趋势容量中军
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            # 3. 主线先锋
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            },
            # 4. 助攻
            "300037": {
                "name": "新宙邦", "close": 38.2, "percent": 5.6, "amount": 7.2e8,
                "category": "固态电池;氟化工", "dff": 0.8, "dff2": 3.2, "dff3": 6.0, "ma20d": 35.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')

        # 触发面板更新
        self.panel.update_payload(df_mock, sh_pct=0.8)

        # 验证表格行数大于 0
        self.assertGreater(self.panel.table.rowCount(), 0)

        # 验证顶部第 1 个卡片被正确渲染
        card0 = self.panel.sector_card_widgets[0]
        self.assertFalse(card0["frame"].isHidden())
        self.assertIn("固态电池", card0["title"].text())

        # 验证表格第一列包含识别出的真龙代码
        table_codes = [self.panel.table.item(r, 0).text() for r in range(self.panel.table.rowCount())]
        self.assertIn("300750", table_codes)
        self.assertIn("002812", table_codes)

        # 验证虚拟量比列（第 6 列）
        vr_col_idx = self.panel.headers.index("虚拟量比")
        self.assertEqual(vr_col_idx, 6)
        vr_item = self.panel.table.item(0, vr_col_idx)
        self.assertIsNotNone(vr_item)
        self.assertTrue(vr_item.text().endswith("x"))

        # 验证卡片描述中显示量比
        self.assertIn("量比:", card0["desc"].text())

        # 验证搜索框即时过滤
        self.panel.search_input.setText("宁德")
        filtered_rows = self.panel.table.rowCount()
        self.assertEqual(filtered_rows, 1)
        self.assertEqual(self.panel.table.item(0, 1).text(), "宁德时代")

        # 还原搜索
        self.panel.search_input.setText("")
        self.assertGreater(self.panel.table.rowCount(), 1)

    def test_card_click_and_pioneer_linkage(self):
        """测试点击板块卡片打开板块明细，以及点击领涨先锋触发联动"""
        mock_data = {
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            },
            "300037": {
                "name": "新宙邦", "close": 38.2, "percent": 5.6, "amount": 7.2e8,
                "category": "固态电池;氟化工", "dff": 0.8, "dff2": 3.2, "dff3": 6.0, "ma20d": 35.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, sh_pct=0.8)

        # 1. 模拟主窗口记录打开板块回调
        opened_sectors = []
        linked_stocks = []
        double_clicked_stocks = []

        class MockMainWindow:
            def on_sector_clicked(self, sec_name, member_codes=None):
                opened_sectors.append((sec_name, member_codes))
            def link_stock(self, code, name):
                linked_stocks.append((code, name))
            def on_stock_clicked(self, code, name, extra):
                double_clicked_stocks.append((code, name))

        mock_mw = MockMainWindow()
        self.panel.main_window = mock_mw

        card0 = self.panel.sector_card_widgets[0]["card_widget"]
        self.assertIsNotNone(card0)
        self.assertEqual(card0.sector_name, "固态电池")

        # 2. 模拟卡片点击 -> 触发打开板块详情
        card0._on_card_clicked()
        self.assertEqual(len(opened_sectors), 1)
        self.assertEqual(opened_sectors[0][0], "固态电池")
        # 验证从 df_mock 自动提取并透传了属于固态电池的成分股代码
        self.assertIn("300750", opened_sectors[0][1])
        self.assertIn("002812", opened_sectors[0][1])

        # 3. 模拟先锋单击 -> 触发个股联动
        card0._on_leader_clicked()
        self.assertEqual(len(linked_stocks), 1)
        self.assertEqual(linked_stocks[0][0], card0.leader_code)

        # 4. 模拟先锋双击 -> 触发打开 SBC
        card0._on_leader_double_clicked()
        self.assertEqual(len(double_clicked_stocks), 1)
        self.assertEqual(double_clicked_stocks[0][0], card0.leader_code)

    def test_sector_detail_dialog_strong_stocks_marking_and_filter(self):
        """测试板块明细弹窗标记强势股与【仅看强势股】按钮筛选"""
        from ats.ui.sector_detail_dialog import ATSSectorDetailDialog

        sample_rows = [
            {"code": "300750", "name": "宁德时代", "score": 98.0, "type": "🛡️ 趋势容量中军", "pct": 5.2, "dff": 1.8, "is_strong": True},
            {"code": "002812", "name": "恩捷股份", "score": 96.0, "type": "🔥 强势涨停", "pct": 9.98, "dff": 1.2, "is_strong": True},
            {"code": "000001", "name": "平安银行", "score": 30.0, "type": "跟随", "pct": -0.5, "dff": -0.2, "is_strong": False}
        ]

        dlg = ATSSectorDetailDialog("固态电池", member_codes=["300750", "002812", "000001"])
        dlg._on_worker_finished(sample_rows, 85.0, "恩捷股份 (002812) [+9.98%]", {"count": 3, "strong_count": 2})

        # 验证默认展示 3 只
        self.assertEqual(dlg.table.rowCount(), 3)
        # 验证宁德时代与恩捷股份被标记为强势股并排在前面
        item_top0 = dlg.table.item(0, 1)
        self.assertTrue(item_top0.font().bold())

        # 开启【仅看强势股】
        dlg.btn_strong_only.setChecked(True)
        dlg._toggle_strong_only()

        # 验证过滤后仅剩 2 只强势股
        self.assertEqual(dlg.table.rowCount(), 2)
        codes = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
        self.assertIn("300750", codes)
        self.assertIn("002812", codes)
        self.assertNotIn("000001", codes)

        dlg.deleteLater()

    def test_extreme_perf_toggle(self):
        """测试【⚡ 极限性能模式】按钮状态切换与标的展示截断"""
        # 初始默认开启
        self.assertTrue(self.panel.extreme_perf_mode)
        self.assertIn("开", self.panel.btn_extreme_perf.text())

        # 验证工具栏不再包含取消的 3 个冗余快捷按钮 (界面整洁不截断)
        self.assertFalse(hasattr(self.panel, "btn_limit_up"))
        self.assertFalse(hasattr(self.panel, "btn_hot_sector"))
        self.assertFalse(hasattr(self.panel, "btn_dragon_mon"))

        # 点击切换为关闭 (全量模式)
        self.panel.btn_extreme_perf.click()
        self.assertFalse(self.panel.extreme_perf_mode)
        self.assertIn("关", self.panel.btn_extreme_perf.text())

        # 再次点击切换为开启
        self.panel.btn_extreme_perf.click()
        self.assertTrue(self.panel.extreme_perf_mode)
        self.assertIn("开", self.panel.btn_extreme_perf.text())

    def test_acceleration_buy_type_rendering_and_card_stats(self):
        """测试分时加速形态（双加速、缺口加速、光脚加速）在买点类型列中的精细化视觉色彩与卡片加速汇聚"""
        mock_data = {
            # 双加速（缺口 + 光脚）
            "600519": {
                "name": "贵州茅台", "close": 1750.0, "open": 1720.0, "low": 1720.0, "lasth1d": 1700.0, "lastp": 1700.0,
                "percent": 3.5, "amount": 6.8e9, "category": "白酒;大消费", "dff": 2.5, "dff2": 6.8, "dff3": 12.0, "ma20d": 1650.0
            },
            # 缺口加速（有跳空缺口，但有小下影）
            "000858": {
                "name": "五粮液", "close": 150.0, "open": 146.0, "low": 144.5, "lasth1d": 142.0, "lastp": 142.0,
                "percent": 5.6, "amount": 3.2e9, "category": "白酒;大消费", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 138.0
            },
            # 光脚加速（无跳空缺口，但平开/微低开后光脚单边拉升）
            "002304": {
                "name": "洋河股份", "close": 98.0, "open": 94.0, "low": 94.0, "lasth1d": 95.0, "lastp": 94.5,
                "percent": 4.2, "amount": 1.5e9, "category": "白酒;大消费", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 90.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, sh_pct=1.0)

        # 1. 验证顶部白酒主线卡片呈现了加速统计
        card0 = self.panel.sector_card_widgets[0]
        self.assertIn("加速:", card0["desc"].text())

        # 2. 验证表格行数与买点类型列（索引 9）渲染
        buy_col_idx = self.panel.headers.index("资金买点类型")
        self.assertEqual(buy_col_idx, 9)

        table_codes = [self.panel.table.item(r, 0).text() for r in range(self.panel.table.rowCount())]
        self.assertIn("600519", table_codes)

        # 查找茅台的买点类型 item
        from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
        idx_mt = table_codes.index("600519")
        item_mt_buy = self.panel.table.item(idx_mt, buy_col_idx)
        self.assertIsNotNone(item_mt_buy)
        # 验证买点类型单元格已升级为 NumericTableWidgetItem (支持高精度量化排序)
        self.assertIsInstance(item_mt_buy, NumericTableWidgetItem)
        # 应该包含双加速
        self.assertIn("双加速", item_mt_buy.text())
        # 验证双加速排序分 >= 90000 分
        self.assertGreaterEqual(float(item_mt_buy.raw_val), 90000.0)
        # 字体加粗
        self.assertTrue(item_mt_buy.font().bold())
        # 颜色匹配 #FFD700
        color_hex = item_mt_buy.foreground().color().name().upper()
        self.assertEqual(color_hex, "#FFD700")

        # 验证买点类型优先级: 茅台(双加速) > 五粮液(缺口加速) > 洋河(光脚加速)
        if "000858" in table_codes and "002304" in table_codes:
            idx_wly = table_codes.index("000858")
            idx_yh = table_codes.index("002304")
            item_wly_buy = self.panel.table.item(idx_wly, buy_col_idx)
            item_yh_buy = self.panel.table.item(idx_yh, buy_col_idx)
            self.assertGreater(float(item_mt_buy.raw_val), float(item_wly_buy.raw_val))
            self.assertGreater(float(item_wly_buy.raw_val), float(item_yh_buy.raw_val))

        # 3. 验证状态栏包含加速汇总统计，且删除极限性能标签以防状态栏遮挡 (状态保留在按钮中)
        stats_text = self.panel.lbl_stats.text()
        self.assertIn("⚡加速:", stats_text)
        self.assertNotIn("极限性能", stats_text)
        self.assertIn("⚡ 极限性能: 开", self.panel.btn_extreme_perf.text())

    def test_sector_cards_auto_wrap_and_pioneer_vr_buy_type(self):
        """测试顶部核心主线卡片自适应换行、自由变形缩放能力，以及先锋行呈现虚拟量比与买点类型"""
        # 1. 验证卡片尺寸策略与自动折行属性 (彻底解除对 ATS 主窗口宽度的绑架)
        card_w0 = self.panel.sector_card_widgets[0]["card_widget"]
        self.assertTrue(card_w0.lbl_title.wordWrap())
        self.assertTrue(card_w0.lbl_desc.wordWrap())
        self.assertTrue(card_w0.lbl_leader.wordWrap())

        # 验证最小尺寸宽度不会阻碍父窗口缩小
        self.assertEqual(card_w0.minimumWidth(), 0)
        self.assertLessEqual(card_w0.minimumSizeHint().width(), 100)
        self.assertEqual(self.panel.top_sector_container.minimumWidth(), 0)

        # 2. 模拟数据注入并验证先锋行包含虚拟量比与买点类型
        mock_data = {
            "600519": {
                "name": "贵州茅台", "close": 1750.0, "open": 1720.0, "low": 1720.0, "lasth1d": 1700.0, "lastp": 1700.0,
                "percent": 6.8, "amount": 6.8e9, "vol_ratio": 2.5, "category": "白酒;大消费", "dff": 2.5, "dff2": 6.8, "dff3": 12.0, "ma20d": 1650.0
            },
            "000858": {
                "name": "五粮液", "close": 150.0, "open": 146.0, "low": 144.5, "lasth1d": 142.0, "lastp": 142.0,
                "percent": 3.2, "amount": 3.2e9, "vol_ratio": 1.5, "category": "白酒;大消费", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 138.0
            },
            "002304": {
                "name": "洋河股份", "close": 98.0, "open": 94.0, "low": 94.0, "lasth1d": 95.0, "lastp": 94.5,
                "percent": 2.1, "amount": 1.5e9, "vol_ratio": 1.2, "category": "白酒;大消费", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 90.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, sh_pct=1.0)

        card0 = self.panel.sector_card_widgets[0]
        leader_text = card0["leader"].text()
        
        # 验证先锋行显性包含：先锋名字、代码、涨幅、量比、买点形态
        self.assertIn("贵州茅台", leader_text)
        self.assertIn("600519", leader_text)
        self.assertIn("+6.8%", leader_text)
        self.assertIn("量比:", leader_text)
        self.assertIn("2.5x", leader_text)
        # 验证包含双加速或领涨买点
        self.assertTrue("👑双加速" in leader_text or "领涨" in leader_text or "先锋" in leader_text)

        # 验证悬浮提示 ToolTip
        leader_tip = card0["leader"].toolTip()
        self.assertIn("先锋虚拟量比:", leader_tip)
        self.assertIn("先锋买点形态:", leader_tip)

    def test_capital_dragon_panel_custom_columns_rendering(self):
        """测试资金主线表格动态自定义列 (ats_col) 呈现与买点类型后置顺序"""
        headers = self.panel.headers
        self.assertIn("资金买点类型", headers)
        self.assertIn("CH_BC2", headers)
        
        buy_col = headers.index("资金买点类型")
        bc2_col = headers.index("CH_BC2")
        self.assertEqual(bc2_col, buy_col + 1)
        self.assertEqual(headers.index("建议买入区间"), bc2_col + 1)

        # 注入带 ch_bc2 的数据
        mock_data = {
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0,
                "ch_bc2": 3.0
            },
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0,
                "ch_bc2": 0.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, sh_pct=1.0)

        self.assertGreater(self.panel.table.rowCount(), 0)
        
        # 查找宁德时代所在行
        target_row = -1
        for r in range(self.panel.table.rowCount()):
            if self.panel.table.item(r, 0).text() == "300750":
                target_row = r
                break
        self.assertGreaterEqual(target_row, 0)

        # 验证资金买点类型列内容
        item_buy = self.panel.table.item(target_row, buy_col)
        self.assertIsNotNone(item_buy)
        self.assertTrue(len(item_buy.text().strip()) > 0)

        # 验证自定义列 CH_BC2 内容与类型 (co2int 转换为 '3')
        item_bc2 = self.panel.table.item(target_row, bc2_col)
        self.assertIsNotNone(item_bc2)
        self.assertEqual(item_bc2.text().strip(), "3")
        self.assertEqual(getattr(item_bc2, "_raw_value", None), 3.0)

        # 验证后续列偏移正常
        item_zone = self.panel.table.item(target_row, bc2_col + 1)
        self.assertIsNotNone(item_zone)
        self.assertIn("~", item_zone.text())

        # 验证搜索框过滤自定义列内容
        self.panel.search_input.setText("3")
        self.assertGreaterEqual(self.panel.table.rowCount(), 1)
        self.panel.search_input.setText("")

    def test_no_false_linkage_or_flicker_during_update(self):
        """验证后台刷新时不会误发射 stock_selected 切股联动信号，且卡片稳定占位不坍塌"""
        mock_data = {
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, force=True)

        # 模拟用户正常选中第一行
        self.panel.table.setCurrentCell(0, 0)
        selected_code_before = self.panel.table.item(0, 0).text()

        # 监听 stock_selected 发射情况
        emitted_signals = []
        self.panel.stock_selected.connect(lambda c, n: emitted_signals.append((c, n)))

        # 模拟后台刷新到来 (价格变动触发重新渲染)
        mock_data_2 = {
            "300750": {
                "name": "宁德时代", "close": 266.0, "percent": 5.6, "amount": 5.0e9,
                "category": "固态电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            "002812": {
                "name": "恩捷股份", "close": 42.6, "percent": 10.0, "amount": 1.6e9,
                "category": "固态电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            }
        }
        df_mock_2 = pd.DataFrame.from_dict(mock_data_2, orient='index')
        self.panel.update_payload(df_mock_2, force=True)

        # 1. 核心断言：后台刷新期间绝对严禁触发 stock_selected (杜绝抢焦与外部终端切股闪烁)
        self.assertEqual(len(emitted_signals), 0, f"后台数据更新期间误发射了联动信号: {emitted_signals}")

        # 2. 核心断言：之前选中的代码在更新后平滑恢复
        curr_row = self.panel.table.currentRow()
        self.assertGreaterEqual(curr_row, 0)
        self.assertEqual(self.panel.table.item(curr_row, 0).text(), selected_code_before)

        # 3. 核心断言：即使当前只有 1 个板块，所有 3 个卡片依然保持占位 (not isHidden)，绝不坍塌
        for card_info in self.panel.sector_card_widgets:
            self.assertFalse(card_info["frame"].isHidden())


if __name__ == "__main__":
    unittest.main()


