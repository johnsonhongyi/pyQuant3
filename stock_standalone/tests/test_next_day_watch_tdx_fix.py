# -*- coding: utf-8 -*-
"""
NextDayWatch与TDX连接池假死自愈及真行情节点保障测试
"""
import pytest
from unittest.mock import MagicMock, patch
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher, FALLBACK_TDX_HOSTS


def test_fallback_tdx_hosts_validity():
    """测试 1: 兜底黄金主站池仅保留实测可用真主站，坚决剔除假活无盘口节点"""
    assert len(FALLBACK_TDX_HOSTS) >= 1
    # 验证江苏主站置顶且端口正确
    assert FALLBACK_TDX_HOSTS[0][0] == "通达信江苏主站"
    assert FALLBACK_TDX_HOSTS[0][1] == "223.112.100.140"
    assert FALLBACK_TDX_HOSTS[0][2] == 7709
    # 验证西安假活节点集群已全数剔除
    for name, ip, port in FALLBACK_TDX_HOSTS:
        assert not ip.startswith("117.34.114."), f"Found dormant xi'an host: {name} ({ip})"


def test_probe_host_alive_trading_vs_off_hours():
    """测试 2: 盘中严禁将无盘口假活节点判定为存活"""
    fetcher = TDXRealtimeFetcher.get_instance()
    mock_api = MagicMock()
    # 模拟返回空盘口，但证券总数返回 24612 (典型西安假死节点行为)
    mock_api.get_security_quotes.return_value = []
    mock_api.get_security_count.return_value = 24612

    # 1. 盘中交易时段：必须严格判定为假死 (False)
    with patch("ats.tdx_realtime_fetcher.is_tdx_trading_allowed", return_value=(True, "交易中", {})):
        assert fetcher._probe_host_alive(mock_api) is False

    # 2. 非交易时段/夜间清算：允许降级兼容 (True)
    with patch("ats.tdx_realtime_fetcher.is_tdx_trading_allowed", return_value=(False, "休市中", {})):
        assert fetcher._probe_host_alive(mock_api) is True


def test_ping_single_host_rejects_fake_alive_in_trading():
    """测试 3: 盘中测速坚决拒绝无盘口节点"""
    fetcher = TDXRealtimeFetcher.get_instance()
    with patch("ats.tdx_realtime_fetcher.TdxHq_API") as MockAPI:
        api_inst = MagicMock()
        api_inst.connect.return_value = True
        api_inst.get_security_quotes.return_value = []
        api_inst.get_security_count.return_value = 24612
        MockAPI.return_value = api_inst

        # 盘中测速应该直接返回 None，杜绝将假死节点纳入活跃池
        with patch("ats.tdx_realtime_fetcher.is_tdx_trading_allowed", return_value=(True, "交易中", {})):
            res = fetcher._ping_single_host(("假死主站", "1.2.3.4", 7709))
            assert res is None


def test_dead_host_does_not_binary_partition_kill_codes():
    """测试 4: 主站假死时直接终止，严禁启动二分拆包误杀全部 185 正常股票"""
    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher._is_connected = True
    fetcher.api = MagicMock()
    fetcher.api.get_security_quotes.return_value = []
    fetcher._unlisted_or_dormant_codes.clear()

    # 模拟探针判定假死且 failover 未果
    with patch("ats.tdx_realtime_fetcher.is_tdx_trading_allowed", return_value=(True, "交易中", {})):
        with patch.object(fetcher, "_probe_host_alive", return_value=False):
            with patch.object(fetcher, "auto_failover", return_value=False):
                fetcher._consecutive_empty_batches = 2
                res = fetcher.get_security_quotes_safe(["000001", "600519", "002307"])
                assert res == []
                # 关键断言：绝对没有启动二分隔离把这 3 只正常代码加入 dormant 黑名单！
                assert "000001" not in fetcher._unlisted_or_dormant_codes
                assert "600519" not in fetcher._unlisted_or_dormant_codes
                assert "002307" not in fetcher._unlisted_or_dormant_codes


def test_mark_host_dead_cooldown():
    """测试 5: 假死节点被记录进黑名单并在冷静期内自动过滤"""
    fetcher = TDXRealtimeFetcher.get_instance()
    from ats.tdx_realtime_fetcher import get_all_tdx_hosts
    bad_ip, bad_port = "223.112.100.140", 7709
    fetcher.mark_host_dead(bad_ip, bad_port, duration=300.0)

    # 验证在冷静期内 get_all_tdx_hosts(exclude_cooldown=True) 自动过滤该节点
    hosts = get_all_tdx_hosts(exclude_cooldown=True)
    assert not any(h[1] == bad_ip and h[2] == bad_port for h in hosts)

    # 恢复该节点
    fetcher._dead_hosts_cooldown.pop((bad_ip, bad_port), None)


def test_deep_scan_auto_recovery_when_fallback_fails():
    """测试 6: 当黄金主力主站全部异常时，系统自动激活全网扩围深搜并成功捕获有效主站"""
    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher.active_hosts_pool.clear()

    # 模拟 _ping_single_host: 对黄金主站返回 None (假死/异常)，对扩围池中的新节点返回有效结果
    def mock_ping(h):
        name, ip, port = h
        if ip == "223.112.100.140":
            return None  # 模拟黄金主站挂了
        if ip == "123.45.67.89":
            return (66.0, "备用新主站", ip, port)  # 模拟深搜池命中
        return None

    with patch.object(fetcher, "_ping_single_host", side_effect=mock_ping):
        with patch("ats.tdx_realtime_fetcher.get_all_tdx_hosts") as mock_get_all:
            # 第一次调用（精简池）只有挂掉的黄金主站
            # 第二次调用（全网深搜池）包含新节点 123.45.67.89
            def dynamic_get_all(include_full=False, exclude_cooldown=True):
                if not include_full:
                    return [("通达信江苏主站", "223.112.100.140", 7709)]
                else:
                    return [
                        ("通达信江苏主站", "223.112.100.140", 7709),
                        ("备用新主站", "123.45.67.89", 7709),
                    ]
            mock_get_all.side_effect = dynamic_get_all

            # 执行重选 (force=True)
            fetcher._init_best_server(force=True)

            # 关键断言：系统成功通过全网深搜自愈捕获了新主站 123.45.67.89！
            assert fetcher.current_host == ("备用新主站", "123.45.67.89", 7709)
            assert len(fetcher.active_hosts_pool) >= 1
            assert fetcher.active_hosts_pool[0][2] == "123.45.67.89"
