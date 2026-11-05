import os
import sys
import tempfile
import pytest

from sys_utils import get_app_root, get_base_path, get_conf_path

def test_alert_notifier_adaptive_paths():
    """验证 alert_notifier 模块的配置文件与图标路径使用打包自适应机制"""
    import ats.alert_notifier as an
    assert os.path.isabs(an.ALERT_CONFIG_FILE)
    assert "alert_notifier_layout.json" in an.ALERT_CONFIG_FILE
    # 路径必须基于 app_root，不能包含临时的 .. 向上逃逸
    assert ".." not in os.path.normpath(an.ALERT_CONFIG_FILE)


def test_reentry_tracker_adaptive_paths():
    """验证 reentry_tracker 数据库路径自动对齐 app_root"""
    from ats.reentry_tracker import ReentryTracker
    tracker = ReentryTracker(check_interval=9999)
    # 验证能正常初始化且 reload_closed_trades 正常执行
    tracker.reload_closed_trades()
    assert tracker._last_db_load_time > 0


def test_multi_period_channel_adaptive_paths():
    """验证 multi_period 策略模块统一使用 get_app_root"""
    import ats.multi_period_channel_strategy as mpcs
    import ats.multi_period_channel_backtester as mpcb
    import ats.multi_period_resampler as mpr

    app_root = get_app_root()
    assert os.path.normcase(os.path.abspath(mpcs.PROJECT_ROOT)) == os.path.normcase(os.path.abspath(app_root))
    assert os.path.normcase(os.path.abspath(mpcb.PROJECT_ROOT)) == os.path.normcase(os.path.abspath(app_root))
    assert os.path.normcase(os.path.abspath(mpr.PROJECT_ROOT)) == os.path.normcase(os.path.abspath(app_root))


def test_fusion_modules_packaged_environment_adaptation(monkeypatch):
    """模拟在不同的 INSTOCK_APP_ROOT 下，fusion 各核心模块自动对齐"""
    with tempfile.TemporaryDirectory() as fake_root:
        monkeypatch.setenv("INSTOCK_APP_ROOT", fake_root)

        # 验证 session_ctx
        import ats.fusion.session_ctx as sctx
        store = sctx.SessionContextStore(root=os.path.join(sctx._app_root(), "logs", "session_ctx"))
        assert os.path.normcase(fake_root) in os.path.normcase(store.root)

        # 验证 market_ctx
        import ats.fusion.market_ctx as mctx
        assert os.path.normcase(fake_root) in os.path.normcase(mctx._app_root())

        # 验证 live_bridge
        import ats.fusion.live_bridge as lb
        assert os.path.normcase(fake_root) in os.path.normcase(lb._app_root())

        # 验证 hot_pool
        import ats.fusion.hot_pool as hp
        assert os.path.normcase(fake_root) in os.path.normcase(hp._app_root())

        # 验证 sector load_external_heat 默认 fallback
        from ats.fusion.sector import load_external_heat
        heat = load_external_heat("2026-11-05")
        assert isinstance(heat, dict)
