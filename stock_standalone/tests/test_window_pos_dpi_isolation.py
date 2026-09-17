# -*- coding: utf-8 -*-
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'webTools')))
from window_manager import core

class TestWindowPosDpiIsolation(unittest.TestCase):
    @patch('window_manager.core.user32')
    @patch('window_manager.core.get_window_host_relation')
    @patch('window_manager.core.get_window_rect')
    @patch('window_manager.core.cancel_window_maximized_or_fullscreen')
    def test_dfcf_main_window_no_dpi_context_switch(self, mock_cancel, mock_get_rect, mock_host_rel, mock_user32):
        mock_host_rel.return_value = {
            'is_sub_window': False,
            'host_hwnd': 0,
            'host_title': '',
            'class_name': 'EastmoneyMainFrame',
            'is_dialog': False,
            'exe_path': 'C:\\Eastmoney\\em.exe'
        }
        mock_get_rect.return_value = (100, 100, 1280, 800)
        mock_user32.IsZoomed.return_value = 0
        mock_user32.SetWindowPos.return_value = 1
        mock_user32.GetWindowDpiAwarenessContext = MagicMock()
        mock_user32.SetThreadDpiAwarenessContext = MagicMock()

        success = core.set_window_hwnd_pos(12345, '100,100,1280,800', title='东方财富经典版')
        self.assertTrue(success)
        mock_user32.GetWindowDpiAwarenessContext.assert_not_called()
        mock_user32.SetThreadDpiAwarenessContext.assert_not_called()
        mock_user32.PostMessageW.assert_any_call(12345, 0x0232, 0, 0)

    @patch('window_manager.core.user32')
    @patch('window_manager.core.get_window_host_relation')
    @patch('window_manager.core.get_window_rect')
    def test_tdx_sub_window_enables_dpi_context_switch(self, mock_get_rect, mock_host_rel, mock_user32):
        mock_host_rel.return_value = {
            'is_sub_window': True,
            'host_hwnd': 99999,
            'host_title': '通达信金融终端',
            'class_name': '#32770',
            'is_dialog': True,
            'exe_path': 'D:\\new_tdx\\tdxw.exe'
        }
        mock_get_rect.return_value = (500, 500, 400, 300)
        mock_user32.IsIconic.return_value = 0
        mock_user32.IsZoomed.return_value = 0
        mock_user32.SetWindowPos.return_value = 1
        mock_user32.GetWindowDpiAwarenessContext = MagicMock(return_value=999)
        mock_user32.SetThreadDpiAwarenessContext = MagicMock(return_value=888)

        success = core.set_window_hwnd_pos(67890, '500,500,400,300', title='上证指数(999999)')
        self.assertTrue(success)
        mock_user32.GetWindowDpiAwarenessContext.assert_called_once_with(67890)
        self.assertGreaterEqual(mock_user32.SetThreadDpiAwarenessContext.call_count, 2)
        mock_user32.SetThreadDpiAwarenessContext.assert_any_call(999)
        mock_user32.SetThreadDpiAwarenessContext.assert_any_call(888)

if __name__ == '__main__':
    unittest.main()
