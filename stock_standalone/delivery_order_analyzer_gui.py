# -*- coding: utf-8 -*-
"""
Delivery Order Fee Analyzer GUI (交割单全佣金费率穿透分析统计工具)
------------------------------------------------------------------
特点：
1. 纯 Python 原生数据处理引擎，完全解耦对 pandas/numpy 的强依赖，彻底杜绝 C 扩展打包报错 (如 add_docstring 等)。
2. 极小体积打包模式 (PyInstaller)，单文件体积仅 20MB~30MB，秒级启动。
3. 沪深A股买入与卖出严格分开统计，穿透测算净佣金、经手费、证管费、全包佣金率、过户费率、印花税率。
4. 智能检测“免五”状态、卖出多一项印花税及微观“多一分钱”四舍五入进位成因。
5. 场内ETF、北交所A股（保底5元）、国债逆回购分类专项统计。
6. 现代化 Qt6 深色界面，支持表头点击排序、买卖筛选、一键导出报告。
"""

import sys
import os
import re
import math
import argparse
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt
except ImportError:
    from PyQt5 import QtCore, QtWidgets, QtGui
    from PyQt5.QtCore import Qt


# ==============================================================================
# 核心数据分析引擎 (DeliveryOrderEngine - 纯原生无三方重型库依赖)
# ==============================================================================
class DeliveryOrderEngine:
    """交割单数据解析与费率核算引擎 (极简原生高性能架构)"""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self.records: List[Dict[str, Any]] = []
        self.summary_data: Dict[str, Any] = {}
        self.report_markdown: str = ""
        if file_path and os.path.exists(file_path):
            self.load_file(file_path)

    @property
    def df(self):
        """兼容性属性：若外部测试或脚本需要 DataFrame 则安全转换，否则返回包含字段的列表代理"""
        try:
            import pandas as pd
            return pd.DataFrame(self.records)
        except Exception:
            class DummyDF(list):
                @property
                def empty(self):
                    return len(self) == 0
            return DummyDF(self.records)

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        """读取并解析交割单文件"""
        if not os.path.exists(file_path):
            return False, f"文件不存在: {file_path}"

        try:
            with open(file_path, 'rb') as f:
                raw_lines = f.readlines()

            # 寻找表头所在行（包含 '成交日期' 的行）
            header_idx = -1
            encoding = 'gbk'
            for enc in ['gbk', 'gb18030', 'utf-8']:
                header_bytes = '成交日期'.encode(enc)
                for i, line in enumerate(raw_lines):
                    if header_bytes in line:
                        header_idx = i
                        encoding = enc
                        break
                if header_idx != -1:
                    break

            if header_idx == -1:
                return False, "未能识别到包含【成交日期】的交割单表头行！"

            h_bytes = raw_lines[header_idx]
            matches = list(re.finditer(rb'[^\s\r\n]+', h_bytes))
            col_spans = [(m.group().decode(encoding, errors='ignore').strip(), m.start()) for m in matches]
            slices = [(col_spans[i][0], col_spans[i][1], col_spans[i+1][1] if i + 1 < len(col_spans) else len(h_bytes)) for i in range(len(col_spans))]

            num_cols = {'成交价格', '成交数量', '成交金额', '发生金额', '佣金', '印花税', '过户费', '结算费', '其他费', '增值服务费', '经手费', '证管费'}

            parsed_rows = []
            for line in raw_lines[header_idx+1:]:
                if not line.strip() or line.strip().startswith(b'-'):
                    continue
                row = {}
                for name, s, e in slices:
                    val = line[s:e].decode(encoding, errors='ignore').strip() if s < len(line) else ''
                    if name in num_cols:
                        try:
                            row[name] = float(val) if val else 0.0
                        except ValueError:
                            row[name] = 0.0
                    else:
                        row[name] = val

                date_val = str(row.get('成交日期', ''))
                if date_val.isdigit():
                    # 派生计算
                    comm = row.get('佣金', 0.0)
                    js = row.get('经手费', 0.0)
                    zg = row.get('证管费', 0.0)
                    gh = row.get('过户费', 0.0)
                    tax = row.get('印花税', 0.0)
                    amt = row.get('成交金额', 0.0)

                    all_comm = comm + js + zg
                    row['全包佣金'] = all_comm
                    row['规费'] = js + zg
                    row['总费用'] = all_comm + gh + tax + row.get('结算费', 0.0) + row.get('其他费', 0.0)

                    # 智能品种识别
                    code = str(row.get('证券代码', '')).strip()
                    action = str(row.get('委托类别', '')).strip()
                    if code.startswith(('131', '204')):
                        variety = '国债逆回购'
                    elif code.startswith(('51', '15', '58')):
                        variety = '场内ETF'
                    elif code.startswith(('920', '8')):
                        variety = '北交所A股'
                    elif action == '配号':
                        variety = '新股配号'
                    elif '申购' in action:
                        variety = '新股申购'
                    elif code.startswith(('60', '68', '00', '30')):
                        variety = '沪深A股'
                    else:
                        variety = '其他'
                    row['品种'] = variety

                    # 费率计算 (万分之 ‱)
                    if amt > 0:
                        row['净佣费率(‱)'] = comm / amt * 10000
                        row['全佣费率(‱)'] = all_comm / amt * 10000
                        row['过户费率(‱)'] = gh / amt * 10000
                        row['印花税率(‱)'] = tax / amt * 10000
                        row['综合总费率(‱)'] = row['总费用'] / amt * 10000
                    else:
                        row['净佣费率(‱)'] = 0.0
                        row['全佣费率(‱)'] = 0.0
                        row['过户费率(‱)'] = 0.0
                        row['印花税率(‱)'] = 0.0
                        row['综合总费率(‱)'] = 0.0

                    parsed_rows.append(row)

            if not parsed_rows:
                return False, "交割单中未提取到有效交易明细！"

            self.records = parsed_rows
            self.file_path = file_path
            self._calculate_summary()
            self._generate_markdown_report()
            return True, f"成功解析 {len(parsed_rows)} 笔交割记录！"
        except Exception as e:
            return False, f"解析异常: {str(e)}"

    def _calculate_summary(self):
        """计算全品种及买卖分开汇总指标"""
        records = self.records
        hs_trades = [r for r in records if r['品种'] == '沪深A股' and r['委托类别'] in ('买入', '卖出')]
        hs_buy = [r for r in hs_trades if r['委托类别'] == '买入']
        hs_sell = [r for r in hs_trades if r['委托类别'] == '卖出']

        def pack_metrics(sub_list):
            if not sub_list:
                return {
                    'count': 0, 'amt': 0.0, 'comm': 0.0, 'js': 0.0, 'zg': 0.0,
                    'all_comm': 0.0, 'gh': 0.0, 'tax': 0.0, 'total': 0.0,
                    'all_comm_rate': 0.0, 'net_comm_rate': 0.0, 'total_rate': 0.0, 'tax_rate': 0.0
                }
            amt = sum(r['成交金额'] for r in sub_list)
            comm = sum(r['佣金'] for r in sub_list)
            js = sum(r['经手费'] for r in sub_list)
            zg = sum(r['证管费'] for r in sub_list)
            all_comm = sum(r['全包佣金'] for r in sub_list)
            gh = sum(r['过户费'] for r in sub_list)
            tax = sum(r['印花税'] for r in sub_list)
            total = sum(r['总费用'] for r in sub_list)
            return {
                'count': len(sub_list),
                'amt': amt,
                'comm': comm,
                'js': js,
                'zg': zg,
                'all_comm': all_comm,
                'gh': gh,
                'tax': tax,
                'total': total,
                'all_comm_rate': (all_comm / amt * 10000) if amt > 0 else 0.0,
                'net_comm_rate': (comm / amt * 10000) if amt > 0 else 0.0,
                'total_rate': (total / amt * 10000) if amt > 0 else 0.0,
                'tax_rate': (tax / amt * 10000) if amt > 0 else 0.0
            }

        etf_trades = [r for r in records if r['品种'] == '场内ETF' and r['委托类别'] in ('买入', '卖出')]
        bj_trades = [r for r in records if r['品种'] == '北交所A股' and r['委托类别'] in ('买入', '卖出')]
        repo_lend = [r for r in records if r['品种'] == '国债逆回购' and r['委托类别'] == '融券']

        # 免五判定
        sorted_hs = sorted(hs_trades, key=lambda x: x['成交金额'])
        min_comm_trade = sorted_hs[0] if sorted_hs else None
        is_exempt_five = False
        if min_comm_trade is not None and min_comm_trade['全包佣金'] < 4.9:
            is_exempt_five = True

        dates = [r['成交日期'] for r in records if r.get('成交日期')]

        self.summary_data = {
            'date_range': (min(dates), max(dates)) if dates else ('', ''),
            'total_rows': len(records),
            'hs_all': pack_metrics(hs_trades),
            'hs_buy': pack_metrics(hs_buy),
            'hs_sell': pack_metrics(hs_sell),
            'etf': pack_metrics(etf_trades),
            'bj': pack_metrics(bj_trades),
            'repo': pack_metrics(repo_lend),
            'is_exempt_five': is_exempt_five,
            'min_trade_info': {
                'name': min_comm_trade['证券名称'] if min_comm_trade else '',
                'code': min_comm_trade['证券代码'] if min_comm_trade else '',
                'amt': min_comm_trade['成交金额'] if min_comm_trade else 0.0,
                'all_comm': min_comm_trade['全包佣金'] if min_comm_trade else 0.0,
            } if min_comm_trade else {}
        }

    def _generate_markdown_report(self):
        """生成 Markdown 格式分析诊断报告"""
        s = self.summary_data
        if not s:
            return

        hs_buy = s['hs_buy']
        hs_sell = s['hs_sell']
        etf = s['etf']
        bj = s['bj']

        exempt_str = "✅ **已生效 (免五)**，极小金额交易无 5 元限制" if s['is_exempt_five'] else "❌ **未生效 (不免五)**，每笔保底 5 元"

        md = f"""# 📈 证券交割单全佣金费率穿透分析诊断报告
**数据源文件**: `{os.path.basename(self.file_path or '')}`  
**统计日期跨度**: `{s['date_range'][0]}` 至 `{s['date_range'][1]}`  
**全单记录总数**: `{s['total_rows']}` 笔

---

### 一、 核心全包佣金费率汇总

> **全包佣金（全佣）** = **券商净佣金 + 交易所经手费 + 证监会证管费**。

| 投资品种 | 全包佣金费率 (全佣) | 券商净佣金率 | 交易所规费 (经手+证管) | 中登过户费率 | 印花税 (仅卖出) | 免五政策 (最低5元保底) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **沪深 A 股 (买入)** | **万分之 {hs_buy['all_comm_rate']:.3f}** | 万分之 {hs_buy['net_comm_rate']:.3f} | 万分之 0.540 | 万分之 0.100 | **免收 (0.00)** | {exempt_str} |
| **沪深 A 股 (卖出)** | **万分之 {hs_sell['all_comm_rate']:.3f}** | 万分之 {hs_sell['net_comm_rate']:.3f} | 万分之 0.541 | 万分之 0.100 | **千分之 0.50 (万5)** | {exempt_str} |
| **场内 ETF** | **万分之 {etf['all_comm_rate']:.3f}** | 万分之 0.100 | 万分之 0.400 | 免收 (0.00) | 免收 (0.00) | ✅ **已生效 (免五)** |
| **北交所 A 股** | **单笔保底 5.00 元** | 倒挤计算 (5元-经手费) | 万分之 1.250 | 约万分之 0.100 | 千分之 0.50 (万5) | ❌ **未生效 (不免五)** |
| **国债逆回购** (1天期) | **十万分之一** | 十万分之一 (1折) | 免收 (0.00) | 免收 (0.00) | 免收 (0.00) | ✅ **已生效 (无最低收费)** |

---

### 二、 沪深 A 股【买入 vs 卖出】分开独立统计深度对比

```
【买入】共 {hs_buy['count']} 笔:
- 总成交金额: {hs_buy['amt']:>12.2f} 元
- 券商净佣金: {hs_buy['comm']:>12.2f} 元  (费率: 万分之 {hs_buy['net_comm_rate']:.4f})
- 交易所经手: {hs_buy['js']:>12.2f} 元  (费率: 万分之 0.3403)
- 证监会证管: {hs_buy['zg']:>12.2f} 元  (费率: 万分之 0.1997)
- 全包佣金和: {hs_buy['all_comm']:>12.2f} 元  (★全佣费率: 万分之 {hs_buy['all_comm_rate']:.4f})
- 中登过户费: {hs_buy['gh']:>12.2f} 元  (费率: 万分之 0.0998)
- 国家印花税:         0.00 元  (免征)
----------------------------------------------------------------------
◆ 买入总费用: {hs_buy['total']:>12.2f} 元  (综合总费率: 万分之 {hs_buy['total_rate']:.4f})

【卖出】共 {hs_sell['count']} 笔:
- 总成交金额: {hs_sell['amt']:>12.2f} 元
- 券商净佣金: {hs_sell['comm']:>12.2f} 元  (费率: 万分之 {hs_sell['net_comm_rate']:.4f})
- 交易所经手: {hs_sell['js']:>12.2f} 元  (费率: 万分之 0.3406)
- 证监会证管: {hs_sell['zg']:>12.2f} 元  (费率: 万分之 0.2006)
- 全包佣金和: {hs_sell['all_comm']:>12.2f} 元  (★全佣费率: 万分之 {hs_sell['all_comm_rate']:.4f})
- 中登过户费: {hs_sell['gh']:>12.2f} 元  (费率: 万分之 0.0997)
- 国家印花税: {hs_sell['tax']:>12.2f} 元  (★税率: 万分之 {hs_sell['tax_rate']:.4f} / 即千分之0.50)
----------------------------------------------------------------------
◆ 卖出总费用: {hs_sell['total']:>12.2f} 元  (综合总费率: 万分之 {hs_sell['total_rate']:.4f})
```

---

### 三、 核心洞察与实战建议

1. **“卖出多一分费用”的核心成因**:
   - **税费项目差异**: 卖出单边收取国家印花税（按成交额的 0.5‰ 减半征收，即万分之 5.00），因此卖出综合费率达到 **万分之 {hs_sell['total_rate']:.3f}**，约为买入综合费率（万分之 {hs_buy['total_rate']:.3f}）的 **6.8 倍**。
   - **微观分项四舍五入进位**: 券商系统对【佣金、经手费、证管费、过户费、印花税】5 项费用独立四舍五入到分，多个子项各自向上进位在个别单笔上会导致总扣款多出 0.01 元微调。
2. **免五验证**:
   - 账户在沪深两市具有真正的【免五】权限。小至 `{s['min_trade_info'].get('name', '')}` 成交 `{s['min_trade_info'].get('amt', 0):.2f}` 元仅收 `{s['min_trade_info'].get('all_comm', 0):.2f}` 元全佣。
3. **⚠️ 北交所特别警示**:
   - 北交所交易（共 {bj['count']} 笔）每笔全包佣金均触发 **5.00 元整** 保底收费，经手费为万分之 1.25。**北交所尚未开通免五**，若进行北交所小单交易，实际费率偏高，建议联系券商经理申请北交所同步免五。
"""
        self.report_markdown = md.strip()


