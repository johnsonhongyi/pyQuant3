# -*- coding: utf-8 -*-
"""
tests/test_subnew_intraday_volume_normalization.py
--------------------------------------------------
2026-09-22 部署计划 P1-01 专项测试：
1. 早盘 09:30~10:00 成交量信号衰减归一化 pure function 8 个计划书时点矩阵测试
2. 09:31 10x 原始放量折减为 2.0x
3. 10:00 与 13:00 不再衰减
4. Feature Flag (enable_intraday_volume_normalization) 开关切换与安全默认值
5. extra_data 审计字段记录与不可击穿安全保护
6. 防守信号 (CLIMAX_EXIT / WEAK_EXIT) 绝不弱化
"""

import pytest
import datetime
import pandas as pd
import numpy as np

from ats.strategy.ipo_vwap_detector_engine import (
    compute_intraday_volume_attenuation_factor,
    get_intraday_volume_attenuation_factor,
    normalize_intraday_volume,
    normalize_volume_signal,
    load_deployment_config,
    parse_feature_flag_value,
    IPOVWAPDetectorEngine,
    VWAPDetectorSignal,
)


class TestIntradayVolumeAttenuationMatrix:
    """8 个计划书时点矩阵确定性测试"""

    def test_matrix_09_30(self):
        # 09:30 因子应为 0.20 (下限 clamp)
        assert compute_intraday_volume_attenuation_factor("09:30") == pytest.approx(0.20, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("09:30:00") == pytest.approx(0.20, abs=1e-5)
        assert get_intraday_volume_attenuation_factor(datetime.time(9, 30)) == pytest.approx(0.20, abs=1e-5)

    def test_matrix_09_31(self):
        # 09:31 因子应为 0.20 (1/30 = 0.0333 < 0.20 -> clamp 0.20)
        assert compute_intraday_volume_attenuation_factor("09:31") == pytest.approx(0.20, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("09:31:00") == pytest.approx(0.20, abs=1e-5)
        assert get_intraday_volume_attenuation_factor(datetime.time(9, 31, 0)) == pytest.approx(0.20, abs=1e-5)

    def test_matrix_09_35(self):
        # 09:35 因子应为 0.20 (5/30 = 0.1667 < 0.20 -> clamp 0.20)
        assert compute_intraday_volume_attenuation_factor("09:35") == pytest.approx(0.20, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("09:35:00") == pytest.approx(0.20, abs=1e-5)

    def test_matrix_09_45(self):
        # 09:45 因子应为 0.50 (15/30 = 0.50)
        assert compute_intraday_volume_attenuation_factor("09:45") == pytest.approx(0.50, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("09:45:00") == pytest.approx(0.50, abs=1e-5)
        assert get_intraday_volume_attenuation_factor(datetime.time(9, 45, 0)) == pytest.approx(0.50, abs=1e-5)

    def test_matrix_09_59_59(self):
        # 09:59:59 因子逼近 1.0 (29.9833 / 30 ≈ 0.999444)
        factor = compute_intraday_volume_attenuation_factor("09:59:59")
        assert factor == pytest.approx(0.999444, abs=1e-4)
        assert 0.999 < factor < 1.0

    def test_matrix_10_00(self):
        # 10:00 因子恒为 1.0
        assert compute_intraday_volume_attenuation_factor("10:00") == pytest.approx(1.0, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("10:00:00") == pytest.approx(1.0, abs=1e-5)
        assert get_intraday_volume_attenuation_factor(datetime.time(10, 0, 0)) == pytest.approx(1.0, abs=1e-5)

    def test_matrix_11_30(self):
        # 11:30 因子恒为 1.0
        assert compute_intraday_volume_attenuation_factor("11:30") == pytest.approx(1.0, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("11:30:00") == pytest.approx(1.0, abs=1e-5)

    def test_matrix_13_00(self):
        # 下午 13:00 绝不能重新开始衰减，恒为 1.0
        assert compute_intraday_volume_attenuation_factor("13:00") == pytest.approx(1.0, abs=1e-5)
        assert compute_intraday_volume_attenuation_factor("13:00:00") == pytest.approx(1.0, abs=1e-5)
        assert get_intraday_volume_attenuation_factor(datetime.time(13, 0, 0)) == pytest.approx(1.0, abs=1e-5)

    @pytest.mark.parametrize("time_str,expected", [
        ("09:30", 0.20),
        ("09:31", 0.20),
        ("09:35", 0.20),
        ("09:45", 0.50),
        ("09:59:59", 0.999444),
        ("10:00", 1.0),
        ("11:30", 1.0),
        ("13:00", 1.0),
    ])
    def test_all_eight_matrix_points(self, time_str, expected):
        res = compute_intraday_volume_attenuation_factor(time_str)
        assert res == pytest.approx(expected, abs=1e-4)


class TestVolumeNormalizationCalculations:
    """放量信号折减计算专项测试"""

    def test_09_31_10x_surge_attenuation_to_2x(self):
        # 09:31 10x 原始放量折减为 2.0x (10.0 * 0.20 = 2.0)
        raw_vol = 10.0
        norm_vol = normalize_intraday_volume(raw_vol, "09:31", enabled=True)
        assert norm_vol == pytest.approx(2.0, abs=1e-5)

        # 别名函数对齐
        assert normalize_volume_signal(raw_vol, "09:31", enabled=True) == pytest.approx(2.0, abs=1e-5)

    def test_10_00_and_13_00_no_attenuation(self):
        # 10:00 与 13:00 不衰减
        assert normalize_intraday_volume(10.0, "10:00", enabled=True) == pytest.approx(10.0, abs=1e-5)
        assert normalize_intraday_volume(10.0, "13:00", enabled=True) == pytest.approx(10.0, abs=1e-5)
        assert normalize_intraday_volume(5.5, "14:30:00", enabled=True) == pytest.approx(5.5, abs=1e-5)

    def test_feature_flag_false_preserves_original_behavior(self):
        # Feature Flag=False 时即使在 09:31 也完全保持原始行为，不折减
        raw_vol = 10.0
        norm_vol = normalize_intraday_volume(raw_vol, "09:31", enabled=False)
        assert norm_vol == pytest.approx(10.0, abs=1e-5)

        engine_disabled = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=False)
        assert engine_disabled.normalize_volume(10.0, "09:31") == pytest.approx(10.0, abs=1e-5)

    def test_robustness_and_zero_division_guard(self):
        # 非法字符串、None、极端情况绝不抛异常且安全回退
        assert compute_intraday_volume_attenuation_factor("invalid_time") == 1.0
        assert compute_intraday_volume_attenuation_factor("") == 1.0
        assert normalize_intraday_volume(0.0, "09:31", enabled=True) == 0.0
        assert normalize_intraday_volume(-5.0, "09:31", enabled=True) == -1.0


class TestDetectorEngineIntegrationAndExtraData:
    """检测器集成与 extra_data 审计字段测试"""

    def _create_mock_intraday_df(self, last_time: str = "09:31:00", volume_multiplier: float = 10.0) -> pd.DataFrame:
        """生成构造好底部平底横盘及最后一根放量 Bar 的测试分时数据"""
        n_bars = 20
        # 构造平底箱体，前 17 根均量 1000，最后 3 根大幅放量 volume_multiplier 倍
        times = [f"09:{30 + i // 2:02d}:{30 * (i % 2):02d}" for i in range(n_bars)]
        times[-1] = last_time

        closes = [10.0] * n_bars
        highs = [10.02] * n_bars
        lows = [9.98] * n_bars
        vwaps = [10.0] * n_bars
        vols = [1000.0] * (n_bars - 3) + [1000.0 * volume_multiplier] * 3

        df = pd.DataFrame({
            "date": ["2026-09-22"] * n_bars,
            "time": times,
            "close": closes,
            "price": closes,
            "high": highs,
            "low": lows,
            "vwap": vwaps,
            "volume": vols,
            "vol": vols,
        })
        return df

    def test_detector_integration_at_09_31_with_audit_fields(self):
        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=True)
        sig = VWAPDetectorSignal(code="688001", name="测试标的", price=10.0, vwap=10.0)

        df = self._create_mock_intraday_df(last_time="09:31:00", volume_multiplier=10.0)
        engine._evaluate_bottom_base_structure(df, sig, eval_time="09:31:00")

        # 验证 extra_data 审计字段
        assert "volume_attenuation_factor" in sig.extra_data
        assert "raw_volume_signal" in sig.extra_data
        assert "normalized_volume_signal" in sig.extra_data

        assert sig.extra_data["volume_attenuation_factor"] == pytest.approx(0.20, abs=1e-5)
        assert sig.extra_data["raw_volume_signal"] == pytest.approx(10.0, abs=1e-2)
        # 10x 原始放量经 0.20 衰减后应为 2.0x
        assert sig.extra_data["normalized_volume_signal"] == pytest.approx(2.0, abs=1e-2)

    def test_detector_suppresses_borderline_false_positive_at_09_31(self):
        # 假设早盘短时放量 2.0 倍 (阈值 1.25 倍)
        # 未开启归一化时 2.0x >= 1.25x 会触发 vol_surge
        # 开启归一化后 2.0x * 0.20 = 0.40x < 1.25x，成功压制早盘假阳性放量！
        df = self._create_mock_intraday_df(last_time="09:31:00", volume_multiplier=2.0)

        # 开启归一化
        engine_on = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=True)
        sig_on = VWAPDetectorSignal(code="688001", name="测试标的", price=10.01, vwap=10.0)
        engine_on._evaluate_bottom_base_structure(df, sig_on, eval_time="09:31:00")
        assert sig_on.extra_data["normalized_volume_signal"] == pytest.approx(0.40, abs=1e-2)

        # 关闭归一化
        engine_off = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=False)
        sig_off = VWAPDetectorSignal(code="688001", name="测试标的", price=10.01, vwap=10.0)
        engine_off._evaluate_bottom_base_structure(df, sig_off, eval_time="09:31:00")
        assert sig_off.extra_data["normalized_volume_signal"] == pytest.approx(2.0, abs=1e-2)
        assert sig_off.extra_data["volume_attenuation_factor"] == 1.0

    def test_defensive_climax_exit_never_weakened(self):
        # 极端高潮平仓点 (偏离 VWAP 超过 25% 且自高位回撤超过 3.5%)
        # 绝不受早盘归一化削弱
        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=True)
        sig = VWAPDetectorSignal(code="601091", name="高潮标的", price=100.0, vwap=70.0)

        df = pd.DataFrame({
            "date": ["2026-09-22"] * 10,
            "time": ["09:31:00"] * 10,
            "open": [75.0] * 10,
            "close": [100.0] * 10,
            "price": [100.0] * 10,
            "high": [105.0] * 10,  # 回撤 (105-100)/105 ≈ 4.76% >= 3.5%
            "low": [74.0] * 10,
            "vwap": [70.0] * 10,
            "volume": [99999.0] * 10,
        })

        engine._evaluate_vwap_structure(df, sig)
        assert sig.is_climax_exit is True
        engine._synthesize_final_decision(sig)
        assert sig.signal_type == "CLIMAX_EXIT"
        assert sig.signal_tier == "ALERT"


class TestDeploymentConfigurationAndFlagDefaults:
    """配置文件读取与安全默认值测试"""

    def test_deployment_config_file_exists_and_loads(self):
        cfg = load_deployment_config()
        assert isinstance(cfg, dict)
        assert "enable_intraday_volume_normalization" in cfg
        assert cfg["enable_intraday_volume_normalization"] is True

    def test_safe_default_true_on_missing_or_corrupt_config(self, monkeypatch):
        # 模拟读取异常，必须安全默认 True
        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: (_ for _ in ()).throw(RuntimeError("Disk Read Failure"))
        )
        flag = IPOVWAPDetectorEngine._resolve_normalization_flag()
        assert flag is True

    @pytest.mark.parametrize("illegal_str", [
        "invalid",
        "random_token",
        "none",
        "disabled",
        "off",
        "UNKNOWN",
        "2",
        "-1",
        "",
        "   ",
        "null",
        "undefined",
    ])
    def test_illegal_string_flags_fallback_to_true(self, illegal_str, monkeypatch):
        # 非法字符串 Feature Flag 语义解析失败时必须安全回退 True，绝不关闭早盘归一化
        assert parse_feature_flag_value(illegal_str) is True

        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: {"enable_intraday_volume_normalization": illegal_str}
        )
        assert IPOVWAPDetectorEngine._resolve_normalization_flag() is True

        # 引擎初始化与归一化行为验证
        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=illegal_str)
        assert engine.enable_intraday_volume_normalization is True
        # 09:31 原始 10x 放量仍然衰减至 2.0x (未被关闭)
        assert engine.normalize_volume(10.0, "09:31") == pytest.approx(2.0, abs=1e-5)

    @pytest.mark.parametrize("illegal_num", [
        2,
        -1,
        100,
        -99,
        0.5,
        999,
        2.0,
        -0.1,
    ])
    def test_illegal_number_flags_fallback_to_true(self, illegal_num, monkeypatch):
        # 非法数字 (除 0 与 1 以外) 必须安全回退 True，绝不关闭早盘归一化
        assert parse_feature_flag_value(illegal_num) is True

        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: {"enable_intraday_volume_normalization": illegal_num}
        )
        assert IPOVWAPDetectorEngine._resolve_normalization_flag() is True

        # 引擎初始化与归一化行为验证
        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=illegal_num)
        assert engine.enable_intraday_volume_normalization is True
        assert engine.normalize_volume(10.0, "09:31") == pytest.approx(2.0, abs=1e-5)

    @pytest.mark.parametrize("valid_false_val", [
        False,
        "false",
        "False",
        "FALSE",
        " 0 ",
        "0",
        "no",
        "NO",
        "No",
        0,
        0.0,
    ])
    def test_valid_false_semantics_disable_normalization(self, valid_false_val, monkeypatch):
        # 显式 false/0/no 语义必须能正确关闭早盘归一化
        assert parse_feature_flag_value(valid_false_val) is False

        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: {"enable_intraday_volume_normalization": valid_false_val}
        )
        assert IPOVWAPDetectorEngine._resolve_normalization_flag() is False

        # 引擎关闭归一化验证：09:31 原始 10x 保持 10x 不衰减
        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=valid_false_val)
        assert engine.enable_intraday_volume_normalization is False
        assert engine.normalize_volume(10.0, "09:31") == pytest.approx(10.0, abs=1e-5)

    @pytest.mark.parametrize("valid_true_val", [
        True,
        "true",
        "True",
        "TRUE",
        " 1 ",
        "1",
        "yes",
        "YES",
        "Yes",
        1,
        1.0,
    ])
    def test_valid_true_semantics_enable_normalization(self, valid_true_val, monkeypatch):
        # 显式 true/1/yes 语义必须正确开启早盘归一化
        assert parse_feature_flag_value(valid_true_val) is True

        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: {"enable_intraday_volume_normalization": valid_true_val}
        )
        assert IPOVWAPDetectorEngine._resolve_normalization_flag() is True

        engine = IPOVWAPDetectorEngine(enable_intraday_volume_normalization=valid_true_val)
        assert engine.enable_intraday_volume_normalization is True
        assert engine.normalize_volume(10.0, "09:31") == pytest.approx(2.0, abs=1e-5)

    @pytest.mark.parametrize("abnormal_cfg", [
        {},
        {"other_key": "val"},
        {"enable_intraday_volume_normalization": None},
        {"enable_intraday_volume_normalization": []},
        {"enable_intraday_volume_normalization": {}},
        [],
        "corrupt_string_config",
        None,
    ])
    def test_missing_corrupt_or_abnormal_type_config_fallback_to_true(self, abnormal_cfg, monkeypatch):
        # 配置缺失、非字典格式、类型异常均必须安全回退 True
        monkeypatch.setattr(
            "ats.strategy.ipo_vwap_detector_engine.load_deployment_config",
            lambda: abnormal_cfg
        )
        assert IPOVWAPDetectorEngine._resolve_normalization_flag() is True
