# -*- coding: utf-8 -*-
"""
ats/ui/intraday_strategy_dialog.py — ATS 单独分时交易策略、SBC 实盘显示与时间轴动态策略段面板
包含：
1. TimeAxisPhasePanel: 随时间显示需执行的策略段、开盘定盘速查卡、规则达成状态与路由日志；
2. IntradayStrategyEditDialog: 图形化/JSON 策略自定制编辑器；
3. IntradayStrategyDialog: 集成时间轴看板、SBC 实盘走势与买卖点标记的主对话框。
"""

import sys
import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QTextEdit, QComboBox, QMessageBox, QFrame, QGridLayout, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush

from ats.intraday_strategy_engine import IntradayStrategyEngine
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyDialog")

class TimeAxisPhasePanel(QWidget):
    """时间轴动态策略段看板组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 1. 顶部开盘价定盘速查卡
        card_group = QGroupBox("📌 开盘定盘速查与策略分配")
        card_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 8px;
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
        card_layout.setContentsMargins(10, 15, 10, 10)
        card_layout.setSpacing(6)

        self.lbl_open_price = QLabel("开盘价: -- 元")
        self.lbl_open_price.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ffd700; border: none; background: transparent;")
        
        self.lbl_tier = QLabel("对应档位: --")
        self.lbl_tier.setStyleSheet("font-size: 11pt; font-weight: bold; color: #00ff88; border: none; background: transparent;")

        self.lbl_strategy_name = QLabel("当前策略: --")
        self.lbl_strategy_name.setStyleSheet("font-size: 10pt; font-weight: bold; color: #aad4ff; border: none; background: transparent;")

        self.lbl_current_time = QLabel("盘中时间: --")
        self.lbl_current_time.setStyleSheet("font-size: 10pt; font-weight: bold; color: #e0e0e0; border: none; background: transparent;")

        card_layout.addWidget(self.lbl_open_price, 0, 0)
        card_layout.addWidget(self.lbl_tier, 0, 1)
        card_layout.addWidget(self.lbl_strategy_name, 1, 0, 1, 2)
        card_layout.addWidget(self.lbl_current_time, 2, 0, 1, 2)

        layout.addWidget(card_group)

        # 2. 随时间推移指示的 4 大策略段 Progress / Phase List
        phase_group = QGroupBox("⏳ 盘中时间轴策略段 (动态阶段指示)")
        phase_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 8px;
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
        phase_layout = QVBoxLayout(phase_group)
        phase_layout.setContentsMargins(8, 14, 8, 8)
        phase_layout.setSpacing(6)

        self.phase_items = []
        phase_defs = [
            ("09:15~09:25", "1️⃣ 集合竞价定盘段", "记录开盘价 Open，判定所属档位并锁定策略"),
            ("09:30~10:00", "2️⃣ 开盘冲高卖出段", "冲高≥10%(或5%)卖50%，10:00前未触发兜底卖30%"),
            ("10:00~15:00", "3️⃣ 临停复牌/持股观察段", "+30%临停复牌卖30% / +60%临停复牌卖33%"),
            ("14:50~14:57", "4️⃣ 尾盘清仓段", "按买一价市价清仓剩余全部(如>20%可留10%过夜)")
        ]

        for idx, (time_range, phase_title, phase_desc) in enumerate(phase_defs):
            p_box = QFrame()
            p_box.setObjectName("PhaseItemFrame")
            p_box.setMinimumHeight(62)
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
            lbl_time.setStyleSheet("font-weight: bold; color: #ffaa44; font-size: 10pt; border: none; background: transparent;")
            
            lbl_title = QLabel(phase_title)
            lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 10pt; border: none; background: transparent;")
            
            lbl_status = QLabel("⏳ 待生效")
            lbl_status.setStyleSheet("font-weight: bold; color: #555566; font-size: 9.5pt; border: none; background: transparent;")

            h_lay.addWidget(lbl_time)
            h_lay.addWidget(lbl_title)
            h_lay.addStretch()
            h_lay.addWidget(lbl_status)

            lbl_sub = QLabel(phase_desc)
            lbl_sub.setWordWrap(True)
            lbl_sub.setStyleSheet("color: #9a9ab0; font-size: 8.5pt; border: none; background: transparent;")

            p_layout.addLayout(h_lay)
            p_layout.addWidget(lbl_sub)
            phase_layout.addWidget(p_box)

            self.phase_items.append({
                "frame": p_box,
                "lbl_time": lbl_time,
                "lbl_title": lbl_title,
                "lbl_status": lbl_status,
                "lbl_desc": lbl_sub
            })

        layout.addWidget(phase_group)

        # 3. 规则细节与达成状态表格
        rule_group = QGroupBox("🔍 当前策略段规则条件达成状态")
        rule_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #303042;
                border-radius: 6px;
                margin-top: 8px;
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
        self.table_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_rules.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_rules.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_rules.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_rules.setAlternatingRowColors(True)
        self.table_rules.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_rules.setStyleSheet("""
            QTableWidget { background-color: #121218; gridline-color: #252535; color: #d0d0e0; }
            QHeaderView::section { background-color: #1b1b26; color: #38bdf8; font-weight: bold; }
        """)
        rule_layout.addWidget(self.table_rules)

        layout.addWidget(rule_group, 1)

        # 4. 路由日志与执行输出
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
        self.txt_log.setMaximumHeight(120)
        log_layout.addWidget(self.txt_log)

        layout.addWidget(log_group)

    def update_status(
        self,
        code: str,
        open_price: float,
        current_time_str: str,
        strategy: Dict[str, Any],
        engine: IntradayStrategyEngine
    ):
        """更新时间轴看板与规则状态"""
        c_clean = str(code).zfill(6)
        tier_name, strat_id, mode = engine.get_open_price_tier(open_price)
        
        self.lbl_open_price.setText(f"开盘价: {open_price:.2f} 元" if open_price > 0 else "开盘价: -- 元")
        self.lbl_tier.setText(f"对应档位: {tier_name}")
        self.lbl_strategy_name.setText(f"当前策略: {strategy.get('name', '未选择')}")
        self.lbl_current_time.setText(f"盘中时间: {current_time_str}")

        clean_t = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        # 1. 动态更新时间轴阶段高亮
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
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #00ff88; font-size: 9.5pt; border: none; background: transparent;")
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
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #8e8e93; font-size: 9.5pt; border: none; background: transparent;")
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
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #555566; font-size: 9.5pt; border: none; background: transparent;")

        # 2. 更新当前阶段规则列表
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

                self.table_rules.setItem(row, 0, QTableWidgetItem(r_name))
                self.table_rules.setItem(row, 1, QTableWidgetItem(target_str))
                self.table_rules.setItem(row, 2, QTableWidgetItem(r_ratio))
                
                item_st = QTableWidgetItem(status_str)
                item_st.setForeground(status_color)
                self.table_rules.setItem(row, 3, item_st)

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
    """ATS 单独分时交易策略与 SBC 实盘显示主窗口"""
    def __init__(self, code: str = "920199", name: str = "倍益康", parent=None):
        super().__init__(parent)
        self.code = str(code).zfill(6)
        self.name = name
        self.engine = IntradayStrategyEngine.get_instance()

        self.setWindowTitle(f"⚡ ATS 单独分时交易策略与 SBC 实盘显示 - {self.code} {self.name}")
        self.resize(1120, 750)
        self.setMinimumSize(850, 550)

        self._init_ui()
        self._load_mock_or_live_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 1. 顶部 Header
        hdr_layout = QHBoxLayout()
        title_lbl = QLabel(f"📈 新股/分时阶梯交易策略 & SBC 实盘监控 ({self.code} {self.name})")
        title_lbl.setStyleSheet("font-size: 14pt; font-weight: bold; color: #38bdf8;")

        btn_edit = QPushButton("⚙️ 自定制策略编辑")
        btn_edit.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; padding: 4px 12px;")
        btn_edit.clicked.connect(self._on_open_editor)

        btn_close = QPushButton("关闭窗口")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; padding: 4px 12px;")
        btn_close.clicked.connect(self.close)

        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(btn_edit)
        hdr_layout.addWidget(btn_close)
        layout.addLayout(hdr_layout)

        # 2. 中央 Splitter (左侧时间轴动态策略段看板, 右侧 SBC 实盘分时)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.phase_panel = TimeAxisPhasePanel(self)
        splitter.addWidget(self.phase_panel)

        # 右侧 SBC 分时显示与买卖点视图容器
        self.sbc_container = QWidget()
        sbc_layout = QVBoxLayout(self.sbc_container)
        sbc_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_sbc_title = QLabel("📊 SBC 实盘分时走势与策略买卖点 (含 Open/临停/止盈线标记)")
        self.lbl_sbc_title.setStyleSheet("font-weight: bold; color: #00ff88; padding: 4px;")
        sbc_layout.addWidget(self.lbl_sbc_title)

        self.txt_sbc_placeholder = QTextEdit()
        self.txt_sbc_placeholder.setReadOnly(True)
        self.txt_sbc_placeholder.setStyleSheet("background-color: #101015; color: #38bdf8; font-family: Consolas; font-size: 10pt;")
        sbc_layout.addWidget(self.txt_sbc_placeholder)

        splitter.addWidget(self.sbc_container)
        splitter.setSizes([450, 670])

        layout.addWidget(splitter, 1)

        # 3. 定时刷新子线程/Timer
        self.timer = QTimer(self)
        self.timer.setInterval(1000) # 1秒
        self.timer.timeout.connect(self._on_tick_update)
        self.timer.start()

    def _on_open_editor(self):
        dlg = IntradayStrategyEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.load_config()
            self._load_mock_or_live_data()

    def _load_mock_or_live_data(self):
        """加载初始或演示分时数据"""
        self.open_price = 350.0 # 模拟中性档
        self.mock_time = "09:35"
        self.mock_trade_price = 386.0 # 较 350 涨 >10%
        
        strategy = self.engine.auto_select_strategy(self.open_price)
        self.phase_panel.update_status(self.code, self.open_price, self.mock_time, strategy, self.engine)

        # 触发一次评估测试
        tick_row = {"trade": self.mock_trade_price, "close": self.mock_trade_price}
        signals = self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=self.mock_time,
            bid1_price=385.5
        )

        sbc_info = (
            f"=== ⚡ SBC 分时走势与买卖点可视化信息 ===\n"
            f"股票代码: {self.code} ({self.name})\n"
            f"开盘基准价 (Open): {self.open_price:.2f} 元 (基准参考线已绘制)\n"
            f"冲高卖出目标 (+10%): {self.open_price*1.10:.2f} 元\n"
            f"临停参考线 (+30%): {self.open_price*1.30:.2f} 元 (挂单 1.28x={self.open_price*1.28:.2f})\n"
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
        """定时刷新界面与策略推算"""
        now_str = datetime.now().strftime("%H:%M:%S")
        strategy = self.engine.auto_select_strategy(self.open_price)
        self.phase_panel.update_status(self.code, self.open_price, now_str, strategy, self.engine)

if __name__ == "__main__":
    # 仅当直接运行本文件进行独立 UI 测试时挂载开发路径
    _CUR_DIR = os.path.dirname(os.path.abspath(__file__))
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(_CUR_DIR))
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)

    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    dlg = IntradayStrategyDialog(code="920199", name="倍益康")
    dlg.show()
    sys.exit(app.exec())

