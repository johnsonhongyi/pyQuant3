# -*- coding: utf-8 -*-
"""
ats/ui/intraday_strategy_dialog.py — ATS 单独分时交易策略、SBC 实盘显示与时间轴动态策略段面板
包含：
1. TimeAxisPhasePanel: 随时间显示需执行的策略段、开盘定盘速查卡、规则达成状态与路由日志；
   支持 Vertical QSplitter 手动调大小、QScrollArea 滚轮查看阶段卡片并聚焦当前策略段，表格防挤压全展示。
2. IntradayStrategyEditDialog: 图形化/JSON 策略自定制编辑器；
3. IntradayStrategyDialog: 集成时间轴看板、SBC 实盘走势与买卖点标记的主对话框（支持多 code 绑定与实时价格跟随）。
"""

import sys
import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 兼容开发模式单独运行子脚本（防重复挂载，打包运行下 if 为 False 不会污染 sys.path）
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CUR_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QTextEdit, QComboBox, QMessageBox, QFrame, QGridLayout, QProgressBar,
    QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush

from sys_utils import resolve_stock_name
from ats.intraday_strategy_engine import IntradayStrategyEngine
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyDialog")

class TimeAxisPhasePanel(QWidget):
    """时间轴动态策略段看板组件（支持 Vertical Splitter 拖拽与 QScrollArea 滚轮查看）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 垂直分划板：允许用户手动调整“时间轴策略段”、“规则达成状态”与“路由日志”3大窗口的高度
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(6)
        self.v_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #252535;
                height: 6px;
            }
            QSplitter::handle:hover {
                background-color: #38bdf8;
            }
        """)

        # ===== 1. 顶部组合容器：开盘定盘速查卡 + 盘中时间轴策略段 (含 QScrollArea 滚轮查看) =====
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        # (1) 开盘定盘速查卡
        card_group = QGroupBox("📌 开盘定盘速查与策略分配")
        card_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 6px;
                font-weight: bold;
                color: #38bdf8;
                background-color: #16161f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        card_layout = QGridLayout(card_group)
        card_layout.setContentsMargins(10, 12, 10, 8)
        card_layout.setSpacing(6)

        self.lbl_open_price = QLabel("开盘价: -- 元")
        self.lbl_open_price.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #ffd700; border: none; background: transparent;")
        
        self.lbl_tier = QLabel("对应档位: --")
        self.lbl_tier.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #00ff88; border: none; background: transparent;")

        self.lbl_strategy_name = QLabel("当前策略: --")
        self.lbl_strategy_name.setStyleSheet("font-size: 10pt; font-weight: bold; color: #aad4ff; border: none; background: transparent;")

        self.lbl_current_time = QLabel("盘中时间: --")
        self.lbl_current_time.setStyleSheet("font-size: 10pt; font-weight: bold; color: #e0e0e0; border: none; background: transparent;")

        card_layout.addWidget(self.lbl_open_price, 0, 0)
        card_layout.addWidget(self.lbl_tier, 0, 1)
        card_layout.addWidget(self.lbl_strategy_name, 1, 0, 1, 2)
        card_layout.addWidget(self.lbl_current_time, 2, 0, 1, 2)

        top_layout.addWidget(card_group)

        # (2) 4大策略段滚轮可查看区域
        phase_group = QGroupBox("⏳ 盘中时间轴策略段 (动态阶段指示)")
        phase_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 6px;
                font-weight: bold;
                color: #aad4ff;
                background-color: #16161f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        phase_group_layout = QVBoxLayout(phase_group)
        phase_group_layout.setContentsMargins(4, 12, 4, 4)

        # QScrollArea 容器
        self.phase_scroll = QScrollArea(self)
        self.phase_scroll.setWidgetResizable(True)
        self.phase_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.phase_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.scroll_content = QWidget(self.phase_scroll)
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(4, 2, 4, 4)
        self.scroll_layout.setSpacing(6)

        self.phase_scroll.setWidget(self.scroll_content)
        phase_group_layout.addWidget(self.phase_scroll)

        top_layout.addWidget(phase_group, 1)
        self.v_splitter.addWidget(top_container)

        # ===== 2. 规则细节与达成状态表格 (可手动拖拽 Splitter 放大调整) =====
        rule_group = QGroupBox("🔍 当前策略段规则条件达成状态")
        rule_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 6px;
                font-weight: bold;
                color: #00ff88;
                background-color: #16161f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        rule_layout = QVBoxLayout(rule_group)
        rule_layout.setContentsMargins(6, 12, 6, 6)

        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(4)
        self.table_rules.setHorizontalHeaderLabels(["规则名称", "目标触发条件", "卖出比例", "触发状态"])
        self.table_rules.setWordWrap(True)
        self.table_rules.setAlternatingRowColors(True)
        self.table_rules.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_rules.setStyleSheet("""
            QTableWidget {
                background-color: #121218;
                gridline-color: #252535;
                color: #d0d0e0;
                font-size: 9pt;
            }
            QHeaderView::section {
                background-color: #1b1b26;
                color: #38bdf8;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #2a2a38;
            }
        """)

        header = self.table_rules.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(65)
        self.table_rules.setColumnWidth(0, 160)
        self.table_rules.setColumnWidth(2, 75)
        self.table_rules.setColumnWidth(3, 95)

        rule_layout.addWidget(self.table_rules)
        self.v_splitter.addWidget(rule_group)

        # ===== 3. 路由日志与执行输出 =====
        log_group = QGroupBox("📋 策略路由实盘指令与日志")
        log_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 6px;
                font-weight: bold;
                color: #ffaa44;
                background-color: #16161f;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 12, 6, 6)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #0e0e14; color: #00ff88; font-family: Consolas, Monospace; font-size: 9pt;")
        log_layout.addWidget(self.txt_log)

        self.v_splitter.addWidget(log_group)

        # 设置 3 大区域初始拉伸比例 [时间轴阶段, 规则表格, 日志输出]
        self.v_splitter.setSizes([290, 220, 130])
        main_layout.addWidget(self.v_splitter, 1)

        self.phase_items = []
        self._last_strategy_id = None

    def _rebuild_phase_items(self, strategy: Dict[str, Any]):
        """根据当前 Strategy 动态渲染左侧盘中时间轴策略段"""
        st_id = strategy.get("id") if isinstance(strategy, dict) else None
        if getattr(self, "_last_strategy_id", None) == st_id and self.phase_items:
            return

        self._last_strategy_id = st_id

        # 清空原有 widget
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
                ("09:15~09:25", "1️⃣ 集合竞价定盘段", "记录开盘价 Open，判定所属档位并锁定策略"),
                ("09:30~10:00", "2️⃣ 开盘冲高卖出段", "冲高≥10%(或5%)卖50%，10:00前未触发兜底卖30%"),
                ("10:00~15:00", "3️⃣ 临停复牌/持股观察段", "+30%临停复牌卖30% / +60%临停复牌卖33%"),
                ("14:50~14:57", "4️⃣ 尾盘清仓段", "按买一价市价清仓剩余全部(如>20%可留10%过夜)")
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
            p_box.setMinimumHeight(56)
            p_box.setStyleSheet("""
                QFrame#PhaseItemFrame {
                    background-color: #14141c;
                    border: 1px solid #22222d;
                    border-radius: 5px;
                }
                QLabel {
                    border: none;
                    background: transparent;
                }
            """)
            p_layout = QVBoxLayout(p_box)
            p_layout.setContentsMargins(8, 6, 8, 6)
            p_layout.setSpacing(4)

            h_lay = QHBoxLayout()
            h_lay.setContentsMargins(0, 0, 0, 0)
            h_lay.setSpacing(8)

            lbl_time = QLabel(time_range)
            lbl_time.setStyleSheet("font-weight: bold; color: #ffaa44; font-size: 9.5pt; border: none; background: transparent;")
            
            lbl_title = QLabel(phase_title)
            lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 9.5pt; border: none; background: transparent;")
            
            lbl_status = QLabel("⏳ 待生效")
            lbl_status.setStyleSheet("font-weight: bold; color: #555566; font-size: 9pt; border: none; background: transparent;")

            h_lay.addWidget(lbl_time)
            h_lay.addWidget(lbl_title)
            h_lay.addStretch()
            h_lay.addWidget(lbl_status)

            lbl_sub = QLabel(phase_desc)
            lbl_sub.setWordWrap(True)
            lbl_sub.setStyleSheet("color: #9a9ab0; font-size: 8.5pt; border: none; background: transparent;")

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

    def update_status(
        self,
        code: str,
        open_price: float,
        current_time_str: str,
        strategy: Dict[str, Any],
        engine: IntradayStrategyEngine,
        is_unlisted: bool = False
    ):
        """更新时间轴看板与规则状态"""
        self._rebuild_phase_items(strategy)
        c_clean = str(code).zfill(6)
        tier_name, strat_id, mode = engine.get_open_price_tier(open_price)
        
        if is_unlisted or open_price <= 0:
            self.lbl_open_price.setText("开盘价: -- 元 (待上市/挂牌定盘)")
            self.lbl_tier.setText("对应档位: 待上市定盘")
        else:
            self.lbl_open_price.setText(f"开盘价: {open_price:.2f} 元")
            self.lbl_tier.setText(f"对应档位: {tier_name}")
            
        self.lbl_strategy_name.setText(f"当前策略: {strategy.get('name', '未选择')}")
        self.lbl_current_time.setText(f"盘中时间: {current_time_str}")

        clean_t = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        # 1. 动态更新时间轴阶段高亮并自动滚轮聚焦当前策略段
        curr_phase, curr_phase_idx = engine.get_current_phase(clean_t, strategy)
        for idx, item in enumerate(self.phase_items):
            if idx == curr_phase_idx:
                item["frame"].setStyleSheet("""
                    QFrame#PhaseItemFrame {
                        background-color: #1e2638;
                        border: 2px solid #38bdf8;
                        border-radius: 6px;
                    }
                    QLabel { border: none; background: transparent; }
                """)
                item["lbl_status"].setText("🔥 执行中")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #00ff88; font-size: 9pt; border: none; background: transparent;")
            elif idx < curr_phase_idx:
                item["frame"].setStyleSheet("""
                    QFrame#PhaseItemFrame {
                        background-color: #161822;
                        border: 1px solid #2a2a3a;
                        border-radius: 5px;
                    }
                    QLabel { border: none; background: transparent; }
                """)
                item["lbl_status"].setText("✅ 已完成")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #8e8e93; font-size: 9pt; border: none; background: transparent;")
            else:
                item["frame"].setStyleSheet("""
                    QFrame#PhaseItemFrame {
                        background-color: #12121a;
                        border: 1px solid #20202c;
                        border-radius: 5px;
                    }
                    QLabel { border: none; background: transparent; }
                """)
                item["lbl_status"].setText("⏳ 待生效")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #555566; font-size: 9pt; border: none; background: transparent;")

        # 自动滚轮平滑移至当前“执行中”策略段
        if 0 <= curr_phase_idx < len(self.phase_items):
            self.phase_scroll.ensureWidgetVisible(self.phase_items[curr_phase_idx]["frame"])

        # 2. 更新当前阶段规则列表与适应表格行高 (防挤压截断)
        if curr_phase:
            rules = curr_phase.get("rules", [])
            state = engine._get_stock_state(c_clean, open_price)
            triggered_rules = state.get("triggered_rules", set())

            self.table_rules.setRowCount(len(rules))
            for row, r in enumerate(rules):
                r_id = r.get("rule_id", "")
                r_name = r.get("name", r_id)
                r_ratio = f"{r.get('sell_ratio', 0.0)*100:.0f}%"

                # 计算目标表达
                if open_price > 0:
                    if r_id == "rule_a1_surge":
                        target_str = f"≥ {open_price*1.10:.2f}元 (+10%)"
                    elif r_id == "rule_a1_surge_decelerated":
                        target_str = f"≥ {open_price*1.05:.2f}元 (+5%)"
                    elif r_id == "rule_a2_halt_30":
                        target_str = f"最高 ≥ {open_price*1.30:.2f}元 (+30%临停)"
                    elif r_id == "rule_b1_surge":
                        target_str = f"≥ {open_price*1.08:.2f}元 (+8%)"
                    elif r_id == "rule_b2_halt_60":
                        target_str = f"最高 ≥ {open_price*1.60:.2f}元 (+60%临停)"
                    else:
                        target_str = r.get("trigger_expr", "--")
                else:
                    target_str = r.get("trigger_expr", "--")

                if r_id in triggered_rules:
                    status_str = "✅ 已触发卖出"
                    status_color = QColor("#00ff88")
                else:
                    status_str = "⏳ 监控中"
                    status_color = QColor("#ffaa44")

                item_0 = QTableWidgetItem(r_name)
                item_0.setToolTip(r_name)
                
                item_1 = QTableWidgetItem(target_str)
                item_1.setToolTip(target_str)

                item_2 = QTableWidgetItem(r_ratio)
                item_2.setToolTip(r_ratio)

                item_st = QTableWidgetItem(status_str)
                item_st.setForeground(status_color)
                item_st.setToolTip(status_str)

                self.table_rules.setItem(row, 0, item_0)
                self.table_rules.setItem(row, 1, item_1)
                self.table_rules.setItem(row, 2, item_2)
                self.table_rules.setItem(row, 3, item_st)

            self.table_rules.resizeRowsToContents()

            # 更新日志窗口
            logs = state.get("execution_logs", [])
            if logs:
                self.txt_log.setText("\n".join(logs))


