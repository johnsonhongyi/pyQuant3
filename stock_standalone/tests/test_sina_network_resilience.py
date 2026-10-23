# -*- coding: utf-8 -*-
"""
新浪行情抓取网络韧性、重试与日志脱敏专项测试
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch
import aiohttp
import pandas as pd
import pytest

from JohnsonUtil import commonTips as cct
from JSONData import sina_data
import singleAnalyseUtil as single


def test_format_clean_error_truncation():
    """验证超长 URL 股票代码的脱敏与截断"""
    # 模拟包含 50 只股票代码的超长 URL
    codes = [f"sz{i:06d}" for i in range(50)]
    long_url = "Connection timeout to host http://hq.sinajs.cn/?format=text&list=" + ",".join(codes)
    
    cleaned = cct.format_clean_error(long_url, max_codes=4)
    assert "total=50 stocks" in cleaned
    assert "sz000000,sz000001,sz000002,sz000003" in cleaned
    assert len(cleaned) < 280
    assert not codes[-1] in cleaned  # 后面的代码被压缩省略

    # 短 URL 或无 list 的错误信息不受影响
    short_msg = "Connection timeout to host http://hq.sinajs.cn/?format=text&list=sz000001,sh600000"
    assert cct.format_clean_error(short_msg) == short_msg

    # 空信息安全返回
    assert cct.format_clean_error("") == ""
    assert cct.format_clean_error(None) == ""


def test_get_stocks_by_range_retry_and_resilience():
    """验证分片内部重试自愈机制"""
    async def _test():
        client = sina_data.Sina(readonly=True)
        client.stock_list = ["sz000001,sz000002"]

        # 模拟第 1 次网络抖动抛异常，第 2 次成功返回
        session_mock = Mock()
        resp_mock = AsyncMock()
        resp_mock.text.return_value = 'var hq_str_sz000001="平安银行,10.0,10.0,10.1...";'
        
        call_count = 0
        class FakeContext:
            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise aiohttp.ServerTimeoutError("Connection timeout")
                return resp_mock
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        session_mock.get.side_effect = lambda *args, **kwargs: FakeContext()

        res = await client.get_stocks_by_range(0, session_mock, max_retries=1)
        assert call_count == 2
        assert "平安银行" in res

    asyncio.run(_test())


def test_fetch_all_stocks_partial_failure_collection():
    """验证多分片请求中单分片超时不掐死其他正常分片"""
    async def _test():
        client = sina_data.Sina(readonly=True)
        client.request_num = 2
        client.stock_list = ["chunk0_codes", "chunk1_codes"]

        # chunk 0 成功，chunk 1 抛出异常
        async def mock_get_range(index, session, max_retries=1):
            if index == 0:
                return 'var hq_str_sz000001="股票A,10.0...";'
            raise aiohttp.ServerTimeoutError("chunk 1 timeout")

        client.get_stocks_by_range = mock_get_range
        session_mock = Mock()

        await client._fetch_all_stocks(session_mock)
        # 验证成功的分片被保留，self.stock_data 包含 chunk 0
        assert len(client.stock_data) == 1
        assert "股票A" in client.stock_data[0]

    asyncio.run(_test())


def test_get_stock_data_retry_exhaustion_attrs_error():
    """验证 get_stock_data 全局重试用尽后返回带有 __error__ 的 DataFrame 且不抛异常"""
    client = sina_data.Sina(readonly=True)

    async def fail_fetch(session):
        raise aiohttp.ServerTimeoutError("Connection timeout to host http://hq.sinajs.cn/?format=text&list=sz000001,sz000002")

    client._fetch_all_stocks = fail_fetch
    df_result = client.get_stock_data(retry_count=2, pause=0.01)

    assert df_result.empty
    assert "__error__" in df_result.attrs
    err = df_result.attrs["__error__"]
    assert err["code"] == "SINA_NETWORK_TIMEOUT"
    assert "ServerTimeoutError" in err["exc_type"]
    assert "timeout" in err["exc_msg"].lower()


def test_sina_all_fallback_to_hdf_on_network_failure(monkeypatch):
    """验证 sina.all 网络全部失败时优雅降级使用本地 HDF5 缓存快照"""
    client = sina_data.Sina(readonly=True)
    client._snapshot_only = True
    client.agg_cache = SimpleNamespace(getkey=lambda k: None, setkey=Mock())
    
    # 模拟本地存在包含 999999 的有效 HDF5 历史缓存
    now_ts = pd.Timestamp.now()
    h5_cache = pd.DataFrame(
        {
            'close': [15.0, 3000.0],
            'llastp': [14.0, 2980.0],
            'ticktime': [now_ts, now_ts],
            'dt': [now_ts.strftime('%Y-%m-%d'), now_ts.strftime('%Y-%m-%d')]
        },
        index=['000001', '999999']
    )
    
    # 网络获取彻底失败返回带 __error__ 的空 DataFrame
    empty_with_err = pd.DataFrame()
    empty_with_err.attrs['__error__'] = {"code": "SINA_NETWORK_TIMEOUT"}
    
    monkeypatch.setattr(client, 'load_stock_codes', lambda codes: None)
    monkeypatch.setattr(sina_data, 'get_global_stock_code', lambda: SimpleNamespace(
        stock_code_path=None, get_stock_codes=lambda: ['000001', '999999']))
    monkeypatch.setattr(sina_data.h5a, 'load_hdf_db', Mock(return_value=h5_cache.copy()))
    monkeypatch.setattr(client, 'get_stock_data', Mock(return_value=empty_with_err))
    monkeypatch.setattr(client, 'combine_lastbuy', lambda df: df)
    monkeypatch.setattr(client, '_sanitize_indicators', lambda df: df)
    monkeypatch.setattr(sina_data.cct, 'get_work_time', lambda: True)
    monkeypatch.setattr(sina_data.cct, 'get_trade_date_status', lambda: True)
    monkeypatch.setattr(sina_data.cct, 'get_now_time_int', lambda: 1100)

    res = client.all
    # 优雅降级命中 h5_cache
    assert not res.empty
    assert res.loc['000001', 'close'] == 15.0
    assert res.loc['999999', 'close'] == 3000.0


def test_single_analyse_util_error_protection_and_counter_reset(monkeypatch):
    """验证 singleAnalyseUtil.py 调用 sina.all 异常受保且不崩溃"""
    monkeypatch.setattr(sina_data.Sina, 'all', property(lambda self: (_ for _ in ()).throw(
        aiohttp.ServerTimeoutError("Connection timeout to host http://hq.sinajs.cn/?format=text&list=sz000001")
    )))

    # get_hot_countNew 内部遇到 sina.all 抛出网络异常，应当被安全捕获并返回 empty DataFrame，绝不向外抛出
    res = single.get_hot_countNew(changepercent=1, rzrq={}, fibl=[], fibc=0)
    assert res.empty
