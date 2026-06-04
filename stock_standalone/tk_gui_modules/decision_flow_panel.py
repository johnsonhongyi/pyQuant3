# -*- coding: utf-8 -*-
import json
import os
import time
import sys
import traceback
import threading
from datetime import datetime
from typing import Any, Optional

from PyQt6 import QtWidgets, QtCore, QtGui
from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory
from stock_logic_utils import toast_message as legacy_toast

# Shadow legacy toast_message to prevent cross-frame Tkinter GIL thread crashes in PyQt windows
def toast_message(parent, text, duration=1500):
    try:
        from PyQt6 import QtWidgets, QtCore
        active_win = QtWidgets.QApplication.activeWindow()
        if active_win:
            QtCore.QTimer.singleShot(0, lambda: _show_qt_toast(active_win, text, duration))
            return
    except Exception as ex:
        pass
    try:
        legacy_toast(parent, text, duration)
    except Exception:
        pass

def _show_qt_toast(parent_win, text, duration=1500):
    try:
        from PyQt6 import QtWidgets, QtCore
        toast = QtWidgets.QFrame(parent_win)
        toast.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 190);
                color: white;
                border-radius: 5px;
                padding: 6px 12px;
            }
            QLabel {
                color: white;
                font-size: 11px;
                font-family: "Microsoft YaHei";
            }
        """)
        toast.setWindowFlags(QtCore.Qt.WindowType.ToolTip | QtCore.Qt.WindowType.FramelessWindowHint)
        toast.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        toast.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        layout = QtWidgets.QHBoxLayout(toast)
        layout.setContentsMargins(10, 5, 10, 5)
        lbl = QtWidgets.QLabel(text, toast)
        layout.addWidget(lbl)
        
        toast.adjustSize()
        geo = parent_win.geometry()
        center_x = geo.x() + (geo.width() - toast.width()) // 2
        center_y = geo.y() + (geo.height() - toast.height()) // 2
        toast.move(center_x, center_y)
        
        toast.show()
        QtCore.QTimer.singleShot(duration, toast.close)
    except Exception as e:
        try:
            logger.error(f"Failed to show shadow Qt toast: {e}")
        except Exception:
            pass

logger = LoggerFactory.getLogger("instock_TK.DecisionFlowPanel")
from sys_utils import get_app_root

class SortableTableWidgetItem(QtWidgets.QTableWidgetItem):
    def __init__(self, text: str, value: Any = None):
        super().__init__(str(text))
        self.value = value

    def __lt__(self, other):
        if not isinstance(other, SortableTableWidgetItem):
            return super().__lt__(other)
        v1 = self.value
        v2 = other.value
        if v1 is None and v2 is None:
            return self.text() < other.text()
        if v1 is None:
            return True
        if v2 is None:
            return False
        try:
            return float(v1) < float(v2)
        except (ValueError, TypeError):
            pass
        return str(v1) < str(v2)

class SystemWorkflowDialog(QtWidgets.QDialog):
    """🚀 交易系统操作指南与风控参数详解 (Operation Guide & Risk Limits Guide)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚀 交易系统操作指南与风控参数说明")
        self.resize(800, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #E2E2E6;
            }
            QTextBrowser {
                background-color: #16161A;
                border: 1px solid #232328;
                color: #D2D2D6;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
            }
            QPushButton {
                background-color: #1E1E24;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 5px 12px;
                color: #C2C2C6;
            }
            QPushButton:hover {
                background-color: #2E2E38;
                border-color: #00E676;
                color: #FFFFFF;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(self)
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser)
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        self._load_plan()
        
    def _load_plan(self):
        html_content = """<html>
<head>
<style>
    body {
        background-color: #121214;
        color: #E2E2E6;
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 11px;
        margin: 15px;
        line-height: 1.6;
    }
    .header-box {
        background: linear-gradient(135deg, #1A1A1F 0%, #121214 100%);
        border: 1px solid #232328;
        border-left: 4px solid #00E676;
        border-radius: 4px;
        padding: 12px;
        margin-bottom: 15px;
    }
    .header-title {
        color: #00E676;
        font-size: 14px;
        font-weight: bold;
        margin: 0 0 5px 0;
    }
    .header-subtitle {
        color: #88888D;
        font-size: 10px;
        margin: 0;
    }
    h2 {
        color: #00E5FF;
        font-size: 12px;
        border-bottom: 1px solid #232328;
        padding-bottom: 4px;
        margin-top: 18px;
        margin-bottom: 8px;
    }
    .mode-card {
        background-color: #16161A;
        border: 1px solid #232328;
        border-radius: 4px;
        padding: 10px;
        margin-bottom: 8px;
    }
    .badge {
        display: inline-block;
        padding: 2px 6px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 9px;
        margin-right: 6px;
    }
    .badge-observe { background-color: #2E2E35; color: #A0A0A5; border: 1px solid #444; }
    .badge-paper { background-color: #1E293B; color: #38BDF8; border: 1px solid #0284C7; }
    .badge-confirm { background-color: #3B2E1E; color: #F59E0B; border: 1px solid #D97706; }
    .badge-live { background-color: #1B3B22; color: #10B981; border: 1px solid #059669; }
    
    .param-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 10px;
        background-color: #16161A;
        border: 1px solid #232328;
    }
    .param-table th {
        background-color: #1E1E24;
        color: #00E5FF;
        font-weight: bold;
        text-align: left;
        padding: 8px 6px;
        border-bottom: 2px solid #282830;
    }
    .param-table td {
        padding: 8px 6px;
        border-bottom: 1px solid #232328;
        color: #D2D2D6;
        vertical-align: top;
    }
    .param-table tr:nth-child(even) {
        background-color: #1A1A1F;
    }
    .highlight-glow {
        color: #00E676;
        font-weight: bold;
    }
    .highlight-warn {
        color: #FF9100;
        font-weight: bold;
    }
    .highlight-danger {
        color: #FF1744;
        font-weight: bold;
    }
    .bullet-list {
        margin-left: 15px;
        padding-left: 0;
    }
    .bullet-list li {
        margin-bottom: 4px;
        color: #C2C2C6;
    }
</style>
</head>
<body>
    <div class="header-box">
        <p class="header-title">🛡️ 交易终端操作指南与量化风控说明信息</p>
        <p class="header-subtitle">内置高等级操作手册 · 面向 Windows 稳健多进程交易架构 · 2026 最新版</p>
    </div>

    <h2>一、系统定位与副驾驶（Copilot）操盘机制</h2>
    <p>交易系统的信号计算、行为锁状态管理、风控判定、订单物理递投、Paper/Live 模拟对账由交易内核 <b>100% 独立全自主闭环运作</b>。</p>
    <p><b>人（操作员）的角色：</b> 相当于飞机副驾驶，主要负责启动前的 Checklist 物理点检、实时观测多进程状态、监控持仓飘移并在高波动行情下动态调整风控极限上限。</p>

    <h2>二、四大天梯交易模式 (set_trading_mode)</h2>
    
    <div class="mode-card">
        <span class="badge badge-observe">旁路记账 OBSERVE</span>
        <span><b>无害化记账：</b> 默认挂载状态。只记录交易信号和风控网关判定逻辑，<span class="highlight-warn">不扣减现金，不买入个股</span>，供操盘前调试及信号验证。</span>
    </div>
    
    <div class="mode-card">
        <span class="badge badge-paper">模拟测试 PAPER</span>
        <span><b>高真内存模拟：</b> 在内存中构建精密的虚拟仓位与资产变动账簿。科学撮合 <span class="highlight-glow">BUY -> ADD -> REDUCE -> SELL</span>，包含持仓均价、日内浮动盈亏 (PnL)、仓位暴露控制，是完美的战术模拟环境。</span>
    </div>
    
    <div class="mode-card">
        <span class="badge badge-confirm">人机协同 CONFIRM</span>
        <span><b>双轨放行拦截：</b> <span class="highlight-warn">强烈推荐实盘运行初期使用！</span> 信号被 10 大风控放行后，会通过跨线程安全调度，在看盘主图正中弹出<b>无边框 Cyberpunk 圆角半透明置顶气泡</b>，伴随 15 秒物理倒计时与滑块微调。操盘手可点击“确认放行”（或敲击回车）投递，或微调下单比率，或作废拦截。</span>
    </div>
    
    <div class="mode-card">
        <span class="badge badge-live">自动实盘 LIVE_AUTO</span>
        <span><b>极速无人值守：</b> 信号一旦通过风控与 8 大前置防护物理拦截，系统以微秒级直接路由投递至物理柜台。进入此模式前，必须通过 8 大前置卡口严格检验，防止人为误操作。</span>
    </div>

    <h2>三、7 大风控极限调优参数详解 (Risk Limits)</h2>
    <table class="param-table">
        <tr>
            <th style="width: 140px;">参数名称 & 控件</th>
            <th style="width: 70px;">单位 / 步进</th>
            <th style="width: 100px;">常规推荐区间</th>
            <th>实盘作用与防冲防滑防雷核心逻辑</th>
        </tr>
        <tr>
            <td class="highlight-glow">防冲高接盘阀值<br/>(pct_diff)</td>
            <td>% / 0.5%</td>
            <td>2.0% - 4.0%</td>
            <td>限制个股切片涨幅偏离“起点价格”的上限。若突破信号触发时股价瞬间被拉得过高（冲高超过该阀值），网关强行拦截阻断，<b>防止盘中情绪化追高被套</b>。</td>
        </tr>
        <tr>
            <td class="highlight-glow">最低策略打分阈值<br/>(min_confidence)</td>
            <td>无 / 0.05</td>
            <td>0.60 - 0.75</td>
            <td>策略计算出的入场信心概率门槛。低于此评分的信号不予放行，<b>过滤弱势横盘或诱多陷阱，确保入场质地</b>。</td>
        </tr>
        <tr>
            <td class="highlight-glow">单股最大持仓占比</td>
            <td>% / 5%</td>
            <td>10% - 20%</td>
            <td>单一股票市值占账户总资产的比例极限。防止重仓单股踩雷，<b>强制执行资产分散度策略，规避极端黑天鹅</b>。</td>
        </tr>
        <tr>
            <td class="highlight-glow">板块最大暴露比例</td>
            <td>% / 5%</td>
            <td>25% - 40%</td>
            <td>单一行业/概念板块的个股市值暴露总和上限。在同板块大涨时防止仓位过分堆积在单一方向，<b>抑制板块集中性崩塌性回撤</b>。</td>
        </tr>
        <tr>
            <td class="highlight-glow">账户最大杠杆仓位</td>
            <td>% / 5%</td>
            <td>60% - 90%</td>
            <td>全局总可用资金已用百分比限额。到达上限后系统拒绝一切新开仓，留足流动性应对市场突变，<b>防范杠杆穿仓爆仓</b>。</td>
        </tr>
        <tr>
            <td class="highlight-warn">今日亏损触底金额</td>
            <td>¥ / 1000</td>
            <td>视账户规模自定</td>
            <td>日内控制的核心防线。当日内累计已实现亏损 + 浮动亏损触及该额度时，<b>系统瞬间自动拉起紧急熔断</b>，强行降级回 OBSERVE，斩断亏损失控。</td>
        </tr>
        <tr>
            <td class="highlight-glow">连亏冷静期笔数</td>
            <td>笔 / 1</td>
            <td>2 - 4 笔</td>
            <td>当系统连续触发了 N 笔止损成交时，认定当前市场环境为极易多头拉锯的震荡市，交易流进入冷静冷静期（30分钟），<b>防止本金被来回“反复抽打”</b>。</td>
        </tr>
    </table>

    <h2>四、8 大前置防护关卡 (Pre-flight Gates)</h2>
    <p>升格至全自动实盘 <span class="highlight-glow">LIVE_AUTO</span> 时，系统底层会无条件完成 8 重物理门禁校验：</p>
    <ul class="bullet-list">
        <li><b>1. 时间防线：</b> 严格在活跃交易时段 (9:15-11:30, 13:00-15:00) 运行，午休及非交易日拒绝一切升级。</li>
        <li><b>2. 柜台防线：</b> 实盘柜台心跳及 API 响应在毫秒级内，物理在线。</li>
        <li><b>3. 熔断防线：</b> 物理熔断开关 (KillSwitch) 为未挂起状态，且磁盘中无遗留锁文件 `.kill_switch`。</li>
        <li><b>4. 风控防线：</b> 内存 `RiskLimits` 结构参数完整，且成功物理初始化加载。</li>
        <li><b>5. 损限防线：</b> 今日累计亏损未触及日内硬止损上限，不处于连亏冷却状态。</li>
        <li><b>6. 对账防线：</b> 本地 PositionBook 与真实柜台持仓对账完全一致，无任何飘移。</li>
        <li><b>7. 指纹防线：</b> 当前交易内核编译版本 MD5 与主系统完全一致，防止物理文件损坏或劫持。</li>
        <li><b>8. 测试红线：</b> 29/29 自动化集成回归测试在本地全部以绿旗通过，防功能破损。</li>
    </ul>

    <h2>五、🚨 紧急熔断与物理断电保护机制</h2>
    <p><b>熔断运作核心：</b> 当检测到行情剧烈失控、系统数据异常、或人工紧急干预点击 <b>🚨 激活紧急熔断切断 (KILL SWITCH)</b> 时：</p>
    <ul class="bullet-list">
        <li><b>内存切断：</b> 内存 `self._kill_switch = True` 瞬间锁定，后续哪怕微秒内涌入 100 只股票突破信号，全部物理阻断。</li>
        <li><b>物理硬锁：</b> 瞬间在应用主目录下原子创建 <code>.kill_switch</code> 锁文件。即使主系统崩塌、电脑掉电重启，在冷启动探测到该锁文件时，系统仍会<b>秒级强制锁死一切下单功能</b>，直至操盘手在 UI 控制台点按“解除熔断”进行人工自愈。</li>
    </ul>
</body>
</html>"""
        self.browser.setHtml(html_content)


class OperatorChecklistDialog(QtWidgets.QDialog):
    """📋 每日操盘 Checklist 流程化操作指引提醒 (Interactive Checklist Dialog)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 每日操盘操作员 Checklist (Pre-flight)")
        self.resize(560, 390)
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #E2E2E6;
            }
            QCheckBox {
                color: #D2D2D6;
                font-size: 11px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                background-color: #16161A;
                border: 1px solid #2E2E35;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #00E676;
                border-color: #00E676;
            }
            QLabel {
                font-size: 11px;
            }
            QPushButton {
                background-color: #1E1E24;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 6px 14px;
                color: #C2C2C6;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2E2E38;
                border-color: #00E676;
                color: #FFFFFF;
            }
            QGroupBox {
                border: 1px solid #232328;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
                font-weight: bold;
                color: #00E5FF;
            }
        """)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(6)
        
        title_lbl = QtWidgets.QLabel("🛠️ 操作员 Checklist (操盘手职责：观摩与调优)")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #00E676; padding-bottom: 2px;")
        main_layout.addWidget(title_lbl)
        
        desc_lbl = QtWidgets.QLabel("注：交易决策、风控网关、并发锁、物理执行由交易内核 100% 全流程自主接管。\n人作为副驾驶主要负责监视指标、排除硬件风险、并在必要时微调上限阈值。")
        desc_lbl.setStyleSheet("color: #88888D; font-size: 10px; padding-bottom: 6px;")
        main_layout.addWidget(desc_lbl)
        
        # 1. 战前准备
        group_pre = QtWidgets.QGroupBox("1. 战前准备 (09:00 - 09:15)")
        lay_pre = QtWidgets.QVBoxLayout(group_pre)
        lay_pre.setContentsMargins(8, 8, 8, 8)
        self.chk1 = QtWidgets.QCheckBox(" 启动主系统，打开 '⚡ 决策流水监控'，检查可用现金及总资产无 Null/报错。")
        self.chk2 = QtWidgets.QCheckBox(" 检查状态徽章 '✅ 交易通道正常'，模式默认挂载在 '旁路记账 OBSERVE'。")
        self.chk3 = QtWidgets.QCheckBox(" 核对 Wind 控制参数配置，根据今日市场情绪进行盘前参数调优。")
        lay_pre.addWidget(self.chk1)
        lay_pre.addWidget(self.chk2)
        lay_pre.addWidget(self.chk3)
        main_layout.addWidget(group_pre)
        
        # 2. 开盘观察
        group_open = QtWidgets.QGroupBox("2. 开盘观察与人机协同 (09:25 - 15:00)")
        lay_open = QtWidgets.QVBoxLayout(group_open)
        lay_open.setContentsMargins(8, 8, 8, 8)
        self.chk4 = QtWidgets.QCheckBox(" 【09:25】集合竞价结束，核对赛马面板 '📍 起点1' 开盘快照亮起。")
        self.chk5 = QtWidgets.QCheckBox(" 【09:30】切换交易模式至 'CONFIRM (人工确认)' 或 'PAPER (高真模拟)'。")
        self.chk6 = QtWidgets.QCheckBox(" 【盘中】保持 Alt+R 监控，在气泡弹出 15s 内决定放行、微调比例或作废拒绝。")
        lay_open.addWidget(self.chk4)
        lay_open.addWidget(self.chk5)
        lay_open.addWidget(self.chk6)
        main_layout.addWidget(group_open)
        
        # 3. 盘后对账
        group_post = QtWidgets.QGroupBox("3. 盘后审计 (15:00 - 15:30)")
        lay_post = QtWidgets.QVBoxLayout(group_post)
        lay_post.setContentsMargins(8, 8, 8, 8)
        self.chk7 = QtWidgets.QCheckBox(" 交易结束后，将模式切换回 'OBSERVE' 确保无残留。")
        self.chk8 = QtWidgets.QCheckBox(" 点击 '实时持仓 Tab' 对账，确认今日无任何漂移 `POSITION_SYNC_AUDIT` 报警。")
        lay_post.addWidget(self.chk7)
        lay_post.addWidget(self.chk8)
        main_layout.addWidget(group_post)
        
        # 底部操作提示
        main_layout.addSpacing(6)
        footer_lbl = QtWidgets.QLabel("🤖 系统全自主运行中，操盘手职责：观摩数据流、监视风控状态、调优极限参数。")
        footer_lbl.setStyleSheet("color: #FF9100; font-weight: bold; font-size: 10px; font-style: italic;")
        main_layout.addWidget(footer_lbl)
        
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QtWidgets.QPushButton("我已核对，准备操盘")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        main_layout.addLayout(btn_layout)


