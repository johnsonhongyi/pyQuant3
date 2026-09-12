# -*- coding: utf-8 -*-
import re
import unittest

def parse_clipboard_concept_tk(clipboard_text: str) -> str:
    """提取与格式化测试函数（与 instock_MonitorTK.py 中的 on_right_click_search_var2 核心逻辑完全一致）"""
    text = clipboard_text.strip() if clipboard_text else ""
    if not text:
        return ""

    # 1. 完整 Query 表达式或包含运算符/contains，原样保留
    query_ops = ['.str.contains', 'category.', 'index.', '>', '<', '==', '!=', '>=', '<=', ' and ', ' or ', ' & ', ' | ']
    if any(op in text for op in query_ops):
        return text
    # 2. 6位纯数字股票代码
    elif text.isdigit() and len(text) == 6:
        return f'index.str.contains("^{text}")'
    else:
        # 3. 板块/概念词提取
        cleaned = re.sub(r'^[【\["“\'`\s]+|[】\]"”\'`\s]+$', '', text)
        cleaned = re.sub(r'^(?:所属)?(?:概念|板块|行业)[:：\s]+', '', cleaned).strip()
        matches = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9\-\(\)（）/]+', cleaned)
        if matches:
            return f'category.str.contains("{matches[0]}")'
        else:
            return text


def parse_clipboard_concept_qt(text: str) -> str:
    """提取与格式化测试函数（与 trade_visualizer_qt6.py 中的 _on_cat_filter_right_click 核心逻辑完全一致）"""
    text = text.strip() if text else ""
    if not text:
        return ""

    query_ops = ['.str.contains', 'category.', 'index.', '>', '<', '==', '!=', '>=', '<=', ' and ', ' or ', ' & ', ' | ']
    if any(op in text for op in query_ops):
        return text
    elif text.isdigit() and len(text) == 6:
        return f'index.str.contains("^{text}")'
    else:
        cleaned = re.sub(r'^[【\["“\'`\s]+|[】\]"”\'`\s]+$', '', text)
        cleaned = re.sub(r'^(?:所属)?(?:概念|板块|行业)[:：\s]+', '', cleaned).strip()
        matches = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9\-\(\)（）/]+', cleaned)
        if matches:
            return f'category.str.contains("{matches[0]}", case=False, regex=False)'
        else:
            return text


class TestRightClickSearchPaste(unittest.TestCase):
    def test_tk_6g_concept_prefix(self):
        """测试 6G概念 不会丢掉 6G 前缀"""
        res = parse_clipboard_concept_tk("6G概念")
        self.assertEqual(res, 'category.str.contains("6G概念")')

    def test_tk_alphanumeric_concepts(self):
        """测试数字/英文开头的各种概念"""
        self.assertEqual(parse_clipboard_concept_tk("5G"), 'category.str.contains("5G")')
        self.assertEqual(parse_clipboard_concept_tk("6G"), 'category.str.contains("6G")')
        self.assertEqual(parse_clipboard_concept_tk("CPO概念"), 'category.str.contains("CPO概念")')
        self.assertEqual(parse_clipboard_concept_tk("AI手机"), 'category.str.contains("AI手机")')
        self.assertEqual(parse_clipboard_concept_tk("MR概念"), 'category.str.contains("MR概念")')
        self.assertEqual(parse_clipboard_concept_tk("DRG/DIP"), 'category.str.contains("DRG/DIP")')

    def test_tk_chinese_and_parentheses(self):
        """测试纯汉字及带括号概念"""
        self.assertEqual(parse_clipboard_concept_tk("固态电池"), 'category.str.contains("固态电池")')
        self.assertEqual(parse_clipboard_concept_tk("机器人概念"), 'category.str.contains("机器人概念")')
        self.assertEqual(parse_clipboard_concept_tk("光刻机(胶)"), 'category.str.contains("光刻机(胶)")')
        self.assertEqual(parse_clipboard_concept_tk("共封装光学(CPO)"), 'category.str.contains("共封装光学(CPO)")')

    def test_tk_stock_code_and_query_passthrough(self):
        """测试 6 位股票代码与已有 query 表达式直通"""
        self.assertEqual(parse_clipboard_concept_tk("002297"), 'index.str.contains("^002297")')
        self.assertEqual(parse_clipboard_concept_tk("600391"), 'index.str.contains("^600391")')
        self.assertEqual(parse_clipboard_concept_tk('category.str.contains("6G概念")'), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk('close > ma5 and category.str.contains("5G")'), 'close > ma5 and category.str.contains("5G")')

    def test_tk_wrapped_and_prefixed_texts(self):
        """测试带外层包裹或前缀文本提取"""
        self.assertEqual(parse_clipboard_concept_tk("  6G概念\r\n"), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk("【6G概念】"), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk("“6G概念”"), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk("概念: 6G概念"), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk("所属概念: 6G概念"), 'category.str.contains("6G概念")')
        self.assertEqual(parse_clipboard_concept_tk("6G概念 880980"), 'category.str.contains("6G概念")')

    def test_qt_visualizer_paste(self):
        """测试 Qt 可视化端粘贴"""
        self.assertEqual(parse_clipboard_concept_qt("6G概念"), 'category.str.contains("6G概念", case=False, regex=False)')
        self.assertEqual(parse_clipboard_concept_qt("5G"), 'category.str.contains("5G", case=False, regex=False)')
        self.assertEqual(parse_clipboard_concept_qt("002297"), 'index.str.contains("^002297")')


if __name__ == '__main__':
    unittest.main()
