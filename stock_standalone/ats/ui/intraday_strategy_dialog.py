# -*- coding: utf-8 -*-
"""
ats/ui/intraday_strategy_dialog.py — ATS 分时阶梯交易策略 & 频准激光 8/18 上市动态时序评估一体化系统
特点：
1. 深度整合原有的分时阶梯交易策略（开盘定盘、时间轴阶段、规则达成、价格笼子挂单、买卖点信号路由与流水、SBC 实盘走势）与 7 节点时序动态打分评估体系；
2. Tab 1 为一体化实盘交易与动态评估工作台，数据由实时 df 全自动摄入解析并动态驱动；
3. Tab 2 为 8/18 开盘时间对齐全天分时模拟回测演练器（四大情景 A/B/C/D型，一键秒级回测 + 动态逐帧回放）；
4. Tab 3 为频准激光 8/18 专属盯盘模板、综合加权汇总表与 7 条实盘法则；
5. 基于 QMainWindow 独立窗口运行，支持窗口置顶 (StayOnTop) 与非模态异步数据推送。
"""

import sys
import os
import json
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 兼容开发模式单独运行子脚本（防重复挂载，打包运行下 if 为 False 不会污染 sys.path）
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CUR_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import (
    QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QTextEdit, QComboBox, QMessageBox, QFrame, QGridLayout, QProgressBar,
    QScrollArea, QTabWidget, QDoubleSpinBox, QRadioButton, QButtonGroup,
    QCheckBox, QSlider, QToolBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush, QIcon

from sys_utils import resolve_stock_name
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.ui.styles import apply_dark_theme, DARK_THEME_QSS
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyDialog")


class IntradayStrategyEditDialog(QDialog):
    """自定制策略编辑器弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 自定制分时交易策略 JSON 编辑器")
        self.resize(780, 580)
        self.engine = IntradayStrategyEngine.get_instance()
        apply_dark_theme(self)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        lbl_tips = QLabel("💡 提示：在下方可编辑/扩充分时交易策略规则 JSON，修改后点击“保存并应用”可即时完成配置落盘。")
        lbl_tips.setStyleSheet("color: #38bdf8; font-weight: bold;")
        layout.addWidget(lbl_tips)

        self.txt_json = QTextEdit()
        self.txt_json.setStyleSheet("background-color: #121218; color: #00ff88; font-family: Consolas, Monospace; font-size: 10pt;")
        layout.addWidget(self.txt_json)

        if os.path.exists(self.engine.config_path):
            try:
                with open(self.engine.config_path, "r", encoding="utf-8") as f:
                    self.txt_json.setText(f.read())
            except Exception:
                pass

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 保存并应用")
        btn_save.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 6px 16px;")
        btn_save.clicked.connect(self._on_save)

        btn_close = QPushButton("取消/关闭")
        btn_close.setStyleSheet("background-color: #333344; color: white; padding: 6px 16px;")
        btn_close.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _on_save(self):
        content = self.txt_json.toPlainText()
        try:
            data = json.loads(content)
            if self.engine.save_config(data):
                QMessageBox.information(self, "成功", "✅ 策略配置更新成功并已物理落盘！")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "❌ 策略配置保存失败，请检查文件写入权限。")
        except Exception as e:
            QMessageBox.critical(self, "JSON 语法错误", f"❌ 解析 JSON 格式失败:\n{e}")


class IntegratedTradingStrategyPanel(QWidget):
    """
    【核心】分时阶梯交易策略 & 7 节点动态评估一体化工作台 (Tab 1)
    整合开盘定盘、策略阶段推进、规则达成状态、价格笼子挂单、买卖点信号流水与 SBC 实盘走势
    """
    manual_score_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.code = "688826"
        self._is_updating = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. 顶部：开盘定盘速查与实时评级诊断卡
        status_card = QGroupBox("📌 开盘定盘速查 & 7 节点动态时序评级诊断")
        status_card.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 4px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        status_layout = QGridLayout(status_card)
        status_layout.setContentsMargins(10, 10, 10, 8)
        status_layout.setSpacing(6)

        self.lbl_open_info = QLabel("开盘基准: -- 元 | 所属档位: --")
        self.lbl_open_info.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffd700;")

        self.lbl_strat_name = QLabel("当前策略: --")
        self.lbl_strat_name.setStyleSheet("font-size: 10pt; font-weight: bold; color: #38bdf8;")

        self.lbl_score_badge = QLabel("🏆 综合评级: -- 分 (形态: --) | 资金强度: --")
        self.lbl_score_badge.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #00ff88;")

        self.lbl_position_status = QLabel("📦 持仓状态: 剩余 100% | 买卖步数: 0 步")
        self.lbl_position_status.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffaa44;")

        status_layout.addWidget(self.lbl_open_info, 0, 0)
        status_layout.addWidget(self.lbl_strat_name, 0, 1)
        status_layout.addWidget(self.lbl_score_badge, 1, 0)
        status_layout.addWidget(self.lbl_position_status, 1, 1)

        main_layout.addWidget(status_card)

        # 2. 💡 盘中阶段自动解析与实操指引
        self.action_card = QGroupBox("💡 盘中阶段自动解析与实操指引 (当前情况如何操作)")
        self.action_card.setStyleSheet("""
            QGroupBox {
                border: 2px solid #00ff88;
                border-radius: 6px;
                margin-top: 4px;
                font-weight: bold;
                color: #00ff88;
                background-color: #101918;
            }
        """)
        action_layout = QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(8, 8, 8, 8)
        action_layout.setSpacing(4)

        self.lbl_diagnosis = QLabel("⏳ 正在自动解析当前盘中阶段与行情特征...")
        self.lbl_diagnosis.setStyleSheet("color: #ffffff; font-size: 9.5pt; font-weight: bold;")
        self.lbl_diagnosis.setWordWrap(True)

        self.lbl_action = QLabel("【实操操作指引】--")
        self.lbl_action.setStyleSheet("color: #ffd700; font-size: 10pt; font-weight: bold; background: #1a221f; padding: 4px 8px; border-radius: 4px;")
        self.lbl_action.setWordWrap(True)

        action_layout.addWidget(self.lbl_diagnosis)
        action_layout.addWidget(self.lbl_action)
        main_layout.addWidget(self.action_card)

        # 3. 主分割器：左侧策略阶段与规则达成，右侧 SBC 实盘分时走势与指令流水
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== 左侧容器：时间轴策略阶段 + 规则达成表 + 7节点动态速查 =====
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 阶段指示 ScrollArea
        phase_box = QGroupBox("⏳ 盘中时间轴策略阶段 (结合 7 节点动态指示)")
        phase_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #aad4ff; background-color: #14141d; }")
        phase_box_layout = QVBoxLayout(phase_box)
        phase_box_layout.setContentsMargins(4, 8, 4, 4)

        self.phase_scroll = QScrollArea(self)
        self.phase_scroll.setWidgetResizable(True)
        self.phase_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.phase_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_content = QWidget(self.phase_scroll)
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(2, 2, 2, 2)
        self.scroll_layout.setSpacing(4)
        self.phase_scroll.setWidget(self.scroll_content)
        phase_box_layout.addWidget(self.phase_scroll)
        phase_box.setMinimumHeight(150)
        left_layout.addWidget(phase_box, 1)

        # 规则达成表格
        rule_box = QGroupBox("🔍 策略规则条件达成与挂单监控")
        rule_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #00ff88; background-color: #14141d; }")
        rule_box_layout = QVBoxLayout(rule_box)
        rule_box_layout.setContentsMargins(4, 8, 4, 4)

        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(5)
        self.table_rules.setHorizontalHeaderLabels(["规则名称", "目标触发条件", "卖出比例", "建议挂单价", "触发状态"])
        self.table_rules.setAlternatingRowColors(True)
        self.table_rules.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_rules.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #00ff88; font-weight: bold; padding: 3px; }")

        h_r = self.table_rules.horizontalHeader()
        h_r.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_r.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_r.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_r.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_r.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_rules.setColumnWidth(0, 130)
        self.table_rules.setColumnWidth(3, 85)
        rule_box_layout.addWidget(self.table_rules)
        rule_box.setMinimumHeight(150)
        left_layout.addWidget(rule_box, 1)

        # 7 节点动态评估速查表
        node_box = QGroupBox("🎯 7 节点动态时序打分速查 (通过实时 df 自动获取计算)")
        node_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_box_layout = QVBoxLayout(node_box)
        node_box_layout.setContentsMargins(4, 8, 4, 4)

        self.table_quick_nodes = QTableWidget()
        self.table_quick_nodes.setColumnCount(6)
        self.table_quick_nodes.setHorizontalHeaderLabels(["节点", "时间", "实时观察值", "信号判定", "评分(0-10)", "权重"])
        self.table_quick_nodes.setAlternatingRowColors(True)
        self.table_quick_nodes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_quick_nodes.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #ffd700; font-weight: bold; padding: 3px; }")

        h_q = self.table_quick_nodes.horizontalHeader()
        h_q.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_q.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        h_q.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_quick_nodes.setColumnWidth(4, 75)
        node_box_layout.addWidget(self.table_quick_nodes)
        node_box.setMinimumHeight(150)
        left_layout.addWidget(node_box, 1)

        self.main_splitter.addWidget(left_container)

        # ===== 右侧容器：SBC 实盘走势 + 买卖点触发明细 + 执行流水日志 =====
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # SBC 分时走势卡片
        sbc_box = QGroupBox("📊 SBC 实盘分时走势与关键阶梯基准线")
        sbc_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #00ff88; background-color: #14141d; }")
        sbc_box_layout = QVBoxLayout(sbc_box)
        sbc_box_layout.setContentsMargins(6, 8, 6, 6)

        self.txt_sbc_info = QTextEdit()
        self.txt_sbc_info.setReadOnly(True)
        self.txt_sbc_info.setStyleSheet("background-color: #0e0e14; color: #38bdf8; font-family: Consolas, Monospace; font-size: 9.5pt;")
        sbc_box_layout.addWidget(self.txt_sbc_info)
        sbc_box.setMinimumHeight(170)
        right_layout.addWidget(sbc_box, 1)

        # 买卖点明细表
        sig_box = QGroupBox("⚡ 策略执行买卖点明细 (实盘/模拟触发)")
        sig_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #ffaa44; background-color: #14141d; }")
        sig_box_layout = QVBoxLayout(sig_box)
        sig_box_layout.setContentsMargins(4, 8, 4, 4)

        self.table_signals = QTableWidget()
        self.table_signals.setColumnCount(5)
        self.table_signals.setHorizontalHeaderLabels(["时间", "买卖动作", "执行价", "卖出比例", "触发规则/理由"])
        self.table_signals.setAlternatingRowColors(True)
        self.table_signals.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_signals.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #ffaa44; font-weight: bold; padding: 3px; }")

        h_s = self.table_signals.horizontalHeader()
        h_s.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        sig_box_layout.addWidget(self.table_signals)
        sig_box.setMinimumHeight(140)
        right_layout.addWidget(sig_box, 1)

        # 路由日志
        log_box = QGroupBox("📋 策略路由与实盘指令流水日志")
        log_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        log_box_layout = QVBoxLayout(log_box)
        log_box_layout.setContentsMargins(4, 8, 4, 4)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #0e0e14; color: #00ff88; font-family: Consolas, Monospace; font-size: 9pt;")
        log_box_layout.addWidget(self.txt_log)
        log_box.setMinimumHeight(110)
        right_layout.addWidget(log_box, 1)

        self.main_splitter.addWidget(right_container)
        self.main_splitter.setSizes([600, 620])
        main_layout.addWidget(self.main_splitter, 1)

        self.phase_items = []
        self._last_strategy_id = None

    def _rebuild_phase_items(self, strategy: Dict[str, Any]):
        st_id = strategy.get("id") if isinstance(strategy, dict) else None
        if getattr(self, "_last_strategy_id", None) == st_id and self.phase_items:
            return
        self._last_strategy_id = st_id

        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        self.phase_items = []
        phases = strategy.get("phases", []) if isinstance(strategy, dict) else []

        if not phases:
            phase_defs = [
                ("09:15~09:25", "1️⃣ 集合竞价定盘段", "记录开盘价 Open，判定所属档位并锁定策略 (权重15%)"),
                ("09:30~10:00", "2️⃣ 开盘冲高卖出段", "冲高≥10%按价格笼子卖50%，10:00前未触发兜底卖30% (权重35%)"),
                ("10:00~15:00", "3️⃣ 临停复牌/持股观察段", "+30%临停复牌前挂1.28x卖30% / 回撤10%移动止盈 (权重25%)"),
                ("14:50~14:57", "4️⃣ 尾盘决策/清仓段", "收盘/最高>=90%且>=8分留10%底仓过夜，否则全部清仓 (权重25%)")
            ]
        else:
            num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
            phase_defs = []
            for idx, p in enumerate(phases):
                s_t = p.get("start_time", "")
                e_t = p.get("end_time", "")
                t_range = f"{s_t}~{e_t}" if (s_t and e_t) else p.get("phase_id", "")
                p_name = p.get("name", f"阶段 {idx+1}")
                emoji = num_emojis[idx] if idx < len(num_emojis) else f"{idx+1}️⃣"
                if not any(char in p_name for char in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]):
                    p_name = f"{emoji} {p_name}"
                p_desc = p.get("description", "")
                phase_defs.append((t_range, p_name, p_desc))

        for idx, (time_range, phase_title, phase_desc) in enumerate(phase_defs):
            p_box = QFrame(self.scroll_content)
            p_box.setObjectName("PhaseItemFrame")
            p_box.setMinimumHeight(44)
            p_box.setStyleSheet("QFrame#PhaseItemFrame { background-color: #14141c; border: 1px solid #22222d; border-radius: 4px; } QLabel { border: none; background: transparent; }")
            p_layout = QVBoxLayout(p_box)
            p_layout.setContentsMargins(6, 4, 6, 4)
            p_layout.setSpacing(2)

            h_lay = QHBoxLayout()
            h_lay.setContentsMargins(0, 0, 0, 0)

            lbl_time = QLabel(time_range)
            lbl_time.setStyleSheet("font-weight: bold; color: #ffaa44; font-size: 8.5pt;")
            lbl_title = QLabel(phase_title)
            lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 8.5pt;")
            lbl_status = QLabel("⏳ 待生效")
            lbl_status.setStyleSheet("font-weight: bold; color: #555566; font-size: 8pt;")

            h_lay.addWidget(lbl_time)
            h_lay.addWidget(lbl_title)
            h_lay.addStretch()
            h_lay.addWidget(lbl_status)

            lbl_sub = QLabel(phase_desc)
            lbl_sub.setStyleSheet("color: #8e8e9e; font-size: 8pt;")

            p_layout.addLayout(h_lay)
            p_layout.addWidget(lbl_sub)
            self.scroll_layout.addWidget(p_box)

            self.phase_items.append({
                "frame": p_box,
                "lbl_time": lbl_time,
                "lbl_title": lbl_title,
                "lbl_status": lbl_status,
                "lbl_desc": lbl_sub
            })

    def update_data(
        self,
        code: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float,
        turnover_rate: float,
        amount: float,
        bid1_price: float,
        current_time_str: str,
        strategy: Dict[str, Any],
        is_unlisted: bool = False
    ):
        """全面刷新一体化工作台数据"""
        self.code = code
        c_clean = str(code).zfill(6)

        # 1. 评估 7 节点动态打分与形态
        eval_res = self.engine.evaluate_seven_nodes(
            code=c_clean,
            current_time_str=current_time_str,
            open_price=open_price,
            price=price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap,
            turnover_rate=turnover_rate,
            amount=amount
        )

        tot_score = eval_res.get("total_weighted_score", 0.0)
        pattern = eval_res.get("pattern", "--")
        intensity_val = eval_res.get("intensity_ratio", 0.0)
        state = self.engine._get_stock_state(c_clean, open_price)
        rem_ratio = state.get("remaining_ratio", 1.0)
        signals = state.get("signals", [])
        logs = state.get("execution_logs", [])

        # 2. 顶部状态卡
        tier_name, strat_id, mode = self.engine.get_open_price_tier(open_price, code=c_clean)
        unlisted_str = " (待上市定盘)" if is_unlisted or open_price <= 0 else ""
        self.lbl_open_info.setText(f"开盘基准: {open_price:.2f}元{unlisted_str} | 所属档位: {tier_name} | 现价: {price:.2f}元 | VWAP: {vwap:.2f}元")
        self.lbl_strat_name.setText(f"当前策略: {strategy.get('name', '默认策略')}")
        self.lbl_score_badge.setText(
            f"🏆 综合评级: <font color='#00ff88'>{tot_score:.2f}分</font> (形态: <font color='#ffd700'>【{pattern}】</font>) | 资金强度: {intensity_val:.2f}x"
        )
        self.lbl_position_status.setText(
            f"📦 持仓状态: 剩余 <font color='#00ff88'>{rem_ratio*100:.0f}%</font> | 已触发: {len(signals)} 步买卖"
        )

        # 3. 实操指引
        self.lbl_diagnosis.setText(f"⏱️ [{current_time_str}] {eval_res.get('current_status_diagnosis', '')}")
        self.lbl_action.setText(eval_res.get("action_execution_text", ""))

        # 4. 时间轴策略阶段高亮
        self._rebuild_phase_items(strategy)
        clean_t = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        curr_phase, curr_phase_idx = self.engine.get_current_phase(clean_t, strategy)
        for idx, item in enumerate(self.phase_items):
            if idx == curr_phase_idx:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #1e2638; border: 2px solid #38bdf8; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("🔥 执行中")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #00ff88; font-size: 8pt;")
            elif idx < curr_phase_idx:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #161822; border: 1px solid #2a2a3a; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("✅ 已完成")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #8e8e93; font-size: 8pt;")
            else:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #12121a; border: 1px solid #20202c; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("⏳ 待生效")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #555566; font-size: 8pt;")

        # 5. 规则达成表格
        if curr_phase:
            rules = curr_phase.get("rules", [])
            triggered_rules = state.get("triggered_rules", set())
            self.table_rules.setRowCount(len(rules))
            for row, r in enumerate(rules):
                r_id = r.get("rule_id", "")
                r_name = r.get("name", r_id)
                r_ratio = f"{r.get('sell_ratio', 0.0)*100:.0f}%"

                if open_price > 0:
                    if r_id in ["rule_a1_surge", "rule_pz_surge_10"]:
                        target_str = f"≥ {open_price*1.10:.2f}元 (+10%)"
                        sugg_p = f"{round((bid1_price if bid1_price>0 else price)*1.02, 2):.2f}元"
                    elif r_id in ["rule_a2_halt_30", "rule_pz_halt_30"]:
                        target_str = f"最高 ≥ {open_price*1.30:.2f}元 (+30%)"
                        sugg_p = f"{round(open_price*1.28, 2):.2f}元"
                    else:
                        target_str = r.get("trigger_expr", "--")
                        sugg_p = f"{price:.2f}元(市价)"
                else:
                    target_str = r.get("trigger_expr", "--")
                    sugg_p = "--"

                status_str = "✅ 已触发卖出" if r_id in triggered_rules else "⏳ 监控中"
                status_color = QColor("#00ff88") if r_id in triggered_rules else QColor("#ffaa44")

                it_0 = QTableWidgetItem(r_name)
                it_1 = QTableWidgetItem(target_str)
                it_2 = QTableWidgetItem(r_ratio)
                it_2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_3 = QTableWidgetItem(sugg_p)
                it_3.setForeground(QColor("#ffd700"))
                it_4 = QTableWidgetItem(status_str)
                it_4.setForeground(status_color)

                self.table_rules.setItem(row, 0, it_0)
                self.table_rules.setItem(row, 1, it_1)
                self.table_rules.setItem(row, 2, it_2)
                self.table_rules.setItem(row, 3, it_3)
                self.table_rules.setItem(row, 4, it_4)
            self.table_rules.resizeRowsToContents()

        # 6. 7 节点动态打分速查表
        node_results = eval_res.get("node_results", [])
        self.table_quick_nodes.setRowCount(len(node_results))
        self._is_updating = True
        for row, nr in enumerate(node_results):
            it_n = QTableWidgetItem(nr["name"])
            it_t = QTableWidgetItem(nr["time_str"])
            it_o = QTableWidgetItem(nr["observed_val"])
            it_o.setToolTip(nr["observed_val"])
            it_j = QTableWidgetItem(nr["judgment"])
            it_j.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if nr["judgment"] == "强":
                it_j.setForeground(QColor("#00ff88"))
            elif nr["judgment"] == "中":
                it_j.setForeground(QColor("#38bdf8"))
            else:
                it_j.setForeground(QColor("#ff5555"))

            spin = self.table_quick_nodes.cellWidget(row, 4)
            if not isinstance(spin, QDoubleSpinBox):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 10.0)
                spin.setSingleStep(0.5)
                spin.setStyleSheet("background-color: #1e1e2d; color: #ffd700; font-weight: bold; border: 1px solid #38bdf8;")
                spin.valueChanged.connect(self._make_spin_handler(row, nr["node_id"]))
                self.table_quick_nodes.setCellWidget(row, 4, spin)

            spin.blockSignals(True)
            spin.setValue(float(nr["final_score"]))
            spin.blockSignals(False)

            it_w = QTableWidgetItem(nr["weight_pct"])
            it_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_quick_nodes.setItem(row, 0, it_n)
            self.table_quick_nodes.setItem(row, 1, it_t)
            self.table_quick_nodes.setItem(row, 2, it_o)
            self.table_quick_nodes.setItem(row, 3, it_j)
            self.table_quick_nodes.setItem(row, 5, it_w)
        self.table_quick_nodes.resizeRowsToContents()
        self._is_updating = False

        # 7. SBC 实盘走势与基准线
        max_p = state.get("max_price", price)
        min_p = state.get("min_price", price)
        sbc_text = (
            f"=== 📊 SBC 实盘分时走势与关键阶梯基准线 ===\n"
            f"【标的代码】: {code} ({resolve_stock_name(code)})\n"
            f"【开盘基准】: {open_price:.2f} 元 (基准参考线已锚定)\n"
            f"【实时成交】: {price:.2f} 元 (最高: {max_p:.2f}元 / 最低: {min_p:.2f}元)\n"
            f"【均价线 VWAP】: {vwap:.2f} 元 | 换手率: {turnover_rate:.1f}% | 成交额: {amount/1e8:.2f} 亿元\n"
            f"【冲高卖出目标 (+10%)】: {open_price*1.10:.2f} 元 (价格笼子限价卖出 50%)\n"
            f"【临停触发目标 (+30%)】: {open_price*1.30:.2f} 元 (复牌前挂单 1.28x={open_price*1.28:.2f} 卖出 30%)\n"
            f"【移动止盈清仓 (-10%)】: {max_p*0.90:.2f} 元 (高点回撤 10% 触发)\n"
            f"【当前持仓管理】: 剩余持仓比例 {rem_ratio*100:.0f}%\n"
        )
        self.txt_sbc_info.setText(sbc_text)

        # 8. 买卖点明细表
        self.table_signals.setRowCount(len(signals))
        for r, s in enumerate(signals):
            pct_str = f"{getattr(s, 'sell_ratio', 0.5)*100:.0f}%"
            sugg_p = getattr(s, 'suggested_price', s.price)
            it_t = QTableWidgetItem(s.timestamp)
            it_act = QTableWidgetItem("🔴 卖出")
            it_act.setForeground(QColor("#ff5555"))
            it_act.setFont(QFont("Arial", 8.5, QFont.Weight.Bold))
            it_p = QTableWidgetItem(f"{s.price:.2f}元 (挂单:{sugg_p:.2f})")
            it_p.setForeground(QColor("#ffd700"))
            it_rt = QTableWidgetItem(pct_str)
            it_rt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_rs = QTableWidgetItem(s.reason)
            it_rs.setToolTip(s.reason)

            self.table_signals.setItem(r, 0, it_t)
            self.table_signals.setItem(r, 1, it_act)
            self.table_signals.setItem(r, 2, it_p)
            self.table_signals.setItem(r, 3, it_rt)
            self.table_signals.setItem(r, 4, it_rs)
        self.table_signals.resizeRowsToContents()

        # 9. 路由日志
        if logs:
            self.txt_log.setText("\n".join(logs))

    def _make_spin_handler(self, row: int, node_id: str):
        def _handler(val: float):
            if not self._is_updating:
                self.engine.set_manual_node_score(self.code, node_id, val)
                self.manual_score_signal.emit()
        return _handler


class PinzhunLadderStandaloneWindow(QMainWindow):
    """
    频准激光 8/18 专属上市盯盘与分时阶梯交易策略独立主窗口
    具备完全独立的窗口生命周期、窗口置顶、最大化最小化、多屏支持与非模态异步更新能力
    """
    def __init__(self, code: Optional[str] = None, name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.selected_strategy_id: Optional[str] = None
        self._is_stay_on_top = False

        if isinstance(code, bool) or not code:
            json_codes = self.engine.get_all_target_codes()
            if json_codes:
                code = json_codes[0]
            elif parent and hasattr(parent, 'current_selected_code') and parent.current_selected_code:
                code = parent.current_selected_code
            elif parent and hasattr(parent, 'selected_code') and parent.selected_code:
                code = parent.selected_code
            else:
                code = "688826"

        self.code = "".join(filter(str.isdigit, str(code))).zfill(6)
        if isinstance(name, bool) or not name or name == "未知" or name == self.code:
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        # 独立窗口属性设置 (允许独立任务栏、独立最小化/最大化/关闭)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(f"⚡ 频准激光（{self.code} {self.name}）8/18 上市盯盘与分时阶梯交易独立系统")
        self.resize(1300, 900)
        self.setMinimumSize(1000, 700)

        # 🎨 全局应用 ATS 统一暗黑主题样式表模板 (QSS)
        apply_dark_theme(self)

        # 缓存最新接收到的 DataFrame
        self._latest_df: Optional[pd.DataFrame] = None

        self._init_ui()
        self._load_mock_or_live_data()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. 顶部 Header 控制栏
        hdr_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"📈 频准激光（{self.code} {self.name}）8/18 上市分时阶梯交易与动态评估工作台")
        self.title_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #38bdf8;")

        lbl_select = QLabel("🎯 目标标的:")
        lbl_select.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_code = QComboBox()
        self.combo_code.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #00ff88; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px; font-weight: bold; min-width: 220px; } QComboBox QAbstractItemView { background-color: #161622; color: #e0e0e0; selection-background-color: #007acc; }")
        self._populate_code_combo()
        self.combo_code.currentIndexChanged.connect(self._on_combo_code_changed)

        lbl_strat = QLabel("📋 动态策略:")
        lbl_strat.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_strategy = QComboBox()
        self.combo_strategy.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #ffaa44; border: 1px solid #ffaa44; border-radius: 4px; padding: 3px 8px; font-weight: bold; min-width: 220px; } QComboBox QAbstractItemView { background-color: #161622; color: #e0e0e0; selection-background-color: #007acc; }")
        self._populate_strategy_combo()
        self.combo_strategy.currentIndexChanged.connect(self._on_combo_strategy_changed)

        self.btn_topmost = QPushButton("📌 窗口置顶: 关")
        self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 4px 10px;")
        self.btn_topmost.clicked.connect(self._toggle_stay_on_top)

        btn_auto_eval = QPushButton("⚡ 全量 Code 检测")
        btn_auto_eval.setStyleSheet("background-color: #1e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 10px;")
        btn_auto_eval.clicked.connect(self._on_eval_all_codes)

        btn_edit = QPushButton("⚙️ 策略编辑")
        btn_edit.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 10px;")
        btn_edit.clicked.connect(self._on_open_editor)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; border-radius: 4px; padding: 4px 10px;")
        btn_close.clicked.connect(self.close)

        hdr_layout.addWidget(self.title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(lbl_select)
        hdr_layout.addWidget(self.combo_code)
        hdr_layout.addWidget(lbl_strat)
        hdr_layout.addWidget(self.combo_strategy)
        hdr_layout.addWidget(self.btn_topmost)
        hdr_layout.addWidget(btn_auto_eval)
        hdr_layout.addWidget(btn_edit)
        hdr_layout.addWidget(btn_close)
        layout.addLayout(hdr_layout)

        # 2. 中央 3 大 Tab 选项卡
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2a2a3a;
                background-color: #101017;
            }
            QTabBar::tab {
                background-color: #161622;
                color: #a0a0c0;
                font-weight: bold;
                padding: 7px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e2638;
                color: #00ff88;
                border-bottom: 2px solid #00ff88;
            }
        """)

        # Tab 1: 【核心主工作台】分时阶梯交易策略 & 7节点动态时序评估工作台
        self.integrated_panel = IntegratedTradingStrategyPanel(self)
        self.integrated_panel.manual_score_signal.connect(self._load_mock_or_live_data)
        self.tab_widget.addTab(self.integrated_panel, "⚡ 分时阶梯交易策略 & 7节点动态评估一体化工作台")

        # Tab 2: 8/18 开盘全天分时模拟回测与情景演练器
        self.sim_panel = IntradaySimulationWidget(self)
        self.sim_panel.tick_emitted_signal.connect(self._on_simulation_tick_emitted)
        self.tab_widget.addTab(self.sim_panel, "🎮 8/18 上市全天分时模拟回测与情景演练 (A/B/C/D型)")

        # Tab 3: 频准激光 8/18 专属盯盘模板 & 综合评分明细汇总
        self.pinzhun_monitor_panel = PinzhunLaserMonitorWidget(self)
        self.pinzhun_monitor_panel.score_changed_signal.connect(self._load_mock_or_live_data)
        self.tab_widget.addTab(self.pinzhun_monitor_panel, "📋 频准激光 8/18 盯盘模板 & 综合评分明细汇总")

        layout.addWidget(self.tab_widget, 1)

        # 3. 定时刷新 Timer (秒级自动推进)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick_update)
        self.timer.start()

    def _toggle_stay_on_top(self):
        """切换窗口置顶状态"""
        self._is_stay_on_top = not self._is_stay_on_top
        if self._is_stay_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.btn_topmost.setText("📌 窗口置顶: 开")
            self.btn_topmost.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 4px 10px;")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.btn_topmost.setText("📌 窗口置顶: 关")
            self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 4px 10px;")
        self.show()

    def on_realtime_df_update(self, df: Optional[pd.DataFrame]):
        """接收来自 ATS 主窗口或独立 IPC 数据流的实时行情推送"""
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            self._latest_df = df
            self._load_mock_or_live_data()

    def _populate_code_combo(self):
        self.combo_code.blockSignals(True)
        self.combo_code.clear()

        all_target_codes = self.engine.get_all_target_codes()
        parent = self.parent()

        code_list = list(all_target_codes)
        if self.code and self.code not in code_list:
            code_list.insert(0, self.code)

        for c in code_list:
            st = self.engine.auto_select_strategy(0.0, code=c)
            st_name = st.get("name", "默认策略")
            c_name = self.name if c == self.code else resolve_stock_name(c)
            if parent and hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c)
                if p_name and p_name != "未知" and p_name != c:
                    c_name = p_name

            item_text = f"{c} {c_name} [{st_name}]"
            self.combo_code.addItem(item_text, c)

        for idx in range(self.combo_code.count()):
            if self.combo_code.itemData(idx) == self.code:
                self.combo_code.setCurrentIndex(idx)
                break
        self.combo_code.blockSignals(False)

    def _populate_strategy_combo(self):
        self.combo_strategy.blockSignals(True)
        self.combo_strategy.clear()

        self.combo_strategy.addItem("⚡ 【自动匹配】按开盘价/TargetCode", "auto")
        for st in self.engine.strategies:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            self.combo_strategy.addItem(f"📋 {st_name}", st_id)

        target_id = self.selected_strategy_id or "auto"
        for idx in range(self.combo_strategy.count()):
            if self.combo_strategy.itemData(idx) == target_id:
                self.combo_strategy.setCurrentIndex(idx)
                break
        self.combo_strategy.blockSignals(False)

    def _on_combo_strategy_changed(self, index: int):
        selected_strat_id = self.combo_strategy.itemData(index)
        if selected_strat_id == "auto":
            self.selected_strategy_id = None
        else:
            self.selected_strategy_id = selected_strat_id
        self._load_mock_or_live_data()

    def _on_combo_code_changed(self, index: int):
        selected_code = self.combo_code.itemData(index)
        if selected_code and selected_code != self.code:
            self.code = selected_code
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)

            self.setWindowTitle(f"⚡ 频准激光（{self.code} {self.name}）8/18 上市盯盘与分时阶梯交易独立系统")
            auto_st = self.engine.auto_select_strategy(self.open_price if hasattr(self, 'open_price') else 0.0, code=self.code)
            if auto_st:
                self.selected_strategy_id = auto_st.get("id")
                self._populate_strategy_combo()

            self._load_mock_or_live_data()

    def _on_simulation_tick_emitted(self, tick_data: Dict[str, Any]):
        """处理模拟回放发出的 Tick 数据，联动刷新 Tab 1 和 Tab 3"""
        p = float(tick_data.get("trade", tick_data.get("close", 0.0)))
        open_p = float(tick_data.get("open", p))
        h_p = float(tick_data.get("high", p))
        l_p = float(tick_data.get("low", p))
        vwap_p = float(tick_data.get("vwap", p))
        to_rate = float(tick_data.get("turnover", 0.0))
        amt = float(tick_data.get("amount", 0.0))
        b1_p = float(tick_data.get("buy", p))
        t_str = tick_data.get("time", "09:30")

        self.open_price = open_p
        strategy = self.engine.auto_select_strategy(open_p, code=self.code)

        # 评估阶梯交易信号
        tick_row = {"trade": p, "close": p}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=open_p,
            current_time_str=t_str,
            bid1_price=b1_p
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=open_p,
            price=p,
            high_price=h_p,
            low_price=l_p,
            vwap=vwap_p,
            turnover_rate=to_rate,
            amount=amt,
            bid1_price=b1_p,
            current_time_str=t_str,
            strategy=strategy,
            is_unlisted=False
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=open_p,
            price=p,
            high_price=h_p,
            low_price=l_p,
            vwap=vwap_p,
            turnover_rate=to_rate,
            amount=amt,
            current_time_str=t_str
        )

    def _on_eval_all_codes(self):
        target_codes = self.engine.get_all_target_codes()
        if not target_codes:
            QMessageBox.information(self, "提示", "未指定 target_codes 目标代码。")
            return

        now_time_str = datetime.now().strftime("%H:%M:%S")
        res_summary = f"=== ⚡ 全量 Code 分时阶梯策略自动检测评估报告 ({now_time_str}) ===\n\n"

        for c in target_codes:
            st = self.engine.auto_select_strategy(0.0, code=c)
            c_name = resolve_stock_name(c)
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c)
                if p_name and p_name != "未知" and p_name != c:
                    c_name = p_name

            open_p, trade_p, high_p, low_p, vwap_p, to_rate, amt_val, bid1_p, _, is_unlisted = self._get_stock_realtime_data_for_code(c)
            tick_row = {"trade": trade_p, "close": trade_p}
            sigs = self.engine.evaluate_tick(
                code=c, tick_row=tick_row, open_price=open_p, current_time_str=now_time_str, bid1_price=bid1_p
            )
            eval_res = self.engine.evaluate_seven_nodes(
                code=c, current_time_str=now_time_str, open_price=open_p, price=trade_p, high_price=high_p,
                low_price=low_price, vwap=vwap_p, turnover_rate=to_rate, amount=amt_val
            )

            res_summary += f"📌 【{c} {c_name}】 -> 策略: {st.get('name', '未知')}\n"
            res_summary += f"   开盘: {open_p:.2f}元 | 现价: {trade_p:.2f}元 | 综合得分: {eval_res.get('total_weighted_score', 0):.2f}分 ({eval_res.get('pattern', '--')})\n"
            res_summary += f"   实操指引: {eval_res.get('action_execution_text', '')}\n"
            for sig in sigs:
                res_summary += f"   🔴 {sig.reason} (建议价: {getattr(sig, 'suggested_price', sig.price):.2f})\n"
            res_summary += "--------------------------------------------------\n"

        QMessageBox.information(self, "⚡ 全量 Code 分时策略自动检测", res_summary)

    def _get_stock_realtime_data_for_code(self, code_str: str) -> Tuple[float, float, float, float, float, float, float, float, str, bool]:
        """全自动从 self._latest_df、parent.current_df 或行情快照解析全量字段"""
        c_clean = str(code_str).zfill(6)
        curr_df = self._latest_df
        parent = self.parent()
        if curr_df is None and parent is not None and hasattr(parent, 'current_df') and parent.current_df is not None:
            curr_df = parent.current_df

        snap = self.engine.extract_market_snapshot_from_df(curr_df, c_clean)
        open_price = snap["open_price"]
        trade_price = snap["price"]
        high_price = snap["high_price"]
        low_price = snap["low_price"]
        vwap_price = snap["vwap"]
        turnover_rate = snap["turnover_rate"]
        amount_val = snap["amount"]
        bid1_price = snap["bid1_price"]
        resolved_name = resolve_stock_name(c_clean)
        is_unlisted = False

        if parent and hasattr(parent, 'get_stock_name'):
            p_name = parent.get_stock_name(c_clean)
            if p_name and p_name != "未知" and p_name != c_clean:
                resolved_name = p_name

        if open_price <= 0 and trade_price <= 0:
            is_unlisted = True
            open_price = 565.0
            trade_price = 625.0
            high_price = 638.0
            low_price = 560.0
            turnover_rate = 62.5
            amount_val = 36.5 * 1e8
            bid1_price = 624.5
            vwap_price = 612.0
        elif open_price <= 0 and trade_price > 0:
            open_price = trade_price
            high_price = max(high_price, trade_price)
            low_price = min(low_price, trade_price) if low_price > 0 else trade_price
            vwap_price = trade_price if vwap_price <= 0 else vwap_price

        return open_price, trade_price, high_price, low_price, vwap_price, turnover_rate, amount_val, bid1_price, resolved_name, is_unlisted

    def _get_stock_realtime_data(self):
        return self._get_stock_realtime_data_for_code(self.code)

    def _on_open_editor(self):
        dlg = IntradayStrategyEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.load_config()
            self._populate_code_combo()
            self._load_mock_or_live_data()

    def _load_mock_or_live_data(self):
        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        self.title_lbl.setText(f"📈 频准激光（{self.code} {self.name}）8/18 上市分时阶梯交易与动态评估工作台")

        now_time_str = datetime.now().strftime("%H:%M:%S")

        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)

        tick_row = {"trade": trade_price, "close": trade_price}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=now_time_str,
            bid1_price=bid1_price if bid1_price > 0 else trade_price
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            bid1_price=bid1_price,
            current_time_str=now_time_str,
            strategy=strategy,
            is_unlisted=is_unlisted
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            current_time_str=now_time_str
        )

    def _on_tick_update(self):
        # 若正在进行模拟回放，则不被真实时钟覆盖
        if hasattr(self, 'sim_panel') and self.sim_panel.replay_timer.isActive():
            return

        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        now_str = datetime.now().strftime("%H:%M:%S")
        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)

        tick_row = {"trade": trade_price, "close": trade_price}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=now_str,
            bid1_price=bid1_price if bid1_price > 0 else trade_price
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            bid1_price=bid1_price,
            current_time_str=now_str,
            strategy=strategy,
            is_unlisted=is_unlisted
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            current_time_str=now_str
        )


