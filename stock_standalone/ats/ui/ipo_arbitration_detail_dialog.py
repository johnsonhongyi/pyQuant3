# -*- coding: utf-8 -*-
"""
集中仲裁与操作建议透视详情窗 (极速复用模式)
- 遵循单例极速复用模式 (Reusable Singleton Window Pattern)，毫秒级就地刷新无缝切换
- 支持从《新股次新集中交易指挥室》与《新股次新超短检测工具》双击“集中仲裁”或“操作建议”直接秒级唤出
- 聚合展示：战术角色分工、山外有山比对结果、集中仲裁深度决议、10d VWAP 动能偏离与买错立斩纪律
"""

import logging
from typing import Optional, Dict, Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut, QClipboard, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame, QGroupBox, QGridLayout, QMessageBox
)

from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOOrderDirective
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal
from ats.ui.styles import load_config_node, save_config_node

logger = logging.getLogger("IPOArbitrationDetailDialog")

# 角色中文映射
ROLE_CN_MAP = {
    "LEADER": "🥇 领头羊",
    "VANGUARD": "🥈 梯队前锋",
    "FOLLOWER": "🥉 后排跟风",
    "CLIMAX_EXIT": "🚨 高潮平仓",
    "PANIC_DEFENSE": "🛡️ 全局避险",
    "STOP_LOSS": "⛔ 买错立斩",
    "CLIMAX_DEFENSE": "🌋 高潮避险",
}

ROLE_COLOR_MAP = {
    "LEADER": "#ffaa00",
    "VANGUARD": "#00e5ff",
    "FOLLOWER": "#8f93a8",
    "CLIMAX_EXIT": "#ff3333",
    "PANIC_DEFENSE": "#ff7733",
    "STOP_LOSS": "#ff4444",
    "CLIMAX_DEFENSE": "#ffaa33",
}


