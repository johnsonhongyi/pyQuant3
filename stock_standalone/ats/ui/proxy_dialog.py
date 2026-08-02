# -*- coding: utf-8 -*-
"""
ATS Global Market Proxy Settings Dialog
网络代理 (HTTP/SOCKS5) 设置与状态控制弹窗，支持一键切换与连通性测试。
采用纯 Python daemon 守护线程与 QObject 信号桥解耦，彻底防范 Qt QThread 销毁引发的致命闪退崩溃。
"""

import sys
import os
import json
import urllib.request
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from JSONData.global_market_data import get_proxy_config, save_proxy_config


class ProxyTestSignalBridge(QObject):
    """用于异步子线程安全向 Qt 主 UI 线程派发结果信号的桥接器"""
    result_signal = pyqtSignal(bool, float, str)


def start_async_proxy_test(proxy_url: str, bridge: ProxyTestSignalBridge):
    """启动纯 Python daemon 守护线程进行 6 秒超时代理连通性测试"""
    def _worker():
        import time
        t0 = time.time()
        test_url = "https://query2.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1m"
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            req = urllib.request.Request(test_url, headers=headers)
            proxy_handler = urllib.request.ProxyHandler({
                'http': proxy_url,
                'https': proxy_url
            })
            opener = urllib.request.build_opener(proxy_handler)
            with opener.open(req, timeout=6.0) as resp:
                status = resp.status
                latency = (time.time() - t0) * 1000.0
                if status == 200:
                    bridge.result_signal.emit(True, latency, f"连通成功 (200 OK), 延迟: {latency:.1f}ms")
                else:
                    bridge.result_signal.emit(False, latency, f"服务器响应异常状态码: {status}")
        except Exception as ex:
            latency = (time.time() - t0) * 1000.0
            bridge.result_signal.emit(False, latency, f"连接失败: {str(ex)}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


class ProxySettingsDialog(QDialog):
    """代理 Proxy 设置与状态控制弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 网络代理 (Proxy) 设置")
        self.setFixedSize(480, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.is_testing = False
        self.bridge = None

        self._init_ui()
        self._load_config()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #131722;
                color: #d1d4dc;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            }
            QLabel {
                color: #d1d4dc;
                font-size: 9.5pt;
            }
            QLineEdit {
                background-color: #1e222d;
                color: #ffffff;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 9.5pt;
            }
            QLineEdit:disabled {
                background-color: #181b24;
                color: #787b86;
                border: 1px solid #2a2e39;
            }
            QPushButton#btn_test {
                background-color: #1e222d;
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton#btn_test:hover {
                background-color: #00E5FF;
                color: #000000;
            }
            QPushButton#btn_test:disabled {
                background-color: #181b24;
                color: #5d606b;
                border: 1px solid #2a2e39;
            }
            QPushButton#btn_save {
                background-color: #2962FF;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 7px 20px;
                font-weight: bold;
            }
            QPushButton#btn_save:hover {
                background-color: #1E54E4;
            }
            QPushButton#btn_save:disabled {
                background-color: #1c274c;
                color: #5d606b;
            }
            QPushButton#btn_cancel {
                background-color: #2a2e39;
                color: #b2b5be;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 7px 16px;
            }
            QPushButton#btn_cancel:hover {
                background-color: #363c4e;
                color: #ffffff;
            }
            QPushButton#btn_cancel:disabled {
                background-color: #181b24;
                color: #5d606b;
                border: 1px solid #2a2e39;
            }
            QCheckBox {
                color: #e2e2e5;
                font-size: 10pt;
                font-weight: bold;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 标题栏说明
        lbl_info = QLabel("配置 HTTP / SOCKS5 全局网络代理，用于穿透访问 Yahoo 财经等外盘行情。")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #787b86; font-size: 8.5pt;")
        layout.addWidget(lbl_info)

        # 勾选框: 启用代理
        self.chk_enabled = QCheckBox("启用网络代理 (Global Proxy)")
        self.chk_enabled.toggled.connect(self._on_toggled)
        layout.addWidget(self.chk_enabled)

        # 地址输入框
        form_layout = QHBoxLayout()
        lbl_url = QLabel("代理 Server 地址:")
        lbl_url.setFixedWidth(110)
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("例如: http://127.0.0.1:7890 或 socks5://127.0.0.1:1080")
        form_layout.addWidget(lbl_url)
        form_layout.addWidget(self.txt_url)
        layout.addLayout(form_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #2a2e39;")
        layout.addWidget(line)

        # 底部按钮组
        btn_layout = QHBoxLayout()

        self.btn_test = QPushButton("⚡ 测试连通性")
        self.btn_test.setObjectName("btn_test")
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.clicked.connect(self._on_test_proxy)
        btn_layout.addWidget(self.btn_test)

        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 保存配置")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _load_config(self):
        cfg = get_proxy_config()
        enabled = cfg.get("enabled", False)
        proxy_url = cfg.get("proxy_url", "http://127.0.0.1:7890")

        self.chk_enabled.setChecked(enabled)
        self.txt_url.setText(proxy_url)
        self._on_toggled(enabled)

    def _on_toggled(self, checked: bool):
        if not self.is_testing:
            self.txt_url.setEnabled(checked)
            if checked:
                self.txt_url.setStyleSheet("QLineEdit { background-color: #1e222d; color: #ffffff; border: 1px solid #00F0FF; }")
            else:
                self.txt_url.setStyleSheet("QLineEdit { background-color: #181b24; color: #787b86; border: 1px solid #2a2e39; }")

    def _set_ui_testing_state(self, testing: bool):
        """测试连通性期间禁用其他保存、取消、修改控件，防并发死锁与重复误触发"""
        self.is_testing = testing
        self.btn_test.setEnabled(not testing)
        self.btn_save.setEnabled(not testing)
        self.btn_cancel.setEnabled(not testing)
        self.chk_enabled.setEnabled(not testing)
        self.txt_url.setEnabled(not testing and self.chk_enabled.isChecked())

        if testing:
            self.btn_test.setText("⏳ 测试中...")
        else:
            self.btn_test.setText("⚡ 测试连通性")

    def _on_test_proxy(self):
        url = self.txt_url.text().strip()
        if not url:
            QMessageBox.warning(self, "代理测试", "请先输入有效代理 Server 地址")
            return

        self._set_ui_testing_state(True)

        # 构建信号桥接器
        self.bridge = ProxyTestSignalBridge()
        self.bridge.result_signal.connect(self._on_test_result)

        # 启动 Python 原生 daemon 守护线程
        start_async_proxy_test(url, self.bridge)

    def _on_test_result(self, ok: bool, latency: float, msg: str):
        self._set_ui_testing_state(False)
        try:
            if ok:
                QMessageBox.information(self, "代理测试成功", f"✅ 代理连通成功！\n{msg}")
            else:
                QMessageBox.warning(self, "代理测试失败", f"❌ 代理连接失败:\n{msg}")
        except Exception as ex:
            print(f"[ProxySettingsDialog] 显示测试结果异常: {ex}")

    def _on_save(self):
        if self.is_testing:
            return

        enabled = self.chk_enabled.isChecked()
        proxy_url = self.txt_url.text().strip()

        if enabled and not proxy_url:
            QMessageBox.warning(self, "保存代理配置", "⚠️ 启用代理时必须填入有效的代理 Server 地址")
            return

        ok = save_proxy_config(enabled, proxy_url)
        if ok:
            self.accept()
        else:
            QMessageBox.critical(self, "保存错误", "❌ 代理配置保存失败，请检查文件权限")

    def _disconnect_bridge(self):
        """退出时断开信号槽连接，守护线程后台自然回收"""
        if self.bridge:
            try:
                self.bridge.result_signal.disconnect(self._on_test_result)
            except Exception:
                pass
            self.bridge = None

    def reject(self):
        if self.is_testing:
            self._set_ui_testing_state(False)
        self._disconnect_bridge()
        super().reject()

    def accept(self):
        if self.is_testing:
            self._set_ui_testing_state(False)
        self._disconnect_bridge()
        super().accept()

    def closeEvent(self, event):
        if self.is_testing:
            self._set_ui_testing_state(False)
        self._disconnect_bridge()
        super().closeEvent(event)
