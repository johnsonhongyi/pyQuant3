"""Qt entry point for explicitly initiated Codex CLI research conversations."""

import json
import threading
import html
import re
import time
from datetime import datetime
from uuid import uuid4

from PyQt6.QtCore import QThread, QTimer, QSettings, Qt, QEvent, pyqtSignal
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QTextBrowser, QComboBox, QSizePolicy, QSplitter, QProgressBar
from sys_utils import safe_resolve_path
from ats.ui.responsive_flow import ResponsiveFlow

from ats.llm.ipo_codex_chat import ask_codex, collect_context, latest_dialogue, list_analyses, model_choices

_ACTIVE_WORKERS = set()


class _CodeEdit(QLineEdit):
    def contextMenuEvent(self, event):
        text = QApplication.clipboard().text().strip()
        match = re.fullmatch(r"(?:sh|sz|bj)?([0-9]{6})(?:\.(?:sh|sz|bj))?", text, re.IGNORECASE)
        if match and not self.isReadOnly():
            self.setText(match.group(1))
            self.setFocus()
            self.returnPressed.emit()
            event.accept()
            return
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        paste = menu.addAction("粘贴代码")
        paste.setEnabled(not self.isReadOnly())
        paste.triggered.connect(self.paste)
        menu.exec(event.globalPos())
        menu.deleteLater()


class _ConversationView(QTextBrowser):
    def loadResource(self, resource_type, name):
        # Answers may contain Markdown images/links; do not load external resources.
        return None


class _DialogueWorker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, root, session, question, ticker, model, restore=False, record_id=None, effort="medium"):
        super().__init__()
        self.arguments = (root, session, question, ticker, model)
        self.cancel = threading.Event()
        self.restore = restore
        self.record_id, self.effort = record_id, effort

    def _emit(self, result):
        try:
            result["analyses"] = list_analyses(self.arguments[0])
        except (OSError, ValueError):
            result["analyses"] = []
        result["models"] = model_choices()
        self.result.emit(result)

    def run(self):
        try:
            root, session, question, ticker, model = self.arguments
            if self.restore:
                self._emit(latest_dialogue(root, self.record_id))
            elif question is None:
                context, digest = collect_context(root, ticker)
                self._emit({"context": context, "context_hash": digest})
            else:
                self._emit(ask_codex(*self.arguments, cancel_event=self.cancel, reasoning_effort=self.effort))
        except Exception as exc:
            self.failed.emit(str(exc)[:500])