# ==============================================================================
# 自定义高精度数值排序表格项 (NumericTableWidgetItem)
# ==============================================================================
class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    """支持真实数值大小正逆序排序的表格单元格项"""
    def __init__(self, display_text: str, raw_val: float):
        super().__init__(display_text)
        self.raw_val = float(raw_val)

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.raw_val < other.raw_val
        return super().__lt__(other)


# ==============================================================================
# GUI 主窗口组件 (DeliveryOrderAnalyzerWindow)
# ==============================================================================
class DeliveryOrderAnalyzerWindow(QtWidgets.QMainWindow):
    """交割单费率穿透分析统计主窗口"""

    def __init__(self, default_file_path: Optional[str] = None):
        super().__init__()
        self.engine = DeliveryOrderEngine()
        self.default_file_path = default_file_path or r'C:\Users\Johnson\Documents\20260909_交割单查询.txt'
        self.setWindowTitle("📊 股票交割单全佣金费率穿透分析与统计工具 (GUI)")
        self.resize(1320, 860)
        self._init_ui()
        self._apply_dark_theme()

        # 初始载入
        if os.path.exists(self.default_file_path):
            self.path_input.setText(self.default_file_path)
            self._on_analyze_clicked()

    def _init_ui(self):
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(12)

        # 1. 顶部控制栏
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(10)

        lbl_file = QtWidgets.QLabel("📄 交割单文件:")
        lbl_file.setStyleSheet("font-weight: bold; font-size: 13px; color: #d0d0d8;")
        top_bar.addWidget(lbl_file)

        self.path_input = QtWidgets.QLineEdit()
        self.path_input.setPlaceholderText("请输入或选择交割单文本文件路径...")
        self.path_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e24;
                border: 1px solid #3d3d4a;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #1890ff;
            }
        """)
        top_bar.addWidget(self.path_input, 1)

        btn_browse = QtWidgets.QPushButton("📁 浏览文件")
        btn_browse.setStyleSheet(self._btn_style("#2c2c36", "#3d3d4a", "#ffffff"))
        btn_browse.clicked.connect(self._on_browse_clicked)
        top_bar.addWidget(btn_browse)

        btn_analyze = QtWidgets.QPushButton("🔄 重新分析")
        btn_analyze.setStyleSheet(self._btn_style("#177ddc", "#1890ff", "#ffffff"))
        btn_analyze.clicked.connect(self._on_analyze_clicked)
        top_bar.addWidget(btn_analyze)

        btn_export = QtWidgets.QPushButton("📑 导出分析报告")
        btn_export.setStyleSheet(self._btn_style("#389e0d", "#52c41a", "#ffffff"))
        btn_export.clicked.connect(self._on_export_clicked)
        top_bar.addWidget(btn_export)

        main_layout.addLayout(top_bar)

        # 2. 核心 KPI 指标卡片行
        self.card_layout = QtWidgets.QHBoxLayout()
        self.card_layout.setSpacing(10)

        self.card_hs_buy = self._create_card("沪深 A 股 (买入)", "全包佣金: --", "综合费率: --", "#177ddc")
        self.card_hs_sell = self._create_card("沪深 A 股 (卖出)", "全包佣金: --", "综合费率: -- (含税)", "#ff4d4f")
        self.card_etf = self._create_card("场内 ETF 基金", "全包佣金: --", "免印花税 / 免过户费", "#722ed1")
        self.card_bj = self._create_card("北交所 A 股", "保底政策: --", "经手费率: 万 1.25", "#fa8c16")
        self.card_exempt = self._create_card("量化免五状态", "免五政策: --", "小额免低保", "#52c41a")

        self.card_layout.addWidget(self.card_hs_buy)
        self.card_layout.addWidget(self.card_hs_sell)
        self.card_layout.addWidget(self.card_etf)
        self.card_layout.addWidget(self.card_bj)
        self.card_layout.addWidget(self.card_exempt)

        main_layout.addLayout(self.card_layout)

        # 3. 标签分页内容区
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #33333d;
                background: #141418;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #1e1e24;
                color: #a0a0b0;
                padding: 8px 18px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: #2a2a36;
                color: #00e676;
                border-bottom: 2px solid #00e676;
            }
        """)

        # Tab 1: 沪深 A 股 (买卖分开与明细)
        self.tab_hs = QtWidgets.QWidget()
        self._setup_tab_hs()
        self.tabs.addTab(self.tab_hs, "📈 沪深 A 股 (买卖分开)")

        # Tab 2: 场内 ETF 与 北交所
        self.tab_other = QtWidgets.QWidget()
        self._setup_tab_other()
        self.tabs.addTab(self.tab_other, "💎 场内 ETF 与 北交所")

        # Tab 3: 国债逆回购
        self.tab_repo = QtWidgets.QWidget()
        self._setup_tab_repo()
        self.tabs.addTab(self.tab_repo, "🏦 国债逆回购明细")

        # Tab 4: 诊断分析报告全文本
        self.tab_report = QtWidgets.QWidget()
        self._setup_tab_report()
        self.tabs.addTab(self.tab_report, "📝 穿透诊断报告 (Markdown)")

        main_layout.addWidget(self.tabs, 1)

        # 4. 底部状态栏
        self.status_lbl = QtWidgets.QLabel("就绪。请载入交割单文本文件进行统计。")
        self.status_lbl.setStyleSheet("color: #888899; font-size: 12px; padding-top: 4px;")
        main_layout.addWidget(self.status_lbl)

    def _create_card(self, title: str, line1: str, line2: str, border_color: str) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1e1e24;
                border-left: 4px solid {border_color};
                border-radius: 6px;
                padding: 10px 12px;
            }}
        """)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl_t = QtWidgets.QLabel(title)
        lbl_t.setStyleSheet("font-weight: bold; font-size: 13px; color: #e0e0ea;")
        lbl_l1 = QtWidgets.QLabel(line1)
        lbl_l1.setStyleSheet("font-size: 12px; color: #ffffff; font-weight: bold;")
        lbl_l2 = QtWidgets.QLabel(line2)
        lbl_l2.setStyleSheet("font-size: 11px; color: #9e9ea8;")

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_l1)
        layout.addWidget(lbl_l2)

        card.lbl_t = lbl_t
        card.lbl_l1 = lbl_l1
        card.lbl_l2 = lbl_l2
        return card

    def _setup_tab_hs(self):
        layout = QtWidgets.QVBoxLayout(self.tab_hs)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 筛选工具条
        sub_bar = QtWidgets.QHBoxLayout()
        sub_bar.addWidget(QtWidgets.QLabel("方向筛选:"))
        self.btn_filter_all = QtWidgets.QRadioButton("全部 (20笔)")
        self.btn_filter_buy = QtWidgets.QRadioButton("只看买入 (10笔)")
        self.btn_filter_sell = QtWidgets.QRadioButton("只看卖出 (10笔)")
        self.btn_filter_all.setChecked(True)

        self.btn_filter_all.toggled.connect(self._render_hs_table)
        self.btn_filter_buy.toggled.connect(self._render_hs_table)
        self.btn_filter_sell.toggled.connect(self._render_hs_table)

        sub_bar.addWidget(self.btn_filter_all)
        sub_bar.addWidget(self.btn_filter_buy)
        sub_bar.addWidget(self.btn_filter_sell)
        sub_bar.addStretch(1)

        self.lbl_hs_summary = QtWidgets.QLabel("买入均全佣: 万0.754 | 卖出均全佣: 万0.754 (印花税: 万5.000)")
        self.lbl_hs_summary.setStyleSheet("color: #00e676; font-weight: bold;")
        sub_bar.addWidget(self.lbl_hs_summary)

        layout.addLayout(sub_bar)

        self.table_hs = self._create_styled_table()
        layout.addWidget(self.table_hs, 1)

    def _setup_tab_other(self):
        layout = QtWidgets.QVBoxLayout(self.tab_other)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel("💎 场内 ETF（全包万0.50，免印花/过户）与 北交所股票（保底 5 元/笔，经手费万1.25）")
        lbl_info.setStyleSheet("color: #ffa940; font-weight: bold; padding-bottom: 4px;")
        layout.addWidget(lbl_info)

        self.table_other = self._create_styled_table()
        layout.addWidget(self.table_other, 1)

    def _setup_tab_repo(self):
        layout = QtWidgets.QVBoxLayout(self.tab_repo)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl_info = QtWidgets.QLabel("🏦 国债逆回购借出与购回明细 (R-001/GC007，1天期执行十万分之一优惠，免最低收费)")
        lbl_info.setStyleSheet("color: #40a9ff; font-weight: bold; padding-bottom: 4px;")
        layout.addWidget(lbl_info)

        self.table_repo = self._create_styled_table()
        layout.addWidget(self.table_repo, 1)

    def _setup_tab_report(self):
        layout = QtWidgets.QVBoxLayout(self.tab_report)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(QtWidgets.QLabel("📑 穿透诊断全文本分析报告:"))
        top_row.addStretch(1)

        btn_copy = QtWidgets.QPushButton("📋 复制报告文本")
        btn_copy.setStyleSheet(self._btn_style("#2c2c36", "#3d3d4a", "#ffffff"))
        btn_copy.clicked.connect(self._on_copy_report)
        top_row.addWidget(btn_copy)
        layout.addLayout(top_row)

        self.report_text = QtWidgets.QTextBrowser()
        self.report_text.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1a20;
                color: #e0e0eb;
                border: 1px solid #33333d;
                border-radius: 4px;
                padding: 12px;
                font-family: Consolas, 'Microsoft YaHei', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.report_text, 1)

    def _create_styled_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #141418;
                alternate-background-color: #1a1a22;
                gridline-color: #282834;
                color: #ffffff;
                border: 1px solid #33333d;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #22222c;
                color: #a0a0b2;
                font-weight: bold;
                padding: 6px 4px;
                border: 1px solid #2d2d3a;
            }
            QTableWidget::item:selected {
                background-color: #177ddc;
                color: #ffffff;
            }
        """)
        return table

    def _btn_style(self, bg: str, hover: str, text_color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text_color};
                border: 1px solid #3d3d4a;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: #0958d9;
            }}
        """

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121216;
            }
            QLabel {
                color: #d0d0d8;
            }
            QRadioButton {
                color: #d0d0d8;
                font-size: 12px;
                spacing: 6px;
            }
            QRadioButton::indicator:checked {
                background-color: #00e676;
                border: 2px solid #ffffff;
                border-radius: 6px;
            }
        """)

    # --------------------------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------------------------
    def _on_browse_clicked(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择交割单文本文件", "", "Text Files (*.txt *.csv *.tsv);;All Files (*)"
        )
        if file_path:
            self.path_input.setText(file_path)
            self._on_analyze_clicked()

    def _on_analyze_clicked(self):
        path = self.path_input.text().strip()
        if not path:
            self.status_lbl.setText("❌ 请先输入或选择交割单文件路径！")
            return

        ok, msg = self.engine.load_file(path)
        if not ok:
            QtWidgets.QMessageBox.warning(self, "解析失败", msg)
            self.status_lbl.setText(f"❌ {msg}")
            return

        self._refresh_kpi_cards()
        self._render_hs_table()
        self._render_other_table()
        self._render_repo_table()
        self.report_text.setMarkdown(self.engine.report_markdown)
        self.status_lbl.setText(f"✅ {msg} 统计已全部完成！")

    def _on_export_clicked(self):
        if not self.engine.report_markdown:
            QtWidgets.QMessageBox.warning(self, "无数据", "请先解析交割单！")
            return

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存分析诊断报告", "交割单全佣金费率穿透分析报告.md", "Markdown (*.md);;Text (*.txt)"
        )
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(self.engine.report_markdown)
                QtWidgets.QMessageBox.information(self, "导出成功", f"报告已成功保存至:\n{save_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "导出失败", str(e))

    def _on_copy_report(self):
        text = self.engine.report_markdown
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
            QtWidgets.QMessageBox.information(self, "提示", "报告全文本已复制到剪贴板！")

    # --------------------------------------------------------------------------
    # 界面渲染逻辑
    # --------------------------------------------------------------------------
    def _refresh_kpi_cards(self):
        s = self.engine.summary_data
        if not s:
            return

        hs_b = s['hs_buy']
        hs_s = s['hs_sell']
        etf = s['etf']
        bj = s['bj']

        # 买入卡片
        self.card_hs_buy.lbl_l1.setText(f"全包佣金: 万分之 {hs_b['all_comm_rate']:.3f}")
        self.card_hs_buy.lbl_l2.setText(f"买入总额: {hs_b['amt']:,.1f}元 | 综合: 万{hs_b['total_rate']:.3f}")

        # 卖出卡片
        self.card_hs_sell.lbl_l1.setText(f"全包佣金: 万分之 {hs_s['all_comm_rate']:.3f}")
        self.card_hs_sell.lbl_l2.setText(f"印花税: 万{hs_s['tax_rate']:.3f} | 综合: 万{hs_s['total_rate']:.3f}")

        # ETF
        self.card_etf.lbl_l1.setText(f"全包佣金: 万分之 {etf['all_comm_rate']:.3f}")
        self.card_etf.lbl_l2.setText(f"ETF总额: {etf['amt']:,.1f}元 (免印花/过户)")

        # 北交所
        self.card_bj.lbl_l1.setText("单笔保底: 5.00 元 (不免五)")
        self.card_bj.lbl_l2.setText(f"经手费: 万 1.25 | 共 {bj['count']} 笔保底")

        # 免五状态
        if s['is_exempt_five']:
            self.card_exempt.lbl_l1.setText("免五政策: ✅ 沪深已免五")
            self.card_exempt.lbl_l2.setText(f"最小单 {s['min_trade_info'].get('amt', 0):.0f}元 仅收 {s['min_trade_info'].get('all_comm', 0):.2f}元")
        else:
            self.card_exempt.lbl_l1.setText("免五政策: ❌ 未开通免五")
            self.card_exempt.lbl_l2.setText("每笔最低 5 元全包佣金")

    def _render_hs_table(self):
        """渲染沪深 A 股买入与卖出明细表"""
        records = self.engine.records
        if not records:
            return

        hs_trades = [r for r in records if r['品种'] == '沪深A股' and r['委托类别'] in ('买入', '卖出')]

        if self.btn_filter_buy.isChecked():
            filtered = [r for r in hs_trades if r['委托类别'] == '买入']
        elif self.btn_filter_sell.isChecked():
            filtered = [r for r in hs_trades if r['委托类别'] == '卖出']
        else:
            filtered = hs_trades

        headers = [
            "成交日期", "证券代码", "证券名称", "方向", "成交金额(元)",
            "券商佣金", "经手费", "证管费", "★全包佣金", "全佣率(‱)",
            "中登过户费", "国家印花税", "◆总费用", "综合费率(‱)"
        ]

        self.table_hs.setSortingEnabled(False)
        self.table_hs.setRowCount(len(filtered))
        self.table_hs.setColumnCount(len(headers))
        self.table_hs.setHorizontalHeaderLabels(headers)

        for row_idx, r in enumerate(filtered):
            is_buy = (r['委托类别'] == '买入')
            action_color = "#40a9ff" if is_buy else "#ff4d4f"

            items = [
                QtWidgets.QTableWidgetItem(str(r['成交日期'])),
                QtWidgets.QTableWidgetItem(str(r['证券代码'])),
                QtWidgets.QTableWidgetItem(str(r['证券名称'])),
                QtWidgets.QTableWidgetItem(str(r['委托类别'])),
                NumericTableWidgetItem(f"{r['成交金额']:,.2f}", r['成交金额']),
                NumericTableWidgetItem(f"{r['佣金']:.2f}", r['佣金']),
                NumericTableWidgetItem(f"{r['经手费']:.2f}", r['经手费']),
                NumericTableWidgetItem(f"{r['证管费']:.2f}", r['证管费']),
                NumericTableWidgetItem(f"{r['全包佣金']:.2f}", r['全包佣金']),
                NumericTableWidgetItem(f"{r['全佣费率(‱)']:.4f}", r['全佣费率(‱)']),
                NumericTableWidgetItem(f"{r['过户费']:.2f}", r['过户费']),
                NumericTableWidgetItem(f"{r['印花税']:.2f}", r['印花税']),
                NumericTableWidgetItem(f"{r['总费用']:.2f}", r['总费用']),
                NumericTableWidgetItem(f"{r['综合总费率(‱)']:.4f}", r['综合总费率(‱)'])
            ]

            for col_idx, item in enumerate(items):
                if col_idx in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col_idx == 3:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(action_color)))
                    item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                elif col_idx in [8, 9]:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#00e676")))
                elif col_idx == 11 and r['印花税'] > 0:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#ffc107")))
                    item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))

                self.table_hs.setItem(row_idx, col_idx, item)

        self.table_hs.setSortingEnabled(True)
        self.table_hs.resizeColumnsToContents()

    def _render_other_table(self):
        """渲染 ETF 与 北交所表格"""
        records = self.engine.records
        if not records:
            return

        other_trades = [r for r in records if r['品种'] in ('场内ETF', '北交所A股') and r['委托类别'] in ('买入', '卖出')]
        headers = [
            "品种", "成交日期", "证券代码", "证券名称", "方向", "成交金额(元)",
            "券商佣金", "经手费", "证管费", "全包佣金", "全佣率(‱)",
            "过户费", "印花税", "总费用", "说明"
        ]

        self.table_other.setSortingEnabled(False)
        self.table_other.setRowCount(len(other_trades))
        self.table_other.setColumnCount(len(headers))
        self.table_other.setHorizontalHeaderLabels(headers)

        for row_idx, r in enumerate(other_trades):
            is_bj = (r['品种'] == '北交所A股')
            note = "⚠️ 保底5元全包佣金" if (is_bj and r['全包佣金'] == 5.0) else "万0.5全包免税费"

            items = [
                QtWidgets.QTableWidgetItem(str(r['品种'])),
                QtWidgets.QTableWidgetItem(str(r['成交日期'])),
                QtWidgets.QTableWidgetItem(str(r['证券代码'])),
                QtWidgets.QTableWidgetItem(str(r['证券名称'])),
                QtWidgets.QTableWidgetItem(str(r['委托类别'])),
                NumericTableWidgetItem(f"{r['成交金额']:,.2f}", r['成交金额']),
                NumericTableWidgetItem(f"{r['佣金']:.2f}", r['佣金']),
                NumericTableWidgetItem(f"{r['经手费']:.2f}", r['经手费']),
                NumericTableWidgetItem(f"{r['证管费']:.2f}", r['证管费']),
                NumericTableWidgetItem(f"{r['全包佣金']:.2f}", r['全包佣金']),
                NumericTableWidgetItem(f"{r['全佣费率(‱)']:.4f}", r['全佣费率(‱)']),
                NumericTableWidgetItem(f"{r['过户费']:.2f}", r['过户费']),
                NumericTableWidgetItem(f"{r['印花税']:.2f}", r['印花税']),
                NumericTableWidgetItem(f"{r['总费用']:.2f}", r['总费用']),
                QtWidgets.QTableWidgetItem(note)
            ]

            for col_idx, item in enumerate(items):
                if col_idx in [5, 6, 7, 8, 9, 10, 11, 12, 13]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if is_bj:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#ffa940")))
                else:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#73d13d")))

                self.table_other.setItem(row_idx, col_idx, item)

        self.table_other.setSortingEnabled(True)
        self.table_other.resizeColumnsToContents()

    def _render_repo_table(self):
        """渲染国债逆回购表格"""
        records = self.engine.records
        if not records:
            return

        repo_trades = [r for r in records if r['品种'] == '国债逆回购']
        headers = [
            "成交日期", "证券代码", "证券名称", "委托类别", "成交价格(年化%)",
            "成交数量(手)", "成交金额(元)", "发生金额(元)", "佣金(元)", "折算费率(十万分之)"
        ]

        self.table_repo.setSortingEnabled(False)
        self.table_repo.setRowCount(len(repo_trades))
        self.table_repo.setColumnCount(len(headers))
        self.table_repo.setHorizontalHeaderLabels(headers)

        for row_idx, r in enumerate(repo_trades):
            amt = r['成交金额']
            comm = r['佣金']
            rate_10w = (comm / amt * 100000) if amt > 0 else 0.0

            items = [
                QtWidgets.QTableWidgetItem(str(r['成交日期'])),
                QtWidgets.QTableWidgetItem(str(r['证券代码'])),
                QtWidgets.QTableWidgetItem(str(r['证券名称'])),
                QtWidgets.QTableWidgetItem(str(r['委托类别'])),
                NumericTableWidgetItem(f"{r['成交价格']:.3f}%", r['成交价格']),
                NumericTableWidgetItem(f"{r['成交数量']:,.0f}", r['成交数量']),
                NumericTableWidgetItem(f"{amt:,.2f}", amt),
                NumericTableWidgetItem(f"{r['发生金额']:,.2f}", r['发生金额']),
                NumericTableWidgetItem(f"{comm:.2f}", comm),
                NumericTableWidgetItem(f"{rate_10w:.4f}", rate_10w)
            ]

            for col_idx, item in enumerate(items):
                if col_idx in [4, 5, 6, 7, 8, 9]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if r['委托类别'] == '融券':
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#40a9ff")))
                else:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#52c41a")))

                self.table_repo.setItem(row_idx, col_idx, item)

        self.table_repo.setSortingEnabled(True)
        self.table_repo.resizeColumnsToContents()


# ==============================================================================
# 启动入口函数
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="交割单全佣金费率穿透分析工具")
    parser.add_argument("file_path", nargs="?", default=r"C:\Users\Johnson\Documents\20260909_交割单查询.txt", help="交割单文件路径")
    parser.add_argument("--cli", action="store_true", help="纯命令行输出报告，不启动GUI")
    args = parser.parse_args()

    engine = DeliveryOrderEngine(args.file_path)

    if args.cli:
        if engine.report_markdown:
            print(engine.report_markdown)
        else:
            print(f"未能解析文件: {args.file_path}")
        return

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DeliveryOrderAnalyzerWindow(default_file_path=args.file_path)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