class DecisionDetailsDialog(QtWidgets.QDialog):
    """💡 核心决策及风控检验流水详情 (Core Decision & Risk Analysis Details)"""
    def __init__(self, rec: dict, parent=None):
        super().__init__(parent)
        self.rec = rec
        self.setWindowTitle("💡 核心决策及风控检验流水详情")
        self.resize(750, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #E2E2E6;
            }
            QTabWidget::pane {
                border: 1px solid #2E2E35;
                background-color: #16161A;
            }
            QTabBar::tab {
                background-color: #1E1E24;
                color: #A2A2A6;
                padding: 6px 15px;
                border: 1px solid #2E2E35;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-family: "Microsoft YaHei";
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background-color: #16161A;
                color: #FFFFFF;
                border-bottom: 1px solid #16161A;
            }
            QTableWidget {
                background-color: #16161A;
                border: none;
                color: #E2E2E6;
                gridline-color: #2E2E35;
                font-family: "Microsoft YaHei";
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #1E1E24;
                color: #A2A2A6;
                border: 1px solid #2E2E35;
                padding: 4px;
            }
            QTextEdit {
                background-color: #16161A;
                border: none;
                color: #00E676;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QPushButton {
                background-color: #1E1E24;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 6px 15px;
                color: #C2C2C6;
                font-family: "Microsoft YaHei";
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2E2E38;
                border-color: #00E676;
                color: #FFFFFF;
            }
        """)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab 1: 核心分析表格
        self.tab_metrics = QtWidgets.QWidget()
        self.tab_metrics_layout = QtWidgets.QVBoxLayout(self.tab_metrics)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["分类", "指标参数/决策项", "数值/状态说明"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab_metrics_layout.addWidget(self.table)
        self.tabs.addTab(self.tab_metrics, "💡 核心指标与风控分析")
        
        # Tab 2: 原始 JSON
        self.tab_raw = QtWidgets.QWidget()
        self.tab_raw_layout = QtWidgets.QVBoxLayout(self.tab_raw)
        self.json_edit = QtWidgets.QTextEdit()
        self.json_edit.setReadOnly(True)
        self.tab_raw_layout.addWidget(self.json_edit)
        self.tabs.addTab(self.tab_raw, "📋 原始决策日志 JSON")
        
        # 填充数据
        self._populate_data()
        
        # 底部按钮
        btn_layout = QtWidgets.QHBoxLayout()
        copy_json_btn = QtWidgets.QPushButton("📋 复制 JSON 数据")
        copy_json_btn.clicked.connect(self._copy_json)
        btn_layout.addWidget(copy_json_btn)
        btn_layout.addStretch()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
    def _populate_data(self):
        # 1. 原始 JSON 数据填充
        import json
        try:
            formatted_json = json.dumps(self.rec, indent=4, ensure_ascii=False)
            self.json_edit.setPlainText(formatted_json)
        except Exception as e:
            self.json_edit.setPlainText(f"JSON 格式化失败: {e}\\n\\n原始数据:\\n{str(self.rec)}")
            
        # 2. 表格填充
        is_audit = (self.rec.get("journal_type") == "HUMAN_CONFIRMATION_AUDIT")
        rows = []
        
        if is_audit:
            # 审计日志填充
            orig_order = self.rec.get("original_order", {})
            meta = self.rec.get("override_metadata", {})
            rows.append(("系统审计", "事件类型", "人工确认审计 (HUMAN_CONFIRMATION_AUDIT)"))
            rows.append(("系统审计", "触发时间", str(self.rec.get("timestamp", ""))))
            rows.append(("系统审计", "股票代码", str(orig_order.get("code", ""))))
            rows.append(("系统审计", "原始买卖", str(orig_order.get("action", ""))))
            rows.append(("系统审计", "原始拟仓", f"{float(orig_order.get('size_pct', 0.0))*100:.1f}%"))
            rows.append(("系统审计", "操盘确认", "已确认同意" if self.rec.get("confirmed") else "已拒绝/超时"))
            rows.append(("系统审计", "干预理由", str(self.rec.get("override_reason", ""))))
            if meta.get("size_changed"):
                rows.append(("系统审计", "实际执行仓位", f"{float(meta.get('actual_size_pct', 0.0))*100:.1f}%"))
        else:
            trace = self.rec.get("trace", {})
            sig = self.rec.get("signal", {})
            intent = self.rec.get("intent", {})
            risk = self.rec.get("risk", {})
            k_res = self.rec.get("kernel_result", {})
            if not isinstance(k_res, dict): k_res = {}
            
            # 基本数据
            rows.append(("基本信息", "触发时间", str(self.rec.get("journal_ts", "") or trace.get("timestamp", ""))))
            rows.append(("基本信息", "股票代码", f"{sig.get('code', '')} ({sig.get('name', '')})"))
            rows.append(("基本信息", "触发价格", f"{sig.get('price', 0.0):.2f} 元" if sig.get('price') else "N/A"))
            rows.append(("基本信息", "系统 Trace ID", str(trace.get("trace_id", "N/A"))))
            
            # 策略决策意图
            rows.append(("策略意图", "状态机前态", str(trace.get("state", "FLAT"))))
            rows.append(("策略意图", "建议动作", str(intent.get("action", "HOLD"))))
            rows.append(("策略意图", "建议仓位", f"{float(intent.get('size_pct', 0.0))*100:.1f}%" if intent.get('size_pct') is not None else "N/A"))
            rows.append(("策略意图", "置信度评分", str(intent.get("confidence", "N/A"))))
            rows.append(("策略意图", "动态止损价", f"{float(intent.get('stop_price', 0.0)):.2f} 元" if intent.get("stop_price") else "N/A"))
            
            # 详细理由
            reason = intent.get("reason", {})
            if isinstance(reason, dict):
                rows.append(("决策参数", "路由策略分支 (Branch)", str(reason.get("routed_branch", "N/A"))))
                rows.append(("决策参数", "入场/出场形态 (Setup)", str(reason.get("setup", "N/A"))))
                rows.append(("决策参数", "所属运行模式 (Regime)", str(reason.get("regime", "N/A"))))
                rows.append(("决策参数", "板块强度", str(reason.get("sector_heat", "N/A"))))
                rows.append(("决策参数", "个股强度 (Priority)", str(sig.get("features", {}).get("priority", "N/A"))))
                rows.append(("决策参数", "板块龙头领涨", "⭐是" if reason.get("is_leader") else "否"))
                rows.append(("决策参数", "突破判定", "是" if reason.get("breakout") else "否"))
                rows.append(("决策参数", "多日资金流向 (dff)", str(reason.get("dff", "N/A"))))
                rows.append(("决策参数", "二次重入信号", "🎯是" if reason.get("is_reentry_signal") else "否"))
                if reason.get("reentry_reason"):
                    rows.append(("决策参数", "重入判定理由", str(reason.get("reentry_reason"))))
            
            # 风控判定
            rows.append(("风控核验", "风控通过", "🟢 允许 (Allowed)" if risk.get("allowed", True) else "🔴 拦截 (Blocked)"))
            rows.append(("风控核验", "最终决策动作", str(risk.get("final_action", "HOLD"))))
            rows.append(("风控核验", "最终批准仓位", f"{float(risk.get('final_size_pct', 0.0))*100:.1f}%" if risk.get('final_size_pct') is not None else "N/A"))
            
            reject_msg = k_res.get("kernel_reject_code", "")
            if not reject_msg and not risk.get("allowed", True):
                reject_msg = risk.get("reject_context", {}).get("message") or risk.get("reject_context", {}).get("code", "")
            if reject_msg:
                rows.append(("风控核验", "拦截原因", f"⚠️ {reject_msg}"))
                
            if risk.get("order"):
                rows.append(("委托订单", "核发委托单 ID", str(risk["order"].get("order_id", ""))))
                rows.append(("委托订单", "委托股数", str(risk["order"].get("volume", ""))))
                rows.append(("委托订单", "最终订单状态", "已提交执行" if k_res.get("kernel_executed") else "待处理/未执行"))

        self.table.setRowCount(len(rows))
        for r_idx, (cat, name, val) in enumerate(rows):
            item_cat = QtWidgets.QTableWidgetItem(cat)
            item_name = QtWidgets.QTableWidgetItem(name)
            item_val = QtWidgets.QTableWidgetItem(val)
            
            # 着色增强
            if "🔴" in val or "🔴" in name or "拦截" in val:
                item_val.setForeground(QtGui.QColor("#FF1744"))
                item_val.setFont(QtGui.QFont("Microsoft YaHei", 10, QtGui.QFont.Weight.Bold))
            elif "🟢" in val or "允许" in val:
                item_val.setForeground(QtGui.QColor("#00E676"))
                item_val.setFont(QtGui.QFont("Microsoft YaHei", 10, QtGui.QFont.Weight.Bold))
            elif "⭐" in val or "🎯" in val:
                item_val.setForeground(QtGui.QColor("#FFEB3B"))
                
            self.table.setItem(r_idx, 0, item_cat)
            self.table.setItem(r_idx, 1, item_name)
            self.table.setItem(r_idx, 2, item_val)
            
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 180)

    def _copy_json(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.json_edit.toPlainText())
        QtWidgets.QMessageBox.information(self, "复制成功", "原始决策 JSON 已经成功复制到剪贴板。")


class DecisionFlowPanel(QtWidgets.QWidget, WindowMixin):
    """
    ⚡ 交易内核决策流水分析面板 (Trading Kernel Decision Flow)
    采用 PyQt6 构建的只读高性能监控看板，完美适配 Windows 多进程并发环境。
    """
    # 股票点击跳转信号 (code, name)
    code_clicked = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None, journal_path: str = "logs/trading_kernel_trace.jsonl"):
        super().__init__()
        self.parent_app = parent
        
        # 🛡️ 强制在最早对齐并标准化为物理绝对路径，扼杀多进程/打包环境下的工作目录飘移硬伤
        import os
        if not os.path.isabs(journal_path):
            journal_path = os.path.join(get_app_root(), journal_path)
        self.journal_path = journal_path
        
        self._last_file_size = 0
        self._last_modified_time = 0.0
        
        # 脏检查状态指示缓存，避免高频对齐重复更新 GUI 样式
        self._last_is_killed = None
        self._last_top_mode = None
        self._last_top_killed = None
        self._last_linked_code = None
        
        # 昨持仓平仓成本追溯与高频遍历优化缓存
        self._position_cost_cache = {}
        self._last_orders_len = -1
        self._cached_code_trade_info = {}
        self._last_rendered_state = None
        self._hidden_closed_codes = set()
        
        self.setWindowFlags(QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.WindowMinMaxButtonsHint | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("⚡ 交易内核决策流水分析 (Trading Kernel Decision Flow)")
        
        # 继承 WindowMixin 缩放因子
        self.scale_factor = getattr(self.parent_app, "scale_factor", 1.0)
        
        # 1. 初始化 UI 与组件布局 (Cyberpunk Dark Mode)
        self._init_ui()
        
        # 1.5 初始化防抖过滤计时器
        self._filter_timer = QtCore.QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._filter_table)
        
        # 2. 载入窗口历史尺寸与位置
        self.load_window_position_qt(self, "DecisionFlowPanel", default_width=1100, default_height=550)
        
        # 2.5 延迟 150ms 恢复列宽与表头状态，确保窗口物理尺寸已就绪
        QtCore.QTimer.singleShot(150, self._safe_restore_and_adjust)
        
        # 3. 首次全量扫描载入 (最多 200 条，防冷启动白屏)
        self._load_initial_records()
        
        # 同步初始化控制页与顶部状态徽章
        self._update_top_status_badges()
        self._sync_control_tab_ui()
        
        # 4. 启动高频定时器：每 500ms 增量扫描更新决策流水日志，实现高精增量追溯
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._check_and_update_records)
        self.timer.start(500)

        # 5. 启动低频定时器：每 2000ms 执行状态徽章同步、控制页同步、持仓刷新与决策流停滞监控，释放主线程 CPU 开销
        self.slow_timer = QtCore.QTimer(self)
        self.slow_timer.timeout.connect(self._slow_update_cycle)
        self.slow_timer.start(2000)

    def _init_ui(self):
        """初始化极富科技感、暗黑渐变之美的决策监控界面 (Premium Dark Mode)"""
        # 全局 Cyberpunk 调色板
        self.setStyleSheet("""
            QWidget {
                background-color: #121214;
                color: #E2E2E6;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
            }
            QTableWidget {
                background-color: #16161A;
                border: 1px solid #232328;
                gridline-color: #232328;
                color: #D2D2D6;
                alternate-background-color: #1A1A1F;
                selection-background-color: #2A2A35;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #1E1E24;
                color: #A0A0A5;
                padding: 1px 2px;
                border: none;
                border-bottom: 2px solid #282830;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 0px 1px;
            }
            QTabWidget::pane {
                border: 1px solid #232328;
                background-color: #121214;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1E1E24;
                color: #A0A0A5;
                border: 1px solid #2E2E35;
                padding: 6px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                margin-right: 2px;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background-color: #16161A;
                color: #00E676;
                border-bottom-color: #16161A;
            }
            QPushButton {
                background-color: #1E1E24;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 4px 10px;
                color: #C2C2C6;
            }
            QPushButton:hover {
                background-color: #2E2E38;
                border-color: #00E676;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #16161B;
            }
            QLineEdit {
                background-color: #16161A;
                border: 1px solid #232328;
                border-radius: 3px;
                padding: 3px 5px;
                color: #FFFFFF;
            }
            QLabel {
                color: #A0A0A5;
            }
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # 引入 QTabWidget 进行多维决策分类
        self.tabs = QtWidgets.QTabWidget()
        
        # ==========================================
        # 1. ⚡ 决策流水监控 页签
        # ==========================================
        flow_widget = QtWidgets.QWidget()
        flow_layout = QtWidgets.QVBoxLayout(flow_widget)
        flow_layout.setContentsMargins(6, 6, 6, 6)
        flow_layout.setSpacing(6)

        # 头部控制栏 (扁平紧凑)
        top_bar = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("🎯 决策流水监控:")
        title_label.setStyleSheet("font-weight: bold; color: #00E676; font-size: 12px;")
        top_bar.addWidget(title_label)

        # 搜索过滤框
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText(" 输入股票代码/名称/动作进行过滤...")
        self.search_input.setFixedWidth(160)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        top_bar.addWidget(self.search_input)

        # 状态徽章区 (Glow badges)
        self.lbl_mode_badge = QtWidgets.QLabel("⚪ 旁路记账")
        self.lbl_mode_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #444; border-radius: 3px; color: #A0A0A5; background-color: #1A1A1F;")
        top_bar.addWidget(self.lbl_mode_badge)

        self.lbl_kill_badge = QtWidgets.QLabel("✅ 通道正常")
        self.lbl_kill_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #444; border-radius: 3px; color: #00E676; background-color: #1A1A1F;")
        top_bar.addWidget(self.lbl_kill_badge)

        top_bar.addStretch()

        # 系统流程拓扑与操作 Checklist 按钮
        plan_btn = QtWidgets.QPushButton("🚀 拓扑规划")
        plan_btn.clicked.connect(self._show_system_workflow_dialog)
        top_bar.addWidget(plan_btn)

        chk_btn = QtWidgets.QPushButton("📋 操盘 Checklist")
        chk_btn.clicked.connect(self._show_checklist_dialog)
        top_bar.addWidget(chk_btn)

        # 一键手工刷新与清理按钮
        refresh_btn = QtWidgets.QPushButton("🔄 手工刷新")
        refresh_btn.clicked.connect(self._force_reload)
        top_bar.addWidget(refresh_btn)

        clear_btn = QtWidgets.QPushButton("🧹 清空显示")
        clear_btn.clicked.connect(self._clear_view)
        top_bar.addWidget(clear_btn)

        flow_layout.addLayout(top_bar)

        # 主数据表格 (只读)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(12)
        headers = [
            "日期时间", "代码", "名称", "前态", "动作", 
            "拟仓位", "打分", "风控结果", "阻断码", 
            "止损价", "Trace ID", "决策理由摘要"
        ]
        self.table.setHorizontalHeaderLabels(headers)
        
        # 基础行为配置
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.setSortingEnabled(True)
        
        # 启用右键菜单支持
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # 表头拉伸策略
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.sortIndicatorChanged.connect(lambda: self.table.scrollToTop())
        
        # 绑定双击行进行代码联动
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        # 绑定键盘/鼠标切换当前行进行自动联动
        self.table.currentCellChanged.connect(self._on_table_cell_changed)
        flow_layout.addWidget(self.table)
        
        self.tabs.addTab(flow_widget, "⚡ 决策流水监控 (Decision Flow)")

        # ==========================================
        # 2. 💼 内核实时持仓 页签
        # ==========================================
        pos_widget = QtWidgets.QWidget()
        pos_layout = QtWidgets.QVBoxLayout(pos_widget)
        pos_layout.setContentsMargins(6, 6, 6, 6)
        pos_layout.setSpacing(6)

        # 持仓控制面板
        pos_ctrl_layout = QtWidgets.QHBoxLayout()
        pos_ctrl_layout.setContentsMargins(2, 2, 2, 2)
        
        pos_title_lbl = QtWidgets.QLabel("💼 实时模拟持仓与资金监控")
        pos_title_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #E2E2E6;")
        pos_ctrl_layout.addWidget(pos_title_lbl)
        
        pos_ctrl_layout.addStretch()
        
        # 选项：显示已平仓持仓
        self.chk_show_closed = QtWidgets.QCheckBox("📜 显示已平仓 (0股)")
        self.chk_show_closed.setToolTip("开启此选项即可显示今日已平仓(持仓为0)的个股记录，默认不显示")
        self.chk_show_closed.setStyleSheet("""
            QCheckBox {
                color: #C2C2C6;
                font-size: 10px;
                margin-right: 12px;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
                background-color: #16161A;
                border: 1px solid #2E2E35;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #00E676;
                border-color: #00E676;
            }
        """)
        self.chk_show_closed.setChecked(False)
        self.chk_show_closed.toggled.connect(self._on_show_closed_toggled)
        pos_ctrl_layout.addWidget(self.chk_show_closed)

        # 一键数据自愈修复按钮
        self.btn_heal = QtWidgets.QPushButton("🔧 一键数据自愈修复")
        self.btn_heal.setToolTip("智能校正初始资金、剔除已平仓(0股)幽灵持仓行、并自愈对账可用现金和资产盈亏")
        self.btn_heal.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #00E5FF;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #FFFFFF;
                border-color: #00E5FF;
            }
            QPushButton:pressed {
                background-color: #0F172A;
            }
        """)
        self.btn_heal.clicked.connect(self._on_one_key_self_heal)
        pos_ctrl_layout.addWidget(self.btn_heal)
        
        pos_layout.addLayout(pos_ctrl_layout)

        # 持仓数据表格 (只读)
        self.pos_table = QtWidgets.QTableWidget()
        self.pos_table.setColumnCount(10)
        pos_headers = ["代码", "名称", "持仓股数", "买入均价", "当前市价", "持仓市值", "浮动盈亏", "盈亏比例", "开仓时间", "平仓时间"]
        self.pos_table.setHorizontalHeaderLabels(pos_headers)
        
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.pos_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.verticalHeader().setDefaultSectionSize(18)
        self.pos_table.setSortingEnabled(True)
        
        # 绑定双击持仓代码跳转
        self.pos_table.cellDoubleClicked.connect(self._on_pos_cell_double_clicked)
        # 绑定键盘/鼠标切换当前行进行自动联动
        self.pos_table.currentCellChanged.connect(self._on_pos_table_cell_changed)
        
        # 启用持仓表格右键快捷菜单支持
        self.pos_table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.pos_table.customContextMenuRequested.connect(self._show_pos_context_menu)
        
        pos_header = self.pos_table.horizontalHeader()
        pos_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        pos_header.setStretchLastSection(True)
        pos_header.sortIndicatorChanged.connect(lambda: self.pos_table.scrollToTop())
        pos_layout.addWidget(self.pos_table)

        # 底部发光大卡片栏 (Summary metrics cards)
        summary_layout = QtWidgets.QHBoxLayout()
        summary_layout.setSpacing(8)
        
        self.cards = {}
        card_metrics = [
            ("cash", "💰 可用现金", "#E2E2E6"),
            ("equity", "📊 账户总资产", "#00E5FF"),
            ("market_value", "💼 持仓总市值", "#00E676"),
            ("total_pnl", "📈 账户总盈亏", "#FF1744"),
            ("ratio", "⚖️ 仓位使用率", "#FF9100")
        ]
        
        for key, name, color in card_metrics:
            card = QtWidgets.QFrame()
            card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
            card.setStyleSheet("""
                QFrame {
                    background-color: #16161A;
                    border: 1px solid #232328;
                    border-radius: 5px;
                    padding: 4px;
                }
            """)
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setSpacing(1)
            card_layout.setContentsMargins(4, 4, 4, 4)
            
            lbl = QtWidgets.QLabel(name)
            lbl.setStyleSheet("font-size: 9px; color: #88888D;")
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            
            val = QtWidgets.QLabel("¥ 0.00")
            val.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
            val.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            
            card_layout.addWidget(lbl)
            card_layout.addWidget(val)
            summary_layout.addWidget(card)
            self.cards[key] = val
            
        pos_layout.addLayout(summary_layout)
        self.tabs.addTab(pos_widget, "💼 内核实时持仓 (Kernel Positions & PnL)")

        # ==========================================
        # 3. ⚙️ 内核控制与风控 页签
        # ==========================================
        ctrl_widget = QtWidgets.QWidget()
        ctrl_layout = QtWidgets.QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(12, 12, 12, 12)
        ctrl_layout.setSpacing(10)
        
        # --- A. 交易运行模式控制区 ---
        mode_group = QtWidgets.QGroupBox("⚡ 交易运行模式控制中心 (Mode Ladder)")
        mode_group.setStyleSheet("QGroupBox { font-size: 11px; font-weight: bold; color: #00E676; border: 1px solid #232328; border-radius: 4px; margin-top: 6px; padding-top: 6px; }")
        mode_lay = QtWidgets.QVBoxLayout(mode_group)
        mode_lay.setSpacing(6)
        
        mode_row = QtWidgets.QHBoxLayout()
        mode_lbl = QtWidgets.QLabel("当前运行模式:")
        mode_lbl.setStyleSheet("font-weight: bold; color: #C2C2C6;")
        mode_row.addWidget(mode_lbl)
        
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([
            "OBSERVE (旁路记账 - 100% 安全无害)",
            "PAPER (模拟测试 - 内存高真撮合)",
            "CONFIRM (人机协同 - 弹出确认气泡)",
            "LIVE_AUTO (全自动实盘 - 打通物理柜台)"
        ])
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #16161A;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 4px 10px;
                color: #FFFFFF;
                min-width: 250px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1E1E24;
                color: #E2E2E6;
                selection-background-color: #00E676;
                selection-color: #121214;
            }
        """)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        mode_lay.addLayout(mode_row)
        
        self.lbl_mode_desc = QtWidgets.QLabel("模式说明: OBSERVE 纯观察旁路模式。系统仅在日志中打印信号与风控判断细节，不进行任何模拟或实盘委托。")
        self.lbl_mode_desc.setStyleSheet("color: #88888D; font-size: 10px;")
        self.lbl_mode_desc.setWordWrap(True)
        mode_lay.addWidget(self.lbl_mode_desc)
        
        self.lbl_preconditions_warn = QtWidgets.QLabel("")
        self.lbl_preconditions_warn.setStyleSheet("color: #FF1744; font-weight: bold; font-size: 10px;")
        self.lbl_preconditions_warn.setWordWrap(True)
        self.lbl_preconditions_warn.setVisible(False)
        mode_lay.addWidget(self.lbl_preconditions_warn)
        
        ctrl_layout.addWidget(mode_group)
        
        # --- B. 紧急交易切断开关 (KillSwitch) ---
        kill_group = QtWidgets.QGroupBox("🚨 交易安全紧急切断通道 (Kill Switch)")
        kill_group.setStyleSheet("QGroupBox { font-size: 11px; font-weight: bold; color: #FF1744; border: 1px solid #232328; border-radius: 4px; margin-top: 6px; padding-top: 6px; }")
        kill_lay = QtWidgets.QHBoxLayout(kill_group)
        kill_lay.setContentsMargins(10, 10, 10, 10)
        
        self.lbl_kill_status_desc = QtWidgets.QLabel("通道状态: ✅ 交易通道正常，买入决策监听中...")
        self.lbl_kill_status_desc.setStyleSheet("font-weight: bold; font-size: 12px; color: #00E676;")
        kill_lay.addWidget(self.lbl_kill_status_desc)
        
        kill_lay.addStretch()
        
        self.btn_kill_toggle = QtWidgets.QPushButton("🚨 激活紧急熔断切断 (KILL SWITCH)")
        self.btn_kill_toggle.setStyleSheet("""
            QPushButton {
                background-color: #D50000;
                color: #FFFFFF;
                font-weight: bold;
                border: 1px solid #FF1744;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #FF1744;
            }
        """)
        self.btn_kill_toggle.clicked.connect(self._on_kill_switch_toggled)
        kill_lay.addWidget(self.btn_kill_toggle)
        
        ctrl_layout.addWidget(kill_group)
        
        # --- C. 10大风控极限阈值调优区 ---
        limits_group = QtWidgets.QGroupBox("🛡️ 交易内核风控阈值调优中心 (Risk Gate Limits)")
        limits_group.setStyleSheet("QGroupBox { font-size: 11px; font-weight: bold; color: #00E5FF; border: 1px solid #232328; border-radius: 4px; margin-top: 6px; padding-top: 6px; }")
        limits_lay = QtWidgets.QGridLayout(limits_group)
        limits_lay.setSpacing(8)
        limits_lay.setContentsMargins(10, 10, 10, 10)
        
        # 1. 过滤追高阈值 (max_pct_diff)
        limits_lay.addWidget(QtWidgets.QLabel("防冲高接盘阀值 (pct_diff):"), 0, 0)
        self.spin_max_diff = QtWidgets.QDoubleSpinBox()
        self.spin_max_diff.setRange(0.0, 20.0)
        self.spin_max_diff.setSingleStep(0.5)
        self.spin_max_diff.setSuffix("%")
        self.spin_max_diff.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_max_diff, 0, 1)
        
        # 2. 最低信号打分 (min_confidence)
        limits_lay.addWidget(QtWidgets.QLabel("最低策略打分阈值:"), 0, 2)
        self.spin_min_conf = QtWidgets.QDoubleSpinBox()
        self.spin_min_conf.setRange(0.0, 1.0)
        self.spin_min_conf.setSingleStep(0.05)
        self.spin_min_conf.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_min_conf.setValue(0.70)
        limits_lay.addWidget(self.spin_min_conf, 0, 3)
        
        # 3. 单股持仓限制 (max_single_stock_position_pct)
        limits_lay.addWidget(QtWidgets.QLabel("单股最大持仓占比:"), 1, 0)
        self.spin_max_stock = QtWidgets.QDoubleSpinBox()
        self.spin_max_stock.setRange(0.0, 100.0)
        self.spin_max_stock.setSingleStep(5.0)
        self.spin_max_stock.setSuffix("%")
        self.spin_max_stock.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_max_stock, 1, 1)
        
        # 4. 板块行业限制 (max_single_sector_exposure_pct)
        limits_lay.addWidget(QtWidgets.QLabel("板块最大暴露比例:"), 1, 2)
        self.spin_max_sector = QtWidgets.QDoubleSpinBox()
        self.spin_max_sector.setRange(0.0, 100.0)
        self.spin_max_sector.setSingleStep(5.0)
        self.spin_max_sector.setSuffix("%")
        self.spin_max_sector.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_max_sector, 1, 3)
        
        # 5. 账户杠杆限制 (total_exposure_cap_pct)
        limits_lay.addWidget(QtWidgets.QLabel("账户最大杠杆仓位:"), 2, 0)
        self.spin_total_exp = QtWidgets.QDoubleSpinBox()
        self.spin_total_exp.setRange(0.0, 100.0)
        self.spin_total_exp.setSingleStep(5.0)
        self.spin_total_exp.setSuffix("%")
        self.spin_total_exp.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_total_exp, 2, 1)
        
        # 6. 日内最大亏损金额 (daily_loss_limit_amount)
        limits_lay.addWidget(QtWidgets.QLabel("今日亏损触底金额:"), 2, 2)
        self.spin_daily_loss = QtWidgets.QSpinBox()
        self.spin_daily_loss.setRange(0, 1000000)
        self.spin_daily_loss.setSingleStep(1000)
        self.spin_daily_loss.setPrefix("¥ ")
        self.spin_daily_loss.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_daily_loss, 2, 3)
        
        # 7. 连续止损冷却笔数 (max_consecutive_losses)
        limits_lay.addWidget(QtWidgets.QLabel("连亏冷静期笔数:"), 3, 0)
        self.spin_losses = QtWidgets.QSpinBox()
        self.spin_losses.setRange(1, 10)
        self.spin_losses.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        limits_lay.addWidget(self.spin_losses, 3, 1)
        
        # 8. 最低触发量能比 (min_volume)
        limits_lay.addWidget(QtWidgets.QLabel("最低触发量能比:"), 3, 2)
        self.spin_min_volume = QtWidgets.QDoubleSpinBox()
        self.spin_min_volume.setRange(0.0, 10.0)
        self.spin_min_volume.setSingleStep(0.1)
        self.spin_min_volume.setSuffix(" 倍")
        self.spin_min_volume.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_min_volume.setValue(1.0)
        limits_lay.addWidget(self.spin_min_volume, 3, 3)
        
        # 9. 网关最大持仓数量 (RiskManager MAX_POSITIONS)
        limits_lay.addWidget(QtWidgets.QLabel("网关最大持仓数量 (RiskManager):"), 4, 0)
        self.spin_rm_max_pos = QtWidgets.QSpinBox()
        self.spin_rm_max_pos.setRange(1, 100)
        self.spin_rm_max_pos.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_rm_max_pos.setValue(10)
        limits_lay.addWidget(self.spin_rm_max_pos, 4, 1)
        
        # 10. 网关单笔持仓占比 (RiskManager MAX_POS_PCT)
        limits_lay.addWidget(QtWidgets.QLabel("网关单笔仓位上限 (RiskManager):"), 4, 2)
        self.spin_rm_max_pos_pct = QtWidgets.QDoubleSpinBox()
        self.spin_rm_max_pos_pct.setRange(0.1, 100.0)
        self.spin_rm_max_pos_pct.setSingleStep(0.5)
        self.spin_rm_max_pos_pct.setSuffix("%")
        self.spin_rm_max_pos_pct.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_rm_max_pos_pct.setValue(5.0)
        limits_lay.addWidget(self.spin_rm_max_pos_pct, 4, 3)
        
        # 11. 网关日内亏损比例 (RiskManager MAX_DAILY_LOSS)
        limits_lay.addWidget(QtWidgets.QLabel("网关日亏损锁仓上限 (RiskManager):"), 5, 0)
        self.spin_rm_max_daily_loss = QtWidgets.QDoubleSpinBox()
        self.spin_rm_max_daily_loss.setRange(0.1, 100.0)
        self.spin_rm_max_daily_loss.setSingleStep(0.5)
        self.spin_rm_max_daily_loss.setSuffix("%")
        self.spin_rm_max_daily_loss.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_rm_max_daily_loss.setValue(2.0)
        limits_lay.addWidget(self.spin_rm_max_daily_loss, 5, 1)
        
        # 12. 网关个股止损比例 (RiskManager STOP_LOSS_PCT)
        limits_lay.addWidget(QtWidgets.QLabel("网关个股默认止损 (RiskManager):"), 5, 2)
        self.spin_rm_stop_loss_pct = QtWidgets.QDoubleSpinBox()
        self.spin_rm_stop_loss_pct.setRange(0.1, 100.0)
        self.spin_rm_stop_loss_pct.setSingleStep(0.5)
        self.spin_rm_stop_loss_pct.setSuffix("%")
        self.spin_rm_stop_loss_pct.setStyleSheet("background-color: #16161A; border: 1px solid #232328; padding: 2px; color: #FFF;")
        self.spin_rm_stop_loss_pct.setValue(2.0)
        limits_lay.addWidget(self.spin_rm_stop_loss_pct, 5, 3)
        
        # 按钮区
        save_btn = QtWidgets.QPushButton("💾 保存并即时应用风控与策略信号参数")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #00E5FF;
                color: #121214;
                font-weight: bold;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                padding: 6px 18px;
            }
            QPushButton:hover {
                background-color: #00B0FF;
            }
        """)
        save_btn.clicked.connect(self._save_and_apply_risk_limits)
        limits_lay.addWidget(save_btn, 6, 0, 1, 4)

        # 连接所有风控与网关参数微调控件的改变信号，实现完全自动持久化与即时热生效
        for spin in [
            self.spin_max_diff, self.spin_min_conf, self.spin_max_stock, self.spin_max_sector,
            self.spin_total_exp, self.spin_daily_loss, self.spin_losses, self.spin_min_volume,
            self.spin_rm_max_pos, self.spin_rm_max_pos_pct, self.spin_rm_max_daily_loss, self.spin_rm_stop_loss_pct
        ]:
            spin.valueChanged.connect(self._auto_save_and_apply)
        
        ctrl_layout.addWidget(limits_group)
        ctrl_layout.addStretch()
        
        self.tabs.addTab(ctrl_widget, "⚙️ 策略信号调整与风控 (Signal Tuning)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs)

        # 底部状态栏
        bottom_bar = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("初始化完成。正在监听交易内核流水与持仓...")
        bottom_bar.addWidget(self.status_label)
        main_layout.addLayout(bottom_bar)

        # 应用自适应列宽分配
        self._adjust_column_widths()

    def _on_cell_double_clicked(self, row, column):
        """双击表格行，提取股票代码并向主进程派发跳转联动，并弹出详情对话框"""
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            self._last_linked_code = code
            logger.info(f"Double clicked on DecisionFlow: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

        # 提取第 0 列的 UserRole 数据 (即完整原始日志 rec) 并弹出详情框
        rec_item = self.table.item(row, 0)
        rec = rec_item.data(QtCore.Qt.ItemDataRole.UserRole) if rec_item else None
        if isinstance(rec, dict):
            dlg = DecisionDetailsDialog(rec, self)
            dlg.exec()

    def _on_table_cell_changed(self, currentRow, currentColumn, previousRow, previousColumn):
        """当键盘或鼠标切换决策表格的当前行时，自动联动"""
        if currentRow < 0 or currentRow >= self.table.rowCount():
            return
        if self.table.hasFocus():
            code_item = self.table.item(currentRow, 1)
            name_item = self.table.item(currentRow, 2)
            if code_item and code_item.text():
                code = code_item.text().strip()
                if code == self._last_linked_code:
                    return
                self._last_linked_code = code
                name = name_item.text().strip() if name_item else ""
                # logger.info(f"Navigation cell changed linkage on DecisionFlowTable: {code} ({name})")
                self.code_clicked.emit(code, name)

    def _show_system_workflow_dialog(self):
        """弹出系统操作指南与风控参数详解窗口"""
        dlg = SystemWorkflowDialog(self)
        dlg.exec()

    def _show_checklist_dialog(self):
        """弹出操盘手 Checklist 流程化窗口"""
        dlg = OperatorChecklistDialog(self)
        dlg.exec()

    def _on_tab_changed(self, index):
        """当标签页切换时触发的回调，若切换到风控调优 Tab 则强制同步一次最新值"""
        if index == 1:  # 💼 内核实时持仓 (Kernel Positions & PnL)
            self._refresh_positions_tab()
        elif index == 2:  # ⚙️ 策略信号调整与风控 (Signal Tuning)
            self._sync_control_tab_ui(force=True)

    def _on_mode_combo_changed(self, index):
        """运行模式下拉框变动回调"""
        modes = ["OBSERVE", "PAPER", "CONFIRM", "LIVE_AUTO"]
        if index < 0 or index >= len(modes):
            return
            
        target_mode = modes[index]
        descriptions = [
            "模式说明: OBSERVE 纯观察旁路模式。系统仅在日志中打印信号与风控判断细节，不进行任何模拟或实盘委托。",
            "模式说明: PAPER 模拟测试模式。系统在内存中开启高保真模拟撮合，自动管理虚拟持仓、买入均价、滑点与日内盈亏。",
            "模式说明: CONFIRM 人机协同模式。风控通过的信号会被主线程调度拦截，并弹出高反差 Cyberpunk 气泡，等待操盘手放行。",
            "模式说明: LIVE_AUTO 全自动实盘模式。信号触发且满足所有前置卡口后，系统微秒级直接投递到物理柜台，完全无人值守。"
        ]
        self.lbl_mode_desc.setText(descriptions[index])
        
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                return
                
            if service.mode == target_mode:
                return
                
            success = service.set_trading_mode(target_mode)
            
            # 物理持久化实际生效的交易运行模式至本地配置文件（双写防抖）
            try:
                from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
                for filepath in (WINDOW_CONFIG_FILE, WINDOW_CONFIG_FILE.replace("window_config.json", "scale2_window_config.json")):
                    data = {}
                    if os.path.exists(filepath):
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                data = json.load(f)
                        except Exception:
                            data = {}
                            
                    if "DecisionFlowPanel" not in data:
                        data["DecisionFlowPanel"] = {}
                        
                    data["DecisionFlowPanel"]["trading_mode"] = service.mode
                    
                    tmp_file = filepath + ".tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    os.replace(tmp_file, filepath)
                logger.info(f"Persistent trading mode '{service.mode}' saved successfully.")
            except Exception as ex:
                logger.error(f"Failed to save persistent trading mode: {ex}")

            if success:
                self.lbl_preconditions_warn.setVisible(False)
                toast_message(self.parent_app, f"交易模式已成功切换为 {target_mode}")
                logger.info(f"Trading mode switched to {target_mode} via Control Panel.")
                self._update_top_status_badges()
            else:
                self.lbl_preconditions_warn.setVisible(True)
                passed, reasons = service._verify_live_preconditions()
                reasons_chinese = {
                    "NON_TRADING_SESSION": "非标准活跃交易时段 (09:15-11:30, 13:00-15:05)",
                    "BROKER_DISCONNECTED": "实盘柜台物理断开连接",
                    "KILL_SWITCH_ACTIVE": "一键紧急切断 KillSwitch 已激活挂起",
                    "RISK_LIMITS_CORRUPTED": "风控网关限额配置文件损坏",
                    "RISK_GATE_FAILED_TO_LOAD": "风控网关组件加载异常",
                    "DAILY_LOSS_BREACHED": "日内累计亏损超出回撤警示阈值",
                    "ACCOUNT_OUT_OF_SYNC": "本地PositionBook与真盘持仓偏差对账未通过",
                    "POSITION_SYNC_EXCEPTION": "对账数据源读取异常",
                    "KERNEL_VERSION_MISMATCH": "交易算法内核版本指纹校验未通过"
                }
                reasons_str = "、".join([reasons_chinese.get(r, r) for r in reasons])
                self.lbl_preconditions_warn.setText(f"🚨 升格失败！未通过的安全前置条件: {reasons_str}。系统强制重置降级为 OBSERVE 观察模式！")
                
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(0)
                self.mode_combo.blockSignals(False)
                self.lbl_mode_desc.setText(descriptions[0])
                self._update_top_status_badges()
                toast_message(self.parent_app, "模式升格失败！已降级至 OBSERVE")
            
            # 切换模式后，立即强制刷新一次持仓与资产看板以保证显示即时对齐
            self._refresh_positions_tab()
        except Exception as e:
            logger.error(f"Failed to change trading mode: {e}")

    def _on_kill_switch_toggled(self):
        """紧急切断按钮切换逻辑"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                return
                
            kill_switch = service.kill_switch
            if kill_switch.is_killed():
                kill_switch.deactivate()
                toast_message(self.parent_app, "交易安全通道已恢复！")
                logger.info("[ControlPanel] Kill switch deactivated manually.")
            else:
                kill_switch.activate()
                toast_message(self.parent_app, "🚨 紧急熔断断电切断已激活！")
                logger.warning("[ControlPanel] Kill switch activated manually.")
                
            self._update_top_status_badges()
            self._sync_control_tab_ui()
        except Exception as e:
            logger.error(f"Failed to toggle kill switch: {e}")

    def _save_and_apply_risk_limits(self):
        """从 UI 读值并重新生成 RiskLimits 实例应用于内核，并物理持久化写入本地配置文件（主动保存带弹窗提示）"""
        self._execute_save_and_apply(show_toast=True)

    def _auto_save_and_apply(self):
        """控件变更触发的后台静默自动保存与应用"""
        self._execute_save_and_apply(show_toast=False)

    def _execute_save_and_apply(self, show_toast: bool):
        """实际执行从 UI 读值、应用于内核和网关并物理持久化的核心逻辑"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            from trading_kernel.engine.risk_gate import RiskLimits
            service = get_kernel_service()
            if not service:
                return
                
            limits = RiskLimits(
                min_confidence=self.spin_min_conf.value(),
                max_pct_diff=self.spin_max_diff.value(),
                max_single_stock_position_pct=self.spin_max_stock.value() / 100.0,
                max_single_sector_exposure_pct=self.spin_max_sector.value() / 100.0,
                total_exposure_cap_pct=self.spin_total_exp.value() / 100.0,
                daily_loss_limit_amount=float(self.spin_daily_loss.value()),
                max_consecutive_losses=self.spin_losses.value(),
                min_volume=self.spin_min_volume.value()
            )
            
            # A. 内存级单例热应用
            service.limits = limits
            
            # B. 应用到网关 RiskManager 风控管理器参数
            try:
                from trade_gateway import get_trade_gateway
                trade_gw = getattr(self.parent_app, "_trade_gw", None) or get_trade_gateway()
                if trade_gw and trade_gw.risk_manager:
                    trade_gw.risk_manager.update_params(
                        max_positions=self.spin_rm_max_pos.value(),
                        max_pos_pct=self.spin_rm_max_pos_pct.value() / 100.0,
                        max_daily_loss=self.spin_rm_max_daily_loss.value() / 100.0,
                        stop_loss_pct=self.spin_rm_stop_loss_pct.value() / 100.0
                    )
            except Exception as e_rm:
                logger.error(f"Failed to apply RiskManager parameters: {e_rm}")

            # C. 物理持久化至本地 JSON 配置文件（双写以兼容高DPI/缩放配置环境）
            try:
                scale = self._get_dpi_scale_factor()
                from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
                
                for filepath in (WINDOW_CONFIG_FILE, WINDOW_CONFIG_FILE.replace("window_config.json", "scale2_window_config.json")):
                    data = {}
                    if os.path.exists(filepath):
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                data = json.load(f)
                        except Exception:
                            data = {}
                            
                    if "DecisionFlowPanel" not in data:
                        data["DecisionFlowPanel"] = {}
                        
                    data["DecisionFlowPanel"]["risk_limits"] = {
                        "min_confidence": limits.min_confidence,
                        "max_pct_diff": limits.max_pct_diff,
                        "max_single_stock_position_pct": limits.max_single_stock_position_pct,
                        "max_single_sector_exposure_pct": limits.max_single_sector_exposure_pct,
                        "total_exposure_cap_pct": limits.total_exposure_cap_pct,
                        "daily_loss_limit_amount": limits.daily_loss_limit_amount,
                        "max_consecutive_losses": limits.max_consecutive_losses,
                        "min_volume": limits.min_volume
                    }
                    
                    data["DecisionFlowPanel"]["risk_manager"] = {
                        "max_positions": self.spin_rm_max_pos.value(),
                        "max_pos_pct": self.spin_rm_max_pos_pct.value() / 100.0,
                        "max_daily_loss": self.spin_rm_max_daily_loss.value() / 100.0,
                        "stop_loss_pct": self.spin_rm_stop_loss_pct.value() / 100.0
                    }
                    
                    # 原子替换写入
                    tmp_file = filepath + ".tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    os.replace(tmp_file, filepath)
                    
                logger.info("Persistent RiskLimits and RiskManager parameters saved to local config files successfully.")
            except Exception as ex:
                logger.error(f"Failed to save persistent configurations to config file: {ex}")
            
            if show_toast:
                toast_message(self.parent_app, "✅ 风控与网关参数已成功实时生效并保存！")
            logger.info(f"New RiskLimits applied: {limits}")
        except Exception as e:
            logger.error(f"Failed to apply new risk limits: {e}")
            if show_toast:
                toast_message(self.parent_app, "❌ 保存风控参数失败！")

    def _sync_control_tab_ui(self, force: bool = False):
        """将内核实时值反向同步至控制面板 UI 控件中（带高能脏检测机制）"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                return
                
            # A. 同步交易模式 (Dirty Check)
            mode = service.mode
            mode_map = {"OBSERVE": 0, "PAPER": 1, "CONFIRM": 2, "LIVE_AUTO": 3}
            idx = mode_map.get(mode, 0)
            if self.mode_combo.currentIndex() != idx:
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(idx)
                self.mode_combo.blockSignals(False)
            
            # B. 同步 KillSwitch 状态 (Dirty Check 避免高频重复设置样式表引发微秒级 CPU 卡死)
            is_killed = service.kill_switch.is_killed()
            if self._last_is_killed != is_killed:
                self._last_is_killed = is_killed
                if is_killed:
                    self.lbl_kill_status_desc.setText("通道状态: 🚨 紧急熔断切断中 (ALL TRADING BLOCKED)")
                    self.lbl_kill_status_desc.setStyleSheet("font-weight: bold; font-size: 11px; color: #FF1744;")
                    self.btn_kill_toggle.setText("✅ 恢复交易通道 (ENABLE CHANNELS)")
                    self.btn_kill_toggle.setStyleSheet("""
                        QPushButton {
                            background-color: #00E676;
                            color: #121214;
                            font-weight: bold;
                            border: 1px solid #00E676;
                            border-radius: 4px;
                            padding: 6px 16px;
                        }
                        QPushButton:hover {
                            background-color: #00C853;
                        }
                    """)
                else:
                    self.lbl_kill_status_desc.setText("通道状态: ✅ 交易通道正常，买入决策监听中...")
                    self.lbl_kill_status_desc.setStyleSheet("font-weight: bold; font-size: 11px; color: #00E676;")
                    self.btn_kill_toggle.setText("🚨 激活紧急熔断切断 (KILL SWITCH)")
                    self.btn_kill_toggle.setStyleSheet("""
                        QPushButton {
                            background-color: #D50000;
                            color: #FFFFFF;
                            font-weight: bold;
                            border: 1px solid #FF1744;
                            border-radius: 4px;
                            padding: 6px 16px;
                        }
                        QPushButton:hover {
                            background-color: #FF1744;
                        }
                    """)
                
            # C. 同步风控各极限阈值控件 (脏检查防抖震颤)
            # 当用户处于“⚙️ 策略信号调整与风控”Tab 页时，为了不打断/重写用户的手动输入/调整过程，
            # 除非显式指定 force=True (如刚刚切换到此 Tab 或者是初次加载)，否则跳过对输入框阈值的强制同步。
            if force or self.tabs.currentIndex() != 2:
                v_min_conf = service.limits.min_confidence
                if abs(self.spin_min_conf.value() - v_min_conf) > 1e-4:
                    self.spin_min_conf.blockSignals(True)
                    self.spin_min_conf.setValue(v_min_conf)
                    self.spin_min_conf.blockSignals(False)
    
                v_max_diff = service.limits.max_pct_diff
                if abs(self.spin_max_diff.value() - v_max_diff) > 1e-4:
                    self.spin_max_diff.blockSignals(True)
                    self.spin_max_diff.setValue(v_max_diff)
                    self.spin_max_diff.blockSignals(False)
    
                v_max_stock = service.limits.max_single_stock_position_pct * 100.0
                if abs(self.spin_max_stock.value() - v_max_stock) > 1e-4:
                    self.spin_max_stock.blockSignals(True)
                    self.spin_max_stock.setValue(v_max_stock)
                    self.spin_max_stock.blockSignals(False)
    
                v_max_sector = service.limits.max_single_sector_exposure_pct * 100.0
                if abs(self.spin_max_sector.value() - v_max_sector) > 1e-4:
                    self.spin_max_sector.blockSignals(True)
                    self.spin_max_sector.setValue(v_max_sector)
                    self.spin_max_sector.blockSignals(False)
    
                v_total_exp = service.limits.total_exposure_cap_pct * 100.0
                if abs(self.spin_total_exp.value() - v_total_exp) > 1e-4:
                    self.spin_total_exp.blockSignals(True)
                    self.spin_total_exp.setValue(v_total_exp)
                    self.spin_total_exp.blockSignals(False)
    
                v_daily_loss = int(service.limits.daily_loss_limit_amount)
                if self.spin_daily_loss.value() != v_daily_loss:
                    self.spin_daily_loss.blockSignals(True)
                    self.spin_daily_loss.setValue(v_daily_loss)
                    self.spin_daily_loss.blockSignals(False)
    
                v_losses = service.limits.max_consecutive_losses
                if self.spin_losses.value() != v_losses:
                    self.spin_losses.blockSignals(True)
                    self.spin_losses.setValue(v_losses)
                    self.spin_losses.blockSignals(False)

                v_min_volume = service.limits.min_volume
                if abs(self.spin_min_volume.value() - v_min_volume) > 1e-4:
                    self.spin_min_volume.blockSignals(True)
                    self.spin_min_volume.setValue(v_min_volume)
                    self.spin_min_volume.blockSignals(False)
                    
                # ── 同步 RiskManager 参数 ──
                try:
                    from trade_gateway import get_trade_gateway
                    trade_gw = getattr(self.parent_app, "_trade_gw", None) or get_trade_gateway()
                    if trade_gw and trade_gw.risk_manager:
                        rm = trade_gw.risk_manager
                        
                        v_rm_max_pos = rm.MAX_POSITIONS
                        if self.spin_rm_max_pos.value() != v_rm_max_pos:
                            self.spin_rm_max_pos.blockSignals(True)
                            self.spin_rm_max_pos.setValue(v_rm_max_pos)
                            self.spin_rm_max_pos.blockSignals(False)

                        v_rm_max_pos_pct = rm.MAX_POS_PCT * 100.0
                        if abs(self.spin_rm_max_pos_pct.value() - v_rm_max_pos_pct) > 1e-4:
                            self.spin_rm_max_pos_pct.blockSignals(True)
                            self.spin_rm_max_pos_pct.setValue(v_rm_max_pos_pct)
                            self.spin_rm_max_pos_pct.blockSignals(False)

                        v_rm_max_daily_loss = rm.MAX_DAILY_LOSS * 100.0
                        if abs(self.spin_rm_max_daily_loss.value() - v_rm_max_daily_loss) > 1e-4:
                            self.spin_rm_max_daily_loss.blockSignals(True)
                            self.spin_rm_max_daily_loss.setValue(v_rm_max_daily_loss)
                            self.spin_rm_max_daily_loss.blockSignals(False)

                        v_rm_stop_loss_pct = rm.STOP_LOSS_PCT * 100.0
                        if abs(self.spin_rm_stop_loss_pct.value() - v_rm_stop_loss_pct) > 1e-4:
                            self.spin_rm_stop_loss_pct.blockSignals(True)
                            self.spin_rm_stop_loss_pct.setValue(v_rm_stop_loss_pct)
                            self.spin_rm_stop_loss_pct.blockSignals(False)
                except Exception as e_rm_sync:
                    logger.error(f"Error syncing RiskManager UI parameters: {e_rm_sync}")
            
        except Exception as e:
            logger.error(f"Error syncing Control Tab UI: {e}")

    def _update_top_status_badges(self):
        """高反差同步刷新决策流水表顶部的核心状态徽章（带高速脏检测）"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                return
                
            mode = service.mode
            is_killed = service.kill_switch.is_killed()
            
            # 脏检测自愈：模式与切断开关均未变更时直接短路跳过，实现完美 0 CPU 开销
            if self._last_top_mode == mode and self._last_top_killed == is_killed:
                return
                
            self._last_top_mode = mode
            self._last_top_killed = is_killed
            
            # 1. 刷新运行模式徽章
            if mode == "LIVE_AUTO":
                self.lbl_mode_badge.setText("🔴 实盘自动")
                self.lbl_mode_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #FF1744; border-radius: 3px; color: #FF1744; background-color: #1A1A1F;")
            elif mode == "CONFIRM":
                self.lbl_mode_badge.setText("🟡 人工拦截")
                self.lbl_mode_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #FFD600; border-radius: 3px; color: #FFD600; background-color: #1A1A1F;")
            elif mode == "PAPER":
                self.lbl_mode_badge.setText("🔵 高真模拟")
                self.lbl_mode_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #00E5FF; border-radius: 3px; color: #00E5FF; background-color: #1A1A1F;")
            else:
                self.lbl_mode_badge.setText("⚪ 旁路记账")
                self.lbl_mode_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #444; border-radius: 3px; color: #A0A0A5; background-color: #1A1A1F;")
                
            # 2. 刷新紧急熔断徽章
            if is_killed:
                self.lbl_kill_badge.setText("🚨 熔断切断")
                self.lbl_kill_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #FF1744; border-radius: 3px; color: #FF1744; background-color: #2D0000;")
            else:
                self.lbl_kill_badge.setText("✅ 通道正常")
                self.lbl_kill_badge.setStyleSheet("font-weight: bold; padding: 2px 6px; border: 1px solid #00E676; border-radius: 3px; color: #00E676; background-color: #1A1A1F;")
        except Exception as e:
            logger.error(f"Failed to update status badges: {e}")

    def _load_initial_records(self):
        """冷启动时快速扫描读取 JSONL 末尾最多 200 条决策，规避白屏"""
        self._last_rendered_state = None
        if not os.path.exists(self.journal_path):
            self.status_label.setText("⚠️ 未检测到交易流水日志文件 logs/trading_kernel_trace.jsonl")
            return

        try:
            file_size = os.path.getsize(self.journal_path)
            self._last_file_size = file_size
            self._last_modified_time = os.path.getmtime(self.journal_path)

            records = []
            with open(self.journal_path, "r", encoding="utf-8") as f:
                # 采用简单、安全的尾部行扫描，提取最后 300 行 JSON，避免全文件解析的爆内存问题
                lines = f.readlines()[-300:]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue

            # 仅截取最后 200 条进行表格渲染
            records = records[-200:]
            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)
            for rec in records:
                self._append_record_to_table(rec)
            self.table.setSortingEnabled(True)
            self.table.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)

            self.status_label.setText(f"✅ 成功载入历史 {len(records)} 条决策，实时监听中...")
            # 自动滚动到最新一行
            self.table.scrollToBottom()
            
            # 首次载入同步加载实时持仓明细页
            self._refresh_positions_tab()
        except Exception as e:
            logger.error(f"Failed to load initial records: {e}\n{traceback.format_exc()}")
            self.status_label.setText(f"❌ 载入历史流水失败: {e}")

    def _check_and_update_records(self):
        """定时扫描函数：仅执行极其高效 of 增量日志文件追溯以确保主线程 20ms 的 UI 调度预算"""
        if not os.path.exists(self.journal_path):
            return

        try:
            file_size = os.path.getsize(self.journal_path)
            if file_size == self._last_file_size:
                return

            mtime = os.path.getmtime(self.journal_path)
            
            # 若文件被物理截断或重建，则全量重载
            if file_size < self._last_file_size:
                logger.info("Journal file truncated, reloading...")
                self._load_initial_records()
                return

            # 精准的增量尾部寻址读取 (零拷贝，高速定位)
            new_records = []
            with open(self.journal_path, "r", encoding="utf-8") as f:
                f.seek(self._last_file_size)
                new_lines = f.readlines()
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        new_records.append(json.loads(line))
                    except Exception:
                        continue

            # 更新追踪指针
            self._last_file_size = file_size
            self._last_modified_time = mtime

            # 增量追加至表格
            if new_records:
                self.table.setSortingEnabled(False)
                for rec in new_records:
                    self._append_record_to_table(rec)
                self.table.setSortingEnabled(True)
                self.table.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
                self.status_label.setText(f"⚡ 增量更新完成，新捕获 {len(new_records)} 条决策信号 (最新更新: {time.strftime('%H:%M:%S')})")
                self.table.scrollToBottom()
                # 重新应用过滤
                self._filter_table()
                
                # 🌟 增量捕获后，立即触发一次实时持仓刷新，确保仓位变动能瞬间对齐
                self._refresh_positions_tab()
                
        except Exception as e:
            logger.error(f"Error in incremental records check: {e}")

    def _slow_update_cycle(self):
        """低频轮询周期：执行状态徽章同步、控制页同步、持仓刷新与决策流停滞监控，释放主线程 CPU 开销"""
        # A. 同步顶部运行模式与熔断徽章
        self._update_top_status_badges()
        
        # B. 同步控制与风控参数 UI 状态
        self._sync_control_tab_ui()
        
        # C. 刷新实时持仓与浮盈数据
        self._refresh_positions_tab()
        
        # D. 执行 [GUI Watchdog] 日志流更新停滞状态审计
        try:
            now = time.time()
            try:
                from JohnsonUtil import commonTips as cct
            except ImportError:
                try:
                    import commonTips as cct
                except ImportError:
                    import common as cct
            
            is_trade_day = cct.get_trade_date_status()
            now_dt = datetime.now()
            now_time_int = now_dt.hour * 100 + now_dt.minute
            is_active_trading = is_trade_day and ((930 <= now_time_int <= 1130) or (1300 <= now_time_int <= 1500))
            
            if not hasattr(self, '_last_growth_time'):
                self._last_growth_time = now
                
            if is_active_trading:
                # 磁盘 I/O 节流：仅在低频周期检查文件大小更新，避免高频系统调用
                if os.path.exists(self.journal_path):
                    current_size = os.path.getsize(self.journal_path)
                    if not hasattr(self, '_last_tracked_size'):
                        self._last_tracked_size = current_size
                    if current_size > self._last_tracked_size:
                        self._last_growth_time = now
                        self._last_tracked_size = current_size
                
                inactive_duration = now - self._last_growth_time
                if inactive_duration > 300: # 5分钟没有更新
                    minutes = inactive_duration / 60
                    self.status_label.setText(f"⚠️ [FlowWatchdog] 决策流已停滞超过 {minutes:.1f} 分钟！请检查后台策略与行情")
                    self.status_label.setStyleSheet("color: #FFCC00; font-weight: bold;")
                else:
                    text = self.status_label.text()
                    if "[FlowWatchdog]" in text:
                        self.status_label.setText("⚡ 决策流正常，监听中...")
                        self.status_label.setStyleSheet("")
            else:
                text = self.status_label.text()
                if "[FlowWatchdog]" in text:
                    self.status_label.setText("⚡ 盘外/休市时段，监听暂停。")
                    self.status_label.setStyleSheet("")
        except Exception as e_watch:
            logger.warning(f"Error in DecisionFlowPanel FlowWatchdog slow cycle: {e_watch}")

    def _parse_timestamp(self, ts_str: Any) -> str:
        """防弹自愈时间戳解析器：统一格式化为 MM-DD HH:MM:SS"""
        if not ts_str:
            return datetime.now().strftime("%m-%d %H:%M:%S")
        try:
            ts_str_clean = str(ts_str).strip()
            if "T" in ts_str_clean:
                parts = ts_str_clean.split("T")
                date_part = parts[0][5:] # "05-23"
                time_part = parts[1][:8] # "20:30:15"
                return f"{date_part} {time_part}"
            elif " " in ts_str_clean:
                parts = ts_str_clean.split(" ")
                date_part = parts[0][5:]
                time_part = parts[1][:8]
                return f"{date_part} {time_part}"
            elif len(ts_str_clean) >= 8:
                return ts_str_clean[-8:]
            else:
                return ts_str_clean
        except Exception:
            return str(ts_str)

    def _append_record_to_table(self, rec: dict):
        """核心解析函数：从 `JsonlJournal` 的多级 nested 结构或人工确认审计日志中精准提炼出扁平 of UI 字段并渲染"""
        # 判断是否为人工确认审计记录 (Phase 7: Human Confirmation Audit)
        is_audit = (rec.get("journal_type") == "HUMAN_CONFIRMATION_AUDIT")
        
        if is_audit:
            orig_order = rec.get("original_order", {})
            confirmed = rec.get("confirmed", False)
            reason = rec.get("override_reason", "")
            meta = rec.get("override_metadata", {})
            
            # 提取时间 (防弹 Fallback)
            timestamp = self._parse_timestamp(rec.get("timestamp", ""))
            
            code = orig_order.get("code", "")
            name = "人工确认"
            state = "AUDIT"
            
            # 下单占比微调渲染
            orig_size = float(orig_order.get("size_pct", 0.0)) * 100.0
            if meta.get("size_changed"):
                act_size = float(meta.get("actual_size_pct", 0.0)) * 100.0
                size_pct = f"{orig_size:.1f}% ➔ {act_size:.1f}%"
                action = "✍️ 覆盖"
            else:
                size_pct = f"{orig_size:.1f}%"
                action = "👤 确认" if confirmed else "❌ 拒绝"
                
            confidence = "N/A"
            risk_allowed = "Confirmed" if confirmed else "Rejected"
            reject_code = "TRADER_REJECT" if not confirmed else ""
            stop_price = "N/A"
            trace_id = "AUDIT"
            short_trace_id = "AUDIT"
            
            # 合并理由
            reason_summary = f"👤 操盘手干预 | {reason}"
            if meta.get("size_changed"):
                reason_summary += f" | 占比微调: {orig_size:.0f}% ➔ {act_size:.0f}%"
                
        else:
            # 1. 字段解包 (常规决策 trace)
            trace = rec.get("trace", {})
            sig = rec.get("signal", {})
            intent = rec.get("intent", {})
            risk = rec.get("risk", {})
            kernel_res = rec.get("kernel_result", {})
            if not isinstance(kernel_res, dict):
                kernel_res = {}
            
            # 2. 字段映射提取 (防弹 Fallback)
            timestamp = self._parse_timestamp(rec.get("journal_ts", "") or trace.get("timestamp", ""))
    
            code = sig.get("code", "")
            name = sig.get("name", "")
            state = kernel_res.get("kernel_state", "") or rec.get("kernel_state", "") or trace.get("state", "FLAT")
            action = kernel_res.get("kernel_action", "") or rec.get("kernel_action", "") or risk.get("final_action", "")
            
            size_val = kernel_res.get("kernel_size_pct", 0.0) or rec.get("kernel_size_pct", 0.0) or risk.get("final_size_pct", 0.0)
            size_pct = f"{float(size_val):.1f}%" if size_val is not None else "0.0%"
            
            confidence = str(kernel_res.get("kernel_confidence", "") or rec.get("kernel_confidence", "") or intent.get("confidence", ""))
            
            allowed_val = kernel_res.get("kernel_allowed", True) if "kernel_allowed" in kernel_res else risk.get("allowed", True)
            risk_allowed = "Allowed" if allowed_val else "Blocked"
            
            reject_code = kernel_res.get("kernel_reject_code", "") or rec.get("kernel_reject_code", "")
            if not reject_code and not allowed_val:
                reject_code = risk.get("reject_context", {}).get("message") or risk.get("reject_context", {}).get("code", "RISK_REJECT")
            
            # 双重保险：对于残留的英文代码进行本地中文简短转换
            RISK_CN_SHORT = {
                "CONSECUTIVE_LOSS_COOLDOWN": "连续亏损冷静期拦截",
                "DAILY_LOSS_LIMIT_EXCEEDED": "每日亏损超限拦截",
                "HIGH_EXTENSION_NO_CHASE": "超强拉升防追高拦截",
                "NON_TRADING_SESSION": "非交易时间段拦截",
                "BLACKLISTED_SYMBOL": "黑名单股票拦截",
                "SIGNAL_EXPIRED": "信号过期失效",
                "LOW_VOLUME_BLOCKED": "极度缩量拦截",
                "BUY_DISABLED": "买入被全局禁用",
                "LOW_CONFIDENCE": "置信度不足拦截",
                "ALREADY_IN_TRADE": "已有持仓限制重复开仓",
                "ADD_REQUIRES_POSITION": "加仓无底仓拦截",
                "SINGLE_STOCK_EXPOSURE_EXCEEDED": "单股持仓限额超限",
                "SECTOR_EXPOSURE_EXCEEDED": "单板块暴露限额超限",
                "TOTAL_EXPOSURE_EXCEEDED": "总仓位暴露限额超限",
                "RISK_REJECT": "风控拒绝",
                "SIMULATION_BYPASS": "模拟测试绕过",
                "BLOCK": "风控拦截",
            }
            if reject_code in RISK_CN_SHORT:
                reject_code = RISK_CN_SHORT[reject_code]
            
            stop_price_val = kernel_res.get("kernel_stop_price", 0.0) or rec.get("kernel_stop_price", 0.0) or intent.get("stop_price", 0.0)
            stop_price = f"{float(stop_price_val):.2f}" if stop_price_val else "0.00"
            
            trace_id = trace.get("trace_id", "") or kernel_res.get("kernel_trace_id", "") or rec.get("kernel_trace_id", "")
            short_trace_id = trace_id[:8] if trace_id else "N/A"
            
            reason_parts = []
            features = sig.get("features", {})
            is_leader = features.get("is_leader", False)
            priority = features.get("priority", 0.0)
            raw_reason = features.get("raw_reason", "")
            
            if is_leader:
                reason_parts.append("⭐龙头领涨")
            if priority and priority > 0:
                reason_parts.append(f"强度:{priority}")
            
            kernel_reason = rec.get("kernel_reason", {})
            if isinstance(kernel_reason, dict):
                for r_k, r_v in kernel_reason.items():
                    if r_v and str(r_v).strip().lower() != "false":
                        reason_parts.append(f"{r_k}={r_v}")
            
            if raw_reason:
                reason_parts.append(raw_reason)
                
            reason_summary = " | ".join(reason_parts) if reason_parts else "常规扫描决策"
 
        # 3. 动态追加物理表格行
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
 
        # 4. 卡片着色与项目填充
        items_data = [
            (timestamp, None),
            (code, "#FFFFFF"),
            (name, "#C2C2C6"),
            (state, "#90A4AE"),  # 状态使用温和蓝灰色
            (action, None),     # 动作根据买卖着色
            (size_pct, None),
            (confidence, "#FFEB3B"), # 打分高亮黄
            (risk_allowed, None),    # 风控红绿卡片
            (str(reject_code), "#FF8A80"),
            (stop_price, "#B0BEC5"),
            (short_trace_id, "#78909C"),
            (reason_summary, "#81C784")  # 决策理由柔和绿色
        ]

        # 颜色映射表
        action_colors = {
            "BUY": "#00E676",      # 亮盈绿
            "ADD": "#00E5FF",      # 亮青
            "SELL": "#FF1744",     # 猩红
            "REDUCE": "#FF9100",   # 橙红
            "FLAT": "#90A4AE"      # 蓝灰
        }

        for col_idx, (text, color_hex) in enumerate(items_data):
            sort_val = text
            if col_idx == 5:
                # 拟仓位
                sort_val = size_val if ('size_val' in locals() and size_val is not None) else 0.0
            elif col_idx == 6:
                # 打分
                try:
                    sort_val = float(confidence) if (confidence and confidence != "N/A") else -1.0
                except ValueError:
                    sort_val = -1.0
            elif col_idx == 9:
                # 止损价
                try:
                    sort_val = float(stop_price_val) if ('stop_price_val' in locals() and stop_price_val) else 0.0
                except ValueError:
                    sort_val = 0.0

            cell_item = SortableTableWidgetItem(str(text), sort_val)
            cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            
            # 设置默认前景色
            if color_hex:
                cell_item.setForeground(QtGui.QColor(color_hex))
                
            # 个性化高亮
            if col_idx == 4:  # Action
                act_upper = str(text).upper()
                if act_upper in action_colors:
                    cell_item.setForeground(QtGui.QColor(action_colors[act_upper]))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 10, QtGui.QFont.Weight.Bold))
            elif col_idx == 5 and action in ("BUY", "ADD", "✍️ 覆盖", "👤 确认"): # Pct / Confirmation
                cell_item.setForeground(QtGui.QColor("#00E676"))
            elif col_idx == 7: # Risk Allowed / Confirmation status
                if text in ("Allowed", "Confirmed"):
                    cell_item.setForeground(QtGui.QColor("#00E676"))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                else:
                    cell_item.setForeground(QtGui.QColor("#FF1744"))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
            elif col_idx == 10 and trace_id: # Trace ID 悬浮提示
                cell_item.setToolTip(f"防伪全量签名 ID: {trace_id}")
                
            if col_idx == 0:
                cell_item.setData(QtCore.Qt.ItemDataRole.UserRole, rec)
                
            self.table.setItem(row_idx, col_idx, cell_item)

    def _filter_table(self):
        """本地搜索快速过滤逻辑，无需重读磁盘，体验流畅"""
        query = self.search_input.text().strip().lower()
        for row in range(self.table.rowCount()):
            if not query:
                self.table.setRowHidden(row, False)
                continue
                
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _on_search_text_changed(self):
        """输入内容变动时防抖 150ms，规避高频重绘，提升流畅度"""
        self._filter_timer.start(150)

    def _show_context_menu(self, pos):
        """为表格行提供精美的右键快捷菜单，支持 Trace ID/代码/理由复制"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        row = index.row()
        menu = QtWidgets.QMenu(self)
        
        # 扁平精致暗黑菜单风格
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E24;
                color: #E2E2E6;
                border: 1px solid #2E2E35;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #00E676;
                color: #121214;
            }
        """)
        
        # 获取各单元格的值
        code_item = self.table.item(row, 1)
        trace_item = self.table.item(row, 10)
        reason_item = self.table.item(row, 11)
        
        trace_id = trace_item.toolTip().replace("防伪全量签名 ID: ", "") if trace_item else ""
        if not trace_id and trace_item:
            trace_id = trace_item.text()
            
        code = code_item.text().strip() if code_item else ""
        reason = reason_item.text().strip() if reason_item else ""
        
        # 动作一：复制 Trace ID
        if trace_id and trace_id != "N/A" and trace_id != "AUDIT":
            action_copy_trace = menu.addAction("📋 复制完整 Trace ID")
            action_copy_trace.triggered.connect(lambda: self._copy_to_clipboard(trace_id, "Trace ID"))
            
        # 动作二：复制股票代码
        if code:
            action_copy_code = menu.addAction(f"📋 复制股票代码 ({code})")
            action_copy_code.triggered.connect(lambda: self._copy_to_clipboard(code, "股票代码"))
            
        # 动作三：复制完整决策理由
        if reason:
            action_copy_reason = menu.addAction("📋 复制决策理由")
            action_copy_reason.triggered.connect(lambda: self._copy_to_clipboard(reason, "决策理由"))

        # 动作四：多选清理/直接删除选中数据 (清除显示垃圾)
        selected_indexes = self.table.selectionModel().selectedRows()
        selected_rows = [idx.row() for idx in selected_indexes]
        if row not in selected_rows:
            selected_rows.append(row)

        menu.addSeparator()
        action_delete = menu.addAction(f"❌ 清理选中记录 ({len(selected_rows)}条)")
        action_delete.triggered.connect(lambda: self._delete_selected_rows(selected_rows))
            
        menu.exec(self.table.viewport().mapToGlobal(pos))
        
    def _delete_selected_rows(self, rows_to_delete):
        """支持多选直接右键删除/清理数据（仅清理UI显示，不篡改物理流水日志，安全平滑）"""
        if not rows_to_delete:
            return
        
        # 降序排序，防止先删除前面的行导致后面行的 row_idx 偏移
        rows_to_delete = sorted(list(set(rows_to_delete)), reverse=True)
        
        self.table.setSortingEnabled(False)
        for r in rows_to_delete:
            self.table.removeRow(r)
        self.table.setSortingEnabled(True)
        
        toast_message(self.parent_app, f"已从显示中清理 {len(rows_to_delete)} 条决策记录")

    def _copy_to_clipboard(self, text: str, label: str):
        """将文本安全复制到剪贴板，并弹出 Toast 提示"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        toast_message(self.parent_app, f"已复制 {label}")

    def _force_reload(self):
        """强制清空重载 (自愈修复时一键恢复)"""
        logger.info("Force reloading decision flow logs...")
        self._load_initial_records()
        toast_message(self.parent_app, "决策流水已强制重载")

    def _clear_view(self):
        """清空当前表格显示 (不删除物理文件)"""
        self.table.blockSignals(True)
        try:
            # 显式在 Python 持有 GIL 的控制范围内，逐行清空 UserRole 绑定的字典数据，
            # 避免在 setRowCount(0) 批量销毁时底层 C++ 析构导致多线程 GC 冲突。
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, None)
            self.table.setRowCount(0)
            self.status_label.setText("显示已清空。等待新增决策流水信号...")
        finally:
            self.table.blockSignals(False)
        toast_message(self.parent_app, "表格显示已清空")

    def closeEvent(self, event):
        """窗口关闭时自动注销并保存位置及列宽参数"""
        try:
            # 1. 保存窗口尺寸
            self.save_window_position_qt_visual(self, "DecisionFlowPanel")
            
            # 2. 精准保存列宽与表头布局状态 (Hex 格式)
            header_state = self.table.horizontalHeader().saveState().toHex().data().decode("utf-8")
            
            # 读取现有 window_config.json 并更新
            scale = self._get_dpi_scale_factor()
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
                    
            if "DecisionFlowPanel" not in data:
                data["DecisionFlowPanel"] = {}
            data["DecisionFlowPanel"]["header_state"] = header_state
            
            # 精准保存持仓表格列宽表头状态
            if hasattr(self, "pos_table"):
                pos_header_state = self.pos_table.horizontalHeader().saveState().toHex().data().decode("utf-8")
                data["DecisionFlowPanel"]["pos_header_state"] = pos_header_state
            
            if hasattr(self, "chk_show_closed"):
                data["DecisionFlowPanel"]["show_closed"] = self.chk_show_closed.isChecked()
            
            # 原子写入
            tmp_file = config_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_file, config_file)
            
            logger.info("DecisionFlowPanel position and header states saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save window state: {e}\n{traceback.format_exc()}")
        
        # 从父窗口引用中抹除，有利于 GC 回收
        if self.parent_app and hasattr(self.parent_app, "panel_manager"):
            self.parent_app.panel_manager._decision_flow_win = None
            
        event.accept()

    def _restore_header_state(self):
        """恢复用户手动调整的列宽与排序状态"""
        try:
            scale = self._get_dpi_scale_factor()
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                restored_any = False
                if "DecisionFlowPanel" in data:
                    panel_cfg = data["DecisionFlowPanel"]
                    if "header_state" in panel_cfg:
                        hex_state = panel_cfg["header_state"]
                        byte_state = QtCore.QByteArray.fromHex(hex_state.encode("utf-8"))
                        self.table.horizontalHeader().restoreState(byte_state)
                        restored_any = True
                    if "pos_header_state" in panel_cfg and hasattr(self, "pos_table"):
                        pos_hex_state = panel_cfg["pos_header_state"]
                        pos_byte_state = QtCore.QByteArray.fromHex(pos_hex_state.encode("utf-8"))
                        self.pos_table.horizontalHeader().restoreState(pos_byte_state)
                        restored_any = True
                    if "show_closed" in panel_cfg and hasattr(self, "chk_show_closed"):
                        self.chk_show_closed.blockSignals(True)
                        self.chk_show_closed.setChecked(bool(panel_cfg["show_closed"]))
                        self.chk_show_closed.blockSignals(False)
                        
                if restored_any:
                    logger.info("DecisionFlowPanel header states restored successfully.")
                    return True
        except Exception as e:
            logger.error(f"Failed to restore DecisionFlowPanel header states: {e}")
        return False

    def _safe_restore_and_adjust(self):
        """延迟执行的安全表头恢复与列宽异常校正，确保物理尺寸已就绪且防范 0 宽隐藏死锁"""
        try:
            has_restored = self._restore_header_state()
            if not has_restored:
                self._adjust_column_widths()
            else:
                # 🛡️ 异常列宽自动校正门禁：防范此前因 bug 导致的列宽被意外折叠为 0 像素的死锁
                fit_needed = False
                if hasattr(self, "table") and self.table.columnCount() == 12:
                    for idx in range(self.table.columnCount()):
                        if self.table.columnWidth(idx) < 15:
                            fit_needed = True
                            break
                if not fit_needed and hasattr(self, "pos_table") and self.pos_table.columnCount() == 10:
                    for idx in range(self.pos_table.columnCount()):
                        if self.pos_table.columnWidth(idx) < 15:
                            fit_needed = True
                            break
                if fit_needed:
                    logger.warning("Detected abnormal column width (<15px) from saved states, triggering auto-fit self-healing.")
                    self._adjust_column_widths()
        except Exception as e:
            logger.error(f"Error in _safe_restore_and_adjust: {e}")

    def showEvent(self, event):
        """展现时自适应"""
        super().showEvent(event)
        self.table.scrollToBottom()

    def _on_show_closed_toggled(self, checked):
        """显示/隐藏已平仓选项勾选变更回调"""
        try:
            scale = self._get_dpi_scale_factor()
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            if "DecisionFlowPanel" not in data:
                data["DecisionFlowPanel"] = {}
            data["DecisionFlowPanel"]["show_closed"] = checked
            
            # 原子写入
            tmp_file = config_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_file, config_file)
        except Exception as e:
            logger.error(f"Failed to save show_closed state on toggled: {e}")

        # 强制清除渲染指纹以触发重新渲染
        if hasattr(self, "_last_rendered_state"):
            delattr(self, "_last_rendered_state")
        self._refresh_positions_tab()

    def _on_pos_cell_double_clicked(self, row, column):
        """双击持仓表格行，提取持仓个股代码并向主进程派发跳转联动"""
        code_item = self.pos_table.item(row, 0)
        name_item = self.pos_table.item(row, 1)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            self._last_linked_code = code
            logger.info(f"Double clicked on KernelPosition: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

    def _on_pos_table_cell_changed(self, currentRow, currentColumn, previousRow, previousColumn):
        """当键盘或鼠标切换持仓表格的当前行时，自动联动"""
        if currentRow < 0 or currentRow >= self.pos_table.rowCount():
            return
        if self.pos_table.hasFocus():
            code_item = self.pos_table.item(currentRow, 0)
            name_item = self.pos_table.item(currentRow, 1)
            if code_item and code_item.text():
                code = code_item.text().strip()
                if code == self._last_linked_code:
                    return
                self._last_linked_code = code
                name = name_item.text().strip() if name_item else ""
                logger.info(f"Navigation cell changed linkage on KernelPositionsTable: {code} ({name})")
                self.code_clicked.emit(code, name)

    def _refresh_positions_tab(self):
        """核心无摩擦刷新：直接从 `get_kernel_service()` 单例物理提取内存中最新持仓与浮盈状态"""
        selected_code = None
        try:
            # 记录当前选中的股票代码，以备在刷新后恢复选中态，防止高频刷新丢失选中行与闪烁
            curr_row = self.pos_table.currentRow()
            if curr_row >= 0:
                item = self.pos_table.item(curr_row, 0)
                if item:
                    selected_code = item.text().strip()
        except Exception:
            pass

        self.pos_table.blockSignals(True)
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                logger.warning("Kernel service not available yet.")
                self.pos_table.blockSignals(False)
                return
                
            mode = service.mode
            executor = service.executor
            
            # 物理对账数据源切换自愈：选择哪种模式显示哪种模式 of 持仓记录
            if mode == "LIVE_AUTO":
                adapter = service.broker_adapter
            elif mode == "CONFIRM":
                adapter = service.confirm_adapter
            elif mode == "PAPER":
                adapter = service.paper_adapter
            else:
                # 旁路记账 (OBSERVE) 模式下，自动降级展示高真模拟 (PAPER) 的持仓以保障两边数据一致性与可视化对齐！
                adapter = service.paper_adapter
            
            # 1. 尝试从 df_all / current_df 更新最新市场价
            if adapter is not None:
                temp_positions = adapter.get_positions()
                if hasattr(adapter, "update_market_price") and self.parent_app:
                    df = None
                    if hasattr(self.parent_app, "df_all") and self.parent_app.df_all is not None and not self.parent_app.df_all.empty:
                        df = self.parent_app.df_all
                    elif hasattr(self.parent_app, "current_df") and self.parent_app.current_df is not None and not self.parent_app.current_df.empty:
                        df = self.parent_app.current_df
                    
                    if df is not None and not df.empty:
                        # ── 局部精准哈希查找，绝不遍历 df.index 以彻底消灭高频多线程 GIL 异常 ──
                        for code in temp_positions.keys():
                            idx_val = None
                            for potential_key in [code, int(code) if code.isdigit() else None, 
                                                 f"{code}.SH", f"{code}.SZ", f"{code}.SS",
                                                 f"sh{code}", f"sz{code}", f"SH{code}", f"SZ{code}"]:
                                if potential_key is None:
                                    continue
                                try:
                                    if potential_key in df.index:
                                        idx_val = potential_key
                                        break
                                except Exception:
                                    pass
                            if idx_val is not None:
                                target_row = df.loc[idx_val]
                                now_price = None
                                
                                # 支持 Series 或 DataFrame 处理（重复行防御）
                                if hasattr(target_row, "ndim") and target_row.ndim > 1:
                                    row_item = target_row.iloc[0]
                                else:
                                    row_item = target_row
                                    
                                for col in ["now", "close", "price", "trade"]:
                                    if col in df.columns:
                                        val = row_item.get(col)
                                        try:
                                            if val is not None:
                                                if hasattr(val, "values"):
                                                    val = val.values[0]
                                                float_val = float(val)
                                                if float_val > 0:
                                                    now_price = float_val
                                                    break
                                        except (ValueError, TypeError, IndexError):
                                            pass
                                if now_price is not None:
                                    adapter.update_market_price(code, now_price)

            # ── 物理对账与双向对账同步 (Auto-Heal Bridge for Paper Adapter) ──
            if service.paper_adapter is not None:
                try:
                    from trade_gateway import get_trade_gateway, Position as LegacyPosition
                    from trading_kernel.execution.paper_adapter import Position as PaperPosition
                    
                    trade_gw = getattr(self.parent_app, "_trade_gw", None) or get_trade_gateway()
                    if trade_gw is not None:
                        # 1) Bridge-Anti-Reverse: 将新内核的持久化持仓反向还原给老柜台内存
                        for p_code_pure, pos_obj in list(service.paper_adapter.account.positions.items()):
                            vol = float(pos_obj.volume)
                            if vol > 0:
                                found_in_old = False
                                with trade_gw._lock:
                                    for old_key in list(trade_gw._positions.keys()):
                                        old_pure = "".join(filter(str.isdigit, str(old_key)))[:6]
                                        if old_pure == p_code_pure:
                                            found_in_old = True
                                            leg_pos = trade_gw._positions[old_key]
                                            leg_pos.shares = int(vol)
                                            break
                                    if not found_in_old:
                                        name_val = "内核持仓"
                                        sector_val = ""
                                        try:
                                            df_rt = None
                                            if hasattr(self.parent_app, "df_all") and self.parent_app.df_all is not None:
                                                df_rt = self.parent_app.df_all
                                            if df_rt is not None:
                                                # 局部精准哈希匹配，绝不遍历 df_rt.index 以消灭多线程 GIL 异常
                                                idx_val = None
                                                for potential_key in [p_code_pure, int(p_code_pure) if p_code_pure.isdigit() else None,
                                                                      f"{p_code_pure}.SH", f"{p_code_pure}.SZ", f"{p_code_pure}.SS",
                                                                      f"sh{p_code_pure}", f"sz{p_code_pure}", f"SH{p_code_pure}", f"SZ{p_code_pure}"]:
                                                    if potential_key is None:
                                                        continue
                                                    try:
                                                        if potential_key in df_rt.index:
                                                            idx_val = potential_key
                                                            break
                                                    except Exception:
                                                        pass
                                                if idx_val is not None:
                                                    row = df_rt.loc[idx_val]
                                                    if hasattr(row, "ndim") and row.ndim > 1:
                                                        row = row.iloc[0]
                                                    name_val = row.get("name", "内核持仓")
                                                    sector_val = row.get("sector", row.get("sector_name", ""))
                                        except Exception:
                                            pass
                                        entry_p = float(pos_obj.entry_price)
                                        curr_p = float(pos_obj.current_price)
                                        
                                        # 解析并还原正确的 entry_time
                                        entry_time_dt = datetime.now()
                                        p_entry_time = getattr(pos_obj, "entry_time", "N/A")
                                        if p_entry_time and p_entry_time != "N/A":
                                            try:
                                                this_year = datetime.now().year
                                                entry_time_dt = datetime.strptime(f"{this_year}-{p_entry_time}", "%Y-%m-%d %H:%M:%S")
                                            except Exception:
                                                pass
                                                
                                        leg_pos = LegacyPosition(
                                            code=p_code_pure,
                                            name=name_val,
                                            sector=sector_val,
                                            entry_price=entry_p,
                                            entry_time=entry_time_dt,
                                            shares=int(vol),
                                            position_value=entry_p * vol,
                                            strategy_tag="内核反哺",
                                            stop_loss=entry_p * 0.98,
                                            current_price=curr_p if curr_p > 0 else entry_p,
                                            pnl_pct=pos_obj.pnl_pct,
                                            pnl_value=pos_obj.pnl,
                                            day_high=curr_p if curr_p > 0 else entry_p,
                                        )
                                        trade_gw._positions[p_code_pure] = leg_pos
                                        logger.info(f"[Bridge-Anti-Reverse] Restored legacy position: {p_code_pure} ({name_val}) with entry_time {entry_time_dt}")
                        
                        # 2) 执行双向对账同步
                        old_positions = trade_gw.get_positions()
                        old_code_set = set()
                        for old_pos in old_positions:
                            o_code = old_pos.get("code")
                            if o_code:
                                o_code_pure = "".join(filter(str.isdigit, str(o_code)))[:6]
                                if len(o_code_pure) == 6:
                                    old_code_set.add(o_code_pure)
                                    vol = float(old_pos.get("shares", 0))
                                    entry_p = float(old_pos.get("entry_price", 0.0))
                                    curr_p = float(old_pos.get("current_price", entry_p))
                                    if o_code_pure not in service.paper_adapter.account.positions:
                                        # 老网关新买入的持仓，同步至新内核并扣除买入成本
                                        service.paper_adapter.account.positions[o_code_pure] = PaperPosition(
                                            code=o_code_pure,
                                            entry_price=entry_p,
                                            volume=vol,
                                            current_price=curr_p,
                                        )
                                        service.paper_adapter.account.cash -= entry_p * vol
                                    else:
                                        # 针对已有的持仓，如有股数发生增量变动，扣减或退回对应的买入成本
                                        pos_obj = service.paper_adapter.account.positions[o_code_pure]
                                        diff_vol = vol - pos_obj.volume
                                        if diff_vol != 0:
                                            service.paper_adapter.account.cash -= diff_vol * entry_p
                                        
                                        pos_obj.volume = vol
                                        pos_obj.entry_price = entry_p
                                        if curr_p > 0:
                                            pos_obj.current_price = curr_p
                                            
                        # 清洗已平仓
                        for active_c in list(service.paper_adapter.account.positions.keys()):
                            if active_c not in old_code_set:
                                # 如果新内核有、但老网关没有（被平仓/清洗了），按现价（若有）或买入成本退回变现资金
                                pos_obj = service.paper_adapter.account.positions[active_c]
                                return_p = pos_obj.current_price if pos_obj.current_price > 0 else pos_obj.entry_price
                                service.paper_adapter.account.cash += return_p * pos_obj.volume
                                service.paper_adapter.account.positions.pop(active_c, None)
                                
                        # 同步初始资金与初始总杠杆上限，但决不在平时高频刷新时通过 pos_value (最新市值) 覆盖 cash 可用现金！
                        total_cap = getattr(trade_gw.risk_manager, "total_capital", 1000000.0)
                        service.paper_adapter.initial_capital = total_cap
                        service.paper_adapter.account.initial_capital = total_cap
                        
                        # 对可用资金进行零值保护，防止意外浮点数溢出为负数
                        if service.paper_adapter.account.cash < 0:
                            service.paper_adapter.account.cash = 0.0
                        
                        # 保存状态
                        if hasattr(service.paper_adapter, "_save_state"):
                            service.paper_adapter._save_state()
                except Exception as e_bridge:
                    logger.warning(f"Error bridging/syncing positions in DecisionFlowPanel: {e_bridge}")

            # 2. 重新获取最新的持仓与资产快照
            if adapter is not None:
                positions = adapter.get_positions()
                account = adapter.get_account_snapshot()
            else:
                positions = {}
                account = {
                    "cash": 0.0,
                    "total_equity": 0.0,
                    "total_pnl": 0.0,
                    "total_pnl_pct": 0.0,
                }
            
            # 3. 收集所有的交易时间与订单记录 (O(N) 遍历优化与缓存机制)
            current_orders = getattr(adapter, "orders", [])
            orders_len = len(current_orders)

            # ── 渲染门槛 (Rendering Gate Check)：仅在数据内容或长度实际变化时才渲染，阻断无意义重绘 ──
            state_rep = {
                "positions": {
                    code: {
                        "volume": float(pos.get("volume", 0.0)),
                        "entry_price": float(pos.get("entry_price", 0.0)),
                        "current_price": float(pos.get("current_price", 0.0)),
                        "pnl": float(pos.get("pnl", 0.0)),
                        "pnl_pct": float(pos.get("pnl_pct", 0.0)),
                    } for code, pos in positions.items()
                },
                "account": {
                    "cash": float(account.get("cash", 0.0)),
                    "total_equity": float(account.get("total_equity", 0.0)),
                    "total_pnl": float(account.get("total_pnl", 0.0)),
                    "total_pnl_pct": float(account.get("total_pnl_pct", 0.0)),
                },
                "orders_len": orders_len,
                "hidden_closed_codes": sorted(list(x for x in self._hidden_closed_codes if isinstance(x, str))) if hasattr(self, "_hidden_closed_codes") else [],
                "show_closed": self.chk_show_closed.isChecked() if hasattr(self, "chk_show_closed") else False,
            }
            import json
            state_str = json.dumps(state_rep, sort_keys=True)
            if hasattr(self, "_last_rendered_state") and self._last_rendered_state == state_str:
                self.pos_table.blockSignals(False)
                return
            self._last_rendered_state = state_str
            
            total_market_val = 0.0
            
            # 3. 收集所有的交易时间与订单记录 (O(N) 遍历优化与缓存机制)
            current_orders = getattr(adapter, "orders", [])
            orders_len = len(current_orders)
            
            if orders_len != self._last_orders_len:
                # 只有订单数有变化时才重新全量解析以释放高频 CPU 负荷
                self._last_orders_len = orders_len
                code_trade_info = {}
                if current_orders:
                    for o in current_orders:
                        c = o.get("code")
                        if not c:
                            continue
                        act = o.get("action", "").upper()
                        ts = o.get("timestamp", "")
                        price = float(o.get("price", 0.0))
                        vol = float(o.get("volume", 0.0))
                        
                        if c not in code_trade_info:
                            code_trade_info[c] = {
                                "open_time": "N/A",
                                "close_time": "N/A",
                                "buys": [],
                                "sells": [],
                            }
                        
                        # 调用统一的高防弹时间戳解析器 (DRY)
                        formatted_ts = self._parse_timestamp(ts)
                        
                        if act in {"BUY", "ADD"}:
                            if code_trade_info[c]["open_time"] == "N/A":
                                code_trade_info[c]["open_time"] = formatted_ts
                            code_trade_info[c]["buys"].append((price, vol, formatted_ts))
                        elif act in {"SELL", "REDUCE"}:
                            code_trade_info[c]["close_time"] = formatted_ts
                            code_trade_info[c]["sells"].append((price, vol, formatted_ts))
                self._cached_code_trade_info = code_trade_info
            else:
                code_trade_info = self._cached_code_trade_info

            # 4. 整合活持仓与今天已平仓的个股
            display_positions = []
            
            # 活着持仓的个股
            for code, pos in positions.items():
                volume = float(pos.get("volume", 0.0))
                if volume <= 0:
                    # 双重保险：股数小于等于 0 的不属于活着持仓，直接跳过，防止渲染幽灵 0 股持仓行
                    continue
                entry_price = float(pos.get("entry_price", 0.0))
                curr_price = float(pos.get("current_price", 0.0))
                market_val = volume * curr_price
                total_market_val += market_val
                pnl = float(pos.get("pnl", 0.0))
                pnl_pct = float(pos.get("pnl_pct", 0.0))
                
                # 将活持仓的成本缓存进内存，以解决昨持平仓成本追溯问题
                if entry_price > 0:
                    self._position_cost_cache[code] = entry_price
                
                open_time = pos.get("entry_time", "N/A")
                if open_time == "N/A" and code in code_trade_info:
                    open_time = code_trade_info[code]["open_time"]
                close_time = "N/A"
                    
                display_positions.append({
                    "code": code,
                    "volume": volume,
                    "entry_price": entry_price,
                    "current_price": curr_price,
                    "market_val": market_val,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "open_time": open_time,
                    "close_time": close_time,
                })
                
            # 今日已平仓的个股
            if hasattr(self, "chk_show_closed") and self.chk_show_closed.isChecked():
                for code, info in code_trade_info.items():
                    if code not in positions:
                        if hasattr(self, "_hidden_closed_codes") and code in self._hidden_closed_codes:
                            continue
                        buys = info["buys"]
                        sells = info["sells"]
                        
                        total_buy_vol = sum(b[1] for b in buys)
                        if total_buy_vol > 0:
                            entry_price = sum(b[0] * b[1] for b in buys) / total_buy_vol
                        else:
                            # 昨持平仓：尝试从内存成本缓存中追溯昨持的成本均价
                            entry_price = self._position_cost_cache.get(code, 0.0)
                        
                        curr_price = sells[-1][0] if sells else entry_price
                        volume = 0.0
                        market_val = 0.0
                        
                        total_sell_vol = sum(s[1] for s in sells)
                        total_sell_val = sum(s[0] * s[1] for s in sells)
                        total_buy_val = entry_price * total_sell_vol
                        pnl = total_sell_val - total_buy_val
                        pnl_pct = (pnl / total_buy_val * 100.0) if total_buy_val > 0 else 0.0
                        
                        display_positions.append({
                            "code": code,
                            "volume": volume,
                            "entry_price": entry_price,
                            "current_price": curr_price,
                            "market_val": market_val,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "open_time": info["open_time"],
                            "close_time": info["close_time"],
                        })

            # 5. 渲染至 Qt 表格，采用行复用与脏检查防闪烁机制
            target_row_count = len(display_positions)
            self.pos_table.setRowCount(target_row_count)
            self.pos_table.setSortingEnabled(False)
            
            for row_idx, pos_data in enumerate(display_positions):
                code = pos_data["code"]
                volume = pos_data["volume"]
                entry_price = pos_data["entry_price"]
                curr_price = pos_data["current_price"]
                market_val = pos_data["market_val"]
                pnl = pos_data["pnl"]
                pnl_pct = pos_data["pnl_pct"]
                open_time = pos_data["open_time"]
                close_time = pos_data["close_time"]
                
                # 精密名称补齐：优先从父窗口的全局df_all查找以确保包含全量股票，降级为当前显示数据集current_df
                stock_name = ""
                if self.parent_app:
                    if hasattr(self.parent_app, "df_all") and self.parent_app.df_all is not None:
                        df_all = self.parent_app.df_all
                        if code in df_all.index:
                            stock_name = str(df_all.loc[code].get("name", ""))
                    if not stock_name and hasattr(self.parent_app, "current_df") and self.parent_app.current_df is not None:
                        df = self.parent_app.current_df
                        if code in df.index:
                            stock_name = str(df.loc[code].get("name", ""))
                if not stock_name:
                    stock_name = "已平仓" if volume == 0 else "持仓中"
                    
                # 盈亏柔和色彩管理 (亮盈绿 vs 猩红)
                pnl_color = "#00E676" if pnl >= 0 else "#FF1744"
                pnl_sign = "+" if pnl >= 0 else ""
                
                items = [
                    (code, "#FFFFFF", code),
                    (stock_name, "#C2C2C6", stock_name),
                    (f"{volume:.0f}", "#B0BEC5", volume),
                    (f"{entry_price:.2f}", "#B0BEC5", entry_price),
                    (f"{curr_price:.2f}", "#FFFFFF", curr_price),
                    (f"¥ {market_val:,.2f}", "#00E5FF", market_val),
                    (f"{pnl_sign}¥ {pnl:,.2f}", pnl_color, pnl),
                    (f"{pnl_sign}{pnl_pct:.2f}%", pnl_color, pnl_pct),
                    (open_time, "#B0BEC5", open_time),
                    (close_time, "#B0BEC5", close_time)
                ]
                
                for col_idx, (text, color_hex, sort_val) in enumerate(items):
                    cell_item = self.pos_table.item(row_idx, col_idx)
                    if not cell_item:
                        cell_item = SortableTableWidgetItem(str(text), sort_val)
                        cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                        if col_idx in {6, 7}:
                            cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                        self.pos_table.setItem(row_idx, col_idx, cell_item)
                    
                    if cell_item.text() != str(text):
                        cell_item.setText(str(text))
                    
                    # 更新 sort_value
                    if isinstance(cell_item, SortableTableWidgetItem):
                        cell_item.value = sort_val
                    
                    if color_hex:
                        new_color = QtGui.QColor(color_hex)
                        if cell_item.foreground().color() != new_color:
                            cell_item.setForeground(new_color)

            # 6. 恢复之前的选中状态，确保位置对齐且不会因为刷新丢失焦点或乱跳
            restored = False
            if selected_code:
                for r in range(self.pos_table.rowCount()):
                    item = self.pos_table.item(r, 0)
                    if item and item.text().strip() == selected_code:
                        self.pos_table.setCurrentCell(r, 0)
                        restored = True
                        break
            if not restored and selected_code and self.pos_table.rowCount() > 0:
                self.pos_table.setCurrentCell(0, 0)
            
            self.pos_table.setSortingEnabled(True)

            # 7. 刷新大卡片统计数据
            cash = float(account.get("cash", 0.0))
            equity = float(account.get("total_equity", 0.0))
            total_pnl = float(account.get("total_pnl", 0.0))
            total_pnl_pct = float(account.get("total_pnl_pct", 0.0))
            ratio = (total_market_val / equity * 100.0) if equity > 0 else 0.0
            
            self.cards["cash"].setText(f"¥ {cash:,.2f}")
            self.cards["equity"].setText(f"¥ {equity:,.2f}")
            self.cards["market_value"].setText(f"¥ {total_market_val:,.2f}")
            
            # 盈亏卡片动态变色与柔和发光渲染
            pnl_sign = "+" if total_pnl >= 0 else ""
            self.cards["total_pnl"].setText(f"{pnl_sign}¥ {total_pnl:,.2f} ({total_pnl_pct:.2f}%)")
            if total_pnl >= 0:
                self.cards["total_pnl"].setStyleSheet("font-size: 13px; font-weight: bold; color: #00E676;")
            else:
                self.cards["total_pnl"].setStyleSheet("font-size: 13px; font-weight: bold; color: #FF1744;")
                
            self.cards["ratio"].setText(f"{ratio:.1f}%")
        except Exception as ex:
            logger.error(f"Failed to fetch/render real-time kernel positions: {ex}\n{traceback.format_exc()}")
        finally:
            self.pos_table.blockSignals(False)

    def resizeEvent(self, event):
        """拖动放大窗口时不要自动_adjust_column_widths，由主窗体布局进行自适应弹性拉伸"""
        super().resizeEvent(event)

    def _adjust_column_widths(self):
        """极致模式自适应：按照可视化左侧列的紧凑显示方式，强行重设并压实列宽参数"""
        if hasattr(self, "table") and self.table.columnCount() == 12:
            total_w = self.table.viewport().width()
            if total_w > 100:
                # 0.日期时间, 1.代码, 2.名称, 3.前态, 4.动作, 5.拟仓, 6.打分, 7.风控, 8.阻断, 9.止损, 10.Trace ID, 11.决策理由摘要
                static_widths = [110, 65, 75, 45, 52, 48, 45, 55, 70, 52, 55]
                scaled_total = int(sum(static_widths) * self.scale_factor)
                
                # 强行设置互动模式，确保完全压实宽度并不受历史配置死锁阻碍
                headers = self.table.horizontalHeader()
                for idx, w in enumerate(static_widths):
                    headers.setSectionResizeMode(idx, QtWidgets.QHeaderView.ResizeMode.Interactive)
                    self.table.setColumnWidth(idx, int(w * self.scale_factor))
                
                # 最后一列“决策理由摘要”自适应 Stretch
                reason_width = max(250, total_w - scaled_total)
                self.table.setColumnWidth(11, reason_width)
                
        if hasattr(self, "pos_table") and self.pos_table.columnCount() == 10:
            total_pos_w = self.pos_table.viewport().width()
            if total_pos_w > 100:
                # 0.代码, 1.名称, 2.持仓股数, 3.买入均价, 4.当前市价, 5.持仓市值, 6.浮动盈亏, 7.盈亏比例, 8.开仓时间, 9.平仓时间
                static_pos_widths = [65, 75, 60, 60, 60, 85, 90, 80, 110]
                scaled_pos_total = int(sum(static_pos_widths) * self.scale_factor)
                
                pos_headers = self.pos_table.horizontalHeader()
                for idx, w in enumerate(static_pos_widths):
                    pos_headers.setSectionResizeMode(idx, QtWidgets.QHeaderView.ResizeMode.Interactive)
                    self.pos_table.setColumnWidth(idx, int(w * self.scale_factor))
                
                # 最后一列“平仓时间”自适应 Stretch
                pct_width = max(110, total_pos_w - scaled_pos_total)
                self.pos_table.setColumnWidth(9, pct_width)

    def _show_pos_context_menu(self, pos):
        """内核实时持仓表格右键快捷菜单：支持手动平仓、一键全平、代码复制"""
        index = self.pos_table.indexAt(pos)
        if not index.isValid():
            return
            
        row = index.row()
        menu = QtWidgets.QMenu(self)
        
        # 扁平精致暗黑菜单风格
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E24;
                color: #E2E2E6;
                border: 1px solid #2E2E35;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #00E676;
                color: #121214;
            }
        """)
        
        code_item = self.pos_table.item(row, 0)
        name_item = self.pos_table.item(row, 1)
        vol_item = self.pos_table.item(row, 2)
        code = code_item.text().strip() if code_item else ""
        name = name_item.text().strip() if name_item else ""
        
        try:
            volume = float(vol_item.text().strip()) if vol_item else 0.0
        except ValueError:
            volume = 0.0
        
        if code:
            if volume > 0:
                # 动作一：手动平仓
                action_sell = menu.addAction(f"🚨 手动平仓此股 ({code})")
                action_sell.triggered.connect(lambda: self._manual_sell_position(code, name))
            else:
                # 针对已平仓(0股)记录，提供“移除记录”功能
                action_remove = menu.addAction(f"🗑️ 移除此已平仓记录 ({code})")
                action_remove.triggered.connect(lambda: self._remove_closed_record(code))
            
            menu.addSeparator()
            
            # 动作二：复制股票代码
            action_copy_code = menu.addAction("📋 复制股票代码")
            action_copy_code.triggered.connect(lambda: self._copy_to_clipboard(code, "股票代码"))
            
            # 动作三：复制股票名称
            if name:
                action_copy_name = menu.addAction("📋 复制股票名称")
                action_copy_name.triggered.connect(lambda: self._copy_to_clipboard(name, "股票名称"))
                
            menu.addSeparator()
            
        # 动作四：一键全平
        action_sell_all = menu.addAction("⚠️ 一键全平所有持仓")
        action_sell_all.triggered.connect(self._manual_sell_all_positions)
        
        # 动作五：清除所有已平仓记录
        has_closed = False
        for r in range(self.pos_table.rowCount()):
            v_item = self.pos_table.item(r, 2)
            try:
                if v_item and float(v_item.text().strip()) == 0.0:
                    has_closed = True
                    break
            except Exception:
                pass
        if has_closed:
            action_clear_closed = menu.addAction("🗑️ 清除所有已平仓记录")
            action_clear_closed.triggered.connect(self._clear_all_closed_records)
        
        menu.exec(self.pos_table.viewport().mapToGlobal(pos))

    def _remove_closed_record(self, code: str):
        """将已平仓的个股代码加入隐藏集合，从而在列表中删除该已平仓行的显示"""
        if not hasattr(self, "_hidden_closed_codes"):
            self._hidden_closed_codes = set()
        if isinstance(code, str) and code:
            self._hidden_closed_codes.add(code)
        self._refresh_positions_tab()

    def _clear_all_closed_records(self):
        """将当前表格中所有股数为0的已平仓个股全部加入隐藏集合"""
        if not hasattr(self, "_hidden_closed_codes"):
            self._hidden_closed_codes = set()
        for r in range(self.pos_table.rowCount()):
            c_item = self.pos_table.item(r, 0)
            v_item = self.pos_table.item(r, 2)
            if c_item and v_item:
                try:
                    if float(v_item.text().strip()) == 0.0:
                        code = c_item.text().strip()
                        if isinstance(code, str) and code:
                            self._hidden_closed_codes.add(code)
                except Exception:
                    pass
        self._refresh_positions_tab()

    def _manual_sell_position(self, code: str, name: str, show_message: bool = True):
        """手动平仓单只个股（异步桥接老网关和平仓新交易内核，安全防GIL崩溃）"""
        try:
            from trade_gateway import get_trade_gateway
            trade_gw = getattr(self.parent_app, "_trade_gw", None) or get_trade_gateway()
            if not trade_gw:
                QtWidgets.QMessageBox.warning(self, "警告", "交易网关未就绪，无法手动平仓")
                return
                
            if show_message:
                if not QtWidgets.QMessageBox.question(self, "确认", f"是否手工平仓所持股票 {name} ({code})？", 
                                                     QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No) == QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            def _async_sell_worker():
                try:
                    # 1. 物理计算平仓价格 (最新价优先)
                    price = 0.0
                    if self.parent_app and hasattr(self.parent_app, "selector") and self.parent_app.selector is not None:
                        df_rt = getattr(self.parent_app.selector, 'df_all_realtime', None)
                        if df_rt is not None and code in df_rt.index:
                            price = float(df_rt.loc[code].get('trade', 0) or 0)
                    
                    if price <= 0:
                        # Fallback 从 pos_table 或 adapter 获取
                        try:
                            from trading_kernel.kernel_service import get_kernel_service
                            service = get_kernel_service()
                            if service and service.paper_adapter:
                                pos = service.paper_adapter.account.positions.get(code)
                                if pos:
                                    price = float(pos.current_price or pos.entry_price)
                        except Exception:
                            pass
                    if price <= 0:
                        price = 1.0  # 安全低保底

                    # 2. 物理调用老版模拟网关执行平仓卖出，实现原有的平仓逻辑不变！
                    trade_gw.submit_sell(code, price, reason="内核面板上手工平仓")

                    # 3. 构造虚拟 SELL 信号，物理写入交易流水，并同步让新交易内核 paper_adapter 执行平仓！
                    sig_sell = {
                        "code": code,
                        "name": name,
                        "signal_type": "手工平仓",
                        "action": "SELL",
                        "price": price,
                        "current_price": price,
                        "suggest_price": price,
                        "reason": "内核面板上手工平仓",
                        "journal_ts": datetime.now().isoformat(),
                        "created_at": datetime.now().isoformat(),
                    }
                    try:
                        from trading_kernel.kernel_service import enrich_decision_item
                        enrich_decision_item(sig_sell, write_journal=True)
                    except Exception as e_journal:
                        logger.warning(f"Error enriching sell journal: {e_journal}")

                    # 4. 强制物理保存 paper_adapter 最新空状态
                    try:
                        from trading_kernel.kernel_service import get_kernel_service
                        service = get_kernel_service()
                        if service and service.paper_adapter:
                            if hasattr(service.paper_adapter, "_save_state"):
                                service.paper_adapter._save_state()
                    except Exception:
                        pass

                    # 5. 回到 UI 线程刷新
                    def _on_sell_finished_ui():
                        self._refresh_positions_tab()
                        if show_message:
                            toast_message(self.parent_app, f"手工平仓成功: {name} ({code})")

                    QtCore.QTimer.singleShot(0, _on_sell_finished_ui)
                except Exception as ex:
                    logger.error(f"Error in async_sell_worker: {ex}")

            # 启动工作线程
            t = threading.Thread(target=_async_sell_worker, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"Error in manual_sell_position: {e}")

    def _manual_sell_all_positions(self):
        """右键一键全平所有内核实时持仓（含桥接旧持仓）"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service or not service.paper_adapter:
                QtWidgets.QMessageBox.warning(self, "警告", "模拟交易内核未就绪，无法一键平仓")
                return
                
            positions = service.paper_adapter.get_positions()
            if not positions:
                QtWidgets.QMessageBox.information(self, "提示", "当前无持仓")
                return
                
            if not QtWidgets.QMessageBox.question(self, "确认", f"是否手工一键全平当前全部 {len(positions)} 只持仓？", 
                                                 QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No) == QtWidgets.QMessageBox.StandardButton.Yes:
                return
                
            # 批量执行平仓
            for code, pos_dict in list(positions.items()):
                name = ""
                # 尝试查找股票名称
                if self.parent_app and hasattr(self.parent_app, "df_all") and self.parent_app.df_all is not None:
                    if code in self.parent_app.df_all.index:
                        name = str(self.parent_app.df_all.loc[code].get("name", ""))
                self._manual_sell_position(code, name, show_message=False)
                
            QtWidgets.QMessageBox.information(self, "完成", "已执行一键平仓所有持仓！")
        except Exception as e:
            logger.error(f"Error in manual_sell_all_positions: {e}")

    def _on_one_key_self_heal(self):
        """一键自适应数据自愈修复：智能调整资金规模、修复个股缺失价格、清理 0 股幽灵持仓、并物理同步适配器与柜台数据（后台线程安全）"""
        try:
            # 1. 主线程即时反馈与确认防误触
            reply = QtWidgets.QMessageBox.question(
                self, 
                "一键数据自愈确认", 
                "即将执行全量账户与资产自愈对账：\n\n"
                "1. 清理幽灵持仓（0股）\n"
                "2. 修复个股价格缺失/异常\n"
                "3. 自愈开仓时间（从流水中追溯）\n"
                "4. 智能对齐初始资金与可用现金\n"
                "5. 同步所有内存与磁盘状态\n\n"
                "此过程将在后台安全执行，请确认是否继续？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            def _async_heal_worker():
                try:
                    from trading_kernel.kernel_service import get_kernel_service
                    from trade_gateway import get_trade_gateway
                    import numpy as np
                    import math
                    import time
                    import uuid
                    
                    def safe_float(v, fallback=0.0):
                        if v is None:
                            return fallback
                        try:
                            if isinstance(v, (np.floating, np.integer)):
                                return float(v)
                        except Exception:
                            pass
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            return fallback
                    
                    service = get_kernel_service()
                    if not service or not service.paper_adapter:
                        def _notify_no_service():
                            QtWidgets.QMessageBox.warning(self, "数据自愈", "模拟交易内核服务未就绪")
                        QtCore.QTimer.singleShot(0, _notify_no_service)
                        return
                        
                    trade_gw = getattr(self.parent_app, "_trade_gw", None) or get_trade_gateway()
                    if not trade_gw:
                        def _notify_no_gateway():
                            QtWidgets.QMessageBox.warning(self, "数据自愈", "模拟交易网关未就绪")
                        QtCore.QTimer.singleShot(0, _notify_no_gateway)
                        return
                        
                    # 1. 物理清理所有 volume/shares <= 0 的幽灵/已平仓持仓，防范 float 盈亏计算干扰
                    removed_ghosts = []
                    
                    # 清理 paper_adapter 内存持仓
                    for c_code, p_obj in list(service.paper_adapter.account.positions.items()):
                        if p_obj.volume <= 0:
                            service.paper_adapter.account.positions.pop(c_code, None)
                            removed_ghosts.append(c_code)
                            
                    # 清理 legacy 柜台持仓，使用 3.0 秒超时避免死锁
                    if trade_gw._lock.acquire(timeout=3.0):
                        try:
                            for c_code in list(trade_gw._positions.keys()):
                                leg_pos = trade_gw._positions[c_code]
                                if leg_pos.shares <= 0:
                                    trade_gw._positions.pop(c_code, None)
                                    removed_ghosts.append(c_code)
                        finally:
                            trade_gw._lock.release()
                    else:
                        logger.warning("[Self-Healing] Failed to acquire trade_gw._lock for cleaning ghosts within 3 seconds, skipping.")

                    # 1.1 价格自愈：物理修复价格数据 (entry_price / current_price) 缺失、0 或为 NaN 的情况
                    def is_invalid_price(p):
                        if p is None:
                            return True
                        try:
                            fp = float(p)
                            return fp <= 0 or math.isnan(fp) or math.isinf(fp)
                        except Exception:
                            return True
                    
                    df_all = getattr(self.parent_app, "df_all", None)
                    rt_price_map = {}
                    if df_all is not None:
                        try:
                            for idx, row in df_all.iterrows():
                                raw_c = str(idx)
                                pure_c = "".join(filter(str.isdigit, raw_c))[:6]
                                if pure_c:
                                    price_val = safe_float(row.get("close") or row.get("price") or row.get("last_close") or row.get("open"), 0.0)
                                    if price_val > 0:
                                        rt_price_map[pure_c] = price_val
                        except Exception as ex:
                            logger.error(f"Error mapping rt_price_map: {ex}")
                    
                    # 从 orders 流水中回溯计算所有个股的买入均价
                    order_entry_prices = {}
                    if service.paper_adapter.orders:
                        try:
                            sorted_orders = sorted(
                                [o for o in service.paper_adapter.orders if isinstance(o, dict)],
                                key=lambda x: str(x.get("timestamp") or "")
                            )
                            temp_volumes = {}
                            temp_costs = {}
                            for o in sorted_orders:
                                c = o.get("code")
                                if not c:
                                    continue
                                pure_c = "".join(filter(str.isdigit, str(c)))[:6]
                                act = str(o.get("action") or "").upper()
                                p = safe_float(o.get("price"), 0.0)
                                vol = safe_float(o.get("volume"), 0.0)
                                if p <= 0 or vol <= 0:
                                    continue
                                if act in {"BUY", "ADD"}:
                                    temp_volumes[pure_c] = temp_volumes.get(pure_c, 0.0) + vol
                                    temp_costs[pure_c] = temp_costs.get(pure_c, 0.0) + (p * vol)
                                elif act in {"SELL", "REDUCE"}:
                                    rem_vol = max(0.0, temp_volumes.get(pure_c, 0.0) - vol)
                                    if rem_vol <= 0:
                                        temp_volumes.pop(pure_c, None)
                                        temp_costs.pop(pure_c, None)
                                    else:
                                        ratio = rem_vol / temp_volumes[pure_c]
                                        temp_costs[pure_c] = temp_costs.get(pure_c, 0.0) * ratio
                                        temp_volumes[pure_c] = rem_vol
                            
                            for pure_c, tot_vol in temp_volumes.items():
                                if tot_vol > 0:
                                    avg_p = temp_costs.get(pure_c, 0.0) / tot_vol
                                    if avg_p > 0:
                                        order_entry_prices[pure_c] = avg_p
                        except Exception as ex:
                            logger.error(f"Error computing order_entry_prices: {ex}")

                    # 遍历并自愈修复持仓的价格
                    healed_prices_count = 0
                    for c_code, pos_obj in list(service.paper_adapter.account.positions.items()):
                        pure_c = "".join(filter(str.isdigit, str(c_code)))[:6]
                        
                        # 修复 current_price
                        rt_p = rt_price_map.get(pure_c, 0.0)
                        if is_invalid_price(pos_obj.current_price):
                            if rt_p > 0:
                                pos_obj.current_price = rt_p
                                healed_prices_count += 1
                                logger.info(f"[Self-Healing] Repaired current_price for {c_code} with real-time price: {rt_p}")
                            elif not is_invalid_price(pos_obj.entry_price):
                                pos_obj.current_price = pos_obj.entry_price
                                healed_prices_count += 1
                                logger.info(f"[Self-Healing] Repaired current_price for {c_code} fallback to entry_price: {pos_obj.entry_price}")
                        
                        # 修复 entry_price
                        if is_invalid_price(pos_obj.entry_price):
                            if pure_c in order_entry_prices:
                                pos_obj.entry_price = order_entry_prices[pure_c]
                                healed_prices_count += 1
                                logger.info(f"[Self-Healing] Repaired entry_price for {c_code} from order ledger: {pos_obj.entry_price}")
                            elif rt_p > 0:
                                pos_obj.entry_price = rt_p
                                healed_prices_count += 1
                                logger.info(f"[Self-Healing] Repaired entry_price for {c_code} with real-time price fallback: {rt_p}")
                            elif not is_invalid_price(pos_obj.current_price):
                                pos_obj.entry_price = pos_obj.current_price
                                healed_prices_count += 1
                                logger.info(f"[Self-Healing] Repaired entry_price for {c_code} with current_price fallback: {pos_obj.current_price}")

                    # 1.2 从决策流水日志中自愈修复缺失的开仓时间
                    journal_path = self.journal_path
                    code_times = {}
                    if os.path.exists(journal_path):
                        try:
                            with open(journal_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        rec = json.loads(line)
                                    except Exception:
                                        continue
                                    
                                    is_audit = (rec.get("journal_type") == "HUMAN_CONFIRMATION_AUDIT")
                                    if is_audit:
                                        orig_order = rec.get("original_order", {})
                                        code = orig_order.get("code", "")
                                        confirmed = rec.get("confirmed", False)
                                        action = orig_order.get("action", "").upper()
                                        if not confirmed:
                                            continue
                                        ts = rec.get("timestamp", "")
                                    else:
                                        sig = rec.get("signal", {})
                                        code = sig.get("code", "")
                                        action = rec.get("kernel_action", "") or rec.get("action", "")
                                        if not action:
                                            risk = rec.get("risk", {})
                                            action = risk.get("final_action", "")
                                        action = action.upper()
                                        ts = rec.get("journal_ts", "") or rec.get("trace", {}).get("timestamp", "")
                                    
                                    if not code or not action or not ts:
                                        continue
                                    
                                    code = "".join(filter(str.isdigit, str(code)))[:6]
                                    if len(code) != 6:
                                        continue
                                        
                                    formatted_ts = self._parse_timestamp(ts)
                                    
                                    if code not in code_times:
                                        code_times[code] = {"open_time": "N/A", "close_time": "N/A"}
                                    
                                    if action in {"BUY", "ADD"}:
                                        if code_times[code]["open_time"] == "N/A":
                                            code_times[code]["open_time"] = formatted_ts
                                    elif action in {"SELL", "REDUCE"}:
                                        code_times[code]["close_time"] = formatted_ts
                        except Exception as ex:
                            logger.error(f"Error scanning journal file for self-heal: {ex}")
                    
                    # 对 positions 里的 entry_time 进行自愈修复
                    healed_times_count = 0
                    for c_code, pos_obj in service.paper_adapter.account.positions.items():
                        current_entry_time = getattr(pos_obj, "entry_time", "N/A")
                        if current_entry_time == "N/A" or current_entry_time == "":
                            if c_code in code_times and code_times[c_code]["open_time"] != "N/A":
                                pos_obj.entry_time = code_times[c_code]["open_time"]
                                healed_times_count += 1
                                logger.info(f"[Self-Healing] Restored open time for {c_code} from journal: {pos_obj.entry_time}")
                    
                    # 同时自愈老版柜台的持仓与价格，使用 3.0 秒超时避免死锁
                    if trade_gw._lock.acquire(timeout=3.0):
                        try:
                            for c_code in list(trade_gw._positions.keys()):
                                leg_pos = trade_gw._positions[c_code]
                                leg_pure = "".join(filter(str.isdigit, str(c_code)))[:6]
                                if leg_pure in code_times and code_times[leg_pure]["open_time"] != "N/A":
                                    try:
                                        ts_str = code_times[leg_pure]["open_time"]
                                        this_year = datetime.now().year
                                        dt = datetime.strptime(f"{this_year}-{ts_str}", "%Y-%m-%d %H:%M:%S")
                                        leg_pos.entry_time = dt
                                    except Exception:
                                        pass
                                
                                # 价格同步
                                paper_pos = service.paper_adapter.account.positions.get(leg_pure)
                                if paper_pos:
                                    leg_pos.price = paper_pos.entry_price
                                    leg_pos.current_price = paper_pos.current_price
                        finally:
                            trade_gw._lock.release()
                    else:
                        logger.warning("[Self-Healing] Failed to acquire trade_gw._lock for syncing positions within 3 seconds, skipping.")
                    
                    # 2. 统计当前活跃持仓的买入成本 and 最新市值
                    active_positions = service.paper_adapter.account.positions
                    entry_cost_sum = 0.0
                    market_val_sum = 0.0
                    
                    for code_key, pos_obj in active_positions.items():
                        vol = float(pos_obj.volume)
                        entry_cost_sum += float(pos_obj.entry_price) * vol
                        market_val_sum += float(pos_obj.current_price) * vol
                        
                    # 3. 智能计算合理、健康的资金规模 (尊重现有总资产，保持一致性)
                    current_initial = float(getattr(service.paper_adapter, "initial_capital", 0.0) or 0.0)
                    if current_initial >= entry_cost_sum and current_initial > 0:
                        target_cap = current_initial
                        logger.info(f"[Self-Healing] Respecting current initial capital: {target_cap}")
                    else:
                        # 只有原资金无效或不足以覆盖持仓时，才自愈重调资金规模 (默认至少 1,000,000.0)
                        min_cap = max(1000000.0, entry_cost_sum * 1.5)
                        target_cap = float((int(min_cap) // 100000) * 100000)
                        if target_cap < min_cap:
                            target_cap += 100000.0
                        logger.info(f"[Self-Healing] Auto-expanded initial capital to: {target_cap} (cost: {entry_cost_sum})")
                        
                    new_cash = max(0.0, target_cap - entry_cost_sum)
                    
                    # 4. 同步可用现金与初始资金到纸盘适配器和老柜台风控
                    service.paper_adapter.initial_capital = target_cap
                    service.paper_adapter.account.initial_capital = target_cap
                    service.paper_adapter.account.cash = new_cash
                    
                    trade_gw.total_capital = target_cap
                    if hasattr(trade_gw, "risk_manager") and trade_gw.risk_manager:
                        trade_gw.risk_manager.total_capital = target_cap
                        
                    # 5. 强行将新数据做物理落盘持久化
                    if hasattr(service.paper_adapter, "_save_state"):
                        service.paper_adapter._save_state()
                        
                    # 5.5 强制校正 state_manager 状态锁与实际持仓一致
                    try:
                        current_states = service.state_manager.snapshot()
                        for code_str, state_val in current_states.items():
                            if code_str not in active_positions and state_val == "IN_TRADE":
                                service.state_manager.set(code_str, "FLAT")
                                logger.info(f"[Self-Healing] Reset state_manager for {code_str} to FLAT (no holdings)")
                        for code_str in active_positions:
                            if current_states.get(code_str) != "IN_TRADE":
                                service.state_manager.set(code_str, "IN_TRADE")
                                logger.info(f"[Self-Healing] Set state_manager for {code_str} to IN_TRADE")
                    except Exception as e_sm_heal:
                        logger.error(f"[Self-Healing] Failed to sync state_manager: {e_sm_heal}")
                        
                    # 5.6 构造并物理追加自愈流水记录
                    try:
                        pnl_val = market_val_sum - entry_cost_sum
                        pnl_pct = (pnl_val / entry_cost_sum * 100.0) if entry_cost_sum > 0 else 0.0
                        rec_heal = {
                            "trace": {
                                "trace_id": f"heal-{uuid.uuid4().hex[:8]}",
                                "timestamp": datetime.now().isoformat()
                            },
                            "signal": {
                                "code": "HEAL",
                                "name": "数据自愈",
                                "action": "MAINT",
                                "signal_type": "系统自愈对账",
                                "reason": f"清理幽灵数: {len(set(removed_ghosts))} | 价格自愈数: {healed_prices_count} | 时间对齐数: {healed_times_count}",
                                "priority": 100
                            },
                            "risk": {
                                "allowed": True,
                                "final_action": "MAINT",
                                "reject_reason": "",
                                "reject_context": {}
                            },
                            "kernel_action": "MAINT",
                            "kernel_reject_code": "",
                            "journal_type": "SELF_HEAL_AUDIT",
                            "journal_ts": datetime.now().isoformat(),
                            "heal_stats": {
                                "ghosts_cleaned": len(set(removed_ghosts)),
                                "prices_healed": healed_prices_count,
                                "times_healed": healed_times_count,
                                "initial_capital": target_cap,
                                "cash": new_cash,
                                "entry_cost_sum": entry_cost_sum,
                                "market_val_sum": market_val_sum,
                                "pnl_val": pnl_val,
                                "pnl_pct": pnl_pct
                            }
                        }
                        
                        journal_path = getattr(self, "journal_path", None)
                        if journal_path:
                            # Write physical record to journal
                            with open(journal_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(rec_heal, ensure_ascii=False) + "\n")
                            logger.info("[Self-Healing] Successfully appended self-heal trace record to journal.")
                    except Exception as e_rec:
                        logger.error(f"[Self-Healing] Failed to append heal record to journal: {e_rec}")

                    # 6. 回到 UI 线程更新与提示
                    def _on_heal_finished_ui():
                        try:
                            # 清除 UI 缓存指纹，强制触发 Qt 刷新
                            if hasattr(self, "_last_rendered_state"):
                                delattr(self, "_last_rendered_state")
                                
                            self._refresh_positions_tab()
                            
                            # 7. 显示成功对话框
                            box = QtWidgets.QMessageBox(self)
                            box.setIcon(QtWidgets.QMessageBox.Icon.Information)
                            box.setWindowTitle("一键数据自愈修复")
                            
                            msg_text = (
                                f"🎉 <b>一键账户资产与资金自愈成功！</b><br><br>"
                                f"1️⃣ <b>清理幽灵持仓</b>：已物理剥离 {len(set(removed_ghosts))} 只已平仓 (0股) 行。<br>"
                                f"2️⃣ <b>自愈价格数据</b>：修复补齐了 <b>{healed_prices_count}</b> 处无效/缺失的价格指标。<br>"
                                f"3️⃣ <b>自愈开仓时间</b>：从决策流水日志中自愈修复了 <b>{healed_times_count}</b> 个持仓的开仓时间。<br>"
                                f"4️⃣ <b>对齐初始资金</b>：已完美尊重并对齐初始资产为 <b>¥ {target_cap:,.2f}</b> (与总资金量一致)。<br>"
                                f"5️⃣ <b>可用现金对账</b>：已精准修正为 <b>¥ {new_cash:,.2f}</b> (账户保持健康购买力)。<br>"
                                f"6️⃣ <b>资产盈亏重算</b>：<br>"
                                f"   - 持仓总成本：¥ {entry_cost_sum:,.2f}<br>"
                                f"   - 持仓最新市值：¥ {market_val_sum:,.2f}<br>"
                                f"   - 浮动总盈亏：<b><font color='{'#00E676' if pnl_val >= 0 else '#FF1744'}'>¥ {pnl_val:+,.2f} ({pnl_pct:+.2f}%)</font></b><br><br>"
                                f"<i>* 修正后数据已安全持久化写入本地配置文件，在重新启动后依然保持完美对账自愈！</i>"
                            )
                            box.setText(msg_text)
                            box.setTextFormat(QtCore.Qt.TextFormat.RichText)
                            box.exec()
                        except Exception as ui_ex:
                            logger.error(f"[Self-Healing] Error in _on_heal_finished_ui: {ui_ex}\n{__import__('traceback').format_exc()}")

                    QtCore.QTimer.singleShot(0, _on_heal_finished_ui)
                except Exception as ex:
                    logger.error(f"Error in _async_heal_worker: {ex}\n{__import__('traceback').format_exc()}")
                    def _on_heal_error_ui():
                        try:
                            QtWidgets.QMessageBox.critical(self, "出错", f"一键自愈执行时抛出异常: {ex}")
                        except Exception as ui_ex2:
                            logger.error(f"[Self-Healing] Error showing error dialog: {ui_ex2}")
                    QtCore.QTimer.singleShot(0, _on_heal_error_ui)

            # 启动守护线程执行
            t = threading.Thread(target=_async_heal_worker, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"Error in One-Key Self-Heal: {e}")
            QtWidgets.QMessageBox.critical(self, "出错", f"一键自愈触发失败: {e}")