class IPOArbitrationDetailDialog(QDialog):
    """
    集中仲裁与操作建议详情窗 (极速复用模式)
    """
    _shared_instance: Optional['IPOArbitrationDetailDialog'] = None

    @classmethod
    def get_instance(cls, parent=None) -> 'IPOArbitrationDetailDialog':
        """获取全局复用实例 (保证全系统只有一个常驻详情窗，杜绝多次弹窗卡顿)"""
        if cls._shared_instance is None:
            cls._shared_instance = cls(parent=None)
        return cls._shared_instance

    @classmethod
    def show_or_update(
        cls,
        code: str,
        signal_obj: Optional[VWAPDetectorSignal] = None,
        directive_obj: Optional[IPOOrderDirective] = None,
        parent=None
    ) -> 'IPOArbitrationDetailDialog':
        """
        【极速复用入口】：单例模式秒级刷新并带到前台，无需重新销毁重建窗口
        """
        dlg = cls.get_instance(parent)
        dlg.update_content(code, signal_obj=signal_obj, directive_obj=directive_obj)
        if not dlg.isVisible():
            dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def __init__(self, parent=None):
        super().__init__(None)  # 独立无父窗口，支持副屏任意拖拽
        self.setWindowTitle("🎯 集中仲裁与操作建议透视详情窗 (极速复用模式)")
        self.setMinimumSize(620, 520)
        self.resize(720, 580)
        self.current_code: str = ""
        self.current_name: str = ""
        self.current_signal: Optional[VWAPDetectorSignal] = None
        self.current_directive: Optional[IPOOrderDirective] = None

        self._init_ui()
        self._load_geometry()

        # 快捷键支持
        QShortcut(QKeySequence("Escape"), self, self.hide)
        QShortcut(QKeySequence("F"), self, self._on_f_linkage)
        QShortcut(QKeySequence("Space"), self, self._on_space_open_sbc)

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0d0e15;
                color: #ffffff;
            }
            QLabel {
                color: #e2e2e5;
                font-size: 9pt;
            }
            QGroupBox {
                border: 1px solid #232536;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #00e5ff;
                padding-top: 12px;
                background-color: #121420;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #1a1c29;
                border: 1px solid #33374d;
                border-radius: 4px;
                color: #ffffff;
                font-size: 9pt;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #26293d;
                border-color: #00e5ff;
            }
            QTextBrowser {
                background-color: #0b0c12;
                border: 1px solid #1f2233;
                border-radius: 4px;
                color: #e2e2e5;
                font-size: 9.5pt;
                line-height: 1.5;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── 1. 顶部标的战况核心胶囊栏 ──
        top_frame = QFrame()
        top_frame.setStyleSheet("background-color: #151724; border: 1px solid #272a3e; border-radius: 6px; padding: 6px;")
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(8, 6, 8, 6)
        top_layout.setSpacing(12)

        self.lbl_code_name = QLabel("代码: -- | 名称: --")
        self.lbl_code_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_code_name.setStyleSheet("color: #ffffff;")
        top_layout.addWidget(self.lbl_code_name)

        self.lbl_price = QLabel("现价: --")
        self.lbl_price.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.lbl_price.setStyleSheet("color: #ff4444;")
        top_layout.addWidget(self.lbl_price)

        self.lbl_role_tag = QLabel("战术角色: --")
        self.lbl_role_tag.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.lbl_role_tag.setStyleSheet("background-color: #261a14; border: 1px solid #5a351e; border-radius: 4px; padding: 3px 8px; color: #ffaa00;")
        top_layout.addWidget(self.lbl_role_tag)

        self.lbl_race_info = QLabel("赛马名次: -- | 动能分: --")
        self.lbl_race_info.setStyleSheet("color: #66fcf1; font-weight: bold;")
        top_layout.addWidget(self.lbl_race_info)

        top_layout.addStretch()
        layout.addWidget(top_frame)

        # ── 2. 核心主卡片：集中仲裁与山外有山决议深度报告 ──
        grp_arbitration = QGroupBox("🎯 集中交易仲裁与山外有山全局调度报告")
        v_arb = QVBoxLayout(grp_arbitration)
        v_arb.setContentsMargins(10, 10, 10, 10)
        v_arb.setSpacing(8)

        # 决议大号高亮胶囊
        self.lbl_action_badge = QLabel("交易决议: 计算中...")
        self.lbl_action_badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_action_badge.setStyleSheet("background-color: #122118; border: 1px solid #1e452e; border-radius: 4px; padding: 4px 10px; color: #00ff88;")
        v_arb.addWidget(self.lbl_action_badge)

        # 决议详细说明正文浏览器
        self.txt_arbitration_desc = QTextBrowser()
        self.txt_arbitration_desc.setOpenExternalLinks(False)
        v_arb.addWidget(self.txt_arbitration_desc)
        layout.addWidget(grp_arbitration, 3)

        # ── 3. 次级卡片：VWAP 动能态势与买错立斩纪律 ──
        grp_vwap = QGroupBox("⚡ 10d VWAP 动能结构与出局斩仓纪律 (预下单逻辑)")
        grid_vwap = QGridLayout(grp_vwap)
        grid_vwap.setContentsMargins(10, 10, 10, 10)
        grid_vwap.setHorizontalSpacing(14)
        grid_vwap.setVerticalSpacing(8)

        self.lbl_vwap_line = QLabel("10d VWAP 成本线: --")
        grid_vwap.addWidget(self.lbl_vwap_line, 0, 0)

        self.lbl_vwap_bias = QLabel("VWAP 偏离度: --")
        grid_vwap.addWidget(self.lbl_vwap_bias, 0, 1)

        self.lbl_vwap_shape = QLabel("走势结构形态: --")
        grid_vwap.addWidget(self.lbl_vwap_shape, 1, 0)

        self.lbl_launch_time = QLabel("启动时点: --")
        grid_vwap.addWidget(self.lbl_launch_time, 1, 1)

        self.lbl_stop_loss = QLabel("极窄止损出局位: --")
        self.lbl_stop_loss.setStyleSheet("color: #ff5555; font-weight: bold;")
        grid_vwap.addWidget(self.lbl_stop_loss, 2, 0)

        self.lbl_discipline = QLabel("出局铁律: 买错跌破 VWAP 0.6% 严守纪律立即出局")
        self.lbl_discipline.setStyleSheet("color: #ff7733; font-weight: bold;")
        grid_vwap.addWidget(self.lbl_discipline, 2, 1)

        layout.addWidget(grp_vwap, 2)

        # ── 4. 底部快捷操作行动栏 ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        btn_sbc = QPushButton("📈 调出 SBC 走势 [空格]")
        btn_sbc.setToolTip("查看该标的 10d 分时与 VWAP 动能走势")
        btn_sbc.clicked.connect(self._on_space_open_sbc)
        bottom_bar.addWidget(btn_sbc)

        btn_tdx = QPushButton("🔗 联动通达信看盘 [F]")
        btn_tdx.setToolTip("将当前标的直接联动到外部通达信看盘界面")
        btn_tdx.clicked.connect(self._on_f_linkage)
        bottom_bar.addWidget(btn_tdx)

        btn_copy = QPushButton("📋 复制决议文本")
        btn_copy.setToolTip("将完整的集中仲裁分析文本复制到剪贴板")
        btn_copy.clicked.connect(self._on_copy_text)
        bottom_bar.addWidget(btn_copy)

        bottom_bar.addStretch()

        btn_close = QPushButton("关闭 [Esc]")
        btn_close.clicked.connect(self.hide)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def update_content(
        self,
        code: str,
        signal_obj: Optional[VWAPDetectorSignal] = None,
        directive_obj: Optional[IPOOrderDirective] = None
    ):
        """
        【极速就地刷新】：毫秒级更新卡片全部数据，杜绝窗口重建
        """
        clean_code = "".join(ch for ch in str(code) if ch.isdigit()).zfill(6)
        self.current_code = clean_code
        self.current_signal = signal_obj
        self.current_directive = directive_obj

        # 1. 尝试从 IPOTradingCenter 获取最新信号与标的上下文
        trading_center = IPOTradingCenter.get_instance()
        if self.current_signal is None:
            if clean_code in trading_center._reports_cache:
                self.current_signal = trading_center._reports_cache.get(clean_code)
            else:
                for s in trading_center._ranked_cache:
                    if s.code == clean_code:
                        self.current_signal = s
                        break

        sig = self.current_signal
        name = (sig.name if sig else (directive_obj.name if directive_obj else clean_code)) or clean_code
        self.current_name = name

        price = sig.price if sig and sig.price > 0 else (directive_obj.price if directive_obj else 0.0)
        self.lbl_code_name.setText(f"代码: {clean_code} | 名称: {name}")
        self.lbl_price.setText(f"现价: ¥{price:.2f}" if price > 0 else "现价: --")

        # 2. 战术角色与赛马信息
        role_raw = (sig.global_fleet_role if sig else "") or "--"
        role_cn = ROLE_CN_MAP.get(role_raw, role_raw or "--")
        role_color = ROLE_COLOR_MAP.get(role_raw, "#ffaa00")
        self.lbl_role_tag.setText(f"战术角色: {role_cn}")
        self.lbl_role_tag.setStyleSheet(
            f"background-color: #1c1a24; border: 1px solid {role_color}; "
            f"border-radius: 4px; padding: 3px 8px; color: {role_color}; font-weight: bold;"
        )

        rank_str = str(sig.horse_race_rank) if sig and sig.horse_race_rank > 0 else "--"
        score_str = f"{sig.horse_race_score:.0f}" if sig and sig.horse_race_score > 0 else "--"
        self.lbl_race_info.setText(f"赛马天梯: 第 {rank_str} 名 | 动能分: {score_str}")

        # 3. 集中仲裁与山外有山决议
        desc_text = ""
        action_text = ""
        size_pct_str = ""

        if directive_obj:
            action_text = directive_obj.action
            size_pct_str = f"{directive_obj.size_pct:.0f}%"
            desc_text = directive_obj.reason
        elif sig and sig.global_arbitration_desc:
            desc_text = sig.global_arbitration_desc
        elif sig and sig.signal_desc:
            desc_text = sig.signal_desc
        else:
            desc_text = "当前标的已纳入监控池，等待下一次全池统筹评估。"

        # 生成决议 Badge 标签
        badge_text = f"🚢 全局决议: {role_cn}"
        if size_pct_str:
            badge_text += f" | 建议仓位: {size_pct_str}"
        self.lbl_action_badge.setText(badge_text)

        # 详细文本富文本展示
        html_content = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #e2e2e5;">
            <p style="margin-top: 0px; font-size: 11pt; color: #66fcf1; font-weight: bold;">
                📌 【集中仲裁判定与山外有山依据】
            </p>
            <p style="background-color: #121522; padding: 8px 12px; border-left: 3px solid #00e5ff; border-radius: 3px; font-size: 10pt; color: #ffffff;">
                {desc_text}
            </p>
            <p style="color: #9aa0a6; font-size: 8.5pt; margin-bottom: 0px;">
                * 决议由集中交易中心融合全池各守护线程提交数据、领头羊动能与全市场情绪综合仲裁生成。
            </p>
        </div>
        """
        self.txt_arbitration_desc.setHtml(html_content)

        # 4. VWAP 动能与极窄止损
        if sig:
            vwap_val = getattr(sig, "vwap", 0.0) or getattr(sig, "vwap_price", 0.0)
            bias_val = getattr(sig, "vwap_diff_pct", 0.0) or getattr(sig, "vwap_bias_pct", 0.0)
            self.lbl_vwap_line.setText(f"10d VWAP 成本线: ¥{vwap_val:.2f}" if vwap_val > 0 else "10d VWAP 成本线: --")
            bias_color = "#ff4444" if bias_val > 0 else "#00ff88"
            self.lbl_vwap_bias.setText(f"VWAP 偏离度: {bias_val:+.2f}%")
            self.lbl_vwap_bias.setStyleSheet(f"color: {bias_color}; font-weight: bold;")

            struct_val = getattr(sig, "structure_tag", "") or getattr(sig, "vwap_structure", "") or "--"
            self.lbl_vwap_shape.setText(f"走势结构形态: {struct_val}")
            self.lbl_launch_time.setText(f"启动时点: {sig.launch_time_str or '--'}")

            sl_price = getattr(sig, "stop_loss_price", 0.0)
            if sl_price > 0:
                self.lbl_stop_loss.setText(f"极窄止损出局位: ¥{sl_price:.2f} (跌破即立斩)")
            else:
                self.lbl_stop_loss.setText("极窄止损出局位: 成本价 * 0.994")
        else:
            self.lbl_vwap_line.setText("10d VWAP 成本线: --")
            self.lbl_vwap_bias.setText("VWAP 偏离度: --")
            self.lbl_vwap_shape.setText("走势结构形态: --")
            self.lbl_launch_time.setText("启动时点: --")
            self.lbl_stop_loss.setText("极窄止损出局位: 成本价 * 0.994")

    def _on_space_open_sbc(self):
        """调出 SBC 10d VWAP 走势"""
        if not self.current_code:
            return
        try:
            from ats.ui.sbc_launcher import open_sbc_for_stock
            open_sbc_for_stock(self.current_code)
        except Exception as e:
            logger.debug(f"调出 SBC 异常: {e}")

    def _on_f_linkage(self):
        """联动通达信看盘"""
        if not self.current_code:
            return
        try:
            from linkage_service import get_link_manager
            lm = get_link_manager()
            if lm:
                lm.push(self.current_code, flags={'tdx': True, 'ths': True, 'dfcf': False}, auto=False)
        except Exception as e:
            logger.debug(f"联动通达信异常: {e}")

    def _on_copy_text(self):
        """将完整决议文本复制到剪贴板"""
        plain_text = (
            f"【集中仲裁决议详情】\n"
            f"股票: {self.current_code} {self.current_name}\n"
            f"{self.lbl_price.text()}\n"
            f"{self.lbl_role_tag.text()} | {self.lbl_race_info.text()}\n"
            f"{self.lbl_action_badge.text()}\n\n"
            f"决议依据:\n{self.txt_arbitration_desc.toPlainText()}\n\n"
            f"{self.lbl_vwap_line.text()} | {self.lbl_vwap_bias.text()}\n"
            f"{self.lbl_vwap_shape.text()} | {self.lbl_launch_time.text()}\n"
            f"{self.lbl_stop_loss.text()}\n"
            f"{self.lbl_discipline.text()}"
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(plain_text)
            QMessageBox.information(self, "复制成功", "集中仲裁与操作建议详情已成功复制到剪贴板！")

    def closeEvent(self, event):
        """拦截关闭事件，改为隐藏，复用单例实例，并记住窗口位置"""
        self._save_geometry()
        self.hide()
        event.ignore()

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    def _load_geometry(self):
        """从本地恢复窗口大小与位置"""
        try:
            geo = load_config_node("ipo_arbitration_detail_geometry")
            if geo and isinstance(geo, dict):
                x = geo.get("x", 200)
                y = geo.get("y", 200)
                w = geo.get("width", 720)
                h = geo.get("height", 580)
                self.setGeometry(x, y, w, h)
        except Exception:
            pass

    def _save_geometry(self):
        """保存当前窗口位置与尺寸"""
        try:
            g = self.geometry()
            geo_data = {
                "x": g.x(),
                "y": g.y(),
                "width": g.width(),
                "height": g.height()
            }
            save_config_node("ipo_arbitration_detail_geometry", geo_data)
        except Exception:
            pass