class CodexIPODialogue(QWidget):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.session = uuid4().hex
        self.worker = None
        self.closing = False
        self._messages = []
        self._preview_pending = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)
        self._preview_timer.timeout.connect(self._auto_preview)
        settings_dir = safe_resolve_path(root) / "data/ipo_learning"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self._question_settings = QSettings(str(settings_dir / "ui_layout.ini"), QSettings.Format.IniFormat)
        saved_questions = self._question_settings.value("codex/recent_questions", [])
        self._recent_questions = [q for q in saved_questions if isinstance(q, str)][:20] if isinstance(saved_questions, list) else []
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(500)
        self._busy_timer.timeout.connect(self._update_busy)
        layout = QVBoxLayout(self)
        note = QLabel("Codex CLI · 使用本机 ChatGPT 登录 · 仅由你点击发送时调用。\n"
                      "发送内容：问题、最近对话、IPO信号/回放摘要及隔离模拟账户；不发送密钥或配置文件。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.setMinimumWidth(0)
        row = ResponsiveFlow()
        self.ticker = _CodeEdit()
        self.ticker.setPlaceholderText("股票代码（留空分析全局）")
        self.ticker.setMaxLength(6)
        self.ticker.setMaximumWidth(150)
        self.security_name = QLabel("全局分析")
        self.security_name.setTextFormat(Qt.TextFormat.PlainText)
        self.security_name.setMinimumWidth(0)
        self.security_name.setMaximumWidth(150)
        self.analysis_history = QComboBox()
        self.analysis_history.addItem("分析历史（最近100次）", None)
        self.analysis_history.setMinimumWidth(0)
        self.analysis_history.setMaximumWidth(450)
        self.analysis_history.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.analysis_history.setMinimumContentsLength(22)
        self.analysis_history.setToolTip("选择历史分析，恢复对应代码、证据和对话")
        self.model = QComboBox()
        self.model.addItem("gpt-6-luna")
        self.effort = QComboBox()
        self._model_options = [{"model": "gpt-6-luna", "levels": ["low", "medium", "high"]}]
        self._update_effort()
        self.model.currentTextChanged.connect(self._update_effort)
        row.addWidget(self.ticker)
        row.addWidget(self.security_name)
        row.addWidget(self.analysis_history)
        row.addWidget(self.model)
        row.addWidget(self.effort)
        for combo in (self.analysis_history, self.model, self.effort):
            combo.setMinimumWidth(0)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addLayout(row)
        self.status = QLabel("输入六位代码后自动读取；回车立即刷新。Ctrl+Enter 发送问题。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(6)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        self.evidence.setMinimumHeight(45)
        self.evidence.setPlaceholderText("数据预览、来源时间与证据哈希")
        self.toggle_evidence = QPushButton("收起证据摘要")
        self.toggle_evidence.clicked.connect(self._toggle_evidence)
        layout.addWidget(self.toggle_evidence)
        self.transcript = _ConversationView()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText("在这里与 Codex 讨论 IPO 数据、审核结果和模拟账户对账。")
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.evidence)
        self.splitter.addWidget(self.transcript)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([100, 400])
        self.splitter.setMinimumWidth(0)
        layout.addWidget(self.splitter, 1)
        self.recent_questions = QComboBox()
        self.recent_questions.setMinimumWidth(0)
        self.recent_questions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.recent_questions.setMinimumContentsLength(20)
        self.recent_questions.activated.connect(self._reuse_question)
        layout.addWidget(self.recent_questions)
        self._refresh_questions()
        self.question = QPlainTextEdit()
        self.question.setMaximumHeight(100)
        self.question.setPlaceholderText("例如：近期为什么没有买入？请结合信号、回放和模拟账户逐项核对。")
        self.question.installEventFilter(self)
        layout.addWidget(self.question)
        actions = ResponsiveFlow()
        self.preview = QPushButton("预览当前数据")
        self.send = QPushButton("发送至 Codex CLI")
        self.analyze = QPushButton("分析 IPO")
        self.reconcile = QPushButton("审核 / 对账")
        self.new = QPushButton("新对话")
        self.restore = QPushButton("恢复最近对话")
        self.stop = QPushButton("取消")
        self.stop.setEnabled(False)
        for button in (self.preview, self.analyze, self.reconcile, self.send, self.new, self.restore, self.stop):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.preview.clicked.connect(lambda: self._start(None))
        self.send.clicked.connect(lambda: self._start(self.question.toPlainText()))
        self.analyze.clicked.connect(lambda: self._start("分析所选IPO或整体信号与纸面回放，列出事实、推断、观察建议和数据缺口。"))
        self.reconcile.clicked.connect(lambda: self._start("审核IPO信号和模拟账户，核对现金、持仓、数量、价格与费用，区分历史回放和当前模拟交易，并列出异常。"))
        self.new.clicked.connect(self._new_session)
        self.restore.clicked.connect(lambda: self._start(None, restore=True))
        self.stop.clicked.connect(self._cancel)
        self.ticker.textChanged.connect(self._schedule_preview)
        self.ticker.returnPressed.connect(self._auto_preview)
        self.analysis_history.activated.connect(self._select_analysis)
        self._render_messages()
        QTimer.singleShot(0, self._auto_preview)

    def _toggle_evidence(self):
        visible = not self.evidence.isHidden()
        self.evidence.setVisible(not visible)
        self.toggle_evidence.setText("展开证据摘要" if visible else "收起证据摘要")

    def _update_effort(self, *_):
        previous = self.effort.currentData() or "medium"
        levels = next((row["levels"] for row in self._model_options
                       if row["model"] == self.model.currentText()), ["low", "medium", "high"])
        labels = {"low": "快速 · low", "medium": "均衡（推荐）· medium", "high": "深入审核 · high",
                  "xhigh": "深度研究 · xhigh", "max": "最大强度 · max"}
        self.effort.clear()
        for level in levels:
            self.effort.addItem(labels[level], level)
        index = self.effort.findData(previous)
        self.effort.setCurrentIndex(index if index >= 0 else 0)
        self.effort.setToolTip("推理深度，不代表买入推荐强度。高档位可能耗时更长，调用仍有180秒上限。")

    def _select_analysis(self, index):
        record_id = self.analysis_history.itemData(index)
        if record_id is not None:
            self._start(None, restore=True, record_id=record_id)

    def eventFilter(self, watched, event):
        if (watched is self.question and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._start(self.question.toPlainText())
            return True
        return super().eventFilter(watched, event)

    def _schedule_preview(self, text):
        self.security_name.setText("识别中…" if text else "全局分析")
        if not text or (len(text) == 6 and text.isascii() and text.isdigit()):
            self._preview_timer.start()

    def _auto_preview(self):
        self._preview_timer.stop()
        if self.closing:
            return
        if self.worker is not None:
            self._preview_pending = True
            return
        self._preview_pending = False
        self._start(None)

    def _add_message(self, role, text, stamp=None):
        self._messages.append((role, text, stamp or datetime.now().strftime("%H:%M:%S")))
        self._render_messages()

    def _render_messages(self, restored=False):
        parts = ["<h3 style='color:#7c3aed'>会话 " + self.session[:8]
                 + (" · 已恢复历史对话" if restored else " · 当前对话") + "</h3>"]
        turn = 0
        for role, text, stamp in self._messages:
            if role == "你":
                turn += 1
            color, background = ("#075985", "#e0f2fe") if role == "你" else ("#166534", "#ecfdf5")
            if role == "系统":
                color, background = "#92400e", "#fffbeb"
            if role == "Codex":
                document = QTextDocument()
                document.setMarkdown(html.escape(text))
                body = document.toHtml()
            else:
                body = html.escape(text).replace("\n", "<br>")
            parts.append(f"<table width='100%' bgcolor='{background}' cellpadding='10'><tr><td style='color:#172b4d'>"
                         f"<b style='color:{color}'>第 {turn} 轮 · {role} · {html.escape(stamp)}</b>"
                         f"<br>{body}</td></tr></table><br>")
        self.transcript.setHtml("".join(parts))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _new_session(self):
        self.session = uuid4().hex
        self._messages.clear()
        self._render_messages()
        self.status.setText("已开始新对话；此前记录保留在本地审计库。")

    def _refresh_questions(self):
        self.recent_questions.clear()
        self.recent_questions.addItem("复用最近20条问题（选择后可编辑，不自动发送）", None)
        for question in self._recent_questions:
            self.recent_questions.addItem(question.replace("\n", " ")[:90], question)
            self.recent_questions.setItemData(self.recent_questions.count()-1, question, Qt.ItemDataRole.ToolTipRole)

    def _reuse_question(self, index):
        question = self.recent_questions.itemData(index)
        if question:
            self.question.setPlainText(question)
            self.question.setFocus()

    def _update_busy(self):
        if not self.closing:
            elapsed = int(time.monotonic() - self._started_at)
            self.status.setText(f"{self._busy_label} · 已等待{elapsed}秒 · 后台运行中，可取消")

    def _start(self, question, restore=False, record_id=None):
        if self.worker is not None:
            return
        self._preview_timer.stop()
        ticker = self.ticker.text().strip()
        if ticker and (len(ticker) != 6 or not ticker.isascii() or not ticker.isdigit()):
            self.status.setText("股票代码须为六位数字，或留空分析全局。")
            return
        if question is not None and not question.strip():
            self.status.setText("请输入问题。")
            return
        self.worker = _DialogueWorker(self.root, self.session, question, self.ticker.text().strip(),
                                      self.model.currentText(), restore, record_id, self.effort.currentData())
        worker = self.worker
        _ACTIVE_WORKERS.add(worker)
        worker.result.connect(self._result)
        worker.failed.connect(self._error)
        worker.finished.connect(self._finished)
        worker.finished.connect(lambda: _ACTIVE_WORKERS.discard(worker))
        worker.finished.connect(worker.deleteLater)
        for button in (self.preview, self.analyze, self.reconcile, self.send, self.new, self.restore):
            button.setEnabled(False)
        self.stop.setEnabled(True)
        self.analysis_history.setEnabled(False)
        self.status.setText("读取证据…" if question is None else "Codex CLI 分析中，最长180秒；可取消。")
        self._busy_label = "正在恢复历史" if restore else "正在读取本地证据" if question is None else "正在读取证据并调用Codex，等待响应（调用最长180秒）"
        self._started_at = time.monotonic()
        self.progress.show()
        self._busy_timer.start()
        if question is not None:
            self._add_message("你", question)
            self._recent_questions = [question] + [q for q in self._recent_questions if q != question]
            self._recent_questions = self._recent_questions[:20]
            self._question_settings.setValue("codex/recent_questions", self._recent_questions)
            self._question_settings.sync()
            self._refresh_questions()
        worker.start()

    def _result(self, result):
        self._busy_timer.stop()
        if self.closing:
            return
        self.evidence.setPlainText("证据哈希：" + result["context_hash"] + "\n" +
                                   json.dumps(result["context"], ensure_ascii=False, indent=2))
        if "models" in result:
            selected = self.model.currentText()
            self._model_options = result["models"]
            self.model.blockSignals(True)
            self.model.clear()
            self.model.addItems([item["model"] for item in self._model_options])
            self.model.setCurrentText(selected)
            self.model.blockSignals(False)
            self._update_effort()
        if "analyses" in result:
            self.analysis_history.clear()
            self.analysis_history.addItem("分析历史（最近100次）", None)
            for item in result["analyses"]:
                label = f"{item['created_at'][:16].replace('T', ' ')} · {item['ticker'] or '全局'} {item['name']} · {item['question']}"
                self.analysis_history.addItem(label, item["id"])
        if "history" in result:
            self.session = result["session"]
            self.ticker.blockSignals(True)
            self.ticker.setText(result["context"].get("ticker", ""))
            self.ticker.blockSignals(False)
            self._preview_timer.stop()
            self._preview_pending = False
            if "record_id" in result:
                self.analysis_history.setCurrentIndex(self.analysis_history.findData(result["record_id"]))
            settings = result["context"].get("analysis_settings", {})
            if settings.get("model"):
                self.model.setCurrentText(settings["model"])
            level_index = self.effort.findData(settings.get("reasoning_effort"))
            if level_index >= 0:
                self.effort.setCurrentIndex(level_index)
            self._messages.clear()
            for turn in result["history"]:
                self._messages.extend([("你", turn["question"], "历史记录"),
                                       ("Codex", turn["answer"], "历史记录")])
            self._render_messages(restored=True)
        if result["context"].get("ticker", "") == self.ticker.text().strip():
            self.security_name.setText(result["context"].get("security_name", "名称暂缺"))
        if "answer" in result:
            self._add_message("Codex", result["answer"])
        self.status.setText("完成。" if "answer" in result else
                            "已恢复最近四轮对话；继续提问时会读取最新数据。" if "history" in result else
                            "预览完成；发送时会重新读取最新摘要。")

    def _error(self, message):
        self._busy_timer.stop()
        if not self.closing:
            explanations = {
                "CLI_USAGE_LIMIT": "账户使用额度已耗尽（可能为5小时或周额度）；请查看Codex账户用量及重置时间，稍后重试。当前回报未提供可验证的重置时间。",
                "CLI_RATE_LIMIT": "请求过于频繁，服务限流；请稍后重试。",
                "CLI_AUTH_REQUIRED": "登录已失效；请在终端执行codex login status检查并重新codex login。",
                "CLI_NETWORK_ERROR": "连接服务失败或网络超时；请检查网络、代理后重试。",
                "CLI_MODEL_UNAVAILABLE": "当前账户无法使用所选模型；请选择其他模型。",
                "CLI_LOCAL_PERMISSION_BLOCKED": "本机文件或进程访问被拒绝；请检查Codex目录和运行目录权限。",
                "CLI_START_OR_IO_FAILED": "Codex子进程启动或读写失败；请查看诊断日志中的系统错误码。",
                "CLI_TIMEOUT": "等待响应超时；本次调用已停止，可保留问题后重试。",
                "CLI_CANCELLED": "已取消本次调用，问题已保留。",
            }
            detail = explanations.get(message, "未识别的调用错误，请提供错误码与诊断日志。")
            self.status.setText(f"调用未完成：{detail} [{message}]")
            self._add_message("系统", f"调用未完成：{detail}\n错误码：{message}")
            self._add_message("系统", "诊断日志：运行数据根目录下 logs/ipo_codex_diagnostics.jsonl（不含提问正文和认证信息）。")

    def _finished(self):
        self._busy_timer.stop()
        self.progress.hide()
        self.worker = None
        if not self.closing:
            for button in (self.preview, self.analyze, self.reconcile, self.send, self.new, self.restore):
                button.setEnabled(True)
            self.stop.setEnabled(False)
            self.analysis_history.setEnabled(True)
            if self._preview_pending:
                QTimer.singleShot(0, self._auto_preview)

    def _cancel(self):
        self._busy_timer.stop()
        if self.worker is not None:
            self.worker.cancel.set()
            self.status.setText("正在取消并清理CLI进程…")

    def shutdown(self, timeout_ms=10000):
        self.closing = True
        self._preview_timer.stop()
        self._busy_timer.stop()
        self._cancel()
        if self.worker is not None:
            self.worker.wait(max(0, int(timeout_ms)))
