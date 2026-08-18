# -*- coding: utf-8 -*-
"""
ats/ui/intraday_strategy_dialog.py — ATS 分时阶梯交易策略 & 频准激光 8/18 上市动态时序评估一体化系统
特点：
1. 深度整合原有的分时阶梯交易策略（开盘定盘、时间轴阶段、规则达成、价格笼子挂单、买卖点信号路由与流水、SBC 实盘走势）与 7 节点时序动态打分评估体系；
2. Tab 1 为一体化实盘交易与动态评估工作台，数据由实时 df / TDX 秒级直连 / 手动估价自动摄入解析并动态驱动；
3. 支持【✍️ 估价推演 / 手动输入价格自动评分】模式，在行情未开盘、数据获取异常或需要推演时，用户输入开盘估价/现价/换手率即可全自动重新评估 7 节点打分与操作策略；
4. 彻底解决滚动条自动跳回顶部问题（采用滚动条位置保护与脏检查复用机制）；
5. Tab 2 为 8/18 开盘时间对齐全天分时模拟回测演练器（四大情景 A/B/C/D型）；
6. Tab 3 为频准激光 8/18 专属盯盘模板、综合加权汇总表与 7 条实盘法则；
7. 基于 QMainWindow 独立窗口运行，支持窗口置顶 (StayOnTop) 与 TDX 1 秒极速直连。
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
    QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QTextEdit, QComboBox, QMessageBox, QFrame, QGridLayout, QProgressBar,
    QScrollArea, QTabWidget, QDoubleSpinBox, QRadioButton, QButtonGroup,
    QCheckBox, QSlider, QToolBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush, QIcon

from sys_utils import resolve_stock_name
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.styles import apply_dark_theme, DARK_THEME_QSS
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyDialog")


def _format_cell_text(val) -> str:
    """安全格式化单元格文本"""
    if val is None:
        return ""
    if isinstance(val, (list, tuple, set)):
        return "；".join(str(x) for x in val)
    return str(val)


def _format_tooltip_text(val) -> Optional[str]:
    """安全格式化 Tooltip 文本"""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        return "\n".join(str(x) for x in val)
    return str(val)


def _set_or_update_table_item(
    table: QTableWidget,
    row: int,
    col: int,
    text: Any,
    fg_color=None,
    bg_color=None,
    align=None,
    font=None,
    tooltip=None
) -> QTableWidgetItem:
    """
    安全设置或更新 QTableWidget 单元格 Item。
    若 Item 已经存在，则只调用 setText / setForeground 等属性更新，
    绝不重复调用 setItem()，彻底避免 'cannot insert an item that is already owned' 警告。
    支持自动格式化 list / tuple 类型的 text 与 tooltip。
    """
    str_text = _format_cell_text(text)
    str_tooltip = _format_tooltip_text(tooltip)

    item = table.item(row, col)
    if item is None:
        item = QTableWidgetItem(str_text)
        if fg_color is not None:
            item.setForeground(fg_color if isinstance(fg_color, (QColor, QBrush)) else QColor(fg_color))
        if bg_color is not None:
            item.setBackground(bg_color if isinstance(bg_color, (QColor, QBrush)) else QColor(bg_color))
        if align is not None:
            item.setTextAlignment(align)
        if font is not None:
            item.setFont(font)
        if str_tooltip is not None:
            item.setToolTip(str_tooltip)
        table.setItem(row, col, item)
    else:
        item.setText(str_text)
        if fg_color is not None:
            item.setForeground(fg_color if isinstance(fg_color, (QColor, QBrush)) else QColor(fg_color))
        if bg_color is not None:
            item.setBackground(bg_color if isinstance(bg_color, (QColor, QBrush)) else QColor(bg_color))
        if align is not None:
            item.setTextAlignment(align)
        if font is not None:
            item.setFont(font)
        if str_tooltip is not None:
            item.setToolTip(str_tooltip)
    return item


import copy


class IntradayStrategyEditDialog(QDialog):
    """自定制分时策略 JSON 编辑器（支持单策略精准聚焦、一键新建/复制/删除策略与全量 JSON 多模式管理）"""
    def __init__(self, parent=None, initial_strategy_id: Optional[str] = None, current_code: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 自定制分时交易策略编辑器")
        self.resize(920, 660)
        self.engine = IntradayStrategyEngine.get_instance()
        self.initial_strategy_id = initial_strategy_id
        self.current_code = current_code
        self._full_config_data = {}
        self._current_selected_mode = ""  # 记录当前选中的策略 ID 或 "__ALL__"
        apply_dark_theme(self)
        self._load_full_config()
        self._init_ui()

    def _load_full_config(self):
        if os.path.exists(self.engine.config_path):
            try:
                with open(self.engine.config_path, "r", encoding="utf-8") as f:
                    self._full_config_data = json.load(f)
            except Exception as e:
                logger.error(f"加载策略配置文件失败: {e}")
                self._full_config_data = {"version": "2.0", "strategies": self.engine.strategies}
        else:
            self._full_config_data = {"version": "2.0", "strategies": self.engine.strategies}

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部策略选择与管理栏
        top_bar = QHBoxLayout()
        lbl_target = QLabel("🎯 策略选择:")
        lbl_target.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 10pt;")
        top_bar.addWidget(lbl_target)

        self.combo_strat = QComboBox()
        self.combo_strat.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #ffaa44; border: 1px solid #ffaa44; border-radius: 4px; padding: 4px 8px; font-weight: bold; min-width: 320px; font-size: 9.5pt; }")
        top_bar.addWidget(self.combo_strat)

        btn_new_strat = QPushButton("➕ 新建策略")
        btn_new_strat.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_new_strat.setToolTip("基于标准阶梯模板创建一个全新独立策略")
        btn_new_strat.clicked.connect(self._on_create_new_strategy)
        top_bar.addWidget(btn_new_strat)

        btn_clone_strat = QPushButton("📑 复制策略")
        btn_clone_strat.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_clone_strat.setToolTip("以当前选中的策略为蓝本快速克隆一套新策略")
        btn_clone_strat.clicked.connect(self._on_clone_current_strategy)
        top_bar.addWidget(btn_clone_strat)

        btn_del_strat = QPushButton("🗑️ 删除策略")
        btn_del_strat.setStyleSheet("background-color: #3a1e1e; color: #ff6666; font-weight: bold; border: 1px solid #ff4444; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_del_strat.setToolTip("从列表中移除当前选中的策略配置")
        btn_del_strat.clicked.connect(self._on_delete_strategy)
        top_bar.addWidget(btn_del_strat)

        top_bar.addStretch()

        self.lbl_tips = QLabel("💡 提示：在下方可实时编辑策略规则，保存后即时生效落盘。")
        self.lbl_tips.setStyleSheet("color: #00ff88; font-size: 9pt;")
        top_bar.addWidget(self.lbl_tips)

        layout.addLayout(top_bar)

        # JSON 编辑框
        self.txt_json = QTextEdit()
        self.txt_json.setStyleSheet("background-color: #121218; color: #00ff88; font-family: Consolas, 'Courier New', Monospace; font-size: 10pt; line-height: 1.3;")
        layout.addWidget(self.txt_json, 1)

        # 底部按钮栏
        btn_layout = QHBoxLayout()
        btn_format = QPushButton("🔄 格式化校验")
        btn_format.setStyleSheet("background-color: #242436; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 6px 14px;")
        btn_format.clicked.connect(self._on_format)

        btn_save = QPushButton("💾 保存并应用")
        btn_save.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 6px 18px;")
        btn_save.clicked.connect(self._on_save)

        btn_close = QPushButton("取消/关闭")
        btn_close.setStyleSheet("background-color: #333344; color: white; border-radius: 4px; padding: 6px 14px;")
        btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(btn_format)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        # 确定初始选中的策略
        target_id = self.initial_strategy_id
        if not target_id and self.current_code:
            auto_st = self.engine.auto_select_strategy(0.0, code=self.current_code)
            if auto_st:
                target_id = auto_st.get("id")

        self.combo_strat.currentIndexChanged.connect(self._on_combo_strat_changed)
        self._refresh_combo_strat(select_id=target_id)

    def _refresh_combo_strat(self, select_id: Optional[str] = None):
        self.combo_strat.blockSignals(True)
        self.combo_strat.clear()

        strats = self._full_config_data.get("strategies", [])
        for st in strats:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            t_codes = st.get("target_codes", [])
            t_str = f" [标的: {', '.join(t_codes)}]" if t_codes else ""
            self.combo_strat.addItem(f"📋 {st_name}{t_str}", st_id)

        self.combo_strat.addItem("🌐 全部策略配置 (全量 JSON 文件)", "__ALL__")

        target_idx = 0
        if select_id:
            for i in range(self.combo_strat.count()):
                if self.combo_strat.itemData(i) == select_id:
                    target_idx = i
                    break

        self.combo_strat.setCurrentIndex(target_idx)
        self.combo_strat.blockSignals(False)
        self._switch_to_mode(self.combo_strat.itemData(target_idx))

    def _switch_to_mode(self, mode: str):
        self._current_selected_mode = mode
        if mode == "__ALL__":
            self.setWindowTitle("⚙️ 自定制分时交易策略编辑器 - 【全量 JSON 配置】")
            content_str = json.dumps(self._full_config_data, ensure_ascii=False, indent=2)
            self.txt_json.setPlainText(content_str)
        else:
            strats = self._full_config_data.get("strategies", [])
            target_st = next((s for s in strats if s.get("id") == mode), None)
            if target_st:
                st_name = target_st.get("name", mode)
                self.setWindowTitle(f"⚙️ 自定制分时交易策略编辑器 - 【{st_name}】")
                content_str = json.dumps(target_st, ensure_ascii=False, indent=2)
                self.txt_json.setPlainText(content_str)
            else:
                self.txt_json.setPlainText("{\n}")

    def _on_combo_strat_changed(self, index: int):
        mode = self.combo_strat.itemData(index)
        self._switch_to_mode(mode)

    def _on_create_new_strategy(self):
        """【➕ 新建策略】一键根据标准阶梯模板生成全新独立策略并进入编辑"""
        strats = self._full_config_data.setdefault("strategies", [])
        new_idx = len(strats) + 1
        ts_suffix = str(int(time.time()))[-4:]
        new_id = f"strategy_custom_{ts_suffix}"
        target_code_str = self.current_code if self.current_code else "688888"
        new_name = f"新股自定义阶梯策略 {new_idx}（{target_code_str}）"

        new_strat = {
            "id": new_id,
            "name": new_name,
            "target_codes": [target_code_str] if target_code_str else [],
            "description": "基于时间轴分批减仓与价格笼子挂单的自定制分时阶梯策略",
            "applicable_rules": {
                "open_price_ranges": [
                    {"name": "标准档", "min": 0.0, "max": 99999.0, "action_mode": "standard"}
                ]
            },
            "phases": [
                {
                    "phase_id": "call_auction",
                    "name": "9:15~9:25 集合竞价定盘",
                    "start_time": "09:15",
                    "end_time": "09:25",
                    "description": "记录开盘价 Open，判定价格所属档位，锁定执行策略",
                    "rules": []
                },
                {
                    "phase_id": "opening_surge",
                    "name": "9:30~10:00 开盘冲高卖出",
                    "start_time": "09:30",
                    "end_time": "10:00",
                    "description": "开盘后冲高分批卖出第一批仓位",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_surge_10",
                            "name": "规则1: 开盘冲高涨10%卖50%",
                            "condition_mode": "standard",
                            "trigger_expr": "price >= open_price * 1.10",
                            "sell_ratio": 0.5,
                            "order_type": "limit_price_cage",
                            "price_offset_ratio": 1.02,
                            "description": "较开盘涨10%以上，按当前买一价*1.02限价单卖出50%"
                        },
                        {
                            "rule_id": f"rule_s{new_idx}_timeout",
                            "name": "规则1兜底: 10:00整超时卖30%",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '10:00'",
                            "sell_ratio": 0.3,
                            "order_type": "market_price",
                            "description": "若10:00前未触发冲高条件，10:00整按市价卖出30%"
                        }
                    ]
                },
                {
                    "phase_id": "circuit_breaker",
                    "name": "9:30~15:00 临停复牌卖出",
                    "start_time": "09:30",
                    "end_time": "15:00",
                    "description": "触发较开盘价+30%临停复牌后卖出",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_halt_30",
                            "name": "规则2: 较开盘+30%临停复牌卖30%",
                            "condition_mode": "all",
                            "trigger_expr": "max_price >= open_price * 1.30",
                            "sell_ratio": 0.3,
                            "order_type": "limit",
                            "limit_price_expr": "open_price * 1.28",
                            "description": "复牌后3分钟内再卖30%，复牌前挂 Open*1.28 限价单"
                        }
                    ]
                },
                {
                    "phase_id": "closing_clearance",
                    "name": "14:50~14:57 尾盘清仓",
                    "start_time": "14:50",
                    "end_time": "14:57",
                    "description": "尾盘清仓剩余全部仓位",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_clear_all",
                            "name": "规则3: 尾盘市价清仓剩余",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '14:50'",
                            "sell_ratio": 1.0,
                            "order_type": "market_price",
                            "description": "14:50~14:57 按买一价市价卖出剩余全部"
                        }
                    ]
                }
            ]
        }

        strats.append(new_strat)
        self._refresh_combo_strat(select_id=new_id)
        QMessageBox.information(self, "新建策略成功", f"✅ 已成功生成新策略【{new_name}】模板！\n可在下方直接调整参数与规则，修改后点击“保存并应用”即可生效。")

    def _on_clone_current_strategy(self):
        """【📑 复制策略】以当前选中的策略为基础克隆一份并直接切换至编辑"""
        if self._current_selected_mode == "__ALL__":
            QMessageBox.warning(self, "提示", "请在上方下拉列表中先选择一个具体策略，再进行复制克隆。")
            return

        strats = self._full_config_data.setdefault("strategies", [])
        target_st = next((s for s in strats if s.get("id") == self._current_selected_mode), None)
        if not target_st:
            QMessageBox.warning(self, "错误", "未找到要克隆的目标策略。")
            return

        cloned_strat = copy.deepcopy(target_st)
        ts_suffix = str(int(time.time()))[-4:]
        cloned_strat["id"] = f"{target_st.get('id', 'strat')}_copy_{ts_suffix}"
        cloned_strat["name"] = f"{target_st.get('name', '策略')} (副本)"
        
        strats.append(cloned_strat)
        self._refresh_combo_strat(select_id=cloned_strat["id"])
        QMessageBox.information(self, "克隆成功", f"✅ 已成功克隆策略【{cloned_strat['name']}】！\n可在下方直接修改配置。")

    def _on_delete_strategy(self):
        """【🗑️ 删除策略】从列表中安全移除当前选中的策略"""
        if self._current_selected_mode == "__ALL__":
            QMessageBox.warning(self, "提示", "全量配置文件不可直接删除！")
            return

        strats = self._full_config_data.get("strategies", [])
        if len(strats) <= 1:
            QMessageBox.warning(self, "提示", "当前只剩 1 套策略，不可继续删除，至少需要保留 1 套有效策略。")
            return

        target_st = next((s for s in strats if s.get("id") == self._current_selected_mode), None)
        if not target_st:
            return

        st_name = target_st.get("name", self._current_selected_mode)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除策略【{st_name}】吗？\n删除后点击“保存并应用”将永久生效。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._full_config_data["strategies"] = [s for s in strats if s.get("id") != self._current_selected_mode]
            next_select = self._full_config_data["strategies"][0].get("id") if self._full_config_data["strategies"] else "__ALL__"
            self._refresh_combo_strat(select_id=next_select)
            QMessageBox.information(self, "已移除", f"策略【{st_name}】已从临时列表中移除，点击“保存并应用”即可写入磁盘。")

    def _on_format(self):
        try:
            cur_text = self.txt_json.toPlainText()
            data = json.loads(cur_text)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            self.txt_json.setPlainText(formatted)
            QMessageBox.information(self, "格式正确", "✅ JSON 语法校验通过并已自动格式化排版！")
        except Exception as e:
            QMessageBox.critical(self, "JSON 语法错误", f"❌ JSON 解析失败，请检查语法:\n{e}")

    def _on_save(self):
        content = self.txt_json.toPlainText()
        try:
            parsed = json.loads(content)
        except Exception as e:
            QMessageBox.critical(self, "JSON 语法错误", f"❌ 解析 JSON 格式失败，请修正后再保存:\n{e}")
            return

        try:
            if self._current_selected_mode == "__ALL__":
                if not isinstance(parsed, dict) or "strategies" not in parsed:
                    QMessageBox.warning(self, "格式错误", "❌ 全量配置必须为包含 'strategies' 列表的 JSON 对象！")
                    return
                self._full_config_data = parsed
            else:
                if not isinstance(parsed, dict):
                    QMessageBox.warning(self, "格式错误", "❌ 单策略配置必须为 JSON 对象 (dict)！")
                    return
                st_id = parsed.get("id") or self._current_selected_mode
                parsed["id"] = st_id
                strats = self._full_config_data.setdefault("strategies", [])
                replaced = False
                for idx, s in enumerate(strats):
                    if s.get("id") == st_id or s.get("id") == self._current_selected_mode:
                        strats[idx] = parsed
                        replaced = True
                        break
                if not replaced:
                    strats.append(parsed)

            if self.engine.save_config(self._full_config_data):
                self.engine.load_config()
                QMessageBox.information(self, "成功", "✅ 策略配置更新成功并已物理落盘！")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "❌ 策略配置保存失败，请检查文件写入权限。")
        except Exception as e:
            QMessageBox.critical(self, "保存异常", f"❌ 保存策略配置失败:\n{e}")


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
        phase_box.setMinimumHeight(140)
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
        rule_box.setMinimumHeight(130)
        left_layout.addWidget(rule_box, 1)

        # 7 节点动态评估速查表 (输入价格校准自动评分)
        node_box = QGroupBox("🎯 7 节点时序评估 (根据当时价格/换手自动评分，数据异常可手动输入价格校准)")
        node_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_box_layout = QVBoxLayout(node_box)
        node_box_layout.setContentsMargins(4, 8, 4, 4)

        node_header_lay = QHBoxLayout()
        lbl_node_hint = QLabel("💡 评分由系统根据价格全自动评估；若行情出错可在【校准价格/换手】列输入真实价格。")
        lbl_node_hint.setStyleSheet("color: #00ff88; font-size: 8pt;")
        btn_reset_node_params = QPushButton("🔄 重置校准")
        btn_reset_node_params.setStyleSheet("background-color: #222232; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 1px 6px; font-size: 8pt;")
        btn_reset_node_params.clicked.connect(self._on_reset_node_custom_params)
        node_header_lay.addWidget(lbl_node_hint)
        node_header_lay.addStretch()
        node_header_lay.addWidget(btn_reset_node_params)
        node_box_layout.addLayout(node_header_lay)

        self.table_quick_nodes = QTableWidget()
        self.table_quick_nodes.setColumnCount(7)
        self.table_quick_nodes.setHorizontalHeaderLabels(["节点", "时间", "校准价格/换手", "特征观察解析", "信号判定", "自动评分", "权重"])
        self.table_quick_nodes.setAlternatingRowColors(True)
        self.table_quick_nodes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_quick_nodes.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #ffd700; font-weight: bold; padding: 3px; }")

        h_q = self.table_quick_nodes.horizontalHeader()
        h_q.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_q.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_q.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_quick_nodes.setColumnWidth(2, 95)
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
        sig_box = QGroupBox("⚡ 策略执行买卖点明细 (实盘/模拟/推演触发)")
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
        sig_box.setMinimumHeight(130)
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

    def _on_reset_node_custom_params(self):
        self.engine.reset_node_custom_params(self.code)
        self.manual_score_signal.emit()

    def _rebuild_phase_items(self, strategy: Dict[str, Any]):
        st_id = strategy.get("id") if isinstance(strategy, dict) else None
        if getattr(self, "_last_strategy_id", None) == st_id and self.phase_items:
            return
        self._last_strategy_id = st_id

        # 记录滚动位置
        sb = self.phase_scroll.verticalScrollBar()
        old_val = sb.value()

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

        sb.setValue(old_val)

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
        is_unlisted: bool = False,
        last_close: Optional[float] = None
    ):
        """全面刷新一体化工作台数据（带滚动条位置锁定保护）"""
        self.code = code
        c_clean = str(code).zfill(6)

        strat_id = strategy.get("id", "") if strategy else ""
        strat_type = strategy.get("strategy_type", "") if strategy else ""
        target_newstock_codes = self.engine.get_all_target_codes()
        has_stock_spec = bool(strategy and ("stock_spec" in strategy or strategy.get("schema_version") == "v1.0-unified"))
        is_daily_strategy = (
            strat_type in ("daily_surge", "general", "daily")
            or "daily" in strat_id
            or "surge" in strat_id
            or (not has_stock_spec and c_clean not in target_newstock_codes)
        )

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
            amount=amount,
            strategy_id=strat_id,
            last_close=last_close
        )

        tot_score = eval_res.get("total_weighted_score", 0.0)
        pattern = eval_res.get("pattern", "--")
        intensity_val = eval_res.get("intensity_ratio", 0.0)
        state = self.engine._get_stock_state(c_clean, open_price)
        rem_ratio = state.get("remaining_ratio", 1.0)
        signals = state.get("signals", [])
        logs = state.get("execution_logs", [])

        # 2. 顶部状态卡
        tier_name, _, _ = self.engine.get_open_price_tier(open_price, code=c_clean)
        unlisted_str = " (待上市估价)" if is_unlisted or open_price <= 0 else ""
        
        if is_daily_strategy:
            open_gain_str = f" (今开幅: {((open_price-last_close)/last_close*100):+.2f}%)" if (last_close and last_close > 0 and open_price > 0) else ""
            self.lbl_open_info.setText(f"开盘基准: {open_price:.2f}元{open_gain_str} | 现价: {price:.2f}元 | VWAP: {vwap:.2f}元")
        else:
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

        # 4. 时间轴策略阶段高亮（带滚动条位置锁定）
        sb_phase = self.phase_scroll.verticalScrollBar()
        old_phase_pos = sb_phase.value()
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

        sb_phase.setValue(old_phase_pos)

        # 5. 规则达成表格（带滚动条锁定）
        sb_rules = self.table_rules.verticalScrollBar()
        old_rule_pos = sb_rules.value()

        if curr_phase:
            rules = curr_phase.get("rules", [])
            triggered_rules = state.get("triggered_rules", set())
            if self.table_rules.rowCount() != len(rules):
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
                    elif is_daily_strategy and ("surge" in r_id or "profit" in r_id):
                        target_str = r.get("trigger_expr", f"冲高 ≥ {open_price*1.03:.2f}元")
                        sugg_p = f"{price:.2f}元(市价)"
                    else:
                        target_str = r.get("trigger_expr", "--")
                        sugg_p = f"{price:.2f}元(市价)"
                else:
                    target_str = r.get("trigger_expr", "--")
                    sugg_p = "--"

                status_str = "✅ 已触发卖出" if r_id in triggered_rules else "⏳ 监控中"
                status_color = "#00ff88" if r_id in triggered_rules else "#ffaa44"

                _set_or_update_table_item(self.table_rules, row, 0, r_name)
                _set_or_update_table_item(self.table_rules, row, 1, target_str)
                _set_or_update_table_item(self.table_rules, row, 2, r_ratio, align=Qt.AlignmentFlag.AlignCenter)
                _set_or_update_table_item(self.table_rules, row, 3, sugg_p, fg_color="#ffd700")
                _set_or_update_table_item(self.table_rules, row, 4, status_str, fg_color=status_color)

        sb_rules.setValue(old_rule_pos)

        # 6. 7 节点动态打分速查表（带滚动条锁定 & 价格校准自动评分）
        sb_quick = self.table_quick_nodes.verticalScrollBar()
        old_quick_pos = sb_quick.value()

        node_results = eval_res.get("node_results", [])
        if self.table_quick_nodes.rowCount() != len(node_results):
            self.table_quick_nodes.setRowCount(len(node_results))

        self._is_updating = True
        for row, nr in enumerate(node_results):
            judg_color = "#00ff88" if nr["judgment"] == "强" else ("#38bdf8" if nr["judgment"] == "中" else "#ff5555")
            _set_or_update_table_item(self.table_quick_nodes, row, 0, nr["name"])
            _set_or_update_table_item(self.table_quick_nodes, row, 1, nr["time_str"])

            # 列 2: 价格/换手校准输入框 (QDoubleSpinBox)
            unit_str = nr.get("input_unit", "元")
            input_v = float(nr.get("input_val", 0.0))
            spin = self.table_quick_nodes.cellWidget(row, 2)
            if not isinstance(spin, QDoubleSpinBox):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 5000.0)
                spin.setSingleStep(1.0 if unit_str == "%" else 5.0)
                spin.setSuffix(f" {unit_str}")
                spin.setStyleSheet("background-color: #1a1a26; color: #ffd700; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px;")
                spin.valueChanged.connect(self._make_param_spin_handler(row, nr["node_id"]))
                self.table_quick_nodes.setCellWidget(row, 2, spin)

            spin.blockSignals(True)
            spin.setSuffix(f" {unit_str}")
            spin.setValue(input_v)
            spin.blockSignals(False)

            # 列 3: 特征解析观察值
            _set_or_update_table_item(self.table_quick_nodes, row, 3, nr["observed_val"], tooltip=nr["observed_val"])

            # 列 4: 信号判定
            _set_or_update_table_item(self.table_quick_nodes, row, 4, nr["judgment"], fg_color=judg_color, align=Qt.AlignmentFlag.AlignCenter)

            # 列 5: 自动评分展示 (不可手动乱改，由价格严谨推导)
            score_fg = "#00ff88" if nr["final_score"] >= 8.0 else ("#38bdf8" if nr["final_score"] >= 6.0 else "#ff5555")
            _set_or_update_table_item(self.table_quick_nodes, row, 5, f"{nr['final_score']:.1f}分", fg_color=score_fg, font=QFont("Arial", 9, QFont.Weight.Bold), align=Qt.AlignmentFlag.AlignCenter)

            # 列 6: 权重
            _set_or_update_table_item(self.table_quick_nodes, row, 6, nr["weight_pct"], align=Qt.AlignmentFlag.AlignCenter)

        sb_quick.setValue(old_quick_pos)
        self._is_updating = False

        # 7. SBC 实盘走势与基准线 (100% 策略与标的自适应)
        strat_name = strategy.get("name", "分时阶梯策略") if strategy else "分时阶梯策略"
        spec = self.engine.get_stock_ladder_spec(code)
        issue_p = float(spec.get("issue_price", open_price * 0.5 if open_price > 0 else 100.0))
        float_mv_yi = float(spec.get("float_mv_yi", 14.24))

        max_p = state.get("max_price", price)
        min_p = state.get("min_price", price)

        if is_daily_strategy:
            # 通用日常个股分时走势面板文案
            lc_str = f"{last_close:.2f} 元" if (last_close and last_close > 0) else f"{open_price:.2f} 元"
            op_pct_str = f"今开: {open_price:.2f} 元 ({((open_price-last_close)/last_close*100):+.2f}%)" if (last_close and last_close > 0) else f"开盘: {open_price:.2f} 元"
            sbc_text = (
                f"=== 📊 【{code} {resolve_stock_name(code)}】{strat_name} ===\n"
                f"【开盘基准】: {op_pct_str} (昨收基准: {lc_str})\n"
                f"【实时成交/估价】: {price:.2f} 元 (最高: {max_p:.2f}元 / 最低: {min_p:.2f}元)\n"
                f"【均价线 VWAP】: {vwap:.2f} 元 | 换手率: {turnover_rate:.2f}% | 成交额: {amount/1e8:.2f} 亿元 (流通市值:{float_mv_yi:.1f}亿)\n"
                f"【冲高卖出目标 (+3%~+5%)】: {open_price*1.03:.2f} ~ {open_price*1.05:.2f} 元 (冲高分批止盈 30%)\n"
                f"【破分时均线止损/减仓】: {vwap:.2f} 元 (跌破分时均价线 VWAP 触发减仓)\n"
                f"【移动止盈清仓 (-3%~-5%)】: {max_p*0.96:.2f} 元 (日内高点回撤触发)\n"
                f"【当前持仓管理】: 剩余持仓比例 {rem_ratio*100:.0f}%\n"
            )
        else:
            # 新股上市专属走势面板文案
            sbc_text = (
                f"=== 📊 【{code} {resolve_stock_name(code)}】{strat_name} ===\n"
                f"【开盘基准】: {open_price:.2f} 元 (基准参考线已锚定 | 发行价: {issue_p:.2f}元)\n"
                f"【实时成交/估价】: {price:.2f} 元 (最高: {max_p:.2f}元 / 最低: {min_p:.2f}元)\n"
                f"【均价线 VWAP】: {vwap:.2f} 元 | 换手率: {turnover_rate:.1f}% | 成交额: {amount/1e8:.2f} 亿元 (流通市值:{float_mv_yi:.1f}亿)\n"
                f"【冲高卖出目标 (+10%)】: {open_price*1.10:.2f} 元 (价格笼子限价卖出 50%)\n"
                f"【临停触发目标 (+30%)】: {open_price*1.30:.2f} 元 (复牌前挂单 1.28x={open_price*1.28:.2f} 卖出 30%)\n"
                f"【移动止盈清仓 (-10%)】: {max_p*0.90:.2f} 元 (高点回撤 10% 触发)\n"
                f"【当前持仓管理】: 剩余持仓比例 {rem_ratio*100:.0f}%\n"
            )

        if self.txt_sbc_info.toPlainText() != sbc_text:
            sb_sbc = self.txt_sbc_info.verticalScrollBar()
            saved_sbc_pos = sb_sbc.value()
            self.txt_sbc_info.setPlainText(sbc_text)
            sb_sbc.setValue(saved_sbc_pos)

        # 8. 买卖点明细表（带滚动条锁定）
        sb_sig = self.table_signals.verticalScrollBar()
        old_sig_pos = sb_sig.value()

        if self.table_signals.rowCount() != len(signals):
            self.table_signals.setRowCount(len(signals))

        for r, s in enumerate(signals):
            pct_str = f"{getattr(s, 'sell_ratio', 0.5)*100:.0f}%"
            sugg_p = getattr(s, 'suggested_price', s.price)
            _set_or_update_table_item(self.table_signals, r, 0, s.timestamp)
            _set_or_update_table_item(self.table_signals, r, 1, "🔴 卖出", fg_color="#ff5555", font=QFont("Arial", 9, QFont.Weight.Bold))
            _set_or_update_table_item(self.table_signals, r, 2, f"{s.price:.2f}元 (挂单:{sugg_p:.2f})", fg_color="#ffd700")
            _set_or_update_table_item(self.table_signals, r, 3, pct_str, align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_signals, r, 4, s.reason, tooltip=s.reason)

        sb_sig.setValue(old_sig_pos)

        # 9. 路由日志 (带文本脏检查与滚动条锁定)
        new_log_text = "\n".join(logs) if logs else ""
        if self.txt_log.toPlainText() != new_log_text:
            sb_log = self.txt_log.verticalScrollBar()
            saved_log_pos = sb_log.value()
            self.txt_log.setPlainText(new_log_text)
            sb_log.setValue(saved_log_pos)

    def _make_param_spin_handler(self, row: int, node_id: str):
        def _handler(val: float):
            if not self._is_updating:
                self.engine.set_node_custom_param(self.code, node_id, val)
                # 反向同步到顶部的估价微调控件 (DoubleSpinBox)
                parent = self.parent()
                while parent:
                    if hasattr(parent, 'spin_eval_open') and hasattr(parent, 'spin_eval_price'):
                        if node_id == "node_1_auction":
                            parent.spin_eval_open.blockSignals(True)
                            parent.spin_eval_open.setValue(val)
                            parent.spin_eval_open.blockSignals(False)
                            # 同步更新 open_price
                            state = self.engine._get_stock_state(self.code, val)
                            state["open_price"] = val
                        elif node_id == "node_2_first_wave":
                            parent.spin_eval_price.blockSignals(True)
                            parent.spin_eval_price.setValue(val)
                            parent.spin_eval_price.blockSignals(False)
                        elif node_id == "node_3_turnover":
                            parent.spin_eval_turnover.blockSignals(True)
                            parent.spin_eval_turnover.setValue(val)
                            parent.spin_eval_turnover.blockSignals(False)
                        break
                    parent = parent.parent()
                self.manual_score_signal.emit()
        return _handler

    def _on_reset_node_custom_params(self):
        """【🔄 重置校准】清空节点自定义参数与人工评分，重新极速拉取 TDX 分时 K 线精准恢复早盘真实节点"""
        self.engine.reset_node_custom_params(self.code)
        try:
            intraday_bars = self.tdx_fetcher.fetch_intraday_bars(self.code)
            if not intraday_bars.empty:
                op = self.spin_eval_open.value()
                self.engine.hydrate_from_intraday_df(self.code, intraday_bars, op if op > 1.0 else None)
        except Exception as e:
            logger.debug(f"重置后刷新 TDX 分时 K 线异常: {e}")

        parent = self.parent()
        while parent:
            if hasattr(parent, '_sync_eval_spins_for_current_stock'):
                parent._sync_eval_spins_for_current_stock()
                break
            parent = parent.parent()
        self.manual_score_signal.emit()


class PinzhunLadderStandaloneWindow(QMainWindow):
    """
    频准激光 8/18 专属上市盯盘与分时阶梯交易策略独立主窗口
    具备完全独立的窗口生命周期、窗口置顶、最大化最小化、多屏支持、TDX 极速秒级直连与估价自动评分能力
    """
    def __init__(self, code: Optional[str] = None, name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.tdx_fetcher = TDXRealtimeFetcher.get_instance()
        self.selected_strategy_id: Optional[str] = None
        self.selected_data_source: str = "TDX_REALTIME"  # TDX_REALTIME | ATS_IPC | MANUAL_EVAL
        self._is_stay_on_top = False
        self.tdx_log_dialog = None

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

        self.code = "".join(filter(str.isdigit, str(code))).zfill(6) if code else "688826"
        if not self.code or self.code == "000000":
            self.code = "688826"
        self._known_codes = [self.code]

        if isinstance(name, bool) or not name or name == "未知" or name == self.code:
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        # 独立窗口属性设置 (允许独立任务栏、独立最小化/最大化/关闭)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")
        self.resize(1340, 920)
        self.setMinimumSize(1020, 720)

        # 🎨 全局应用 ATS 统一暗黑主题样式表模板 (QSS)
        apply_dark_theme(self)

        # 缓存最新接收到的 DataFrame
        self._latest_df: Optional[pd.DataFrame] = None

        self._init_ui()
        self._load_mock_or_live_data()

        # 启动 3.0s 极速 UI 自动刷新定时器，驱动 UI 画面与 TDX 秒级直连后台无缝同步跳动！
        self.live_poll_timer = QTimer(self)
        self.live_poll_timer.timeout.connect(self._on_live_timer_tick)
        self.live_poll_timer.start(3000)

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. 顶部 Header 控制栏 第一行：以策略为主导驱动标的与价格联动
        hdr_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")
        self.title_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #38bdf8;")

        lbl_strat = QLabel("📋 策略:")
        lbl_strat.setStyleSheet("font-weight: bold; color: #ffaa44;")

        self.combo_strategy = QComboBox()
        self.combo_strategy.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #ffaa44; border: 1px solid #ffaa44; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 220px; }")
        self._populate_strategy_combo()
        self.combo_strategy.currentIndexChanged.connect(self._on_combo_strategy_changed)

        lbl_select = QLabel("🎯 标的:")
        lbl_select.setStyleSheet("font-weight: bold; color: #00ff88;")

        self.combo_code = QComboBox()
        self.combo_code.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #00ff88; border: 1px solid #00ff88; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 140px; }")
        self._populate_code_combo()
        self.combo_code.currentIndexChanged.connect(self._on_combo_code_changed)

        lbl_src = QLabel("📡 数据源:")
        lbl_src.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_source = QComboBox()
        self.combo_source.addItem("⚡ 【TDX 极速秒级直连 1s】", "TDX_REALTIME")
        self.combo_source.addItem("🔄 【ATS 后台 IPC 同步】", "ATS_IPC")
        self.combo_source.addItem("✍️ 【手动估价/推演模式】", "MANUAL_EVAL")
        self.combo_source.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #00ff88; border: 1px solid #00ff88; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 175px; }")
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)

        # TDX 连接状态徽标
        tdx_host_str = f"{self.tdx_fetcher.current_host[1]}:{self.tdx_fetcher.current_host[2]}" if self.tdx_fetcher.current_host else "默认"
        self.lbl_tdx_status = QLabel(f"🟢 TDX: {tdx_host_str} ({self.tdx_fetcher.latency_ms:.0f}ms)")
        self.lbl_tdx_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold; background-color: #14241d; padding: 3px 6px; border-radius: 3px; border: 1px solid #00ff88;")

        btn_refresh = QPushButton("⚡ 刷新")
        btn_refresh.setStyleSheet("background-color: #0e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_refresh.clicked.connect(self._on_manual_refresh)

        self.btn_topmost = QPushButton("📌 置顶: 关")
        self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 3px 8px;")
        self.btn_topmost.clicked.connect(self._toggle_stay_on_top)

        btn_auto_eval = QPushButton("⚡ 全量检测")
        btn_auto_eval.setStyleSheet("background-color: #1e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_auto_eval.clicked.connect(self._on_eval_all_codes)

        btn_edit = QPushButton("⚙️ 策略编辑")
        btn_edit.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_edit.clicked.connect(self._on_open_editor)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; border-radius: 4px; padding: 3px 8px;")
        btn_close.clicked.connect(self.close)

        hdr_layout.addWidget(self.title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(lbl_strat)
        hdr_layout.addWidget(self.combo_strategy)
        hdr_layout.addWidget(lbl_select)
        hdr_layout.addWidget(self.combo_code)
        hdr_layout.addWidget(lbl_src)
        hdr_layout.addWidget(self.combo_source)
        hdr_layout.addWidget(self.lbl_tdx_status)
        hdr_layout.addWidget(btn_refresh)
        hdr_layout.addWidget(self.btn_topmost)
        hdr_layout.addWidget(btn_auto_eval)
        hdr_layout.addWidget(btn_edit)
        hdr_layout.addWidget(btn_close)
        layout.addLayout(hdr_layout)

        # 2. 顶部第二行：【💡 估价自动评估 & 手动输入快速推演栏 (带默认关闭开关)】
        eval_bar_layout = QHBoxLayout()
        eval_bar_layout.setContentsMargins(0, 0, 0, 0)
        eval_bar_layout.setSpacing(8)

        self.chk_manual_eval = QCheckBox("💡 开启手动估价/异常推演 (默认关闭)")
        self.chk_manual_eval.setChecked(False) # 默认关闭，绝对优先保证实盘自动获取不受干扰
        self.chk_manual_eval.setStyleSheet("QCheckBox { color: #ffd700; font-weight: bold; font-size: 8.5pt; } QCheckBox::indicator:unchecked { border: 1px solid #777799; background: #1a1a24; } QCheckBox::indicator:checked { border: 1px solid #00ff88; background: #00ff88; }")
        self.chk_manual_eval.toggled.connect(self._on_toggle_manual_eval)

        lbl_open_p = QLabel("开盘估价:")
        lbl_open_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_open = QDoubleSpinBox()
        self.spin_eval_open.setRange(1.0, 5000.0)
        self.spin_eval_open.setValue(565.0)
        self.spin_eval_open.setSingleStep(5.0)
        self.spin_eval_open.setSuffix(" 元")
        self.spin_eval_open.setStyleSheet("background-color: #1a1a24; color: #ffd700; font-weight: bold; border: 1px solid #ffd700; border-radius: 3px; padding: 2px;")
        self.spin_eval_open.setEnabled(False) # 默认禁用
        self.spin_eval_open.valueChanged.connect(self._on_eval_param_changed)

        lbl_curr_p = QLabel("当前现价/估价:")
        lbl_curr_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_price = QDoubleSpinBox()
        self.spin_eval_price.setRange(1.0, 5000.0)
        self.spin_eval_price.setValue(625.0)
        self.spin_eval_price.setSingleStep(5.0)
        self.spin_eval_price.setSuffix(" 元")
        self.spin_eval_price.setStyleSheet("background-color: #1a1a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 3px; padding: 2px;")
        self.spin_eval_price.setEnabled(False) # 默认禁用
        self.spin_eval_price.valueChanged.connect(self._on_eval_param_changed)

        lbl_to_p = QLabel("换手率估算:")
        lbl_to_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_turnover = QDoubleSpinBox()
        self.spin_eval_turnover.setRange(0.0, 100.0)
        self.spin_eval_turnover.setValue(62.5)
        self.spin_eval_turnover.setSingleStep(1.0)
        self.spin_eval_turnover.setSuffix(" %")
        self.spin_eval_turnover.setStyleSheet("background-color: #1a1a24; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px;")
        self.spin_eval_turnover.valueChanged.connect(self._on_eval_param_changed)

        self.btn_auto_calc = QPushButton("⚡ 根据估价全自动评分 & 策略推演")
        self.btn_auto_calc.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 12px;")
        self.btn_auto_calc.setEnabled(False) # 默认禁用
        self.btn_auto_calc.clicked.connect(self._on_apply_custom_eval)

        # 📜 TDX 数据获取日志与异常诊断按钮 (与龙头榜样式完全一致)
        self.btn_tdx_log = QPushButton("📜 TDX日志")
        self.btn_tdx_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tdx_log.setToolTip("查看通达信 (pytdx) 行情拉取实时日志、非交易休市状态与网络诊断")
        self.btn_tdx_log.setStyleSheet("""
            QPushButton { 
                background-color: #1a2233; 
                color: #aad4ff; 
                border: 1px solid #334466; 
                border-radius: 3px; 
                padding: 3px 10px; 
                font-size: 8.5pt; 
                font-weight: bold; 
            }
            QPushButton:hover { 
                background-color: #2b3855; 
                color: #00ffcc; 
                border: 1px solid #00ffcc; 
            }
        """)
        self.btn_tdx_log.clicked.connect(self._open_tdx_log_dialog)

        eval_bar_layout.addWidget(self.chk_manual_eval)
        eval_bar_layout.addWidget(lbl_open_p)
        eval_bar_layout.addWidget(self.spin_eval_open)
        eval_bar_layout.addWidget(lbl_curr_p)
        eval_bar_layout.addWidget(self.spin_eval_price)
        eval_bar_layout.addWidget(lbl_to_p)
        eval_bar_layout.addWidget(self.spin_eval_turnover)
        eval_bar_layout.addWidget(self.btn_auto_calc)
        eval_bar_layout.addStretch()
        eval_bar_layout.addWidget(self.btn_tdx_log)

        layout.addLayout(eval_bar_layout)

        # 3. 中央 3 大 Tab 选项卡
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

        # Tab 2: 开盘全天分时模拟回测与情景演练器
        self.sim_panel = IntradaySimulationWidget(self)
        self.sim_panel.tick_emitted_signal.connect(self._on_simulation_tick_emitted)
        self.tab_widget.addTab(self.sim_panel, "🎮 上市全天分时模拟回测与情景演练 (A/B/C/D型)")

        # Tab 3: 专属盯盘模板 & 综合评分明细汇总
        self.pinzhun_monitor_panel = PinzhunLaserMonitorWidget(self)
        self.pinzhun_monitor_panel.score_changed_signal.connect(self._load_mock_or_live_data)
        self.tab_widget.addTab(self.pinzhun_monitor_panel, f"📋 【{self.name}】专属盯盘模板 & 综合评分汇总")

        layout.addWidget(self.tab_widget, 1)

        # 4. 定时刷新 Timer (秒级自动推进，基准 3.0s，支持自适应退避调节)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._on_tick_update)
        self.timer.start()

    def _toggle_stay_on_top(self):
        """切换窗口置顶状态"""
        self._is_stay_on_top = not self._is_stay_on_top
        if self._is_stay_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.btn_topmost.setText("📌 置顶: 开")
            self.btn_topmost.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 8px;")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.btn_topmost.setText("📌 置顶: 关")
            self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 3px 8px;")
        self.show()

    def _on_toggle_manual_eval(self, checked: bool):
        """【开关】手动估价/异常推演开关切换：默认关闭，防止干扰实盘"""
        # 更新输入框与推演按钮启用状态
        self.spin_eval_open.setEnabled(checked)
        self.spin_eval_price.setEnabled(checked)
        self.spin_eval_turnover.setEnabled(checked)
        self.btn_auto_calc.setEnabled(checked)

        target_source = "MANUAL_EVAL" if checked else "TDX_REALTIME"
        if self.selected_data_source != target_source:
            self.combo_source.blockSignals(True)
            idx = self.combo_source.findData(target_source)
            if idx >= 0:
                self.combo_source.setCurrentIndex(idx)
            self.selected_data_source = target_source
            self.combo_source.blockSignals(False)

        if not checked:
            # 关闭手动估价时，重置节点覆盖参数，完全恢复实盘自动拉取
            self.engine.reset_node_custom_params(self.code)
            self.lbl_tdx_status.show()
            self._update_tdx_status_badge()
        else:
            self.lbl_tdx_status.setText("✍️ 估价模式")
            self.lbl_tdx_status.show()
            self._on_eval_param_changed()
            return

        self._load_mock_or_live_data()

    def _on_source_changed(self, index: int):
        self.selected_data_source = self.combo_source.itemData(index)
        is_manual = (self.selected_data_source == "MANUAL_EVAL")
        if hasattr(self, 'chk_manual_eval'):
            self.chk_manual_eval.blockSignals(True)
            self.chk_manual_eval.setChecked(is_manual)
            self.spin_eval_open.setEnabled(is_manual)
            self.spin_eval_price.setEnabled(is_manual)
            self.spin_eval_turnover.setEnabled(is_manual)
            self.btn_auto_calc.setEnabled(is_manual)
            self.chk_manual_eval.blockSignals(False)

        if self.selected_data_source == "TDX_REALTIME":
            self.lbl_tdx_status.show()
            self._update_tdx_status_badge()
        elif self.selected_data_source == "MANUAL_EVAL":
            self.lbl_tdx_status.setText("✍️ 估价模式")
            self.lbl_tdx_status.show()
        else:
            self.lbl_tdx_status.hide()
        self._load_mock_or_live_data()

    def _on_eval_param_changed(self):
        """当用户修改开盘估价、现价估价或换手率时自动同步 7 节点校准参数并触发评分"""
        if not getattr(self, 'chk_manual_eval', None) or not self.chk_manual_eval.isChecked():
            return
        if hasattr(self, 'spin_eval_open'):
            op = self.spin_eval_open.value()
            tp = self.spin_eval_price.value()
            to_rate = self.spin_eval_turnover.value()
            self.open_price = op
            # 实时同步到引擎中 7 节点对应的节点校准槽位
            self.engine.set_node_custom_param(self.code, "node_1_auction", op)
            self.engine.set_node_custom_param(self.code, "node_2_first_wave", tp)
            self.engine.set_node_custom_param(self.code, "node_3_turnover", to_rate)
            # 同步更新股票状态
            state = self.engine._get_stock_state(self.code, op)
            state["open_price"] = op
            if tp > state.get("max_price", 0.0):
                state["max_price"] = tp
        self._load_mock_or_live_data()

    def _on_apply_custom_eval(self):
        """手动点击估价评估按钮：一键开启估价模式并全自动打分"""
        if hasattr(self, 'chk_manual_eval'):
            self.chk_manual_eval.setChecked(True)
        idx = self.combo_source.findData("MANUAL_EVAL")
        if idx >= 0:
            self.combo_source.setCurrentIndex(idx)
        self.selected_data_source = "MANUAL_EVAL"
        self._on_eval_param_changed()

    def _on_live_timer_tick(self):
        """3.0s 定时刷新回调：在 TDX 直连模式且未开启手动估价勾选时，自动驱动界面极速跳动与评估"""
        if getattr(self, "selected_data_source", "") == "TDX_REALTIME":
            if not hasattr(self, "chk_manual_eval") or not self.chk_manual_eval.isChecked():
                self._load_mock_or_live_data()

    def _on_manual_refresh(self):
        """用户手动点击【⚡ 刷新】按钮：重置 TDX 静默状态并立即拉取"""
        if self.tdx_fetcher:
            self.tdx_fetcher.reset_code_dormancy(self.code)
        self._load_mock_or_live_data()

    def _open_tdx_log_dialog(self):
        """打开/激活通达信高频数据获取诊断日志独立窗口"""
        from PyQt6.sip import isdeleted
        from ats.ui.hot_sector_leaderboard import TDXFetchLogDialog
        if self.tdx_log_dialog is not None and not isdeleted(self.tdx_log_dialog):
            self.tdx_log_dialog.show()
            self.tdx_log_dialog.raise_()
            self.tdx_log_dialog.activateWindow()
            return

        self.tdx_log_dialog = TDXFetchLogDialog(parent=self)
        self.tdx_log_dialog.show()
        self.tdx_log_dialog.raise_()
        self.tdx_log_dialog.activateWindow()

    def _update_tdx_status_badge(self):
        if self.tdx_fetcher and self.tdx_fetcher.current_host:
            h = self.tdx_fetcher.current_host
            is_dormant = self.code in getattr(self.tdx_fetcher, '_unlisted_or_dormant_codes', set())
            if is_dormant:
                self.lbl_tdx_status.setText(f"🟡 TDX: 暂无成交 (30s静默)")
            else:
                self.lbl_tdx_status.setText(f"🟢 TDX: {h[1]}:{h[2]} ({self.tdx_fetcher.latency_ms:.0f}ms)")
        else:
            self.lbl_tdx_status.setText("🔴 TDX: 未连接")

    def on_realtime_df_update(self, df: Optional[pd.DataFrame]):
        """接收来自 ATS 主窗口或独立 IPC 数据流的实时行情推送"""
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            self._latest_df = df
            if self.selected_data_source == "ATS_IPC":
                self._load_mock_or_live_data()

    def _populate_strategy_combo(self):
        self.combo_strategy.blockSignals(True)
        self.combo_strategy.clear()

        for st in self.engine.strategies:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            self.combo_strategy.addItem(f"📋 {st_name}", st_id)

        target_id = self.selected_strategy_id
        if not target_id and self.engine.strategies:
            # 优先匹配当前标的归属的策略，若无则默认第一套
            auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
            target_id = auto_st.get("id") if auto_st else self.engine.strategies[0].get("id")
            self.selected_strategy_id = target_id

        for idx in range(self.combo_strategy.count()):
            if self.combo_strategy.itemData(idx) == target_id:
                self.combo_strategy.setCurrentIndex(idx)
                break
        self.combo_strategy.blockSignals(False)

    def switch_to_code(self, code: str, name: Optional[str] = None):
        """外部（如主窗口）动态切换当前监控标的"""
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if not c_clean or c_clean == "000000":
            return
        self.code = c_clean
        if not hasattr(self, '_known_codes'):
            self._known_codes = []
        if self.code not in self._known_codes:
            self._known_codes.append(self.code)

        # 切换标的时重置该标的的 TDX 静默保护状态
        if self.tdx_fetcher:
            self.tdx_fetcher.reset_code_dormancy(self.code)

        if isinstance(name, bool) or not name or name == "未知" or name == c_clean:
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")

        # 自动匹配新标的对应的策略并更新策略下拉框
        auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
        if auto_st:
            self.selected_strategy_id = auto_st.get("id")
            self._populate_strategy_combo()

        # 刷新并同步标的下拉框
        self._populate_code_combo()
        self._sync_eval_spins_for_current_stock()
        if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
            self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分汇总")
        self._load_mock_or_live_data()

    def _populate_code_combo(self):
        self.combo_code.blockSignals(True)
        self.combo_code.clear()

        # 聚合所有可用、历史传入与策略配置的代码，杜绝任何代码丢失
        strat_codes = []
        if self.code and self.code not in strat_codes and self.code != "000000":
            strat_codes.append(self.code)
        for kc in getattr(self, '_known_codes', []):
            if kc and kc not in strat_codes and kc != "000000":
                strat_codes.append(kc)

        # 获取当前选定策略所绑定的目标标的代码
        curr_strat = self.engine.get_strategy_by_id(self.selected_strategy_id) if self.selected_strategy_id else None
        if curr_strat and curr_strat.get("target_codes"):
            for tc in curr_strat.get("target_codes", []):
                c_clean = "".join(filter(str.isdigit, str(tc))).zfill(6)
                if c_clean and c_clean not in strat_codes and c_clean != "000000":
                    strat_codes.append(c_clean)

        for c in self.engine.get_all_target_codes():
            if c and c not in strat_codes and c != "000000":
                strat_codes.append(c)

        if not strat_codes:
            strat_codes = [self.code] if self.code and self.code != "000000" else ["688826"]

        for c in strat_codes:
            c_name = resolve_stock_name(c)
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c)
                if p_name and p_name != "未知" and p_name != c:
                    c_name = p_name
            self.combo_code.addItem(f"{c} {c_name}", c)

        for idx in range(self.combo_code.count()):
            if self.combo_code.itemData(idx) == self.code:
                self.combo_code.setCurrentIndex(idx)
                break
        self.combo_code.blockSignals(False)

    def _sync_eval_spins_for_current_stock(self):
        """根据当前标的的策略规格（stock_spec / price_ladder）自动重置顶部预估价格与换手率，并清空旧节点的校准缓存"""
        if not hasattr(self, 'spin_eval_open') or not hasattr(self, 'spin_eval_price'):
            return

        spec = self.engine.get_stock_ladder_spec(self.code)
        issue_p = float(spec.get("issue_price", 100.0))
        price_ladder = spec.get("price_ladder", [])

        # 默认开盘估价取 +200% 强势基准（如果有价格阶梯则取第2档价格，否则 issue_p * 3.0）
        suggested_open = round(issue_p * 3.0, 2)
        if len(price_ladder) >= 2 and "price" in price_ladder[1]:
            suggested_open = float(price_ladder[1]["price"])
        elif len(price_ladder) >= 1 and "price" in price_ladder[0]:
            suggested_open = float(price_ladder[0]["price"])

        # 默认现价估价取开盘价 * 1.10（较开盘冲高 10%）
        suggested_price = round(suggested_open * 1.10, 2)
        suggested_turnover = 62.5

        # 仅当手动估价勾选开启时才写入 custom_params；在实盘 TDX 直连模式下绝对不注入污染数据！
        if hasattr(self, 'chk_manual_eval') and self.chk_manual_eval.isChecked():
            self.engine.set_node_custom_param(self.code, "node_1_auction", suggested_open)
            self.engine.set_node_custom_param(self.code, "node_2_first_wave", suggested_price)
            self.engine.set_node_custom_param(self.code, "node_3_turnover", suggested_turnover)
        else:
            # 清理历史可能残留的手动覆盖参数
            state = self.engine._get_stock_state(self.code, 0.0)
            custom_p = state.get("node_custom_params", {})
            custom_p.pop("node_1_auction", None)
            custom_p.pop("node_2_first_wave", None)
            custom_p.pop("node_3_turnover", None)

        self.spin_eval_open.blockSignals(True)
        self.spin_eval_price.blockSignals(True)
        self.spin_eval_turnover.blockSignals(True)
        self.spin_eval_open.setValue(suggested_open)
        self.spin_eval_price.setValue(suggested_price)
        self.spin_eval_turnover.setValue(suggested_turnover)
        self.spin_eval_open.blockSignals(False)
        self.spin_eval_price.blockSignals(False)
        self.spin_eval_turnover.blockSignals(False)

    def _on_combo_strategy_changed(self, index: int):
        selected_strat_id = self.combo_strategy.itemData(index)
        self.selected_strategy_id = selected_strat_id
        strategy = self.engine.get_strategy_by_id(selected_strat_id)
        if strategy:
            t_codes = [str(c).zfill(6) for c in strategy.get("target_codes", []) if str(c).strip() not in ("", "000000", "0")]
            # 只有当策略具有专属 target_codes 且当前 code 不在该专属列表中时，才切换为专属代码
            if t_codes and self.code not in t_codes:
                self.code = t_codes[0]
                if not hasattr(self, '_known_codes'):
                    self._known_codes = []
                if self.code not in self._known_codes:
                    self._known_codes.append(self.code)
                self.name = resolve_stock_name(self.code)

            # 刷新并同步标的下拉框
            self._populate_code_combo()

            # 动态重置估价输入框为当前标的基准价格
            self._sync_eval_spins_for_current_stock()

            if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
                self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分明细汇总")

        self._load_mock_or_live_data()

    def _on_combo_code_changed(self, index: int):
        selected_code = self.combo_code.itemData(index)
        if selected_code and selected_code != self.code:
            self.code = str(selected_code).zfill(6)
            if not hasattr(self, '_known_codes'):
                self._known_codes = []
            if self.code not in self._known_codes:
                self._known_codes.append(self.code)

            # 切换标的时重置该标的的 TDX 静默保护状态
            if self.tdx_fetcher:
                self.tdx_fetcher.reset_code_dormancy(self.code)

            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)

            if hasattr(self, 'title_lbl'):
                self.title_lbl.setText(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")
            self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")

            # 自动联动切换到该标的对应的策略
            auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
            if auto_st:
                self.selected_strategy_id = auto_st.get("id")
                self.combo_strategy.blockSignals(True)
                for idx in range(self.combo_strategy.count()):
                    if self.combo_strategy.itemData(idx) == self.selected_strategy_id:
                        self.combo_strategy.setCurrentIndex(idx)
                        break
                self.combo_strategy.blockSignals(False)

            # 动态重置估价输入框为当前标的基准价格
            self._sync_eval_spins_for_current_stock()

            if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
                self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分明细汇总")

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

    def _get_stock_realtime_data_for_code(self, code_str: str) -> Tuple[float, float, float, float, float, float, float, float, str, bool, float]:
        """全自动从 TDX 秒级直连、手动估价输入、self._latest_df 或行情快照解析全量字段"""
        c_clean = str(code_str).zfill(6)
        resolved_name = resolve_stock_name(c_clean)
        parent = self.parent()
        if parent and hasattr(parent, 'get_stock_name'):
            p_name = parent.get_stock_name(c_clean)
            if p_name and p_name != "未知" and p_name != c_clean:
                resolved_name = p_name

        spec = self.engine.get_stock_ladder_spec(c_clean)
        float_mv_yi = float(spec.get("float_mv_yi", 15.0))

        # 1. 只有当用户显式勾选了【✍️ 开启手动估价/异常推演 (默认关闭)】复选框时，才由手动 SpinBox 驱动；否则 100% 走 TDX 秒级直连！
        if hasattr(self, "chk_manual_eval") and self.chk_manual_eval.isChecked() and getattr(self, "selected_data_source", "") == "MANUAL_EVAL":
            op = self.spin_eval_open.value()
            tp = self.spin_eval_price.value()
            to_rate = self.spin_eval_turnover.value()
            hp = max(op, tp, op * 1.13)
            lp = min(op, tp)
            vw = (op + tp) / 2.0
            amt = float(to_rate / 100.0 * float_mv_yi * 1e8)
            b1 = tp
            lc = op
            return op, tp, hp, lp, vw, to_rate, amt, b1, resolved_name, False, lc

        # 2. 优先从 TDX 极速秒级直连获取
        if getattr(self, "selected_data_source", "TDX_REALTIME") == "TDX_REALTIME":
            try:
                tdx_snap = self.tdx_fetcher.fetch_stock_snapshot(c_clean)
                if tdx_snap and float(tdx_snap.get("price", 0.0)) > 0:
                    op = float(tdx_snap.get("open_price", tdx_snap.get("price", 0.0)))
                    tp = float(tdx_snap.get("price", 0.0))
                    hp = float(tdx_snap.get("high_price", tp))
                    lp = float(tdx_snap.get("low_price", tp))
                    vw = float(tdx_snap.get("vwap", tp))
                    to_rate = float(tdx_snap.get("turnover_rate", 0.0))
                    amt = float(tdx_snap.get("amount", 0.0))
                    b1 = float(tdx_snap.get("bid1_price", tp))
                    lc = float(tdx_snap.get("last_close", op))
                    self._update_tdx_status_badge()

                    # 首次加载或切换标的时，不受非交易时段限制，强力获取 TDX 今日 1分钟 K线全量回溯早盘节点 (09:25, 09:40, 10:00, 11:00 等)
                    st_state = self.engine._get_stock_state(c_clean, op)
                    intraday_bars = self.tdx_fetcher.fetch_intraday_bars(c_clean)
                    if not intraday_bars.empty:
                        self.engine.hydrate_from_intraday_df(c_clean, intraday_bars, op)

                    # 同步到界面估价框中方便观察
                    self.spin_eval_open.blockSignals(True)
                    self.spin_eval_price.blockSignals(True)
                    self.spin_eval_turnover.blockSignals(True)
                    self.spin_eval_open.setValue(op)
                    self.spin_eval_price.setValue(tp)
                    self.spin_eval_turnover.setValue(to_rate)
                    self.spin_eval_open.blockSignals(False)
                    self.spin_eval_price.blockSignals(False)
                    self.spin_eval_turnover.blockSignals(False)
                    return op, tp, hp, lp, vw, to_rate, amt, b1, resolved_name, False, lc
            except Exception as e:
                logger.debug(f"TDX 获取 {c_clean} 异常: {e}")

        # 3. 若 TDX 秒级快照未能获取，从 1 分钟 K 线历史或 ATS 推送 df 解析
        curr_df = self._latest_df
        if curr_df is None and parent is not None and hasattr(parent, 'current_df') and parent.current_df is not None:
            curr_df = parent.current_df

        if curr_df is None or curr_df.empty:
            try:
                curr_df = self.tdx_fetcher.fetch_intraday_bars(c_clean)
            except Exception:
                curr_df = None

        if curr_df is not None and not curr_df.empty:
            self.engine.hydrate_from_intraday_df(c_clean, curr_df)

        snap = self.engine.extract_market_snapshot_from_df(curr_df, c_clean)
        open_price = snap["open_price"]
        trade_price = snap["price"]
        high_price = snap["high_price"]
        low_price = snap["low_price"]
        vwap_price = snap["vwap"]
        turnover_rate = snap["turnover_rate"]
        amount_val = snap["amount"]
        bid1_price = snap["bid1_price"]
        last_close = snap.get("last_close", open_price)
        is_unlisted = False

        # 4. 若行情与 K线 历史均尚未产生（如周日或未上市），且用户显式勾选了手动估价，才由界面估价 SpinBox 驱动
        if open_price <= 0 and trade_price <= 0:
            if hasattr(self, "chk_manual_eval") and self.chk_manual_eval.isChecked():
                is_unlisted = True
                open_price = self.spin_eval_open.value()
                trade_price = self.spin_eval_price.value()
                turnover_rate = self.spin_eval_turnover.value()
                high_price = max(open_price, trade_price)
                low_price = min(open_price, trade_price)
                amount_val = float(turnover_rate / 100.0 * float_mv_yi * 1e8)
                bid1_price = trade_price
                vwap_price = round((open_price + trade_price) / 2.0, 2)
                last_close = open_price
            else:
                st_state = self.engine._get_stock_state(c_clean, 0.0)
                open_price = st_state.get("open_price", 0.0)
                trade_price = st_state.get("max_price", open_price)
                high_price = st_state.get("max_price", open_price)
                low_price = st_state.get("min_price", open_price)
                vwap_price = open_price
                last_close = open_price
        elif open_price <= 0 and trade_price > 0:
            open_price = trade_price
            high_price = max(high_price, trade_price)
            low_price = min(low_price, trade_price) if low_price > 0 else trade_price
            vwap_price = trade_price if vwap_price <= 0 else vwap_price
            last_close = open_price if last_close <= 0 else last_close

        return open_price, trade_price, high_price, low_price, vwap_price, turnover_rate, amount_val, bid1_price, resolved_name, is_unlisted, last_close

    def _get_stock_realtime_data(self):
        return self._get_stock_realtime_data_for_code(self.code)

    def _on_open_editor(self):
        dlg = IntradayStrategyEditDialog(parent=self, initial_strategy_id=self.selected_strategy_id, current_code=self.code)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.load_config()
            self._populate_strategy_combo()
            self._populate_code_combo()
            self._load_mock_or_live_data()

    def _load_mock_or_live_data(self):
        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted, last_close = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        self.title_lbl.setText(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")
        self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")

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
            is_unlisted=is_unlisted,
            last_close=last_close
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

        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted, last_close = self._get_stock_realtime_data()
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
            is_unlisted=is_unlisted,
            last_close=last_close
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

    def closeEvent(self, event):
        """窗口关闭时停止所有后台定时器并释放资源，确保应用彻底安全退出"""
        try:
            if hasattr(self, 'timer') and self.timer.isActive():
                self.timer.stop()
            if hasattr(self, 'sim_panel') and hasattr(self.sim_panel, 'replay_timer') and self.sim_panel.replay_timer.isActive():
                self.sim_panel.replay_timer.stop()
            if hasattr(self, 'tdx_fetcher') and self.tdx_fetcher:
                self.tdx_fetcher.disconnect()
        except Exception as e:
            logger.debug(f"closeEvent cleanup: {e}")
        event.accept()


# 向后兼容别名
IntradayStrategyDialog = PinzhunLadderStandaloneWindow


# 补充 PinzhunLaserMonitorWidget 类的定义供 Tab 3 使用（带滚动条位置保持保护）
class PinzhunLaserMonitorWidget(QWidget):
    """
    新股上市专属盯盘与动态评分实操看板组件 (Tab 3)
    全自动由实时推送的 df / TDX 秒级行情获取换手率、成交量、成交额、最高最低价并自动填表打分
    100% 动态自适应不同标的（688826、688835、688836等）的发行价、阶梯价位与流通盘
    """
    score_changed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.code = "688826"
        self._current_spec_code = None
        self._is_updating = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(8)

        # 1. 🔑 关键阈值速查与量能档位面板（动态容器）
        self.card_spec = QGroupBox("🔑 关键阈值速查与量能档位面板")
        self.card_spec.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        self.spec_layout = QGridLayout(self.card_spec)
        self.spec_layout.setContentsMargins(10, 14, 10, 8)
        self.spec_layout.setSpacing(8)

        self._refresh_spec_card(self.code)
        content_layout.addWidget(self.card_spec)

        # 2. 🎯 七节点实盘观察表
        node_group = QGroupBox("🎯 七节点实盘观察表（通过行情/估价自动解析换手率、成交量与价格，自动填表打分）")
        node_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_layout = QVBoxLayout(node_group)
        node_layout.setContentsMargins(6, 14, 6, 6)

        top_bar = QHBoxLayout()
        lbl_hint = QLabel("⚡ 全自动模式：数据根据行情/估价自动计算；您也可在【节点评分】列手动微调分值。")
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
            "实际观察值\n(实时df/估价自动获取)", "信号判定\n强/中/弱", "节点评分\n(0-10分)", "备注/应对"
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

        self.lbl_guide = QLabel()
        self.lbl_guide.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_guide.setStyleSheet("color: #b0b0c8; font-size: 8.5pt; line-height: 140%;")
        self.lbl_guide.setWordWrap(True)
        self._refresh_guide_text(self.code)
        guide_layout.addWidget(self.lbl_guide)
        content_layout.addWidget(guide_group)

        self.scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.scroll_area)

    def _refresh_spec_card(self, code: str):
        """根据当前标的重新渲染顶部阈值卡片（支持5档/6档价格阶梯与不同流通盘）"""
        c_clean = str(code).zfill(6)
        spec = self.engine.get_stock_ladder_spec(c_clean)
        issue_p = float(spec.get("issue_price", 100.0))
        float_shares_wan = float(spec.get("float_shares_wan", 1000.0))
        float_mv = float(spec.get("float_mv_yi", 15.0))
        lottery = spec.get("lottery_rate", "--")
        name = spec.get("name", resolve_stock_name(c_clean))

        self.card_spec.setTitle(
            f"🔑 【{name}】关键阈值速查（发行价 {issue_p:.2f} 元 | 流通股≈{float_shares_wan:.2f}万股 | 流通市值≈{float_mv:.2f}亿 | 中签率 {lottery}）"
        )

        # 清空已有子控件
        while self.spec_layout.count():
            item = self.spec_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        price_ladder = spec.get("price_ladder", [])
        colors = ["#00ff88", "#ffd700", "#ffaa44", "#ff5555", "#ff00ff", "#00ffff"]
        cols = max(len(price_ladder), 5)

        for i, ld in enumerate(price_ladder):
            p_val = float(ld.get("price", 0.0))
            p_name = ld.get("name", "")
            p_mean = ld.get("meaning", "")
            lbl = QLabel(f"<b>{p_name}</b>: {p_val:.2f}元 ({p_mean})")
            c_idx = i % len(colors)
            lbl.setStyleSheet(f"color: {colors[c_idx]}; font-size: 9pt; {'font-weight: bold;' if i==1 else ''}")
            self.spec_layout.addWidget(lbl, 0, i)

        lbl_t1 = QLabel("<b>换手档位</b>: 弱(<40%) | 标准(50-70%健康) | 高(70-90%充分) | 极高(>90%过热)")
        lbl_t1.setStyleSheet("color: #a0a0c0; font-size: 9pt;")
        
        self.lbl_intensity = QLabel(f"<b>资金强度</b>: 成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强 [当前: --]")
        self.lbl_intensity.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 9pt;")

        span_left = max(1, cols - 2)
        self.spec_layout.addWidget(lbl_t1, 1, 0, 1, span_left)
        self.spec_layout.addWidget(self.lbl_intensity, 1, span_left, 1, cols - span_left)
        self._current_spec_code = c_clean

    def _refresh_guide_text(self, code: str):
        c_clean = str(code).zfill(6)
        spec = self.engine.get_stock_ladder_spec(c_clean)
        float_mv = float(spec.get("float_mv_yi", 15.0))
        guide_txt = (
            f"1. <b>节点观察</b>: 每个时间节点到达时，系统自动抓取价格/涨幅/换手/量能/VWAP；<br>"
            f"2. <b>信号判定</b>: 自动判定 \"强\" / \"中\" / \"弱\" 并高亮呈现；<br>"
            f"3. <b>节点评分</b>: 强=8-10分，中=5-7分，弱=0-4分；<br>"
            f"4. <b>加权得分</b>: 自动计算 (加权得分 = 节点分 × 权重)；<br>"
            f"5. <b>形态判定</b>: <b>综合得分≥8.0</b> → A型超强趋势(★关注次日竞价接力)；<b>6.5-8.0</b> → B型(★观察回踩承接)；<b>5.0-6.5</b> → C型(★冲高兑现)；<b><5.0</b> → D/E型(★弱势回避)；<br>"
            f"6. <b>重点监控</b>: <b>成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强</b>；<b>收盘/最高 > 90% 为超强锁仓</b>；<br>"
            f"7. <b>同板块联动</b>: 同步观察关联板块龙头走势，确认资金协同性与做多共识。"
        )
        self.lbl_guide.setText(guide_txt)

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
        """全面刷新盯盘看板数据（带全局滚动条锁定保护）"""
        self.code = code
        c_clean = str(code).zfill(6)
        if getattr(self, "_current_spec_code", None) != c_clean:
            self._refresh_spec_card(c_clean)
            self._refresh_guide_text(c_clean)

        # 保护外层 ScrollArea 滚动条位置
        outer_sb = self.scroll_area.verticalScrollBar()
        saved_outer_pos = outer_sb.value()

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

        spec = self.engine.get_stock_ladder_spec(code)
        float_mv = float(spec.get("float_mv_yi", 14.24))
        intensity_val = res.get("intensity_ratio", 0.0)
        int_str = f"{intensity_val:.2f}x"
        int_color = "#00ff88" if intensity_val >= 2.5 else "#38bdf8"
        if hasattr(self, 'lbl_intensity'):
            self.lbl_intensity.setText(
                f"<b>资金强度</b>: 成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强 [当前: <font color='{int_color}'>{int_str}</font>]"
            )

        node_results = res.get("node_results", [])
        if self.table_nodes.rowCount() != len(node_results):
            self.table_nodes.setRowCount(len(node_results))

        self._is_updating = True

        for row, nr in enumerate(node_results):
            n_id = nr["node_id"]
            _set_or_update_table_item(self.table_nodes, row, 0, nr["node_num"], align=Qt.AlignmentFlag.AlignCenter)

            fg_t = QColor("#00ff88") if nr["is_active"] else (QColor("#888899") if nr["is_completed"] else None)
            bg_t = QColor("#1a2e24") if nr["is_active"] else None
            _set_or_update_table_item(self.table_nodes, row, 1, f"{nr['name']}\n({nr['time_str']})", fg_color=fg_t, bg_color=bg_t, align=Qt.AlignmentFlag.AlignCenter)

            _set_or_update_table_item(self.table_nodes, row, 2, nr["focus"], tooltip=nr["focus"])
            _set_or_update_table_item(self.table_nodes, row, 3, nr["strong_signals"], fg_color="#00ff88", tooltip=nr["strong_signals"])
            _set_or_update_table_item(self.table_nodes, row, 4, nr["risk_signals"], fg_color="#ff5555", tooltip=nr["risk_signals"])
            _set_or_update_table_item(self.table_nodes, row, 5, nr["observed_val"], fg_color="#ffd700", tooltip=nr["observed_val"])

            judg = nr["judgment"]
            fg_j = QColor("#00ff88") if judg == "强" else (QColor("#38bdf8") if judg == "中" else QColor("#ff4444"))
            bg_j = QColor("#163322") if judg == "强" else (QColor("#162838") if judg == "中" else QColor("#331616"))
            _set_or_update_table_item(self.table_nodes, row, 6, judg, fg_color=fg_j, bg_color=bg_j, align=Qt.AlignmentFlag.AlignCenter)

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

            remark_text = f"{nr['remarks']} | {nr['action_guide']}"
            _set_or_update_table_item(self.table_nodes, row, 8, remark_text, tooltip=remark_text)

        if self.table_summary.rowCount() != 10:
            self.table_summary.setRowCount(10)

        tot_score = res.get("total_weighted_score", 0.0)
        pattern = res.get("pattern", "--")
        t1_advice = res.get("t1_advice", "--")
        pat_color = res.get("pattern_color", "#00ff88")

        for row, nr in enumerate(node_results):
            _set_or_update_table_item(self.table_summary, row, 0, f"{nr['name']}({nr['time_str']})")
            _set_or_update_table_item(self.table_summary, row, 1, nr["time_str"], align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 2, f"{nr['final_score']:.1f}", align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 3, nr["weight_pct"], fg_color="#38bdf8", align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 4, f"{nr['weighted_score']:.2f}", align=Qt.AlignmentFlag.AlignCenter)

            if row == 0:
                _set_or_update_table_item(self.table_summary, row, 5, f"{res.get('gain_from_issue', 0.0):+.1f}%", fg_color="#00ff88")
                _set_or_update_table_item(self.table_summary, row, 6, f"{res.get('turnover_rate', 0.0):.1f}%")
                _set_or_update_table_item(self.table_summary, row, 7, f"{res.get('close_high_ratio', 1.0)*100:.1f}%")
                _set_or_update_table_item(self.table_summary, row, 8, pattern, fg_color=pat_color, font=QFont("Arial", 9, QFont.Weight.Bold))
            else:
                for c in range(5, 9):
                    _set_or_update_table_item(self.table_summary, row, c, "")

        r_sum = 7
        score_fg = "#ff0055" if tot_score < 5 else ("#00ff88" if tot_score >= 8 else "#ffd700")
        _set_or_update_table_item(self.table_summary, r_sum, 0, "综合得分", fg_color="#38bdf8", font=QFont("Arial", 9, QFont.Weight.Bold))
        _set_or_update_table_item(self.table_summary, r_sum, 1, "合计", align=Qt.AlignmentFlag.AlignCenter)
        _set_or_update_table_item(self.table_summary, r_sum, 2, "")
        _set_or_update_table_item(self.table_summary, r_sum, 3, "100%", fg_color="#38bdf8", align=Qt.AlignmentFlag.AlignCenter)
        _set_or_update_table_item(self.table_summary, r_sum, 4, f"{tot_score:.2f}", fg_color=score_fg, bg_color="#2d2218", font=QFont("Arial", 10, QFont.Weight.Bold), align=Qt.AlignmentFlag.AlignCenter)
        for c in range(5, 9):
            _set_or_update_table_item(self.table_summary, r_sum, c, "")

        r_pat = 8
        _set_or_update_table_item(self.table_summary, r_pat, 0, "形态判定", font=QFont("Arial", 9, QFont.Weight.Bold))
        for c in range(1, 8):
            _set_or_update_table_item(self.table_summary, r_pat, c, "")
        _set_or_update_table_item(self.table_summary, r_pat, 8, f"【{pattern}】", fg_color=pat_color, bg_color="#22182d", font=QFont("Arial", 10, QFont.Weight.Bold))

        r_t1 = 9
        _set_or_update_table_item(self.table_summary, r_t1, 0, "T+1建议", font=QFont("Arial", 9, QFont.Weight.Bold))
        for c in range(1, 8):
            _set_or_update_table_item(self.table_summary, r_t1, c, "")
        _set_or_update_table_item(self.table_summary, r_t1, 8, t1_advice, fg_color=pat_color, font=QFont("Arial", 9, QFont.Weight.Bold))

        self._is_updating = False

        # 恢复外层滚动条位置
        outer_sb.setValue(saved_outer_pos)

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

    def _get_current_code(self) -> str:
        parent = self.parent()
        while parent:
            if hasattr(parent, 'code') and getattr(parent, 'code'):
                return str(getattr(parent, 'code')).zfill(6)
            parent = parent.parent()
        return "688826"

    def _ensure_scenario_df(self):
        sc_type = self.combo_scenario.currentData()
        cur_code = self._get_current_code()
        last_code = getattr(self, "_last_code", None)
        if self.sim_df is None or getattr(self, "_last_sc_type", None) != sc_type or last_code != cur_code:
            self.sim_df = self.engine.generate_scenario_intraday_df(sc_type, code=cur_code)
            self._last_sc_type = sc_type
            self._last_code = cur_code
            self.slider_progress.setMaximum(len(self.sim_df) - 1)
        return self.sim_df

    def _on_run_full_backtest(self):
        """一键全天秒级回测"""
        cur_code = self._get_current_code()
        spec = self.engine.get_stock_ladder_spec(cur_code)
        issue_p = float(spec.get("issue_price", 100.0))
        float_mv = float(spec.get("float_mv_yi", 15.0))
        stock_name = spec.get("name", resolve_stock_name(cur_code))

        df = self._ensure_scenario_df()
        res = self.engine.run_full_day_backtest(cur_code, df)

        final_eval = res.get("final_evaluation", {})
        sigs = res.get("signals", [])
        logs = res.get("execution_logs", [])
        rem_ratio = res.get("remaining_ratio", 0.0)

        report = (
            f"=== ⚡ 【{cur_code} {stock_name}】全天分时模拟回测报告 ===\n"
            f"【情景选择】: {self.combo_scenario.currentText()}\n"
            f"【开盘基准】: {res.get('open_price', 0):.2f} 元 | 发行价: {issue_p:.2f} 元\n"
            f"【收盘价格】: {final_eval.get('price', 0):.2f} 元 (较开盘 {final_eval.get('gain_from_open', 0):+.1f}% | 较发行价 {final_eval.get('gain_from_issue', 0):+.1f}%)\n"
            f"【全天最高】: {final_eval.get('high_price', 0):.2f} 元 | 最低: {final_eval.get('low_price', 0):.2f} 元 | VWAP均价: {final_eval.get('vwap', 0):.2f} 元\n"
            f"【全天换手】: {final_eval.get('turnover_rate', 0):.1f}% | 成交金额: {final_eval.get('amount_yi', 0):.2f} 亿元\n"
            f"【资金强度】: {final_eval.get('intensity_ratio', 0):.2f}x (流通市值{float_mv:.2f}亿) | 锁仓比例: {final_eval.get('close_high_ratio', 1)*100:.1f}%\n"
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
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    apply_dark_theme(app)

    # 启用定时器周期唤醒 Python 解释器处理 Ctrl+C 信号
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(300)

    engine = IntradayStrategyEngine.get_instance()
    default_code = engine.get_default_target_code() or "688826"
    win = PinzhunLadderStandaloneWindow(code=default_code)
    win.show()
    sys.exit(app.exec())