# 向后兼容别名
IntradayStrategyDialog = PinzhunLadderStandaloneWindow


# 补充 PinzhunLaserMonitorWidget 类的定义供 Tab 3 使用
class PinzhunLaserMonitorWidget(QWidget):
    """
    频准激光（688826）8/18 上市盯盘与动态评分实操看板组件 (Tab 3)
    全自动由实时推送的 df 获取换手率、成交量、成交额、最高最低价并自动填表打分
    """
    score_changed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.code = "688826"
        self._is_updating = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(8)

        # 1. 🔑 关键阈值速查与量能档位面板
        card_spec = QGroupBox("🔑 关键阈值速查（发行价 186.88 元 | 首日流通≈761.78万股 | 流通市值≈14.24亿 | 中签率 0.02014%）")
        card_spec.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        spec_layout = QGridLayout(card_spec)
        spec_layout.setContentsMargins(10, 14, 10, 8)
        spec_layout.setSpacing(8)

        lbl_l1 = QLabel("<b>+100%</b>: 373.76元 (翻倍)")
        lbl_l1.setStyleSheet("color: #00ff88; font-size: 9.5pt;")
        lbl_l2 = QLabel("<b>+200%</b>: 560.64元 (强势基准)")
        lbl_l2.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 9.5pt;")
        lbl_l3 = QLabel("<b>+300%</b>: 747.52元 (高频发区间)")
        lbl_l3.setStyleSheet("color: #ffaa44; font-size: 9.5pt;")
        lbl_l4 = QLabel("<b>+400%</b>: 934.40元 (强势上限)")
        lbl_l4.setStyleSheet("color: #ff5555; font-size: 9.5pt;")
        lbl_l5 = QLabel("<b>+500%</b>: 1121.28元 (极端行情)")
        lbl_l5.setStyleSheet("color: #ff00ff; font-size: 9.5pt;")

        spec_layout.addWidget(lbl_l1, 0, 0)
        spec_layout.addWidget(lbl_l2, 0, 1)
        spec_layout.addWidget(lbl_l3, 0, 2)
        spec_layout.addWidget(lbl_l4, 0, 3)
        spec_layout.addWidget(lbl_l5, 0, 4)

        lbl_t1 = QLabel("<b>换手档位</b>: 弱(<40%) | 标准(50-70%健康) | 高(70-90%充分) | 极高(>90%过热)")
        lbl_t1.setStyleSheet("color: #a0a0c0; font-size: 9pt;")
        self.lbl_intensity = QLabel("<b>资金强度</b>: 成交额/流通市值(14.24亿) > 2.5x 为极强 [当前: --]")
        self.lbl_intensity.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 9pt;")

        spec_layout.addWidget(lbl_t1, 1, 0, 1, 3)
        spec_layout.addWidget(self.lbl_intensity, 1, 3, 1, 2)
        content_layout.addWidget(card_spec)

        # 2. 🎯 七节点实盘观察表
        node_group = QGroupBox("🎯 七节点实盘观察表（通过推送 df 自动解析换手率、成交量与价格，自动填表打分）")
        node_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_layout = QVBoxLayout(node_group)
        node_layout.setContentsMargins(6, 14, 6, 6)

        top_bar = QHBoxLayout()
        lbl_hint = QLabel("⚡ 全自动模式：数据 100% 由实时行情 df 自动摄入计算（换手/量能/VWAP/锁仓比）；您也可在【节点评分】列手动微调分值。")
        lbl_hint.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        
        btn_reset_scores = QPushButton("🔄 重置为自动打分")
        btn_reset_scores.setStyleSheet("background-color: #242436; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px 8px;")
        btn_reset_scores.clicked.connect(self._on_reset_scores)

        top_bar.addWidget(lbl_hint)
        top_bar.addStretch()
        top_bar.addWidget(btn_reset_scores)
        node_layout.addLayout(top_bar)

        self.table_nodes = QTableWidget()
        self.table_nodes.setColumnCount(9)
        self.table_nodes.setHorizontalHeaderLabels([
            "#", "时间节点", "观察项目", "强势信号（打✓）", "风险信号（打✓）",
            "实际观察值\n(实时df自动获取)", "信号判定\n强/中/弱", "节点评分\n(0-10分)", "备注/应对"
        ])
        self.table_nodes.setAlternatingRowColors(True)
        self.table_nodes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_nodes.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1a1a26; color: #ffd700; font-weight: bold; padding: 4px; border: 1px solid #2a2a38; }")
        
        h_header = self.table_nodes.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        self.table_nodes.setColumnWidth(1, 95)
        self.table_nodes.setColumnWidth(2, 95)
        self.table_nodes.setColumnWidth(5, 150)
        self.table_nodes.setColumnWidth(7, 85)
        self.table_nodes.setMinimumHeight(240)

        node_layout.addWidget(self.table_nodes)
        content_layout.addWidget(node_group)

        # 3. 📋 综合评分汇总与形态判定
        summary_group = QGroupBox("📋 综合评分汇总（自动计算加权得分、形态分类与 T+1 操作建议）")
        summary_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(6, 14, 6, 6)

        self.table_summary = QTableWidget()
        self.table_summary.setColumnCount(9)
        self.table_summary.setHorizontalHeaderLabels([
            "评分项", "时间", "节点分(0-10)", "权重", "加权得分",
            "首日涨幅", "换手率", "收盘/最高价", "形态分类"
        ])
        self.table_summary.setAlternatingRowColors(True)
        self.table_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_summary.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1e2638; color: #38bdf8; font-weight: bold; padding: 4px; border: 1px solid #2a2a38; }")
        
        sum_header = self.table_summary.horizontalHeader()
        sum_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_summary.setMinimumHeight(280)

        summary_layout.addWidget(self.table_summary)
        content_layout.addWidget(summary_group)

        # 4. 📝 实盘盯盘使用说明
        guide_group = QGroupBox("📝 实盘盯盘使用说明与应对规则（7条核心法则）")
        guide_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 4px; font-weight: bold; color: #a0a0d0; background-color: #14141d; }")
        guide_layout = QVBoxLayout(guide_group)
        guide_layout.setContentsMargins(8, 12, 8, 8)

        guide_txt = (
            "1. <b>节点观察</b>: 每个时间节点到达时，系统自动从实时 df 抓取价格/涨幅/换手/量能/VWAP；<br>"
            "2. <b>信号判定</b>: 自动判定 \"强\" / \"中\" / \"弱\" 并高亮呈现；<br>"
            "3. <b>节点评分</b>: 强=8-10分，中=5-7分，弱=0-4分；<br>"
            "4. <b>加权得分</b>: 自动计算 (加权得分 = 节点分 × 权重)；<br>"
            "5. <b>形态判定</b>: <b>综合得分≥8.0</b> → A型超强趋势(★关注竞价接力)；<b>6.5-8.0</b> → B型(★观察回踩)；<b>5.0-6.5</b> → C型(★谨慎)；<b><5.0</b> → D/E型(★回避)；<br>"
            "6. <b>重点监控</b>: <b>成交额/流通市值(14.24亿) > 2.5x 为极强</b>；<b>收盘/最高 > 90% 为超强锁仓</b>；<br>"
            "7. <b>同板块联动</b>: 同步观察半导体设备与激光板块龙头走势，确认资金协同性。"
        )
        lbl_guide = QLabel(guide_txt)
        lbl_guide.setTextFormat(Qt.TextFormat.RichText)
        lbl_guide.setStyleSheet("color: #b0b0c8; font-size: 8.5pt; line-height: 140%;")
        lbl_guide.setWordWrap(True)
        guide_layout.addWidget(lbl_guide)
        content_layout.addWidget(guide_group)

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

    def _on_reset_scores(self):
        state = self.engine._get_stock_state(self.code, 0.0)
        state["manual_scores"].clear()
        self.score_changed_signal.emit()

    def update_monitor_data(
        self,
        code: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float,
        turnover_rate: float,
        amount: float,
        current_time_str: str
    ):
        """全面刷新盯盘看板数据"""
        self.code = code
        res = self.engine.evaluate_seven_nodes(
            code=code,
            current_time_str=current_time_str,
            open_price=open_price,
            price=price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap,
            turnover_rate=turnover_rate,
            amount=amount
        )

        intensity_val = res.get("intensity_ratio", 0.0)
        int_str = f"{intensity_val:.2f}x"
        int_color = "#00ff88" if intensity_val >= 2.5 else "#38bdf8"
        self.lbl_intensity.setText(
            f"<b>资金强度</b>: 成交额/流通市值(14.24亿) > 2.5x 为极强 [当前: <font color='{int_color}'>{int_str}</font>]"
        )

        node_results = res.get("node_results", [])
        self.table_nodes.setRowCount(len(node_results))
        self._is_updating = True

        for row, nr in enumerate(node_results):
            n_id = nr["node_id"]
            it_0 = QTableWidgetItem(nr["node_num"])
            it_0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_nodes.setItem(row, 0, it_0)

            it_1 = QTableWidgetItem(f"{nr['name']}\n({nr['time_str']})")
            it_1.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if nr["is_active"]:
                it_1.setForeground(QColor("#00ff88"))
                it_1.setBackground(QColor("#1a2e24"))
            elif nr["is_completed"]:
                it_1.setForeground(QColor("#888899"))
            self.table_nodes.setItem(row, 1, it_1)

            it_2 = QTableWidgetItem(nr["focus"])
            it_2.setToolTip(nr["focus"])
            self.table_nodes.setItem(row, 2, it_2)

            it_3 = QTableWidgetItem(nr["strong_signals"])
            it_3.setToolTip(nr["strong_signals"])
            it_3.setForeground(QColor("#00ff88"))
            self.table_nodes.setItem(row, 3, it_3)

            it_4 = QTableWidgetItem(nr["risk_signals"])
            it_4.setToolTip(nr["risk_signals"])
            it_4.setForeground(QColor("#ff5555"))
            self.table_nodes.setItem(row, 4, it_4)

            it_5 = QTableWidgetItem(nr["observed_val"])
            it_5.setToolTip(nr["observed_val"])
            it_5.setForeground(QColor("#ffd700"))
            self.table_nodes.setItem(row, 5, it_5)

            judg = nr["judgment"]
            it_6 = QTableWidgetItem(judg)
            it_6.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if judg == "强":
                it_6.setForeground(QColor("#00ff88"))
                it_6.setBackground(QColor("#163322"))
            elif judg == "中":
                it_6.setForeground(QColor("#38bdf8"))
                it_6.setBackground(QColor("#162838"))
            else:
                it_6.setForeground(QColor("#ff4444"))
                it_6.setBackground(QColor("#331616"))
            self.table_nodes.setItem(row, 6, it_6)

            spin = self.table_nodes.cellWidget(row, 7)
            if not isinstance(spin, QDoubleSpinBox):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 10.0)
                spin.setSingleStep(0.5)
                spin.setStyleSheet("background-color: #1e1e2d; color: #ffd700; font-weight: bold; border: 1px solid #38bdf8;")
                spin.valueChanged.connect(self._make_spin_handler(row, n_id))
                self.table_nodes.setCellWidget(row, 7, spin)

            spin.blockSignals(True)
            spin.setValue(float(nr["final_score"]))
            spin.blockSignals(False)

            it_8 = QTableWidgetItem(f"{nr['remarks']} | {nr['action_guide']}")
            it_8.setToolTip(it_8.text())
            self.table_nodes.setItem(row, 8, it_8)

        self.table_nodes.resizeRowsToContents()

        self.table_summary.setRowCount(10)
        tot_score = res.get("total_weighted_score", 0.0)
        pattern = res.get("pattern", "--")
        t1_advice = res.get("t1_advice", "--")
        pat_color = res.get("pattern_color", "#00ff88")

        for row, nr in enumerate(node_results):
            it_name = QTableWidgetItem(f"{nr['name']}({nr['time_str']})")
            it_time = QTableWidgetItem(nr["time_str"])
            it_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_score = QTableWidgetItem(f"{nr['final_score']:.1f}")
            it_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_weight = QTableWidgetItem(nr["weight_pct"])
            it_weight.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_weight.setForeground(QColor("#38bdf8"))
            it_wscore = QTableWidgetItem(f"{nr['weighted_score']:.2f}")
            it_wscore.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_summary.setItem(row, 0, it_name)
            self.table_summary.setItem(row, 1, it_time)
            self.table_summary.setItem(row, 2, it_score)
            self.table_summary.setItem(row, 3, it_weight)
            self.table_summary.setItem(row, 4, it_wscore)

            if row == 0:
                it_gain = QTableWidgetItem(f"{res.get('gain_from_issue', 0.0):+.1f}%")
                it_gain.setForeground(QColor("#00ff88"))
                it_to = QTableWidgetItem(f"{res.get('turnover_rate', 0.0):.1f}%")
                it_ch = QTableWidgetItem(f"{res.get('close_high_ratio', 1.0)*100:.1f}%")
                it_pat = QTableWidgetItem(pattern)
                it_pat.setForeground(QColor(pat_color))
                it_pat.setFont(QFont("Arial", 9, QFont.Weight.Bold))

                self.table_summary.setItem(row, 5, it_gain)
                self.table_summary.setItem(row, 6, it_to)
                self.table_summary.setItem(row, 7, it_ch)
                self.table_summary.setItem(row, 8, it_pat)
            else:
                for c in range(5, 9):
                    self.table_summary.setItem(row, c, QTableWidgetItem(""))

        r_sum = 7
        it_sum_lbl = QTableWidgetItem("综合得分")
        it_sum_lbl.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        it_sum_lbl.setForeground(QColor("#38bdf8"))
        it_sum_t = QTableWidgetItem("合计")
        it_sum_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sum_pct = QTableWidgetItem("100%")
        it_sum_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sum_pct.setForeground(QColor("#38bdf8"))
        it_sum_val = QTableWidgetItem(f"{tot_score:.2f}")
        it_sum_val.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sum_val.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        it_sum_val.setForeground(QColor("#ff0055" if tot_score < 5 else ("#00ff88" if tot_score >= 8 else "#ffd700")))
        it_sum_val.setBackground(QColor("#2d2218"))

        self.table_summary.setItem(r_sum, 0, it_sum_lbl)
        self.table_summary.setItem(r_sum, 1, it_sum_t)
        self.table_summary.setItem(r_sum, 2, QTableWidgetItem(""))
        self.table_summary.setItem(r_sum, 3, it_sum_pct)
        self.table_summary.setItem(r_sum, 4, it_sum_val)
        for c in range(5, 9):
            self.table_summary.setItem(r_sum, c, QTableWidgetItem(""))

        r_pat = 8
        it_p_lbl = QTableWidgetItem("形态判定")
        it_p_lbl.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        it_p_val = QTableWidgetItem(f"【{pattern}】")
        it_p_val.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        it_p_val.setForeground(QColor(pat_color))
        it_p_val.setBackground(QColor("#22182d"))

        self.table_summary.setItem(r_pat, 0, it_p_lbl)
        self.table_summary.setItem(r_pat, 8, it_p_val)
        for c in range(1, 8):
            self.table_summary.setItem(r_pat, c, QTableWidgetItem(""))

        r_t1 = 9
        it_t1_lbl = QTableWidgetItem("T+1建议")
        it_t1_lbl.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        it_t1_val = QTableWidgetItem(t1_advice)
        it_t1_val.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        it_t1_val.setForeground(QColor(pat_color))

        self.table_summary.setItem(r_t1, 0, it_t1_lbl)
        self.table_summary.setItem(r_t1, 8, it_t1_val)
        for c in range(1, 8):
            self.table_summary.setItem(r_t1, c, QTableWidgetItem(""))

        self.table_summary.resizeRowsToContents()
        self._is_updating = False

    def _make_spin_handler(self, row: int, node_id: str):
        def _handler(val: float):
            if not self._is_updating:
                self.engine.set_manual_node_score(self.code, node_id, val)
                self.score_changed_signal.emit()
        return _handler


