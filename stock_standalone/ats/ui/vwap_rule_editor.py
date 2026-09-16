# -*- coding: utf-8 -*-
"""
ats/ui/vwap_rule_editor.py
--------------------------
Qt6 策略规则可视化配置编辑器（盘中秒级热生效）。
支持：
1. 🛡️ 8 层主动防守守护阵列（时间衰减、无量不涨、反弹前高不过、冲高派发、震荡不创高、量价背离、大级别MA5d、VWAP兜底）
2. ⚔️ 进攻端与激进/保守双组投票机制（动能突破 + 分时结构清晰度 + 犹豫期一票否决）
3. 🌐 大盘/板块宏观守护（大盘跳水清仓、板块集中抛压、买入信号冻结）
4. 盘中修改参数实时落盘 json，并秒级热加载至运行时引擎，SBC 画布即刻自动重新测算买卖点！
"""

import os
import json
import logging
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QGroupBox, QGridLayout, QCheckBox, QDoubleSpinBox,
    QSpinBox, QMessageBox, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from ats.vwap_rule_model import VWAPRuleModel, DEFAULT_CONFIG_PATH

logger = logging.getLogger("VWAPRuleEditor")


class VWAPRuleEditorDialog(QDialog):
    """
    全自动分时策略规则与 8 层防守参数可视化配置界面
    """
    rules_updated = pyqtSignal()

    def __init__(self, parent=None, config_path: Optional[str] = None):
        super().__init__(parent)
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.rule_model = VWAPRuleModel(self.config_path)

        self.setWindowTitle("⚙️ 全自动分时策略规则与 8 层防守阵列可视化配置 (盘中热生效)")
        self.resize(760, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #101018;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #2a2a3c;
                background-color: #141420;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #1a1a28;
                color: #8888aa;
                padding: 6px 14px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 9pt;
            }
            QTabBar::tab:selected {
                background-color: #242436;
                color: #00ff88;
                border-bottom: 2px solid #00ff88;
            }
            QGroupBox {
                border: 1px solid #2a2a3c;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                color: #38bdf8;
                background-color: #141420;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #cccccc;
                font-size: 8.5pt;
            }
            QCheckBox {
                color: #ffffff;
                font-weight: bold;
                font-size: 8.5pt;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #1a1a28;
                color: #00ff88;
                border: 1px solid #3a3a4c;
                border-radius: 3px;
                padding: 2px 4px;
                font-weight: bold;
                font-size: 8.5pt;
            }
            QDoubleSpinBox:focus, QSpinBox:focus {
                border: 1px solid #00ff88;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部提示条
        hdr = QLabel("💡 提示: 参数修改后点击【💾 保存并盘中热生效】，规则将毫秒级写入配置并通知 SBC 分时走势图实时重新跑测与标记！")
        hdr.setStyleSheet("color: #ffd700; font-size: 8.5pt; background-color: #1e1e12; padding: 4px 8px; border-radius: 3px; border: 1px solid #554411;")
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # 选项卡
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._build_defense_tab()
        self._build_offense_tab()
        self._build_guardian_tab()

        # 底部按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(10)

        self.btn_reset_default = QPushButton("🔄 恢复默认规则")
        self.btn_reset_default.setStyleSheet("background-color: #2b1f14; color: #ffaa44; font-weight: bold; border: 1px solid #ffaa44; border-radius: 4px; padding: 6px 14px;")
        self.btn_reset_default.clicked.connect(self._on_reset_defaults)
        btn_layout.addWidget(self.btn_reset_default)

        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 保存并盘中热生效")
        self.btn_save.setStyleSheet("background-color: #1a3a2a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 6px 20px; font-size: 9.5pt;")
        self.btn_save.clicked.connect(self._on_save_rules)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton("❌ 关闭")
        self.btn_close.setStyleSheet("background-color: #222230; color: #aaaaaa; border: 1px solid #444455; border-radius: 4px; padding: 6px 16px;")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # 加载初始数据
        self._load_values_from_config()

    def _build_defense_tab(self):
        """选项卡 1: 🛡️ 8 层防守主动出局守护阵列"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        # L1 时间衰减
        g_l1 = QGroupBox("Layer 1: ⏱️ 时间衰减止损 (买入死水横盘，杜绝无限死等)")
        gl1 = QGridLayout(g_l1)
        self.chk_l1 = QCheckBox("启用 L1 守护")
        self.sp_l1_warn = QSpinBox()
        self.sp_l1_warn.setRange(5, 60); self.sp_l1_warn.setSuffix(" 分钟预警")
        self.sp_l1_reduce = QSpinBox()
        self.sp_l1_reduce.setRange(10, 120); self.sp_l1_reduce.setSuffix(" 分钟减半")
        self.sp_l1_exit = QSpinBox()
        self.sp_l1_exit.setRange(15, 180); self.sp_l1_exit.setSuffix(" 分钟清仓")
        self.sp_l1_gain = QDoubleSpinBox()
        self.sp_l1_gain.setRange(0.05, 3.0); self.sp_l1_gain.setSingleStep(0.05); self.sp_l1_gain.setSuffix(" % 涨幅门槛")
        gl1.addWidget(self.chk_l1, 0, 0, 1, 4)
        gl1.addWidget(QLabel("时间阶段:"), 1, 0)
        gl1.addWidget(self.sp_l1_warn, 1, 1)
        gl1.addWidget(self.sp_l1_reduce, 1, 2)
        gl1.addWidget(self.sp_l1_exit, 1, 3)
        gl1.addWidget(QLabel("低于涨幅视为未启动:"), 2, 0)
        gl1.addWidget(self.sp_l1_gain, 2, 1)
        lay.addWidget(g_l1)

        # L2 无量不涨
        g_l2 = QGroupBox("Layer 2: 📉 无量不涨止损 (主力弃庄缩量盘跌)")
        gl2 = QGridLayout(g_l2)
        self.chk_l2 = QCheckBox("启用 L2 守护")
        self.sp_l2_ratio = QDoubleSpinBox()
        self.sp_l2_ratio.setRange(0.1, 1.0); self.sp_l2_ratio.setSingleStep(0.05); self.sp_l2_ratio.setSuffix(" 缩量均比 (<50%)")
        self.sp_l2_gain = QDoubleSpinBox()
        self.sp_l2_gain.setRange(0.05, 2.0); self.sp_l2_gain.setSingleStep(0.05); self.sp_l2_gain.setSuffix(" % 涨幅门槛")
        gl2.addWidget(self.chk_l2, 0, 0, 1, 4)
        gl2.addWidget(QLabel("缩量门槛:"), 1, 0)
        gl2.addWidget(self.sp_l2_ratio, 1, 1)
        gl2.addWidget(QLabel("滞涨涨幅:"), 1, 2)
        gl2.addWidget(self.sp_l2_gain, 1, 3)
        lay.addWidget(g_l2)

        # L3 反弹前高不过 (600733 关键克星)
        g_l3 = QGroupBox("Layer 3: 🛑 反弹前高不过 (600733 致命被割点克星 — 阻力区遇阻机械离场)")
        g_l3.setStyleSheet("QGroupBox { border: 1px solid #ff4444; color: #ff8888; }")
        gl3 = QGridLayout(g_l3)
        self.chk_l3 = QCheckBox("启用 L3 守护 (极度推荐)")
        self.sp_l3_tol = QDoubleSpinBox()
        self.sp_l3_tol.setRange(0.1, 2.0); self.sp_l3_tol.setSingleStep(0.1); self.sp_l3_tol.setSuffix(" % 阻力区范围")
        self.sp_l3_dwell = QSpinBox()
        self.sp_l3_dwell.setRange(1, 15); self.sp_l3_dwell.setSuffix(" 分钟滞留遇阻")
        self.sp_l3_vr = QDoubleSpinBox()
        self.sp_l3_vr.setRange(0.3, 3.0); self.sp_l3_vr.setSingleStep(0.1); self.sp_l3_vr.setSuffix(" 最低放量量比")
        self.sp_l3_pullback = QDoubleSpinBox()
        self.sp_l3_pullback.setRange(0.5, 5.0); self.sp_l3_pullback.setSingleStep(0.1); self.sp_l3_pullback.setSuffix(" % 回落清仓线")
        gl3.addWidget(self.chk_l3, 0, 0, 1, 4)
        gl3.addWidget(QLabel("阻力区判定:"), 1, 0)
        gl3.addWidget(self.sp_l3_tol, 1, 1)
        gl3.addWidget(QLabel("滞留不过减半:"), 1, 2)
        gl3.addWidget(self.sp_l3_dwell, 1, 3)
        gl3.addWidget(QLabel("突破所需量比:"), 2, 0)
        gl3.addWidget(self.sp_l3_vr, 2, 1)
        gl3.addWidget(QLabel("遇阻回落清仓:"), 2, 2)
        gl3.addWidget(self.sp_l3_pullback, 2, 3)
        lay.addWidget(g_l3)

        # L4 冲高派发
        g_l4 = QGroupBox("Layer 4: ⚡ 冲高派发与诱多假突破识别 (长上影/爆量滞涨锁定利润)")
        gl4 = QGridLayout(g_l4)
        self.chk_l4 = QCheckBox("启用 L4 守护")
        self.sp_l4_surge = QDoubleSpinBox()
        self.sp_l4_surge.setRange(1.0, 10.0); self.sp_l4_surge.setSingleStep(0.5); self.sp_l4_surge.setSuffix(" % 日内冲高门槛")
        self.sp_l4_drop = QDoubleSpinBox()
        self.sp_l4_drop.setRange(0.5, 5.0); self.sp_l4_drop.setSingleStep(0.2); self.sp_l4_drop.setSuffix(" % 高点回撤清仓")
        gl4.addWidget(self.chk_l4, 0, 0, 1, 4)
        gl4.addWidget(QLabel("冲高幅度:"), 1, 0)
        gl4.addWidget(self.sp_l4_surge, 1, 1)
        gl4.addWidget(QLabel("冲高回撤:"), 1, 2)
        gl4.addWidget(self.sp_l4_drop, 1, 3)
        lay.addWidget(g_l4)

        # L5/L6/L7/L8 简略汇总组
        g_rest = QGroupBox("Layer 5~8: 震荡不创高 / 量价背离 / 大级别 MA5d 拐头 / VWAP 兜底")
        gr = QGridLayout(g_rest)
        self.chk_l5 = QCheckBox("L5 震荡不创高 (波峰连续下移)")
        self.chk_l6 = QCheckBox("L6 量价背离出局 (资金流出顶背离)")
        self.chk_l7 = QCheckBox("L7 大级别 MA5d 拐头 (跨周期反抽均价离场)")
        self.chk_l8 = QCheckBox("L8 VWAP 破位最后防线 (5分钟强清兜底)")
        gr.addWidget(self.chk_l5, 0, 0)
        gr.addWidget(self.chk_l6, 0, 1)
        gr.addWidget(self.chk_l7, 1, 0)
        gr.addWidget(self.chk_l8, 1, 1)
        lay.addWidget(g_rest)

        scroll.setWidget(w)
        self.tabs.addTab(scroll, "🛡️ 8 层主动防守守护阵列")

    def _build_offense_tab(self):
        """选项卡 2: ⚔️ 进攻端与激进/保守双组投票机制"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)

        g_con = QGroupBox("🛡️ 保守组辅助监管审查（核心机制：分时犹豫期一票否决权）")
        g_con.setStyleSheet("QGroupBox { border: 1px solid #00ff88; color: #00ff88; }")
        gl = QGridLayout(g_con)
        self.chk_con_dual = QCheckBox("强制双重同意开仓 (Dual Consent: 激进组+保守组均赞成才买入)")
        self.chk_con_veto_hesitation = QCheckBox("对多空犹豫期行使一票否决 (Veto on Hesitation)")
        self.sp_con_clarity = QDoubleSpinBox()
        self.sp_con_clarity.setRange(40.0, 95.0); self.sp_con_clarity.setSingleStep(5.0); self.sp_con_clarity.setSuffix(" 分 (形态清晰度门槛)")
        self.sp_con_star_ratio = QDoubleSpinBox()
        self.sp_con_star_ratio.setRange(0.1, 0.8); self.sp_con_star_ratio.setSingleStep(0.05); self.sp_con_star_ratio.setSuffix(" (十字星容许上限)")
        gl.addWidget(self.chk_con_dual, 0, 0, 1, 2)
        gl.addWidget(self.chk_con_veto_hesitation, 1, 0, 1, 2)
        gl.addWidget(QLabel("分时形态清晰度最低要求:"), 2, 0)
        gl.addWidget(self.sp_con_clarity, 2, 1)
        gl.addWidget(QLabel("连续 10 根十字星比例上限:"), 3, 0)
        gl.addWidget(self.sp_con_star_ratio, 3, 1)
        lay.addWidget(g_con)

        g_agg = QGroupBox("⚔️ 激进组买入触发条件 (VWAP 突破 & 动能量比)")
        gl2 = QGridLayout(g_agg)
        self.sp_agg_consol_min = QSpinBox()
        self.sp_agg_consol_min.setRange(5, 60); self.sp_agg_consol_min.setSuffix(" 分钟 (筑底横盘)")
        self.sp_agg_consol_rng = QDoubleSpinBox()
        self.sp_agg_consol_rng.setRange(0.5, 3.0); self.sp_agg_consol_rng.setSingleStep(0.1); self.sp_agg_consol_rng.setSuffix(" % (横盘最大振幅)")
        self.sp_agg_vr = QDoubleSpinBox()
        self.sp_agg_vr.setRange(0.8, 3.0); self.sp_agg_vr.setSingleStep(0.1); self.sp_agg_vr.setSuffix(" (突破最低量比)")
        self.sp_agg_mp_score = QDoubleSpinBox()
        self.sp_agg_mp_score.setRange(40.0, 90.0); self.sp_agg_mp_score.setSingleStep(5.0); self.sp_agg_mp_score.setSuffix(" 分 (多周期最低分)")
        gl2.addWidget(QLabel("低位横盘整理分钟数:"), 0, 0)
        gl2.addWidget(self.sp_agg_consol_min, 0, 1)
        gl2.addWidget(QLabel("横盘整理最大振幅:"), 0, 2)
        gl2.addWidget(self.sp_agg_consol_rng, 0, 3)
        gl2.addWidget(QLabel("突破 VWAP 最低量比:"), 1, 0)
        gl2.addWidget(self.sp_agg_vr, 1, 1)
        gl2.addWidget(QLabel("多周期通道最低评分:"), 1, 2)
        gl2.addWidget(self.sp_agg_mp_score, 1, 3)
        lay.addWidget(g_agg)

        lay.addStretch()
        self.tabs.addTab(w, "⚔️ 进攻端与双组投票")

    def _build_guardian_tab(self):
        """选项卡 3: 🌐 大盘/板块宏观守护"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)

        g_mkt = QGroupBox("🌐 大盘系统性风险熔断 (Market Crash Circuit Breaker)")
        gl = QGridLayout(g_mkt)
        self.chk_mkt_crash = QCheckBox("启用大盘急杀一键清仓全仓止损")
        self.sp_down_up_ratio = QDoubleSpinBox()
        self.sp_down_up_ratio.setRange(1.5, 6.0); self.sp_down_up_ratio.setSingleStep(0.5); self.sp_down_up_ratio.setSuffix(" 倍 (下跌/上涨家数比)")
        self.sp_limit_down_cnt = QSpinBox()
        self.sp_limit_down_cnt.setRange(5, 100); self.sp_limit_down_cnt.setSuffix(" 只 (全市场跌停家数门槛)")
        gl.addWidget(self.chk_mkt_crash, 0, 0, 1, 2)
        gl.addWidget(QLabel("全市场下跌/上涨家数比:"), 1, 0)
        gl.addWidget(self.sp_down_up_ratio, 1, 1)
        gl.addWidget(QLabel("跌停家数超过即清仓:"), 2, 0)
        gl.addWidget(self.sp_limit_down_cnt, 2, 1)
        lay.addWidget(g_mkt)

        g_sec = QGroupBox("📊 板块共振抛压与买入冻结 (Sector Dump & Freeze)")
        gl2 = QGridLayout(g_sec)
        self.chk_sec_dump = QCheckBox("启用同板块集中破位清仓")
        self.sp_sec_broken = QSpinBox()
        self.sp_sec_broken.setRange(2, 10); self.sp_sec_broken.setSuffix(" 只 (同板块破位家数)")
        self.chk_freeze_buy = QCheckBox("市场降温弱势期一键冻结买入信号 (Freeze Buy)")
        gl2.addWidget(self.chk_sec_dump, 0, 0, 1, 2)
        gl2.addWidget(QLabel("板块内个股破均线触发:"), 1, 0)
        gl2.addWidget(self.sp_sec_broken, 1, 1)
        gl2.addWidget(self.chk_freeze_buy, 2, 0, 1, 2)
        lay.addWidget(g_sec)

        lay.addStretch()
        self.tabs.addTab(w, "🌐 宏观与板块守护")

    def _load_values_from_config(self):
        """从 JSON 加载配置参数至控件"""
        cfg = self.rule_model._raw_config
        ex_layers = cfg.get("exit_layers", {})

        # L1
        l1 = ex_layers.get("layer1_time_decay", {})
        self.chk_l1.setChecked(l1.get("enabled", True))
        p1 = l1.get("params", {})
        self.sp_l1_warn.setValue(p1.get("warning_minutes", 10))
        self.sp_l1_reduce.setValue(p1.get("reduce_half_minutes", 20))
        self.sp_l1_exit.setValue(p1.get("exit_all_minutes", 30))
        self.sp_l1_gain.setValue(p1.get("min_gain_pct", 0.3))

        # L2
        l2 = ex_layers.get("layer2_volume_absence", {})
        self.chk_l2.setChecked(l2.get("enabled", True))
        p2 = l2.get("params", {})
        self.sp_l2_ratio.setValue(p2.get("volume_drop_ratio", 0.5))
        self.sp_l2_gain.setValue(p2.get("max_gain_pct", 0.2))

        # L3
        l3 = ex_layers.get("layer3_failed_rally", {})
        self.chk_l3.setChecked(l3.get("enabled", True))
        p3 = l3.get("params", {})
        self.sp_l3_tol.setValue(p3.get("resistance_tolerance_pct", 0.5))
        self.sp_l3_dwell.setValue(p3.get("dwell_minutes", 3))
        self.sp_l3_vr.setValue(p3.get("min_breakout_volume_ratio", 0.8))
        self.sp_l3_pullback.setValue(p3.get("pullback_exit_pct", 1.5))

        # L4
        l4 = ex_layers.get("layer4_distribution", {})
        self.chk_l4.setChecked(l4.get("enabled", True))
        p4 = l4.get("params", {})
        self.sp_l4_surge.setValue(p4.get("surge_gain_threshold", 3.0))
        self.sp_l4_drop.setValue(p4.get("retracement_threshold", 2.0))

        # L5~L8
        self.chk_l5.setChecked(ex_layers.get("layer5_oscillation_no_new_high", {}).get("enabled", True))
        self.chk_l6.setChecked(ex_layers.get("layer6_volume_price_divergence", {}).get("enabled", True))
        self.chk_l7.setChecked(ex_layers.get("layer7_multi_timeframe_rollover", {}).get("enabled", True))
        self.chk_l8.setChecked(ex_layers.get("layer8_vwap_break_final", {}).get("enabled", True))

        # 保守组
        con = cfg.get("strategy_groups", {}).get("conservative", {}).get("oversight_rules", {})
        self.chk_con_dual.setChecked(con.get("consensus_required", True))
        self.chk_con_veto_hesitation.setChecked(con.get("veto_on_hesitation", True))
        self.sp_con_clarity.setValue(con.get("min_structure_clarity", 70.0))
        self.sp_con_star_ratio.setValue(con.get("max_hesitation_star_ratio", 0.4))

        # 激进组
        agg_rules = cfg.get("strategy_groups", {}).get("aggressive", {}).get("buy_rules", [])
        if agg_rules:
            c0 = agg_rules[0].get("conditions", {})
            self.sp_agg_consol_min.setValue(c0.get("min_consolidation_minutes", 10))
            self.sp_agg_consol_rng.setValue(c0.get("max_consolidation_range_pct", 1.2))
            self.sp_agg_vr.setValue(c0.get("min_volume_ratio", 1.1))
            self.sp_agg_mp_score.setValue(c0.get("min_multi_period_score", 65.0))

        # 守护
        mg = cfg.get("market_guardian", {})
        self.chk_mkt_crash.setChecked(mg.get("market_crash", {}).get("enabled", True))
        self.sp_down_up_ratio.setValue(mg.get("market_crash", {}).get("down_up_ratio_threshold", 3.0))
        self.sp_limit_down_cnt.setValue(mg.get("market_crash", {}).get("limit_down_count_threshold", 20))
        self.chk_sec_dump.setChecked(mg.get("sector_dump", {}).get("enabled", True))
        self.sp_sec_broken.setValue(mg.get("sector_dump", {}).get("min_broken_stocks", 3))
        self.chk_freeze_buy.setChecked(mg.get("freeze_buy", {}).get("enabled", True))

    def _on_save_rules(self):
        """将控件中的数值整理写盘，并通知热重载"""
        cfg = self.rule_model._raw_config
        ex = cfg.setdefault("exit_layers", {})

        # L1
        l1 = ex.setdefault("layer1_time_decay", {})
        l1["enabled"] = self.chk_l1.isChecked()
        p1 = l1.setdefault("params", {})
        p1["warning_minutes"] = self.sp_l1_warn.value()
        p1["reduce_half_minutes"] = self.sp_l1_reduce.value()
        p1["exit_all_minutes"] = self.sp_l1_exit.value()
        p1["min_gain_pct"] = round(self.sp_l1_gain.value(), 2)

        # L2
        l2 = ex.setdefault("layer2_volume_absence", {})
        l2["enabled"] = self.chk_l2.isChecked()
        p2 = l2.setdefault("params", {})
        p2["volume_drop_ratio"] = round(self.sp_l2_ratio.value(), 2)
        p2["max_gain_pct"] = round(self.sp_l2_gain.value(), 2)

        # L3
        l3 = ex.setdefault("layer3_failed_rally", {})
        l3["enabled"] = self.chk_l3.isChecked()
        p3 = l3.setdefault("params", {})
        p3["resistance_tolerance_pct"] = round(self.sp_l3_tol.value(), 2)
        p3["dwell_minutes"] = self.sp_l3_dwell.value()
        p3["min_breakout_volume_ratio"] = round(self.sp_l3_vr.value(), 2)
        p3["pullback_exit_pct"] = round(self.sp_l3_pullback.value(), 2)

        # L4
        l4 = ex.setdefault("layer4_distribution", {})
        l4["enabled"] = self.chk_l4.isChecked()
        p4 = l4.setdefault("params", {})
        p4["surge_gain_threshold"] = round(self.sp_l4_surge.value(), 2)
        p4["retracement_threshold"] = round(self.sp_l4_drop.value(), 2)

        # L5~L8
        ex.setdefault("layer5_oscillation_no_new_high", {})["enabled"] = self.chk_l5.isChecked()
        ex.setdefault("layer6_volume_price_divergence", {})["enabled"] = self.chk_l6.isChecked()
        ex.setdefault("layer7_multi_timeframe_rollover", {})["enabled"] = self.chk_l7.isChecked()
        ex.setdefault("layer8_vwap_break_final", {})["enabled"] = self.chk_l8.isChecked()

        # 保守组
        con = cfg.setdefault("strategy_groups", {}).setdefault("conservative", {}).setdefault("oversight_rules", {})
        con["consensus_required"] = self.chk_con_dual.isChecked()
        con["veto_on_hesitation"] = self.chk_con_veto_hesitation.isChecked()
        con["min_structure_clarity"] = round(self.sp_con_clarity.value(), 1)
        con["max_hesitation_star_ratio"] = round(self.sp_con_star_ratio.value(), 2)

        # 激进组
        agg_rules = cfg.setdefault("strategy_groups", {}).setdefault("aggressive", {}).setdefault("buy_rules", [])
        if agg_rules:
            c0 = agg_rules[0].setdefault("conditions", {})
            c0["min_consolidation_minutes"] = self.sp_agg_consol_min.value()
            c0["max_consolidation_range_pct"] = round(self.sp_agg_consol_rng.value(), 2)
            c0["min_volume_ratio"] = round(self.sp_agg_vr.value(), 2)
            c0["min_multi_period_score"] = round(self.sp_agg_mp_score.value(), 1)

        # 宏观守护
        mg = cfg.setdefault("market_guardian", {})
        mc = mg.setdefault("market_crash", {})
        mc["enabled"] = self.chk_mkt_crash.isChecked()
        mc["down_up_ratio_threshold"] = round(self.sp_down_up_ratio.value(), 2)
        mc["limit_down_count_threshold"] = self.sp_limit_down_cnt.value()
        sd = mg.setdefault("sector_dump", {})
        sd["enabled"] = self.chk_sec_dump.isChecked()
        sd["min_broken_stocks"] = self.sp_sec_broken.value()
        mg.setdefault("freeze_buy", {})["enabled"] = self.chk_freeze_buy.isChecked()

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.rule_model.reload()
            self.rules_updated.emit()
            QMessageBox.information(self, "保存成功", "✅ 策略规则配置已保存并完成热重载！\nSBC 分时图将立即以最新参数重新测算信号！")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入规则配置文件失败:\n{e}")

    def _on_reset_defaults(self):
        """恢复默认规则配置"""
        res = QMessageBox.question(self, "确认恢复", "确定将所有策略规则恢复为系统默认出厂参数吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            self.rule_model._apply_fallback_config()
            self._load_values_from_config()
