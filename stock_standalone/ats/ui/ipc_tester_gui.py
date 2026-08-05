# -*- coding: utf-8 -*-
"""
Created At: 2026-08-05
Description: IPC 全功能实时诊断与图形化可视测试工具 (IPC Tester GUI) - 支持端口自定义与全指令集测试
"""
import sys
import os
import time
import socket
import struct
import pickle
import json
import pandas as pd

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QTextEdit, QLineEdit, QGroupBox, QSplitter, QSpinBox,
    QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QFont

# 导入项目核心引擎
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from ipc_sync_manager import IPCSyncManager
from multi_period_strategy_engine import MultiPeriodStrategyEngine


class IPCTesterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ IPC 数据流与多周期策略全功能图形化测试诊断中心")
        self.setMinimumSize(800, 500)
        self.resize(1280, 820)
        self.config_key = "ipc_tester_gui_state"
        self.current_df = None
        self.ipc_mgr = None
        self.current_port = 26671

        self.engine = MultiPeriodStrategyEngine()
        self._init_ui()
        self._restore_window_state()
        self._rebind_ipc_port(self.current_port)

    def _restore_window_state(self):
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    state_hex = data.get(self.config_key, "")
                    if state_hex:
                        from PyQt6.QtCore import QByteArray
                        # 精准恢复用户上次调整的窗口位置与尺寸大小
                        self.restoreGeometry(QByteArray.fromHex(state_hex.encode("utf-8")))
        except Exception as e:
            print(f"[IPCTesterGUI] Restore window state error: {e}")

    def closeEvent(self, event):
        self._save_window_state()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口大小发生改变时触发防抖保存
        if not hasattr(self, '_save_timer'):
            from PyQt6.QtCore import QTimer
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save_window_state)
        self._save_timer.start(500)

    def _save_window_state(self):
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            data = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data[self.config_key] = bytes(self.saveGeometry().toHex()).decode("utf-8")
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[IPCTesterGUI] Save window state error: {e}")

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 1. 顶部端口配置与控制中心
        top_box = QGroupBox("⚙️ 端口自定义与通信服务控制中心")
        top_layout = QHBoxLayout(top_box)

        top_layout.addWidget(QLabel("🎯 自定义监听端口:"))
        self.spn_port = QSpinBox()
        self.spn_port.setRange(1024, 65535)
        self.spn_port.setValue(26671)
        self.spn_port.setFixedWidth(90)
        top_layout.addWidget(self.spn_port)

        self.btn_rebind = QPushButton("🔌 切换/重新绑定端口")
        self.btn_rebind.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        self.btn_rebind.clicked.connect(self._on_rebind_clicked)
        top_layout.addWidget(self.btn_rebind)

        top_layout.addSpacing(20)
        self.lbl_status = QLabel("状态: 准备就绪")
        self.lbl_status.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        top_layout.addWidget(self.lbl_status)

        top_layout.addStretch()
        self.lbl_meta = QLabel("数据: 0 行 | 0 列 | 最新更新: --:--:--")
        top_layout.addWidget(self.lbl_meta)
        layout.addWidget(top_box)

        # 2. 全量定义的 IPC 指令操作面板
        cmd_box = QGroupBox("🎮 全量 IPC 信令指令集操作面板")
        cmd_layout = QHBoxLayout(cmd_box)

        self.btn_sync = QPushButton("🚀 全量同步 (REQ_FULL_SYNC)")
        self.btn_sync.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_sync.clicked.connect(lambda: self._send_ipc_cmd("REQ_FULL_SYNC"))
        cmd_layout.addWidget(self.btn_sync)

        self.btn_ack = QPushButton("✅ 反馈确认 (ATS_RECEIVED)")
        self.btn_ack.setStyleSheet("background-color: #198754; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_ack.clicked.connect(lambda: self._send_ipc_cmd("ATS_RECEIVED"))
        cmd_layout.addWidget(self.btn_ack)

        self.btn_delta = QPushButton("🔄 增量同步 (REQ_DELTA_SYNC)")
        self.btn_delta.setStyleSheet("background-color: #0dcaf0; color: black; font-weight: bold; padding: 6px 12px;")
        self.btn_delta.clicked.connect(lambda: self._send_ipc_cmd("REQ_DELTA_SYNC"))
        cmd_layout.addWidget(self.btn_delta)

        self.btn_ping = QPushButton("💓 心跳检测 (PING)")
        self.btn_ping.setStyleSheet("background-color: #ffc107; color: black; font-weight: bold; padding: 6px 12px;")
        self.btn_ping.clicked.connect(lambda: self._send_ipc_cmd("PING"))
        cmd_layout.addWidget(self.btn_ping)

        cmd_layout.addSpacing(15)
        self.btn_mock = QPushButton("⚡ 本地模拟 300058 真实行情包注入")
        self.btn_mock.setStyleSheet("background-color: #6f42c1; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_mock.clicked.connect(self._inject_mock_300058)
        cmd_layout.addWidget(self.btn_mock)

        layout.addWidget(cmd_box)

        # 3. 中央多 Tab 看板
        self.tabs = QTabWidget()

        # Tab 1: 全量 IPC 行情列表 (支持代码/名称、Pandas Query 表达式、特定列精准过滤)
        tab1 = QWidget()
        l1 = QVBoxLayout(tab1)
        
        search_box = QHBoxLayout()
        search_box.setSpacing(6)

        # 1.1 代码/名称过滤
        search_box.addWidget(QLabel("🔍 代码/名称:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("代码/名称...")
        self.txt_search.setFixedWidth(130)
        self.txt_search.textChanged.connect(self._apply_combined_filter)
        search_box.addWidget(self.txt_search)

        search_box.addSpacing(10)

        # 1.2 Query 表达式查询
        search_box.addWidget(QLabel("⚡ Query 表达式:"))
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("如: percent > 3.0 and close > nclose")
        self.txt_query.returnPressed.connect(self._apply_combined_filter)
        search_box.addWidget(self.txt_query)

        # Query 预设下拉
        self.cmb_preset_query = QComboBox()
        self.cmb_preset_query.addItems([
            "📋 常用 Query 预设...",
            "percent > 5.0 (大涨>5%)",
            "close > nclose (站上均价)",
            "nclose >= 1.005 * vwap_cum_2d (突破2日机构线)",
            "vwap_cum_2d >= vwap_cum_3d (机构成本线多头)",
            "sig_bottom > 0 or sig_launch > 0 (信号启动)"
        ])
        self.cmb_preset_query.currentIndexChanged.connect(self._on_preset_query_changed)
        search_box.addWidget(self.cmb_preset_query)

        self.btn_run_query = QPushButton("▶ 运行 Query")
        self.btn_run_query.setStyleSheet("background-color: #1e3a29; color: #00ff88; font-weight: bold;")
        self.btn_run_query.clicked.connect(self._apply_combined_filter)
        search_box.addWidget(self.btn_run_query)

        search_box.addSpacing(10)

        # 1.3 特定列筛选
        search_box.addWidget(QLabel("📌 特定列:"))
        self.txt_col_search = QLineEdit()
        self.txt_col_search.setPlaceholderText("特定列 (如: vwap, nclose)...")
        self.txt_col_search.setFixedWidth(150)
        self.txt_col_search.textChanged.connect(self._apply_combined_filter)
        search_box.addWidget(self.txt_col_search)

        self.btn_reset_filter = QPushButton("🧹 重置")
        self.btn_reset_filter.setFixedWidth(50)
        self.btn_reset_filter.clicked.connect(self._reset_all_filters)
        search_box.addWidget(self.btn_reset_filter)

        l1.addLayout(search_box)

        self.tbl_all = QTableWidget()
        self.tbl_all.setAlternatingRowColors(True)
        l1.addWidget(self.tbl_all)
        self.tabs.addTab(tab1, "🌐 全量 IPC 实时行情表 (5000+ 行)")

        # Tab 2: 300058 精细诊断抽屉
        tab2 = QWidget()
        l2 = QVBoxLayout(tab2)

        self.lbl_300058_title = QLabel("📌 300058 (蓝色光标) 真实 IPC 衍生指标与 [条件1] 判定面板")
        self.lbl_300058_title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        l2.addWidget(self.lbl_300058_title)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：IPC 衍生列明细
        self.tbl_300058_cols = QTableWidget()
        self.tbl_300058_cols.setColumnCount(2)
        self.tbl_300058_cols.setHorizontalHeaderLabels(["指标字段 (Column)", "真实数值 (Value)"])
        self.tbl_300058_cols.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.tbl_300058_cols)

        # 右侧：条件 1 评估细节
        self.txt_cond1_eval = QTextEdit()
        self.txt_cond1_eval.setReadOnly(True)
        self.txt_cond1_eval.setFont(QFont("Consolas", 10))
        splitter.addWidget(self.txt_cond1_eval)

        splitter.setSizes([500, 750])
        l2.addWidget(splitter)
        self.tabs.addTab(tab2, "🎯 300058 专属精细诊断")

        # Tab 3: 通信与异常日志
        tab3 = QWidget()
        l3 = QVBoxLayout(tab3)
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas; font-size: 11pt;")
        l3.addWidget(self.txt_logs)
        self.tabs.addTab(tab3, "📜 IPC 实时信令日志控制台")

        layout.addWidget(self.tabs)

        # 4. 定时器自动轮询同步数据
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_ipc_update)
        self.timer.start(300)

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.txt_logs.append(f"[{ts}] {msg}")

    def _rebind_ipc_port(self, port):
        if self.ipc_mgr:
            self.ipc_mgr.stop()

        self.current_port = port
        self.log(f"正在建立 IPCSyncManager 句柄，绑定端口: {port}...")
        self.ipc_mgr = IPCSyncManager(port=port)
        self.ipc_mgr.start()
        if hasattr(self.ipc_mgr, '_bind_event'):
            self.ipc_mgr._bind_event.wait(timeout=1.0)
        else:
            time.sleep(0.15)

        if getattr(self.ipc_mgr, 'is_bound', False):
            self.spn_port.setValue(port)
            self.lbl_status.setText(f"状态: ✅ 已成功绑定本地端口 {port} 并开启监听")
            self.lbl_status.setStyleSheet("color: #198754; font-weight: bold;")
            self.log(f"✅ 后台 Socket 监听线程启动成功 (Port={port})！")
        else:
            self.log(f"❌ 端口 {port} 已经被占用！系统正在自动探索备用测试端口 (26679)...")
            self.ipc_mgr.stop()
            fallback_port = 26679 if port != 26679 else 26678
            self.current_port = fallback_port
            self.ipc_mgr = IPCSyncManager(port=fallback_port)
            self.ipc_mgr.start()
            if hasattr(self.ipc_mgr, '_bind_event'):
                self.ipc_mgr._bind_event.wait(timeout=1.0)
            else:
                time.sleep(0.15)
            self.spn_port.setValue(fallback_port)
            self.lbl_status.setText(f"状态: ✅ 智能切至备用端口 {fallback_port} 监听就绪")
            self.lbl_status.setStyleSheet("color: #0d6efd; font-weight: bold;")
            self.log(f"✅ 自动切至备用测试端口 {fallback_port} 并开启 Socket 监听！")

    def _on_rebind_clicked(self):
        new_port = self.spn_port.value()
        self._rebind_ipc_port(new_port)

    def _send_ipc_cmd(self, cmd_name):
        if not self.ipc_mgr:
            return
        from data_utils import send_code_via_pipe, PIPE_NAME_TK
        import logging
        logger = logging.getLogger("IPCTesterGUI")

        self.log(f"📤 [发送信令] 指令: {cmd_name} | 目标端口: {self.current_port}")
        cmd_dict = {"cmd": cmd_name, "port": self.current_port, "ts": time.time()}
        
        ok = send_code_via_pipe(cmd_dict, logger=logger, pipe_name=PIPE_NAME_TK)
        if ok:
            self.lbl_status.setText(f"状态: 成功向 TK 发送 {cmd_name} (Port={self.current_port})")
            self.log(f"✅ 信令 {cmd_name} 成功通过标准管道写入 TK 监控端 (Port={self.current_port})！")
        else:
            self.lbl_status.setText(f"状态: ❌ 发送 {cmd_name} 失败！")
            self.log(f"❌ 管道信令 {cmd_name} 发送失败，请确认 TK 监控端处于运行状态。")

    def _inject_mock_300058(self):
        self.log("⚡ 正在构造并注入 300058 真实行情测试包...")
        mock_df = pd.DataFrame([{
            'code': '300058',
            'name': '蓝色光标',
            'nclose': 15.798,
            'vwap_cum_2d': 15.523,
            'vwap_cum_3d': 15.198,
            'vwap_cum_4d': 14.826,
            'last_vwap_cum_2d': 14.978,
            'last_vwap_cum_3d': 14.572,
            'close': 15.73,
            'open': 15.24,
            'volume': 1250000,
            'amount': 19687500.0
        }])

        pkg_payload = ('UPDATE_DF_DATA', {'type': 'UPDATE_DF_ALL', 'data': mock_df})
        raw_pickle = pickle.dumps(pkg_payload)
        header = b"DATA" + struct.pack("!I", len(raw_pickle)) + raw_pickle

        try:
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.connect(('127.0.0.1', self.current_port))
            client_sock.sendall(header)
            client_sock.close()
            self.log(f"✅ 成功向本地 Socket (Port={self.current_port}) 注入 300058 测试数据包！")
        except Exception as e:
            self.log(f"❌ 本地 Socket 注入失败: {e}")

    def _check_ipc_update(self):
        if not self.ipc_mgr:
            return
        df = self.ipc_mgr.get_current_df()
        if df is not None and not df.empty:
            if self.current_df is None or len(df) != len(self.current_df) or self.ipc_mgr.last_recv_t != getattr(self, '_last_seen_t', 0):
                self._last_seen_t = self.ipc_mgr.last_recv_t
                self.current_df = df
                self._update_ui_with_df(df)

    def _update_ui_with_df(self, df):
        ts = time.strftime("%H:%M:%S", time.localtime(self.ipc_mgr.last_recv_t))
        self.lbl_status.setText("状态: ✅ 成功接收行情数据包！")
        self.lbl_status.setStyleSheet("color: #198754; font-weight: bold;")
        self.lbl_meta.setText(f"数据: {len(df)} 行 | {len(df.columns)} 列 | 最新更新: {ts}")
        self.log(f"✅ 成功从 IPC Socket 接收解包: rows={len(df)}, cols={len(df.columns)}")

    def _on_preset_query_changed(self, idx):
        if idx <= 0:
            return
        raw_text = self.cmb_preset_query.currentText()
        if '(' in raw_text and ')' in raw_text:
            expr = raw_text.split('(')[0].strip()
        else:
            expr = raw_text.strip()
        self.txt_query.setText(expr)
        self._apply_combined_filter()

    def _reset_all_filters(self):
        self.txt_search.clear()
        self.txt_query.clear()
        self.txt_col_search.clear()
        self.cmb_preset_query.setCurrentIndex(0)
        if self.current_df is not None:
            self._populate_all_table(self.current_df)

    def _apply_combined_filter(self):
        if self.current_df is None or self.current_df.empty:
            return
            
        target_df = self.current_df.copy()
        
        # 1. 应用 Query 表达式过滤
        query_expr = self.txt_query.text().strip()
        if query_expr:
            try:
                from stock_logic_utils import PandasQueryEngine
                engine = PandasQueryEngine()
                target_df = engine.execute(target_df, query_expr)
                self.lbl_status.setText(f" Query 命中: {len(target_df)} 只标的")
                self.lbl_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            except Exception as e:
                self.lbl_status.setText(f"❌ Query 语法异常: {e}")
                self.lbl_status.setStyleSheet("color: #ff5555; font-weight: bold;")

        # 2. 应用 代码/名称 检索
        code_name_kw = self.txt_search.text().strip().lower()
        if code_name_kw and not target_df.empty:
            def _match_row(r):
                c_val = str(r.name if hasattr(r, 'name') else r.get('code', '')).lower()
                n_val = str(r.get('name', '')).lower()
                return (code_name_kw in c_val) or (code_name_kw in n_val)
            
            mask = target_df.apply(_match_row, axis=1)
            target_df = target_df[mask]

        # 3. 应用 特定列 (Specific Column) 多词模糊匹配显隐过滤
        col_kw_raw = self.txt_col_search.text().strip().lower()
        if col_kw_raw and not target_df.empty:
            import re
            # 支持空格、逗号、分号分割多个模糊子串 (如 'vwap 2d' 或 'vwap, 2d')
            sub_kws = [k for k in re.split(r'[,;\s]+', col_kw_raw) if k]
            
            def _match_col(col_name):
                c_str = str(col_name).lower()
                # 要求列名中必须同时包含所有输入的模糊关键词片段
                return all(kw in c_str for kw in sub_kws)

            matched_cols = [c for c in target_df.columns if _match_col(c)]
            # 保证保留 code 和 name 主键列
            base_cols = [c for c in ['code', 'name'] if c in target_df.columns]
            final_cols = list(dict.fromkeys(base_cols + matched_cols))
            
            if len(matched_cols) > 0:
                target_df = target_df[final_cols]
                self.lbl_status.setText(f"📌 特定列模糊匹配: 找到 {len(matched_cols)} 列 ({', '.join(matched_cols[:3])}...)")
                self.lbl_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            else:
                self.lbl_status.setText(f"⚠️ 未找到匹配 '{col_kw_raw}' 的特定列")
                self.lbl_status.setStyleSheet("color: #ffaa00; font-weight: bold;")

        self._populate_all_table(target_df)

    def _populate_all_table(self, df):
        display_df = df.head(500)
        self.tbl_all.clear()
        self.tbl_all.setRowCount(len(display_df))
        
        # 自动提取列
        cols = list(display_df.columns)
        has_code_index = 'code' not in cols
        
        if has_code_index:
            self.tbl_all.setColumnCount(len(cols) + 1)
            headers = ["代码 (code)"] + cols
        else:
            self.tbl_all.setColumnCount(len(cols))
            headers = cols
            
        self.tbl_all.setHorizontalHeaderLabels(headers)

        for r_idx, (idx_val, row) in enumerate(display_df.iterrows()):
            col_offset = 0
            if has_code_index:
                self.tbl_all.setItem(r_idx, 0, QTableWidgetItem(str(idx_val)))
                col_offset = 1

            code_str = str(row.get('code', idx_val))
            for c_idx, col in enumerate(cols):
                val = row[col]
                val_str = f"{val:.3f}" if isinstance(val, float) else str(val)
                item = QTableWidgetItem(val_str)
                if code_str == '300058':
                    item.setBackground(QColor("#fff3cd"))
                self.tbl_all.setItem(r_idx, c_idx + col_offset, item)

    def _diagnose_300058(self, df):
        if 'code' in df.columns:
            row_df = df[df['code'].astype(str).str.zfill(6) == '300058']
        elif '300058' in df.index:
            row_df = df.loc[['300058']]
        else:
            row_df = pd.DataFrame()

        if row_df.empty:
            self.lbl_300058_title.setText("📌 300058 (未在当前 IPC 数据集中找到！)")
            return

        enriched_df = self.engine.ensure_strategy_ipc_columns(row_df.copy(), force_refresh=True)
        r = enriched_df.iloc[0]

        cols = list(enriched_df.columns)
        self.tbl_300058_cols.setRowCount(len(cols))
        for idx, col in enumerate(cols):
            self.tbl_300058_cols.setItem(idx, 0, QTableWidgetItem(col))
            val = r[col]
            val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
            self.tbl_300058_cols.setItem(idx, 1, QTableWidgetItem(val_str))

        nclose = r.get('nclose', 0.0)
        vwap_2d = r.get('vwap_cum_2d', 0.0)
        vwap_3d = r.get('vwap_cum_3d', 0.0)
        vwap_4d = r.get('vwap_cum_4d', 0.0)
        l_vwap_2d = r.get('last_vwap_cum_2d', 0.0)
        l_vwap_3d = r.get('last_vwap_cum_3d', 0.0)
        close_val = r.get('close', 0.0)

        c1 = nclose >= 1.005 * vwap_2d
        c2 = vwap_2d >= vwap_3d
        c3 = vwap_3d >= vwap_4d
        c4 = vwap_2d > l_vwap_2d
        c5 = vwap_3d > l_vwap_3d
        c6 = close_val > nclose

        html = f"""
        <h3>📊 300058 真实 IPC 行情 [条件 1] 评估报告</h3>
        <p><b>提取时间:</b> {time.strftime('%H:%M:%S')}</p>
        <hr>
        <table border='1' cellspacing='0' cellpadding='5' width='100%'>
          <tr bgcolor='#f8f9fa'><th>子条件表达式</th><th>真实提取数据与比较</th><th>判定结果</th></tr>
          <tr><td>nclose &gt;= 1.005 * vwap_cum_2d</td><td>{nclose:.3f} &gt;= {1.005*vwap_2d:.3f} (vwap_2d={vwap_2d:.3f})</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c1 else '<font color="red"><b>❌ FAIL</b></font>'}</td></tr>
          <tr><td>vwap_cum_2d &gt;= vwap_cum_3d</td><td>{vwap_2d:.3f} &gt;= {vwap_3d:.3f}</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c2 else '<font color="red"><b>❌ FAIL</b></font>'}</td></tr>
          <tr><td>vwap_cum_3d &gt;= vwap_cum_4d</td><td>{vwap_3d:.3f} &gt;= {vwap_4d:.3f}</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c3 else '<font color="red"><b>❌ FAIL</b></font>'}</td></tr>
          <tr><td>vwap_cum_2d &gt; last_vwap_cum_2d</td><td>{vwap_2d:.3f} &gt; {l_vwap_2d:.3f}</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c4 else '<font color="red"><b>❌ FAIL</b></font>'}</td></tr>
          <tr><td>vwap_cum_3d &gt; last_vwap_cum_3d</td><td>{vwap_3d:.3f} &gt; {l_vwap_3d:.3f}</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c5 else '<font color="red"><b>❌ FAIL</b></font>'}</td></tr>
          <tr><td>close &gt; nclose</td><td>{close_val:.3f} &gt; {nclose:.3f}</td><td>{'<font color="green"><b>✅ PASSED</b></font>' if c6 else '<font color="red"><b>❌ FAIL (盘中微调)</b></font>'}</td></tr>
        </table>
        """
        self.txt_cond1_eval.setHtml(html)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    gui = IPCTesterGUI()
    gui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