class IntradaySimulationWidget(QWidget):
    """
    8/18 开盘实盘全天分时模拟回测与情景演练面板 (Tab 2)
    支持 A/B/C/D 4大情景、一键秒级全天回测与分时动态逐帧回放
    """
    tick_emitted_signal = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.sim_df: Optional[pd.DataFrame] = None
        self.current_frame_idx = 0
        self.replay_timer = QTimer(self)
        self.replay_timer.timeout.connect(self._on_replay_step)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 1. 顶部情景选择与操作控制栏
        ctrl_group = QGroupBox("🎮 8/18 开盘分时模拟情景演练与全天回测控制")
        ctrl_group.setStyleSheet("QGroupBox { border: 1px solid #38bdf8; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setContentsMargins(10, 14, 10, 10)
        ctrl_layout.setSpacing(10)

        lbl_sc = QLabel("🎯 演练情景:")
        lbl_sc.setStyleSheet("color: #ffd700; font-weight: bold;")
        self.combo_scenario = QComboBox()
        self.combo_scenario.setStyleSheet("background-color: #1e1e2d; color: #00ff88; font-weight: bold; min-width: 320px; padding: 4px;")
        self.combo_scenario.addItem("🚀 情景1: A型·超强主升主线 (+210%高开 -> 冲高 -> +30%临停 -> 815元锁仓)", "A_SUPER_TREND")
        self.combo_scenario.addItem("📈 情景2: B型·强势换手洗盘 (+162%高开 -> 冲高 -> 均线强承接 -> 540元健康收盘)", "B_STRONG_TURNOVER")
        self.combo_scenario.addItem("📉 情景3: C型·冲高兑现回落 (+108%开盘 -> 冲高卖出50% -> 破均线兑现 -> 355元回落)", "C_SURGE_AND_CASH")
        self.combo_scenario.addItem("⚠️ 情景4: D/E型·高开低走衰竭 (+125%开盘 -> 放量砸盘破位 -> 阴跌跳水 -> 310元清仓)", "D_WEAK_EXHAUSTION")

        btn_run_full = QPushButton("⚡ 一键全天秒级回测")
        btn_run_full.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 5px 14px; border-radius: 4px;")
        btn_run_full.clicked.connect(self._on_run_full_backtest)

        self.btn_play = QPushButton("▶️ 分时动态逐帧回放")
        self.btn_play.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 5px 14px; border-radius: 4px;")
        self.btn_play.clicked.connect(self._on_toggle_play)

        btn_reset = QPushButton("⏮️ 重置")
        btn_reset.setStyleSheet("background-color: #333344; color: white; padding: 5px 12px; border-radius: 4px;")
        btn_reset.clicked.connect(self._on_reset_replay)

        lbl_spd = QLabel("速度:")
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["5x 快速", "10x 极速", "1x 真实", "20x 飞速"])
        self.combo_speed.setStyleSheet("background-color: #1e1e2d; color: #e0e0e0;")

        ctrl_layout.addWidget(lbl_sc)
        ctrl_layout.addWidget(self.combo_scenario)
        ctrl_layout.addWidget(btn_run_full)
        ctrl_layout.addWidget(self.btn_play)
        ctrl_layout.addWidget(btn_reset)
        ctrl_layout.addWidget(lbl_spd)
        ctrl_layout.addWidget(self.combo_speed)
        ctrl_layout.addStretch()

        layout.addWidget(ctrl_group)

        # 2. 进度条与当前回放状态
        prog_box = QHBoxLayout()
        self.lbl_replay_status = QLabel("⏱️ 回放进度: 0 / 241 分钟 (待开始)")
        self.lbl_replay_status.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 9.5pt;")
        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setRange(0, 241)
        self.slider_progress.setValue(0)
        self.slider_progress.sliderMoved.connect(self._on_slider_moved)
        self.slider_progress.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #252535; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #00ff88; border-radius: 3px; }
            QSlider::handle:horizontal { background: #ffd700; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
        """)

        prog_box.addWidget(self.lbl_replay_status)
        prog_box.addWidget(self.slider_progress, 1)
        layout.addLayout(prog_box)

        # 3. 回测结果总览卡片与阶梯指令流水 Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：回测报告与评分演进
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.txt_backtest_report = QTextEdit()
        self.txt_backtest_report.setReadOnly(True)
        self.txt_backtest_report.setStyleSheet("background-color: #0e0e14; color: #38bdf8; font-family: Consolas, Monospace; font-size: 9.5pt;")
        left_layout.addWidget(QLabel("📊 8/18 模拟回测总览与评分诊断报告:"))
        left_layout.addWidget(self.txt_backtest_report)
        splitter.addWidget(left_widget)

        # 右侧：买卖点阶梯信号流水
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.table_sim_signals = QTableWidget()
        self.table_sim_signals.setColumnCount(5)
        self.table_sim_signals.setHorizontalHeaderLabels(["时间", "买卖动作", "执行价", "卖出比例", "触发规则/理由"])
        self.table_sim_signals.setAlternatingRowColors(True)
        self.table_sim_signals.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_sim_signals.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1a1a26; color: #00ff88; font-weight: bold; padding: 4px; }")
        
        h_h = self.table_sim_signals.horizontalHeader()
        h_h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        right_layout.addWidget(QLabel("⚡ 阶梯交易买卖点触发明细与实盘挂单流水:"))
        right_layout.addWidget(self.table_sim_signals)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 650])
        layout.addWidget(splitter, 1)

    def _ensure_scenario_df(self):
        sc_type = self.combo_scenario.currentData()
        if self.sim_df is None or getattr(self, "_last_sc_type", None) != sc_type:
            self.sim_df = self.engine.generate_scenario_intraday_df(sc_type, code="688826")
            self._last_sc_type = sc_type
            self.slider_progress.setMaximum(len(self.sim_df) - 1)
        return self.sim_df

    def _on_run_full_backtest(self):
        """一键全天秒级回测"""
        df = self._ensure_scenario_df()
        res = self.engine.run_full_day_backtest("688826", df)

        final_eval = res.get("final_evaluation", {})
        sigs = res.get("signals", [])
        logs = res.get("execution_logs", [])
        rem_ratio = res.get("remaining_ratio", 0.0)

        report = (
            f"=== ⚡ 频准激光（688826）8/18 全天分时模拟回测报告 ===\n"
            f"【情景选择】: {self.combo_scenario.currentText()}\n"
            f"【开盘基准】: {res.get('open_price', 0):.2f} 元 | 发行价: 186.88 元\n"
            f"【收盘价格】: {final_eval.get('price', 0):.2f} 元 (较开盘 {final_eval.get('gain_from_open', 0):+.1f}% | 较发行价 {final_eval.get('gain_from_issue', 0):+.1f}%)\n"
            f"【全天最高】: {final_eval.get('high_price', 0):.2f} 元 | 最低: {final_eval.get('low_price', 0):.2f} 元 | VWAP均价: {final_eval.get('vwap', 0):.2f} 元\n"
            f"【全天换手】: {final_eval.get('turnover_rate', 0):.1f}% | 成交金额: {final_eval.get('amount_yi', 0):.2f} 亿元\n"
            f"【资金强度】: {final_eval.get('intensity_ratio', 0):.2f}x (流通市值14.24亿) | 锁仓比例: {final_eval.get('close_high_ratio', 1)*100:.1f}%\n"
            f"--------------------------------------------------\n"
            f"【🏆 15:00 最终综合评分】: {final_eval.get('total_weighted_score', 0):.2f} 分 (满分10分)\n"
            f"【🎯 最终形态分类】: 【{final_eval.get('pattern', '--')}】\n"
            f"【💡 次日 T+1 操作建议】: {final_eval.get('t1_advice', '--')}\n"
            f"【📦 持仓管理状态】: 剩余持仓比例 {rem_ratio*100:.0f}%\n"
            f"--------------------------------------------------\n"
            f"【📋 实操执行诊断】:\n{final_eval.get('action_execution_text', '')}\n"
        )
        self.txt_backtest_report.setText(report)

        # 填充买卖点表格
        self.table_sim_signals.setRowCount(len(sigs))
        for r, s in enumerate(sigs):
            pct_str = f"{getattr(s, 'sell_ratio', 0.5)*100:.0f}%"
            sugg_p = getattr(s, 'suggested_price', s.price)
            it_t = QTableWidgetItem(s.timestamp)
            it_act = QTableWidgetItem("🔴 卖出")
            it_act.setForeground(QColor("#ff5555"))
            it_act.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            it_p = QTableWidgetItem(f"{s.price:.2f}元 (挂单:{sugg_p:.2f})")
            it_p.setForeground(QColor("#ffd700"))
            it_rt = QTableWidgetItem(pct_str)
            it_rt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_rs = QTableWidgetItem(s.reason)
            it_rs.setToolTip(s.reason)

            self.table_sim_signals.setItem(r, 0, it_t)
            self.table_sim_signals.setItem(r, 1, it_act)
            self.table_sim_signals.setItem(r, 2, it_p)
            self.table_sim_signals.setItem(r, 3, it_rt)
            self.table_sim_signals.setItem(r, 4, it_rs)

        self.table_sim_signals.resizeRowsToContents()
        self.current_frame_idx = len(df) - 1
        self.slider_progress.setValue(self.current_frame_idx)
        self.lbl_replay_status.setText(f"⏱️ 回测完成: 241 / 241 分钟 (15:00 收盘)")

    def _on_toggle_play(self):
        if self.replay_timer.isActive():
            self.replay_timer.stop()
            self.btn_play.setText("▶️ 继续回放")
            self.btn_play.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; padding: 5px 14px;")
        else:
            self._ensure_scenario_df()
            spd_text = self.combo_speed.currentText()
            interval = 50 if "20x" in spd_text else (100 if "10x" in spd_text else (200 if "5x" in spd_text else 800))
            self.replay_timer.setInterval(interval)
            self.replay_timer.start()
            self.btn_play.setText("⏸️ 暂停回放")
            self.btn_play.setStyleSheet("background-color: #3a2e1e; color: #ffd700; font-weight: bold; padding: 5px 14px;")

    def _on_reset_replay(self):
        self.replay_timer.stop()
        self.current_frame_idx = 0
        self.slider_progress.setValue(0)
        self.btn_play.setText("▶️ 分时动态逐帧回放")
        self.lbl_replay_status.setText("⏱️ 回放进度: 0 / 241 分钟 (已重置)")
        self.engine.reset_state("688826")
        self.table_sim_signals.setRowCount(0)
        self.txt_backtest_report.clear()

    def _on_slider_moved(self, val):
        self.current_frame_idx = val
        self._render_frame(val)

    def _on_replay_step(self):
        df = self._ensure_scenario_df()
        if self.current_frame_idx >= len(df):
            self.replay_timer.stop()
            self.btn_play.setText("▶️ 重新回放")
            self.lbl_replay_status.setText("⏱️ 全天回放完毕 (15:00)")
            return

        self._render_frame(self.current_frame_idx)
        self.current_frame_idx += 1
        self.slider_progress.setValue(self.current_frame_idx)

    def _render_frame(self, frame_idx: int):
        df = self._ensure_scenario_df()
        if frame_idx >= len(df):
            return
        row = df.iloc[frame_idx]
        t_str = row["time"]
        self.lbl_replay_status.setText(f"⏱️ 回放时间: {t_str} ({frame_idx+1}/{len(df)} 分钟) | 价格: {row['close']:.2f}元")
        self.tick_emitted_signal.emit(row.to_dict())


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    engine = IntradayStrategyEngine.get_instance()
    default_code = engine.get_default_target_code() or "688826"
    win = PinzhunLadderStandaloneWindow(code=default_code)
    win.show()
    sys.exit(app.exec())
