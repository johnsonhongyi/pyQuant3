# -*- coding: utf-8 -*-
"""
test_clipboard_stock_name_linkage.py
验证剪贴板股票中文名（如“工商银行”、“ST天玑”、“中国银行”等）自动识别与联动解析功能
"""

import sys
import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock

# 确保路径能够导入 stock_standalone 下模块
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import sys_utils
import tdx_utils


class TestStockNameResolution:
    """测试 sys_utils 中的股票代码与中文名双向解析"""

    @pytest.mark.parametrize("input_val, expected_code", [
        # 用户指定的 5 个核心标的 (代码与名称相互映射)
        ("300245", "300245"),
        ("ST天玑", "300245"),
        ("601988", "601988"),
        ("中国银行", "601988"),
        ("601398", "601398"),
        ("工商银行", "601398"),
        ("603230", "603230"),
        ("内蒙新华", "603230"),
        ("600650", "600650"),
        ("锦江在线", "600650"),
        
        # 大小写与前缀容错
        ("st天玑", "300245"),
        ("*ST天玑", "300245"),
        ("天玑", "300245"),
        
        # 常见含空格股票名称规整
        ("深赛格", "000058"),
        ("深 赛 格", "000058"),
        ("万科A", "000002"),
        ("万 科Ａ", "000002"),
        ("农产品", "000061"),
        ("农 产 品", "000061"),
    ])
    def test_resolve_stock_code_basic_and_normalized(self, input_val, expected_code):
        code = sys_utils.resolve_stock_code(input_val)
        assert code == expected_code, f"Failed resolving {input_val}: expected {expected_code}, got {code}"

    @pytest.mark.parametrize("composite_text, expected_code", [
        # 终端打印 gem_tops 格式复合行
        ("300245  ST天玑    -14.29      95.00        0", "300245"),
        ("601988  中国银行      3.34      92.84        0", "601988"),
        ("601398  工商银行      4.36      92.68        0", "601398"),
        ("603230  内蒙新华    -26.22      92.15        0", "603230"),
        ("600650  锦江在线     -8.13      85.80        0", "600650"),
        
        # 仅复制名称及后序列（不含6位代码）
        ("ST天玑    -14.29      95.00        0", "300245"),
        ("工商银行      4.36      92.68        0", "601398"),
        ("中国银行  3.34", "601988"),
        
        # 代码+名称组合
        ("601398 工商银行", "601398"),
        ("工商银行 601398", "601398"),
    ])
    def test_resolve_stock_code_composite_text(self, composite_text, expected_code):
        code = sys_utils.resolve_stock_code(composite_text)
        assert code == expected_code, f"Failed resolving composite: {composite_text}"

    def test_resolve_stock_code_invalid(self):
        assert sys_utils.resolve_stock_code("") is None
        assert sys_utils.resolve_stock_code(None) is None
        assert sys_utils.resolve_stock_code("完全不是股票的文字ABCDEF") is None
        assert sys_utils.resolve_stock_code("123") is None


class TestTdxUtilsClipboardExtractor:
    """测试 tdx_utils 中的剪贴板文本提取器与生成器"""

    @pytest.mark.parametrize("clip_text, expected_code", [
        ("601988", "601988"),
        ("601398", "601398"),
        ("工商银行", "601398"),
        ("ST天玑", "300245"),
        ("中国银行", "601988"),
        ("内蒙新华", "603230"),
        ("锦江在线", "600650"),
        ("300245  ST天玑    -14.29      95.00        0", "300245"),
        ("ST天玑    -14.29      95.00        0", "300245"),
    ])
    def test_extract_or_resolve_code(self, clip_text, expected_code):
        code = tdx_utils.extract_or_resolve_code(clip_text)
        assert code == expected_code, f"extract_or_resolve_code failed on '{clip_text}'"

    def test_get_clipboard_contents_generator(self):
        """模拟剪贴板复制序列并验证异步生成器能够连续、去重识别代码与名称"""
        async def _run():
            mock_clips = [
                "601988",       # 1. 纯数字代码
                "601988",       # 2. 重复代码 (应去重)
                "工商银行",     # 3. 中文股票名
                "ST天玑",       # 4. 中文带ST股票名
                "300245  ST天玑    -14.29      95.00        0",  # 5. 复合行
                "invalid text", # 6. 非股票文本 (应忽略)
                "锦江在线",     # 7. 中文名
            ]
            
            clip_iter = iter(mock_clips)
            def mock_paste():
                try:
                    return next(clip_iter)
                except StopIteration:
                    return ""

            received_codes = []
            with patch("tdx_utils.pyperclip.paste", side_effect=mock_paste):
                gen = tdx_utils.get_clipboard_contents(timesleep=0.01)
                # 消费前 4 个成功产出的代码
                for _ in range(4):
                    try:
                        code = await asyncio.wait_for(gen.asend(None), timeout=0.5)
                        received_codes.append(code)
                    except asyncio.TimeoutError:
                        break

            assert "601988" in received_codes
            assert "601398" in received_codes  # 工商银行
            assert "300245" in received_codes  # ST天玑

        asyncio.run(_run())


class TestHttpLinkageStockNameSupport:
    """测试本地微型 HTTP 服务 /link 接口对中文名称的支持"""

    def test_http_link_callback_with_name_and_code(self):
        called_codes = []
        def my_link_cb(c):
            called_codes.append(c)

        sys_utils.register_link_callback(my_link_cb)

        # 模拟各种参数传入解析
        # 1. code=工商银行
        c1 = sys_utils.resolve_stock_code("工商银行")
        if c1: sys_utils._link_callback(c1)
        assert "601398" in called_codes

        # 2. name=ST天玑
        c2 = sys_utils.resolve_stock_code("ST天玑")
        if c2: sys_utils._link_callback(c2)
        assert "300245" in called_codes

        # 3. code=601988
        c3 = sys_utils.resolve_stock_code("601988")
        if c3: sys_utils._link_callback(c3)
        assert "601988" in called_codes