class IntradayStrategyEditDialog(QDialog):
    """自定制策略编辑器弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 自定制分时交易策略 JSON 编辑器")
        self.resize(750, 550)
        self.engine = IntradayStrategyEngine.get_instance()
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

        # 加载现有 JSON
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


class IntradayStrategyDialog(QDialog):
    """ATS 单独分时交易策略与 SBC 实盘显示主窗口（支持 JSON 配置多 code 绑定、自动路由与实时价格跟随）"""
    def __init__(self, code: Optional[str] = None, name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.selected_strategy_id: Optional[str] = None

        # 动态解析股票代码与名称（绝对防死锁硬编码）
        if isinstance(code, bool) or not code:
            json_codes = self.engine.get_all_target_codes()
            if json_codes:
                code = json_codes[0]
            elif parent and hasattr(parent, 'current_selected_code') and parent.current_selected_code:
                code = parent.current_selected_code
            elif parent and hasattr(parent, 'selected_code') and parent.selected_code:
                code = parent.selected_code
            else:
                code = "000001"

        self.code = "".join(filter(str.isdigit, str(code))).zfill(6)
        if isinstance(name, bool) or not name or name == "未知" or name == self.code:
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        self.setWindowTitle(f"⚡ ATS 单独分时阶梯交易策略 & SBC 实盘 - {self.code} {self.name}")
        self.resize(1120, 780)
        self.setMinimumSize(850, 580)

        self._init_ui()
        self._load_mock_or_live_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 1. 顶部 Header (展示当前 Code 与 名称 + 动态股票/策略选择器 + 操作按钮)
        hdr_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"📈 阶梯交易策略 & SBC 实盘监控 ({self.code} {self.name})")
        self.title_lbl.setStyleSheet("font-size: 12.5pt; font-weight: bold; color: #38bdf8;")

        # 多 Code 动态选择下拉框
        lbl_select = QLabel("🎯 目标标的:")
        lbl_select.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_code = QComboBox()
        self.combo_code.setStyleSheet("""
            QComboBox {
                background-color: #1e1e2d;
                color: #00ff88;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                min-width: 220px;
            }
            QComboBox QAbstractItemView {
                background-color: #161622;
                color: #e0e0e0;
                selection-background-color: #007acc;
            }
        """)
        self._populate_code_combo()
        self.combo_code.currentIndexChanged.connect(self._on_combo_code_changed)

        # 动态策略选择下拉框
        lbl_strat = QLabel("📋 动态策略:")
        lbl_strat.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_strategy = QComboBox()
        self.combo_strategy.setStyleSheet("""
            QComboBox {
                background-color: #1e1e2d;
                color: #ffaa44;
                border: 1px solid #ffaa44;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                min-width: 220px;
            }
            QComboBox QAbstractItemView {
                background-color: #161622;
                color: #e0e0e0;
                selection-background-color: #007acc;
            }
        """)
        self._populate_strategy_combo()
        self.combo_strategy.currentIndexChanged.connect(self._on_combo_strategy_changed)

        btn_auto_eval = QPushButton("⚡ 全量 Code 自动检测")
        btn_auto_eval.setStyleSheet("background-color: #1e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; padding: 4px 10px;")
        btn_auto_eval.clicked.connect(self._on_eval_all_codes)

        btn_edit = QPushButton("⚙️ 自定制策略编辑")
        btn_edit.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; padding: 4px 10px;")
        btn_edit.clicked.connect(self._on_open_editor)

        btn_close = QPushButton("关闭窗口")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; padding: 4px 10px;")
        btn_close.clicked.connect(self.close)

        hdr_layout.addWidget(self.title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(lbl_select)
        hdr_layout.addWidget(self.combo_code)
        hdr_layout.addWidget(lbl_strat)
        hdr_layout.addWidget(self.combo_strategy)
        hdr_layout.addWidget(btn_auto_eval)
        hdr_layout.addWidget(btn_edit)
        hdr_layout.addWidget(btn_close)
        layout.addLayout(hdr_layout)

        # 2. 中央 Splitter (左侧时间轴动态策略段看板, 右侧 SBC 实盘分时)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.phase_panel = TimeAxisPhasePanel(self)
        self.main_splitter.addWidget(self.phase_panel)

        # 右侧 SBC 分时显示与买卖点视图容器
        self.sbc_container = QWidget()
        sbc_layout = QVBoxLayout(self.sbc_container)
        sbc_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_sbc_title = QLabel(f"📊 SBC 实盘分时走势与策略买卖点 ({self.code} {self.name})")
        self.lbl_sbc_title.setStyleSheet("font-weight: bold; color: #00ff88; padding: 4px;")
        sbc_layout.addWidget(self.lbl_sbc_title)

        self.txt_sbc_placeholder = QTextEdit()
        self.txt_sbc_placeholder.setReadOnly(True)
        self.txt_sbc_placeholder.setStyleSheet("background-color: #101015; color: #38bdf8; font-family: Consolas, Monospace; font-size: 10pt;")
        sbc_layout.addWidget(self.txt_sbc_placeholder)

        self.main_splitter.addWidget(self.sbc_container)
        self.main_splitter.setSizes([460, 660])

        layout.addWidget(self.main_splitter, 1)

        # 3. 定时刷新 Timer (1秒刷新)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick_update)
        self.timer.start()

    def _populate_code_combo(self):
        """填充下拉框股票代码选项（整合 JSON 配置中的 target_codes 与当前 selected_code）"""
        self.combo_code.blockSignals(True)
        self.combo_code.clear()

        all_target_codes = self.engine.get_all_target_codes()
        parent = self.parent()

        # 确保当前 code 在列表中
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

        # 选中当前代码
        for idx in range(self.combo_code.count()):
            if self.combo_code.itemData(idx) == self.code:
                self.combo_code.setCurrentIndex(idx)
                break
        self.combo_code.blockSignals(False)

    def _populate_strategy_combo(self):
        """填充策略下拉框选项（自动匹配 + JSON 中的全量策略）"""
        self.combo_strategy.blockSignals(True)
        self.combo_strategy.clear()

        # 0. 自动匹配选项
        self.combo_strategy.addItem("⚡ 【自动匹配】按开盘价/TargetCode", "auto")

        for st in self.engine.strategies:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            self.combo_strategy.addItem(f"📋 {st_name}", st_id)

        # 选中当前 selected_strategy_id 或 自动匹配
        target_id = self.selected_strategy_id or "auto"
        for idx in range(self.combo_strategy.count()):
            if self.combo_strategy.itemData(idx) == target_id:
                self.combo_strategy.setCurrentIndex(idx)
                break
        self.combo_strategy.blockSignals(False)

    def _on_combo_strategy_changed(self, index: int):
        """策略下拉框切换触发更新"""
        selected_strat_id = self.combo_strategy.itemData(index)
        if selected_strat_id == "auto":
            self.selected_strategy_id = None
        else:
            self.selected_strategy_id = selected_strat_id
        
        self._load_mock_or_live_data()

    def _on_combo_code_changed(self, index: int):
        """下拉框切换代码触发更新"""
        selected_code = self.combo_code.itemData(index)
        if selected_code and selected_code != self.code:
            self.code = selected_code
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)

            self.setWindowTitle(f"⚡ ATS 单独分时阶梯交易策略 & SBC 实盘 - {self.code} {self.name}")
            
            # 代码切换时重新自动定位对应的策略并同步下拉框
            auto_st = self.engine.auto_select_strategy(self.open_price if hasattr(self, 'open_price') else 0.0, code=self.code)
            if auto_st:
                self.selected_strategy_id = auto_st.get("id")
                self._populate_strategy_combo()

            self._load_mock_or_live_data()

    def _on_eval_all_codes(self):
        """全量 Code 自动检测并运行策略结果总览"""
        target_codes = self.engine.get_all_target_codes()
        if not target_codes:
            QMessageBox.information(self, "提示", "JSON 策略配置中未指定 target_codes 专属目标代码，当前将按通用开盘价规则路由。")
            return

        now_time_str = datetime.now().strftime("%H:%M:%S")
        res_summary = f"=== ⚡ 全量 Code 分时策略自动检测评估报告 ({now_time_str}) ===\n\n"

        for c in target_codes:
            st = self.engine.auto_select_strategy(0.0, code=c)
            c_name = resolve_stock_name(c)
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c)
                if p_name and p_name != "未知" and p_name != c:
                    c_name = p_name

            open_p, trade_p, bid1_p, _, is_unlisted = self._get_stock_realtime_data_for_code(c)
            tick_row = {"trade": trade_p, "close": trade_p}
            sigs = self.engine.evaluate_tick(
                code=c, tick_row=tick_row, open_price=open_p, current_time_str=now_time_str, bid1_price=bid1_p
            )

            res_summary += f"📌 【{c} {c_name}】 -> 策略: {st.get('name', '未知')}\n"
            res_summary += f"   开盘价: {open_p:.2f}元 | 实时价: {trade_p:.2f}元 | 信号点数: {len(sigs)} 个\n"
            for sig in sigs:
                res_summary += f"   🔴 {sig.reason} (建议价: {getattr(sig, 'suggested_price', sig.price):.2f})\n"
            res_summary += "--------------------------------------------------\n"

        QMessageBox.information(self, "⚡ 全量 Code 分时策略自动检测", res_summary)

    def _get_stock_realtime_data_for_code(self, code_str: str) -> Tuple[float, float, float, str, bool]:
        """获取指定 Code 的实时/模拟行情数据"""
        c_clean = str(code_str).zfill(6)
        open_price, trade_price, bid1_price = 0.0, 0.0, 0.0
        resolved_name = resolve_stock_name(c_clean)
        is_unlisted = False

        parent = self.parent()
        if parent is not None:
            if hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c_clean)
                if p_name and p_name != "未知" and p_name != c_clean:
                    resolved_name = p_name

            if hasattr(parent, 'current_df') and parent.current_df is not None and not parent.current_df.empty:
                row = None
                if hasattr(parent, 'get_df_row_safe'):
                    row = parent.get_df_row_safe(parent.current_df, c_clean)
                elif c_clean in parent.current_df.index:
                    row = parent.current_df.loc[c_clean]

                if row is not None:
                    try:
                        open_price = float(row.get('open', row.get('open_price', 0.0)))
                        trade_price = float(row.get('close', row.get('trade', 0.0)))
                        bid1_price = float(row.get('buy', row.get('bid1', trade_price)))
                    except Exception:
                        pass

            if trade_price <= 0 and hasattr(parent, 'price_pct_cache') and c_clean in parent.price_pct_cache:
                p_tuple = parent.price_pct_cache[c_clean]
                if isinstance(p_tuple, (tuple, list)) and len(p_tuple) > 0:
                    trade_price = float(p_tuple[0])

        if open_price <= 0 and trade_price <= 0:
            is_unlisted = True
            open_price = 350.0
            trade_price = 386.0
        elif open_price <= 0 and trade_price > 0:
            open_price = trade_price

        return open_price, trade_price, bid1_price, resolved_name, is_unlisted

    def _get_stock_realtime_data(self) -> Tuple[float, float, float, str, bool]:
        """获取当前 Code 的真实/实时行情数据"""
        return self._get_stock_realtime_data_for_code(self.code)

    def _on_open_editor(self):
        dlg = IntradayStrategyEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.load_config()
            self._populate_code_combo()
            self._load_mock_or_live_data()

    def _load_mock_or_live_data(self):
        """加载初始或实盘行情数据并匹配策略"""
        open_price, trade_price, bid1_price, real_name, is_unlisted = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        self.title_lbl.setText(f"📈 阶梯交易策略 & SBC 实盘监控 ({self.code} {self.name})")
        self.lbl_sbc_title.setText(f"📊 SBC 实盘分时走势与策略买卖点 ({self.code} {self.name})")

        now_time_str = datetime.now().strftime("%H:%M:%S")

        # 优先采用用户手动选中的策略，未选择则自动匹配
        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)
        self.phase_panel.update_status(self.code, self.open_price, now_time_str, strategy, self.engine, is_unlisted=is_unlisted)

        # 触发一次评估
        tick_row = {"trade": trade_price, "close": trade_price}
        signals = self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=now_time_str,
            bid1_price=bid1_price if bid1_price > 0 else trade_price
        )

        unlisted_tag = " (未上市/挂牌定盘)" if is_unlisted else ""
        sbc_info = (
            f"=== ⚡ SBC 分时走势与买卖点可视化信息 ===\n"
            f"股票代码: {self.code} ({self.name}){unlisted_tag}\n"
            f"开盘基准价 (Open): {self.open_price:.2f} 元 (基准参考线已绘制)\n"
            f"实时触发价 (Price): {trade_price:.2f} 元\n"
            f"冲高卖出目标 (+10%): {self.open_price*1.10:.2f} 元\n"
            f"临停参考线 (+30%): {self.open_price*1.30:.2f} 元 (挂单 1.28x={self.open_price*1.28:.2f})\n"
            f"应用策略: {strategy.get('name', '默认策略')}\n"
            f"--------------------------------------------------\n"
            f"捕获策略触发买卖点数: {len(signals)} 个\n"
        )
        for sig in signals:
            sbc_info += (
                f"  🔴 [SELL 卖出信号] BarIndex: {sig.bar_index} | 触发价: {sig.price:.2f}\n"
                f"     原因: {sig.reason}\n"
                f"     卖出比例: {getattr(sig, 'sell_ratio', 0.5)*100:.0f}%\n"
                f"     价格笼子挂单买一价*1.02: {getattr(sig, 'suggested_price', sig.price):.2f} 元\n"
            )
        self.txt_sbc_placeholder.setText(sbc_info)

    def _on_tick_update(self):
        """定时刷新界面与策略推算（实时跟随 code 价格变动）"""
        open_price, trade_price, bid1_price, real_name, is_unlisted = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        now_str = datetime.now().strftime("%H:%M:%S")
        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)
        self.phase_panel.update_status(self.code, self.open_price, now_str, strategy, self.engine, is_unlisted=is_unlisted)

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    engine = IntradayStrategyEngine.get_instance()
    default_code = engine.get_default_target_code() or "688826"
    dlg = IntradayStrategyDialog(code=default_code)
    dlg.show()
    sys.exit(app.exec())
