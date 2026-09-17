# -*- coding: utf-8 -*-
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webTools')))
from window_manager import core

class TestTdxWildcardMatching(unittest.TestCase):
    def test_semantic_sub_title_and_stock_code(self):
        # 1. 验证语义通配占位符
        self.assertTrue(core.is_tdx_semantic_sub_title('\u901a\u8fbe\u4fe1\u4ece\u5c5e\u6d6e\u7a97'))
        self.assertTrue(core.is_tdx_semantic_sub_title('[\u901a\u8fbe\u4fe1\u4ece\u5c5e\u6d6e\u7a97]'))
        self.assertTrue(core.is_tdx_semantic_sub_title('\u901a\u8fbe\u4fe1\u4e2a\u80a1\u6d6e\u7a97'))
        self.assertTrue(core.is_tdx_semantic_sub_title('TDX_SUB_WIN'))
        self.assertFalse(core.is_tdx_semantic_sub_title('\u4e1c\u65b9\u8d22\u5bcc\u7ecf\u5178\u7248'))
        self.assertFalse(core.is_tdx_semantic_sub_title('\u901a\u8fbe\u4fe1\u91d1\u878d\u7ec8\u7aef'))

        # 2. 验证个股代码标题格式
        self.assertTrue(core.is_stock_code_title('\u4e0a\u8bc1\u6307\u6570(999999)'))
        self.assertTrue(core.is_stock_code_title('\u6625\u5149\u96c6\u56e2(301531)'))
        self.assertTrue(core.is_stock_code_title('\u8d35\u5dde\u8305\u53f0\uff08600519\uff09'))
        self.assertFalse(core.is_stock_code_title('\u901a\u8fbe\u4fe1\u91d1\u878d\u7ec8\u7aefV7.65'))
        self.assertFalse(core.is_stock_code_title('\u4e1c\u65b9\u8d22\u5bcc'))

    def test_wildcard_pattern_compilation(self):
        pat = core.compile_wildcard_pattern('*(*)')
        self.assertTrue(bool(pat.match('\u4e0a\u8bc1\u6307\u6570(999999)')))
        self.assertTrue(bool(pat.match('\u6625\u5149\u96c6\u56e2(301531)')))
        self.assertTrue(bool(pat.match('\u6625\u5149\u96c6\u56e2\uff08301531\uff09')))
        self.assertFalse(bool(pat.match('\u901a\u8fbe\u4fe1\u91d1\u878d\u7ec8\u7aef')))

    def test_matches_window_title(self):
        # 1. 语义宏匹配个股
        self.assertTrue(core.matches_window_title('[\u901a\u8fbe\u4fe1\u4ece\u5c5e\u6d6e\u7a97]', '\u6625\u5149\u96c6\u56e2(301531)'))
        self.assertTrue(core.matches_window_title('\u901a\u8fbe\u4fe1\u4e2a\u80a1\u6d6e\u7a97', '\u4e0a\u8bc1\u6307\u6570(999999)'))

        # 2. 通配符匹配
        self.assertTrue(core.matches_window_title('*(*)', '\u6625\u5149\u96c6\u56e2(301531)'))
        self.assertTrue(core.matches_window_title('*(??????)', '\u6625\u5149\u96c6\u56e2(301531)'))

        # 3. 个股泛化匹配 (配置里是上证指数，实际开着春光集团)
        self.assertTrue(core.matches_window_title('\u4e0a\u8bc1\u6307\u6570(999999)', '\u6625\u5149\u96c6\u56e2(301531)'))

    @patch('window_manager.core.user32')
    @patch('window_manager.core.win32gui')
    @patch('window_manager.core.get_window_host_relation')
    def test_find_windows_by_title_safe_wildcard_and_fallback(self, mock_host_rel, mock_win32gui, mock_user32):
        mock_user32.IsWindowVisible.return_value = 1
        
        # 模拟当前桌面只开着 春光集团(301531)，宿主是通达信
        fake_hwnd = 88888
        fake_title = '\u6625\u5149\u96c6\u56e2(301531)'
        
        def fake_enum_windows(callback, extra):
            callback(fake_hwnd, None)
            return True

        mock_win32gui.EnumWindows.side_effect = fake_enum_windows
        mock_win32gui.GetWindowText.return_value = fake_title
        
        mock_host_rel.return_value = {
            'is_sub_window': True,
            'host_hwnd': 10001,
            'host_title': '\u901a\u8fbe\u4fe1\u91d1\u878d\u7ec8\u7aef',
            'class_name': '#32770',
            'is_dialog': True,
            'exe_path': 'D:\\\\new_tdx\\\\tdxw.exe'
        }

        # 场景 1：用户使用语义通配 '[通达信从属浮窗]'
        res1 = core.find_windows_by_title_safe('[\u901a\u8fbe\u4fe1\u4ece\u5c5e\u6d6e\u7a97]')
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0], (fake_hwnd, fake_title))

        # 场景 2：用户使用通配符 '*(*)'
        res2 = core.find_windows_by_title_safe('*(*)')
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0], (fake_hwnd, fake_title))

        # 场景 3：用户配置里写着旧股票 '上证指数(999999)'，智能兜底命中当前通达信浮窗 '春光集团(301531)'
        res3 = core.find_windows_by_title_safe('\u4e0a\u8bc1\u6307\u6570(999999)')
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0], (fake_hwnd, fake_title))

    @patch('window_manager.core.user32')
    @patch('window_manager.core.get_window_text_safe')
    @patch('window_manager.core.get_exe_path')
    def test_tdx_sub_screen_identified_as_independent_window(self, mock_get_exe, mock_get_text, mock_user32):
        """验证通达信多屏(副屏一、副屏二等)被正确识别为独立顶层大窗口，绝不误判为附属浮窗"""
        mock_user32.IsWindow.return_value = 1
        mock_user32.GetWindow.return_value = 10001  # 即使 Win32 底层被通达信挂载了 GW_OWNER
        mock_get_text.return_value = '\u901a\u8fbe\u4fe1\u91d1\u878d\u7ec8\u7aef(\u5f00\u5fc3\u679c\u4ea4\u6613\u7248) \u526f\u5c4f\u4e00(\u5206\u7ec42) - [\u5206\u6790\u56fe\u8868-\u521b\u4e1a\u677fETF\u6613\u65b9\u8fbe]'
        mock_get_exe.return_value = 'D:\\new_tdx\\tdxw.exe'

        rel = core.get_window_host_relation(77777)
        self.assertFalse(rel['is_sub_window'], '副屏一绝不应被判定为附属小浮窗')
        self.assertEqual(rel['host_hwnd'], 0)

if __name__ == '__main__':
    unittest.main()
