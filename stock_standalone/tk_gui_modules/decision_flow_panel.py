# -*- coding: utf-8 -*-
import json
import os
import time
import sys
import traceback
from datetime import datetime
from typing import Any, Optional

from PyQt6 import QtWidgets, QtCore, QtGui
from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory
from stock_logic_utils import toast_message

logger = LoggerFactory.getLogger("instock_TK.DecisionFlowPanel")

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
        self.journal_path = journal_path
        self._last_file_size = 0
        self._last_modified_time = 0.0
        
        # 脏检查状态指示缓存，避免高频对齐重复更新 GUI 样式
        self._last_is_killed = None
        self._last_top_mode = None
        self._last_top_killed = None
        
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
        
        # 2.5 恢复列宽与表头状态
        has_restored = self._restore_header_state()
        if not has_restored:
            # 仅在无历史保存的手动调整配置时，才去执行默认的极致初始列宽自适应
            self._adjust_column_widths()
        
        # 3. 首次全量扫描载入 (最多 200 条，防冷启动白屏)
        self._load_initial_records()
        
        # 同步初始化控制页与顶部状态徽章
        self._update_top_status_badges()
        self._sync_control_tab_ui()
        
        # 4. 启动定时器：每 500ms 增量扫描更新，实现真正的零 CPU 负荷监控
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._check_and_update_records)
        self.timer.start(500)

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
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(18)
        
        # 启用右键菜单支持
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # 表头拉伸策略
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # 绑定双击行进行代码联动
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        flow_layout.addWidget(self.table)
        
        self.tabs.addTab(flow_widget, "⚡ 决策流水监控 (Decision Flow)")

        # ==========================================
        # 2. 💼 内核实时持仓 页签
        # ==========================================
        pos_widget = QtWidgets.QWidget()
        pos_layout = QtWidgets.QVBoxLayout(pos_widget)
        pos_layout.setContentsMargins(6, 6, 6, 6)
        pos_layout.setSpacing(6)

        # 持仓数据表格 (只读)
        self.pos_table = QtWidgets.QTableWidget()
        self.pos_table.setColumnCount(8)
        pos_headers = ["代码", "名称", "持仓股数", "买入均价", "当前市价", "持仓市值", "浮动盈亏", "盈亏比例"]
        self.pos_table.setHorizontalHeaderLabels(pos_headers)
        
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.pos_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.verticalHeader().setDefaultSectionSize(18)
        
        # 绑定双击持仓代码跳转
        self.pos_table.cellDoubleClicked.connect(self._on_pos_cell_double_clicked)
        
        pos_header = self.pos_table.horizontalHeader()
        pos_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        pos_header.setStretchLastSection(True)
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
        
        # 按钮区
        save_btn = QtWidgets.QPushButton("💾 保存并即时应用风控参数")
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
        limits_lay.addWidget(save_btn, 3, 2, 1, 2)
        
        ctrl_layout.addWidget(limits_group)
        ctrl_layout.addStretch()
        
        self.tabs.addTab(ctrl_widget, "⚙️ 内核控制与风控 (Kernel Controls)")

        main_layout.addWidget(self.tabs)

        # 底部状态栏
        bottom_bar = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("初始化完成。正在监听交易内核流水与持仓...")
        bottom_bar.addWidget(self.status_label)
        main_layout.addLayout(bottom_bar)

        # 应用自适应列宽分配
        self._adjust_column_widths()

    def _on_cell_double_clicked(self, row, column):
        """双击表格行，提取股票代码并向主进程派发跳转联动"""
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            logger.info(f"Double clicked on DecisionFlow: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

    def _show_system_workflow_dialog(self):
        """弹出系统操作指南与风控参数详解窗口"""
        dlg = SystemWorkflowDialog(self)
        dlg.exec()

    def _show_checklist_dialog(self):
        """弹出操盘手 Checklist 流程化窗口"""
        dlg = OperatorChecklistDialog(self)
        dlg.exec()

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
        """从 UI 读值并重新生成 RiskLimits 实例应用于内核，并物理持久化写入本地配置文件"""
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
                max_consecutive_losses=self.spin_losses.value()
            )
            
            # A. 内存级单例热应用
            service.limits = limits
            
            # B. 物理持久化至本地 JSON 配置文件（双写以兼容高DPI/缩放配置环境）
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
                        "max_consecutive_losses": limits.max_consecutive_losses
                    }
                    
                    # 原子替换写入
                    tmp_file = filepath + ".tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    os.replace(tmp_file, filepath)
                    
                logger.info("Persistent RiskLimits saved to local config files successfully.")
            except Exception as ex:
                logger.error(f"Failed to save persistent RiskLimits to config file: {ex}")
            
            toast_message(self.parent_app, "✅ 风控参数已成功实时生效并保存！")
            logger.info(f"New RiskLimits applied: {limits}")
        except Exception as e:
            logger.error(f"Failed to apply new risk limits: {e}")
            toast_message(self.parent_app, "❌ 保存风控参数失败！")

    def _sync_control_tab_ui(self):
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
            self.table.setRowCount(0)
            for rec in records:
                self._append_record_to_table(rec)

            self.status_label.setText(f"✅ 成功载入历史 {len(records)} 条决策，实时监听中...")
            # 自动滚动到最新一行
            self.table.scrollToBottom()
            
            # 首次载入同步加载实时持仓明细页
            self._refresh_positions_tab()
        except Exception as e:
            logger.error(f"Failed to load initial records: {e}\n{traceback.format_exc()}")
            self.status_label.setText(f"❌ 载入历史流水失败: {e}")

    def _check_and_update_records(self):
        """定时扫描函数：比对文件大小与修改时间，以绝对零开销增量追溯最新决策"""
        # 每 500ms 自动核对并刷新控制面板与顶部状态徽章，保障多进程状态完美同步
        self._update_top_status_badges()
        self._sync_control_tab_ui()

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
                for rec in new_records:
                    self._append_record_to_table(rec)
                self.status_label.setText(f"⚡ 增量更新完成，新捕获 {len(new_records)} 条决策信号 (最新更新: {time.strftime('%H:%M:%S')})")
                self.table.scrollToBottom()
                # 重新应用过滤
                self._filter_table()
                
            # 同步刷新实时持仓与盈亏标签页
            self._refresh_positions_tab()
        except Exception as e:
            logger.error(f"Error in incremental records check: {e}")

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
            
            # 2. 字段映射提取 (防弹 Fallback)
            timestamp = self._parse_timestamp(rec.get("journal_ts", "") or trace.get("timestamp", ""))
    
            code = sig.get("code", "")
            name = sig.get("name", "")
            state = rec.get("kernel_state", "") or trace.get("state", "FLAT")
            action = rec.get("kernel_action", "") or risk.get("final_action", "")
            
            size_val = rec.get("kernel_size_pct", 0.0) or risk.get("final_size_pct", 0.0)
            size_pct = f"{float(size_val):.1f}%" if size_val is not None else "0.0%"
            
            confidence = str(rec.get("kernel_confidence", "") or intent.get("confidence", ""))
            
            allowed_val = risk.get("allowed", True)
            risk_allowed = "Allowed" if allowed_val else "Blocked"
            
            reject_code = rec.get("kernel_reject_code", "")
            if not reject_code and not allowed_val:
                reject_code = risk.get("reject_context", {}).get("code", "RISK_REJECT")
            
            stop_price_val = rec.get("kernel_stop_price", 0.0) or intent.get("stop_price", 0.0)
            stop_price = f"{float(stop_price_val):.2f}" if stop_price_val else "0.00"
            
            trace_id = trace.get("trace_id", "") or rec.get("kernel_trace_id", "")
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
            cell_item = QtWidgets.QTableWidgetItem(str(text))
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
            
        menu.exec(self.table.viewport().mapToGlobal(pos))
        
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
        self.table.setRowCount(0)
        self.status_label.setText("显示已清空。等待新增决策流水信号...")
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
                        
                if restored_any:
                    logger.info("DecisionFlowPanel header states restored successfully.")
                    return True
        except Exception as e:
            logger.error(f"Failed to restore DecisionFlowPanel header states: {e}")
        return False

    def showEvent(self, event):
        """展现时自适应"""
        super().showEvent(event)
        self.table.scrollToBottom()

    def _on_pos_cell_double_clicked(self, row, column):
        """双击持仓表格行，提取持仓个股代码并向主进程派发跳转联动"""
        code_item = self.pos_table.item(row, 0)
        name_item = self.pos_table.item(row, 1)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            logger.info(f"Double clicked on KernelPosition: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

    def _refresh_positions_tab(self):
        """核心无摩擦刷新：每 500ms 直接从 `get_kernel_service()` 单例物理提取内存中最新持仓与浮盈状态"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                logger.warning("Kernel service not available yet.")
                return
                
            mode = service.mode
            executor = service.executor
            
            # 物理对账数据源切换自愈：如果是 LIVE_AUTO 则拉取实盘真柜台数据，否则高保真拉取模拟盘
            adapter = executor if (executor is not None and mode == "LIVE_AUTO") else service.paper_adapter
            if not adapter:
                logger.warning("Active execution adapter not found.")
                return
            
            positions = adapter.get_positions()
            account = adapter.get_account_snapshot()
        except Exception as ex:
            logger.error(f"Failed to fetch real-time kernel positions for rendering: {ex}")
            return

        self.pos_table.setRowCount(0)
        total_market_val = 0.0
        
        # 依次填充持仓行
        for code, pos in positions.items():
            row_idx = self.pos_table.rowCount()
            self.pos_table.insertRow(row_idx)
            
            entry_price = float(pos.get("entry_price", 0.0))
            volume = float(pos.get("volume", 0.0))
            curr_price = float(pos.get("current_price", 0.0))
            market_val = volume * curr_price
            total_market_val += market_val
            
            pnl = float(pos.get("pnl", 0.0))
            pnl_pct = float(pos.get("pnl_pct", 0.0))
            
            # 精密名称补齐：尝试从父窗口的实时数据集中查找，降级为默认
            stock_name = ""
            if self.parent_app and hasattr(self.parent_app, "current_df") and self.parent_app.current_df is not None:
                df = self.parent_app.current_df
                if code in df.index:
                    stock_name = str(df.loc[code].get("name", ""))
            if not stock_name:
                stock_name = "已持仓"
                
            # 盈亏柔和色彩管理 (亮盈绿 vs 猩红)
            pnl_color = "#00E676" if pnl >= 0 else "#FF1744"
            pnl_sign = "+" if pnl >= 0 else ""
            
            items = [
                (code, "#FFFFFF"),
                (stock_name, "#C2C2C6"),
                (f"{volume:.0f}", "#B0BEC5"),
                (f"{entry_price:.2f}", "#B0BEC5"),
                (f"{curr_price:.2f}", "#FFFFFF"),
                (f"¥ {market_val:,.2f}", "#00E5FF"),
                (f"{pnl_sign}¥ {pnl:,.2f}", pnl_color),
                (f"{pnl_sign}{pnl_pct:.2f}%", pnl_color)
            ]
            
            for col_idx, (text, color_hex) in enumerate(items):
                cell_item = QtWidgets.QTableWidgetItem(str(text))
                cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if color_hex:
                    cell_item.setForeground(QtGui.QColor(color_hex))
                if col_idx in {6, 7}:
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                self.pos_table.setItem(row_idx, col_idx, cell_item)

        # 刷新大卡片统计数据
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
                
        if hasattr(self, "pos_table") and self.pos_table.columnCount() == 8:
            total_pos_w = self.pos_table.viewport().width()
            if total_pos_w > 100:
                # 0.代码, 1.名称, 2.数量, 3.买均, 4.现价, 5.市值, 6.盈亏, 7.盈亏比例
                static_pos_widths = [65, 75, 60, 60, 60, 85, 90]
                scaled_pos_total = int(sum(static_pos_widths) * self.scale_factor)
                
                pos_headers = self.pos_table.horizontalHeader()
                for idx, w in enumerate(static_pos_widths):
                    pos_headers.setSectionResizeMode(idx, QtWidgets.QHeaderView.ResizeMode.Interactive)
                    self.pos_table.setColumnWidth(idx, int(w * self.scale_factor))
                
                # 最后一列“盈亏比例”自适应 Stretch
                pct_width = max(80, total_pos_w - scaled_pos_total)
                self.pos_table.setColumnWidth(7, pct_width)
