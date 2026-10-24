# -*- coding: utf-8 -*-
"""ats/ui/fusion_ladder_dialog.py — 融合梯度监视器（所见即所得）。

三个页签对应三种"看得见"：
    1. 实时梯度：直接读 `logs/fusion_shadow/<today>.jsonl` 尾部，与实盘信号同源同一条流；
    2. 按日回放：选一个历史交易日，3 分钟内跑完整天，看到 L0~L4 与事后表现；
    3. 验收与复盘：填几只"走出来的答案"（如 688787,300296），看系统哪一天、几点、几级抓到。

设计约束：
    - 非模态独立窗口，不阻塞主界面；
    - 所有耗时任务在 QThread 里跑，UI 只负责画；
    - 任何数据缺失都显示"无数据"，不弹异常、不阻塞。
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from ats.fusion.adapter import today_str
from ats.fusion.replay import DayReplay, ReplayConfig, render_focus, render_report
from ats.fusion.review import load_records, render_markdown, suggest_cuts, summarize

_DARK_QSS = """
QWidget { background-color: #17171c; color: #d8d8e0; font-size: 9pt; }
QLabel { color: #b9b9c8; }
QPushButton {
    background-color: #24242e; color: #e6e6f0; border: 1px solid #3a3a48;
    border-radius: 3px; padding: 3px 10px;
}
QPushButton:hover { background-color: #30303e; border-color: #5a5a72; }
QPushButton:disabled { color: #666677; border-color: #2c2c36; }
QComboBox, QLineEdit, QSpinBox {
    background-color: #202028; color: #e6e6f0; border: 1px solid #3a3a48;
    border-radius: 3px; padding: 2px 6px;
}
QTabWidget::pane { border: 1px solid #2c2c36; }
QTabBar::tab {
    background: #1d1d24; color: #9a9aac; padding: 5px 14px;
    border: 1px solid #2c2c36; border-bottom: none;
}
QTabBar::tab:selected { background: #2a2a36; color: #ffcc66; }
QTableWidget {
    background-color: #14141a; alternate-background-color: #191921;
    gridline-color: #26262f; color: #d8d8e0; border: none;
}
QHeaderView::section {
    background-color: #23232d; color: #9fa4b8; border: none;
    border-right: 1px solid #2c2c36; border-bottom: 1px solid #2c2c36; padding: 4px;
}
QProgressBar { border: 1px solid #2c2c36; border-radius: 3px; text-align: center; color: #cfcfda; }
QProgressBar::chunk { background-color: #3a6ea5; }
QTextBrowser { background-color: #14141a; border: 1px solid #2c2c36; }
"""

_TIER_COLORS = {
    4: QColor("#ff5c5c"),
    3: QColor("#ffa64d"),
    2: QColor("#ffd75e"),
    1: QColor("#7fb3d5"),
    0: QColor("#6b6b7b"),
}


def _shadow_log_path(day: str = "") -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        root = get_app_root()
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "logs", "fusion_shadow", "{}.jsonl".format(day or today_str()))


def load_live_rows(day: str = "", max_lines: int = 3000) -> List[Dict[str, Any]]:
    """读影子日志尾部，按 code 取最新一条，按级别+RAR 排序。"""
    path = _shadow_log_path(day)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=max_lines)
    except Exception:
        return []

    latest: Dict[str, Dict[str, Any]] = {}
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        code = str(rec.get("code") or "")
        if not code:
            continue
        prev = latest.get(code)
        if prev is None or float(rec.get("ts") or 0) >= float(prev.get("ts") or 0):
            latest[code] = rec

    rows = list(latest.values())
    rows.sort(key=lambda r: (int((r.get("fusion") or {}).get("tier") or 0),
                             float((r.get("fusion") or {}).get("rar") or 0)), reverse=True)
    return rows


class ReplayWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, day: str, focus: List[str], top_n: int = 300, step: int = 1,
                 cuts_mode: str = "percentile", parent=None):
        super().__init__(parent)
        self.day = day
        self.focus = focus
        self.top_n = top_n
        self.step = step
        self.cuts_mode = cuts_mode

    def run(self) -> None:  # noqa: D401
        try:
            rp = DayReplay(config=ReplayConfig(
                top_n=self.top_n, step=self.step,
                focus_codes=tuple(self.focus), cuts_mode=self.cuts_mode,
            ))
            if not rp.cache:
                self.failed.emit("找不到分钟线缓存（G:/minute_kline_cache.pkl）")
                return
            day = self.day or (rp.days()[-1] if rp.days() else today_str())
            result = rp.run_day(day, progress=lambda a, b: self.progress.emit(a, b), focus=self.focus)
            self.done.emit(result)
        except Exception as exc:  # 线程内异常必须自己吞，否则整个窗口崩
            self.failed.emit("{}: {}".format(type(exc).__name__, exc))


class FusionLadderDialog(QWidget):
    """融合梯度监视器主窗口（非模态）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧬 融合梯度监视器 · SFL")
        self.setStyleSheet(_DARK_QSS)
        self.resize(1220, 760)
        self.setWindowFlags(Qt.WindowType.Window)

        self._worker: Optional[ReplayWorker] = None
        self._result = None
        self._replay_days: List[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- 顶部控制条 ----
        bar = QHBoxLayout()
        self.lbl_status = QLabel("状态：就绪")
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")
        bar.addWidget(self.lbl_status)
        bar.addStretch(1)

        bar.addWidget(QLabel("交易日"))
        self.cmb_day = QComboBox()
        self.cmb_day.setMinimumWidth(120)
        bar.addWidget(self.cmb_day)

        bar.addWidget(QLabel("标的数"))
        self.spin_top = QSpinBox()
        self.spin_top.setRange(50, 2000)
        self.spin_top.setSingleStep(50)
        self.spin_top.setValue(300)
        bar.addWidget(self.spin_top)

        bar.addWidget(QLabel("步长"))
        self.cmb_step = QComboBox()
        for s in (1, 2, 3):
            self.cmb_step.addItem("每{}根".format(s), s)
        bar.addWidget(self.cmb_step)

        self.btn_run = QPushButton("▶ 跑回放")
        self.btn_run.clicked.connect(self.run_replay)
        bar.addWidget(self.btn_run)

        self.btn_refresh = QPushButton("🔄 刷新实时")
        self.btn_refresh.clicked.connect(self.refresh_live)
        bar.addWidget(self.btn_refresh)

        root.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumHeight(10)
        root.addWidget(self.progress)

        # ---- 页签 ----
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.tbl_live = self._make_table([
            "级别", "代码", "名称", "RAR", "位", "接", "意", "环", "仓位%", "进场", "止损", "先手min", "来源",
        ])
        self.tabs.addTab(self.tbl_live, "实时梯度（影子流）")

        self.tbl_replay = self._make_table([
            "时间", "代码", "级别", "RAR", "仓位%", "涨幅%", "MFE%", "MAE%", "收盘%", "温度℃",
        ])
        self.tabs.addTab(self.tbl_replay, "按日回放")

        page3 = QWidget()
        v3 = QVBoxLayout(page3)
        v3.setContentsMargins(4, 4, 4, 4)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("验收标的"))
        self.ed_focus = QLineEdit("688787,300296")
        self.ed_focus.setPlaceholderText("逗号分隔，如 688787,300296")
        row3.addWidget(self.ed_focus, 1)
        self.btn_focus = QPushButton("跑验收")
        self.btn_focus.clicked.connect(self.run_focus)
        row3.addWidget(self.btn_focus)
        v3.addLayout(row3)
        self.txt_report = QTextBrowser()
        self.txt_report.setOpenExternalLinks(False)
        v3.addWidget(self.txt_report, 1)
        self.tabs.addTab(page3, "验收与复盘")

        self._init_days()
        self.refresh_live()

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    @staticmethod
    def _make_table(headers: List[str]) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        return tbl

    def _init_days(self) -> None:
        try:
            rp = DayReplay()
            self._replay_days = rp.days()
        except Exception:
            self._replay_days = []
        self.cmb_day.clear()
        if self._replay_days:
            for d in self._replay_days:
                self.cmb_day.addItem(d)
            self.cmb_day.setCurrentIndex(len(self._replay_days) - 1)
        else:
            self.cmb_day.addItem(today_str())
        self.cmb_day.addItem(today_str())
        self.cmb_day.setCurrentIndex(self.cmb_day.count() - 1)

    @staticmethod
    def _item(text: Any, color: Optional[QColor] = None, bold: bool = False) -> QTableWidgetItem:
        it = QTableWidgetItem(str(text))
        if color is not None:
            it.setForeground(color)
        if bold:
            f = QFont()
            f.setBold(True)
            it.setFont(f)
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it

    # ------------------------------------------------------------------
    # 实时
    # ------------------------------------------------------------------
    def refresh_live(self) -> None:
        rows = load_live_rows()
        tbl = self.tbl_live
        tbl.setRowCount(0)
        if not rows:
            self.lbl_status.setText("状态：今日暂无影子记录（确认 config/fusion_ladder.json enabled=true 且盘中运行）")
            self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")
            return

        tier_count = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        for r in rows:
            fusion = r.get("fusion") or {}
            tier = int(fusion.get("tier") or 0)
            tier_count[tier] = tier_count.get(tier, 0) + 1
            i = tbl.rowCount()
            tbl.insertRow(i)
            axes = fusion.get("axes") or {}
            entry = fusion.get("entry") or {}
            stop = fusion.get("stop") or {}
            band = ""
            if entry.get("price_lo") and entry.get("price_hi"):
                band = "{:.2f}~{:.2f}".format(float(entry["price_lo"]), float(entry["price_hi"]))
            vals = [
                "L{}".format(tier), r.get("code", ""), r.get("name", ""),
                fusion.get("rar", 0), axes.get("position", 0), axes.get("support", 0),
                axes.get("intent", 0), axes.get("regime", 0), fusion.get("size_pct", 0),
                band, stop.get("price", "-"), fusion.get("age_min", 0),
                ",".join(fusion.get("sources") or []),
            ]
            for c, v in enumerate(vals):
                tbl.setItem(i, c, self._item(v, _TIER_COLORS.get(tier), bold=(c == 0)))

        self.lbl_status.setText(
            "状态：今日影子 {} 条｜L4 {} / L3 {} / L2 {} / L1 {} / L0 {}".format(
                len(rows), tier_count[4], tier_count[3], tier_count[2], tier_count[1], tier_count[0]
            )
        )
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

    # ------------------------------------------------------------------
    # 回放
    # ------------------------------------------------------------------
    def _start_worker(self, focus: List[str]) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.lbl_status.setText("状态：回放进行中，请稍候…")
            return
        day = self.cmb_day.currentText().strip()
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_focus.setEnabled(False)
        self.lbl_status.setText("状态：回放 {} 中…".format(day))
        self.lbl_status.setStyleSheet("color:#ffd75e; font-weight:bold;")

        self._worker = ReplayWorker(
            day=day, focus=focus, top_n=self.spin_top.value(),
            step=int(self.cmb_step.currentData() or 1),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_replay_done)
        self._worker.failed.connect(self._on_replay_failed)
        self._worker.start()

    def _on_progress(self, cur: int, total: int) -> None:
        pct = int(cur * 100 / max(1, total))
        self.progress.setValue(pct)

    def _on_replay_failed(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.lbl_status.setText("状态：回放失败 — {}".format(msg))
        self.lbl_status.setStyleSheet("color:#ff5c5c; font-weight:bold;")

    def _on_replay_done(self, result) -> None:
        self._result = result
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.progress.setValue(100)

        rows = sorted(result.records, key=lambda r: (r["tier"], r["rar"]), reverse=True)[:800]
        tbl = self.tbl_replay
        tbl.setRowCount(0)
        for r in rows:
            i = tbl.rowCount()
            tbl.insertRow(i)
            vals = [
                r["time"], r["code"], r["tier_name"], r["rar"], r["size_pct"],
                r["pct"], r["mfe"], r["mae"], r["close_ret"], r["temp"],
            ]
            for c, v in enumerate(vals):
                tbl.setItem(i, c, self._item(v, _TIER_COLORS.get(r["tier"]), bold=(c == 2)))

        self.lbl_status.setText(
            "状态：{} 回放完成｜标的 {}｜评估 {}｜记录 {}｜分档 {}".format(
                result.day, result.meta.get("codes"), result.meta.get("evaluations"),
                result.meta.get("records"), result.meta.get("cuts_used") or "固定阈值",
            )
        )
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

        self.txt_report.setPlainText(render_report(result))

    def run_replay(self) -> None:
        self._start_worker([])

    def run_focus(self) -> None:
        codes = [c.strip() for c in self.ed_focus.text().split(",") if c.strip()]
        self.tabs.setCurrentIndex(2)
        self._start_worker(codes)

    # ------------------------------------------------------------------
    # 复盘
    # ------------------------------------------------------------------
    def refresh_review(self) -> None:
        day = self.cmb_day.currentText().strip()
        records = load_records(day)
        md = render_markdown(summarize(records), suggest_cuts(records), day)
        self.txt_report.setPlainText(md)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.progress.disconnect()
                self._worker.done.disconnect()
                self._worker.failed.disconnect()
            except Exception:
                pass
        super().closeEvent(event)


_INSTANCE: Optional[FusionLadderDialog] = None


def open_fusion_ladder_dialog(parent_window=None) -> Optional[FusionLadderDialog]:
    """单例打开（非模态，不抢焦点）。"""
    global _INSTANCE
    try:
        from PyQt6.sip import isdeleted

        if _INSTANCE is not None and not isdeleted(_INSTANCE):
            _INSTANCE.show()
            _INSTANCE.raise_()
            _INSTANCE.activateWindow()
            _INSTANCE.refresh_live()
            return _INSTANCE
    except Exception:
        _INSTANCE = None

    try:
        dlg = FusionLadderDialog(parent=parent_window)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dlg.show()
        _INSTANCE = dlg
        return dlg
    except Exception:
        return None
